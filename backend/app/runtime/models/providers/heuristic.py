"""Deterministic offline provider.

This is the fallback that keeps Buttlr fully functional with no cloud credentials: it drafts
AI employee configurations with the rule-based generator in ``app.runtime.drafting`` and
answers everything else with a short, stable completion. It never calls out to the network.
"""

from __future__ import annotations

import json
import re

from app.core.config import Settings
from app.runtime.drafting import heuristic_draft
from app.runtime.models.base import (
    CompletionRequest,
    CompletionResponse,
    ModelProvider,
)
from app.schemas.execution import Usage

__all__ = ["HeuristicProvider"]

BUILDER_MARKER = "You are the Buttlr Builder"
_MAX_COMPLETION_CHARS = 2000


class HeuristicProvider(ModelProvider):
    id = "heuristic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def is_available(self) -> bool:
        return True

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        system = request.system or ""
        if request.json_mode and BUILDER_MARKER in system:
            content = self._draft(request)
        else:
            content = self._plain(request)
        return CompletionResponse(
            content=content,
            usage=Usage(),
            provider=self.id,
            model=self._settings.default_model if self._settings.default_model != "auto" else self.id,
            finish_reason="stop",
        )

    def _draft(self, request: CompletionRequest) -> str:
        plan = heuristic_draft(
            _user_request(request),
            [tool.name for tool in request.tools],
            default_timezone=_timezone(request) or "UTC",
            teams=_teams(request),
            organization_name=_organization(request),
        )
        return json.dumps(plan, ensure_ascii=False, indent=2)

    def _plain(self, request: CompletionRequest) -> str:
        prompt = _user_request(request)
        summary = re.sub(r"\s+", " ", prompt).strip()
        if len(summary) > _MAX_COMPLETION_CHARS:
            summary = summary[:_MAX_COMPLETION_CHARS] + "\u2026"
        return (
            f"{self.id}: no language model is configured, so this response is a deterministic "
            f"placeholder.\n\nRequest: {summary or '(empty)'}"
        )


def _user_request(request: CompletionRequest) -> str:
    """Pull the description out of the builder prompt, which embeds it after a marker."""
    for message in reversed(request.messages):
        if message.role != "user":
            continue
        content = message.content
        marker = "User request:"
        if marker in content:
            return content.split(marker, 1)[1].strip()
        return content.strip()
    return ""


def _context_value(request: CompletionRequest, label: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(label)}\s+(.+)$", re.MULTILINE)
    for message in request.messages:
        match = pattern.search(message.content)
        if match:
            value = match.group(1).strip()
            return None if value.lower() == "unknown" else value
    return None


def _timezone(request: CompletionRequest) -> str | None:
    return _context_value(request, "Default timezone:")


def _organization(request: CompletionRequest) -> str | None:
    return _context_value(request, "Organization:")


def _teams(request: CompletionRequest) -> list[str] | None:
    value = _context_value(request, "Available teams:")
    if not value:
        return None
    teams = [team.strip() for team in value.split(",") if team.strip()]
    return teams or None
