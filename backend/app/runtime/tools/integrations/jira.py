"""Jira tools.

Four capabilities over `JiraClient`: search, create, update and comment. Project scope is
enforced from the JQL itself — a query naming a project outside the Buttlr's scope is
refused rather than silently rewritten.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.integrations.jira import JiraClient
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.integrations import (
    call,
    dry_run_refusal,
    first,
    not_connected,
    outside_scope,
    query_summary,
    scope_values,
    trim_text,
)
from app.schemas.enums import Permission, RiskLevel

PROVIDER = "jira"

_PROJECT_CLAUSE = re.compile(
    r"""project\s*(?:=|!=|in|~)\s*\(?\s*["']?([A-Za-z0-9_ ,*'-]+?)["']?\s*\)?\s*(?=$|\band\b|\border\b|$)""",
    re.IGNORECASE,
)


def _client(ctx: ToolContext) -> JiraClient | ToolResult:
    credentials = ctx.credentials.get(PROVIDER) or {}
    base_url = credentials.get("base_url")
    email = credentials.get("email")
    token = credentials.get("api_token") or credentials.get("token")
    if not (base_url and email and token):
        return not_connected(PROVIDER)
    return JiraClient(base_url, email, token)


def _projects_in_scope(ctx: ToolContext) -> list[str]:
    return [value.upper() for value in scope_values(ctx, PROVIDER, "projects")]


def _issue_view(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    issue_type = fields.get("issuetype") or {}
    status = fields.get("status") or {}
    project = fields.get("project") or {}
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": status.get("name"),
        "issue_type": issue_type.get("name"),
        "project": project.get("key"),
        "priority": (fields.get("priority") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "reporter": (fields.get("reporter") or {}).get("displayName"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "url": issue.get("self"),
    }


def _comment_view(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "author": (comment.get("author") or {}).get("displayName"),
        "body": trim_text(comment.get("body"), 800),
        "created": comment.get("created"),
    }


def _key_project(key: str) -> str:
    return key.split("-", 1)[0].upper() if "-" in key else key.upper()


def _check_key_scope(ctx: ToolContext, key: str) -> ToolResult | None:
    allowed = _projects_in_scope(ctx)
    if allowed and _key_project(key) not in allowed:
        return outside_scope("Jira projects", key, allowed)
    return None


def _jql_projects(jql: str) -> list[str]:
    found: list[str] = []
    for match in _PROJECT_CLAUSE.finditer(jql):
        for part in match.group(1).split(","):
            value = part.strip().strip("\"'").upper()
            if value:
                found.append(value)
    return found


class SearchIssues(Tool):
    name = "jira.search_issues"
    description = (
        "Search Jira issues with a JQL query and return their key, summary, status, type "
        "and assignee."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        jql: str = Field(
            description="JQL query, for example 'project = ENG AND status = Open'.",
        )
        max_results: int = Field(
            default=25, ge=1, le=100, description="Maximum number of issues to return."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        jql = str(args["jql"] or "").strip()
        if not jql:
            return ToolResult.failure("A JQL query is required to search Jira issues.")
        allowed = _projects_in_scope(ctx)
        if allowed:
            named = _jql_projects(jql)
            outside = [project for project in named if project not in allowed]
            if outside:
                return outside_scope("Jira projects", ", ".join(outside), allowed)
            if not named:
                clause = ", ".join(f'"{project}"' for project in allowed)
                jql = f"({jql}) AND project IN ({clause})"
        try:
            issues, failure = await call(
                client.search_issues(jql, max_results=max(1, min(int(args.get("max_results", 25)), 100))),
                action="jira.search_issues",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [_issue_view(issue) for issue in issues or []]
        if allowed:
            views = [view for view in views if not view["project"] or view["project"].upper() in allowed]
        return ToolResult.success(
            query_summary(len(views), "issue", jql),
            data={"issues": views, "jql": jql},
            jql=jql,
            count=len(views),
        )


class CreateIssue(Tool):
    name = "jira.create_issue"
    description = (
        "Create a Jira issue. The project defaults to the only project in scope when the "
        "Buttlr is limited to one."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.HIGH
    read_only = False

    class Input(BaseModel):
        project: str | None = Field(
            default=None,
            description="Jira project key, for example 'ENG'. Omit when only one project is in scope.",
        )
        summary: str = Field(description="Issue summary, one sentence.")
        description: str = Field(default="", description="Issue description.")
        issue_type: str = Field(
            default="Task", description="Jira issue type name, for example Task or Bug."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        project: str | None = args.get("project")
        allowed = _projects_in_scope(ctx)
        try:
            if project:
                denial = (
                    outside_scope("Jira projects", project, allowed)
                    if allowed and project.upper() not in allowed
                    else None
                )
                if denial is not None:
                    return denial
            else:
                project = first(allowed)
                if not project:
                    projects, failure = await call(
                        client.list_projects(), action="jira.list_projects"
                    )
                    if failure is not None:
                        return failure
                    project = next(
                        (
                            str(item.get("key"))
                            for item in projects or []
                            if item.get("key")
                        ),
                        "",
                    )
                    if not project:
                        return ToolResult.failure(
                            "No Jira projects are available to this account."
                        )
            issue, failure = await call(
                client.create_issue(
                    project_key=project,
                    summary=args["summary"],
                    description=args.get("description") or "",
                    issue_type=args.get("issue_type") or "Task",
                ),
                action=f"jira.create_issue[{project}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        # Jira returns only the created key, so the summary is filled in from the request.
        key = (issue or {}).get("key") or ""
        data = _issue_view(issue or {})
        data["key"] = key
        data["summary"] = args["summary"]
        data["project"] = project
        data["issue_type"] = args.get("issue_type") or "Task"
        return ToolResult.success(
            f"Created Jira issue {key} “{data['summary']}” in project {project}.",
            data=data,
            key=key,
            project=project,
        )


class UpdateIssue(Tool):
    name = "jira.update_issue"
    description = "Change the summary or description of an existing Jira issue."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.MEDIUM
    read_only = False

    class Input(BaseModel):
        key: str = Field(description="Jira issue key, for example 'ENG-142'.")
        summary: str | None = Field(default=None, description="New summary, if changing it.")
        description: str | None = Field(
            default=None, description="New description, if changing it."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        key = str(args["key"]).strip().upper()
        fields: dict[str, Any] = {}
        if args.get("summary"):
            fields["summary"] = args["summary"]
        if args.get("description"):
            fields["description"] = args["description"]
        if not fields:
            return ToolResult.failure(
                f"Nothing to change on {key}: provide a new summary or description."
            )
        try:
            denial = _check_key_scope(ctx, key)
            if denial is not None:
                return denial
            issue, failure = await call(
                client.update_issue(key, fields),
                action=f"jira.update_issue[{key}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        # A Jira update returns no body, so the change is described from what was sent.
        data = _issue_view(issue or {})
        data["key"] = key
        if args.get("summary"):
            data["summary"] = args["summary"]
        data["changed_fields"] = sorted(fields)
        return ToolResult.success(
            f"Updated Jira issue {key} ({', '.join(sorted(fields))}).",
            data=data,
            key=key,
            changed_fields=sorted(fields),
        )


class AddComment(Tool):
    name = "jira.add_comment"
    description = "Add a comment to an existing Jira issue."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.MEDIUM
    read_only = False

    class Input(BaseModel):
        key: str = Field(description="Jira issue key, for example 'ENG-142'.")
        body: str = Field(description="Comment text.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        key = str(args["key"]).strip().upper()
        try:
            denial = _check_key_scope(ctx, key)
            if denial is not None:
                return denial
            comment, failure = await call(
                client.add_comment(key, args["body"]),
                action=f"jira.add_comment[{key}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        data = _comment_view(comment or {})
        data["key"] = key
        return ToolResult.success(f"Commented on Jira issue {key}.", data=data, key=key)


__all__ = ["AddComment", "CreateIssue", "SearchIssues", "UpdateIssue"]
