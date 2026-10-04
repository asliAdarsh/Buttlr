/**
 * Server state. Every read goes through TanStack Query; every write invalidates the keys it
 * affects so screens never show stale data after an action.
 */

import { useEffect, useRef, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api, streamExecution } from "./api";
import type {
  ButtlrCreate,
  ButtlrDraftRequest,
  ButtlrRefineRequest,
  ButtlrRunRequest,
  ButtlrUpdate,
  ChatRequest,
  Execution,
  ExecutionEvent,
  IntegrationConnectToken,
  IntegrationScopesUpdate,
  MemberInvite,
  MemberUpdate,
  OrganizationCreate,
  OrganizationUpdate,
  SeedRequest,
  TeamCreate,
  TeamUpdate,
  UserUpdate,
} from "./types";

export const keys = {
  meta: ["meta"] as const,
  session: ["session"] as const,
  organizations: ["organizations"] as const,
  organization: (id: string) => ["organization", id] as const,
  members: (id: string) => ["organization", id, "members"] as const,
  teams: (id: string) => ["organization", id, "teams"] as const,
  buttlrs: (id: string, filters?: Record<string, unknown>) =>
    ["organization", id, "buttlrs", filters ?? {}] as const,
  buttlr: (id: string, buttlrId: string) => ["organization", id, "buttlr", buttlrId] as const,
  executions: (id: string, filters?: Record<string, unknown>) =>
    ["organization", id, "executions", filters ?? {}] as const,
  execution: (id: string, executionId: string) =>
    ["organization", id, "execution", executionId] as const,
  conversations: (id: string, buttlrId: string) =>
    ["organization", id, "buttlr", buttlrId, "conversations"] as const,
  messages: (id: string, buttlrId: string, conversationId: string) =>
    ["organization", id, "buttlr", buttlrId, "conversation", conversationId, "messages"] as const,
  approvals: (id: string, filters?: Record<string, unknown>) =>
    ["organization", id, "approvals", filters ?? {}] as const,
  approvalStats: (id: string) => ["organization", id, "approvals", "stats"] as const,
  integrations: (id: string) => ["organization", id, "integrations"] as const,
  catalogue: (id: string) => ["organization", id, "integrations", "catalogue"] as const,
  audit: (id: string, filters?: Record<string, unknown>) =>
    ["organization", id, "audit", filters ?? {}] as const,
  notifications: (id: string, filters?: Record<string, unknown>) =>
    ["organization", id, "notifications", filters ?? {}] as const,
  dashboard: (id: string) => ["organization", id, "dashboard"] as const,
  analytics: (id: string, days: number) => ["organization", id, "analytics", days] as const,
  tools: ["tools"] as const,
};

function invalidateOrg(client: QueryClient, organizationId: string) {
  void client.invalidateQueries({ queryKey: ["organization", organizationId] });
  void client.invalidateQueries({ queryKey: keys.dashboard(organizationId) });
  void client.invalidateQueries({ queryKey: ["organizations"] });
}

/* ------------------------------- reads ---------------------------------- */

export const useMeta = () =>
  useQuery({ queryKey: keys.meta, queryFn: api.meta.config, staleTime: 5 * 60_000 });

export const useOrganizations = () =>
  useQuery({ queryKey: keys.organizations, queryFn: api.organizations.list });

