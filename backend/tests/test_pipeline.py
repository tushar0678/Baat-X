"""End-to-end pipeline behaviour: Tell AI -> extraction -> review -> CRM update."""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.enums import ConversationSource, FollowUpType, JobStatus, LeadStatus
from app.schemas.ai import ApplyExtractionRequest
from app.services.ai.base import LLMResult
from app.services.ai.pipeline import AIProcessingService
from app.services.ai.stt_providers import NullSTT
from app.services.storage.providers import LocalStorage
from factories import make_business

RAJESH_EXTRACTION = {
    "customer_name": {"value": "Rajesh", "confidence": 0.98, "source_text": "Rajesh se baat hui"},
    "phone_number": {"value": "9876543210", "confidence": 0.99, "source_text": None},
    "requirement": {"value": "2BHK", "confidence": 0.96, "source_text": "2BHK chahiye"},
    "budget": {"value": "70 lakh", "confidence": 0.94, "source_text": "around 70 lakh"},
    "location": {"value": "Noida", "confidence": 0.93, "source_text": "Noida mein"},
    "purchase_intent": {"value": "high", "confidence": 0.9, "source_text": None},
    "lead_status": {"value": "interested", "confidence": 0.92, "source_text": None},
    "customer_query": {"value": "Availability and pricing", "confidence": 0.9,
                       "source_text": None},
    "query_categories": {"value": ["availability", "pricing"], "confidence": 0.9,
                         "source_text": None},
    "summary": "Customer is interested in a 2BHK in Noida around 70 lakh.",
    "follow_up": {
        "required": True,
        "date": "Friday",
        "time": None,
        "type": "call_customer",
        "action": "Call customer",
        "reason": "Customer requested callback",
        "customer_requested_callback": True,
        "confidence": 0.91,
    },
    "language_detected": "hinglish",
}


class FakeLLM:
    """Deterministic stand-in for Azure OpenAI."""

    name = "fake"
    model = "fake-model"

    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or RAJESH_EXTRACTION
        self.calls = 0

    async def complete_json(self, **_: object) -> LLMResult:
        self.calls += 1
        return LLMResult(content=json.dumps(self.payload), model=self.model)

    async def complete_text(self, **_: object) -> LLMResult:
        return LLMResult(content="", model=self.model)

    async def healthy(self) -> bool:
        return True


def build_service(db, business, llm=None) -> AIProcessingService:  # noqa: ANN001
    from app.config.settings import get_settings

    return AIProcessingService(
        db,
        business_id=business.id,
        llm=llm or FakeLLM(),
        stt=NullSTT(),
        storage=LocalStorage(get_settings()),
        timezone=business.timezone,
    )


async def run_tell_ai(db, business, user, text: str, key: str | None = None):  # noqa: ANN001, ANN201
    service = build_service(db, business)
    job, _ = await service.create_job(
        source=ConversationSource.TELL_AI,
        idempotency_key=key or uuid.uuid4().hex,
        user_id=user.id,
        transcript_text=text,
    )
    extraction = await service.process_job(job.id)
    return service, job, extraction


@pytest.mark.anyio
async def test_tell_ai_creates_customer_followup_and_timeline(db) -> None:
    business, user = await make_business(db)
    service, job, extraction = await run_tell_ai(
        db,
        business,
        user,
        "Aaj Rajesh se baat hui. Usko Noida mein 2BHK chahiye around 70 lakh. "
        "Friday ko call karna hai.",
    )

    assert job.status == JobStatus.AWAITING_REVIEW
    assert extraction.overall_confidence >= 0.85

    review = await service.build_review(extraction)
    assert review.title == "Here's what I understood"
    assert {item.key for item in review.items} >= {"customer_name", "requirement", "budget"}
    assert review.follow_up.resolved_due_at is not None

    result = await service.apply_extraction(
        extraction.id, ApplyExtractionRequest(), actor_id=user.id
    )
    customer = await service.customers.customers.get(result.customer_id)

    assert customer.name == "Rajesh"
    assert customer.normalized_phone == "+919876543210"
    assert customer.requirement == "2BHK"
    assert float(customer.budget_max) == 7_000_000
    assert customer.lead_status == LeadStatus.INTERESTED
    assert result.follow_up_id is not None

    follow_up = await service.follow_ups.repo.get(result.follow_up_id)
    assert follow_up.type == FollowUpType.CALL_CUSTOMER
    assert follow_up.customer_requested_callback is True
    assert follow_up.created_by_ai is True

    timeline = await service.customers.timeline(customer.id)
    kinds = {entry.kind for entry in timeline.entries}
    assert "conversation" in kinds and "follow_up_created" in kinds


