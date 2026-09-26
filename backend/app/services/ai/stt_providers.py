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
import shutil
import subprocess
import tempfile
from pathlib import Path
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


_FFMPEG_PATH = shutil.which("ffmpeg")
_FFPROBE_PATH = shutil.which("ffprobe")

# Audio codecs a Whisper-compatible endpoint decodes without complaint. This is
# deliberately a codec allowlist, not a container/content-type allowlist: a
# file can claim "audio/mp4" (a perfectly valid container) while the stream
# inside it is encoded with something OpenAI's Whisper backend still rejects -
# this is exactly what several manufacturers' call-recorder apps produce
# (commonly an AMR-NB voice codec wrapped in an MP4/3GP container labelled
# as audio/mp4). Trusting the container label alone let that case through
# untranscoded and produced a 400 from OpenAI with no further recourse.
#
# Each codec maps to a single (extension, content_type) PAIR that are known to
# agree with each other for OpenAI's format sniffing. Sending a mismatched
# pair - e.g. filename "audio.m4a" with Content-Type "audio/mp4" - is enough
# on its own to make OpenAI reject an otherwise perfectly valid file with
# "Invalid file format": this was an actual production regression the first
# version of this mapping introduced, by choosing the extension and
# content-type from two different, uncoordinated dicts.
_CODEC_TO_EXTENSION_AND_CONTENT_TYPE: dict[str, tuple[str, str]] = {
    "aac": ("mp4", "audio/mp4"),
    "mp3": ("mp3", "audio/mpeg"),
    "flac": ("flac", "audio/flac"),
    "vorbis": ("ogg", "audio/ogg"),
    "opus": ("ogg", "audio/ogg"),
    "pcm_s16le": ("wav", "audio/wav"),
    "pcm_s24le": ("wav", "audio/wav"),
    "pcm_f32le": ("wav", "audio/wav"),
}

_WHISPER_SAFE_CODECS = frozenset(_CODEC_TO_EXTENSION_AND_CONTENT_TYPE.keys())


def _probe_audio_codec(audio_bytes: bytes) -> str | None:
    """Returns the audio codec name (e.g. "aac", "amr_nb"), or None if it can't be determined."""
    if not _FFPROBE_PATH:
        return None

    with tempfile.NamedTemporaryFile(suffix=".bin") as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        result = subprocess.run(
            [
                _FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "json",
                tmp.name,
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        try:
            parsed = json.loads(result.stdout or "{}")
            streams = parsed.get("streams") or []
            return streams[0].get("codec_name") if streams else None
        except (json.JSONDecodeError, IndexError, AttributeError):
            return None


def _transcode_to_wav(audio_bytes: bytes) -> bytes:
    """Converts arbitrary audio into 16kHz mono WAV via ffmpeg.

    Exists because a phone's call-recorder app can save its output with a
    codec a Whisper-compatible endpoint flatly rejects - most commonly
    AMR-NB (a low-bitrate speech codec used for call audio), regardless of
    what the surrounding container or content-type claims to be. This is not
    one device's problem: whichever app or manufacturer produced the
    recording, if its encoding isn't in the accepted set, the fix is the
    same - normalise to a format every provider accepts, rather than trying
    to special-case each unsupported encoder as it's discovered.

    Raises ProviderUnavailableError with a user-facing message if ffmpeg is
    unavailable or the input can't be decoded at all (e.g. a genuinely
    corrupted or empty file) - callers should treat that as a job failure,
    not retry it, since retrying can't fix a bad recording.
    """
    if not _FFMPEG_PATH:
        raise ProviderUnavailableError(
            "This recording's audio format isn't supported.",
            user_message="This recording's audio format isn't supported. Please try a different recording.",
        )

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "input.bin"
        dst = Path(tmp) / "output.wav"
        src.write_bytes(audio_bytes)

        result = subprocess.run(
            [
                _FFMPEG_PATH,
                "-y",
                "-i", str(src),
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                str(dst),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )

        if result.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
            log.warning(
                "audio_transcode_failed",
                ffmpeg_stderr=result.stderr.decode("utf-8", errors="replace")[-500:],
            )
            raise ProviderUnavailableError(
                "audio transcode failed",
                user_message="We couldn't process this recording's audio. Please try a different recording.",
            )

        return dst.read_bytes()


def _prepare_for_whisper(audio_bytes: bytes, content_type: str | None) -> tuple[bytes, str, str]:
    """Returns (bytes, content_type, filename_extension) ready to upload.

    Probes the actual audio codec (not just the claimed content-type/container)
    and only transcodes when that codec is one Whisper is known to reject.
    A file whose container says "audio/mp4" but whose stream is AMR-NB - the
    common shape of call-recorder output on several manufacturers' phones -
    is transcoded here even though "audio/mp4" looks like a natively
    supported content type, because the container label was never a reliable
    signal for what OpenAI's backend can actually decode.

    When the codec IS one Whisper accepts, the returned extension and
    content_type always come from the same lookup table entry, so they never
    disagree with each other - a mismatched pair (e.g. ".m4a" filename with
    an "audio/mp4" Content-Type) is by itself enough to make OpenAI reject
    an otherwise valid file.

    If ffprobe isn't available, or the codec can't be determined, this errs
    on the side of transcoding rather than gambling on a 400 from OpenAI -
    transcoding a file that was already fine just costs a little CPU time.
    """
    codec = _probe_audio_codec(audio_bytes)

    if codec is not None and codec in _WHISPER_SAFE_CODECS:
        ext, native_content_type = _CODEC_TO_EXTENSION_AND_CONTENT_TYPE[codec]
        return audio_bytes, native_content_type, ext

    log.info(
        "audio_transcoding_to_wav",
        original_content_type=content_type,
        detected_codec=codec,
    )
    wav_bytes = _transcode_to_wav(audio_bytes)
    return wav_bytes, "audio/wav", "wav"


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
    async def _transcribe_part(
        self, part: bytes, content_type: str, extension: str, language: str | None
    ) -> str:
        files = {"file": (f"audio.{extension}", io.BytesIO(part), content_type)}
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
            log.warning(
                "stt_endpoint_not_found",
                base_url=self._base_url,
                model=self._model,
            )
            raise ProviderUnavailableError(
                f"STT endpoint not found at {self._base_url}/audio/transcriptions. "
                "Check STT_BASE_URL/STT_API_KEY/STT_MODEL."
            )
        if response.status_code == 400:
            log.warning(
                "stt_rejected_audio",
                base_url=self._base_url,
                content_type=content_type,
                extension=extension,
                part_bytes=len(part),
                response_body=response.text[:1000],
            )
            raise ProviderUnavailableError(
                "STT rejected the audio",
                user_message="We couldn't process this recording's audio. Please try a different recording.",
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

        # Transcoding decision runs once on the whole file, before chunking -
        # splitting an unsupported codec's stream into byte-range parts first
        # and probing/transcoding each part independently would produce
        # corrupt, independently-undecodable fragments for most codecs.
        prepared_bytes, prepared_content_type, extension = await asyncio.to_thread(
            _prepare_for_whisper, audio_bytes, content_type
        )

        language = (candidate_locales or ["hi"])[0].split("-")[0]
        parts = [
            prepared_bytes[i : i + self._max_part_bytes]
            for i in range(0, len(prepared_bytes), self._max_part_bytes)
        ]

        texts = []
        for part in parts:  # sequential: preserves ordering and respects rate limits
            texts.append(
                await self._transcribe_part(part, prepared_content_type, extension, language)
            )
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
