/**
 * The single HTTP entry point. No component calls `fetch` directly.
 *
 * Every failure surfaces as an `ApiError` carrying the server's machine code and a
 * user-readable message, so screens can render something useful without inspecting status
 * codes themselves.
 */

import type {
  Ack,
  AnalyticsOverview,
  Approval,
  ApprovalStats,
  AuditLog,
  Buttlr,
  ButtlrCreate,
  ButtlrDraftRequest,
  ButtlrDraftResponse,
  ButtlrRefineRequest,
  ButtlrRunRequest,
  ButtlrUpdate,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  Conversation,
  DashboardOverview,
  Execution,
  ExecutionEvent,
  ExecutionSummary,
  HealthStatus,
  IntegrationCatalogEntry,
  IntegrationConnectToken,
  IntegrationPublic,
  IntegrationScopesUpdate,
  MemberInvite,
  MemberUpdate,
  MemberWithUser,
  MetaConfig,
  Notification,
  OAuthStartResponse,
  Organization,
  OrganizationCreate,
  OrganizationUpdate,
  OrgSummary,
  Page,
  SeedRequest,
  SeedResponse,
  SessionContext,
  Team,
  TeamCreate,
  TeamUpdate,
  ToolCatalogue,
  TokenResponse,
  User,
  UserUpdate,
} from "./types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

