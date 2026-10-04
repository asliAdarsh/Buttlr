"""The runtime loop: permissions, approval pause and resume — with a scripted planner.

The planner is swapped for a deterministic script so the test exercises the executor,
permission engine, approval service and store, not the heuristics.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.container import Container
from app.runtime.executor import ExecutionJob, ResumeJob
from app.runtime.permissions.engine import AccessContext
from app.runtime.planner.base import Plan, Planner
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.registry import ToolRegistry
from app.schemas.buttlr import ApprovalPolicy, ApprovalRule, ButtlrCreate
from app.schemas.enums import (
    ApprovalMode,
    ApprovalStatus,
    ButtlrStatus,
    ExecutionStatus,
    ExecutionTrigger,
    OrgRole,
    Permission,
    RiskLevel,
    StepStatus,
)
from app.schemas.organization import OrganizationCreate

GOAL = "Echo a status message."


class EchoTool(Tool):
    name = "demo.echo"
    description = "Echo a message back to the caller."
    integration = "demo"
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = False

    class Input(BaseModel):
        message: str = Field(description="Text to echo")

    input_model = Input

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        message = params.message
        if ctx.dry_run:
            return ToolResult.failure("Dry run: demo.echo was not executed.")
        self.calls.append(message)
        return ToolResult.success(f"echoed: {message}", data={"message": message})


class ScriptedPlanner(Planner):
    id = "scripted"

    def __init__(self, plans: list[Plan]) -> None:
        self._plans = list(plans)
        self.requests: list[Any] = []

    async def next(self, request):  # type: ignore[override]
        self.requests.append(request)
        if self._plans:
            return self._plans.pop(0)
        return Plan.finish("Nothing left to do.")


async def build_world(
    container: Container,
    tool: EchoTool,
    *,
    policy: ApprovalPolicy | None = None,
    role: OrgRole = OrgRole.OWNER,
):
    registry = ToolRegistry([tool])
    container.registry = registry
    container.executor.registry = registry
    container.buttlrs.registry = registry

    tokens = await container.auth.dev_login("runtime@example.com", "Runtime Owner")
    principal = await container.auth.principal_from_token(tokens.access_token)
    organization = await container.organizations.create(
        principal, OrganizationCreate(name="Runtime Corp")
    )
    membership = await container.organizations.require_membership(
        organization.id, principal.user_id
    )
    access = AccessContext(
        user_id=principal.user_id,
        org_role=role,
        team_ids=tuple(membership.team_ids),
        settings=organization.settings,
    )
    buttlr = await container.buttlrs.create(
        principal,
        organization.id,
        ButtlrCreate(
            name="Echo Buttlr",
            role="Test assistant",
            tools=[EchoTool.name],
            status=ButtlrStatus.ACTIVE,
            approval_policy=policy,
            permissions=[],
        ),
    )
    return principal, organization, access, buttlr


def scripted(container: Container, plans: list[Plan]) -> ScriptedPlanner:
    planner = ScriptedPlanner(plans)
    container.executor._select_planner = (  # type: ignore[assignment]
        lambda _organization_id, _buttlr, p=planner: _resolved(p)
    )
    return planner


async def _resolved(planner: Planner) -> Planner:
    return planner


async def test_ask_policy_pauses_the_run_then_resumes_after_approval(container: Container) -> None:
    tool = EchoTool()
    policy = ApprovalPolicy(
        default_mode=ApprovalMode.AUTO,
        rules=[ApprovalRule(tool=EchoTool.name, mode=ApprovalMode.ASK)],
    )
    principal, organization, access, buttlr = await build_world(container, tool, policy=policy)
    scripted(
        container,
        [
            Plan.call(EchoTool.name, {"message": "hello"}, thought="Echo once."),
            Plan.finish("Echoed the message."),
        ],
    )

    execution = await container.executions.create(
        organization.id,
        buttlr,
        ExecutionTrigger.MANUAL,
        GOAL,
        requested_by=principal.user_id,
    )
    paused = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=access,
        )
    )

    assert paused.status == ExecutionStatus.WAITING_APPROVAL
    assert paused.pending_approval_id
    assert tool.calls == [], "the tool must not run before approval"

    pending = await container.approvals.list(organization.id, status=ApprovalStatus.PENDING)
    assert pending.total == 1
    approval = pending.items[0]
    assert approval.tool == EchoTool.name
    assert approval.params == {"message": "hello"}
    assert approval.risk == RiskLevel.LOW

    decided = await container.approvals.decide(
        principal, organization.id, approval.id, True, "Looks good"
    )
    assert decided.status == ApprovalStatus.APPROVED

    fresh = await container.executions.get(organization.id, paused.id)
    final = await container.executor.resume(
        ResumeJob(
            organization=organization,
            buttlr=buttlr,
            execution=fresh,
            approval=decided,
            granted=True,
            access=access,
        )
    )

    assert final.status == ExecutionStatus.COMPLETED
    assert tool.calls == ["hello"]
    assert final.output and "Echoed the message." in final.output
    actions = {row.action for row in (await container.audit.list(organization.id)).items}
    assert {"approval.granted", "tool.executed", "execution.completed"} <= actions

    stats_buttlr = await container.buttlrs.get(organization.id, buttlr.id)
    assert stats_buttlr.stats.total_runs == 1
    assert stats_buttlr.stats.successful_runs == 1


async def test_a_rejected_approval_does_not_execute_the_tool(container: Container) -> None:
    tool = EchoTool()
    policy = ApprovalPolicy(rules=[ApprovalRule(tool=EchoTool.name, mode=ApprovalMode.ASK)])
    principal, organization, access, buttlr = await build_world(container, tool, policy=policy)
    scripted(
        container,
        [Plan.call(EchoTool.name, {"message": "nope"}), Plan.finish("Skipped the action.")],
    )
    execution = await container.executions.create(
        organization.id, buttlr, ExecutionTrigger.MANUAL, GOAL, requested_by=principal.user_id
    )
    paused = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=access,
        )
    )
    approval = (await container.approvals.list(organization.id, status=ApprovalStatus.PENDING)).items[0]
    decided = await container.approvals.decide(
        principal, organization.id, approval.id, False, "Not now"
    )
    fresh = await container.executions.get(organization.id, paused.id)
    final = await container.executor.resume(
        ResumeJob(
            organization=organization,
            buttlr=buttlr,
            execution=fresh,
            approval=decided,
            granted=False,
            access=access,
        )
    )
    assert final.status == ExecutionStatus.COMPLETED
    assert tool.calls == []
    rejected = [step for step in final.steps if step.type.value == "approval_result"]
    assert rejected and rejected[0].status == StepStatus.FAILED
    assert final.output and "Skipped" in final.output


async def test_a_deny_policy_blocks_the_tool_and_records_it(container: Container) -> None:
    tool = EchoTool()
    policy = ApprovalPolicy(rules=[ApprovalRule(tool=EchoTool.name, mode=ApprovalMode.DENY)])
    principal, organization, access, buttlr = await build_world(container, tool, policy=policy)
    scripted(
        container,
        [Plan.call(EchoTool.name, {"message": "blocked"}), Plan.finish("Gave up.")],
    )
    execution = await container.executions.create(
        organization.id, buttlr, ExecutionTrigger.MANUAL, GOAL, requested_by=principal.user_id
    )
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=access,
        )
    )
    assert outcome.status == ExecutionStatus.COMPLETED
    assert tool.calls == []
    blocked = [step for step in outcome.steps if step.status == StepStatus.BLOCKED]
    assert blocked and blocked[0].tool == EchoTool.name
    actions = {row.action for row in (await container.audit.list(organization.id)).items}
    assert "tool.denied" in actions


async def test_a_member_without_grants_cannot_drive_the_buttlr(container: Container) -> None:
    tool = EchoTool()
    principal, organization, _, buttlr = await build_world(container, tool)
    scripted(container, [Plan.call(EchoTool.name, {"message": "x"}), Plan.finish("stopped")])

    member_access = AccessContext(user_id="someone-else", org_role=OrgRole.MEMBER, team_ids=())
    execution = await container.executions.create(
        organization.id, buttlr, ExecutionTrigger.MANUAL, GOAL, requested_by=principal.user_id
    )
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=member_access,
        )
    )
    assert tool.calls == []
    assert any(step.status == StepStatus.BLOCKED for step in outcome.steps)


async def test_a_dry_run_never_pauses_for_approval_and_never_writes(container: Container) -> None:
    tool = EchoTool()
    policy = ApprovalPolicy(rules=[ApprovalRule(tool=EchoTool.name, mode=ApprovalMode.ASK)])
    principal, organization, access, buttlr = await build_world(container, tool, policy=policy)
    scripted(container, [Plan.call(EchoTool.name, {"message": "dry"}), Plan.finish("Done, dry.")])

    execution = await container.executions.create(
        organization.id,
        buttlr,
        ExecutionTrigger.TEST,
        GOAL,
        requested_by=principal.user_id,
        dry_run=True,
    )
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.TEST,
            requested_by=principal.user_id,
            access=access,
            dry_run=True,
        )
    )
    assert outcome.status == ExecutionStatus.COMPLETED
    assert tool.calls == []
    assert (await container.approvals.list(organization.id, status=ApprovalStatus.PENDING)).total == 0
    assert any(step.status == StepStatus.FAILED for step in outcome.steps)


async def test_cancelling_a_queued_run_stops_before_any_tool_call(container: Container) -> None:
    tool = EchoTool()
    principal, organization, access, buttlr = await build_world(container, tool)
    scripted(container, [Plan.call(EchoTool.name, {"message": "later"})])
    execution = await container.executions.create(
        organization.id, buttlr, ExecutionTrigger.MANUAL, GOAL, requested_by=principal.user_id
    )
    await container.executions.cancel(organization.id, execution.id)
    fresh = await container.executions.get(organization.id, execution.id)
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=buttlr,
            execution=fresh,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=access,
        )
    )
    assert tool.calls == []
    assert outcome.status in (ExecutionStatus.CANCELLED, ExecutionStatus.RUNNING)


async def test_execution_with_no_tools_fails_with_a_clear_message(container: Container) -> None:
    tool = EchoTool()
    principal, organization, access, _ = await build_world(container, tool)
    toolless = await container.buttlrs.create(
        principal,
        organization.id,
        ButtlrCreate(name="Do Nothing", role="Test assistant", tools=[], status=ButtlrStatus.ACTIVE),
    )
    scripted(container, [Plan.finish("unused")])
    execution = await container.executions.create(
        organization.id, toolless, ExecutionTrigger.MANUAL, GOAL, requested_by=principal.user_id
    )
    outcome = await container.executor.run(
        ExecutionJob(
            organization=organization,
            buttlr=toolless,
            execution=execution,
            goal=GOAL,
            trigger=ExecutionTrigger.MANUAL,
            requested_by=principal.user_id,
            access=access,
        )
    )
    assert outcome.status == ExecutionStatus.FAILED
    assert outcome.error and "no tools" in outcome.error.lower()
