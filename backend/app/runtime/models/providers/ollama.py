"""Local Ollama models through the OpenAI-compatible server API.

Availability is a cheap liveness probe of ``GET {base}/api/tags``; completion goes through
``/v1/chat/completions`` exactly like any other OpenAI-compatible endpoint.
"""

from __future__ import annotations

from app.core.config import Settings
from app.runtime.models.providers.openai import OpenAIProvider

__all__ = ["OllamaProvider"]

PROBE_TIMEOUT_SECONDS = 1.5
# The local server ignores the bearer token but the SDK requires one.
PLACEHOLDER_API_KEY = "ollama"


class OllamaProvider(OpenAIProvider):
    id = "ollama"

    def __init__(self, settings: Settings) -> None:
        base = (settings.ollama_base_url or "").strip().rstrip("/")
        super().__init__(
            settings,
            provider_id=self.id,
            api_key=PLACEHOLDER_API_KEY,
            base_url=f"{base}/v1" if base else None,
            model=settings.ollama_default_model,
        )
        self._server_base = base

    async def is_available(self) -> bool:
        if not self._server_base:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
                response = await client.get(f"{self._server_base}/api/tags")
            return response.status_code < 400
        except Exception:
            return False
