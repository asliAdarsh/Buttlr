"""Deterministic planner.

This is the offline path: no model provider, no network, no randomness. It reads the goal,
the tools the Buttlr was granted and everything observed so far, and decides the single next
action. The same request always produces the same action, which is what makes the product
demonstrable without an LLM key.

Two rules shape everything here:

* never emit a tool that is not in ``PlanRequest.tools`` — the permission engine is the only
  thing that decides whether a tool may run, and the planner may not even name a tool the
  Buttlr was not granted;
* never invent a finding — the closing report is composed exclusively from observations.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.runtime.models.base import ToolSpec
from app.runtime.planner.base import Observation, Plan, Planner, PlanRequest
from app.schemas.common import utcnow

logger = get_logger(__name__)

__all__ = ["HeuristicPlanner"]

# --------------------------------------------------------------------------------------
# Goal vocabulary
# --------------------------------------------------------------------------------------

_INTENTS: dict[str, tuple[str, ...]] = {
    "pull_requests": ("pull request", "pull requests", "pr", "prs", "review", "merge", "diff"),
    "issues": ("issue", "issues", "bug", "bugs", "ticket", "tickets"),
    "jira_issues": ("jira", "jira ticket", "jira issue", "backlog", "sprint"),
    "email": ("email", "emails", "mail", "inbox", "message", "messages", "notification"),
    "files": ("file", "files", "document", "documents", "doc", "docs", "drive"),
    "sheets": ("sheet", "sheets", "spreadsheet", "spreadsheets", "table", "cell"),
    "calendar": ("calendar", "event", "events", "meeting", "meetings", "agenda"),
    "repositories": ("repository", "repositories", "repo", "repos"),
}

# Read-only chains, in the order a Buttlr should work through them.
_READ_CHAINS: dict[str, tuple[str, ...]] = {
    "repositories": ("github.list_repositories",),
    "pull_requests": (
        "github.list_pull_requests",
        "github.get_pull_request",
        "github.list_pull_request_files",
        "github.list_pull_request_comments",
    ),
    "issues": ("github.list_issues",),
    "jira_issues": ("jira.search_issues",),
    "email": ("gmail.search_messages", "gmail.get_message"),
    "files": ("drive.search_files", "drive.get_file"),
    "sheets": ("sheets.read_range",),
    "calendar": ("calendar.list_events",),
}

# Write tools are only planned when the goal explicitly asks for that action, matched as a
# verb near its object ("open a GitHub issue", "file a bug") rather than as a fixed phrase.
# The permission engine, not this planner, decides whether the action needs approval.
_WRITE_PATTERNS: dict[str, str] = {
    "github.create_issue": (
        r"\b(create|open|file|raise|log|report|track|start)(s|ed|ing)?\b\s+(up\s+)?"
        r"(a|an|the|new)\s+(github\s+)?(issue|bug|ticket)\b"
    ),
    "jira.create_issue": (
        r"\b(create|open|file|raise|log|report|track|start)(s|ed|ing)?\b\s+(up\s+)?"
        r"(a|an|the|new)\s+jira\s+(issue|ticket|bug)\b"
    ),
    "github.add_comment": (
        r"\b(comment|reply|note)(s|ed|ing)?\s+on\b"
        r"|\b(add|leave|post)\b\s+(a|an|the)?\s*comments?\b"
    ),
    "jira.add_comment": (
        r"\b(comment|reply|note)(s|ed|ing)?\s+on\b[^.]{0,20}?\bjira\b"
        r"|\b(add|leave|post)\b\s+(a|an|the)?\s*comments?\b[^.]{0,20}?\bjira\b"
    ),
    "jira.update_issue": (
        r"\b(update|move|transition|close|reopen|assign)(s|ed|ing)?\b\s+(the\s+)?"
        r"(issue|ticket)\b"
    ),
    "gmail.send_message": (
        r"\b(send|sending|sent|reply|forward|email)\b[^.]{0,25}?"
        r"\b(email|e-mail|mail|message|note)\b"
    ),
    "calendar.create_event": (
        r"\b(schedule|book|create|add|arrange)\b\s+(up\s+)?(a|an|the|new)\s+"
        r"(meeting|event|call|appointment)\b"
    ),
    "sheets.write_range": (
        r"\b(update|write|append|add|edit|fill in)\b\s+(up\s+)?(the|a|an)?\s*"
        r"(sheet|spreadsheet|rows?|cells?|table)\b"
    ),
}

_WRITE_COMPILED: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern) for name, pattern in _WRITE_PATTERNS.items()
}

# Words that are verbs when they introduce a write request. Inside such a phrase they must
# not also be read as a reason to go and gather data.
_WRITE_VERBS = frozenset(
    {
        "add",
        "append",
        "arrange",
        "assign",
        "book",
        "close",
        "comment",
        "create",
        "edit",
        "file",
        "fill",
        "forward",
        "leave",
        "log",
        "move",
        "note",
        "open",
        "post",
        "raise",
        "reopen",
        "reply",
        "report",
        "schedule",
        "send",
        "start",
        "track",
        "transition",
        "update",
        "write",
    }
)

# Chain each write tool follows, so the report it writes is grounded in a real read first.
_WRITE_PRECEDES: dict[str, str] = {
    "github.create_issue": "issues",
    "jira.create_issue": "jira_issues",
    "github.add_comment": "pull_requests",
    "gmail.send_message": "email",
    "jira.add_comment": "jira_issues",
    "jira.update_issue": "jira_issues",
    "sheets.write_range": "sheets",
}

# A goal that names Jira and no repository is a Jira question; GitHub issue tools would
# only add noise (and would fail as out of scope).
_GITHUB_ISSUE_TOOLS = frozenset({"github.list_issues", "github.create_issue"})

_READ_VERBS = ("list", "get", "search", "read")
_VERB_RANK = {"list": 0, "search": 1, "get": 2, "read": 3}

# Human labels used in the closing report. Only real observed data is ever rendered.
_FAMILY_LABEL: dict[str, tuple[str, str]] = {
    "github.list_repositories": ("repositories", "repository"),
    "github.list_pull_requests": ("pull requests", "pull request"),
    "github.get_pull_request": ("pull requests", "pull request"),
    "github.list_pull_request_files": ("changed files", "file"),
    "github.list_pull_request_comments": ("review comments", "comment"),
    "github.list_issues": ("issues", "issue"),
    "github.create_issue": ("issues", "issue"),
    "github.add_comment": ("comments", "comment"),
    "jira.search_issues": ("Jira issues", "Jira issue"),
    "jira.create_issue": ("Jira issues", "Jira issue"),
    "jira.update_issue": ("Jira issues", "Jira issue"),
    "jira.add_comment": ("Jira comments", "comment"),
    "gmail.search_messages": ("emails", "email"),
    "gmail.get_message": ("emails", "email"),
    "gmail.send_message": ("emails", "email"),
    "drive.search_files": ("files", "file"),
    "drive.get_file": ("files", "file"),
    "sheets.read_range": ("rows", "row"),
    "sheets.write_range": ("rows", "row"),
    "calendar.list_events": ("calendar events", "event"),
    "calendar.create_event": ("calendar events", "event"),
    "docs.get_document": ("documents", "document"),
}

# --------------------------------------------------------------------------------------
# Argument vocabulary
# --------------------------------------------------------------------------------------

# Semantic role -> the field names a tool may use for it. Only names the tool's own JSON
# schema declares are ever emitted.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "repository": ("repository", "repo", "repository_full_name", "full_name", "owner_repo"),
    "pull_request": ("number", "pull_number", "pr_number", "issue_number"),
    "query": ("query", "jql", "q", "search", "text"),
    "issue_key": ("key", "issue_key", "issue"),
    "project": ("project", "project_key", "projects"),
    "spreadsheet": ("spreadsheet_id", "spreadsheet", "sheet_id"),
    "range": ("cell_range", "range", "range_name", "a1_range"),
    "file": ("file_id", "document_id", "id"),
    "message": ("message_id", "id"),
    "calendar": ("calendar_id", "calendar"),
    "recipient": ("to", "recipient", "email", "addressee"),
    "labels": ("labels", "label"),
    "state": ("state", "status"),
    "limit": ("max_results", "limit", "per_page", "page_size", "top"),
    "title": ("title", "summary", "subject"),
    "body": ("body", "description", "text", "comment"),
    "timezone": ("timezone", "time_zone", "tz"),
    "time_min": ("time_min", "start", "from", "start_time", "timeMin"),
    "time_max": ("time_max", "end", "until", "end_time", "timeMax"),
    "values": ("values", "rows", "data"),
}

_ROLE_BY_TOOL: dict[str, tuple[str, ...]] = {
    "github.list_repositories": (),
    "github.list_pull_requests": ("repository", "state", "limit"),
    "github.get_pull_request": ("repository", "pull_request"),
    "github.list_pull_request_files": ("repository", "pull_request"),
    "github.list_pull_request_comments": ("repository", "pull_request"),
    "github.list_issues": ("repository", "state", "labels", "limit"),
    "github.create_issue": ("repository", "title", "body", "labels"),
    "github.add_comment": ("repository", "pull_request", "body"),
    "jira.search_issues": ("project", "query", "limit"),
    "jira.create_issue": ("project", "title", "body"),
    "jira.update_issue": ("issue_key", "title", "body"),
    "jira.add_comment": ("issue_key", "body"),
    "gmail.search_messages": ("query", "limit"),
    "gmail.get_message": ("message",),
    "gmail.send_message": ("recipient", "title", "body"),
    "drive.search_files": ("query", "limit"),
    "drive.get_file": ("file",),
    "sheets.read_range": ("spreadsheet", "range"),
    "sheets.write_range": ("spreadsheet", "range", "values"),
    "calendar.list_events": ("calendar", "time_min", "time_max", "limit"),
    "calendar.create_event": ("calendar", "title", "time_min", "time_max"),
    "docs.get_document": ("file",),
}

_DEFAULTS: dict[str, Any] = {
    "limit": 20,
    "range": "A1:Z200",
}

# Only a read tool may invent a reporting window; a write tool must be given real times.
_DEFAULT_WINDOW_TOOLS = frozenset({"calendar.list_events"})


_STATES = ("open", "closed", "merged", "all")

_TITLE_KEYS = (
    "title",
    "subject",
    "name",
    "full_name",
    "nameWithOwner",
    "filename",
    "summary",
    "snippet",
    "body",
    "text",
)
_NUMBER_KEYS = ("number", "pull_number", "issue_number", "id")
_STATE_KEYS = ("state", "status")
_OWNER_KEYS = ("user", "author", "sender", "owner")
_CONTAINER_KEYS = (
    "items",
    "results",
    "records",
    "repositories",
    "pull_requests",
    "issues",
    "files",
    "comments",
    "events",
    "messages",
    "values",
    "rows",
    "data",
)

_MAX_BULLETS = 8
_MAX_ITEMS_IN_BULLET = 4
_MAX_SUMMARY_CHARS = 900


class HeuristicPlanner(Planner):
    """A deterministic ``Planner``. Same input, same action, every time."""

    id = "heuristic"

    async def next(self, request: PlanRequest) -> Plan:
        available = {spec.name: spec for spec in request.tools}
        if not available:
            return Plan.finish(
                _no_tools_report(request.goal),
                thought="This Buttlr has no tools available, so there is nothing to look up.",
            )

        if request.step_index >= request.max_steps - 1:
            return Plan.finish(
                self._report(request, limit_reached=True),
                thought=(
                    "Step budget reached; reporting what was gathered so far."
                    if request.observations
                    else "Step budget reached before any tool could run."
                ),
            )

        used = {obs.tool for obs in request.observations if obs.approved is not False}
        rejected = {obs.tool for obs in request.observations if obs.approved is False}

        for tool_name in self._sequence(request, available):
            if tool_name in used or tool_name in rejected:
                continue
            spec = available.get(tool_name)
            if spec is None:  # pragma: no cover - sequence is built from the available set
                continue
            arguments = self._arguments(spec, request)
            if arguments is None:
                continue
            return Plan.call(
                tool_name,
                arguments,
                thought=self._thought(spec, arguments),
            )

        return Plan.finish(
            self._report(request),
            thought="Every planned check has been gathered; writing the report.",
        )

    # -- planning ----------------------------------------------------------------

    def _sequence(self, request: PlanRequest, available: dict[str, ToolSpec]) -> list[str]:
        """The ordered, de-duplicated list of tools this goal calls for."""
        text = _normalise(request.goal)
        spans = _write_spans(text, available)

        sequence: list[str] = []

        def add(name: str) -> None:
            if name in available and name not in sequence:
                sequence.append(name)

        matched = _matched_intents(text, spans)
        jira_only = "jira" in text.split() and _repository(request) is None

        if not matched:
            # Generic goal: work through the read-only tools in a sensible order.
            for spec in self._read_only_specs(available):
                add(spec.name)
        else:
            for intent in matched:
                for name in _READ_CHAINS.get(intent, ()):
                    if jira_only and name in _GITHUB_ISSUE_TOOLS:
                        # "open OPS tickets in Jira" is a Jira question, not a GitHub one.
                        continue
                    add(name)

        for name, pattern in _WRITE_COMPILED.items():
            if name not in available or not pattern.search(text):
                continue
            if jira_only and name in _GITHUB_ISSUE_TOOLS:
                continue
            intent = _WRITE_PRECEDES.get(name)
            if intent and not any(candidate in sequence for candidate in _READ_CHAINS[intent]):
                # Never write on top of nothing: without the read, the write has no grounding.
                logger.debug("Skipping write tool %s: no matching read tool in the plan.", name)
                continue
            add(name)

        # A GitHub read needs a repository: discover one unless the scope already names one.
        if (
            any(name.startswith("github.") for name in sequence)
            and _repository(request) is None
            and "github.list_repositories" in available
        ):
            sequence.insert(0, "github.list_repositories")

        return sequence

    @staticmethod
    def _read_only_specs(available: dict[str, ToolSpec]) -> list[ToolSpec]:
        def rank(spec: ToolSpec) -> tuple[int, str]:
            verb = spec.name.split(".", 1)[-1].split("_", 1)[0]
            return (_VERB_RANK.get(verb, 9), spec.name)

        specs = [
            spec
            for spec in available.values()
            if spec.name.split(".", 1)[-1].split("_", 1)[0] in _READ_VERBS
        ]
        return sorted(specs, key=rank)

    def _arguments(
        self, spec: ToolSpec, request: PlanRequest
    ) -> dict[str, Any] | None:
        """Arguments for one call, or ``None`` when a required value is not known yet."""
        properties: dict[str, Any] = spec.parameters.get("properties") or {}
        if not properties:
            return {}
        required = set(spec.parameters.get("required") or ())
        values = self._role_values(spec.name, request, properties, required)

        arguments: dict[str, Any] = {}
        for role in _ROLE_BY_TOOL.get(spec.name, ()):
            field = next(
                (alias for alias in _FIELD_ALIASES.get(role, (role,)) if alias in properties),
                None,
            )
            if field is None:
                continue
            value = values.get(role, _MISSING)
            if value is _MISSING:
                if field in required:
                    return None
                continue
            coerced = _coerce(value, properties[field])
            if coerced is None:
                if field in required:
                    return None
                continue
            arguments[field] = coerced

        # A required field we could not fill means the call would fail validation: skip it.
        missing = required - set(arguments)
        if missing:
            logger.debug(
                "Tool %s needs %s, which this run cannot supply.",
                spec.name,
                ", ".join(sorted(missing)),
            )
            return None
        return arguments

    def _role_values(
        self,
        tool_name: str,
        request: PlanRequest,
        properties: dict[str, Any],
        required: set[str],
    ) -> dict[str, Any]:
        observations = request.observations
        scope = request.scope
        goal = request.goal
        roles = _ROLE_BY_TOOL.get(tool_name, ())
        values: dict[str, Any] = {}

        repository = _repository(request)
        if repository:
            values["repository"] = repository

        if "pull_request" in roles:
            number = _first_pull_request_number(observations)
            if number is not None:
                values["pull_request"] = number

        if "state" in roles:
            state = _state(goal, properties)
            if state:
                values["state"] = state

        if "labels" in roles:
            labels = _scope_lookup(scope, "labels", "label")
            if labels:
                values["labels"] = labels

        if "limit" in roles:
            limit = _scope_lookup(scope, "limit", "max_results", "per_page")
            values["limit"] = limit if isinstance(limit, int) else _DEFAULTS["limit"]

        if "project" in roles:
            project = _scope_lookup(scope, "projects", "project", "project_key")
            if project:
                values["project"] = project

        if "issue_key" in roles:
            key = (
                _scope_lookup(scope, "issue_key", "issue", "key") or _issue_key(observations)
            )
            if not key:
                return {}
            if "title" in roles and "body" in roles and not (
                _goal_title(goal) or _grounded_body(observations)
            ):
                # jira.update_issue fails without a new summary or a new description.
                return {}
            values["issue_key"] = key

        if "recipient" in roles:
            recipient = _scope_lookup(scope, "to", "recipients", "recipient", "email")
            if recipient:
                values["recipient"] = recipient

        if "values" in roles:
            rows = _scope_lookup(scope, "values", "rows", "cells")
            if rows:
                values["values"] = rows

        if "spreadsheet" in roles:
            spreadsheet = _scope_lookup(
                scope, "spreadsheets", "spreadsheet", "spreadsheet_id", "sheet_id"
            )
            if spreadsheet:
                values["spreadsheet"] = spreadsheet

        if "range" in roles:
            cell_range = _scope_lookup(scope, "ranges", "range", "cell_range", "cells")
            if cell_range:
                values["range"] = cell_range
            else:
                sheet = _scope_lookup(scope, "sheet", "sheet_name", "tab")
                values["range"] = (
                    f"{sheet}!{_DEFAULTS['range']}" if sheet else _DEFAULTS["range"]
                )

        if "file" in roles:
            file_ids = _scope_lookup(scope, "file_ids", "files", "documents", "document_id")
            if isinstance(file_ids, str):
                values["file"] = file_ids
            else:
                file_id = _first_item_value(
                    observations, ("drive.search_files", "docs.get_document"), _ID_KEYS
                )
                if file_id:
                    values["file"] = file_id

        if "message" in roles:
            message_id = _scope_lookup(scope, "message_ids", "message_id") or _first_item_value(
                observations, ("gmail.search_messages",), _ID_KEYS
            )
            if message_id:
                values["message"] = message_id

        if "calendar" in roles:
            calendars = _scope_lookup(scope, "calendars", "calendar", "calendar_id")
            if calendars:
                values["calendar"] = calendars

        if "query" in roles:
            query = _query(tool_name, goal, scope)
            if query:
                values["query"] = query

        if "timezone" in roles:
            timezone = _scope_lookup(scope, "timezone", "time_zone", "tz")
            if timezone:
                values["timezone"] = timezone

        if "time_min" in roles:
            window = _scope_lookup(scope, "time_min", "start", "from")
            if window:
                values["time_min"] = window
            elif tool_name in _DEFAULT_WINDOW_TOOLS and (
                required & set(_FIELD_ALIASES["time_min"])
            ):
                # No window configured: start a day back so the report is never empty.
                values["time_min"] = _iso(_days_from_now(-1))

        if "time_max" in roles:
            window = _scope_lookup(scope, "time_max", "end", "until")
            if window:
                values["time_max"] = window
            elif tool_name in _DEFAULT_WINDOW_TOOLS and (
                required & set(_FIELD_ALIASES["time_max"])
            ):
                values["time_max"] = _iso(_days_from_now(14))

        if "title" in roles:
            title = _goal_title(goal)
            if title:
                values["title"] = title

        if "body" in roles:
            body = _grounded_body(observations)
            if body:
                values["body"] = body

        return values


    @staticmethod
    def _thought(spec: ToolSpec, arguments: dict[str, Any]) -> str:
        label = spec.description.split(".")[0].strip() or spec.name
        target = arguments.get("repo") or arguments.get("repository") or arguments.get("project")
        if target:
            return f"{label} ({target})."
        return f"{label}."

    # -- reporting ---------------------------------------------------------------

    def _report(self, request: PlanRequest, *, limit_reached: bool = False) -> str:
        observations = request.observations
        counts = _counts(observations)

        clauses = [label for label, _ in counts]
        if clauses:
            headline = f"Collected {_join(clauses)}."
        else:
            headline = "No data could be gathered for this request."

        lines = [f"**{headline}**", ""]

        findings = _findings(observations)
        lines.append("### Findings")
        lines.append("")
        if findings:
            lines.extend(f"- {finding}" for finding in findings[:_MAX_BULLETS])
        elif any(obs.ok for obs in observations):
            lines.append("- The tools returned nothing to report.")
        else:
            lines.append("- No tool was able to return data — see the notes below.")

        notes = _notes(observations, limit_reached=limit_reached)
        if notes:
            lines.append("")
            lines.append("### Approvals and blocked actions")
            lines.append("")
            lines.extend(f"- {note}" for note in notes)

        return "\n".join(lines)[:_MAX_SUMMARY_CHARS].strip()


# --------------------------------------------------------------------------------------
# Scope, goal and observation readers
# --------------------------------------------------------------------------------------

_MISSING = object()

_ID_KEYS = ("id", "file_id", "message_id", "thread_id", "name")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _write_spans(text: str, available: dict[str, ToolSpec]) -> list[tuple[int, int]]:
    """Character spans of the goal that explicitly ask for a write action."""
    spans: list[tuple[int, int]] = []
    for name, pattern in _WRITE_COMPILED.items():
        if name not in available:
            continue
        spans.extend(match.span() for match in pattern.finditer(text))
    return spans


def _matched_intents(text: str, write_spans: Sequence[tuple[int, int]]) -> list[str]:
    """Intents the goal is actually about.

    A word that only appears as the verb of a requested write ("file an issue") must not
    also send the planner off to read files; the same word outside that phrase still counts.
    """
    tokens: set[str] = set()
    for match in re.finditer(r"[a-z0-9]+", text):
        word = match.group(0)
        if word in _WRITE_VERBS and _inside(match.start(), write_spans):
            continue
        tokens.add(word)

    matched: list[str] = []
    for intent, keywords in _INTENTS.items():
        for keyword in keywords:
            if " " in keyword:
                if _phrase_outside(keyword, text, write_spans):
                    matched.append(intent)
                    break
            elif keyword in tokens:
                matched.append(intent)
                break
    return matched


def _phrase_outside(
    phrase: str, text: str, write_spans: Sequence[tuple[int, int]]
) -> bool:
    """True when the phrase appears somewhere that is not part of a requested write."""
    for match in re.finditer(re.escape(phrase), text):
        if not _inside(match.start(), write_spans):
            return True
    return False


def _inside(position: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _scope_lookup(scope: dict[str, Any], *keys: str) -> Any:
    """Read a scope value, whether scope is flat or grouped per provider."""
    if not scope:
        return None
    for key in keys:
        value = scope.get(key)
        if value not in (None, "", [], {}):
            return value
    for value in scope.values():
        if isinstance(value, dict):
            for key in keys:
                inner = value.get(key)
                if inner not in (None, "", [], {}):
                    return inner
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


def _repository(request: PlanRequest) -> str | None:
    scoped = _as_list(_scope_lookup(request.scope, "repositories", "repository", "repos"))
    discovered = _repositories_from(_observation_data(request.observations, "github.list_repositories"))
    if scoped:
        return str(scoped[0])
    if discovered:
        return discovered[0]
    return None


def _repositories_from(data: Any) -> list[str]:
    names: list[str] = []
    for item in _items(data):
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            for key in ("full_name", "fullName", "name_with_owner", "name", "id"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    names.append(value)
                    break
    return names


def _first_pull_request_number(observations: list[Observation]) -> int | None:
    for tool in ("github.list_pull_requests", "github.get_pull_request"):
        for item in _items(_observation_data(observations, tool)):
            if not isinstance(item, dict):
                continue
            for key in ("number", "pull_number", "pr_number"):
                value = item.get(key)
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)
            nested = item.get("pull_request")
            if isinstance(nested, dict):
                value = nested.get("number")
                if isinstance(value, int):
                    return value
    return None


def _issue_key(observations: list[Observation]) -> str | None:
    for tool in ("jira.search_issues", "jira.update_issue"):
        for item in _items(_observation_data(observations, tool)):
            value = _scalar(item, ("key", "id"))
            if value:
                return value
    return None


def _query(tool_name: str, goal: str, scope: dict[str, Any]) -> str | None:
    """The search string for a tool: scope first, then a JQL clause, then the goal's words."""
    configured = _scope_lookup(scope, "query", "search", "jql")
    if isinstance(configured, str) and configured:
        return configured

    if tool_name == "jira.search_issues":
        clause = _jql(goal, scope)
        if clause:
            return clause

    terms = _search_terms(goal)
    if not terms:
        return None
    if tool_name == "gmail.search_messages":
        # Gmail needs a real search expression rather than bare words.
        return f"in:anywhere {terms}"
    return terms


