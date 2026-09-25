"""Speech-to-text providers.

Azure AI Speech (fast transcription REST API) is the production default because
it does automatic language identification across hi-IN / en-IN, which is what
Hinglish sales calls need. OpenAI-compatible Whisper is the portable fallback.

Long recordings are handled by uploading once and letting the provider do the
segmentation; where a provider has a hard size limit we split the payload and
stitch the transcript back together in order.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.errors import ProviderUnavailableError
from app.services.ai.base import TranscriptionResult, TranscriptSegment

log = get_logger(__name__)

_retry = retry(
    retry=retry_if_exception_type((httpx.HTTPError, ProviderUnavailableError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=2, max=30),
    reraise=True,
)


class AzureSpeechProvider:
    """Azure AI Speech `transcriptions` fast REST endpoint."""

    name = "azure_speech"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._region = settings.azure_speech_region
        self._key = settings.azure_speech_key
        self._endpoint = settings.azure_speech_endpoint or (
            f"https://{self._region}.api.cognitive.microsoft.com"
        )
        if not self._key or not (self._region or settings.azure_speech_endpoint):
            raise ProviderUnavailableError("Azure Speech is not configured")

    @_retry
    async def transcribe(
        self,
        *,
        audio_uri: str | None = None,
        audio_bytes: bytes | None = None,
        content_type: str | None = None,
        candidate_locales: list[str] | None = None,
    ) -> TranscriptionResult:
        if audio_bytes is None:
            raise ProviderUnavailableError("Azure Speech requires the audio payload")

        locales = candidate_locales or self._settings.stt_candidate_locales
        url = f"{self._endpoint}/speechtotext/transcriptions:transcribe?api-version=2024-11-15"
        definition = {"locales": locales, "profanityFilterMode": "None", "channels": [0]}
        files = {
            "audio": ("audio", io.BytesIO(audio_bytes), content_type or "application/octet-stream"),
            "definition": (None, json.dumps(definition), "application/json"),
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            response = await client.post(
                url, headers={"Ocp-Apim-Subscription-Key": self._key}, files=files
            )

        if response.status_code >= 500:
            raise ProviderUnavailableError(f"Azure Speech {response.status_code}")
        if response.status_code >= 400:
            log.warning("azure_speech_rejected", status=response.status_code)
            raise ProviderUnavailableError("Azure Speech rejected the audio")

        data: dict[str, Any] = response.json()
        phrases = data.get("phrases") or []
        segments = [
            TranscriptSegment(
                text=p.get("text", ""),
                start_seconds=(p.get("offsetMilliseconds") or 0) / 1000,
                end_seconds=(
                    (p.get("offsetMilliseconds") or 0) + (p.get("durationMilliseconds") or 0)
                ) / 1000,
                language=p.get("locale"),
            )
            for p in phrases
        ]
        combined = data.get("combinedPhrases") or []
        text = combined[0].get("text") if combined else None
        text = text or " ".join(s.text for s in segments)

        return TranscriptionResult(
            text=text.strip(),
            language=(segments[0].language if segments else locales[0]),
            duration_seconds=(data.get("durationMilliseconds") or 0) / 1000 or None,
            segments=segments,
            provider=self.name,
        )

    async def healthy(self) -> bool:
        return bool(self._key)


class OpenAICompatibleSTT:
    """Whisper-style `/audio/transcriptions`. Splits payloads above the configured limit.

    Uses the *resolved* STT settings (``resolved_stt_base_url`` /
    ``resolved_stt_api_key`` / ``resolved_stt_model``), not the plain
    ``openai_*`` fields directly.

    This matters because the STT host can legitimately differ from the LLM
    host - e.g. Gemini for chat/extraction plus Groq for Whisper, which is the
    free/budget stack this app is commonly deployed with. Gemini's
    OpenAI-compatible surface has no ``/audio/transcriptions`` endpoint, so
    reading ``openai_base_url`` here instead of the resolved value sends every
    transcription request to the wrong host and produces a silent 404,
    regardless of what STT_BASE_URL/STT_API_KEY/STT_MODEL are set to.
    """

    name = "openai_compatible_stt"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.resolved_stt_base_url.rstrip("/")
        self._api_key = settings.resolved_stt_api_key
        self._model = settings.resolved_stt_model
        self._max_part_bytes = settings.stt_max_part_bytes

        if not self._api_key:
            raise ProviderUnavailableError(
                "No STT API key configured (set STT_API_KEY or OPENAI_API_KEY)"
            )
        if not self._base_url:
            raise ProviderUnavailableError(
                "No STT base URL configured (set STT_BASE_URL or OPENAI_BASE_URL)"
            )

    @_retry
    async def _transcribe_part(self, part: bytes, content_type: str, language: str | None) -> str:
        files = {"file": ("audio", io.BytesIO(part), content_type)}
        data = {"model": self._model, "response_format": "json"}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            response = await client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files=files,
                data=data,
            )

        if response.status_code >= 500:
            raise ProviderUnavailableError(f"STT {response.status_code}")
        if response.status_code == 404:
            # Almost always a base-URL mismatch (e.g. pointed at a host with no
            # Whisper-compatible endpoint) - surface that clearly instead of a
            # bare "404 Not Found" deep in a stack trace.
            log.warning(
                "stt_endpoint_not_found",
                base_url=self._base_url,
                model=self._model,
            )
            raise ProviderUnavailableError(
                f"STT endpoint not found at {self._base_url}/audio/transcriptions. "
                "Check STT_BASE_URL/STT_API_KEY/STT_MODEL."
            )
        response.raise_for_status()
        return (response.json().get("text") or "").strip()

    async def transcribe(
        self,
        *,
        audio_uri: str | None = None,
        audio_bytes: bytes | None = None,
        content_type: str | None = None,
        candidate_locales: list[str] | None = None,
    ) -> TranscriptionResult:
        if audio_bytes is None:
            raise ProviderUnavailableError("STT requires the audio payload")

        language = (candidate_locales or ["hi"])[0].split("-")[0]
        parts = [
            audio_bytes[i : i + self._max_part_bytes]
            for i in range(0, len(audio_bytes), self._max_part_bytes)
        ]

        texts = []
        for part in parts:  # sequential: preserves ordering and respects rate limits
            texts.append(await self._transcribe_part(part, content_type or "audio/mpeg", language))
            await asyncio.sleep(0)

        return TranscriptionResult(
            text=" ".join(t for t in texts if t).strip(), language=language, provider=self.name
        )

    async def healthy(self) -> bool:
        return bool(self._api_key and self._base_url)


class GoogleSpeechProvider:
    """Placeholder for Google STT v2 - wire credentials before enabling."""

    name = "google_speech"

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        raise ProviderUnavailableError("Google Speech provider is not configured")


class AWSTranscribeProvider:
    """Placeholder for Amazon Transcribe - wire credentials before enabling."""

    name = "aws_transcribe"

    def __init__(self, settings: Settings) -> None:  # pragma: no cover
        raise ProviderUnavailableError("AWS Transcribe provider is not configured")


class NullSTT:
    """Returns an empty transcript - used by tests and local runs without cloud keys."""

    name = "null"

    async def transcribe(self, **kwargs: Any) -> TranscriptionResult:
        return TranscriptionResult(text="", language="en-IN", provider=self.name)

    async def healthy(self) -> bool:
        return True
