"""The offline planner is a real code path: the product must work with no model credentials.

These tests pin its contract — only offered tools, always terminates, and a rejected approval
is never retried.
"""

from __future__ import annotations

import pytest

from app.runtime.planner.base import Observation, PlanAction, PlanRequest
from app.runtime.planner.heuristic import HeuristicPlanner
from app.runtime.tools import build_registry

GOAL = (
    "Monitor our selected GitHub repositories every morning. Analyse new pull requests for "
    "bugs, security issues, missing tests and unresolved review comments. Summarise the "
    "important findings. If a critical issue is found, open a GitHub issue and ask the "
    "Engineering Lead for approval before creating it."
)

TOOLS = [
    "github.list_repositories",
    "github.list_pull_requests",
    "github.get_pull_request",
    "github.list_pull_request_files",
    "github.list_pull_request_comments",
    "github.list_issues",
    "github.create_issue",
]

SAMPLE_DATA: dict[str, object] = {
    "github.list_repositories": [{"full_name": "acme/backend"}, {"full_name": "acme/web"}],
    "github.list_pull_requests": [
        {"number": 182, "title": "Add payments webhook", "repository": "acme/backend"},
        {"number": 184, "title": "Fix login redirect", "repository": "acme/backend"},
    ],
    "github.get_pull_request": {"number": 182, "title": "Add payments webhook", "additions": 240},
    "github.list_pull_request_files": [{"filename": "payments/webhook.py", "additions": 210}],
    "github.list_pull_request_comments": [{"user": "reviewer", "body": "needs tests"}],
    "github.list_issues": [{"number": 490, "title": "Old duplicate"}],
    "github.create_issue": {"number": 501, "html_url": "https://github.com/acme/backend/issues/501"},
}


def request(observations: list[Observation], step: int = 0) -> PlanRequest:
    registry = build_registry()
    return PlanRequest(
        goal=GOAL,
        system_prompt="You are PR Guardian, a Buttlr in the Engineering team.",
        tools=registry.specs(TOOLS),
        observations=observations,
        step_index=step,
        max_steps=12,
        scope={"repositories": ["acme/backend"]},
    )


async def test_heuristic_planner_only_offers_allowed_tools_and_terminates() -> None:
    planner = HeuristicPlanner()
    observations: list[Observation] = []
    planned: list[str] = []

    for step in range(20):
        plan = await planner.next(request(observations, step))
        if plan.action == PlanAction.FINAL:
            assert plan.final, "the run must end with a written summary"
            break
        assert plan.tool in TOOLS, f"planned an unavailable tool: {plan.tool}"
        assert isinstance(plan.arguments, dict)
        planned.append(plan.tool or "")
        observations.append(
            Observation(
                tool=plan.tool or "",
                arguments=plan.arguments,
                ok=True,
                summary=f"{plan.tool} returned data",
                data=SAMPLE_DATA.get(plan.tool or ""),
            )
        )
    else:  # pragma: no cover
        pytest.fail("the planner never finished")

    assert "github.list_pull_requests" in planned
    assert "github.create_issue" in planned, "the approval-gated action must be planned"


async def test_the_final_summary_uses_real_observations() -> None:
    planner = HeuristicPlanner()
    observations = [
        Observation(
            tool="github.list_pull_requests",
            arguments={},
            ok=True,
            summary="Found 2 open pull requests in acme/backend",
            data=SAMPLE_DATA["github.list_pull_requests"],
        )
    ]
    for step in range(20):
        plan = await planner.next(request(observations, step))
        if plan.action == PlanAction.FINAL:
            text = plan.final.lower()
            assert "182" in plan.final or "184" in plan.final or "pull request" in text
            return
        observations.append(
            Observation(
                tool=plan.tool or "",
                arguments=plan.arguments,
                ok=True,
                summary="ok",
                data=SAMPLE_DATA.get(plan.tool or ""),
            )
        )
    pytest.fail("the planner never produced a final answer")


async def test_a_rejected_action_is_not_retried() -> None:
    planner = HeuristicPlanner()
    observations: list[Observation] = [
        Observation(
            tool="github.create_issue",
            arguments={"title": "Critical: webhook signature not verified"},
            ok=False,
            summary="Rejected by a human reviewer: duplicate of #490",
            approved=False,
        )
    ]
    planned: list[str] = []
    for step in range(20):
        plan = await planner.next(request(observations, step))
        if plan.action == PlanAction.FINAL:
            assert "reject" in plan.final.lower() or "approval" in plan.final.lower()
            break
        planned.append(plan.tool or "")
        observations.append(
            Observation(tool=plan.tool or "", arguments=plan.arguments, ok=True, summary="ok")
        )
    else:  # pragma: no cover
        pytest.fail("the planner never finished")
    assert "github.create_issue" not in planned[1:]


async def test_no_tools_finishes_immediately_with_an_explanation() -> None:
    planner = HeuristicPlanner()
    plan = await planner.next(
        PlanRequest(goal=GOAL, system_prompt="You are a Buttlr.", tools=[], observations=[])
    )
    assert plan.action == PlanAction.FINAL
    assert plan.final