def _jql(goal: str, scope: dict[str, Any]) -> str | None:
    clauses: list[str] = []
    project = _as_list(_scope_lookup(scope, "projects", "project", "project_key"))
    for key in project:
        clauses.append(f'project = "{key}"')

    text = _normalise(goal)
    for state in _STATES:
        if state in text.split():
            clauses.append(f'status = "{state.capitalize()}"')
            break

    terms = _search_terms(goal)
    if terms:
        clauses.append(f'text ~ "{terms}"')

    if not clauses:
        return None
    return " AND ".join(clauses) + " ORDER BY updated DESC"


def _state(goal: str, properties: dict[str, Any]) -> str | None:
    text = _normalise(goal)
    for state in _STATES:
        if state in text.split():
            return state
    schema = next(
        (properties[alias] for alias in _FIELD_ALIASES["state"] if alias in properties), {}
    )
    enum = schema.get("enum")
    if isinstance(enum, list) and enum and not set(enum) & {"open", "OPEN"}:
        return None
    return "open"


def _search_terms(goal: str) -> str | None:
    text = _normalise(goal)
    if not text:
        return None
    stop = {
        "please",
        "check",
        "find",
        "list",
        "search",
        "look",
        "for",
        "all",
        "the",
        "a",
        "an",
        "in",
        "on",
        "of",
        "my",
        "our",
        "and",
        "any",
        "me",
        "review",
        "report",
        "to",
        "give",
        "summary",
        "update",
    }
    words = [word for word in re.findall(r"[a-z0-9]+", text) if word not in stop]
    return " ".join(words) if words else text


