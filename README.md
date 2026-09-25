# BaatX

**You talk. BaatX remembers, updates, and reminds.**

> We don't store your recordings. We extract what matters and update your CRM.

BaatX is an AI sales assistant for small shopkeepers, dealers, field salespeople and
local businesses in India. It is deliberately **not** an enterprise CRM: the
salesperson talks, and BaatX does the data entry.

```
CONVERSATION → TELL AI → AI UNDERSTANDS → REVIEW → CRM UPDATED
            → FOLLOW-UP CREATED → REMINDER → CONVERSION → REPORT
```

---

## What's in this repository

```
baatx/
├── backend/            FastAPI + SQLAlchemy 2 + Alembic + arq worker
├── android/            Kotlin, Jetpack Compose, Material 3, Hilt, Room, WorkManager
├── infrastructure/     Terraform modules + dev / staging / prod environments
├── .github/workflows/  Backend CI, Android CI, gated production deploy
├── docker-compose.yml  Postgres + Redis + Azurite + API + worker
└── .env.example
```
Hierarchy Structure

I recommend this hierarchy for BaatX CRM:

Plain Text
Owner
│
├── Manager
│ │
│ ├── Team Lead
│ │ │
│ │ ├── Salesperson
│ │ ├── Salesperson
│ │ └── Salesperson
│ │
│ └── Team Lead
│ ├── Salesperson
│ └── Salesperson
│
└── Viewer
Show more lines
1. OWNER
Who?

Business owner, company founder, CRM administrator.

Scope
Plain Text
Entire Organization
Show more lines

Can see:

✅ All customers
 ✅ All leads
 ✅ All follow-ups
 ✅ All recordings
 ✅ All reports
 ✅ All teams
 ✅ All users

Can do

✅ Create teams

✅ Invite users

✅ Promote managers

✅ Create another owner

✅ Assign permissions

✅ Remove users

✅ Change company settings

Example:

Plain Text
GHM Real Estate Owner
↓
Can see all 500 leads
Show more lines
2. MANAGER
Who?

Branch manager / sales manager.

Scope
Plain Text
Entire Organization
Show more lines

Can see:

✅ All teams

✅ All leads

✅ All customers

✅ All reports

But cannot:

❌ Delete company

❌ Transfer ownership

❌ Create another owner

Example

Plain Text
Delhi Sales Manager
Show more lines

can see

Plain Text
North Team
South Team
East Team
West Team
Show more lines

all together.

3. TEAM LEAD
Who?

Sales leader.

Scope
Plain Text
Own Team Only
Show more lines

Can see:

✅ Own leads

✅ Team member leads

✅ Team follow-ups

✅ Team reports

Cannot see:

❌ Other team data

Example

Plain Text
Team Lead = Rahul
 
Team:
Aman
Suraj
Rakesh
Show more lines

Rahul can see:

Plain Text
Aman leads
Suraj leads
Rakesh leads
Rahul leads
Show more lines

But cannot see:

Plain Text
Priya Team
Ankit Team
Show more lines
4. MEMBER / SALESPERSON
Who?

Actual salesperson.

Scope
Plain Text
Only Own Records
Show more lines

Can see:

✅ Own customers

✅ Own leads

✅ Own follow-ups

✅ Own call recordings

Cannot see:

❌ Team lead records

❌ Colleague records

❌ Other teams

❌ Organization reports

Example

Plain Text
Salesperson = Aman
Show more lines

Aman can see only:

Plain Text
Lead A
Lead B
Lead C
Show more lines

Created/assigned to Aman.

5. VIEWER
Who?

HR, auditor, CEO assistant.

Scope
Plain Text
Read Only
Show more lines

Can see data.

Cannot:

❌ Edit

❌ Delete

❌ Create

❌ Reassign

Data Visibility Matrix
Role	Own Data	Team Data	Org Data	Manage UsersOwner	✅	✅	✅	✅
Manager	✅	✅	✅	✅
Team Lead	✅	✅	❌	Limited
Member	✅	❌	❌	❌
Viewer	✅	Depends	Depends	❌
---

## Quick start (local)