export const useOrganization = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.organization(organizationId ?? "none"),
    queryFn: () => api.organizations.get(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useMembers = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.members(organizationId ?? "none"),
    queryFn: () => api.organizations.members(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useTeams = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.teams(organizationId ?? "none"),
    queryFn: () => api.teams.list(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useButtlrs = (
  organizationId: string | null,
  filters?: { team_id?: string; status?: string; q?: string },
) =>
  useQuery({
    queryKey: keys.buttlrs(organizationId ?? "none", filters),
    queryFn: () => api.buttlrs.list(organizationId as string, filters),
    enabled: Boolean(organizationId),
  });

export const useButtlr = (organizationId: string | null, buttlrId: string | null) =>
  useQuery({
    queryKey: keys.buttlr(organizationId ?? "none", buttlrId ?? "none"),
    queryFn: () => api.buttlrs.get(organizationId as string, buttlrId as string),
    enabled: Boolean(organizationId && buttlrId),
  });

export const useExecutions = (
  organizationId: string | null,
  filters?: { buttlr_id?: string; status?: string; limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: keys.executions(organizationId ?? "none", filters),
    queryFn: () => api.executions.list(organizationId as string, filters),
    enabled: Boolean(organizationId),
  });

export const useExecution = (organizationId: string | null, executionId: string | null) =>
  useQuery({
    queryKey: keys.execution(organizationId ?? "none", executionId ?? "none"),
    queryFn: () => api.executions.get(organizationId as string, executionId as string),
    enabled: Boolean(organizationId && executionId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" || status === "waiting_approval"
        ? 3000
        : false;
    },
  });

export const useApprovals = (
  organizationId: string | null,
  filters?: { status?: string; limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: keys.approvals(organizationId ?? "none", filters),
    queryFn: () => api.approvals.list(organizationId as string, filters),
    enabled: Boolean(organizationId),
  });

export const useApprovalStats = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.approvalStats(organizationId ?? "none"),
    queryFn: () => api.approvals.stats(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useIntegrations = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.integrations(organizationId ?? "none"),
    queryFn: () => api.integrations.list(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useIntegrationCatalogue = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.catalogue(organizationId ?? "none"),
    queryFn: () => api.integrations.catalogue(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useAudit = (
  organizationId: string | null,
  filters?: { action?: string; buttlr_id?: string; limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: keys.audit(organizationId ?? "none", filters),
    queryFn: () => api.activity.audit(organizationId as string, filters),
    enabled: Boolean(organizationId),
  });

export const useNotifications = (
  organizationId: string | null,
  filters?: { unread_only?: boolean; limit?: number },
) =>
  useQuery({
    queryKey: keys.notifications(organizationId ?? "none", filters),
    queryFn: () => api.activity.notifications(organizationId as string, filters),
    enabled: Boolean(organizationId),
    refetchInterval: 30_000,
  });

export const useDashboard = (organizationId: string | null) =>
  useQuery({
    queryKey: keys.dashboard(organizationId ?? "none"),
    queryFn: () => api.analytics.dashboard(organizationId as string),
    enabled: Boolean(organizationId),
  });

export const useAnalytics = (organizationId: string | null, days = 30) =>
  useQuery({
    queryKey: keys.analytics(organizationId ?? "none", days),
    queryFn: () => api.analytics.overview(organizationId as string, days),
    enabled: Boolean(organizationId),
  });

export const useTools = () =>
  useQuery({ queryKey: keys.tools, queryFn: api.tools.catalogue, staleTime: 10 * 60_000 });

export const useConversations = (organizationId: string | null, buttlrId: string | null) =>
  useQuery({
    queryKey: keys.conversations(organizationId ?? "none", buttlrId ?? "none"),
    queryFn: () => api.buttlrs.conversations(organizationId as string, buttlrId as string),
    enabled: Boolean(organizationId && buttlrId),
  });

export const useMessages = (
  organizationId: string | null,
  buttlrId: string | null,
  conversationId: string | null,
) =>
  useQuery({
    queryKey: keys.messages(organizationId ?? "none", buttlrId ?? "none", conversationId ?? "none"),
    queryFn: () =>
      api.buttlrs.messages(
        organizationId as string,
        buttlrId as string,
        conversationId as string,
      ),
    enabled: Boolean(organizationId && buttlrId && conversationId),
    refetchInterval: (query) => (query.state.data?.length ? 4000 : false),
  });

/* ------------------------------ mutations -------------------------------- */

export function useCreateOrganization() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrganizationCreate) => api.organizations.create(payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.organizations });
      void client.invalidateQueries({ queryKey: keys.session });
    },
  });
}

