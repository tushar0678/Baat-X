# BaatX Architecture

## Layering

```
Android (Compose → ViewModel → Repository → Retrofit/Room)
                    │  HTTPS + Bearer + X-Business-Id
                    ▼
FastAPI  →  Service  →  Repository  →  PostgreSQL
   │
   └─ enqueue ─→ Redis (arq) ─→ Worker ─→ STT ─→ LLM ─→ CRM update ─→ Notification
```

The API never performs long work inline. `POST /ai/process-audio` returns `202`
with a job id; the Android client polls `/ai/jobs/{id}` for the stage label and
percentage, which the worker keeps current.

## Why the review step exists

The CRM is **never** written by the AI directly. The worker produces an
`AIExtraction` row and stops. A human sees "Here's what I understood", edits
anything wrong, and only then does `POST /ai/extractions/{id}/apply` touch
customers, leads, follow-ups and the timeline. This is what makes it safe to run
an LLM over live customer data.

## Confidence model

Each extracted field carries `{value, confidence, source_text}`. The customer row
stores a `field_confidence` map recording the confidence behind the value
currently in each column.

On merge:
- empty column → new value wins
- new confidence ≥ stored confidence → new value wins
- new confidence < stored confidence → **skipped** and reported back
- a human edit → confidence 1.0, always wins

Bands: ≥ 0.90 high, 0.60–0.89 medium, < 0.60 low. Important fields
(name, phone, requirement, budget, lead status, follow-up) below the medium
threshold are surfaced for confirmation instead of being applied silently.

## Tenant isolation

`TenantRepository` only ever builds queries with `business_id` pre-applied; there
is no "get by id" that skips it. Customers are unique on
`(business_id, normalized_phone)`, so the same phone number can exist in many
businesses while remaining invisible across them. Cross-tenant reads return 404,
not 403 — we don't confirm that another tenant's record exists.

## Date resolution

`core/timeparse.py` understands Hindi, Hinglish and English expressions
("Friday ko call karna", "2 din baad", "kal shaam", "10 din baad") and returns a
resolved datetime plus a `needs_confirmation` flag. Conditional expressions
("quotation bhejne ke baad call karna") resolve to `None` on purpose — BaatX asks
rather than inventing a date. The LLM copies the spoken phrase verbatim and never
does the date maths itself.

## Idempotency

Every capture carries a client-generated idempotency key. `create_job` returns the
existing job for a repeated key, `process_job` returns the existing extraction if
already processed, and the queue de-duplicates on `_job_id`. An offline phone that
retries eight times still produces exactly one customer conversation.

## Failure handling

- arq retries with exponential backoff up to `JOB_MAX_TRIES`.
- The job row stores a user-facing `error_message` — the client never sees a stack trace.
- A cron reconciles jobs stuck in `queued`, and expires anything older than 6 hours.
- Temporary audio is deleted in a `finally` block, on success *and* on failure.
- Redis being down degrades rate limiting to pass-through rather than failing requests.
