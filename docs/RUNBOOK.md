# BaatX Runbook

## Daily health

```bash
curl -fsS https://<api>/health    # {"status":"ok"}
curl -fsS https://<api>/ready     # database + queue status
```

## Alerts and first response

| Alert | Likely cause | First check |
|---|---|---|
| `alert-api-5xx` | DB unreachable, bad deploy | `/ready`, Container Apps revision health |
| `alert-ai-failures` | Azure OpenAI / Speech throttling or quota | provider quota, `job_failed` traces |
| `alert-auth-failures` | Credential stuffing | audit logs for `auth.login`, consider tightening `RATE_LIMIT_AUTH` |

## "A recording is stuck"

1. `GET /api/v1/ai/jobs/{id}` — read `status` and `stage_label`.
2. Jobs left in `queued` are re-queued automatically by the `reconcile_stuck_jobs`
   cron (every 30 minutes) and expired after 6 hours.
3. Worker logs: filter `job_id` in Application Insights (no customer content is logged).
4. Once a job reaches `applied`, its audio is already deleted — re-analysis is not
   possible and the API says so explicitly.

## "A customer got duplicated"

Duplicates inside one business are prevented by the unique index on
`(business_id, normalized_phone)`. A duplicate almost always means one record has
no phone number. Add the phone to the correct record; the next extraction will
match it automatically.

## Scaling

- API scales on HTTP concurrency (50 requests/replica).
- The worker scales on Redis queue depth via KEDA.
- A backlog usually means STT latency, not worker shortage — check provider metrics first.

## Rotating secrets

Secrets live in Key Vault and are referenced by Container Apps. After updating a
secret, restart the revision so it is re-resolved:

```bash
az containerapp revision restart --name ca-api-baatx-prod --resource-group <rg>
```

Rotating `jwt-secret` signs every user out — that is intended behaviour.

## Migrations

```bash
az containerapp exec --name ca-api-baatx-prod --resource-group <rg> \
  --command "alembic upgrade head"
```

Migrations are tested in CI with `upgrade head → downgrade base → upgrade head`
against a real PostgreSQL service container.

## Privacy incident checklist

1. Confirm `DELETE_AUDIO_AFTER_PROCESSING=true` and `RETAIN_TRANSCRIPTS=false`.
2. Check the storage lifecycle rule is still enabled (1-day backstop).
3. Search logs for redaction failures — audio, transcripts, phones and tokens must
   never appear.
4. Review `audit_logs` for the affected `business_id`.
