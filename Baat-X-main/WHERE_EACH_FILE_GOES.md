# Where each file goes

Copy these over your existing `baatx-complete` folder, keeping the paths.

| File in this bundle | Destination | Action |
|---|---|---|
| `backend/requirements.txt` | `backend/requirements.txt` | replace |
| `backend/requirements-dev.txt` | `backend/requirements-dev.txt` | replace |
| `backend/pyproject.toml` | `backend/pyproject.toml` | replace |
| `backend/app/main.py` | `backend/app/main.py` | replace |
| `backend/app/config/settings.py` | `backend/app/config/settings.py` | replace |
| `backend/app/services/ai/stt_providers.py` | `backend/app/services/ai/stt_providers.py` | replace |
| `backend/start.sh` | `backend/start.sh` | **new** |
| `backend/preflight.py` | `backend/preflight.py` | **new** |
| `render.yaml` | repo root | **new** |
| `.github/workflows/backup.yml` | `.github/workflows/backup.yml` | **new** |

Plus two hand edits in `ANDROID_EDITS.md`.

## On Windows

```powershell
# from the folder containing both baatx-complete and baatx-updated-files
Copy-Item -Recurse -Force baatx-updated-files\* baatx-complete\baatx\
```

`start.sh` needs the executable bit, which Windows doesn't set. Git can fix it:

```bash
git update-index --chmod=+x backend/start.sh
```

Or just let Render handle it — the Dockerfile `COPY` preserves whatever mode
Git has recorded, so setting it once in Git is enough.

## Verify

```powershell
cd backend
python -m pytest -q          # must still be: 64 passed
```

If the count changed, a file didn't copy cleanly.

Then, with your real service URLs and keys set as env vars:

```powershell
python preflight.py
```

This actually calls Neon, Upstash, Gemini and Groq. Fix anything it flags
before pushing — a failed preflight is a failed deploy, just faster.
