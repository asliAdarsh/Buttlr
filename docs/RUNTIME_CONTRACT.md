# Buttlr — runtime orchestration contract (architect-owned)

`docs/CONTRACTS.md` freezes module paths, services and HTTP. This file freezes the pieces it
left open: the executor/runner API, tool and integration naming, and the offline
(`heuristic`) code path. **Do not change these signatures.** Every slice is written against
them.

## 1. Tool naming

`Tool.name` is `"<provider>.<verb>_<noun>"`. Registration is by exact name; a Buttlr stores
tool names in `Buttlr.tools`.

| Provider | Tools |
| --- | --- |
| GitHub | `github.list_repositories`, `github.list_pull_requests`, `github.get_pull_request`, `github.list_pull_request_files`, `github.list_pull_request_comments`, `github.list_issues`, `github.create_issue`, `github.add_comment` |
| Jira | `jira.search_issues`, `jira.create_issue`, `jira.update_issue`, `jira.add_comment` |
| Gmail | `gmail.search_messages`, `gmail.get_message`, `gmail.send_message` |
| Drive | `drive.search_files`, `drive.get_file` |
| Sheets | `sheets.read_range`, `sheets.write_range` |
| Calendar | `calendar.list_events`, `calendar.create_event` |
| Docs | `docs.get_document` |

Tool risk/permission defaults:

* `list_*`, `get_*`, `search_*`, `read_*` → `required_permission=EXECUTE`, `risk=LOW`, `read_only=True`
* `create_*` → `risk=MEDIUM`
* `add_comment`, `update_*`, `write_range` → `risk=MEDIUM`
* `send_message`, `create_event` → `risk=HIGH`
* `github.create_issue`, `jira.create_issue` → `risk=HIGH`

`Tool.run(ctx, params)` must return `ToolResult`. When `ctx.dry_run` is true a write tool must
return `ToolResult.failure("Dry run: <tool> was not executed.")` without performing the write.
Read-only tools execute normally in a dry run.

## 2. Model providers

`app.runtime.models.providers.build_providers(settings) -> list[ModelProvider]` returns, in
preference order:

`OpenAIProvider` (`openai`), `AnthropicProvider` (`anthropic`), `GoogleProvider` (`google`),
`OllamaProvider` (`ollama`), `HeuristicProvider` (`heuristic`).

`HeuristicProvider.is_available()` always returns `True`; it is the offline path. It must:

* accept `CompletionRequest` and return `CompletionResponse` with `provider="heuristic"`;
* when `json_mode` is true and the prompt is the Buttlr-draft prompt (system contains
  `"You are the Buttlr Builder"`), return the deterministic draft JSON produced by
  `app.runtime.drafting.heuristic_draft(...)`;
* otherwise return a short deterministic completion string.

`app.runtime.drafting` must export:

```python
def heuristic_draft(
    prompt: str,
    tool_names: list[str],
    *,
    default_timezone: str = "UTC",
    teams: list[str] | None = None,
    organization_name: str | None = None,
) -> dict[str, Any]
def heuristic_refine(current: dict[str, Any], instruction: str, tool_names: list[str]) -> dict[str, Any]
```

`heuristic_draft` returns the same JSON shape `build_draft_from_plan` consumes.

## 3. Planner

`app.runtime.planner.heuristic.HeuristicPlanner()` — no constructor arguments, implements
`Planner`. Deterministic; it drives the offline demo. Rules:

* Decide the tool sequence from `PlanRequest.goal` + `PlanRequest.tools` (the names available).
  Recognise: pull requests / PR review, issues, emails (Gmail), files (Drive), sheets, calendar.
* Never emit a tool that is not in `PlanRequest.tools`.
* Emit exactly one action per `next()` call, reading `PlanRequest.observations` to decide.
* Always terminate with `Plan.finish(summary)` where the summary is composed from the actual
  observations (real data — never invented).
* If an observation is an approval rejection (`approved is False`), do not retry that tool;
  move on and note it in the final summary.
* If no tools are available, finish immediately with a clear explanation.

`app.runtime.planner.llm.LLMPlanner(models: ModelRouter, config: ModelConfig)` implements
`Planner`; on any model failure it raises `PlannerError` and the executor falls back to the
heuristic planner.

## 4. Executor and runner

```python
# dataclasses ExecutionJob / ResumeJob are defined in app/runtime/executor.py and re-exported
class ExecutionRunner:                 # app/workers/runner.py
    def __init__(self, executor: ButtlrExecutor, settings: Settings) -> None
    async def start(self) -> None
    async def stop(self) -> None
    def submit(self, job: ExecutionJob) -> None        # fire and forget, bounded concurrency
    def submit_resume(self, job: ResumeJob) -> None
    def create_execution(self, organization, buttlr, trigger, goal, requested_by,
                         dry_run=False, conversation_id=None) -> Execution
    def active_count(self) -> int

class ButtlrExecutor:                  # app/runtime/executor.py
    def __init__(self, *, settings, store, registry, models, permissions,
                 executions, approvals, integrations, audit, notifications, bus) -> None
    async def run(self, job: ExecutionJob) -> Execution
    async def resume(self, job: ResumeJob) -> Execution
```

