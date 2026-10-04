# Buttlr — frozen interfaces

Every slice of the codebase is written against these. Do not change a signature without
updating every call site in the same change.

## Backend module map

| Module | Must export |
| --- | --- |
| `app.core.config` | `Settings`, `settings`, `get_settings()` |
| `app.core.errors` | `ButtlrError`, `NotFoundError`, `ConflictError`, `ValidationError`, `PermissionDeniedError`, `UnauthenticatedError`, `IntegrationError`, `ToolExecutionError`, `ModelError`, `ApprovalRequiredError` |
| `app.core.logging` | `configure_logging()`, `get_logger(name)`, `new_request_id()`, `set_request_context(**kw)`, `current_request_id()` |
| `app.core.crypto` | `encrypt_secret(str)->str`, `decrypt_secret(str)->str`, `mask_secret(str)->str` |
| `app.database.base` | `Store`, `Query`, `Condition`, `Op`, `Sort`, `eq`, `new_id()` |
| `app.database.factory` | `build_store(settings) -> Store` |
| `app.database.memory` | `MemoryStore` |
| `app.database.firestore` | `FirestoreStore` |
| `app.database.repository` | `Repository` (typed helpers over `Store`) |
| `app.schemas.*` | as written |
| `app.auth.provider` | `TokenVerifier` protocol, `FirebaseTokenVerifier`, `DevTokenVerifier`, `build_verifier(settings)` |
| `app.auth.service` | `AuthService` |
| `app.runtime.tools.base` | `Tool`, `ToolContext`, `ToolResult` |
| `app.runtime.tools.registry` | `ToolRegistry`, `registry` |
| `app.runtime.models.base` | `ModelProvider`, `CompletionRequest`, `CompletionResponse`, `Message`, `ToolCall`, `ToolSpec` |
| `app.runtime.models.router` | `ModelRouter` |
| `app.runtime.models.providers.*` | `OpenAIProvider`, `AnthropicProvider`, `GoogleProvider`, `OllamaProvider`, `HeuristicProvider` |
| `app.runtime.permissions.engine` | `PermissionEngine`, `engine`, `AccessContext`, `PermissionDecision`, `granted_permission`, `resolve_approval` |
| `app.runtime.planner.base` | `Planner`, `Plan`, `PlanAction` |
| `app.runtime.planner.llm` | `LLMPlanner` |
| `app.runtime.planner.heuristic` | `HeuristicPlanner` |
| `app.runtime.executor` | `ButtlrExecutor`, `ExecutionOutcome` |
| `app.runtime.pubsub` | `ExecutionBus`, `bus` |
| `app.runtime.memory` | `MemoryStoreService` |
| `app.services.*` | see below |
| `app.api.deps` | `get_container`, `get_principal`, `require_org`, `CurrentPrincipal` |
| `app.container` | `Container` |

## Services

```
OrganizationService(store, audit)
  create(principal, payload) -> Organization
  list_for_user(user_id) -> list[OrgSummary]
  get(org_id) -> Organization
  update(principal, org_id, patch) -> Organization
  require_role(org_id, user_id, minimum: OrgRole) -> Member
  members(org_id) -> list[MemberWithUser]
  invite(principal, org_id, payload) -> MemberWithUser
  update_member(principal, org_id, user_id, patch) -> MemberWithUser
  remove_member(principal, org_id, user_id) -> None

TeamService(store, audit)
  create(principal, org_id, payload) -> Team
  list(org_id) -> list[Team]
  get(org_id, team_id) -> Team
  update(principal, org_id, team_id, patch) -> Team
  delete(principal, org_id, team_id) -> None
  members(org_id, team_id) -> list[MemberWithUser]

ButtlrService(store, audit, registry, router, bus, runner)
  create(principal, org_id, payload) -> Buttlr
  list(org_id, team_id=None, status=None, q=None) -> list[Buttlr]
  get(org_id, buttlr_id) -> Buttlr
  update(principal, org_id, buttlr_id, patch) -> Buttlr
  delete(principal, org_id, buttlr_id) -> None
  deploy(principal, org_id, buttlr_id) -> Buttlr
  pause(principal, org_id, buttlr_id) -> Buttlr
  run(principal, org_id, buttlr_id, request) -> Execution
  draft(principal, org_id, request) -> ButtlrDraftResponse
  refine(principal, org_id, request) -> ButtlrDraftResponse

ExecutionService(store, audit, bus)
  create(org_id, buttlr, trigger, goal, requested_by, dry_run) -> Execution
  get(org_id, execution_id) -> Execution
  list(org_id, buttlr_id=None, status=None, limit=50, offset=0) -> Page[ExecutionSummary]
  append_step(...) -> Execution
  finish(execution, status, output=None, error=None) -> Execution
  cancel(org_id, execution_id) -> Execution

ApprovalService(store, audit, notifications)
  create(...) -> Approval
  get(org_id, approval_id) -> Approval
  list(org_id, status=None, limit, offset) -> Page[Approval]
  pending_for_org(org_id) -> int
  decide(principal, org_id, approval_id, granted: bool, note) -> Approval

AuditService(store)
  record(org_id, action, actor_type, actor_id, actor_name, summary, **targets) -> AuditLog
  list(org_id, limit, offset, action=None, buttlr_id=None) -> Page[AuditLog]

NotificationService(store)
  notify(org_id, kind, title, body="", link=None, user_id=None) -> Notification
  list(user, org_id, unread_only=False, limit) -> list[Notification]
  mark_read(user, org_id, notification_id) -> Notification
  unread_count(user, org_id) -> int

IntegrationService(store, audit, crypto)
  catalogue() -> list[IntegrationCatalogEntry]
  connect_token(principal, org_id, payload) -> IntegrationPublic
  connect_oauth_callback(org_id, provider, code, state) -> IntegrationPublic
  oauth_start(org_id, provider, redirect_uri) -> OAuthStartResponse
  list(org_id) -> list[IntegrationPublic]
  get(org_id, provider) -> Integration | None
  credentials_for(org_id, buttlr) -> dict[provider, dict]
  update_scopes(principal, org_id, integration_id, payload) -> IntegrationPublic
  disconnect(principal, org_id, integration_id) -> None
  refresh_resources(principal, org_id, integration_id) -> IntegrationPublic

AnalyticsService(store)
  overview(org_id, days=30) -> AnalyticsOverview
  dashboard(principal, org_id) -> DashboardOverview
```

