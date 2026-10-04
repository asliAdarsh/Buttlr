/**
 * Mirrors the Pydantic schemas in `backend/app/schemas` one-for-one. JSON stays snake_case.
 */

export type OrgRole = "owner" | "admin" | "member";

export type Permission = "view" | "ask" | "approve" | "execute" | "configure" | "admin";

export type GrantSubject = "everyone" | "role" | "team" | "user";

export type ButtlrStatus = "draft" | "active" | "paused" | "disabled";

export type ModelProviderKind = "openai" | "anthropic" | "google" | "ollama" | "heuristic";

export type ScheduleKind =
  | "manual"
  | "once"
  | "interval"
  | "hourly"
  | "daily"
  | "weekly"
  | "monthly"
  | "cron";

export type ApprovalMode = "auto" | "ask" | "deny";

export type RiskLevel = "low" | "medium" | "high" | "critical";

export type Decision = "allow" | "deny" | "request_approval";

export type ExecutionStatus =
  | "queued"
  | "running"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type ExecutionTrigger =
  | "schedule"
  | "manual"
  | "chat"
  | "test"
  | "webhook"
  | "event"
  | "approval_resume";

export type StepType =
  | "status"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "approval_request"
  | "approval_result"
  | "message"
  | "error";

export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped" | "blocked";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired" | "cancelled";

export type IntegrationProvider = "github" | "google" | "jira";

export type IntegrationScope = "organization" | "personal";

export type IntegrationStatus = "connected" | "disconnected" | "error" | "expired";

export type AuditAction = string;

export type NotificationKind =
  | "approval_required"
  | "approval_decided"
  | "execution_completed"
  | "execution_failed"
  | "integration_error"
  | "member_added"
  | "system";

export type ActorType = "user" | "buttlr" | "system";

export type ChatRole = "user" | "assistant" | "system";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Ack {
  ok: boolean;
  message?: string | null;
}

export interface UserPreferences {
  theme: string;
  accent: string;
  density: string;
  email_notifications: boolean;
  in_app_notifications: boolean;
  notify_on_approval: boolean;
  notify_on_completion: boolean;
  notify_on_failure: boolean;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  photo_url?: string | null;
  title?: string | null;
  default_organization_id?: string | null;
  preferences: UserPreferences;
  created_at: string;
  updated_at: string;
  last_seen_at?: string | null;
}

export interface UserUpdate {
  display_name?: string | null;
  photo_url?: string | null;
  title?: string | null;
  default_organization_id?: string | null;
  preferences?: UserPreferences | null;
}

export interface OrganizationSettings {
  default_model: string;
  allow_local_models: boolean;
  require_approval_for_high_risk: boolean;
  data_retention_days: number;
  log_retention_days: number;
  audit_enabled: boolean;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  logo_emoji: string;
  owner_id: string;
  settings: OrganizationSettings;
  created_at: string;
  updated_at: string;
}

export interface OrganizationCreate {
  name: string;
  description?: string | null;
  logo_emoji?: string;
}

export interface OrganizationUpdate {
  name?: string | null;
  description?: string | null;
  logo_emoji?: string | null;
  settings?: OrganizationSettings | null;
}

export interface Member {
  user_id: string;
  organization_id: string;
  role: OrgRole;
  team_ids: string[];
  invited_by?: string | null;
  joined_at: string;
}

export interface MemberWithUser extends Member {
  user?: User | null;
}

export interface MemberInvite {
  email: string;
  role?: OrgRole;
  team_ids?: string[];
}

export interface MemberUpdate {
  role?: OrgRole | null;
  team_ids?: string[] | null;
}

export interface Team {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  emoji: string;
  color: string;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  member_ids?: string[];
}

export interface TeamCreate {
  name: string;
  description?: string | null;
  emoji?: string;
  color?: string;
  member_ids?: string[];
}

export interface TeamUpdate {
  name?: string | null;
  description?: string | null;
  emoji?: string | null;
  color?: string | null;
  member_ids?: string[] | null;
}

export interface OrgSummary {
  organization: Organization;
  role: OrgRole;
  member_count: number;
  team_count: number;
  buttlr_count: number;
  active_buttlr_count: number;
  pending_approval_count: number;
}

export interface Principal {
  user_id: string;
  email: string;
  display_name: string;
  photo_url?: string | null;
  organization_id?: string | null;
  role?: OrgRole | null;
  team_ids: string[];
  is_dev: boolean;
}