def _goal_title(goal: str) -> str | None:
    """A short, human title for a write, taken from the goal's own first sentence."""
    text = " ".join((goal or "").split())
    if not text:
        return None
    sentence = re.split(r"(?<=[.!?])\s|,\s+(?=if\b|and\s+(then|ask|also)\b)", text, maxsplit=1)[0]
    if len(sentence) > 120:
        sentence = sentence[:120].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return sentence or None


def _grounded_body(observations: list[Observation]) -> str | None:
    """A write body that only restates what the tools actually returned."""
    findings = _findings(observations, limit=6)
    if not findings:
        return None
    body = "\n".join(f"- {finding}" for finding in findings)
    return f"Written from this Buttlr run's own findings:\n{body}"[:_MAX_SUMMARY_CHARS]


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _days_from_now(days: int) -> datetime:
    return utcnow() + timedelta(days=days)


def _observation_data(observations: list[Observation], tool: str) -> Any:
    for observation in observations:
        if observation.tool == tool and observation.ok and observation.data is not None:
            return observation.data
    return None


def _items(data: Any) -> list[Any]:
    """Best-effort extraction of the record list inside a tool payload."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _CONTAINER_KEYS:
            value = data.get(key)
            if isinstance(value, list) and value:
                return value
        for value in data.values():
            if isinstance(value, list) and value:
                return value
    return []


def _first_item_value(
    observations: list[Observation], tools: Sequence[str], keys: Sequence[str]
) -> str | None:
    for tool in tools:
        for item in _items(_observation_data(observations, tool)):
            value = _scalar(item, keys)
            if value:
                return value
    return None


def _scalar(item: Any, keys: Sequence[str]) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, list):
        # A spreadsheet row: the first non-empty cell identifies it.
        for cell in item:
            value = _scalar(cell, keys)
            if value:
                return value
        return None
    if not isinstance(item, dict):
        return None
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value)
    return None


def _join(clauses: Sequence[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    return f"{', '.join(clauses[:-1])} and {clauses[-1]}"


def _clip(text: str, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sentence(text: str, limit: int = 180) -> str:
    """Clip to a single tidy sentence, without doubling the full stop."""
    clipped = _clip(text, limit).rstrip(". ")
    return f"{clipped}."


# --------------------------------------------------------------------------------------
# Report composition — every value below comes from an observation
# --------------------------------------------------------------------------------------


def _family(tool_name: str) -> tuple[str, str]:
    if tool_name in _FAMILY_LABEL:
        return _FAMILY_LABEL[tool_name]
    return ("results", "result")



def _agree(count: int, plural: str, singular: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _counts(observations: list[Observation]) -> list[tuple[str, int]]:
    """``[(phrased count, count), ...]`` for every family that returned records."""
    totals: dict[str, int] = {}
    forms: dict[str, str] = {}
    order: list[str] = []
    for observation in observations:
        if not observation.ok:
            continue
        items = _items(observation.data)
        if not items:
            continue
        plural, singular = _family(observation.tool)
        if plural not in totals:
            order.append(plural)
            forms[plural] = singular
        totals[plural] = totals.get(plural, 0) + len(items)
    return [(_agree(totals[label], label, forms[label]), totals[label]) for label in order]


def _findings(observations: list[Observation], limit: int = _MAX_BULLETS) -> list[str]:
    findings: list[str] = []
    for observation in observations:
        if observation.approved is False:
            continue
        if not observation.ok:
            continue
        items = _items(observation.data)
        plural, singular = _family(observation.tool)
        if items:
            described = ", ".join(_describe(item, singular) for item in items[:_MAX_ITEMS_IN_BULLET])
            more = len(items) - _MAX_ITEMS_IN_BULLET
            suffix = f" and {more} more" if more > 0 else ""
            findings.append(
                f"**{observation.tool}** — {_agree(len(items), plural, singular)}: "
                f"{described}{suffix}."
            )
        elif observation.summary:
            findings.append(f"**{observation.tool}** — {_clip(observation.summary)}")
    return findings[:limit]


def _describe(item: Any, singular: str) -> str:
    label = _scalar(item, _TITLE_KEYS)
    number = _scalar(item, _NUMBER_KEYS)
    state = _scalar(item, _STATE_KEYS)
    who = _owner(item)

    text = label or (number or "")
    if not text:
        text = singular
    if number and label and number != label:
        text = f"{text} (#{number})"
    if who:
        text = f"{text} — {who}"
    if state:
        text = f"{text} ({state})"
    return f"“{_clip(text, 120)}”"


def _owner(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in _OWNER_KEYS:
        value = item.get(key)
        if isinstance(value, dict):
            for inner in ("login", "name", "displayName", "email"):
                candidate = value.get(inner)
                if isinstance(candidate, str) and candidate:
                    return candidate
        elif isinstance(value, str) and value:
            return value
    return None


def _notes(observations: list[Observation], *, limit_reached: bool = False) -> list[str]:
    notes: list[str] = []
    for observation in observations:
        if observation.approved is False:
            notes.append(
                f"**{observation.tool}** was declined in review; it was not retried."
            )
        elif not observation.ok:
            reason = observation.summary or "the tool returned no reason"
            notes.append(f"**{observation.tool}** did not complete: {_sentence(reason)}")
    if limit_reached:
        notes.append("The step budget for this run ended before every planned check ran.")
    if not notes:
        notes.append("No action needed approval during this run.")
    return notes


def _no_tools_report(goal: str) -> str:
    headline = f"**Nothing to do for: {_clip(goal, 120)}**" if goal else "**Nothing to do**"
    return "\n".join(
        [
            headline,
            "",
            "### Findings",
            "",
            "- This Buttlr has no tools available for this request, so it could not look "
            "anything up.",
            "",
            "### Approvals and blocked actions",
            "",
            "- Grant the Buttlr a tool — for example `github.list_pull_requests` — and run it "
            "again to get a real report.",
        ]
    )


# --------------------------------------------------------------------------------------
# JSON-schema coercion
# --------------------------------------------------------------------------------------


def _coerce(value: Any, schema: dict[str, Any]) -> Any | None:
    """Fit ``value`` to what the tool's schema declares, or ``None`` if it cannot."""
    kind = schema.get("type")
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        for candidate in _candidates(value):
            if candidate in enum:
                return candidate
            for option in enum:
                if isinstance(option, str) and option.lower() == str(candidate).lower():
                    return option
        return None

    if kind == "array":
        if isinstance(value, list):
            return list(value)
        item = _first_scalar(value)
        return [item] if item is not None else None
    if kind == "object":
        return value if isinstance(value, dict) else None

    # A scalar field: scope stores collections, so take the single meaningful entry.
    candidate = _first_scalar(value)
    if candidate is None or isinstance(candidate, (list, dict)):
        return None

    if kind == "integer":
        try:
            return int(candidate)
        except (TypeError, ValueError):
            return None
    if kind == "number":
        try:
            return float(candidate)
        except (TypeError, ValueError):
            return None
    if kind == "boolean":
        if isinstance(candidate, bool):
            return candidate
        return str(candidate).strip().lower() in {"1", "true", "yes", "y"}

    text = str(candidate)
    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and max_length > 0 and len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def _candidates(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return [item for item in value if not isinstance(item, (list, dict))]
    if isinstance(value, dict):
        return [value]
    return [value]


def _first_scalar(value: Any) -> Any:
    """A scope collection reduced to the single entry a scalar field can hold."""
    if not isinstance(value, (list, tuple)):
        return value
    for item in value:
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, (str, int, float)):
            return item
        if isinstance(item, dict):
            for key in ("id", "full_name", "fullName", "name", "value", "key"):
                inner = item.get(key)
                if isinstance(inner, (str, int, float)) and str(inner).strip():
                    return inner
    return None
