"""Anthropic Messages API provider.

The Messages API differs from the OpenAI shape in three ways that matter here: the system
prompt is a top-level field, assistant tool calls are ``tool_use`` content blocks, and tool
results are separate ``user`` messages keyed by ``tool_use_id``.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.errors import ModelError
from app.core.logging import get_logger
from app.runtime.models.base import (
    CompletionRequest,
    CompletionResponse,
    Message,
    ModelProvider,
    ToolCall,
)
from app.runtime.models.providers.openai import decode_tool_arguments, usage_for

logger = get_logger(__name__)



class AnthropicProvider(ModelProvider):
    id = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_default_model
        self._client: Any | None = None

    async def is_available(self) -> bool:
        return bool(self._api_key)

    def _client_or_fail(self) -> Any:
        if self._client is None:
            if not self._api_key:
                raise ModelError("No API key configured for the anthropic provider.")
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.close()
            except Exception:  # pragma: no cover - transport specific
                logger.debug("anthropic client close failed", exc_info=True)

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        client = self._client_or_fail()
        messages = self._build_messages(request.messages)
        if not messages:
            raise ModelError("The anthropic provider requires at least one non-system message.")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        system_prompt = request.system or self._extract_system(request.messages)
        if system_prompt:
            payload["system"] = system_prompt
        if request.tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters
                    or {"type": "object", "properties": {}},
                }
                for tool in request.tools
            ]

        try:
            result = await client.messages.create(**payload)
        except Exception as exc:
            raise ModelError(f"anthropic completion failed: {exc}") from exc

        return self._to_response(result)

    @staticmethod
    def _extract_system(messages: list[Message]) -> str:
        return "\n\n".join(m.content for m in messages if m.role == "system" and m.content)

    @staticmethod
    def _build_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or message.name or "tool",
                    "content": message.content,
                }
                # Consecutive tool results must share one user turn.
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
                continue

            content: list[dict[str, Any]] = []
            if message.content:
                content.append({"type": "text", "text": message.content})
            out.append({"role": message.role, "content": content if content else " "})
        return out

    def _to_response(self, result: Any) -> CompletionResponse:
        texts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(result, "content", None) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "") or ""
                if text:
                    texts.append(text)
            elif block_type == "tool_use":
                name = getattr(block, "name", None)
                if not name:
                    logger.warning("anthropic returned a tool_use block without a name")
                    continue
                arguments = getattr(block, "input", None)
                if not isinstance(arguments, dict):
                    arguments = decode_tool_arguments(
                        arguments if isinstance(arguments, str) else "",
                        provider=self.id,
                        tool=name,
                    )
                tool_calls.append(
                    ToolCall(
                        id=str(getattr(block, "id", None) or f"call_{len(tool_calls)}"),
                        name=name,
                        arguments=arguments,
                    )
                )

        raw_usage = getattr(result, "usage", None)
        usage = usage_for(
            self._settings,
            input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
        )
        stop_reason = str(getattr(result, "stop_reason", None) or "stop")
        return CompletionResponse(
            content="\n".join(texts),
            tool_calls=tool_calls,
            usage=usage,
            provider=self.id,
            model=str(getattr(result, "model", None) or self._model),
            finish_reason="tool_calls" if tool_calls else stop_reason,
        )
