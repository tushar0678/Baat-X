"""CRM merge policy.

Rule (§7): a low-confidence extraction must never overwrite a higher-confidence
value that is already stored. Each customer row keeps a `field_confidence` map
of the confidence that produced the value currently in the column; a new value
only wins when it is at least as confident, or when the column is empty, or
when a human edited it (confidence 1.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.crm import Customer
from app.schemas.ai import ExtractionPayload

HUMAN_CONFIDENCE = 1.0

# extraction field -> customer column
FIELD_MAP: dict[str, str] = {
    "customer_name": "name",
    "email": "email",
    "company": "company",
    "location": "location",
    "requirement": "requirement",
    "product": "product",
    "service": "service",
    "quantity": "quantity",
    "budget_min": "budget_min",
    "budget_max": "budget_max",
    "currency": "currency",
    "price_discussed": "price_discussion",
    "availability": "availability",
    "timeline": "timeline",
    "purchase_intent": "purchase_intent",
    "sentiment": "sentiment",
    "pain_points": "pain_points",
    "objections": "objections",
    "competitors": "competitors",
    "decision_maker": "decision_maker",
    "customer_query": "query",
    "topic": "topic",
    "lead_score": "lead_score",
}

DECIMAL_COLUMNS = {"budget_min", "budget_max"}


@dataclass(slots=True)
class MergeResult:
    updated_fields: list[str] = field(default_factory=list)
    skipped_low_confidence: list[str] = field(default_factory=list)


def _coerce(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in DECIMAL_COLUMNS:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    if column == "currency":
        return str(value).upper()[:3]
    if column == "lead_score":
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return None
    return value


def merge_extraction_into_customer(
    customer: Customer,
    payload: ExtractionPayload,
    *,
    edited_fields: dict[str, Any] | None = None,
) -> MergeResult:
    """Apply an extraction to a customer under the confidence policy.

    `edited_fields` are values the user corrected on the review screen; they are
    applied unconditionally at confidence 1.0.
    """
    result = MergeResult()
    stored: dict[str, float] = dict(customer.field_confidence or {})
    edited = edited_fields or {}

    for extraction_key, column in FIELD_MAP.items():
        field_obj = getattr(payload, extraction_key, None)
        if field_obj is None:
            continue

        if extraction_key in edited:
            new_value, new_confidence = _coerce(column, edited[extraction_key]), HUMAN_CONFIDENCE
        else:
            if field_obj.value in (None, "", []):
                continue
            new_value, new_confidence = _coerce(column, field_obj.value), field_obj.confidence

        if new_value in (None, "", []):
            continue

        current_value = getattr(customer, column, None)
        current_confidence = float(stored.get(column, 0.0))
        is_empty = current_value in (None, "", [], Decimal("0")) or (
            column == "lead_score" and not current_value
        )

        if not is_empty and new_confidence < current_confidence:
            result.skipped_low_confidence.append(column)
            continue
        if not is_empty and current_value == new_value:
            stored[column] = max(current_confidence, new_confidence)
            continue

        setattr(customer, column, new_value)
        stored[column] = new_confidence
        result.updated_fields.append(column)

    customer.field_confidence = stored
    return result


def customer_context_hint(customer: Customer | None) -> str | None:
    """A compact, non-sensitive digest passed to the LLM for disambiguation only."""
    if customer is None:
        return None
    bits = [
        f"name={customer.name}" if customer.name else None,
        f"requirement={customer.requirement}" if customer.requirement else None,
        f"location={customer.location}" if customer.location else None,
        f"status={customer.lead_status}",
    ]
    return ", ".join(b for b in bits if b) or None
