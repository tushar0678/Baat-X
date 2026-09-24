"""WhatsApp: nothing leaves BaatX without explicit approval, and never internals."""

from __future__ import annotations

import pytest

from app.core.errors import ApprovalRequiredError, ProviderUnavailableError, ValidationError
from app.models.crm import Customer
from app.models.enums import LeadStatus, WhatsAppMessageStatus
from app.schemas.whatsapp import WhatsAppDraftRequest, WhatsAppSendRequest
from app.services.whatsapp.service import WhatsAppService
from factories import make_business


async def seed_customer(db, business) -> Customer:  # noqa: ANN001
    customer = Customer(
        business_id=business.id,
        name="Rajesh",
        phone="9876543210",
        normalized_phone="+919876543210",
        requirement="2BHK",
        location="Noida",
        budget_max=7_000_000,
        topic="availability and pricing",
        lead_status=LeadStatus.INTERESTED,
        lead_score=88,
        objections=["price too high"],
        competitors=["Other Builders Ltd"],
    )
    db.add(customer)
    await db.flush()
    return customer


@pytest.mark.anyio
async def test_draft_is_created_but_not_sent(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await seed_customer(db, business)
    service = WhatsAppService(db, business.id, llm=None)

    draft = await service.draft(WhatsAppDraftRequest(customer_id=customer.id), actor_id=user.id)
    assert draft.status == WhatsAppMessageStatus.DRAFT
    assert draft.to_phone_masked == "+91 XXXXX 43210"
    assert "Rajesh" in draft.body
    assert "approval" in draft.disclaimer.lower()


@pytest.mark.anyio
async def test_draft_never_contains_internal_information(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await seed_customer(db, business)
    service = WhatsAppService(db, business.id, llm=None)

    body = (
        await service.draft(WhatsAppDraftRequest(customer_id=customer.id), actor_id=user.id)
    ).body.lower()
    for forbidden in ("lead score", "88", "objection", "competitor", "sentiment", "internal"):
        assert forbidden not in body


@pytest.mark.anyio
async def test_send_without_approval_is_refused(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await seed_customer(db, business)
    service = WhatsAppService(db, business.id, llm=None)
    draft = await service.draft(WhatsAppDraftRequest(customer_id=customer.id), actor_id=user.id)

    with pytest.raises(ApprovalRequiredError):
        await service.send(
            WhatsAppSendRequest(message_id=draft.message_id, approved=False), actor_id=user.id
        )

    message = await service.repo.get(draft.message_id)
    assert message.status == WhatsAppMessageStatus.DRAFT
    assert message.sent_at is None


@pytest.mark.anyio
async def test_approved_send_stops_when_provider_disabled(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await seed_customer(db, business)
    service = WhatsAppService(db, business.id, llm=None)
    draft = await service.draft(WhatsAppDraftRequest(customer_id=customer.id), actor_id=user.id)

    with pytest.raises(ProviderUnavailableError):
        await service.send(
            WhatsAppSendRequest(message_id=draft.message_id, approved=True), actor_id=user.id
        )

    message = await service.repo.get(draft.message_id)
    assert message.status == WhatsAppMessageStatus.APPROVED
    assert message.approved_by_user_id == user.id
    assert message.sent_at is None


@pytest.mark.anyio
async def test_edited_body_is_filtered_for_internal_terms(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await seed_customer(db, business)
    service = WhatsAppService(db, business.id, llm=None)
    draft = await service.draft(WhatsAppDraftRequest(customer_id=customer.id), actor_id=user.id)

    with pytest.raises((ValidationError, ProviderUnavailableError)):
        await service.send(
            WhatsAppSendRequest(
                message_id=draft.message_id,
                approved=True,
                edited_body="Your lead score is 88 and our competitor is cheaper",
            ),
            actor_id=user.id,
        )
    message = await service.repo.get(draft.message_id)
    assert "lead score" not in message.body.lower()