export interface SessionContext {
  user: User;
  organizations: Organization[];
  active_organization_id?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ModelConfig {
  provider: string;
  name: string;
  temperature: number;
  max_tokens: number;
  fallback: string[];
}

export interface Schedule {
  enabled: boolean;
  kind: ScheduleKind;
  timezone: string;
  at?: string | null;
  day_of_week?: string | null;
  day_of_month?: number | null;
  interval_minutes?: number | null;
  run_at?: string | null;
  cron?: string | null;
  business_hours_only: boolean;
}

export interface ApprovalRule {
  tool: string;
  mode: ApprovalMode;
  approver_roles: string[];
}

export interface ApprovalPolicy {
  default_mode: ApprovalMode;
  rules: ApprovalRule[];
  require_for_risk: RiskLevel;
  approver_permission: Permission;
  expiry_minutes?: number | null;
}

export interface PermissionGrant {
  subject_type: GrantSubject;
  subject: string;
  permission: Permission;
}

export interface KnowledgeSource {
  id: string;
  kind: string;
  name: string;
  location: string;
  created_at: string;
}

export interface ButtlrStats {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  last_run_at?: string | null;
  last_status?: ExecutionStatus | null;
  last_duration_ms?: number | null;
  pending_approvals: number;
  estimated_minutes_saved: number;
}

export interface Buttlr {
  id: string;
  organization_id: string;
  team_id?: string | null;
  name: string;
  avatar: string;
  role: string;
  department?: string | null;
  description: string;
  objective: string;
  responsibilities: string[];
  instructions: string;
  model: ModelConfig;
  tools: string[];
  integrations: string[];
  scope: Record<string, unknown>;
  knowledge: KnowledgeSource[];
  schedule: Schedule;
  status: ButtlrStatus;
  approval_policy: ApprovalPolicy;
  permissions: PermissionGrant[];
  memory_enabled: boolean;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
  deployed_at?: string | null;
  stats: ButtlrStats;
}

export interface ButtlrCreate {
  name: string;
  avatar?: string;
  role?: string;
  team_id?: string | null;
  department?: string | null;
  description?: string;
  objective?: string;
  responsibilities?: string[];
  instructions?: string;
  model?: ModelConfig | null;
  tools?: string[];
  integrations?: string[];
  scope?: Record<string, unknown>;
  schedule?: Schedule | null;
  approval_policy?: ApprovalPolicy | null;
  permissions?: PermissionGrant[];
  memory_enabled?: boolean;
  status?: ButtlrStatus;
}

export interface ButtlrUpdate extends Partial<Omit<ButtlrCreate, "status">> {
  status?: ButtlrStatus | null;
}

export interface ButtlrDraftRequest {
  prompt: string;
  organization_id: string;
  team_id?: string | null;
}

export interface ButtlrRefineRequest {
  instruction: string;
  current: ButtlrCreate;
}

export interface ButtlrDraftResponse {
  draft: ButtlrCreate;
  rationale: string;
  assumptions: string[];
  missing: string[];
  provider: string;
  model: string;
}

export interface ButtlrRunRequest {
  input?: string | null;
  dry_run?: boolean;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  calls: number;
}

export interface ExecutionStep {
  index: number;
  type: StepType;
  title: string;
  status: StepStatus;
  detail?: string | null;
  tool?: string | null;
  params?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  approval_id?: string | null;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
}

export interface Execution {
  id: string;
  organization_id: string;
  buttlr_id: string;
  buttlr_name: string;
  conversation_id?: string | null;
  trigger: ExecutionTrigger;
  trigger_detail?: string | null;
  status: ExecutionStatus;
  goal: string;
  steps: ExecutionStep[];
  output?: string | null;
  error?: string | null;
  model?: string | null;
  provider?: string | null;
  usage: Usage;
  requested_by?: string | null;
  dry_run: boolean;
  pending_approval_id?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
}

export interface ExecutionSummary {
  id: string;
  organization_id: string;
  buttlr_id: string;
  buttlr_name: string;
  trigger: ExecutionTrigger;
  status: ExecutionStatus;
  goal: string;
  output?: string | null;
  error?: string | null;
  step_count: number;
  usage: Usage;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
}

export interface ExecutionEvent {
  execution_id: string;
  event: string;
  step?: ExecutionStep | null;
  status?: ExecutionStatus | null;
  output?: string | null;
  error?: string | null;
  at: string;
}

export interface Approval {
  id: string;
  organization_id: string;
  buttlr_id: string;
  buttlr_name: string;
  execution_id: string;
  step_index: number;
  tool: string;
  action: string;
  resource?: string | null;
  reason: string;
  risk: RiskLevel;
  params: Record<string, unknown>;
  status: ApprovalStatus;
  requested_at: string;
  expires_at?: string | null;
  decided_by?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
}

export interface ApprovalStats {
  pending: number;
  approved: number;
  rejected: number;
  expired: number;
}

export interface AuditLog {
  id: string;
  organization_id: string;
  action: AuditAction;
  actor_type: ActorType;
  actor_id?: string | null;
  actor_name?: string | null;
  summary: string;
  target_type?: string | null;
  target_id?: string | null;
  buttlr_id?: string | null;
  execution_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Notification {
  id: string;
  organization_id: string;
  user_id?: string | null;
  kind: NotificationKind;
  title: string;
  body: string;
  link?: string | null;
  read: boolean;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  organization_id: string;
  buttlr_id: string;
  conversation_id: string;
  role: ChatRole;
  content: string;
  execution_id?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  dry_run?: boolean;
}

export interface ChatResponse {
  conversation_id: string;
  reply: ChatMessage;
  execution_id?: string | null;
  pending_approval_id?: string | null;
}

export interface Conversation {
  id: string;
  organization_id: string;
  buttlr_id: string;
  title: string;
  created_by?: string | null;
  message_count: number;
  updated_at: string;
  created_at: string;
}

export interface IntegrationResource {
  id: string;
  name: string;
  kind: string;
  selected: boolean;
  meta: Record<string, unknown>;
}

export interface IntegrationPublic {
  id: string;
  organization_id: string;
  provider: IntegrationProvider;
  display_name: string;
  scope: IntegrationScope;
  owner_id?: string | null;
  owner_name?: string | null;
  status: IntegrationStatus;
  account?: string | null;
  scopes: string[];
  resources: IntegrationResource[];
  error?: string | null;
  created_at: string;
  updated_at: string;
  last_used_at?: string | null;
}

export interface IntegrationConnectToken {
  provider: IntegrationProvider;
  token: string;
  scope?: IntegrationScope;
  account?: string | null;
  base_url?: string | null;
  email?: string | null;
  label?: string | null;
}

export interface OAuthClientPublic {
  provider: IntegrationProvider;
  configured: boolean;
  client_id?: string | null;
  masked_client_id?: string | null;
  has_secret: boolean;
  source?: string | null;
  redirect_uri?: string | null;
}

export interface OAuthClientUpdate {
  client_id: string;
  client_secret?: string | null;
}

export interface ModelProviderEntry {
  provider: string;
  name: string;
  kind: "cloud" | "local" | "builtin" | string;
  description: string;
  configured: boolean;
  source?: "workspace" | "deployment" | null;
  model?: string | null;
  base_url?: string | null;
  requires_key: boolean;
  requires_base_url: boolean;
  docs_url?: string | null;
  note: string;
}

export interface ModelProviderUpdate {
  api_key?: string | null;
  base_url?: string | null;
  model?: string | null;
}

export interface IntegrationScopesUpdate {
  resource_ids: string[];
}

export interface IntegrationCatalogEntry {
  provider: IntegrationProvider;
  name: string;
  description: string;
  category: string;
  logo: string;
  auth_kind: string;
  available: boolean;
  coming_soon: boolean;
  tools: string[];
}

export interface OAuthStartResponse {
  authorization_url: string;
  state: string;
}

export interface ToolDescription {
  name: string;
  description: string;
  integration?: string | null;
  required_permission: Permission;
  risk: RiskLevel;
  read_only: boolean;
  parameters: Record<string, unknown>;
}

export interface ToolCatalogue {
  tools: ToolDescription[];
  integrations: string[];
  total: number;
}

export interface TimeBucket {
  label: string;
  date: string;
  total: number;
  completed: number;
  failed: number;
}

export interface ModelUsageBreakdown {
  provider: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface ToolUsageBreakdown {
  tool: string;
  calls: number;
  failures: number;
}

export interface AnalyticsOverview {
  executions_total: number;
  executions_completed: number;
  executions_failed: number;
  success_rate: number;
  avg_duration_ms: number;
  total_tokens: number;
  estimated_cost_usd: number;
  approvals_pending: number;
  approvals_approved: number;
  approvals_rejected: number;
  avg_approval_minutes: number;
  estimated_minutes_saved: number;
  timeline: TimeBucket[];
  by_model: ModelUsageBreakdown[];
  by_tool: ToolUsageBreakdown[];
}

export interface DashboardOverview {
  organization: Organization;
  buttlrs_total: number;
  buttlrs_active: number;
  buttlrs_running: number;
  teams_total: number;
  members_total: number;
  integrations_connected: number;
  integrations_total: number;
  approvals_pending: number;
  executions_today: number;
  executions_failed_today: number;
  estimated_minutes_saved: number;
  recent_executions: ExecutionSummary[];
  recent_audit: AuditLog[];
  buttlrs: Buttlr[];
}

export interface MetaConfig {
  app_name: string;
  version: string;
  environment: string;
  auth_mode: string;
  dev_login_enabled: boolean;
  store_backend: string;
  scheduler_enabled: boolean;
  providers: string[];
  github_oauth_enabled: boolean;
  google_oauth_enabled: boolean;
  demo_seed_enabled: boolean;
  default_timezone: string;
}

export interface HealthStatus {
  status: string;
  name: string;
  version: string;
  store: string;
  store_healthy: boolean;
  scheduler: boolean;
  running_executions: number;
}

export interface SeedRequest {
  email?: string | null;
  display_name?: string | null;
  github_token?: string | null;
  reset?: boolean;
}

export interface SeedResponse {
  user_id: string;
  organization_id: string;
  team_id: string;
  buttlr_id: string;
  lead_email: string;
  github_connected: boolean;
  deployed: boolean;
  created: boolean;
}