const TOKEN_KEY = "buttlr.token";
const ORG_KEY = "buttlr.activeOrg";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId?: string;

  constructor(
    message: string,
    options: { code?: string; status?: number; details?: Record<string, unknown>; requestId?: string } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code ?? "request_failed";
    this.status = options.status ?? 0;
    this.details = options.details ?? {};
    this.requestId = options.requestId;
  }

  get isUnauthorized() {
    return this.status === 401;
  }

  get isForbidden() {
    return this.status === 403;
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export const activeOrgStore = {
  get: () => localStorage.getItem(ORG_KEY),
  set: (id: string) => localStorage.setItem(ORG_KEY, id),
  clear: () => localStorage.removeItem(ORG_KEY),
};

function authHeaders(): Record<string, string> {
  const token = tokenStore.get();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function withQuery(path: string, query?: Record<string, unknown>): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  query?: Record<string, unknown>,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${withQuery(path, query)}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        ...authHeaders(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("We couldn't reach Buttlr. Check your connection and try again.", {
      code: "network_error",
    });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeJson(text) : undefined;

  if (!response.ok) {
    const error = (payload as { error?: Record<string, unknown> } | undefined)?.error ?? {};
    throw new ApiError(
      typeof error.message === "string" ? error.message : defaultMessageFor(response.status),
      {
        code: typeof error.code === "string" ? error.code : `http_${response.status}`,
        status: response.status,
        details: (error.details as Record<string, unknown>) ?? {},
        requestId: typeof error.request_id === "string" ? error.request_id : undefined,
      },
    );
  }
  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function defaultMessageFor(status: number): string {
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "You don't have permission to do that.";
  if (status === 404) return "We couldn't find what you were looking for.";
  if (status === 409) return "That action conflicts with the current state. Refresh and try again.";
  if (status === 422) return "Some of the information sent was not valid.";
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return "The request failed.";
}

/** Streams a Buttlr run. Returns an unsubscribe function. */
export function streamExecution(
  organizationId: string,
  executionId: string,
  onEvent: (event: ExecutionEvent) => void,
  onError?: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  const path = `${BASE_URL}/organizations/${organizationId}/executions/${executionId}/stream`;

  void (async () => {
    try {
      const response = await fetch(path, {
        headers: { Accept: "text/event-stream", ...authHeaders() },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new ApiError(defaultMessageFor(response.status), { status: response.status });
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((candidate) => candidate.startsWith("data: "));
          if (!line) continue;
          const parsed = safeJson(line.slice(6));
          if (parsed) onEvent(parsed as ExecutionEvent);
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      onError?.(error instanceof Error ? error : new Error(String(error)));
    }
  })();

  return () => controller.abort();
}

export const api = {
  meta: {
    config: () => request<MetaConfig>("GET", "/meta/config"),
    health: () => request<HealthStatus>("GET", "/health"),
  },
  auth: {
    devLogin: (email: string, display_name?: string) =>
      request<TokenResponse>("POST", "/auth/dev/login", { email, display_name }),
    session: () => request<SessionContext>("GET", "/auth/session"),
    me: () => request<User>("GET", "/users/me"),
    updateMe: (patch: UserUpdate) => request<User>("PATCH", "/users/me", patch),
  },
  organizations: {
    list: () => request<OrgSummary[]>("GET", "/organizations"),
    create: (payload: OrganizationCreate) => request<Organization>("POST", "/organizations", payload),
    get: (id: string) => request<Organization>("GET", `/organizations/${id}`),
    update: (id: string, patch: OrganizationUpdate) =>
      request<Organization>("PATCH", `/organizations/${id}`, patch),
    members: (id: string) => request<MemberWithUser[]>("GET", `/organizations/${id}/members`),
    invite: (id: string, payload: MemberInvite) =>
      request<MemberWithUser>("POST", `/organizations/${id}/members`, payload),
    updateMember: (id: string, userId: string, patch: MemberUpdate) =>
      request<MemberWithUser>("PATCH", `/organizations/${id}/members/${userId}`, patch),
    removeMember: (id: string, userId: string) =>
      request<void>("DELETE", `/organizations/${id}/members/${userId}`),
  },
  teams: {
    list: (orgId: string) => request<Team[]>("GET", `/organizations/${orgId}/teams`),
    create: (orgId: string, payload: TeamCreate) =>
      request<Team>("POST", `/organizations/${orgId}/teams`, payload),
    get: (orgId: string, teamId: string) =>
      request<Team>("GET", `/organizations/${orgId}/teams/${teamId}`),
    members: (orgId: string, teamId: string) =>
      request<MemberWithUser[]>("GET", `/organizations/${orgId}/teams/${teamId}/members`),
    update: (orgId: string, teamId: string, patch: TeamUpdate) =>
      request<Team>("PATCH", `/organizations/${orgId}/teams/${teamId}`, patch),
    remove: (orgId: string, teamId: string) =>
      request<void>("DELETE", `/organizations/${orgId}/teams/${teamId}`),
  },
  buttlrs: {
    list: (orgId: string, query?: { team_id?: string; status?: string; q?: string }) =>
      request<Buttlr[]>("GET", `/organizations/${orgId}/buttlrs`, undefined, query),
    create: (orgId: string, payload: ButtlrCreate) =>
      request<Buttlr>("POST", `/organizations/${orgId}/buttlrs`, payload),
    draft: (orgId: string, payload: ButtlrDraftRequest) =>
      request<ButtlrDraftResponse>("POST", `/organizations/${orgId}/buttlrs/draft`, payload),
    refine: (orgId: string, payload: ButtlrRefineRequest) =>
      request<ButtlrDraftResponse>("POST", `/organizations/${orgId}/buttlrs/refine`, payload),
    get: (orgId: string, id: string) => request<Buttlr>("GET", `/organizations/${orgId}/buttlrs/${id}`),
    update: (orgId: string, id: string, patch: ButtlrUpdate) =>
      request<Buttlr>("PATCH", `/organizations/${orgId}/buttlrs/${id}`, patch),
    remove: (orgId: string, id: string) =>
      request<void>("DELETE", `/organizations/${orgId}/buttlrs/${id}`),
    deploy: (orgId: string, id: string) =>
      request<Buttlr>("POST", `/organizations/${orgId}/buttlrs/${id}/deploy`),
    pause: (orgId: string, id: string) =>
      request<Buttlr>("POST", `/organizations/${orgId}/buttlrs/${id}/pause`),
    run: (orgId: string, id: string, payload: ButtlrRunRequest = {}) =>
      request<Execution>("POST", `/organizations/${orgId}/buttlrs/${id}/run`, payload),
    chat: (orgId: string, id: string, payload: ChatRequest) =>
      request<ChatResponse>("POST", `/organizations/${orgId}/buttlrs/${id}/chat`, payload),
    conversations: (orgId: string, id: string) =>
      request<Conversation[]>("GET", `/organizations/${orgId}/buttlrs/${id}/conversations`),
    messages: (orgId: string, id: string, conversationId: string) =>
      request<ChatMessage[]>(
        "GET",
        `/organizations/${orgId}/buttlrs/${id}/conversations/${conversationId}/messages`,
      ),
  },
  executions: {
    list: (orgId: string, query?: { buttlr_id?: string; status?: string; limit?: number; offset?: number }) =>
      request<Page<ExecutionSummary>>("GET", `/organizations/${orgId}/executions`, undefined, query),
    get: (orgId: string, id: string) =>
      request<Execution>("GET", `/organizations/${orgId}/executions/${id}`),
    cancel: (orgId: string, id: string) =>
      request<Execution>("POST", `/organizations/${orgId}/executions/${id}/cancel`),
  },
  approvals: {
    list: (orgId: string, query?: { status?: string; limit?: number; offset?: number }) =>
      request<Page<Approval>>("GET", `/organizations/${orgId}/approvals`, undefined, query),
    stats: (orgId: string) => request<ApprovalStats>("GET", `/organizations/${orgId}/approvals/stats`),
    approve: (orgId: string, id: string, note?: string) =>
      request<Approval>("POST", `/organizations/${orgId}/approvals/${id}/approve`, { note }),
    reject: (orgId: string, id: string, note?: string) =>
      request<Approval>("POST", `/organizations/${orgId}/approvals/${id}/reject`, { note }),
  },
  integrations: {
    list: (orgId: string) => request<IntegrationPublic[]>("GET", `/organizations/${orgId}/integrations`),
    catalogue: (orgId: string) =>
      request<IntegrationCatalogEntry[]>("GET", `/organizations/${orgId}/integrations/catalogue`),
    connectToken: (orgId: string, payload: IntegrationConnectToken) =>
      request<IntegrationPublic>("POST", `/organizations/${orgId}/integrations/token`, payload),
    oauthStart: (orgId: string, provider: string, redirectUri?: string) =>
      request<OAuthStartResponse>(
        "GET",
        `/organizations/${orgId}/integrations/${provider}/oauth/start`,
        undefined,
        { redirect_uri: redirectUri },
      ),
    updateScopes: (orgId: string, id: string, payload: IntegrationScopesUpdate) =>
      request<IntegrationPublic>("PATCH", `/organizations/${orgId}/integrations/${id}`, payload),
    disconnect: (orgId: string, id: string) =>
      request<void>("DELETE", `/organizations/${orgId}/integrations/${id}`),
    refresh: (orgId: string, id: string) =>
      request<IntegrationPublic>("POST", `/organizations/${orgId}/integrations/${id}/refresh`),
  },
  activity: {
    audit: (orgId: string, query?: { action?: string; buttlr_id?: string; limit?: number; offset?: number }) =>
      request<Page<AuditLog>>("GET", `/organizations/${orgId}/audit`, undefined, query),
    notifications: (orgId: string, query?: { unread_only?: boolean; limit?: number }) =>
      request<Notification[]>("GET", `/organizations/${orgId}/notifications`, undefined, query),
    markRead: (orgId: string, id: string) =>
      request<Notification>("POST", `/organizations/${orgId}/notifications/${id}/read`),
    markAllRead: (orgId: string) =>
      request<Ack>("POST", `/organizations/${orgId}/notifications/read-all`),
  },
  analytics: {
    overview: (orgId: string, days = 30) =>
      request<AnalyticsOverview>("GET", `/organizations/${orgId}/analytics/overview`, undefined, { days }),
    dashboard: (orgId: string) => request<DashboardOverview>("GET", `/organizations/${orgId}/dashboard`),
  },
  tools: {
    catalogue: () => request<ToolCatalogue>("GET", "/tools"),
  },
  dev: {
    seed: (payload: SeedRequest = {}) => request<SeedResponse>("POST", "/dev/seed", payload),
  },
};
