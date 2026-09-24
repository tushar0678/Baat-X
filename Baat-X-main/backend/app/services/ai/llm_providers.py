"""LLM implementations: Azure OpenAI (primary) and any OpenAI-compatible endpoint."""

from __future__ import annotations

from typing import Any

from openai import APITimeoutError, AsyncAzureOpenAI, AsyncOpenAI, InternalServerError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config.logging import get_logger
from app.config.settings import Settings
from app.core.errors import ProviderUnavailableError
from app.services.ai.base import LLMResult

log = get_logger(__name__)

_RETRYABLE = (RateLimitError, APITimeoutError, InternalServerError)
_retry = retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=20),
    reraise=True,
)


class _BaseOpenAILLM:
    name = "openai"

    def __init__(self, client: AsyncOpenAI | AsyncAzureOpenAI, model: str, settings: Settings):
        self._client = client
        self.model = model
        self._settings = settings

    @_retry
    async def _chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        max_output_tokens: int | None,
        temperature: float | None,
    ) -> LLMResult:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"} if json_mode else {"type": "text"},
                max_tokens=max_output_tokens or self._settings.llm_max_output_tokens,
                temperature=(
                    self._settings.llm_temperature if temperature is None else temperature
                ),
                timeout=self._settings.llm_timeout_seconds,
            )
        except _RETRYABLE as exc:
            log.warning("llm_call_failed", provider=self.name, model=self.model)
            raise ProviderUnavailableError("LLM provider unavailable") from exc

        choice = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResult(
            content=choice,
            model=self.model,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_hint: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        if schema_hint:
            user_prompt = f"{user_prompt}\n\nReturn JSON matching exactly this shape:\n{schema_hint}"
        return await self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=True,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

    async def complete_text(
        self, *, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None
    ) -> LLMResult:
        return await self._chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_mode=False,
            max_output_tokens=max_output_tokens,
            temperature=None,
        )

    async def healthy(self) -> bool:
        try:
            await self._client.models.list()
        except Exception:  # noqa: BLE001 - health probe must never raise
            return False
        return True


class AzureOpenAILLM(_BaseOpenAILLM):
    """Primary production LLM. Uses Managed Identity when no API key is configured."""

    name = "azure_openai"

    def __init__(self, settings: Settings):
        if not settings.azure_openai_endpoint:
            raise ProviderUnavailableError("AZURE_OPENAI_ENDPOINT is not configured")

        kwargs: dict[str, Any] = {
            "azure_endpoint": settings.azure_openai_endpoint,
            "api_version": settings.azure_openai_api_version,
            "timeout": settings.llm_timeout_seconds,
        }
        if settings.azure_openai_api_key:
            kwargs["api_key"] = settings.azure_openai_api_key
        elif settings.azure_openai_use_managed_identity:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
        else:
            raise ProviderUnavailableError("No Azure OpenAI credential configured")

        super().__init__(AsyncAzureOpenAI(**kwargs), settings.azure_openai_deployment, settings)


class OpenAICompatibleLLM(_BaseOpenAILLM):
    """Works with OpenAI, vLLM, Ollama, Together, Groq - anything OpenAI-shaped."""

    name = "openai_compatible"

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise ProviderUnavailableError("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.llm_timeout_seconds,
        )
        super().__init__(client, settings.openai_model, settings)


class NullLLM:
    """Used in tests and local smoke runs: deterministic, no network."""

    name = "null"
    model = "null"

    async def complete_json(self, **_: Any) -> LLMResult:
        return LLMResult(content="{}", model=self.model)

    async def complete_text(self, **_: Any) -> LLMResult:
        return LLMResult(content="", model=self.model)

    async def healthy(self) -> bool:
        return True