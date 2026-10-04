"""OpenAI (and OpenAI-compatible) completions.

``OpenAIProvider`` is also the shared base for the OpenAI-compatible providers (Google's
generativelanguage endpoint, a local Ollama server): subclasses only override identity and
credential checks.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.core.errors import ModelError
from app.core.logging import get_logger
from app.runtime.models.base import (
    CompletionRequest,
    CompletionResponse,
    ModelProvider,
    ToolCall,
)
from app.schemas.execution import Usage

logger = get_logger(__name__)

__all__ = ["OpenAIProvider", "decode_tool_arguments", "usage_for"]


def decode_tool_arguments(raw: str, *, provider: str, tool: str) -> dict[str, Any]:
    """Decode a tool-call argument payload. Never raises: bad JSON becomes ``{}``."""
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning("%s returned undecodable JSON arguments for tool %s", provider, tool)
        return {}
    if isinstance(decoded, dict):
        return decoded
    logger.warning("%s returned non-object arguments for tool %s", provider, tool)
    return {}


def usage_for(
    settings: Settings,
    *,
    input_tokens: int,
    output_tokens: int,
) -> Usage:
    """Map vendor token counts onto ``Usage``, including the estimated USD cost."""
    input_tokens = max(0, int(input_tokens or 0))
    output_tokens = max(0, int(output_tokens or 0))
    cost = round(
        input_tokens / 1000.0 * settings.estimated_cost_per_1k_input
        + output_tokens / 1000.0 * settings.estimated_cost_per_1k_output,
        6,
    )
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd=cost,
        calls=1,
    )


class OpenAIProvider(ModelProvider):
    """Chat completions via the official ``openai`` SDK."""

    id = "openai"

    def __init__(
        self,
        settings: Settings,
        *,
        provider_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._settings = settings
        self.id = provider_id or type(self).id
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._base_url = base_url if base_url is not None else settings.openai_base_url
        self._model = model or settings.openai_default_model
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._model

    def _build_client(self) -> Any:
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": self._api_key or "missing"}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return AsyncOpenAI(**kwargs)

    def _client_or_fail(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise ModelError(f"No API key configured for the {self.id} provider.")
            self._client = self._build_client()
        return self._client

    async def is_available(self) -> bool:
        return bool(self._api_key)

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.close()
            except Exception:  # pragma: no cover - transport specific
                logger.debug("%s client close failed", self.id, exc_info=True)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        client = self._client_or_fail()
        messages = self._build_messages(request)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = self._build_tools(request)
            payload["tool_choice"] = "auto"

        try:
            result = await client.chat.completions.create(**payload)
        except Exception as exc:  # SDK raises a family of transport/auth errors
            raise ModelError(f"{self.id} completion failed: {exc}") from exc

        return self._to_response(result)

    def _build_messages(self, request: CompletionRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for message in request.messages:
            if message.role == "tool":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id or message.name or "tool",
                        "content": message.content,
                    }
                )
                continue
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "assistant":
                entry["name"] = message.name
            messages.append(entry)
        return messages

    @staticmethod
    def _build_tools(request: CompletionRequest) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                },
            }
            for tool in request.tools
        ]

    def _to_response(self, result: Any) -> CompletionResponse:
        choices = getattr(result, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        content = getattr(message, "content", None) or ""
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None

        tool_calls: list[ToolCall] = []
        for raw_call in getattr(message, "tool_calls", None) or []:
            function = getattr(raw_call, "function", None)
            name = getattr(function, "name", None)
            if not name:
                logger.warning("%s returned a tool call without a function name", self.id)
                continue
            tool_calls.append(
                ToolCall(
                    id=str(getattr(raw_call, "id", None) or f"call_{len(tool_calls)}"),
                    name=name,
                    arguments=decode_tool_arguments(
                        getattr(function, "arguments", "") or "",
                        provider=self.id,
                        tool=name,
                    ),
                )
            )

        raw_usage = getattr(result, "usage", None)
        usage = usage_for(
            self._settings,
            input_tokens=int(getattr(raw_usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(raw_usage, "completion_tokens", 0) or 0),
        )
        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            provider=self.id,
            model=str(getattr(result, "model", None) or self._model),
            finish_reason=str(finish_reason or ("tool_calls" if tool_calls else "stop")),
        )