@pytest.mark.anyio
async def test_same_phone_in_two_businesses_stays_isolated(db) -> None:
    business_a, user_a = await make_business(db, name="A")
    business_b, user_b = await make_business(db, name="B")

    for business, user in ((business_a, user_a), (business_b, user_b)):
        service, _, extraction = await run_tell_ai(db, business, user, "Rajesh called")
        await service.apply_extraction(extraction.id, ApplyExtractionRequest(), actor_id=user.id)

    from app.repositories.customer_repo import CustomerRepository

    repo_a = CustomerRepository(db, business_a.id)
    repo_b = CustomerRepository(db, business_b.id)
    customer_a = await repo_a.get_by_normalized_phone("+919876543210")
    customer_b = await repo_b.get_by_normalized_phone("+919876543210")

    assert customer_a is not None and customer_b is not None
    assert customer_a.id != customer_b.id
    # Cross-tenant reads must return nothing, not the other tenant's row.
    assert await repo_a.get(customer_b.id) is None
    assert await repo_b.get(customer_a.id) is None


@pytest.mark.anyio
async def test_low_confidence_cannot_overwrite_high_confidence(db) -> None:
    business, user = await make_business(db)

    service, _, extraction = await run_tell_ai(db, business, user, "first call")
    result = await service.apply_extraction(
        extraction.id, ApplyExtractionRequest(), actor_id=user.id
    )

    weak = dict(RAJESH_EXTRACTION)
    weak["requirement"] = {"value": "3BHK", "confidence": 0.31, "source_text": None}
    weak["budget"] = {"value": "40 lakh", "confidence": 0.2, "source_text": None}

    service2 = build_service(db, business, llm=FakeLLM(weak))
    job2, _ = await service2.create_job(
        source=ConversationSource.TELL_AI,
        idempotency_key=uuid.uuid4().hex,
        user_id=user.id,
        transcript_text="second call",
    )
    extraction2 = await service2.process_job(job2.id)
    result2 = await service2.apply_extraction(
        extraction2.id, ApplyExtractionRequest(), actor_id=user.id
    )

    customer = await service2.customers.customers.get(result.customer_id)
    assert result2.customer_id == result.customer_id  # same identity, no duplicate
    assert customer.requirement == "2BHK"
    assert float(customer.budget_max) == 7_000_000
    assert "requirement" in result2.skipped_low_confidence_fields


@pytest.mark.anyio
async def test_user_edit_always_wins(db) -> None:
    business, user = await make_business(db)
    service, _, extraction = await run_tell_ai(db, business, user, "call")
    result = await service.apply_extraction(
        extraction.id,
        ApplyExtractionRequest(edited_fields={"requirement": "3BHK penthouse"}),
        actor_id=user.id,
    )
    customer = await service.customers.customers.get(result.customer_id)
    assert customer.requirement == "3BHK penthouse"
    assert customer.field_confidence["requirement"] == 1.0


