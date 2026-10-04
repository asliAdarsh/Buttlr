"""GitHub tools.

Eight read/write capabilities over one `GitHubClient`. Credentials come from the run
context, never from the process environment, and every read is filtered by the scope the
Buttlr was configured with.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.integrations.github import GitHubClient
from app.runtime.tools.base import Tool, ToolContext, ToolResult
from app.runtime.tools.integrations import (
    REPO_FANOUT_LIMIT,
    call,
    dry_run_refusal,
    list_summary,
    matches_repository,
    not_connected,
    outside_scope,
    page_limit,
    scope_values,
    trim_patch,
    trim_text,
)
from app.schemas.enums import Permission, RiskLevel

PROVIDER = "github"


def _client(ctx: ToolContext) -> GitHubClient | ToolResult:
    credentials = ctx.credentials.get(PROVIDER) or {}
    token = credentials.get("token")
    if not token:
        return not_connected(PROVIDER)
    base_url = credentials.get("base_url") or "https://api.github.com"
    return GitHubClient(token, base_url=base_url)


def _repos_in_scope(ctx: ToolContext, repository: str) -> ToolResult | None:
    allowed = scope_values(ctx, PROVIDER, "repositories")
    if allowed and not matches_repository(allowed, repository):
        return outside_scope("repositories", repository, allowed)
    return None


def _pr_view(pr: dict[str, Any]) -> dict[str, Any]:
    user = pr.get("user") or {}
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": pr.get("draft"),
        "author": user.get("login"),
        "branch": (pr.get("head") or {}).get("ref"),
        "base": (pr.get("base") or {}).get("ref"),
        "url": pr.get("html_url"),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "body": trim_text(pr.get("body")),
    }


def _issue_view(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "author": (issue.get("user") or {}).get("login"),
        "labels": [label.get("name") for label in (issue.get("labels") or []) if label],
        "comments": issue.get("comments"),
        "url": issue.get("html_url"),
        "created_at": issue.get("created_at"),
        "body": trim_text(issue.get("body")),
    }


def _comment_view(comment: dict[str, Any]) -> dict[str, Any]:
    return {
        "author": (comment.get("user") or {}).get("login"),
        "body": trim_text(comment.get("body"), 800),
        "created_at": comment.get("created_at"),
        "url": comment.get("html_url"),
    }


class ListRepositories(Tool):
    name = "github.list_repositories"
    description = (
        "List the GitHub repositories the connected account can reach, with their default "
        "branch, language and last update time."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        limit: int = Field(default=30, ge=1, le=100, description="How many repositories to return.")
        sort: str = Field(
            default="updated",
            description="Sort order accepted by GitHub: updated, created, pushed or full_name.",
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        try:
            repositories, failure = await call(
                client.list_repositories(
                    per_page=page_limit(args.get("limit", 30), 100),
                    page=1,
                    sort=args.get("sort") or "updated",
                ),
                action="github.list_repositories",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [
            {
                "full_name": repo.get("full_name"),
                "description": trim_text(repo.get("description"), 300),
                "language": repo.get("language"),
                "default_branch": repo.get("default_branch"),
                "private": repo.get("private"),
                "stars": (repo.get("stargazers_count") if isinstance(repo.get("stargazers_count"), int) else None),
                "open_issues": repo.get("open_issues_count"),
                "updated_at": repo.get("updated_at"),
                "url": repo.get("html_url"),
            }
            for repo in repositories or []
        ]
        return ToolResult.success(
            list_summary(len(views), "repository", ""),
            data={"repositories": views},
            repository_count=len(views),
        )


class ListPullRequests(Tool):
    name = "github.list_pull_requests"
    description = (
        "List pull requests for one repository. When no repository is given, every "
        "repository in scope is searched and the results are combined."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        repository: str | None = Field(
            default=None,
            description="Repository as 'owner/name'. Omit to search every repository in scope.",
        )
        state: str = Field(
            default="open",
            description="Pull request state: open, closed or all.",
        )
        limit: int = Field(default=20, ge=1, le=50, description="Maximum results to return.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository: str | None = args.get("repository")
        state = args.get("state") or "open"
        limit = page_limit(args.get("limit", 20), 50)
        allowed = scope_values(ctx, PROVIDER, "repositories")
        try:
            if repository:
                denial = _repos_in_scope(ctx, repository)
                if denial is not None:
                    return denial
                targets = [repository]
            elif allowed:
                targets = allowed[:REPO_FANOUT_LIMIT]
            else:
                repositories, failure = await call(
                    client.list_repositories(per_page=REPO_FANOUT_LIMIT, page=1),
                    action="github.list_repositories",
                )
                if failure is not None:
                    return failure
                targets = [
                    repo.get("full_name")
                    for repo in repositories or []
                    if repo.get("full_name")
                ][:REPO_FANOUT_LIMIT]
                if not targets:
                    return ToolResult.failure(
                        "No GitHub repositories are available to this account."
                    )

            collected: list[dict[str, Any]] = []
            errors: list[str] = []
            for target in targets:
                pulls, failure = await call(
                    client.list_pull_requests(
                        target, state=state, per_page=limit, sort="updated"
                    ),
                    action=f"github.list_pull_requests[{target}]",
                )
                if failure is not None:
                    errors.append(failure.error or failure.summary)
                    continue
                for pull in (pulls or [])[:limit]:
                    view = _pr_view(pull)
                    view["repository"] = target
                    collected.append(view)
            if not collected and errors:
                return ToolResult.failure(errors[0])
        finally:
            await client.close()

        collected.sort(key=lambda item: (item.get("updated_at") or ""), reverse=True)
        collected = collected[:limit]
        where = repository or ", ".join(targets[:3])
        noun = "open pull request" if state == "open" else f"{state} pull request"
        return ToolResult.success(
            list_summary(len(collected), noun, where),
            data={"pull_requests": collected, "state": state, "repositories": targets},
            count=len(collected),
            repositories=targets,
        )


class GetPullRequest(Tool):
    name = "github.get_pull_request"
    description = (
        "Get one pull request in full: title, description, author, branches, review state "
        "and the commits it contains."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        repository: str = Field(description="Repository as 'owner/name'.")
        number: int = Field(description="Pull request number.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository = args["repository"]
        number = int(args["number"])
        try:
            denial = _repos_in_scope(ctx, repository)
            if denial is not None:
                return denial
            pull, failure = await call(
                client.get_pull_request(repository, number),
                action=f"github.get_pull_request[{repository}#{number}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure
        if not pull:
            return ToolResult.failure(
                f"Pull request {repository}#{number} was not found."
            )

        data = _pr_view(pull)
        data["repository"] = repository
        data["merged"] = pull.get("merged")
        data["mergeable_state"] = pull.get("mergeable_state")
        data["additions"] = pull.get("additions")
        data["deletions"] = pull.get("deletions")
        data["changed_files"] = pull.get("changed_files")
        data["commits"] = pull.get("commits")
        data["review_comments"] = pull.get("review_comments")
        state = "merged" if pull.get("merged") else (pull.get("state") or "unknown")
        return ToolResult.success(
            f"Pull request {repository}#{number} “{pull.get('title')}” is {state}.",
            data=data,
            repository=repository,

        )




class ListPullRequestFiles(Tool):
    name = "github.list_pull_request_files"
    description = (
        "List the files changed by a pull request with additions, deletions and the first "
        "lines of each patch."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        repository: str = Field(description="Repository as 'owner/name'.")
        number: int = Field(description="Pull request number.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository = args["repository"]
        number = int(args["number"])
        try:
            denial = _repos_in_scope(ctx, repository)
            if denial is not None:
                return denial
            files, failure = await call(
                client.list_pull_request_files(repository, number),
                action=f"github.list_pull_request_files[{repository}#{number}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [
            {
                "filename": item.get("filename"),
                "status": item.get("status"),
                "additions": item.get("additions"),
                "deletions": item.get("deletions"),
                "changes": item.get("changes"),
                "patch": trim_patch(item.get("patch")),
            }
            for item in files or []
        ]
        return ToolResult.success(
            list_summary(len(views), "changed file", f"{repository}#{number}"),
            data={"files": views, "repository": repository, "number": number},
            repository=repository,
            number=number,
            count=len(views),
        )


class ListPullRequestComments(Tool):
    name = "github.list_pull_request_comments"
    description = "List the review comments left on a pull request, oldest first."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        repository: str = Field(description="Repository as 'owner/name'.")
        number: int = Field(description="Pull request or issue number.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository = args["repository"]
        number = int(args["number"])
        try:
            denial = _repos_in_scope(ctx, repository)
            if denial is not None:
                return denial
            comments, failure = await call(
                client.list_pull_request_comments(repository, number),
                action=f"github.list_pull_request_comments[{repository}#{number}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        views = [_comment_view(comment) for comment in comments or []]
        return ToolResult.success(
            list_summary(len(views), "comment", f"{repository}#{number}"),
            data={"comments": views, "repository": repository, "number": number},
            repository=repository,
            number=number,
            count=len(views),
        )


class ListIssues(Tool):
    name = "github.list_issues"
    description = (
        "List issues in a repository, optionally filtered by label. When no repository is "
        "given, every repository in scope is searched."
    )
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.LOW
    read_only = True

    class Input(BaseModel):
        repository: str | None = Field(
            default=None,
            description="Repository as 'owner/name'. Omit to search every repository in scope.",
        )
        state: str = Field(default="open", description="Issue state: open, closed or all.")
        labels: list[str] = Field(
            default_factory=list, description="Label names the issues must carry."
        )
        limit: int = Field(default=20, ge=1, le=50, description="Maximum results to return.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository: str | None = args.get("repository")
        state = args.get("state") or "open"
        limit = page_limit(args.get("limit", 20), 50)
        requested_labels = [str(label).strip() for label in (args.get("labels") or []) if str(label).strip()]
        allowed_labels = [label.lower() for label in scope_values(ctx, PROVIDER, "labels")]
        if requested_labels and allowed_labels:
            outside = [
                label for label in requested_labels if label.lower() not in allowed_labels
            ]
            if outside:
                return outside_scope("labels", ", ".join(outside), scope_values(ctx, PROVIDER, "labels"))
        effective_labels = requested_labels or (
            scope_values(ctx, PROVIDER, "labels") if allowed_labels else []
        )
        allowed = scope_values(ctx, PROVIDER, "repositories")
        try:
            if repository:
                denial = _repos_in_scope(ctx, repository)
                if denial is not None:
                    return denial
                targets = [repository]
            elif allowed:
                targets = allowed[:REPO_FANOUT_LIMIT]
            else:
                repositories, failure = await call(
                    client.list_repositories(per_page=REPO_FANOUT_LIMIT, page=1),
                    action="github.list_repositories",
                )
                if failure is not None:
                    return failure
                targets = [
                    repo.get("full_name")
                    for repo in repositories or []
                    if repo.get("full_name")
                ][:REPO_FANOUT_LIMIT]
                if not targets:
                    return ToolResult.failure(
                        "No GitHub repositories are available to this account."
                    )

            collected: list[dict[str, Any]] = []
            errors: list[str] = []
            for target in targets:
                issues, failure = await call(
                    client.list_issues(
                        target,
                        state=state,
                        labels=",".join(effective_labels) if effective_labels else None,
                        per_page=limit,
                    ),
                    action=f"github.list_issues[{target}]",
                )
                if failure is not None:
                    errors.append(failure.error or failure.summary)
                    continue
                for issue in issues or []:
                    if issue.get("pull_request"):
                        continue
                    view = _issue_view(issue)
                    view["repository"] = target
                    collected.append(view)
            if not collected and errors:
                return ToolResult.failure(errors[0])
        finally:
            await client.close()

        collected.sort(key=lambda item: (item.get("created_at") or ""), reverse=True)
        collected = collected[:limit]
        where = repository or ", ".join(targets[:3])
        noun = "open issue" if state == "open" else f"{state} issue"
        return ToolResult.success(
            list_summary(len(collected), noun, where),
            data={
                "issues": collected,
                "state": state,
                "labels": effective_labels,
                "repositories": targets,
            },
            count=len(collected),
            repositories=targets,
        )


class CreateIssue(Tool):
    name = "github.create_issue"
    description = "Create an issue in a repository with a title, description and optional labels."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.HIGH
    read_only = False

    class Input(BaseModel):
        repository: str = Field(description="Repository as 'owner/name'.")
        title: str = Field(description="Issue title.")
        body: str = Field(default="", description="Issue description in Markdown.")
        labels: list[str] = Field(
            default_factory=list, description="Label names to apply to the new issue."
        )

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository = args["repository"]
        labels = [str(label).strip() for label in (args.get("labels") or []) if str(label).strip()]
        allowed_labels = [label.lower() for label in scope_values(ctx, PROVIDER, "labels")]
        if labels and allowed_labels:
            outside = [label for label in labels if label.lower() not in allowed_labels]
            if outside:
                return outside_scope("labels", ", ".join(outside), scope_values(ctx, PROVIDER, "labels"))
        try:
            denial = _repos_in_scope(ctx, repository)
            if denial is not None:
                return denial
            issue, failure = await call(
                client.create_issue(
                    repository,
                    title=args["title"],
                    body=args.get("body") or "",
                    labels=labels or None,
                ),
                action=f"github.create_issue[{repository}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        data = _issue_view(issue or {})
        data["repository"] = repository
        return ToolResult.success(
            f"Created issue {repository}#{data['number']} “{data['title']}”.",
            data=data,
            repository=repository,
            number=data["number"],
            url=data.get("url"),
        )


class AddComment(Tool):
    name = "github.add_comment"
    description = "Add a comment to a pull request or issue in a repository."
    integration = PROVIDER
    required_permission = Permission.EXECUTE
    risk = RiskLevel.MEDIUM
    read_only = False

    class Input(BaseModel):
        repository: str = Field(description="Repository as 'owner/name'.")
        number: int = Field(description="Pull request or issue number.")
        body: str = Field(description="Comment text in Markdown.")

    input_model = Input

    async def run(self, ctx: ToolContext, params: BaseModel) -> ToolResult:
        if ctx.dry_run:
            return dry_run_refusal(self.name)
        client = _client(ctx)
        if isinstance(client, ToolResult):
            return client
        args: dict[str, Any] = params.model_dump()
        repository = args["repository"]
        number = int(args["number"])
        try:
            denial = _repos_in_scope(ctx, repository)
            if denial is not None:
                return denial
            comment, failure = await call(
                client.add_comment(repository, number, args["body"]),
                action=f"github.add_comment[{repository}#{number}]",
            )
        finally:
            await client.close()
        if failure is not None:
            return failure

        data = _comment_view(comment or {})
        data["repository"] = repository
        data["number"] = number
        return ToolResult.success(
            f"Commented on {repository}#{number}.",
            data=data,
            repository=repository,
            number=number,
            url=data.get("url"),
        )


__all__ = [
    "AddComment",
    "CreateIssue",
    "GetPullRequest",
    "ListIssues",
    "ListPullRequestComments",
    "ListPullRequestFiles",
    "ListPullRequests",
    "ListRepositories",
]


