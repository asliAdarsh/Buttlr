"""Model routing.

``ModelRouter`` is the single entry point the runtime uses to talk to an LLM. It resolves
``ModelConfig`` (explicit provider, or ``auto``) into a concrete provider, applies
per-provider defaults, walks the configured fallback chain on failure, and accumulates usage.
"""

from __future__ import annotations

from app.core.errors import ModelError
from app.core.logging import get_logger
from app.runtime.models.base import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ModelProvider,
    ToolCall,
    ToolSpec,
)
from app.schemas.buttlr import ModelConfig

logger = get_logger(__name__)

__all__ = [
    "CompletionRequest",
    "CompletionResponse",
    "Message",
    "ModelProvider",
    "ModelRouter",
    "ToolCall",
    "ToolSpec",
]


class ModelRouter:
    def __init__(self, providers: list[ModelProvider], preference: list[str] | None = None) -> None:
        self._providers: dict[str, ModelProvider] = {p.id: p for p in providers}
        self._preference = preference or list(self._providers)
        #: Last failure per provider, so a degraded run can say *why* it degraded instead of
        #: silently changing model. Advisory text only; it never decides behaviour.
        self.last_failures: dict[str, str] = {}

    @property
    def providers(self) -> dict[str, ModelProvider]:
        return dict(self._providers)

    def get(self, provider_id: str) -> ModelProvider | None:
        return self._providers.get(provider_id)

    async def available_providers(self) -> list[str]:
        out: list[str] = []
        for provider_id in self._preference:
            provider = self._providers.get(provider_id)
            if provider and await provider.is_available():
                out.append(provider_id)
        return out

    async def resolve(self, config: ModelConfig) -> tuple[ModelProvider, str]:
        chain = self._chain(config)
        for candidate in chain:
            provider = self._providers.get(candidate)
            if provider and await provider.is_available():
                return provider, self._model_name(provider.id, config)
        raise ModelError(
            "No model provider is available. Add an API key (OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GOOGLE_API_KEY) or run a local model with OLLAMA_BASE_URL."
        )

    async def complete(self, config: ModelConfig, request: CompletionRequest) -> CompletionResponse:
        chain = self._chain(config)
        last_error: Exception | None = None
        for candidate in chain:
            provider = self._providers.get(candidate)
            if provider is None or not await provider.is_available():
                continue
            try:
                response = await provider.complete(request)
                self.last_failures.pop(candidate, None)
                logger.debug(
                    "model completion ok provider=%s model=%s tools=%d",
                    response.provider,
                    response.model,
                    len(response.tool_calls),
                )
                return response
            except Exception as exc:
                last_error = exc
                self.last_failures[candidate] = str(exc)
                logger.warning("provider %s failed: %s", candidate, exc)
                continue
        if last_error is not None:
            raise ModelError(f"All model providers failed. Last error: {last_error}")
        raise ModelError("No model provider is available for this request.")

    def _chain(self, config: ModelConfig) -> list[str]:
        chain: list[str] = []
        if config.provider and config.provider != "auto":
            chain.append(config.provider)
        for name in config.fallback:
            if name not in chain:
                chain.append(name)
        for name in self._preference:
            if name not in chain:
                chain.append(name)
        return chain

    @staticmethod
    def _model_name(provider_id: str, config: ModelConfig) -> str:
        if config.name and config.name != "auto":
            return config.name
        return {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-latest",
            "google": "gemini-2.0-flash",
            "ollama": "qwen2.5:7b",
            "heuristic": "heuristic",
        }.get(provider_id, "auto")
