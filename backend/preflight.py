#!/usr/bin/env python
"""BaatX deployment preflight.

Validates the config you are ABOUT to deploy, and actually calls the external
services. Catches the mistakes that otherwise only surface after a six-minute
build and a confusing 500.

Usage, from backend/ with your venv active and the deploy env vars set:

    python preflight.py
"""

from __future__ import annotations

import asyncio
import os
import sys

GREEN, RED, YELLOW, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"
failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"{GREEN}  PASS{RESET}  {msg}")


def fail(msg: str, fix: str) -> None:
    print(f"{RED}  FAIL{RESET}  {msg}\n        fix: {fix}")
    failures.append(msg)


def warn(msg: str) -> None:
    print(f"{YELLOW}  WARN{RESET}  {msg}")
    warnings.append(msg)


def check_database_url() -> None:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return fail("DATABASE_URL is not set", "paste the Neon connection string")
    if url.startswith("postgresql://"):
        return fail(
            "DATABASE_URL uses the plain driver",
            "change 'postgresql://' to 'postgresql+asyncpg://'",
        )
    if not url.startswith("postgresql+asyncpg://") and not url.startswith("sqlite"):
        return fail("DATABASE_URL has an unexpected scheme", "use postgresql+asyncpg://")
    if url.startswith("postgresql") and "ssl=require" not in url and "sslmode=require" not in url:
        warn("DATABASE_URL has no ssl=require - Neon needs TLS")
    ok("DATABASE_URL format")


def check_redis_url() -> None:
    url = os.getenv("REDIS_URL", "")
    if not url:
        return fail("REDIS_URL is not set", "paste the Upstash TCP URL")
    if url.startswith("https://"):
        return fail(
            "REDIS_URL is the Upstash REST URL",
            "use the TCP URL instead: rediss://default:<pw>@<host>:6379",
        )
    if not url.startswith(("redis://", "rediss://")):
        return fail("REDIS_URL is not a redis:// or rediss:// URL", "copy the TCP URL")
    if url.startswith("redis://") and "upstash" in url:
        warn("Upstash over plain redis:// - prefer rediss:// for TLS")
    ok("REDIS_URL format")


def check_ai_config() -> None:
    llm = os.getenv("LLM_PROVIDER", "")
    stt = os.getenv("STT_PROVIDER", "")

    if llm == "null" or stt == "null":
        warn("A 'null' AI provider is set - extractions will come back empty")

    llm_base = os.getenv("OPENAI_BASE_URL", "")
    stt_base = os.getenv("STT_BASE_URL", "") or llm_base

    if llm == "openai_compatible":
        if not os.getenv("OPENAI_API_KEY"):
            fail("OPENAI_API_KEY is not set", "get a key from aistudio.google.com")
        if not llm_base:
            fail("OPENAI_BASE_URL is not set", "set the Gemini OpenAI-compatible URL")

    # The single most common deployment mistake on this stack.
    if stt == "openai_compatible" and "generativelanguage.googleapis.com" in stt_base:
        fail(
            "Speech-to-text points at Gemini, which has no /audio/transcriptions",
            "set STT_BASE_URL=https://api.groq.com/openai/v1 and STT_API_KEY",
        )
    elif stt == "openai_compatible" and not os.getenv("STT_API_KEY"):
        warn("STT_API_KEY unset - falling back to OPENAI_API_KEY for transcription")
    else:
        ok("LLM and STT hosts are configured separately")


def check_audio_limits() -> None:
    audio_max = int(os.getenv("AUDIO_MAX_BYTES", "209715200"))
    stt_max = int(os.getenv("STT_MAX_PART_BYTES", "25165824"))
    if audio_max > stt_max:
        warn(
            f"AUDIO_MAX_BYTES ({audio_max // 1_048_576} MB) is above "
            f"STT_MAX_PART_BYTES ({stt_max // 1_048_576} MB) - uploads will be "
            "accepted then fail at transcription. Set them equal."
        )
    else:
        ok("audio size limits are consistent")


