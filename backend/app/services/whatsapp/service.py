"""WhatsApp: draft -> human approval -> send.

Two invariants enforced here and covered by tests:
1. A message can only leave BaatX after an explicit approval by a permitted user.
2. Internal-only fields (lead score, sentiment, objections, competitors, internal
   notes) can never appear in an outbound message.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.core.errors import (
    ApprovalRequiredError,
    ConflictError,
    ProviderUnavailableError,
    ValidationError,
)
from app.core.phone import mask_phone
from app.models.enums import WhatsAppMessageStatus
from app.models.whatsapp import WhatsAppMessage
from app.repositories.base import TenantRepository
from app.repositories.customer_repo import CustomerRepository
from app.schemas.whatsapp import (
    WhatsAppDraftRequest,
    WhatsAppDraftResponse,
    WhatsAppSendRequest,
    WhatsAppSendResponse,
)
from app.services.ai.base import LLMProvider
from app.services.ai.prompts import WHATSAPP_SYSTEM_PROMPT

log = get_logger(__name__)

# Never allowed in an outbound customer message.
FORBIDDEN_PATTERNS = re.compile(
    r"\b(lead score|lead_score|sentiment|objection|objections|competitor|competitors|"
    r"internal|crm|ai note|ai-generated|purchase intent|pain point|strategy)\b",
    re.IGNORECASE,
)


class WhatsAppRepository(TenantRepository[WhatsAppMessage]):
    model = WhatsAppMessage


class WhatsAppService:
    def __init__(
        self,
        session: AsyncSession,
        business_id: uuid.UUID,
        *,
        llm: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.business_id = business_id
        self.settings = settings or get_settings()
        self.llm = llm
        self.repo = WhatsAppRepository(session, business_id)
        self.customers = CustomerRepository(session, business_id)

    async def draft(
        self, request: WhatsAppDraftRequest, *, actor_id: uuid.UUID | None
    ) -> WhatsAppDraftResponse:
        customer = await self.customers.get_or_404(request.customer_id)
        if not customer.normalized_phone:
            raise ValidationError(
                "no phone",
                user_message="Add a phone number for this customer before drafting a message.",
            )

        facts = {
            "customer_name": customer.name,
            "requirement": customer.requirement,
            "product": customer.product,
            "location": customer.location,
            "budget": _budget_phrase(customer),
            "topic_discussed": customer.topic or customer.query,
            "next_contact": (
                customer.next_follow_up_at.strftime("%A") if customer.next_follow_up_at else None
            ),
            "purpose": request.purpose,
            "extra_instruction": request.extra_instruction,
        }
        body = self._strip_internal(await self._generate(facts))

        message = WhatsAppMessage(
            business_id=self.business_id,
            customer_id=customer.id,
            to_phone=customer.normalized_phone,
            body=body,
            status=WhatsAppMessageStatus.DRAFT,
            drafted_by_ai=True,
        )
        self.session.add(message)
        await self.session.flush()

        return WhatsAppDraftResponse(
            message_id=message.id,
            customer_id=customer.id,
            to_phone_masked=mask_phone(customer.normalized_phone),
            body=body,
            status=message.status,
        )

    async def send(
        self, request: WhatsAppSendRequest, *, actor_id: uuid.UUID | None
    ) -> WhatsAppSendResponse:
        if not request.approved:
            raise ApprovalRequiredError("approval flag not set")

        message = await self.repo.get_or_404(request.message_id)
        if message.status == WhatsAppMessageStatus.SENT:
            raise ConflictError("already sent", user_message="This message has already been sent.")
        if message.status == WhatsAppMessageStatus.DISCARDED:
            raise ConflictError("message discarded")

        if request.edited_body:
            message.body = self._strip_internal(request.edited_body.strip())
        message.status = WhatsAppMessageStatus.APPROVED
        message.approved_by_user_id = actor_id
        message.approved_at = datetime.now(UTC)
        await self.session.flush()

        if not self.settings.whatsapp_enabled:
            raise ProviderUnavailableError(
                "whatsapp disabled",
                user_message="WhatsApp sending isn't enabled for your business yet.",
            )

        try:
            provider_id = await self._send_via_provider(message.to_phone, message.body)
        except httpx.HTTPError as exc:
            message.status = WhatsAppMessageStatus.FAILED
            message.error_message = "Delivery failed"
            await self.session.flush()
            raise ProviderUnavailableError(
                "whatsapp send failed",
                user_message="We couldn't send that message. Please try again.",
            ) from exc

        message.status = WhatsAppMessageStatus.SENT
        message.sent_at = datetime.now(UTC)
        message.provider_message_id = provider_id
        await self.session.flush()
        log.info("whatsapp_sent", message_id=str(message.id))

        return WhatsAppSendResponse(
            message_id=message.id,
            status=message.status,
            sent_at=message.sent_at,
            provider_message_id=provider_id,
        )

    async def discard(self, message_id: uuid.UUID) -> None:
        message = await self.repo.get_or_404(message_id)
        if message.status == WhatsAppMessageStatus.SENT:
            raise ConflictError("already sent")
        message.status = WhatsAppMessageStatus.DISCARDED
        await self.session.flush()

    # ---------------- internals ----------------
    async def _generate(self, facts: dict) -> str:
        if self.llm is None:
            return _template_message(facts)
        try:
            result = await self.llm.complete_json(
                system_prompt=WHATSAPP_SYSTEM_PROMPT,
                user_prompt=json.dumps({k: v for k, v in facts.items() if v}, ensure_ascii=False)[
                    :3000
                ],
                max_output_tokens=400,
            )
            body = (json.loads(result.content or "{}").get("message") or "").strip()
            return body or _template_message(facts)
        except Exception:  # noqa: BLE001 - a draft must always be produced
            log.info("whatsapp_draft_fallback")
            return _template_message(facts)

    def _strip_internal(self, body: str) -> str:
        cleaned = " ".join(body.split())[:1000]
        kept = [line for line in cleaned.split(". ") if not FORBIDDEN_PATTERNS.search(line)]
        result = ". ".join(kept).strip()
        if not result:
            raise ValidationError(
                "message emptied by safety filter",
                user_message="This message contained internal details. Please rewrite it.",
            )
        return result

    async def _send_via_provider(self, to_phone: str, body: str) -> str:
        url = (
            f"{self.settings.whatsapp_api_base}/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone.lstrip("+"),
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        return (response.json().get("messages") or [{}])[0].get("id", "")


def _budget_phrase(customer) -> str | None:  # noqa: ANN001
    if customer.budget_max is None and customer.budget_min is None:
        return None
    value = float(customer.budget_max or customer.budget_min)
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:.2f} crore".replace(".00", "")
    if value >= 100_000:
        return f"₹{value / 100_000:.2f} lakh".replace(".00", "")
    return f"₹{value:,.0f}"


def _template_message(facts: dict) -> str:
    """Deterministic fallback draft - still customer-safe, no internal fields."""
    name = facts.get("customer_name") or "there"
    parts = [f"Hi {name},"]
    requirement = facts.get("requirement") or facts.get("product")
    if requirement:
        detail = f"as discussed, you're looking for {requirement}"
        if facts.get("budget"):
            detail += f" around {facts['budget']}"
        if facts.get("location"):
            detail += f" in {facts['location']}"
        parts.append(detail + ".")
    if facts.get("topic_discussed"):
        parts.append(f"We discussed {facts['topic_discussed']}.")
    if facts.get("next_contact"):
        parts.append(f"I'll connect with you again on {facts['next_contact']}.")
    parts.append("Please let me know if you have any additional requirements.")
    return " ".join(parts)
