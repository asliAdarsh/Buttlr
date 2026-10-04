"""Model provider registry.

``build_providers`` returns every provider the runtime knows about, in preference order. The
router walks the list, so order here is order of preference: hosted frontier models first,
local models next, and the deterministic offline provider last as the always-available floor.
"""

from __future__ import annotations

from app.core.config import Settings
from app.runtime.models.base import ModelProvider
from app.runtime.models.providers.anthropic import AnthropicProvider
from app.runtime.models.providers.google import GoogleProvider
from app.runtime.models.providers.heuristic import HeuristicProvider
from app.runtime.models.providers.ollama import OllamaProvider
from app.runtime.models.providers.openai import OpenAIProvider

__all__ = [
    "AnthropicProvider",
    "GoogleProvider",
    "HeuristicProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "build_providers",
]


def build_providers(settings: Settings) -> list[ModelProvider]:
    """Construct every model provider from settings, in preference order."""
    return [
        OpenAIProvider(settings),
        AnthropicProvider(settings),
        GoogleProvider(settings),
        OllamaProvider(settings),
        HeuristicProvider(settings),
    ]