```bash
cp .env.example .env
# Generate a real secret for local use:
python -c "import secrets;print('JWT_SECRET='+secrets.token_urlsafe(48))" >> .env

docker compose up --build
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Running the backend without Docker:

```bash
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload          # API
arq app.workers.main.WorkerSettings    # worker (separate terminal)
pytest -q                              # 64 tests
```

Running without any cloud keys — providers fall back to deterministic no-ops:

```bash
ENVIRONMENT=test LLM_PROVIDER=null STT_PROVIDER=null STORAGE_PROVIDER=local \
  uvicorn app.main:app --reload
```

### Android

```bash
cd android
./gradlew assembleDebug        # APK for testing
./gradlew bundleRelease        # AAB for Play Store (needs signing config)
```

The debug build points at `http://10.0.2.2:8000/` (the host machine as seen from
the emulator). Override with `BAATX_API_BASE_URL`.

---

## How the AI pipeline works

| Stage | What happens | Where |
|---|---|---|
| 1. Capture | Tell AI recording, or a user-picked audio file | `features/tellai`, `features/audio` |
| 2. Upload | Private blob, short TTL, magic-byte validated | `services/audio/validator.py`, `services/storage` |
| 3. Transcribe | Azure AI Speech with hi-IN/en-IN language ID | `services/ai/stt_providers.py` |
| 4. Extract | Chunked LLM extraction with per-field confidence | `services/ai/extraction.py` |
| 5. Resolve dates | "Friday ko call karna" → real datetime | `core/timeparse.py` |
| 6. Review | "Here's what I understood" — user approves | `features/tellai/AiReviewScreen.kt` |
| 7. Apply | Confidence-aware merge into the CRM | `services/crm/merge.py` |
| 8. Delete audio | Temporary audio removed immediately | `services/ai/pipeline.py` |

Long recordings (5–60+ minutes) are supported through chunking, background
processing, progress reporting, retries with exponential backoff, and
idempotency keys.

---

## Design rules that are enforced in code

| Rule | Where it's enforced | Test |
|---|---|---|
| The AI never invents data — unknown stays `null` | `prompts.py`, `extraction.py` | `test_ai_does_not_invent_missing_data` |
| Low-confidence data can't overwrite high-confidence data | `crm/merge.py` | `test_low_confidence_cannot_overwrite_high_confidence` |
| Same phone in two businesses stays fully isolated | `repositories/base.py`, unique index | `test_same_phone_in_two_businesses_stays_isolated` |
| WhatsApp never sends without explicit approval | `whatsapp/service.py` | `test_send_without_approval_is_refused` |
| Internal fields never reach a customer message | `FORBIDDEN_PATTERNS` filter | `test_draft_never_contains_internal_information` |
| Audio is deleted after processing | `pipeline._delete_audio` | `test_audio_is_deleted_after_processing` |
| Unresolvable dates are confirmed, not guessed | `core/timeparse.py` | `test_conditional_followup_is_flagged_not_invented` |
| Reports come from real rows only | `reports/report_service.py` | `test_conversion_rate_is_mathematically_correct` |
| Errors are human-readable, never `HTTP 500` | `middleware/errors.py`, `ErrorMapper.kt` | `test_validation_errors_are_human_readable` |

Run them all:

```bash
cd backend && ENVIRONMENT=test pytest -q
```

---
# BaatX — Call Sync feature

Call end hote hi popup → recording attach → CRM me naam + number ke saath data.
Repeat call par wahi customer record update hota hai (duplicate nahi banta).

---

## Flow

```
Call ends (OFFHOOK -> IDLE)
  -> CallEndReceiver reads the last call log row (number, name, duration)
  -> pending_calls row + high-priority notification "Sync this call?"
  -> user taps -> CallSyncScreen (number + name prefilled, editable)
  -> user picks the recording + ticks consent
  -> POST /ai/process-audio  (phone_hint, name_hint, source=import_call_recording)
  -> worker: transcribe -> extract -> match customer BY PHONE
  -> AiReviewScreen -> "Save to CRM"
  -> ConversationEvent on that customer's timeline
```