@pytest.mark.anyio
async def test_ai_does_not_invent_missing_data(db) -> None:
    business, user = await make_business(db)
    sparse = {
        "customer_name": {"value": "Amit", "confidence": 0.9, "source_text": "Amit"},
        "summary": "Amit asked about delivery.",
        "follow_up": {"required": False, "confidence": 0.0},
    }
    service = build_service(db, business, llm=FakeLLM(sparse))
    job, _ = await service.create_job(
        source=ConversationSource.TELL_AI,
        idempotency_key=uuid.uuid4().hex,
        user_id=user.id,
        transcript_text="Amit ne delivery ke baare mein pucha",
    )
    extraction = await service.process_job(job.id)

    assert extraction.payload["phone_number"]["value"] is None
    assert extraction.payload["budget_min"]["value"] is None
    assert extraction.payload["location"]["value"] is None
    assert extraction.customer_id is None  # nothing to match on


@pytest.mark.anyio
async def test_conditional_followup_is_flagged_not_invented(db) -> None:
    business, user = await make_business(db)
    payload = dict(RAJESH_EXTRACTION)
    payload["follow_up"] = {
        "required": True,
        "date": "quotation bhejne ke baad",
        "type": "send_quotation",
        "action": "Send quotation",
        "confidence": 0.8,
    }
    service = build_service(db, business, llm=FakeLLM(payload))
    job, _ = await service.create_job(
        source=ConversationSource.TELL_AI,
        idempotency_key=uuid.uuid4().hex,
        user_id=user.id,
        transcript_text="quotation bhejne ke baad call karna",
    )
    extraction = await service.process_job(job.id)
    review = await service.build_review(extraction)

    assert review.follow_up.resolved_due_at is None
    assert review.follow_up.needs_confirmation is True

    # Applying without a user-supplied date must not fabricate one.
    result = await service.apply_extraction(
        extraction.id, ApplyExtractionRequest(), actor_id=user.id
    )
    assert result.follow_up_id is None


@pytest.mark.anyio
async def test_idempotent_submission_and_processing(db) -> None:
    business, user = await make_business(db)
    key = "offline-sync-key-123456"
    service, job, extraction = await run_tell_ai(db, business, user, "Rajesh called", key)

    service2 = build_service(db, business)
    job2, created = await service2.create_job(
        source=ConversationSource.TELL_AI,
        idempotency_key=key,
        user_id=user.id,
        transcript_text="Rajesh called",
    )
    assert created is False and job2.id == job.id

    replay = await service2.process_job(job.id)
    assert replay.id == extraction.id


@pytest.mark.anyio
async def test_audio_is_deleted_after_processing(db) -> None:
    from app.config.settings import get_settings
    from app.services.ai.base import TranscriptionResult

    business, user = await make_business(db)
    storage = LocalStorage(get_settings())
    blob = f"{business.id}/test-{uuid.uuid4().hex}.mp3"
    await storage.upload(
        blob_name=blob, data=b"ID3fake-audio", content_type="audio/mpeg", ttl_minutes=60
    )

    class TranscribingSTT(NullSTT):
        async def transcribe(self, **kwargs):  # noqa: ANN003, ANN201
            return TranscriptionResult(
                text="Rajesh ko Noida mein 2BHK chahiye", language="hi-IN", provider="test"
            )

    service = AIProcessingService(
        db,
        business_id=business.id,
        llm=FakeLLM(),
        stt=TranscribingSTT(),
        storage=storage,
        timezone=business.timezone,
    )
    job, _ = await service.create_job(
        source=ConversationSource.IMPORT_AUDIO,
        idempotency_key=uuid.uuid4().hex,
        user_id=user.id,
        audio_blob_name=blob,
        audio_mime_type="audio/mpeg",
        audio_size_bytes=13,
    )
    await service.process_job(job.id)

    refreshed = await service.jobs.get(job.id)
    assert refreshed.audio_blob_name is None
    assert refreshed.audio_deleted_at is not None
    with pytest.raises(FileNotFoundError):
        await storage.download(blob)
