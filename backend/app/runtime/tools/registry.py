"""Tool registry.

Buttlrs discover capabilities here. Adding an integration means registering tools — nothing
in the planner, executor or API needs to change.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.runtime.models.base import ToolSpec
from app.runtime.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_many(self, tools: Iterable[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def replace(self, tools: Iterable[Tool]) -> None:
        for tool in tools:
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def names(self) -> list[str]:
        return [tool.name for tool in self.all()]

    def by_integration(self, provider: str | None) -> list[Tool]:
        return [tool for tool in self.all() if tool.integration == provider]

    def resolve(self, names: Iterable[str]) -> list[Tool]:
        resolved: list[Tool] = []
        for name in names:
            tool = self._tools.get(name)
            if tool is not None:
                resolved.append(tool)
        return resolved

    def specs(self, names: Iterable[str] | None = None) -> list[ToolSpec]:
        tools = self.all() if names is None else self.resolve(names)
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters_schema(),
            )
            for tool in tools
        ]

    def describe(self, name: str) -> dict[str, Any] | None:
        tool = self._tools.get(name)
        if tool is None:
            return None
        return {
            "name": tool.name,
            "description": tool.description,
            "integration": tool.integration,
            "required_permission": tool.required_permission.value,
            "risk": tool.risk.value,
            "read_only": tool.read_only,
            "parameters": tool.parameters_schema(),
        }

    def catalogue(self) -> list[dict[str, Any]]:
        return [self.describe(tool.name) or {} for tool in self.all()]


registry = ToolRegistry()
