"""Provider factory + process-wide singletons."""

from __future__ import annotations

from functools import lru_cache

from app.config.logging import get_logger
from app.config.settings import Settings, get_settings
from app.services.ai.base import LLMProvider, SpeechToTextProvider, StorageProvider
from app.services.ai.llm_providers import AzureOpenAILLM, NullLLM, OpenAICompatibleLLM
from app.services.ai.stt_providers import (
    AWSTranscribeProvider,
    AzureSpeechProvider,
    GoogleSpeechProvider,
    NullSTT,
    OpenAICompatibleSTT,
)
from app.services.storage.providers import AzureBlobStorage, GCSStorage, LocalStorage, S3Storage

log = get_logger(__name__)


def build_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    match settings.llm_provider:
        case "azure_openai":
            return AzureOpenAILLM(settings)
        case "openai_compatible":
            return OpenAICompatibleLLM(settings)
        case _:
            return NullLLM()


def build_stt(settings: Settings | None = None) -> SpeechToTextProvider:
    settings = settings or get_settings()
    match settings.stt_provider:
        case "azure_speech":
            return AzureSpeechProvider(settings)
        case "openai_compatible":
            return OpenAICompatibleSTT(settings)
        case "google":
            return GoogleSpeechProvider(settings)
        case "aws":
            return AWSTranscribeProvider(settings)
        case _:
            return NullSTT()


def build_storage(settings: Settings | None = None) -> StorageProvider:
    settings = settings or get_settings()
    match settings.storage_provider:
        case "azure_blob":
            return AzureBlobStorage(settings)
        case "s3":
            return S3Storage(settings)
        case "gcs":
            return GCSStorage(settings)
        case _:
            return LocalStorage(settings)


@lru_cache
def llm_provider() -> LLMProvider:
    return build_llm()


@lru_cache
def stt_provider() -> SpeechToTextProvider:
    return build_stt()


@lru_cache
def storage_provider() -> StorageProvider:
    return build_storage()


async def close_providers() -> None:
    storage = storage_provider()
    close = getattr(storage, "close", None)
    if close is not None:
        await close()
