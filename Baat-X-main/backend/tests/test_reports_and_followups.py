"""Reports must be arithmetic over real rows; the board must bucket correctly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.models.crm import ConversionEvent, Customer, Lead
from app.models.enums import FollowUpStatus, FollowUpType, LeadStatus
from app.repositories.lead_repo import LeadRepository
from app.schemas.followup import FollowUpCreate, FollowUpUpdate
from app.services.reminders.followup_service import FollowUpService
from app.services.reports.report_service import ReportService
from factories import make_business

IST = ZoneInfo("Asia/Kolkata")


async def add_customer(db, business, name: str, status=LeadStatus.NEW) -> Customer:  # noqa: ANN001
    customer = Customer(
        business_id=business.id,
        name=name,
        normalized_phone=f"+9198765{abs(hash(name)) % 90000 + 10000}",
        lead_status=status,
    )
    db.add(customer)
    await db.flush()
    db.add(Lead(business_id=business.id, customer_id=customer.id, status=status))
    await db.flush()
    return customer


@pytest.mark.anyio
async def test_conversion_rate_is_mathematically_correct(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    for index in range(10):
        status = LeadStatus.CONVERTED if index < 3 else LeadStatus.NEW
        customer = await add_customer(db, business, f"C{index}", status)
        if status == LeadStatus.CONVERTED:
            db.add(
                ConversionEvent(
                    business_id=business.id, customer_id=customer.id, currency="INR"
                )
            )
    await db.flush()

    repo = LeadRepository(db, business.id)
    total, converted = await repo.total_and_converted()
    assert (total, converted) == (10, 3)
    assert round((converted / total) * 100, 2) == 30.0

    report = await ReportService(db, business.id, llm=None).period("weekly", with_insights=False)
    assert report.leads.conversion_rate == pytest.approx(30.0, abs=0.01)
    assert report.metrics_source == "database"


@pytest.mark.anyio
async def test_daily_report_counts_only_real_rows(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    empty = await ReportService(db, business.id, llm=None).daily(with_insights=True)

    assert empty.new_leads == 0
    assert empty.customers_contacted == 0
    assert empty.converted_customers == 0
    assert empty.queries.total_queries == 0
    assert empty.insights_are_ai_generated is True
    assert empty.ai_insights == ["No activity recorded for this period yet."]

    await add_customer(db, business, "Rajesh")
    await add_customer(db, business, "Amit")
    populated = await ReportService(db, business.id, llm=None).daily(with_insights=False)
    assert populated.new_leads == 2


@pytest.mark.anyio
async def test_followup_board_buckets_and_overdue(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await add_customer(db, business, "Rajesh")
    service = FollowUpService(db, business.id, business.timezone)
    now = datetime.now(IST)

    await service.create(
        FollowUpCreate(
            customer_id=customer.id,
            type=FollowUpType.CALL_CUSTOMER,
            title="Call customer",
            due_at=now + timedelta(hours=3),
        ),
        actor_id=user.id,
    )
    await service.create(
        FollowUpCreate(
            customer_id=customer.id,
            type=FollowUpType.SEND_QUOTATION,
            title="Send quotation",
            due_at=now + timedelta(days=1, hours=2),
        ),
        actor_id=user.id,
    )
    overdue = await service.create(
        FollowUpCreate(
            customer_id=customer.id,
            type=FollowUpType.CALL_CUSTOMER,
            title="Missed callback",
            due_at=now - timedelta(days=1),
        ),
        actor_id=user.id,
    )

    board = await service.board(assigned_user_id=None)
    assert board.counts["today"] == 1
    assert board.counts["tomorrow"] == 1
    assert board.counts["overdue"] == 1
    assert board.overdue[0].is_overdue is True
    assert board.overdue[0].customer_name == "Rajesh"

    await service.update(
        overdue.id, FollowUpUpdate(status=FollowUpStatus.COMPLETED), actor_id=user.id
    )
    board = await service.board(assigned_user_id=None)
    assert board.counts["overdue"] == 0
    assert board.counts["completed"] == 1


@pytest.mark.anyio
async def test_reminder_sweep_is_not_spammy(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await add_customer(db, business, "Rajesh")
    service = FollowUpService(db, business.id, business.timezone)
    await service.create(
        FollowUpCreate(
            customer_id=customer.id,
            type=FollowUpType.CALL_CUSTOMER,
            title="Call customer",
            due_at=datetime.now(UTC) + timedelta(minutes=10),
        ),
        actor_id=user.id,
    )

    first = await service.sweep_due_reminders()
    second = await service.sweep_due_reminders()
    assert first == 1
    assert second == 0  # deduped, no repeat notification


@pytest.mark.anyio
async def test_smart_suggestions_detect_stale_hot_leads(db) -> None:  # noqa: ANN001
    business, user = await make_business(db)
    customer = await add_customer(db, business, "Hot Lead", LeadStatus.HOT)
    customer.last_interaction_at = datetime.now(UTC) - timedelta(days=5)
    await db.flush()

    suggestions = await FollowUpService(db, business.id, business.timezone).smart_suggestions()
    assert "hot_lead_no_recent_contact" in {s.kind for s in suggestions}
    assert all(s.is_ai_generated for s in suggestions)
