"""When a configured model cannot answer, the run must degrade honestly.

The failure this pins: the model router walks its chain and lands on the deterministic
provider, whose reply is a placeholder. Returning that as the run's answer looks like success
while doing nothing. It must instead fall back to the planner that sequences tools, and say so.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from app.container import Container
from app.runtime.executor import ExecutionJob
from app.runtime.models.base import CompletionRequest, CompletionResponse
from app.runtime.permissions.engine import AccessContext
from app.runtime.planner.base import PlannerError, PlanRequest
from app.runtime.planner.llm import LLMPlanner
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.registry import ToolRegistry
from app.schemas.buttlr import ButtlrCreate, ModelConfig
from app.schemas.enums import (
    ButtlrStatus,
    ExecutionStatus,
    ExecutionTrigger,
    OrgRole,
    Permission,
    RiskLevel,
    StepType,
)
from app.schemas.organization import OrganizationCreate

PLACEHOLDER = (
    "heuristic: no language model is configured, so this response is a deterministic "
    "placeholder."
)
QUOTA = (
    "429 RESOURCE_EXHAUSTED: You exceeded your current quota, model gemini-3.8-flash"
)


class StubRouter:
    """A router whose chain ends at the deterministic provider, as a 429 quota does."""

    def __init__(self) -> None:
        self.last_failures = {"google": QUOTA}
        self.deployment = self

    async def available_providers(self) -> list[str]:
        return ["google", "heuristic"]

    async def complete(self, config: ModelConfig, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(content=PLACEHOLDER, provider="heuristic", model="heuristic")


class StubRegistry:
    def __init__(self, router: StubRouter) -> None:
        self._router = router
        self.deployment = router

    async def router(self, organization_id: str) -> StubRouter:
        return self._router


def stub_planner_request() -> PlanRequest:
    from app.runtime.models.base import ToolSpec

    return PlanRequest(
        goal="List the repositories.",
        system_prompt="You are a Buttlr.",
        tools=[ToolSpec(name="github.list_repositories", description="List repositories.")],
    )


async def test_the_planner_refuses_a_deterministic_placeholder() -> None:
    planner = LLMPlanner(StubRouter(), ModelConfig(provider="google"))  # type: ignore[arg-type]
    with pytest.raises(PlannerError):
        await planner.next(stub_planner_request())
    assert planner.last_error and "429" in planner.last_error, "the reason must be kept"


class RepoListTool(Tool):
    name = "github.list_repositories"
    description = "List repositories."
    integration = "github"
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        pass

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        return ToolResult.success(
            "Found 2 repositories in acme",
            data=[{"full_name": "acme/backend"}, {"full_name": "acme/web"}],
        )


async def test_a_run_degrades_to_the_built_in_planner_and_does_the_work(
    container: Container,
) -> None:
    tokens = await container.auth.dev_login("degrade@example.com", "Degrade")
    principal = await container.auth.principal_from_token(tokens.access_token)
    organization = await container.organizations.create(
        principal, OrganizationCreate(name="Degrade Corp")
    )
    principal = principal.model_copy(update={"organization_id": organization.id})

    registry = ToolRegistry([RepoListTool()])
    container.registry = registry
    container.executor.registry = registry
    container.buttlrs.registry = registry
    # Every model call lands on the deterministic provider.
    container.executor.models = StubRegistry(StubRouter())  # type: ignore[assignment]

    buttlr = await container.buttlrs.create(
        principal,
        organization.id,
        ButtlrCreate(
            name="Repo Watcher",
            tools=[RepoListTool.name],
            integrations=["github"],
            status=ButtlrStatus.ACTIVE,
            model=ModelConfig(provider="google"),
        ),
    )
    execution = await container.executions.create(
        organization.id,
        buttlr,
        ExecutionTrigger.MANUAL,
        "List the repositories.",
        requested_by=principal.user_id,
    )
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal="List the repositories.",
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=AccessContext(
                user_id=principal.user_id,
                org_role=OrgRole.OWNER,
                team_ids=(),
                settings=organization.settings,
            ),
        )
    )

    assert outcome.status == ExecutionStatus.COMPLETED
    notices: list[Any] = [
        step
        for step in outcome.steps
        if step.type == StepType.STATUS and "built-in planner" in step.title
    ]
    assert notices, "the run must say that a configured model did not answer"
    assert QUOTA.split(":")[0] in (notices[0].detail or ""), "and why"

    assert PLACEHOLDER.split(",")[0] not in (outcome.output or ""), (
        "a placeholder must never be reported as the run's answer"
    )
    assert "acme/backend" in (outcome.output or "") or "acme" in (outcome.output or ""), (
        "the fallback must actually use the tools"
    )
    assert any(step.tool == RepoListTool.name for step in outcome.steps)
