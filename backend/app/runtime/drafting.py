"""Deterministic Buttlr drafting.

This is the offline configuration generator used when no LLM credentials are configured.
It is a real rule engine over the user's description: it maps keywords onto the tool
catalogue, derives identity, scope, schedule and approval policy, and records what it
assumed and what is still undecided. It is production code -- the offline demo runs on it --
so it must never echo the request back unexamined.

The output dict carries exactly the keys ``app.runtime.prompt.build_draft_from_plan``
consumes, plus ``rationale``, ``assumptions`` and ``missing``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = ["heuristic_draft", "heuristic_refine"]

# --------------------------------------------------------------------------- catalogue

GITHUB_PR_TOOLS = (
    "github.list_pull_requests",
    "github.get_pull_request",
    "github.list_pull_request_files",
    "github.list_pull_request_comments",
)
GITHUB_REPO_TOOLS = ("github.list_repositories",)
GITHUB_ISSUE_TOOL = "github.create_issue"
JIRA_SEARCH_TOOL = "jira.search_issues"
JIRA_CREATE_TOOL = "jira.create_issue"
GMAIL_READ_TOOLS = ("gmail.search_messages", "gmail.get_message")
GMAIL_SEND_TOOL = "gmail.send_message"
DRIVE_READ_TOOLS = ("drive.search_files", "drive.get_file")
SHEETS_READ_TOOL = "sheets.read_range"
SHEETS_WRITE_TOOL = "sheets.write_range"
CALENDAR_READ_TOOLS = ("calendar.list_events",)
CALENDAR_WRITE_TOOL = "calendar.create_event"

DEPARTMENTS = (
    "Engineering",
    "Finance",
    "HR",
    "Marketing",
    "Sales",
    "Customer Support",
    "Operations",
)

_WEEKDAYS = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}


@dataclass(frozen=True)
class _Capability:
    """One recognisable job the Buttlr could be given."""

    key: str
    name: str
    avatar: str
    role: str
    department: str
    domain: str = ""
    read_tools: tuple[str, ...] = ()
    write_tools: tuple[str, ...] = ()
    mentions: tuple[re.Pattern[str], ...] = ()
    writes: tuple[re.Pattern[str], ...] = ()
    duty: str = ""


def _p(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in patterns)


CAPABILITIES: tuple[_Capability, ...] = (
    _Capability(
        key="pull_requests",
        name="PR Guardian",
        avatar="\U0001f6e1\ufe0f",
        role="AI Pull Request Assistant",
        domain="pull request review",
        department="Engineering",
        read_tools=GITHUB_PR_TOOLS,
        mentions=_p(
            r"\bpull requests?\b",
            r"\bprs\b",
            r"\bpr\b",
            r"\bcode review",
            r"\breview comments?\b",
            r"\bmerge requests?\b",
            r"\bdiff\b",
        ),
        writes=_p(r"\bcomment on\b", r"\breview\b", r"\bapprove\b", r"\bmerge\b"),
        duty=(
            "Read new and updated pull requests, including their changed files and review "
            "comments, every time you run."
        ),
    ),
    _Capability(
        key="repositories",
        name="Repo Scout",
        avatar="\U0001f50d",
        role="AI Repository Analyst",
        domain="repository analysis",
        department="Engineering",
        read_tools=GITHUB_REPO_TOOLS,
        mentions=_p(r"\brepositor", r"\brepos\b", r"\bgithub\b", r"\bcodebases?\b", r"\bsource code\b"),
        duty="Enumerate the repositories and pull requests in scope before each analysis run.",
    ),
    _Capability(
        key="jira",
        name="Issue Shepherd",
        avatar="\U0001f3ad",
        role="AI Issue Tracker Assistant",
        domain="issue tracking",
        department="Engineering",
        read_tools=(JIRA_SEARCH_TOOL,),
        write_tools=(JIRA_CREATE_TOOL,),
        mentions=_p(r"\bjira\b", r"\bsprints?\b", r"\bbacklog\b", r"\bsprint board\b"),
        writes=_p(
            r"\b(create|open|file|raise|log|prepare|add|put)\b[^.]{0,40}\b(ticket|issue|jira)",
        ),
        duty=(
            "Search Jira for existing issues before creating anything, so duplicates are never "
            "filed."
        ),
    ),
    _Capability(
        key="github_issues",
        name="Issue Shepherd",
        avatar="\U0001f3ad",
        role="AI Issue Tracker Assistant",
        domain="issue tracking",
        department="Engineering",
        read_tools=GITHUB_REPO_TOOLS,
        write_tools=(GITHUB_ISSUE_TOOL,),
        mentions=_p(r"\bgithub issues?\b", r"\bissues?\b[^.]{0,30}\bgithub\b"),
        writes=_p(
            r"\b(create|open|file|raise|log|prepare|add|put)\b[^.]{0,40}\bgithub issue",
        ),
        duty="Check existing GitHub issues before raising a new one.",
    ),
    _Capability(
        key="email",
        name="Inbox Pilot",
        avatar="\U0001f4eb",
        role="AI Email Assistant",
        domain="email triage",
        department="Operations",
        read_tools=GMAIL_READ_TOOLS,
        write_tools=(GMAIL_SEND_TOOL,),
        mentions=_p(r"\be-?mails?\b", r"\bgmail\b", r"\binbox\b", r"\bmailbox\b", r"\bmessages?\b"),
        writes=_p(
            r"\b(send|draft|reply|respond|forward)\b[^.]{0,30}\b(e-?mail|message|mail|note|update|me|us|them|reply)\b",
            r"\bemail\s+(me|us|them|back|the team)\b",
        ),
        duty="Search the mailbox for the threads that need attention and summarise what matters.",
    ),
    _Capability(
        key="drive",
        name="Doc Navigator",
        avatar="\U0001f5c2\ufe0f",
        role="AI Document Assistant",
        domain="document search",
        department="Operations",
        read_tools=DRIVE_READ_TOOLS,
        mentions=_p(
            r"\bgoogle drive\b",
            r"\bdrive\b",
            r"\bfolders?\b",
            r"\bdocuments?\b",
            r"\bdocs?\b",
            r"\bfiles?\b",
        ),
        duty="Locate the relevant documents and folders, and read only what is needed.",
    ),
    _Capability(
        key="sheets",
        name="Cell Sentinel",
        avatar="\U0001f4ca",
        role="AI Spreadsheet Analyst",
        domain="spreadsheet analysis",
        department="Finance",
        read_tools=(SHEETS_READ_TOOL,),
        write_tools=(SHEETS_WRITE_TOOL,),
        mentions=_p(r"\bspreadsheets?\b", r"\bsheets?\b", r"\btables?\b", r"\bcsv\b", r"\brows?\b"),
        writes=_p(
            r"\b(write|update|append|add|fill|record|log|put)\b[^.]{0,30}\b(sheet|row|cell|table|csv)",
            r"\bupdate\b[^.]{0,30}\bspreadsheet\b",
        ),
        duty="Read the relevant spreadsheet ranges and report what changed.",
    ),
    _Capability(
        key="calendar",
        name="Calendar Clerk",
        avatar="\U0001f5d3\ufe0f",
        role="AI Scheduling Assistant",
        domain="scheduling",
        department="Operations",
        read_tools=CALENDAR_READ_TOOLS,
        write_tools=(CALENDAR_WRITE_TOOL,),
        mentions=_p(r"\bcalendar\b", r"\bmeetings?\b", r"\bappointments?\b", r"\bevents?\b", r"\bschedule\b"),
        writes=_p(
            r"\b(schedule|book|create|add|arrange|put)\b[^.]{0,30}\b(meeting|event|call|appointment)",
        ),
        duty="Check the calendar for conflicts before proposing or booking anything.",
    ),
)

_WRITE_VERBS = (
    "send",
    "create",
    "write",
    "open",
    "raise",
    "file",
    "book",
    "schedule",
    "post",
    "reply",
    "update",
    "log",
    "delete",
    "close",
    "comment",
    "approve",
    "merge",
    "assign",
    "add",
    "put",
)


# Leading verbs that turn a bare instruction into second-person prose.
_IMPERATIVE_VERBS = frozenset(
    {
        "monitor",
        "analyse",
        "analyze",
        "summarise",
        "summarize",
        "track",
        "review",
        "check",
        "read",
        "send",
        "create",
        "report",
        "digest",
        "follow",
        "watch",
        "keep",
        "find",
        "search",
        "open",
        "file",
        "draft",
        "prepare",
        "book",
        "write",
        "update",
        "list",
        "compile",
        "gather",
        "flag",
        "notify",
        "post",
        "raise",
        "audit",
        "process",
        "triage",
        "brief",
        "answer",
        "handle",
    }
)


# --------------------------------------------------------------------------- helpers


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _first_sentence(text: str, limit: int = 240) -> str:
    text = _normalise(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0] if parts else text
    if len(sentence) > limit:
        sentence = sentence[: limit - 1].rstrip() + "\u2026"
    return sentence


def _matches_any(text: str, *keywords: str) -> bool:
    """Word-boundary match of any keyword against ``text``."""
    return any(re.search(rf"\b{re.escape(keyword)}\w*\b", text) for keyword in keywords)


def _filter_tools(candidates: tuple[str, ...] | list[str], tool_names: list[str]) -> list[str]:
    """Keep only catalogue tools that are actually available."""
    available = set(tool_names)
    ordered: list[str] = []
    for name in candidates:
        if name in available and name not in ordered:
            ordered.append(name)
    return ordered


def _integrations_for(tools: list[str]) -> list[str]:
    return list(dict.fromkeys(name.split(".", 1)[0] for name in tools if "." in name))




# --------------------------------------------------------------------------- detection


def _detect(text: str) -> list[_Capability]:
    return [cap for cap in CAPABILITIES if _any(cap.mentions, text)]


def _write_requested(capability: _Capability, text: str) -> bool:
    """A write tool is only offered when the request actually asks for the action."""
    return bool(capability.write_tools) and _any(capability.writes, text)


def _resolve_tools(capabilities: list[_Capability], text: str, tool_names: list[str]) -> list[str]:
    ordered: list[str] = []
    for capability in capabilities:
        candidates = list(capability.read_tools)
        if _write_requested(capability, text):
            candidates += list(capability.write_tools)
        for tool in _filter_tools(candidates, tool_names):
            if tool not in ordered:
                ordered.append(tool)
    return ordered


def _approval_rules(tools: list[str], text: str, capabilities: list[_Capability]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    asked = {
        tool
        for capability in capabilities
        if _write_requested(capability, text)
        for tool in capability.write_tools
    }
    # Read-only tools never need a rule; only writes that are actually emitted do.
    for tool in tools:
        if tool in asked:
            rules.append({"tool": tool, "mode": "ask", "approver_roles": []})
    return rules


# --------------------------------------------------------------------------- identity


def _identity(capabilities: list[_Capability]) -> tuple[str, str, str, str]:
    if not capabilities:
        return ("Task Helper", "\U0001f916", "AI Assistant", "Operations")
    primary = capabilities[0]
    # The name comes from the primary job only. A compound name ("PR Guardian & Repo Scout")
    # reads like two employees and says less than the one the user asked for.
    return (primary.name, primary.avatar, primary.role, primary.department)


def _responsibilities(capabilities: list[_Capability], text: str) -> list[str]:
    duties = [cap.duty for cap in capabilities if cap.duty]
    analysis: list[str] = []
    if _matches_any(text, "bug", "defect", "regression"):
        analysis.append("Classify every finding as a bug, a security issue, a missing test or an open review comment.")
    if _matches_any(text, "security", "vulnerab", "cve", "exploit", "secret", "credential"):
        analysis.append("Assess security findings and describe the concrete exposure for each one.")
    if _matches_any(text, "test", "coverage", "unit test", "regression test"):
        analysis.append("Point out changes that ship without test coverage.")
    if _matches_any(text, "review comment", "unresolved", "thread", "discussion"):
        analysis.append("Track unresolved review comments and state who still owes a response.")
    if _matches_any(text, "summar", "digest", "brief", "report", "recap", "digest"):
        analysis.append("Summarise the important findings into a short, ranked report.")
    if _matches_any(text, "approve", "sign off", "sign-off", "lead"):
        analysis.append("Request approval from the named approver before taking any write action.")
    duties = analysis + duties or duties
    if not duties:
        duties = [
            "Review the material in scope at the start of every run.",
            "Record what you found, with links back to the source.",
            "Take no write action without approval.",
        ]
    return duties[:6]


def _domain_list(capabilities: list[_Capability]) -> str:
    domains = list(dict.fromkeys(cap.domain for cap in capabilities if cap.domain))
    if not domains:
        return "the work you have been given"
    if len(domains) == 1:
        return domains[0]
    return ", ".join(domains[:-1]) + " and " + domains[-1]


def _join_names(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _instructions(
    capabilities: list[_Capability],
    text: str,
    timezone: str,
    approval_rules: list[dict[str, Any]],
) -> str:
    lines = [
        f"You are responsible for {_domain_list(capabilities)}.",
        "",
        "At the start of every run:",
    ]
    for capability in capabilities:
        tools = list(capability.read_tools)
        duty = capability.duty or f"Gather the material for {capability.key.replace('_', ' ')}."
        lines.append(f"- Use {_join_names(tools) or 'the available tools'} to {duty[0].lower()}{duty[1:]}")
    if _matches_any(text, "summar", "digest", "brief", "report", "recap"):
        lines.append(
            "- Finish with a short ranked summary. Lead with what a human has to act on, and "
            "say plainly when nothing important was found."
        )
    lines += [
        "",
        "Working rules:",
        "- Work only inside the configured scope and never widen it on your own.",
        "- Distinguish a confirmed finding from a suspicion, and cite the source for every claim.",
    ]
    if approval_rules:
        gated = _join_names([f"{rule['tool']} ({rule['mode']})" for rule in approval_rules])
        lines.append(
            f"- Prepare these changes in full, then ask for approval before running them: {gated}."
        )
    lines.append(
        "- Never send, create or modify anything in an external system before a human has approved it."
    )
    lines.append(f"- Interpret every date and time in {timezone}.")
    return "\n".join(lines)


def _objective(text: str, capabilities: list[_Capability]) -> str:
    """What the Buttlr is trying to achieve, written in the second person."""
    if not capabilities:
        return "You carry out the work you have been given, end to end, without waiting to be asked."
    request = _first_sentence(text).rstrip(". ")
    first_word = request.split(" ", 1)[0].lower() if request else ""
    if first_word in _IMPERATIVE_VERBS and len(request) > len(first_word):
        return f"You {first_word}{request[len(first_word):]}."
    if _matches_any(text, "summar", "digest", "brief", "report", "recap"):
        return "You make sure the findings that matter are summarised in time for someone to act."
    if request:
        return f"You make sure this happens without anyone chasing it: {request}."
    return f"You keep {_domain_list(capabilities)} under control without anyone chasing them."


# --------------------------------------------------------------------------- scope

_REPO_PATTERNS = (
    re.compile(r"\b(?:the\s+)?[\"'`]?([a-z0-9][a-z0-9._-]{1,40})[\"'`]?\s+repo(?:sitory|s)?\b"),
    re.compile(r"\brepo(?:sitory|s)?\s+[\"'`]?([a-z0-9][a-z0-9._-]{1,40})[\"'`]?\b"),
    re.compile(r"\b([a-z0-9][a-z0-9._/-]*)/[a-z0-9][a-z0-9._-]*\b"),
)
_LABEL_PATTERN = re.compile(r"\blabels?\s+[\"'`]?([\w-]+)[\"'`]?")
_PROJECT_PATTERN = re.compile(r"\bproject\s+(?:key\s+)?[\"'`]?([A-Za-z][A-Za-z0-9_-]{1,20})[\"'`]?")


def _scope(text: str, tools: list[str], teams: list[str] | None) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    integrations = _integrations_for(tools)

    if "github" in integrations:
        github: dict[str, Any] = {}
        repositories: list[str] = []
        for pattern in _REPO_PATTERNS:
            for match in pattern.findall(text):
                candidate = match.strip("/").lower()
                if candidate and candidate not in repositories:
                    repositories.append(candidate)
        if repositories:
            github["repositories"] = repositories
        labels = [m.strip().lower() for m in _LABEL_PATTERN.findall(text)]
        if labels:
            github["labels"] = list(dict.fromkeys(labels))
        if _matches_any(text, "open pull request", "open prs", "open pr", "ready for review"):
            github["states"] = ["open"]
        elif _matches_any(text, "all pull requests", "every pull request", "all prs"):
            github["states"] = ["open", "closed"]
        if _matches_any(text, "exclude fork", "not fork", "ignore fork"):
            github["include_forks"] = False
        if teams and _matches_any(text, "team", "squad", "group"):
            github["teams"] = list(teams)
        if _matches_any(text, "only mine", "assigned to me", "my pull requests"):
            github["assignee"] = "@me"
        if github:
            scope["github"] = github

    if "jira" in integrations:
        jira: dict[str, Any] = {}
        projects = [m for m in _PROJECT_PATTERN.findall(text) if not m.islower()]
        if projects:
            jira["projects"] = list(dict.fromkeys(projects))
        if _matches_any(text, "only open", "open issues", "unresolved issues"):
            jira["statuses"] = ["open"]
        if jira:
            scope["jira"] = jira

    if "gmail" in integrations:
        gmail: dict[str, Any] = {}
        if _matches_any(text, "unread", "not read"):
            gmail["unread_only"] = True
        if _matches_any(text, "inbox"):
            gmail["folder"] = "INBOX"
        labels = [m.strip().lower() for m in re.findall(r"\blabel\s+[\"'`]?([\w-]+)[\"'`]?", text)]
        if labels:
            gmail["labels"] = list(dict.fromkeys(labels))
        if gmail:
            scope["gmail"] = gmail

    if "drive" in integrations:
        drive: dict[str, Any] = {}
        folders = [m.strip() for m in re.findall(r"\bfolder\s+[\"']([^\"']+)[\"']", text)]
        if folders:
            drive["folders"] = list(dict.fromkeys(folders))
        if drive:
            scope["drive"] = drive

    return scope


# --------------------------------------------------------------------------- schedule

_TIME_24 = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_TIME_12 = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
_CRON = re.compile(
    r"\bcron\b[^0-9\-*/,\s]*((?:\S+\s+){4}\S+)", re.IGNORECASE
)
_INTERVAL_MINUTES = re.compile(r"\bevery\s+(\d+)\s*(?:minutes?|mins?)\b")
_INTERVAL_HOURS = re.compile(r"\bevery\s+(\d+)\s*hours?\b")
_WEEKDAY = re.compile(r"\b(?:every|on|each)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")
_DAY_OF_MONTH = re.compile(r"\bon the\s+(\d{1,2})(?:st|nd|rd|th)?\b")

DEFAULT_DAILY_TIME = "09:00"


def _extract_time(text: str) -> str | None:
    match = _TIME_12.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
        if hour <= 23 and minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    match = _TIME_24.search(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour <= 23 and minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


def _empty_schedule(timezone: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "kind": "manual",
        "timezone": timezone,
        "at": None,
        "day_of_week": None,
        "day_of_month": None,
        "interval_minutes": None,
        "cron": None,
    }


def _parse_schedule(text: str, timezone: str) -> dict[str, Any]:
    lowered = text.lower()
    stated_time = _extract_time(lowered)

    cron_match = _CRON.search(lowered)
    if cron_match:
        cron = re.sub(r"\s+", " ", cron_match.group(1)).strip()
        if len(cron.split()) == 5:
            schedule = _empty_schedule(timezone)
            schedule.update(enabled=True, kind="cron", cron=cron)
            return schedule

    minutes = _INTERVAL_MINUTES.search(lowered)
    if minutes:
        value = int(minutes.group(1))
        if value > 0:
            schedule = _empty_schedule(timezone)
            schedule.update(enabled=True, kind="interval", interval_minutes=value)
            return schedule

    hours = _INTERVAL_HOURS.search(lowered)
    if hours:
        value = int(hours.group(1))
        if value > 0:
            schedule = _empty_schedule(timezone)
            schedule.update(enabled=True, kind="interval", interval_minutes=value * 60)
            return schedule

    if _matches_any(lowered, "every hour", "hourly", "each hour"):
        schedule = _empty_schedule(timezone)
        schedule.update(enabled=True, kind="hourly")
        return schedule

    day_of_month = _DAY_OF_MONTH.search(lowered)
    if _matches_any(lowered, "every month", "monthly", "each month"):
        schedule = _empty_schedule(timezone)
        schedule.update(
            enabled=True,
            kind="monthly",
            day_of_month=int(day_of_month.group(1)) if day_of_month else None,
            at=stated_time or DEFAULT_DAILY_TIME,
        )
        return schedule

    weekday = _WEEKDAY.search(lowered)
    weekly = bool(weekday) or _matches_any(lowered, "every week", "weekly", "each week", "weekdays", "every friday")
    if weekly:
        schedule = _empty_schedule(timezone)
        schedule.update(
            enabled=True,
            kind="weekly",
            day_of_week=_WEEKDAYS[weekday.group(1)] if weekday else None,
            at=stated_time or DEFAULT_DAILY_TIME,
        )
        return schedule

    daily = _matches_any(lowered, 
        "every morning", "every day", "every evening", "every night", "daily", "each day", "every weekday"
    )
    if daily:
        schedule = _empty_schedule(timezone)
        schedule.update(enabled=True, kind="daily", at=stated_time or DEFAULT_DAILY_TIME)
        return schedule

    if stated_time and _matches_any(lowered, "every day", "each day", "daily", "at", "each morning"):
        schedule = _empty_schedule(timezone)
        schedule.update(enabled=True, kind="daily", at=stated_time)
        return schedule

    return _empty_schedule(timezone)


# --------------------------------------------------------------------------- public API


def heuristic_draft(
    prompt: str,
    tool_names: list[str],
    *,
    default_timezone: str = "UTC",
    teams: list[str] | None = None,
    organization_name: str | None = None,
) -> dict[str, Any]:
    """Build a complete Buttlr configuration from a plain-English description."""
    text = _normalise(prompt)
    lowered = text.lower()
    capabilities = _detect(lowered)
    tools = _resolve_tools(capabilities, lowered, tool_names)
    name, avatar, role, department = _identity(capabilities)
    schedule = _parse_schedule(lowered, default_timezone)
    rules = _approval_rules(tools, lowered, capabilities)

    assumptions = [
        f"All times are interpreted in {default_timezone}.",
    ]
    if schedule["enabled"] and schedule["at"] and not _extract_time(lowered):
        assumptions.append(
            f"No time of day was given, so runs start at {DEFAULT_DAILY_TIME} {default_timezone}."
        )
    if capabilities and not tools:
        assumptions.append(
            "No matching tool is connected for the requested work, so this Buttlr starts without tools."
        )
    if organization_name:
        assumptions.append(f"Assumes the workspace belongs to {organization_name}.")

    missing: list[str] = []
    if not capabilities:
        missing.append("Describe what the Buttlr should watch or act on so tools can be assigned.")
    if not tools and capabilities:
        missing.append(
            "Connect the "
            + ", ".join(_integrations_for([t for c in capabilities for t in c.read_tools + c.write_tools]))
            + " integration so the requested tools become available."
        )
    if not schedule["enabled"]:
        missing.append("No run time was given, so the Buttlr is manual. Tell it when to run.")
    if any(rule["tool"] == JIRA_CREATE_TOOL for rule in rules):
        missing.append(
            "Decide which approver role signs off on a created ticket, and which Jira project it goes to."
        )
    if _matches_any(lowered, "critical", "severity", "severities") and not _matches_any("escalat", "notify", "slack", "email"):
        missing.append("Define what counts as critical and where a critical finding should be escalated.")

    rationale = _rationale(capabilities, tools, schedule, rules, default_timezone)

    return {
        "name": name,
        "avatar": avatar,
        "role": role,
        "department": department,
        "description": _first_sentence(text) or "Keeps an eye on the work that matters.",
        "objective": _objective(text, capabilities),
        "responsibilities": _responsibilities(capabilities, lowered),
        "instructions": _instructions(capabilities, lowered, default_timezone, rules),
        "tools": tools,
        "integrations": _integrations_for(tools),
        "scope": _scope(lowered, tools, teams),
        "schedule": schedule,
        "approval_policy": {
            "default_mode": "auto",
            "rules": rules,
            "require_for_risk": "high",
        },
        "rationale": rationale,
        "assumptions": assumptions,
        "missing": missing,
    }


def _rationale(
    capabilities: list[_Capability],
    tools: list[str],
    schedule: dict[str, Any],
    rules: list[dict[str, Any]],
    timezone: str,
) -> str:
    if not capabilities:
        return (
            "The request does not name a system this Buttlr could read from, so it was drafted "
            "without tools and left on manual trigger. Once you say what it should watch, the "
            "matching tools are added automatically."
        )
    domains = _domain_list(capabilities)
    parts = [
        f"The description points at {domains}, so the Buttlr was given the smallest tool set that "
        f"covers it: {', '.join(tools) if tools else 'none of the requested tools are connected'}."
    ]
    if schedule["enabled"]:
        parts.append(
            f"It runs on a {schedule['kind']} schedule"
            + (f" at {schedule['at']}" if schedule.get("at") else "")
            + f" in {timezone}, as stated."
        )
    else:
        parts.append("No run time was stated, so it stays on manual trigger rather than guessing one.")
    if rules:
        parts.append(
            "The write actions ("
            + ", ".join(rule["tool"] for rule in rules)
            + ") are gated behind an approval prompt, because they change something outside Buttlr."
        )
    parts.append("Everything else runs automatically; high-risk actions still require a human.")
    return " ".join(parts)


def heuristic_refine(
    current: dict[str, Any],
    instruction: str,
    tool_names: list[str],
) -> dict[str, Any]:
    """Apply a follow-up instruction to an existing draft, leaving other keys untouched."""
    draft: dict[str, Any] = {key: _deep_copy(value) for key, value in current.items()}
    text = _normalise(instruction)
    lowered = text.lower()
    if not lowered:
        return draft

    notes: list[str] = []

    # --- schedule ---------------------------------------------------------
    schedule = _parse_schedule(lowered, draft.get("schedule", {}).get("timezone") or "UTC")
    if schedule["enabled"]:
        draft["schedule"] = schedule
        notes.append(
            f"Schedule updated to {schedule['kind']}"
            + (f" at {schedule['at']}" if schedule.get("at") else "")
            + "."
        )
    elif _matches_any(lowered, "stop", "disable", "no longer run", "on demand", "manual only", "cancel the schedule"):
        existing = dict(draft.get("schedule") or {})
        timezone = existing.get("timezone") or "UTC"
        draft["schedule"] = _empty_schedule(timezone)
        notes.append("Schedule disabled; the Buttlr now runs only when triggered manually.")

    # --- scope narrowing --------------------------------------------------
    scope = dict(draft.get("scope") or {})
    repositories: list[str] = []
    for pattern in _REPO_PATTERNS:
        for match in pattern.findall(lowered):
            candidate = match.strip("/").lower()
            if candidate and candidate not in repositories:
                repositories.append(candidate)
    if repositories and ("only" in lowered or "just" in lowered or "restrict" in lowered or "scope" in lowered):
        github = dict(scope.get("github") or {})
        github["repositories"] = repositories
        scope["github"] = github
        draft["scope"] = scope
        notes.append("Scope narrowed to " + ", ".join(repositories) + ".")
    if _matches_any(lowered, "all repositories", "every repository", "whole organisation", "whole organization", "all repos"):
        github = dict(scope.get("github") or {})
        github.pop("repositories", None)
        github.pop("teams", None)
        if github:
            scope["github"] = github
        else:
            scope.pop("github", None)
        draft["scope"] = scope
        notes.append("Scope widened to every repository the connection can see.")

    # --- tools ------------------------------------------------------------
    previous_tools = [str(t) for t in (draft.get("tools") or [])]
    tools = list(previous_tools)
    if _matches_any(lowered, "no longer", "stop using", "remove", "without", "don't use", "drop the"):
        removed = [t for t in tools if any(key in lowered for key in _tool_keywords(t))]
        tools = [t for t in tools if t not in removed]
        if removed:
            notes.append("Removed " + ", ".join(removed) + ".")
    if _matches_any(lowered, "also", "additionally", "as well", "plus", "and also", "now"):
        for tool in _resolve_tools(_detect(lowered), text, tool_names):
            if tool not in tools:
                tools.append(tool)
                notes.append(f"Added {tool}.")
    added = [t for t in tools if t not in previous_tools]
    if tools != previous_tools:
        draft["tools"] = tools
        draft["integrations"] = _integrations_for(tools)

    # --- approval policy --------------------------------------------------
    policy = dict(draft.get("approval_policy") or {})
    # A rule for a tool the Buttlr no longer carries is dead configuration.
    rules = [dict(rule) for rule in (policy.get("rules") or []) if rule.get("tool") in tools]
    default_mode = policy.get("default_mode", "auto")
    for tool in added:
        if _is_write_tool(tool) and not any(rule["tool"] == tool for rule in rules):
            rules.append({"tool": tool, "mode": "ask", "approver_roles": []})

    if _matches_any(lowered, "always ask", "ask me first", "ask before", "require approval", "always get approval", "confirm"):
        default_mode = "ask"
        notes.append("Everything now needs your approval before it runs.")
    elif _matches_any(lowered, "don't need approval", "no approval", "without asking", "automatically", "don't ask"):
        default_mode = "auto"
        notes.append("Approval prompts removed; actions run automatically.")

    mentioned_writes = [
        tool
        for tool in tools
        if _is_write_tool(tool) and any(key in lowered for key in _tool_keywords(tool))
    ]
    if mentioned_writes:
        deny = _matches_any(lowered, "don't", "do not", "never", "stop")
        for tool in mentioned_writes:
            rules = [rule for rule in rules if rule.get("tool") != tool]
            if deny and _matches_any(lowered, "automatic", "automatically", "create", "send", "post"):
                rules.append({"tool": tool, "mode": "deny", "approver_roles": []})
                notes.append(f"{tool} is no longer allowed at all.")
            else:
                rules.append({"tool": tool, "mode": "ask", "approver_roles": []})
                notes.append(f"{tool} now asks for approval first.")
    if "approval_policy" in draft or rules or default_mode != "auto":
        policy["default_mode"] = default_mode
        policy.setdefault("require_for_risk", "high")
        policy["rules"] = rules
        draft["approval_policy"] = policy

    # --- identity and prose ----------------------------------------------
    if _matches_any(lowered, "rename", "call it", "name it"):
        match = re.search(r"(?:call it|name it|rename (?:it|this|to))\s+[\"']?([A-Za-z0-9][\w '-]{1,30}?)[\"']?(?:[.,]|$)", text)
        if match:
            draft["name"] = match.group(1).strip()
            notes.append(f"Renamed to {draft['name']}.")
    if _matches_any(lowered, "department"):
        for candidate in DEPARTMENTS:
            if _matches_any(candidate.lower(), lowered):
                draft["department"] = candidate
                notes.append(f"Department set to {candidate}.")
                break

    if notes:
        existing = _normalise(str(draft.get("instructions") or ""))
        addition = "Update requested: " + " ".join(notes)
        draft["instructions"] = f"{existing}\n\n{addition}".strip() if existing else addition

    return draft


def _tool_keywords(tool: str) -> tuple[str, ...]:
    """Words that refer to a tool in plain English."""
    integration, _, action = tool.partition(".")
    base = action.split("_")[0]
    words = {integration, base}
    if base == "list":
        words.add("list")
    if base == "get":
        words.add("read")
    return tuple(word for word in words if len(word) > 3)


def _is_write_tool(tool: str) -> bool:
    """Whether a tool changes something outside Buttlr, based on its action verb."""
    action = tool.partition(".")[2].split("_", 1)[0]
    return action in _WRITE_VERBS


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
