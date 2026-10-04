"""Runtime tools.

`build_registry` is the single place every capability is registered; the container, the
planner and the API all read tools through the registry rather than importing tool modules.
"""

from __future__ import annotations

from app.runtime.tools.base import Tool, ToolContext, ToolResult, UnavailableTool
from app.runtime.tools.integrations.github import (
    AddComment as GitHubAddComment,
)
from app.runtime.tools.integrations.github import (
    CreateIssue as GitHubCreateIssue,
)
from app.runtime.tools.integrations.github import (
    GetPullRequest,
    ListIssues,
    ListPullRequestComments,
    ListPullRequestFiles,
    ListPullRequests,
    ListRepositories,
)
from app.runtime.tools.integrations.google import (
    CreateEvent,
    GetDocument,
    GetFile,
    GetMessage,
    ListEvents,
    ReadRange,
    SearchFiles,
    SearchMessages,
    SendMessage,
    WriteRange,
)
from app.runtime.tools.integrations.jira import (
    AddComment as JiraAddComment,
)
from app.runtime.tools.integrations.jira import (
    CreateIssue as JiraCreateIssue,
)
from app.runtime.tools.integrations.jira import (
    SearchIssues,
    UpdateIssue,
)
from app.runtime.tools.registry import ToolRegistry, registry

__all__ = [
    "TOOLS",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "UnavailableTool",
    "build_registry",
    "registry",
]


def _tools() -> tuple[type[Tool], ...]:
    return (
        # GitHub
        ListRepositories,
        ListPullRequests,
        GetPullRequest,
        ListPullRequestFiles,
        ListPullRequestComments,
        ListIssues,
        GitHubCreateIssue,
        GitHubAddComment,
        # Jira
        SearchIssues,
        JiraCreateIssue,
        UpdateIssue,
        JiraAddComment,
        # Gmail
        SearchMessages,
        GetMessage,
        SendMessage,
        # Drive
        SearchFiles,
        GetFile,
        # Sheets
        ReadRange,
        WriteRange,
        # Calendar
        ListEvents,
        CreateEvent,
        # Docs
        GetDocument,
    )


TOOLS: tuple[type[Tool], ...] = _tools()


def build_registry() -> ToolRegistry:
    """A fresh registry holding every tool this runtime can execute."""
    return ToolRegistry(tool() for tool in TOOLS)
