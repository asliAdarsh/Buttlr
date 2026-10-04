"""Planner contract.

The planner is the Buttlr's decision loop: given the goal, its own configuration, the tools
it is allowed to use and everything observed so far, decide the single next action.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.runtime.models.base import ToolSpec
from app.schemas.execution import Usage


class PlanAction(str, Enum):
    TOOL = "tool"
    FINAL = "final"


class Observation(BaseModel):
    """A completed step, as the planner sees it."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    summary: str = ""
    data: Any = None
    approved: bool | None = None


class PlanRequest(BaseModel):
    goal: str
    system_prompt: str
    tools: list[ToolSpec] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    step_index: int = 0
    max_steps: int = 12
    scope: dict[str, Any] = Field(default_factory=dict)


class Plan(BaseModel):
    action: PlanAction
    thought: str = ""
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    final: str = ""
    usage: Usage = Field(default_factory=Usage)
    provider: str = ""
    model: str = ""

    @classmethod
    def finish(cls, final: str, thought: str = "", **kw: Any) -> Plan:
        return cls(action=PlanAction.FINAL, final=final, thought=thought, **kw)

    @classmethod
    def call(cls, tool: str, arguments: dict[str, Any], thought: str = "", **kw: Any) -> Plan:
        return cls(action=PlanAction.TOOL, tool=tool, arguments=arguments, thought=thought, **kw)


class Planner(ABC):
    id: str = "base"

    @abstractmethod
    async def next(self, request: PlanRequest) -> Plan: ...


class PlannerError(Exception):
    """Raised when a plan cannot be produced; the executor degrades gracefully."""