def check_security() -> None:
    env = os.getenv("ENVIRONMENT", "dev")
    secret = os.getenv("JWT_SECRET", "")

    if not secret or secret == "change-me-in-every-environment":
        fail("JWT_SECRET is missing or the default",
             'python -c "import secrets;print(secrets.token_urlsafe(48))"')
    elif len(secret) < 32:
        fail("JWT_SECRET is shorter than 32 characters", "generate a longer one")
    else:
        ok("JWT_SECRET looks strong")

    if env == "prod":
        if "*" in os.getenv("ALLOWED_ORIGINS", "*"):
            fail("ALLOWED_ORIGINS=* with ENVIRONMENT=prod", "set your real frontend origin")
        if os.getenv("STORAGE_PROVIDER") == "local":
            fail("STORAGE_PROVIDER=local with ENVIRONMENT=prod",
                 "audio would be lost on restart - use azure_blob")
    else:
        warn(f"ENVIRONMENT={env} - /docs stays open, CORS is unrestricted")


async def check_connectivity() -> None:
    """Actually call the services rather than just parsing strings."""
    print("\nLive connectivity:")

    # --- database ---
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(os.environ["DATABASE_URL"])
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        ok("database reachable")
    except Exception as exc:  # noqa: BLE001
        fail(f"database unreachable: {type(exc).__name__}", "check DATABASE_URL and Neon status")

    # --- redis ---
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(os.environ["REDIS_URL"])
        await client.ping()
        await client.aclose()
        ok("redis reachable")
    except Exception as exc:  # noqa: BLE001
        fail(f"redis unreachable: {type(exc).__name__}", "check the Upstash TCP URL")

    # --- LLM ---
    if os.getenv("LLM_PROVIDER") == "openai_compatible":
        try:
            import httpx

            base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
            key = os.getenv("OPENAI_API_KEY", "")
            model = os.getenv("OPENAI_MODEL", "gemini-3-flash")
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "reply with OK"}],
                        "max_tokens": 5,
                    },
                )
            if response.status_code == 404:
                fail(f"LLM model '{model}' not found (404)",
                     "check the exact model name in AI Studio")
            elif response.status_code == 401:
                fail("LLM rejected the API key (401)", "regenerate OPENAI_API_KEY")
            elif response.status_code >= 400:
                fail(f"LLM returned {response.status_code}", response.text[:120])
            else:
                ok(f"LLM reachable ({model})")
        except Exception as exc:  # noqa: BLE001
            fail(f"LLM unreachable: {type(exc).__name__}", "check OPENAI_BASE_URL")

    # --- STT ---
    if os.getenv("STT_PROVIDER") == "openai_compatible":
        stt_key = os.getenv("STT_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        stt_base = (os.getenv("STT_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")).rstrip("/")
        if not stt_key:
            warn("no STT key - skipping transcription check")
        else:
            try:
                import httpx

                # A tiny silent WAV proves the endpoint exists and the key is
                # accepted, without burning real audio quota.
                wav = (
                    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
                    b"\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
                )
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        f"{stt_base}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {stt_key}"},
                        files={"file": ("t.wav", wav, "audio/wav")},
                        data={"model": os.getenv("STT_MODEL", "whisper-large-v3")},
                    )
                if response.status_code == 404:
                    fail("STT endpoint not found (404)",
                         "this host has no /audio/transcriptions - use Groq")
                elif response.status_code == 401:
                    fail("STT rejected the API key (401)", "check STT_API_KEY")
                elif response.status_code >= 500:
                    warn(f"STT returned {response.status_code} - may be transient")
                else:
                    ok("STT endpoint reachable")
            except Exception as exc:  # noqa: BLE001
                fail(f"STT unreachable: {type(exc).__name__}", "check STT_BASE_URL")


async def main() -> int:
    print("BaatX preflight\n" + "=" * 50)
    print("\nConfiguration:")
    check_database_url()
    check_redis_url()
    check_ai_config()
    check_audio_limits()
    check_security()
    await check_connectivity()

    print("\n" + "=" * 50)
    if failures:
        print(f"{RED}{len(failures)} blocking issue(s). Fix before deploying.{RESET}")
        return 1
    if warnings:
        print(f"{YELLOW}Ready, with {len(warnings)} warning(s).{RESET}")
        return 0
    print(f"{GREEN}All checks passed. Ready to deploy.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