`ExecutionRunner` owns an `asyncio.Semaphore(settings.execution_workers)`, tracks tasks, and
cancels them on `stop()`. It must never raise into the caller of `submit`.

`ButtlrExecutor.run`:

1. mark the execution `RUNNING` (`started_at`), publish a status event;
2. build tool specs for `buttlr.tools`, credentials via
   `integrations.credentials_for(org_id, buttlr)`, and a `ToolContext` (scope, credentials,
   `dry_run`);
3. loop up to `settings.max_agent_steps`:
   * `plan = await planner.next(PlanRequest(...))`;
   * `FINAL` → append a `MESSAGE` step, set `output`, break;
   * `TOOL` → unknown tool ⇒ observation `ok=False`; else evaluate
     `permissions.evaluate(buttlr=..., access=job.access, tool_name=..., required_permission=tool.required_permission,
     risk=tool.risk, owner_access=<creator AccessContext if resolvable, else None>)`:
     * `DENY` → append a `BLOCKED` step, audit `TOOL_DENIED`, observation `ok=False`;
     * `REQUEST_APPROVAL` → `approvals.create(...)`, append an `APPROVAL_REQUEST` step, set
       execution `WAITING_APPROVAL` + `pending_approval_id`, publish, return;
     * `ALLOW` → run the tool with `asyncio.wait_for(..., settings.tool_timeout_seconds)`,
       append a `TOOL_RESULT` step, audit `TOOL_EXECUTED`;
4. when the loop ends or breaks: `executions.finish(...)` with `COMPLETED`/`FAILED`, update
   stats, audit, notify, publish.

`ButtlrExecutor.resume` rebuilds observations from `execution.steps`, applies the approval
decision (executing the approved tool on grant, recording a rejection otherwise), then
continues the same loop.

Both must check `executions.get(...)` for a `CANCELLED` status between steps and stop cleanly.

## 5. IntegrationService

Constructor is `IntegrationService(store, audit, settings)` (see `app/container.py`).
Beyond `docs/CONTRACTS.md` it must expose:

```python
async def add_tools(self, registry) -> None            # not needed; tools are static
async def probe(self, provider: IntegrationProvider, credentials: dict) -> str | None
```

`credentials_for(org_id, buttlr) -> dict[str, dict]` returns **decrypted** credentials keyed by
provider, for every provider in `buttlr.integrations` (deduplicated, ignoring disconnected
integrations). A missing integration yields no key; tools then fail closed with an actionable
message.

Provider client modules (used by both tools and IntegrationService):

* `app.integrations.github.GitHubClient(token, base_url=None)`
* `app.integrations.jira.JiraClient(base_url, email, api_token)`
* `app.integrations.google.GoogleClient(credentials)` — Gmail/Drive/Sheets/Calendar/Docs via REST

Each raises `IntegrationError` with a human-readable message on failure (401 → "connection may
have expired, reconnect"). Tokens are never logged.

## 6. ExecutionService additions

```python
async def set_status(self, execution: Execution, status: ExecutionStatus, **fields) -> Execution
async def append_step(self, execution: Execution, step: ExecutionStep) -> Execution
```

`append_step` assigns `step.index`, persists the execution and publishes a
`ExecutionEvent(event="step", step=...)` on the bus. `set_status` publishes
`ExecutionEvent(event="status", status=...)`. `finish` publishes `event="status"` with the
terminal status and updates the parent Buttlr's `stats` document
(`total_runs`, `successful_runs`, `failed_runs`, `last_run_at`, `last_status`,
`last_duration_ms`, `estimated_minutes_saved`).

## 7. Chat

`app/services/chat.py`:

```python
class ChatService:
    def __init__(self, *, store, runner, executions, buttlrs, settings, audit) -> None
    async def send(self, *, principal, organization, buttlr, message, conversation_id, dry_run) -> ChatResponse
    async def conversations(self, org_id, buttlr_id) -> list[Conversation]
    async def messages(self, org_id, buttlr_id, conversation_id) -> list[ChatMessage]
```

`send` persists the user message, enforces `Permission.ASK` on the Buttlr, creates an
execution (trigger `CHAT`, same conversation) and submits it to the runner, then returns the
conversation id. The assistant reply is written when the execution finishes (the executor
appends a `ChatMessage` with `role=assistant` when `conversation_id` is set).

## 8. Access resolution

`AccessContext` is built only from the resolved `Principal` + `Member`:

```python
AccessContext(
    user_id=principal.user_id,
    org_role=member.role,
    team_ids=tuple(member.team_ids),
    settings=organization.settings,
)
```

Never accept a role, permission or team list from a request body.
