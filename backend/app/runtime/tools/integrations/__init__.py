"""Concrete tools backed by the provider clients.

Only the tool classes live in the sibling modules; the helpers every provider tool needs
(credential checks, dry-run short-circuit, scope resolution, provider error mapping) live
here so each tool file only describes its own capability.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any, TypeVar

from app.core.errors import IntegrationError
from app.core.logging import get_logger
from app.runtime.tools.base import ToolContext, ToolResult

logger = get_logger(__name__)

T = TypeVar("T")

#: Long provider text (bodies, descriptions) is trimmed before it reaches the model.
TEXT_LIMIT = 2000
#: A file patch is only useful as its first few lines; the rest is noise in a prompt.
PATCH_LINE_LIMIT = 40
#: Upper bound on how many repositories a cross-repository read fans out to.
REPO_FANOUT_LIMIT = 5

PROVIDER_LABELS: dict[str, str] = {
    "github": "GitHub",
    "jira": "Jira",
    "google": "Google",
}

#: Scope keys a Buttlr may carry, per provider-agnostic naming in the draft schema.
SCOPE_KEYS = (
    "repositories",
    "labels",
    "folders",
    "projects",
    "channels",
    "file_ids",
    "spreadsheets",
    "calendars",
    "query",
)


def not_connected(provider: str) -> ToolResult:
    """The one message every tool returns when its provider was never connected."""
    label = PROVIDER_LABELS.get(provider, provider)
    return ToolResult.failure(
        f"{label} is not connected. Connect it in Integrations and try again."
    )


def dry_run_refusal(tool_name: str) -> ToolResult:
    return ToolResult.failure(f"Dry run: {tool_name} was not executed.")


async def call(
    coro: Coroutine[Any, Any, T], *, action: str
) -> tuple[T | None, ToolResult | None]:
    """Await a provider call, mapping an expected provider failure to a failed result.

    The planner can adapt to a failed observation; letting ``IntegrationError`` escape would
    abort the whole run instead.
    """
    try:
        return await coro, None
    except IntegrationError as exc:
        logger.warning("Provider call failed: %s (%s)", action, exc)
        return None, ToolResult.failure(str(exc))


def provider_scope(ctx: ToolContext, provider: str) -> dict[str, Any]:
    """Return the scope configured for one provider.

    Scope is stored provider-keyed (``{"github": {"repositories": [...]}}``); flat keys are
    also accepted so a hand-built context behaves the same way.
    """
    scope: dict[str, Any] = ctx.scope or {}
    nested = scope.get(provider)
    resolved: dict[str, Any] = {}
    if isinstance(nested, dict):
        resolved.update(nested)
    for key in SCOPE_KEYS:
        if key in scope:
            resolved.setdefault(key, scope[key])
    return resolved


def scope_values(ctx: ToolContext, provider: str, key: str) -> list[str]:
    """The list of values a scope key is restricted to; empty means unrestricted."""
    raw = provider_scope(ctx, provider).get(key)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def outside_scope(kind: str, requested: str, allowed: list[str]) -> ToolResult:
    listed = ", ".join(allowed)
    return ToolResult.failure(
        f"{requested} is outside this Buttlr's configured scope "
        f"({kind}: {listed}). Ask an administrator to widen the scope first."
    )


def matches_repository(allowed: list[str], repository: str) -> bool:
    """Compare ``owner/name`` against scope entries, which may be full or bare names."""
    candidate = repository.strip().strip("/").lower()
    for prefix in ("https://github.com/", "http://github.com/"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
    for entry in allowed:
        value = entry.strip().strip("/").lower()
        if not value:
            continue
        if value == candidate:
            return True
        if "/" not in value and candidate.split("/")[-1] == value:
            return True
        if value.endswith("/") and candidate.startswith(value):
            return True
    return False


def trim_text(value: Any, limit: int = TEXT_LIMIT) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit].rstrip() + " …[truncated]"
    return value


def trim_patch(patch: Any, limit: int = PATCH_LINE_LIMIT) -> Any:
    if not isinstance(patch, str) or "\n" not in patch:
        return patch
    lines = patch.splitlines()
    if len(lines) <= limit:
        return patch
    return "\n".join([*lines[:limit], f"…[truncated, {len(lines) - limit} more lines]"])


def compact(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Project a provider payload down to the fields the planner actually reasons about."""
    return {key: mapping.get(key) for key in keys if key in mapping}


def first(values: list[str], default: str = "") -> str:
    return values[0] if values else default


def list_summary(count: int, noun: str, where: str) -> str:
    plural = noun if count == 1 else f"{noun}s"
    where = f" in {where}" if where else ""
    return f"Found {count} {plural}{where}."



def query_summary(count: int, noun: str, query: str) -> str:
    plural = noun if count == 1 else f"{noun}s"
    return f"Found {count} {plural} for query “{query}”."


def page_limit(value: int, ceiling: int) -> int:
    return max(1, min(int(value), ceiling))
