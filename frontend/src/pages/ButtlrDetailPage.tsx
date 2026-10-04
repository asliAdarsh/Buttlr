import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CircleSlash,
  Loader2,
  MessageSquare,
  Pause,
  Play,
  Send,
  ShieldCheck,
  Trash2,
  TrendingUp,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import { SectionCard } from "@/components/common/SectionCard";
import { Field } from "@/components/common/Field";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { StatusPill } from "@/components/common/StatusPill";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ButtlrAvatar } from "@/components/buttlr/ButtlrAvatar";
import { ApiError } from "@/lib/api";
import { ScheduleBadge } from "@/components/buttlr/ScheduleBadge";
import { ExecutionTimeline } from "@/components/buttlr/ExecutionTimeline";
import { ToolPicker, describeApps, resolveToolChoices } from "@/components/buttlr/ToolPicker";
import { ScopeEditor } from "@/components/buttlr/ScopeEditor";
import { ModelPicker } from "@/components/buttlr/ModelPicker";
import { PermissionMatrix } from "@/components/buttlr/PermissionMatrix";
import {
  ScheduleEditor,
  normalizeModel,
  normalizePolicy,
  normalizeSchedule,
} from "@/pages/ButtlrNewPage";
import { useAuth } from "@/lib/auth";
import {
  useAvailableModelProviders,
  useApprovals,
  useButtlr,
  useConversations,
  useDeleteButtlr,
  useDeployButtlr,
  useExecution,
  useExecutionStream,
  useExecutions,
  useIntegrationCatalogue,
  useIntegrations,
  useMembers,
  useMessages,
  useMeta,
  usePauseButtlr,
  useRunButtlr,
  useSendChat,
  useTeams,
  useTools,
  useUpdateButtlr,
} from "@/lib/queries";
import { RISK_LEVELS } from "@/lib/constants";
import {
  formatDuration,
  formatRelative,
  formatTokens,
  humanize,
  toolLabel,
} from "@/lib/format";
import type {
  ApprovalMode,
  ApprovalPolicy,
  ButtlrUpdate,
  ModelConfig,
  RiskLevel,
  Schedule,
} from "@/lib/types";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "chat", label: "Chat" },
  { value: "runs", label: "Runs" },
  { value: "configuration", label: "Configuration" },
  { value: "permissions", label: "Permissions" },
] as const;

type TabValue = (typeof TABS)[number]["value"];

const RUNS_PER_PAGE = 20;
const LIVE_STATUSES = new Set(["queued", "running", "waiting_approval"]);

const MODE_OPTIONS: { value: ApprovalMode; label: string }[] = [
  { value: "auto", label: "Run without asking" },
  { value: "ask", label: "Ask someone first" },
  { value: "deny", label: "Never allow" },
];

/* ------------------------------------------------------------------ overview */