export function useUpdateOrganization(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: OrganizationUpdate) => api.organizations.update(organizationId, patch),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useInviteMember(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemberInvite) => api.organizations.invite(organizationId, payload),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useUpdateMember(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, patch }: { userId: string; patch: MemberUpdate }) =>
      api.organizations.updateMember(organizationId, userId, patch),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useRemoveMember(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.organizations.removeMember(organizationId, userId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useCreateTeam(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TeamCreate) => api.teams.create(organizationId, payload),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useUpdateTeam(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ teamId, patch }: { teamId: string; patch: TeamUpdate }) =>
      api.teams.update(organizationId, teamId, patch),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useDeleteTeam(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) => api.teams.remove(organizationId, teamId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useDraftButtlr(organizationId: string) {
  return useMutation({
    mutationFn: (payload: ButtlrDraftRequest) => api.buttlrs.draft(organizationId, payload),
  });
}

export function useRefineButtlr(organizationId: string) {
  return useMutation({
    mutationFn: (payload: ButtlrRefineRequest) => api.buttlrs.refine(organizationId, payload),
  });
}

export function useCreateButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: ButtlrCreate) => api.buttlrs.create(organizationId, payload),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useUpdateButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ buttlrId, patch }: { buttlrId: string; patch: ButtlrUpdate }) =>
      api.buttlrs.update(organizationId, buttlrId, patch),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useDeleteButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (buttlrId: string) => api.buttlrs.remove(organizationId, buttlrId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useDeployButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (buttlrId: string) => api.buttlrs.deploy(organizationId, buttlrId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function usePauseButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (buttlrId: string) => api.buttlrs.pause(organizationId, buttlrId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useRunButtlr(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ buttlrId, payload }: { buttlrId: string; payload?: ButtlrRunRequest }) =>
      api.buttlrs.run(organizationId, buttlrId, payload ?? {}),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useSendChat(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ buttlrId, payload }: { buttlrId: string; payload: ChatRequest }) =>
      api.buttlrs.chat(organizationId, buttlrId, payload),
    onSuccess: (response) => {
      void client.invalidateQueries({
        queryKey: keys.messages(organizationId, response.reply.buttlr_id, response.conversation_id),
      });
      void client.invalidateQueries({ queryKey: ["organization", organizationId] });
    },
  });
}

export function useDecideApproval(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, granted, note }: { approvalId: string; granted: boolean; note?: string }) =>
      granted
        ? api.approvals.approve(organizationId, approvalId, note)
        : api.approvals.reject(organizationId, approvalId, note),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useConnectToken(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: IntegrationConnectToken) =>
      api.integrations.connectToken(organizationId, payload),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useUpdateIntegrationScopes(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ integrationId, payload }: { integrationId: string; payload: IntegrationScopesUpdate }) =>
      api.integrations.updateScopes(organizationId, integrationId, payload),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useDisconnectIntegration(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (integrationId: string) => api.integrations.disconnect(organizationId, integrationId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useRefreshIntegration(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (integrationId: string) => api.integrations.refresh(organizationId, integrationId),
    onSuccess: () => invalidateOrg(client, organizationId),
  });
}

export function useMarkNotificationRead(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string) => api.activity.markRead(organizationId, notificationId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["organization", organizationId, "notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead(organizationId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.activity.markAllRead(organizationId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["organization", organizationId, "notifications"] });
    },
  });
}

export function useUpdateMe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: UserUpdate) => api.auth.updateMe(patch),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.session }),
  });
}

export function useSeedDemo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: SeedRequest) => api.dev.seed(payload),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.organizations });
      void client.invalidateQueries({ queryKey: keys.session });
    },
  });
}

/* --------------------------- live executions ----------------------------- */

export interface LiveExecution {
  execution: Execution | null;
  events: ExecutionEvent[];
  isStreaming: boolean;
}

/** Subscribes to a run's SSE stream and keeps the execution fresh from the store. */
export function useExecutionStream(
  organizationId: string | null,
  executionId: string | null,
  seed?: Execution | null,
): LiveExecution {
  const [execution, setExecution] = useState<Execution | null>(seed ?? null);
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const seedId = useRef<string | null>(null);

  useEffect(() => {
    if (seed && seed.id !== seedId.current) {
      seedId.current = seed.id;
      setExecution(seed);
      setEvents([]);
    }
  }, [seed]);

  useEffect(() => {
    if (!organizationId || !executionId) return;
    setIsStreaming(true);
    let cancelled = false;

    const refresh = async () => {
      try {
        const fresh = await api.executions.get(organizationId, executionId);
        if (!cancelled) setExecution(fresh);
      } catch {
        /* the list view will report the failure */
      }
    };

    void refresh();
    const stop = streamExecution(
      organizationId,
      executionId,
      (event) => {
        setEvents((current) => [...current, event]);
        if (event.step) {
          setExecution((current) => {
            if (!current) return current;
            const steps = [...current.steps];
            steps[event.step!.index] = event.step!;
            return { ...current, steps };
          });
        }
        if (event.event === "status" || event.event === "done") void refresh();
        if (event.event === "done") setIsStreaming(false);
      },
      () => setIsStreaming(false),
    );

    return () => {
      cancelled = true;
      stop();
      setIsStreaming(false);
    };
  }, [organizationId, executionId]);

  return { execution, events, isStreaming };
}