## HTTP surface (`/api/v1`)

```
GET    /health
GET    /meta/config                      -> feature flags for the UI
POST   /auth/dev/login                   -> TokenResponse
GET    /auth/session                     -> SessionContext
GET    /users/me                         -> User
PATCH  /users/me                         -> User

GET    /organizations                    -> list[OrgSummary]
POST   /organizations                    -> Organization
GET    /organizations/{org}              -> Organization
PATCH  /organizations/{org}              -> Organization
GET    /organizations/{org}/members      -> list[MemberWithUser]
POST   /organizations/{org}/members      -> MemberWithUser
PATCH  /organizations/{org}/members/{uid}-> MemberWithUser
DELETE /organizations/{org}/members/{uid}
GET    /organizations/{org}/teams        -> list[Team]
POST   /organizations/{org}/teams        -> Team
GET    /organizations/{org}/teams/{t}    -> Team
PATCH  /organizations/{org}/teams/{t}    -> Team
DELETE /organizations/{org}/teams/{t}
GET    /organizations/{org}/buttlrs      -> list[Buttlr]
POST   /organizations/{org}/buttlrs      -> Buttlr
POST   /organizations/{org}/buttlrs/draft   -> ButtlrDraftResponse
POST   /organizations/{org}/buttlrs/refine  -> ButtlrDraftResponse
GET    /organizations/{org}/buttlrs/{b}  -> Buttlr
PATCH  /organizations/{org}/buttlrs/{b}  -> Buttlr
DELETE /organizations/{org}/buttlrs/{b}
POST   /organizations/{org}/buttlrs/{b}/deploy  -> Buttlr
POST   /organizations/{org}/buttlrs/{b}/pause   -> Buttlr
POST   /organizations/{org}/buttlrs/{b}/run     -> Execution
POST   /organizations/{org}/buttlrs/{b}/chat    -> ChatResponse
GET    /organizations/{org}/buttlrs/{b}/conversations -> list[Conversation]
GET    /organizations/{org}/buttlrs/{b}/conversations/{c}/messages -> list[ChatMessage]
GET    /organizations/{org}/executions        -> Page[ExecutionSummary]
GET    /organizations/{org}/executions/{e}    -> Execution
POST   /organizations/{org}/executions/{e}/cancel -> Execution
GET    /organizations/{org}/executions/{e}/stream -> text/event-stream
GET    /organizations/{org}/approvals      -> Page[Approval]
GET    /organizations/{org}/approvals/stats-> ApprovalStats
POST   /organizations/{org}/approvals/{a}/approve -> Approval
POST   /organizations/{org}/approvals/{a}/reject  -> Approval
GET    /organizations/{org}/integrations          -> list[IntegrationPublic]
GET    /organizations/{org}/integrations/catalogue-> list[IntegrationCatalogEntry]
POST   /organizations/{org}/integrations/token    -> IntegrationPublic
GET    /organizations/{org}/integrations/{p}/oauth/start -> OAuthStartResponse
GET    /integrations/oauth/{p}/callback   -> RedirectResponse
PATCH  /organizations/{org}/integrations/{i}      -> IntegrationPublic
DELETE /organizations/{org}/integrations/{i}
POST   /organizations/{org}/integrations/{i}/refresh -> IntegrationPublic
GET    /organizations/{org}/audit          -> Page[AuditLog]
GET    /organizations/{org}/notifications  -> list[Notification]
POST   /organizations/{org}/notifications/{n}/read -> Notification
POST   /organizations/{org}/notifications/read-all -> Ack
GET    /organizations/{org}/analytics/overview -> AnalyticsOverview
GET    /organizations/{org}/dashboard      -> DashboardOverview
GET    /tools                              -> tool catalogue
POST   /dev/seed                           -> seeds the Acme Technologies demo
```

## Frontend contract

* Types in `src/types.ts` mirror the Pydantic schemas exactly (snake_case JSON kept as-is).
* All HTTP goes through `src/lib/api.ts`. No component calls `fetch` directly.
* Server state lives in TanStack Query (`src/lib/queries.ts`).
* Session state lives in `src/lib/auth.tsx` (React context).
* Theming uses CSS variables in `src/index.css`; never hard-code a colour in a component.
