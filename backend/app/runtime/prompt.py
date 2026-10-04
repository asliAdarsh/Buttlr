"""Prompt construction.

How a Buttlr is described to a model is a product decision, not an implementation detail:
it is what makes the Buttlr behave like a scoped employee rather than a chatbot with tools.
"""

from __future__ import annotations

import json
from typing import Any

from app.runtime.models.base import ToolSpec
from app.schemas.buttlr import Buttlr, ButtlrCreate
from app.schemas.enums import ApprovalMode, RiskLevel
from app.schemas.integration import canonical_providers

SCOPE_LABELS: dict[str, str] = {
    "repositories": "repositories",
    "labels": "labels",
    "folders": "folders",
    "projects": "Jira projects",
    "channels": "channels",
    "file_ids": "files",
    "spreadsheets": "spreadsheets",
    "calendars": "calendars",
    "query": "default search",
}

DRAFT_SYSTEM_PROMPT = """You are the Buttlr Builder. You turn a plain-English description of a \
job to be done into a complete, deployable AI employee configuration.

You must return a single JSON object with exactly these keys:
{
  "name": short employee-style name (2-4 words, e.g. "PR Guardian"),
  "avatar": a single emoji suitable for an avatar,
  "role": job title (e.g. "AI Pull Request Assistant"),
  "department": one of Engineering, Finance, HR, Marketing, Sales, Customer Support, Operations,
  "description": one sentence describing the job,
  "objective": what the Buttlr is trying to achieve, in the second person,
  "responsibilities": array of 3-6 concrete duties,
  "instructions": detailed operating instructions written in the second person,
  "tools": array of tool names chosen ONLY from the provided catalogue,
  "integrations": array of provider names required by those tools,
  "scope": object keyed by provider, holding only the restrictions implied by the request,
  "schedule": {"enabled": bool, "kind": one of manual,once,interval,hourly,daily,weekly,monthly,cron,
               "timezone": IANA timezone, "at": "HH:MM" or null, "day_of_week": "mon".."sun" or null,
               "day_of_month": int or null, "interval_minutes": int or null, "cron": string or null},
  "approval_policy": {"default_mode": "auto" or "ask", "rules": [{"tool": "tool.name", "mode": "auto"|"ask"|"deny", "approver_roles": []}], "require_for_risk": "low"|"medium"|"high"|"critical"},
  "rationale": one paragraph explaining the choices,
  "assumptions": array of assumptions you made,
  "missing": array of things the user still needs to decide
}

Rules:
- Prefer the smallest tool set that accomplishes the job.
- Any action that writes to an external system and is described as needing permission, or that
  is destructive, must have an approval rule with mode "ask".
- If the user states a time without a timezone, use the provided default timezone and record it
  in "assumptions".
- Never invent tool names. If no tool fits, leave it out and list the gap in "missing".
- Output JSON only. No prose, no markdown fences.
"""


def _format_tool_list(tools: list[ToolSpec]) -> str:
    lines = []
    for tool in tools:
        marker = " (read-only)" if "list" in tool.name or "get" in tool.name else ""
        lines.append(f"- {tool.name}{marker}: {tool.description.splitlines()[0]}")
    return "\n".join(lines) if lines else "- (none available)"


def build_draft_prompt(
    user_prompt: str,
    tools: list[ToolSpec],
    *,
    default_timezone: str = "UTC",
    teams: list[str] | None = None,
    organization_name: str | None = None,
) -> tuple[str, str]:
    context = [
        f"Default timezone: {default_timezone}",
        f"Organization: {organization_name or 'unknown'}",
    ]
    if teams:
        context.append("Available teams: " + ", ".join(teams))
    user = "\n".join(
        [
            *context,
            "",
            "Available tools:",
            _format_tool_list(tools),
            "",
            "User request:",
            user_prompt.strip(),
        ]
    )
    return DRAFT_SYSTEM_PROMPT, user


def render_scope(buttlr: Buttlr) -> str:
    if not buttlr.scope:
        return "No explicit scope was configured. Stay within what the tools return."
    lines: list[str] = []
    for provider, values in buttlr.scope.items():
        if not values:
            continue
        if isinstance(values, dict):
            rendered = ", ".join(
                f"{SCOPE_LABELS.get(k, k)}: {', '.join(map(str, v)) if isinstance(v, list) else v}"
                for k, v in values.items()
            )
        elif isinstance(values, list):
            rendered = ", ".join(map(str, values))
        else:
            rendered = str(values)
        lines.append(f"- {provider}: {rendered}")
    return "\n".join(lines) if lines else "No explicit scope was configured."