function StatCards({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const buttlr = useButtlr(organizationId, buttlrId);
  const stats = buttlr.data?.stats;
  const finished = (stats?.successful_runs ?? 0) + (stats?.failed_runs ?? 0);
  const successRate = finished === 0 ? null : Math.round(((stats?.successful_runs ?? 0) / finished) * 100);

  return (
    <section aria-label="Performance" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard
        label="Total runs"
        value={buttlr.isLoading ? "—" : (stats?.total_runs ?? 0)}
        icon={Play}
        loading={buttlr.isLoading}
      />
      <StatCard
        label="Success rate"
        value={buttlr.isLoading ? "—" : successRate === null ? "No finished runs" : `${successRate}%`}
        hint={successRate === null ? undefined : `${stats?.failed_runs ?? 0} failed`}
        icon={TrendingUp}
        tone={successRate === null || successRate >= 90 ? "success" : "warning"}
        loading={buttlr.isLoading}
      />
      <StatCard
        label="Last run"
        value={
          buttlr.isLoading
            ? "—"
            : stats?.last_run_at
              ? formatRelative(stats.last_run_at)
              : "Never run"
        }
        hint={stats?.last_status ? humanize(stats.last_status) : undefined}
        loading={buttlr.isLoading}
      />
      <StatCard
        label="Pending approvals"
        value={buttlr.isLoading ? "—" : (stats?.pending_approvals ?? 0)}
        hint={stats?.pending_approvals ? "Waiting for a decision" : "Nothing waiting"}
        icon={ShieldCheck}
        tone={stats?.pending_approvals ? "warning" : "default"}
        loading={buttlr.isLoading}
      />
      <StatCard
        label="Time saved"
        value={buttlr.isLoading ? "—" : formatMinutes(stats?.estimated_minutes_saved ?? 0)}
        hint="Estimated against manual handling"
        loading={buttlr.isLoading}
      />
    </section>
  );
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} h`;
}

function LatestExecution({ executionId }: { executionId: string | undefined }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const query = useExecution(organizationId, executionId ?? null);
  const streaming = useExecutionStream(
    organizationId,
    executionId ?? null,
    query.data,
  );
  const execution = streaming.execution ?? query.data;

  if (!executionId) {
    return (
      <EmptyState
        icon={CircleSlash}
        title="No runs yet"
        description="Start a test run or a real run and the full timeline appears here."
      />
    );
  }

  if (query.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!execution) {
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }

  return <ExecutionTimeline execution={execution} live={streaming.isStreaming} />;
}

/* ------------------------------------------------------------------ chat */

function ChatPanel({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const navigate = useNavigate();

  const conversations = useConversations(organizationId, buttlrId);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [startingFresh, setStartingFresh] = useState(false);
  const sendChat = useSendChat(organizationId ?? "");
  const [draftMessage, setDraftMessage] = useState("");
  const [liveExecutionId, setLiveExecutionId] = useState<string | null>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const list = conversations.data ?? [];

  // A fresh conversation is selected deliberately, so the newest thread stays open otherwise.
  const active = startingFresh ? null : (conversationId ?? list[0]?.id ?? null);
  const live = useExecutionStream(organizationId, liveExecutionId, null);
  const messages = useMessages(organizationId, buttlrId, active);

  const choose = (id: string | null) => {
    setStartingFresh(id === null);
    setConversationId(id);
  };

  const send = async () => {
    const text = draftMessage.trim();
    if (text.length === 0) return;
    try {
      const response = await sendChat.mutateAsync({
        buttlrId,
        payload: { message: text, conversation_id: active },
      });
      choose(response.conversation_id);
      setDraftMessage("");
      setLiveExecutionId(response.execution_id ?? null);
      setPendingApprovalId(response.pending_approval_id ?? null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The message could not be sent.");
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
      <div className="lg:hidden">
        <Field label="Conversation" htmlFor="chat-conversation">
          <Select
            value={active ?? "__new__"}
            onValueChange={(value) => choose(value === "__new__" ? null : value)}
            placeholder="New conversation"
            options={[
              { value: "__new__", label: "Start a new conversation" },
              ...list.map((conversation) => ({
                value: conversation.id,
                label: `${conversation.title} · ${conversation.message_count}`,
              })),
            ]}
          />
        </Field>
        <p className="mt-2 text-xs text-muted-foreground">
          Choosing “Start a new conversation” clears the current thread.
        </p>
      </div>

      <div className="hidden lg:block">
        <SectionCard
          title="Conversations"
          actions={
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => choose(null)}
              disabled={startingFresh}
            >
              New
            </Button>
          }
        >
          {list.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No conversations yet. Send a message to start one.
            </p>
          ) : (
            <ul className="space-y-1">
              {list.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    aria-current={conversation.id === active ? "true" : undefined}
                    onClick={() => choose(conversation.id)}
                    className={
                      conversation.id === active
                        ? "w-full rounded-md bg-accent px-3 py-2 text-left text-sm text-accent-foreground"
                        : "w-full rounded-md px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                    }
                  >
                    <span className="block truncate font-medium text-foreground">
                      {conversation.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {conversation.message_count} messages ·{" "}
                      {formatRelative(conversation.updated_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <div className="flex min-w-0 flex-col gap-3">
        <div className="min-h-[16rem] space-y-3 rounded-md border border-border p-3">
          {messages.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-2/3" />
              <Skeleton className="h-12 w-3/4" />
            </div>
          ) : messages.isError ? (
            <ErrorState error={messages.error} onRetry={() => void messages.refetch()} />
          ) : (messages.data ?? []).length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Ask this Buttlr a question about its work. It answers from the accounts and scope it
              has.
            </p>
          ) : (
            (messages.data ?? []).map((message) => (
              <div
                key={message.id}
                className={
                  message.role === "user"
                    ? "ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                    : "mr-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground"
                }
              >
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
                <p
                  className={
                    message.role === "user"
                      ? "mt-1 text-[0.7rem] text-primary-foreground/70"
                      : "mt-1 text-[0.7rem] text-muted-foreground"
                  }
                >
                  {message.role === "user" ? "You" : humanize(message.role)} ·{" "}
                  {formatRelative(message.created_at)}
                </p>
              </div>
            ))
          )}
        </div>

        {live.execution ? (
          <div className="rounded-md border border-border p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <StatusPill status={live.execution.status} size="sm" />
              {live.isStreaming ? (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
                  <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  Working
                </span>
              ) : null}
            </div>
            <ExecutionTimeline execution={live.execution} live={live.isStreaming} />
            {pendingApprovalId ? (
              <Alert tone="warning" title="Waiting for approval" className="mt-3">
                <span>
                  This run is paused until someone decides.{" "}
                  <button
                    type="button"
                    className="font-medium underline underline-offset-4"
                    onClick={() => navigate("/approvals")}
                  >
                    Open approvals
                  </button>
                  .
                </span>
              </Alert>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-2">
          <Field label="Message" htmlFor="chat-composer">
            <Textarea
              id="chat-composer"
              rows={3}
              value={draftMessage}
              onChange={(event) => setDraftMessage(event.target.value)}
              placeholder="Ask about the last run, or give it new work."
            />
          </Field>
          <Button
            type="button"
            onClick={() => void send()}
            loading={sendChat.isPending}
            disabled={draftMessage.trim().length === 0}
          >
            <Send aria-hidden="true" />
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ runs */

function RunsPanel({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const [page, setPage] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("execution");

  const runs = useExecutions(organizationId, {
    buttlr_id: buttlrId,
    limit: RUNS_PER_PAGE,
    offset: page * RUNS_PER_PAGE,
  });
  const selected = useExecution(organizationId, selectedId);
  const streaming = useExecutionStream(organizationId, selectedId, selected.data);
  const execution = streaming.execution ?? selected.data;

  const total = runs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / RUNS_PER_PAGE));

  const open = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", "runs");
    next.set("execution", id);
    setSearchParams(next);
  };

  const close = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("execution");
    setSearchParams(next, { replace: true });
  };

  return (
    <div className="space-y-4">
      <SectionCard
        title="Runs"
        description="Every time this Buttlr has been triggered. Open a run to read its steps."
      >
        {runs.isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </div>
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
        ) : (runs.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title="No runs yet"
            description="Use Run now from the header, or test the configuration before deploying."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Goal</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runs.data?.items ?? []).map((run) => (
                  <TableRow
                    key={run.id}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open run: ${run.goal}`}
                    onClick={() => open(run.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        open(run.id);
                      }
                    }}
                    className="cursor-pointer"
                  >
                    <TableCell>
                      <StatusPill status={run.status} size="sm" />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {humanize(run.trigger)}
                    </TableCell>
                    <TableCell className="max-w-xs truncate">{run.goal}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {run.duration_ms != null ? formatDuration(run.duration_ms) : "—"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {formatTokens(run.usage.total_tokens)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatRelative(run.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {pages > 1 ? (
          <div className="mt-4 flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => Math.max(0, current - 1))}
              disabled={page === 0}
            >
              <ArrowLeft aria-hidden="true" />
              Newer
            </Button>
            <span className="text-xs text-muted-foreground">
              Page {page + 1} of {pages}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => Math.min(pages - 1, current + 1))}
              disabled={page >= pages - 1}
            >
              Older
              <ArrowRight aria-hidden="true" />
            </Button>
          </div>
        ) : null}
      </SectionCard>

      <Dialog open={Boolean(selectedId)} onOpenChange={(next) => (next ? undefined : close())}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Run</DialogTitle>
            <DialogDescription>
              Every step this Buttlr took, in order.
            </DialogDescription>
          </DialogHeader>
          {selected.isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : selected.isError ? (
            <ErrorState error={selected.error} onRetry={() => void selected.refetch()} />
          ) : execution ? (
            <ExecutionTimeline
              execution={execution}
              live={
                streaming.isStreaming ||
                (selectedId !== null && LIVE_STATUSES.has(execution.status) && streaming.events.length > 0)
              }
            />
          ) : (
            <p className="text-sm text-muted-foreground">This run is no longer available.</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ configuration */

type Editable = {
  name: string;
  avatar: string;
  role: string;
  team_id: string | null;
  department: string | null;
  description: string;
  objective: string;
  responsibilities: string[];
  instructions: string;
  model: ModelConfig;
  schedule: Schedule;
  memory_enabled: boolean;
};

function ConfigurationPanel({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const buttlr = useButtlr(organizationId, buttlrId);
  const tools = useTools();
  const integrations = useIntegrations(organizationId);
  const catalogue = useIntegrationCatalogue(organizationId);
  const availableModels = useAvailableModelProviders(organizationId);
  const teams = useTeams(organizationId);
  const meta = useMeta();
  const updateButtlr = useUpdateButtlr(organizationId ?? "");

  const [form, setForm] = useState<Editable | null>(null);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [scope, setScope] = useState<Record<string, unknown>>({});
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const editsAreProtected = useRef(false);

  const source = buttlr.data;

  // Never clobber edits in progress: a background refetch (or the memory switch on
  // Overview) must not wipe what the user is typing.
  useEffect(() => {
    if (!source || editsAreProtected.current) return;
    setForm({
      name: source.name,
      avatar: source.avatar,
      role: source.role,
      team_id: source.team_id ?? null,
      department: source.department ?? null,
      description: source.description,
      objective: source.objective,
      responsibilities: [...source.responsibilities],
      instructions: source.instructions,
      model: normalizeModel(source.model),
      schedule: normalizeSchedule(source.schedule),
      memory_enabled: source.memory_enabled,
    });
    setSelectedTools([...source.tools]);
    setScope({ ...source.scope });
  }, [source]);

  const dirty = useMemo(() => {
    if (!form || !source) return false;
    return (
      form.name !== source.name ||
      form.avatar !== source.avatar ||
      form.role !== source.role ||
      form.team_id !== (source.team_id ?? null) ||
      form.department !== (source.department ?? null) ||
      form.description !== source.description ||
      form.objective !== source.objective ||
      form.responsibilities.join("\n") !== source.responsibilities.join("\n") ||
      form.instructions !== source.instructions ||
      form.model.provider !== source.model.provider ||
      form.model.name !== source.model.name ||
      form.model.temperature !== source.model.temperature ||
      form.model.max_tokens !== source.model.max_tokens ||
      JSON.stringify(form.schedule) !== JSON.stringify(normalizeSchedule(source.schedule)) ||
      form.memory_enabled !== source.memory_enabled ||
      selectedTools.join("\n") !== source.tools.join("\n") ||
      JSON.stringify(scope) !== JSON.stringify(source.scope)
    );
  }, [form, selectedTools, scope, source]);

  useEffect(() => {
    editsAreProtected.current = dirty;
  }, [dirty]);


  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // The deployment gate reads `integrations`, so a tool added here must bring its account with it.
  const providersForTools = useMemo(() => {
    const byName = new Map(
      (tools.data?.tools ?? [])
        .filter((tool) => tool.integration)
        .map((tool) => [tool.name, tool.integration as string]),
    );
    return (names: string[]) => [
      ...new Set(
        names.map((name) => byName.get(name)).filter((provider): provider is string => Boolean(provider)),
      ),
    ];
  }, [tools.data]);

  const apps = useMemo(
    () => describeApps(catalogue.data ?? [], integrations.data ?? []),
    [catalogue.data, integrations.data],
  );

  // Only the work a connected app can do is offered. Anything already selected from
  // an app with no connection stays visible so it can be seen and removed.
  const { available: availableTools, detached: detachedTools } = useMemo(
    () => resolveToolChoices(tools.data?.tools ?? [], apps, selectedTools),
    [tools.data, apps, selectedTools],
  );

  const appsAreLoading = tools.isLoading || integrations.isLoading || catalogue.isLoading;
  const modelProviderIds = useMemo(
    () => (availableModels.data ?? []).map((entry) => entry.provider),
    [availableModels.data],
  );

  if (buttlr.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (buttlr.isError) {
    return <ErrorState error={buttlr.error} onRetry={() => void buttlr.refetch()} />;
  }

  if (!form || !source) return null;

  const set = (partial: Partial<Editable>) => setForm({ ...form, ...partial });

  const save = async () => {
    if (form.name.trim().length < 2) {
      toast.error("The name needs at least two characters.");
      return;
    }
    try {
      const patch: ButtlrUpdate = {
        name: form.name.trim(),
        avatar: form.avatar,
        role: form.role,
        team_id: form.team_id,
        department: form.department,
        description: form.description,
        objective: form.objective,
        responsibilities: form.responsibilities.filter((item) => item.trim().length > 0),
        instructions: form.instructions,
        model: form.model,
        schedule: form.schedule,
        tools: selectedTools,
        integrations: providersForTools(selectedTools),
        scope,
        memory_enabled: form.memory_enabled,
      };
      await updateButtlr.mutateAsync({ buttlrId, patch });
      toast.success("Configuration saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The changes could not be saved.");
    }
  };
  const teamOptions = [
    { value: "", label: "No team" },
    ...(teams.data ?? []).map((team) => ({ value: team.id, label: `${team.emoji} ${team.name}` })),
  ];

  return (
    <div className="space-y-6">
      <SectionCard
        title="Configuration"
        description="Everything the runtime reads when this Buttlr runs."
        actions={
          <Button
            type="button"
            size="sm"
            onClick={() => void save()}
            loading={updateButtlr.isPending}
            disabled={!dirty}
          >
            Save changes
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="cfg-name" required>
            <Input
              id="cfg-name"
              value={form.name}
              maxLength={80}
              onChange={(event) => set({ name: event.target.value })}
            />
          </Field>
          <Field label="Role" htmlFor="cfg-role">
            <Input
              id="cfg-role"
              value={form.role}
              onChange={(event) => set({ role: event.target.value })}
            />
          </Field>
          <Field label="Team" htmlFor="cfg-team">
            <Select
              id="cfg-team"
              value={form.team_id ?? ""}
              onValueChange={(value) => set({ team_id: value || null })}
              options={teamOptions}
            />
          </Field>
          <Field label="Department" htmlFor="cfg-department">
            <Input
              id="cfg-department"
              value={form.department ?? ""}
              onChange={(event) => set({ department: event.target.value || null })}
            />
          </Field>
          <Field label="Description" htmlFor="cfg-description" className="sm:col-span-2">
            <Textarea
              id="cfg-description"
              rows={2}
              value={form.description}
              onChange={(event) => set({ description: event.target.value })}
            />
          </Field>
          <Field label="Objective" htmlFor="cfg-objective" className="sm:col-span-2">
            <Textarea
              id="cfg-objective"
              rows={2}
              value={form.objective}
              onChange={(event) => set({ objective: event.target.value })}
            />
          </Field>
          <Field
            label="Responsibilities"
            htmlFor="cfg-responsibility"
            className="sm:col-span-2"
            hint="One duty per line. Empty lines are dropped when you save."
          >
            <Textarea
              id="cfg-responsibility"
              rows={4}
              value={form.responsibilities.join("\n")}
              onChange={(event) =>
                set({ responsibilities: event.target.value.split("\n").map((line) => line.trim()) })
              }
            />
          </Field>
          <Field
            label="Instructions"
            htmlFor="cfg-instructions"
            className="sm:col-span-2"
            hint="The standing brief it works from on every run."
          >
            <Textarea
              id="cfg-instructions"
              rows={8}
              value={form.instructions}
              onChange={(event) => set({ instructions: event.target.value })}
            />
          </Field>
          <div className="flex items-start justify-between gap-4 rounded-md border border-border p-3 sm:col-span-2">
            <div className="min-w-0 space-y-0.5">
              <Label htmlFor="cfg-memory">Remember previous runs</Label>
              <p className="text-xs text-muted-foreground">
                Keeps a short memory of earlier runs so it does not repeat work. Turn it off for
                stateless jobs.
              </p>
            </div>
            <Switch
              id="cfg-memory"
              checked={form.memory_enabled}
              onCheckedChange={(memory_enabled) => set({ memory_enabled })}
            />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Tools"
        description="Only the apps connected to this workspace are listed. What this Buttlr is allowed to call."
      >
        <ToolPicker
          tools={availableTools}
          detachedTools={detachedTools}
          apps={apps}
          loading={appsAreLoading}
          value={selectedTools}
          onChange={setSelectedTools}
        />
      </SectionCard>

      <SectionCard title="Scope" description="Which repositories and projects it may touch.">
        <ScopeEditor
          scope={scope}
          onChange={setScope}
          integrations={integrations.data ?? []}
          apps={apps}
          loading={appsAreLoading}
        />
      </SectionCard>

      <SectionCard title="Schedule" description="When it runs without anyone asking.">
        <ScheduleEditor
          value={form.schedule}
          defaultTimezone={meta.data?.default_timezone || "UTC"}
          onChange={(schedule) => set({ schedule })}
        />
      </SectionCard>

      <SectionCard
        title="Model"
        description="Only providers that can answer right now are listed. Auto uses the organization default."
      >
        <ModelPicker
          value={form.model}
          providers={modelProviderIds}
          onChange={(model) => set({ model })}
        />
      </SectionCard>

      {dirty ? (
        <Alert tone="warning" title="Unsaved changes" icon={<AlertTriangle className="size-4" />}>
          <span>
            Your edits are only in this browser. Save them, or{" "}
            <button
              type="button"
              className="font-medium underline underline-offset-4"
              onClick={() => setConfirmDiscard(true)}
            >
              discard them
            </button>
            .
          </span>
        </Alert>
      ) : null}

      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title="Discard your changes?"
        description="The saved configuration stays as it was on the server. This cannot be undone."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        destructive
        onConfirm={() => {
          setForm({
            name: source.name,
            avatar: source.avatar,
            role: source.role,
            team_id: source.team_id ?? null,
            department: source.department ?? null,
            description: source.description,
            objective: source.objective,
            responsibilities: [...source.responsibilities],
            instructions: source.instructions,
            model: normalizeModel(source.model),
            schedule: normalizeSchedule(source.schedule),
            memory_enabled: source.memory_enabled,
          });
          setSelectedTools([...source.tools]);
          setScope({ ...source.scope });
          setConfirmDiscard(false);
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ permissions */

function ApprovalPolicyEditor({
  policy,
  onChange,
  saving,
}: {
  policy: ApprovalPolicy;
  onChange: (next: ApprovalPolicy) => void;
  saving: boolean;
}) {
  const patch = (partial: Partial<ApprovalPolicy>) => onChange({ ...policy, ...partial });

  return (
    <div className="space-y-4">
      <Field
        label="Default behaviour"
        htmlFor="policy-default"
        hint="Applied to every tool without a rule of its own."
      >
        <Select
          id="policy-default"
          value={policy.default_mode}
          onValueChange={(value) => patch({ default_mode: value as ApprovalMode })}
          options={MODE_OPTIONS}
          disabled={saving}
        />
      </Field>

      <Field
        label="Always ask when a tool is at least this risky"
        htmlFor="policy-risk"
      >
        <Select
          id="policy-risk"
          value={policy.require_for_risk}
          onValueChange={(value) => patch({ require_for_risk: value as RiskLevel })}
          options={RISK_LEVELS.map((risk) => ({ value: risk, label: humanize(risk) }))}
          disabled={saving}
        />
      </Field>

      <div className="space-y-2">
        <p className="text-sm font-medium">Per-tool rules</p>
        {policy.rules.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
            No per-tool rules. The default behaviour above applies to everything.
          </p>
        ) : (
          <ul className="space-y-2">
            {policy.rules.map((rule, index) => (
              <li
                key={`${rule.tool}-${index}`}
                className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center"
              >
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {toolLabel(rule.tool)}
                </span>
                <Select
                  aria-label={`Behaviour for ${toolLabel(rule.tool)}`}
                  value={rule.mode}
                  onValueChange={(value) =>
                    patch({
                      rules: policy.rules.map((item, i) =>
                        i === index ? { ...item, mode: value as ApprovalMode } : item,
                      ),
                    })
                  }
                  options={MODE_OPTIONS}
                  className="sm:w-52"
                  disabled={saving}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove rule for ${toolLabel(rule.tool)}`}
                  disabled={saving}
                  onClick={() => patch({ rules: policy.rules.filter((_, i) => i !== index) })}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PermissionsPanel({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const buttlr = useButtlr(organizationId, buttlrId);
  const teams = useTeams(organizationId);
  const members = useMembers(organizationId);
  const updateButtlr = useUpdateButtlr(organizationId ?? "");

  const source = buttlr.data;
  const [policy, setPolicy] = useState<ApprovalPolicy | null>(null);

  useEffect(() => {
    if (source) setPolicy(normalizePolicy(source.approval_policy));
  }, [source]);

  const dirty =
    policy !== null && source !== undefined
      ? JSON.stringify(policy) !== JSON.stringify(normalizePolicy(source.approval_policy))
      : false;

  const save = async () => {
    if (!policy) return;
    try {
      await updateButtlr.mutateAsync({ buttlrId, patch: { approval_policy: policy } });
      toast.success("Approval policy saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The policy could not be saved.");
    }
  };

  if (buttlr.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (buttlr.isError) {
    return <ErrorState error={buttlr.error} onRetry={() => void buttlr.refetch()} />;
  }

  if (!source || !policy) return null;

  return (
    <div className="space-y-6">
      <SectionCard
        title="Who may do what"
        description="The grants this Buttlr carries. Organization roles still set the floor."
      >
        <PermissionMatrix
          buttlr={source}
          teams={teams.data ?? []}
          members={members.data ?? []}
        />
      </SectionCard>

      <SectionCard
        title="Approval policy"
        description="What this Buttlr must ask about before acting."
        actions={
          <Button
            type="button"
            size="sm"
            onClick={() => void save()}
            loading={updateButtlr.isPending}
            disabled={!dirty}
          >
            Save policy
          </Button>
        }
      >
        <ApprovalPolicyEditor
          policy={policy}
          onChange={setPolicy}
          saving={updateButtlr.isPending}
        />
      </SectionCard>

      <SectionCard
        title="Who is waiting on this Buttlr"
        description="Runs paused until somebody decides."
      >
        <PendingApprovals buttlrId={buttlrId} />
      </SectionCard>
    </div>
  );
}

function PendingApprovals({ buttlrId }: { buttlrId: string }) {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const navigate = useNavigate();
  const approvals = useApprovals(organizationId, { status: "pending", limit: 20 });

  const pending = (approvals.data?.items ?? []).filter(
    (approval) => approval.buttlr_id === buttlrId,
  );

  if (approvals.isLoading) {
    return <Skeleton className="h-16 w-full" />;
  }

  if (pending.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing is waiting. Runs that need a decision will pause and show up here and in Approvals.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {pending.map((approval) => (
        <li
          key={approval.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
        >
          <div className="min-w-0 space-y-0.5">
            <p className="text-sm font-medium">{approval.action}</p>
            <p className="text-xs text-muted-foreground">
              {toolLabel(approval.tool)} · asked {formatRelative(approval.requested_at)}
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => navigate("/approvals")}>
            Decide
          </Button>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ page */

export function ButtlrDetailPage() {
  const { buttlrId } = useParams<{ buttlrId: string }>();
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const buttlr = useButtlr(organizationId, buttlrId ?? null);
  const runs = useExecutions(organizationId, {
    buttlr_id: buttlrId ?? undefined,
    limit: 1,
  });

  const deploy = useDeployButtlr(organizationId ?? "");
  const pause = usePauseButtlr(organizationId ?? "");
  const run = useRunButtlr(organizationId ?? "");
  const remove = useDeleteButtlr(organizationId ?? "");
  const updateButtlr = useUpdateButtlr(organizationId ?? "");

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const requestedTab = searchParams.get("tab");
  const tab: TabValue = TABS.some((item) => item.value === requestedTab)
    ? (requestedTab as TabValue)
    : "overview";

  const setTab = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", value);
    setSearchParams(next, { replace: true });
  };

  const source = buttlr.data;

  const runNow = async (dryRun: boolean) => {
    setActionError(null);
    try {
      const execution = await run.mutateAsync({
        buttlrId: buttlrId ?? "",
        payload: { dry_run: dryRun },
      });
      const next = new URLSearchParams(searchParams);
      next.set("tab", "runs");
      next.set("execution", execution.id);
      setSearchParams(next, { replace: true });
      toast.success(dryRun ? "Test run started" : "Run started");
    } catch (error) {
      const message = error instanceof Error ? error.message : "The run could not be started.";
      setActionError(message);
      toast.error(message);
    }
  };
  const toggleMemory = async (memory_enabled: boolean) => {
    try {
      await updateButtlr.mutateAsync({ buttlrId: buttlrId ?? "", patch: { memory_enabled } });
      toast.success(memory_enabled ? "Memory turned on" : "Memory turned off");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The change could not be saved.");
    }
  };

  const toggleStatus = async () => {
    if (!source) return;
    setActionError(null);
    try {
      if (source.status === "active") {
        await pause.mutateAsync(source.id);
        toast.success(`${source.name} is paused`);
      } else {
        await deploy.mutateAsync(source.id);
        toast.success(`${source.name} is deployed`);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "The status could not be changed.";
      setActionError(message);
      toast.error(message);
    }
  };

  const destroy = async () => {
    if (!source) return;
    try {
      await remove.mutateAsync(source.id);
      toast.success(`${source.name} was deleted`);
      navigate("/buttlrs");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The Buttlr could not be deleted.");
    }
  };

  if (buttlrId === undefined) {
    return (
      <EmptyState
        title="No Buttlr selected"
        description="Pick a Buttlr from the list to see its configuration and runs."
        action={
          <Button asChild>
            <Link to="/buttlrs">All Buttlrs</Link>
          </Button>
        }
      />
    );
  }

  if (buttlr.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (buttlr.isError) {
    const notFound = buttlr.error instanceof ApiError && buttlr.error.status === 404;
    return (
      <div className="space-y-6">
        <PageHeader title="Buttlr" back={{ to: "/buttlrs", label: "All Buttlrs" }} />
        {notFound ? (
          <EmptyState
            icon={AlertTriangle}
            title="This Buttlr does not exist"
            description="It may have been deleted, or it belongs to another organization."
            action={
              <Button asChild>
                <Link to="/buttlrs">Back to all Buttlrs</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={buttlr.error} onRetry={() => void buttlr.refetch()} />
        )}
      </div>
    );
  }

  if (!source) {
    return (
      <div className="space-y-6">
        <PageHeader title="Buttlr" back={{ to: "/buttlrs", label: "All Buttlrs" }} />
        <EmptyState
          title="This Buttlr does not exist"
          description="It may have been deleted, or it belongs to another organization."
          action={
            <Button asChild>
              <Link to="/buttlrs">Back to all Buttlrs</Link>
            </Button>
          }
        />
      </div>
    );
  }

  const latestRunId = runs.data?.items[0]?.id;
  const isActive = source.status === "active";

  return (
    <div className="space-y-6">
      <PageHeader
        title={source.name}
        description={[source.role, source.department].filter(Boolean).join(" · ")}
        back={{ to: "/buttlrs", label: "All Buttlrs" }}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ButtlrAvatar buttlr={source} size="md" />
            <StatusPill status={source.status} />
            <ScheduleBadge schedule={source.schedule} />
            <Button
              type="button"
              variant={isActive ? "outline" : "default"}
              onClick={() => void toggleStatus()}
              loading={deploy.isPending || pause.isPending}
            >
              {isActive ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              {isActive ? "Pause" : "Deploy"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void runNow(false)}
              loading={run.isPending}
            >
              <Play aria-hidden="true" />
              Run now
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => void runNow(true)}
              loading={run.isPending}
            >
              Test run
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Delete ${source.name}`}
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          </div>
        }
      />

      {actionError ? <ErrorState error={actionError} title="That action did not go through" /> : null}

      {source.status === "draft" ? (
        <Alert tone="info" title="Not deployed yet" icon={<AlertTriangle className="size-4" />}>
          <span>
            This Buttlr is a draft. It runs only when someone starts it, and it will not pick up its
            schedule until it is deployed.
          </span>
        </Alert>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList aria-label="Buttlr sections">
          {TABS.map((item) => (
            <TabsTrigger key={item.value} value={item.value}>
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <StatCards buttlrId={buttlrId} />

          <SectionCard title="Objective" description="What this Buttlr exists to achieve.">
            <p className="whitespace-pre-wrap text-sm">
              {source.objective || "No objective recorded yet."}
            </p>
          </SectionCard>

          <SectionCard title="Responsibilities" description="What it is accountable for.">
            {source.responsibilities.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                None recorded. Add them in Configuration.
              </p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {source.responsibilities.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Tools" description="Everything it is allowed to call.">
            {source.tools.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No tools selected. It can read its memory but cannot act on anything.
              </p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {source.tools.map((tool) => (
                  <Badge key={tool} tone="outline">
                    {toolLabel(tool)}
                  </Badge>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard title="Integrations" description="Accounts it depends on.">
            {source.integrations.length === 0 ? (
              <p className="text-sm text-muted-foreground">No integrations needed.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {source.integrations.map((provider) => (
                  <Badge key={provider} tone="outline">
                    {humanize(provider)}
                  </Badge>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Memory"
            description="Whether previous runs are carried forward."
            actions={
              <Switch
                id="overview-memory"
                checked={source.memory_enabled}
                aria-label="Remember previous runs"
                onCheckedChange={(memory_enabled) => void toggleMemory(memory_enabled)}
                disabled={updateButtlr.isPending}
              />
            }
          >
            <p className="text-sm text-muted-foreground">
              {source.memory_enabled
                ? "On. It keeps a short memory of earlier runs so it does not repeat work."
                : "Off. Every run starts from nothing."}
            </p>
          </SectionCard>

          <SectionCard title="Latest run" description="The most recent execution, end to end.">
            <LatestExecution executionId={latestRunId} />
          </SectionCard>

          <p className="text-xs text-muted-foreground">
            Created {formatRelative(source.created_at)}
            {source.deployed_at ? ` · deployed ${formatRelative(source.deployed_at)}` : ""}
          </p>
        </TabsContent>

        <TabsContent value="chat">
          <ChatPanel buttlrId={buttlrId} />
        </TabsContent>

        <TabsContent value="runs">
          <RunsPanel buttlrId={buttlrId} />
        </TabsContent>

        <TabsContent value="configuration">
          <ConfigurationPanel buttlrId={buttlrId} />
        </TabsContent>

        <TabsContent value="permissions">
          <PermissionsPanel buttlrId={buttlrId} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${source.name}?`}
        description="The configuration, its runs and its chat history go with it. This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Keep"
        destructive
        loading={remove.isPending}
        onConfirm={destroy}
      />
    </div>
  );
}