Next time the same number calls, `_match_customer()` finds the existing
customer and the whole history is already on their detail screen.

---

## File map (copy-paste into your repo)

### Backend

| Put this file at | Action |
|---|---|
| `backend/app/models/conversation.py` | replace |
| `backend/app/api/v1/endpoints/ai.py` | replace |
| `backend/app/services/ai/pipeline.py` | replace |
| `backend/migrations/versions/0002_call_sync_hints.py` | new |

### Android

| Put this file at | Action |
|---|---|
| `android/app/src/main/AndroidManifest.xml` | replace |
| `android/app/src/main/java/com/baatx/MainActivity.kt` | replace |
| `android/app/src/main/java/com/baatx/BaatXApplication.kt` | replace |
| `android/app/src/main/java/com/baatx/navigation/Navigation.kt` | replace |
| `android/app/src/main/java/com/baatx/data/local/PendingCapture.kt` | replace |
| `android/app/src/main/java/com/baatx/data/local/DatabaseModule.kt` | replace |
| `android/app/src/main/java/com/baatx/data/local/PendingCall.kt` | **new** |
| `android/app/src/main/java/com/baatx/data/remote/BaatXApi.kt` | replace |
| `android/app/src/main/java/com/baatx/domain/repository/Repositories.kt` | replace |
| `android/app/src/main/java/com/baatx/data/repository/RepositoryImpls.kt` | replace |
| `android/app/src/main/java/com/baatx/work/CaptureSyncWorker.kt` | replace |
| `android/app/src/main/java/com/baatx/features/settings/SettingsScreen.kt` | replace |
| `android/app/src/main/java/com/baatx/core/calls/CallStateStore.kt` | **new** |
| `android/app/src/main/java/com/baatx/core/calls/CallLogReader.kt` | **new** |
| `android/app/src/main/java/com/baatx/core/calls/CallEndReceiver.kt` | **new** |
| `android/app/src/main/java/com/baatx/core/calls/CallSyncNotifier.kt` | **new** |
| `android/app/src/main/java/com/baatx/features/audio/AudioPicking.kt` | **new** |
| `android/app/src/main/java/com/baatx/features/callsync/CallSyncViewModel.kt` | **new** |
| `android/app/src/main/java/com/baatx/features/callsync/CallSyncScreen.kt` | **new** |

**Unchanged:** `AudioRecorder.kt`, `TellAiScreen/ViewModel`, all other features.
`TellAiViewModel` already calls `importAudio` with named args, so the new
optional params don't break it.

---

## Deploy steps

### 1. Backend

```bash
cd backend
alembic upgrade head          # applies 0002_call_sync_hints
```

Render par `start.py` ye migration deploy par khud chala dega.

### 2. Android

```powershell
cd android
.\gradlew.bat clean assembleDebug
.\gradlew.bat installDebug
```

Room version 1 -> 2 hai aur `fallbackToDestructiveMigration()` on hai, to local
cache reset ho jayega (koi server data loss nahi).

### 3. Enable karein

App -> **More** -> **Sync calls automatically** -> permissions allow karein.

Feature default OFF hai. Permission deny karne par app normal chalti rahegi.

---

## Test checklist

1. Toggle on karke permissions allow karein.
2. Kisi number par 10+ second ki call karein.
3. Call cut hote hi notification aani chahiye.
4. Tap -> number aur naam prefilled dikhein.
5. Recording pick karein, consent tick karein, **Sync to BaatX**.
6. Review screen -> **Save to CRM**.
7. Customers -> wahi naam/number dikhe, timeline par "Call Recording" entry.
8. **Usi number par dobara call karke sync karein** -> naya customer nahi
   banna chahiye, usi timeline me doosri entry aani chahiye.
9. Aeroplane mode me sync karein -> "Waiting for internet", net aane par
   apne aap upload ho.
10. Missed call cut karein -> koi notification nahi aani chahiye.

---

## Zaroori limitations (honestly)

