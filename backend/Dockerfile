# syntax=docker/dockerfile:1.7
# ---------- builder ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# ffmpeg (and ffprobe, bundled with it) are required by
# app/services/ai/stt_providers.py to normalise call recordings before
# sending them to Whisper. Several manufacturers' call-recorder apps save
# audio in a container that looks natively supported (e.g. audio/mp4) while
# the actual codec inside (commonly AMR-NB) is not - without ffmpeg/ffprobe
# available, every such recording fails STT with a hard-to-diagnose 400 or,
# once probing was added, a ProviderUnavailableError raised specifically
# because these binaries were missing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 baatx

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=baatx:baatx . .

# Never run as root in production.
USER baatx
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", "--bind", "0.0.0.0:8000", \
     "--timeout", "120", "--graceful-timeout", "30", "--access-logfile", "-"]