def _render_permissions(buttlr: Buttlr) -> str:
    if not buttlr.permissions:
        return "- Only organization owners and admins can operate this Buttlr."
    lines = []
    for grant in buttlr.permissions:
        subject = {
            "everyone": "Everyone in the organization",
            "role": f"Members with the '{grant.subject}' organization role",
            "team": f"Members of team '{grant.subject}'",
            "user": f"User '{grant.subject}'",
        }.get(grant.subject_type.value, grant.subject)
        lines.append(f"- {subject}: {grant.permission.value}")
    return "\n".join(lines)


def _render_approvals(buttlr: Buttlr) -> str:
    policy = buttlr.approval_policy
    lines = [
        f"- Default: {policy.default_mode.value}",
        f"- Always ask before risk level: {policy.require_for_risk.value}",
    ]
    for rule in policy.rules:
        roles = f" (approvers: {', '.join(rule.approver_roles)})" if rule.approver_roles else ""
        lines.append(f"- '{rule.tool}': {rule.mode.value}{roles}")
    return "\n".join(lines)


def build_system_prompt(
    buttlr: Buttlr,
    tools: list[ToolSpec],
    *,
    is_dry_run: bool = False,
) -> str:
    responsibilities = (
        "\n".join(f"- {item}" for item in buttlr.responsibilities) or "- (none specified)"
    )
    approvals = _render_approvals(buttlr)

    sections = [
        f"You are {buttlr.name}, a Buttlr working inside the organization's AI workforce.",
        f"Role: {buttlr.role}" + (f" | Department: {buttlr.department}" if buttlr.department else ""),
        "",
        f"Objective:\n{buttlr.objective or buttlr.description or 'Serve the user request accurately.'}",
        "",
        f"Responsibilities:\n{responsibilities}",
    ]

    if buttlr.instructions:
        sections += ["", f"Operating instructions:\n{buttlr.instructions}"]

    sections += [
        "",
        "Access scope — you may only work within this scope. If something outside it is needed,"
        " say so instead of acting:",
        render_scope(buttlr),
        "",
        "Available tools:",
        _format_tool_list(tools),
        "",
        "Approval policy (enforced by the platform, not by you):",
        approvals,
        "",
        "How to work:",
        "1. Call one tool at a time. Read the result before deciding the next step.",
        "2. Never claim you did something you did not actually do with a tool.",
        "3. If a tool returns an error, either try a different correct approach or explain the"
        " blocker. Never invent data to fill a gap.",
        "4. Keep the final answer concise and useful: lead with what matters, then the detail.",
        "5. When the objective is achieved, stop and report the outcome.",
    ]

    if is_dry_run:
        sections += [
            "",
            "This is a DRY RUN. Tools will not change anything. Say clearly that no changes were"
            " made.",
        ]

    if tools and all(_is_read_only(tool) for tool in tools):
        sections += [
            "",
            "Every tool available to you is read-only. You cannot change anything in this run.",
        ]

    return "\n".join(sections)


def _is_read_only(tool: ToolSpec) -> bool:
    read_prefixes = (
        "github.list_",
        "github.get_",
        "jira.search_",
        "gmail.search_",
        "gmail.get_",
        "drive.search_",
        "drive.get_",
        "sheets.read_",
    )
    return tool.name.startswith(read_prefixes)


def build_draft_from_plan(plan: dict[str, Any]) -> ButtlrCreate:
    """Coerce a model-produced plan into the validated create payload."""
    schedule = plan.get("schedule") or {}
    schedule.setdefault("enabled", False)
    schedule.setdefault("kind", "manual")
    policy = plan.get("approval_policy") or {}
    policy.setdefault("default_mode", ApprovalMode.AUTO.value)
    policy.setdefault("require_for_risk", RiskLevel.HIGH.value)
    tools = [str(t) for t in (plan.get("tools") or [])]
    payload = {
        "name": (plan.get("name") or "New Buttlr").strip()[:80],
        "avatar": plan.get("avatar") or "🤖",
        "role": plan.get("role") or "AI Assistant",
        "department": plan.get("department"),
        "description": plan.get("description") or "",
        "objective": plan.get("objective") or plan.get("description") or "",
        "responsibilities": [str(r) for r in (plan.get("responsibilities") or [])][:8],
        "instructions": plan.get("instructions") or "",
        "tools": tools,
        # Integrations are connection names, not tool prefixes: "gmail" becomes "google", so
        # the deploy gate and the credential lookup agree with the tool catalogue.
        "integrations": canonical_providers(tools, plan.get("integrations") or []),
        "scope": plan.get("scope") or {},
        "schedule": schedule,
        "approval_policy": policy,
        "permissions": plan.get("permissions") or [],
    }
    return ButtlrCreate.model_validate(payload)


def json_schema_hint(model: type) -> str:
    return json.dumps(model.model_json_schema(), indent=2)