- **BaatX call record nahi kar sakta.** Android third-party apps ko call audio
  ka koi public API nahi deta. Isliye user apne dialer ki saved recording pick
  karta hai. Jis phone me call recording hi nahi hai, wahan recording nahi
  milegi — popup phir bhi aayega aur user "Tell AI" se bol kar note kar sakta hai.
- **READ_CALL_LOG Google Play ki restricted permission hai.** Play Console par
  Permissions Declaration Form bharna padega aur listing me call-sync ko core
  feature ke roop me describe karna hoga. Approve na ho to bas ye permission
  hata dein — baaki sab chalta rahega, user number khud type karega
  (`CallSyncScreen` already handle karta hai).
- **Consent:** recording upload karne se pehle user ka tick mandatory rakha hai.
  Doosre party ko recording ke baare me batane ki zimmedari user ki hai — ise
  privacy policy me clearly likhein.




## Privacy and security

- Audio lives in a **private** container with a short TTL and a lifecycle rule as a
  backstop; the app deletes it as soon as the transcript exists.
- Transcripts are **not** retained unless `RETAIN_TRANSCRIPTS=true`.
- Structured logging redacts audio, transcripts, phone numbers, emails, tokens and keys.
- Tokens are stored in `EncryptedSharedPreferences` backed by the Android Keystore,
  and excluded from cloud backup and device transfer.
- Every tenant-scoped query is forced through `business_id` by `TenantRepository`.
- Transcript text is fenced and declared untrusted in every prompt (prompt-injection defence);
  all model output is re-validated through Pydantic before it touches the database.
- **No call interception, no accessibility abuse, no background recording** — only
  official Android APIs and files the user explicitly picks.

---

## Azure production architecture

PostgreSQL Flexible Server (VNet-injected) · Blob Storage (private endpoint) ·
Azure Cache for Redis · Azure OpenAI · Azure AI Speech · Key Vault ·
Managed Identity · Container Apps (API + KEDA-scaled worker) ·
Application Insights + Log Analytics.

```bash
cd infrastructure/terraform/environments/prod
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform plan
```

Secrets are generated in Terraform, stored in Key Vault, and injected into
Container Apps as secret references — they never appear in the image, in
Terraform outputs, or in CI logs.

---

## CI/CD

| Workflow | Trigger | Does |
|---|---|---|
| `backend-ci.yml` | backend changes | lint, format, mypy, tests, migration up/down/up, bandit, pip-audit, gitleaks, Docker build, Trivy scan |
| `android-ci.yml` | android changes | lint, unit tests, debug APK artifact |
| `production-deploy.yml` | `v*.*.*` tag or manual | full gate → signed AAB → image build+scan+push → `terraform plan` → **manual approval** → apply → migrations → smoke tests |

Required repository secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID` (OIDC), `AZURE_SPEECH_KEY`, `ANDROID_KEYSTORE_BASE64`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.

---

## API surface

```
POST   /api/v1/ai/process-audio        POST   /api/v1/ai/tell-ai
GET    /api/v1/ai/jobs/{id}            GET    /api/v1/ai/jobs/{id}/review
POST   /api/v1/ai/extractions/{id}/apply
POST   /api/v1/customers               GET    /api/v1/customers/{id}
PATCH  /api/v1/customers/{id}          GET    /api/v1/customers/{id}/timeline
GET    /api/v1/leads                   GET    /api/v1/leads/funnel
PATCH  /api/v1/leads/{id}/status       POST   /api/v1/leads/{id}/convert
GET/POST /api/v1/follow-ups            PATCH  /api/v1/follow-ups/{id}
GET    /api/v1/dashboard               GET    /api/v1/reports/{daily|weekly|monthly}
POST   /api/v1/whatsapp/draft          POST   /api/v1/whatsapp/send
POST   /api/v1/assistant/query
GET    /health                         GET    /ready
```

34 routes total. Full schema at `/docs` (disabled in production).

---

## Built for scale later, not over-engineered now

The provider abstractions (`SpeechToTextProvider`, `LLMProvider`,
`StorageProvider`), the versioned API, and the tenant-scoped data model leave
room for a web app, iOS, more messaging integrations, billing and larger teams —
without adding that complexity today.
