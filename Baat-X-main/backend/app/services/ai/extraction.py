"""Transcript -> validated ExtractionPayload.

Everything the model returns is treated as untrusted input: parsed defensively,
coerced through Pydantic, clamped, and stripped of control characters before it
reaches the database.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.core.errors import AIProcessingError
from app.core.phone import normalize_phone
from app.core.timeparse import resolve_follow_up_datetime
from app.models.enums import BusinessVertical, FollowUpType, QueryCategory
from app.schemas.ai import ExtractionPayload, Field_, FollowUpExtraction
from app.services.ai.base import LLMProvider
from app.services.ai.prompts import (
    EXTRACTION_SCHEMA_HINT,
    EXTRACTION_SYSTEM_PROMPT,
    MERGE_SYSTEM_PROMPT,
    TRANSCRIPT_CLOSE,
    TRANSCRIPT_OPEN,
    build_extraction_user_prompt,
)

log = get_logger(__name__)

# Fields whose accuracy materially changes CRM state (§7).
IMPORTANT_FIELDS = ("customer_name", "phone_number", "requirement", "budget", "lead_status")

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_FENCE = re.compile(r"^\s*```(?:json)?|```\s*$", re.MULTILINE)
_LAKH = re.compile(r"(\d+(?:\.\d+)?)\s*(lakh|lac|lakhs)", re.IGNORECASE)
_CRORE = re.compile(r"(\d+(?:\.\d+)?)\s*(crore|cr)\b", re.IGNORECASE)


def sanitize_transcript(text: str, max_chars: int = 200_000) -> str:
    """Strip control chars and neutralise attempts to close our fences."""
    cleaned = _CONTROL_CHARS.sub(" ", text or "")
    cleaned = cleaned.replace(TRANSCRIPT_OPEN, "").replace(TRANSCRIPT_CLOSE, "")
    return cleaned.strip()[:max_chars]


def chunk_transcript(text: str, chunk_chars: int, overlap: int) -> list[str]:
    """Split a long transcript on sentence-ish boundaries with a small overlap."""
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            window = text.rfind(". ", start + int(chunk_chars * 0.6), end)
            if window != -1:
                end = window + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def parse_money(value: Any) -> float | None:
    """'70 lakh' / '₹70,00,000' / '1.2 crore' -> float. None when unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if m := _CRORE.search(text):
        return float(m.group(1)) * 10_000_000
    if m := _LAKH.search(text):
        return float(m.group(1)) * 100_000
    digits = re.sub(r"[^\d.]", "", text)
    if not digits or digits.count(".") > 1:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _loads(content: str) -> dict[str, Any]:
    """Tolerant JSON parse - models occasionally wrap output in a fence."""
    raw = _FENCE.sub("", content or "").strip()
    if not raw:
        raise AIProcessingError("empty LLM response")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise AIProcessingError("LLM did not return JSON") from None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIProcessingError("LLM returned malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise AIProcessingError("LLM returned a non-object")
    return parsed


def _coerce_field(raw: Any) -> dict[str, Any]:
    """Accept both `{"value":..}` envelopes and bare scalars from the model."""
    if isinstance(raw, dict) and ("value" in raw or "confidence" in raw):
        return {
            "value": raw.get("value"),
            "confidence": raw.get("confidence", 0.0),
            "source_text": raw.get("source_text"),
        }
    return {
        "value": raw,
        "confidence": 0.5 if raw not in (None, "", []) else 0.0,
        "source_text": None,
    }


def normalize_raw_extraction(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key in {"summary", "language_detected", "follow_up"}:
            out[key] = value
        else:
            out[key] = _coerce_field(value)
    return out


class ExtractionService:
    def __init__(self, llm: LLMProvider, settings: Settings | None = None) -> None:
        self._llm = llm
        self._settings = settings or get_settings()

    async def extract(
        self,
        transcript: str,
        *,
        vertical: BusinessVertical = BusinessVertical.GENERIC,
        currency: str = "INR",
        known_customer_hint: str | None = None,
        timezone: str = "Asia/Kolkata",
        now: datetime | None = None,
    ) -> ExtractionPayload:
        clean = sanitize_transcript(transcript)
        if len(clean) < 3:
            raise AIProcessingError(
                "transcript too short",
                user_message="We couldn't hear anything in that recording. Please try again.",
            )

        chunks = chunk_transcript(
            clean,
            self._settings.transcript_chunk_chars,
            self._settings.transcript_chunk_overlap_chars,
        )
        partials: list[dict[str, Any]] = []
        context: str | None = None
        for index, chunk in enumerate(chunks):
            prompt = build_extraction_user_prompt(
                chunk,
                vertical=vertical,
                currency=currency,
                known_customer_hint=known_customer_hint,
                previous_context=context,
            )
            result = await self._llm.complete_json(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_prompt=prompt,
                schema_hint=EXTRACTION_SCHEMA_HINT,
            )
            parsed = normalize_raw_extraction(_loads(result.content))
            partials.append(parsed)
            context = self._context_digest(parsed)
            log.info("chunk_extracted", chunk=index + 1, total=len(chunks))

        merged = partials[0] if len(partials) == 1 else await self._merge(partials)
        payload = self._to_payload(merged, currency=currency)
        self._resolve_follow_up(payload, timezone=timezone, now=now)
        return payload

    # ---------------- internals ----------------
    async def _merge(self, partials: list[dict[str, Any]]) -> dict[str, Any]:
        """Deterministic merge first; the LLM only rewrites the summary."""
        merged: dict[str, Any] = {}
        summaries: list[str] = []
        for partial in partials:
            for key, value in partial.items():
                if key == "summary":
                    if value:
                        summaries.append(str(value))
                    continue
                if key == "follow_up":
                    prev = merged.get("follow_up") or {}
                    if (value or {}).get("confidence", 0) >= prev.get("confidence", 0):
                        merged["follow_up"] = value
                    continue
                if key == "language_detected":
                    merged.setdefault(key, value)
                    continue
                current = merged.get(key)
                if current is None:
                    merged[key] = value
                    continue
                new_val, cur_val = (value or {}).get("value"), current.get("value")
                if isinstance(cur_val, list) or isinstance(new_val, list):
                    union = list(dict.fromkeys([*(cur_val or []), *(new_val or [])]))
                    merged[key] = {
                        "value": union,
                        "confidence": max(
                            current.get("confidence", 0), (value or {}).get("confidence", 0)
                        ),
                        "source_text": current.get("source_text"),
                    }
                elif (value or {}).get("confidence", 0) >= current.get("confidence", 0) and (
                    new_val not in (None, "", [])
                ):
                    merged[key] = value

        if len(summaries) == 1:
            merged["summary"] = summaries[0]
        elif summaries:
            try:
                result = await self._llm.complete_json(
                    system_prompt=MERGE_SYSTEM_PROMPT,
                    user_prompt=json.dumps({"summaries": summaries})[:12_000],
                )
                merged["summary"] = _loads(result.content).get("summary") or " ".join(summaries)
            except AIProcessingError:
                merged["summary"] = " ".join(summaries)[:1500]
        return merged

    def _context_digest(self, parsed: dict[str, Any]) -> str:
        keep = ("customer_name", "phone_number", "requirement", "budget", "location")
        facts = {
            k: (parsed.get(k) or {}).get("value")
            for k in keep
            if (parsed.get(k) or {}).get("value")
        }
        return json.dumps(facts, ensure_ascii=False)[:800]

    def _to_payload(self, merged: dict[str, Any], *, currency: str) -> ExtractionPayload:
        payload = ExtractionPayload.model_validate(merged)

        # Phone must be E.164 before it can ever become part of the identity key.
        if payload.phone_number.value:
            normalized = normalize_phone(str(payload.phone_number.value))
            if normalized:
                payload.phone_number.value = normalized
            else:
                payload.phone_number = Field_(value=None, confidence=0.0, source_text=None)

        # Money: derive numeric bounds from the human phrase when absent.
        if payload.budget_min.value is None and payload.budget.value:
            amount = parse_money(payload.budget.value)
            if amount is not None:
                payload.budget_min = Field_(
                    value=amount,
                    confidence=payload.budget.confidence,
                    source_text=payload.budget.source_text,
                )
                payload.budget_max = Field_(
                    value=amount,
                    confidence=payload.budget.confidence,
                    source_text=payload.budget.source_text,
                )
        else:
            payload.budget_min.value = parse_money(payload.budget_min.value)
            payload.budget_max.value = parse_money(payload.budget_max.value)
        if (
            payload.budget_min.value is not None
            and payload.budget_max.value is not None
            and payload.budget_max.value < payload.budget_min.value
        ):
            payload.budget_min.value, payload.budget_max.value = (
                payload.budget_max.value,
                payload.budget_min.value,
            )
        if not payload.currency.value:
            payload.currency = Field_(value=currency, confidence=0.5)

        # Drop unrecognised query categories instead of failing the whole job.
        if payload.query_categories.value:
            valid = []
            for item in payload.query_categories.value:
                try:
                    valid.append(QueryCategory(str(item).strip().lower()))
                except ValueError:
                    continue
            payload.query_categories.value = valid or None

        if payload.lead_score.value is not None:
            payload.lead_score.value = max(0, min(100, int(payload.lead_score.value)))
        if payload.summary:
            payload.summary = sanitize_transcript(payload.summary, 2000)
        return payload

    def _resolve_follow_up(
        self, payload: ExtractionPayload, *, timezone: str, now: datetime | None
    ) -> None:
        fu: FollowUpExtraction = payload.follow_up
        if not fu.required and not fu.date:
            return
        try:
            fu.type = FollowUpType(str(fu.type))
        except ValueError:
            fu.type = FollowUpType.GENERAL_FOLLOW_UP

        resolved = resolve_follow_up_datetime(
            fu.date, now=now, timezone=timezone, explicit_time=fu.time
        )
        fu.resolved_due_at = resolved.due_at
        fu.resolved_time_known = resolved.time_known
        fu.needs_confirmation = resolved.needs_confirmation or resolved.due_at is None
        fu.resolution_reason = resolved.reason
        # Never let the model's stated confidence exceed what we could actually resolve.
        fu.confidence = round(min(fu.confidence or 0.0, resolved.confidence or 0.0), 4)


def needs_confirmation_fields(payload: ExtractionPayload, threshold: float) -> list[str]:
    """Important fields that are present but not confident enough to trust silently."""
    flagged = [
        name
        for name in IMPORTANT_FIELDS
        if (field := getattr(payload, name, None)) is not None
        and field.value not in (None, "", [])
        and field.confidence < threshold
    ]
    if payload.follow_up.required and payload.follow_up.needs_confirmation:
        flagged.append("follow_up")
    return flagged
