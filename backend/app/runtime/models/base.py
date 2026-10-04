"""Model provider contract.

Buttlrs talk to ``ModelRouter``; they never import a vendor SDK. Providers declare their id
and availability, and the router handles selection, fallback and usage accounting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.execution import Usage

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    role: Role
    content: str = ""
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @property
    def raw_arguments(self) -> str:
        import json

        return json.dumps(self.arguments)


class CompletionRequest(BaseModel):
    messages: list[Message]
    tools: list[ToolSpec] = Field(default_factory=list)
    temperature: float = 0.2
    max_tokens: int = 2048
    json_mode: bool = False
    system: str | None = None


class CompletionResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    finish_reason: str = "stop"

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class ModelProvider(ABC):
    id: str

    @abstractmethod
    async def is_available(self) -> bool:
        """Cheap check: is this provider configured and reachable enough to attempt?"""

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    async def close(self) -> None:
        return None
