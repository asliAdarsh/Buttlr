"""Tool contract.

A tool is the only way a Buttlr can touch the outside world. Each one declares the
permission it needs and how risky it is; the permission engine uses those declarations,
never anything supplied by the caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.schemas.enums import Permission, RiskLevel


class ToolResult(BaseModel):
    ok: bool
    summary: str = ""
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(cls, summary: str, data: Any = None, **meta: Any) -> ToolResult:
        return cls(ok=True, summary=summary, data=data, meta=meta)

    @classmethod
    def failure(cls, error: str, **meta: Any) -> ToolResult:
        return cls(ok=False, summary=error, error=error, meta=meta)


class ToolContext(BaseModel):
    """Everything a tool is allowed to know about the run."""

    model_config = {"arbitrary_types_allowed": True}

    organization_id: str
    buttlr_id: str | None = None
    execution_id: str | None = None
    user_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, dict[str, Any]] = Field(default_factory=dict)
    dry_run: bool = False

    def credential(self, provider: str) -> dict[str, Any]:
        return self.credentials.get(provider, {})

    def scoped(self, key: str, default: Any = None) -> Any:
        return self.scope.get(key, default)


class Tool(ABC):
    """Base class for every capability a Buttlr can be granted."""

    name: ClassVar[str]
    description: ClassVar[str]
    integration: ClassVar[str | None] = None
    required_permission: ClassVar[Permission] = Permission.EXECUTE
    risk: ClassVar[RiskLevel] = RiskLevel.LOW
    read_only: ClassVar[bool] = False
    input_model: ClassVar[type[BaseModel]]

    @classmethod
    def parameters_schema(cls) -> dict[str, Any]:
        return cls.input_model.model_json_schema()

    @classmethod
    def action_label(cls) -> str:
        return cls.description.split(".")[0].strip()

    @abstractmethod
    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult: ...


class UnavailableTool(Tool):
    """Placeholder for a tool whose integration is not configured.

    It always fails closed with a clear message — it never pretends to work.
    """

    name = "unavailable"
    description = "Not available"
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW

    class Input(BaseModel):
        pass

    input_model = Input

    def __init__(self, name: str, reason: str, integration: str | None = None) -> None:
        self.name = name
        self.description = reason
        self.integration = integration

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        return ToolResult.failure(f"{self.name} is unavailable: {self.description}")
