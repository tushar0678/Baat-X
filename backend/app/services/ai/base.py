"""Provider abstractions.

Swapping Azure OpenAI for any OpenAI-compatible endpoint, or Azure Speech for
Google/AWS, must never require touching service or API code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class TranscriptSegment:
    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None
    language: str | None = None


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    provider: str = "unknown"


@dataclass(slots=True)
class LLMResult:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@runtime_checkable
class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(
        self,
        *,
        audio_uri: str | None = None,
        audio_bytes: bytes | None = None,
        content_type: str | None = None,
        candidate_locales: list[str] | None = None,
    ) -> TranscriptionResult: ...

    async def healthy(self) -> bool: ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult: ...

    async def complete_text(
        self, *, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None
    ) -> LLMResult: ...

    async def healthy(self) -> bool: ...


@runtime_checkable
class StorageProvider(Protocol):
    name: str

    async def upload(
        self, *, blob_name: str, data: bytes, content_type: str, ttl_minutes: int
    ) -> str: ...

    async def download(self, blob_name: str) -> bytes: ...

    async def delete(self, blob_name: str) -> bool: ...

    async def signed_read_url(self, blob_name: str, ttl_minutes: int = 30) -> str: ...

    async def healthy(self) -> bool: ...
