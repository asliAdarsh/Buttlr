"""Google Gemini via its OpenAI-compatible endpoint.

Gemini is reachable through the same wire format as OpenAI, so this provider reuses
``OpenAIProvider`` and only overrides identity and credential availability.
"""

from __future__ import annotations

from app.core.config import Settings
from app.runtime.models.providers.openai import OpenAIProvider

__all__ = ["GoogleProvider"]


class GoogleProvider(OpenAIProvider):
    id = "google"

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            provider_id=self.id,
            api_key=settings.google_api_key,
            base_url=settings.google_base_url,
            model=settings.google_default_model,
        )

    async def is_available(self) -> bool:
        return bool(self._api_key)
