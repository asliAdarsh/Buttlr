import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Link2,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
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
import { PageHeader } from "@/components/common/PageHeader";
import { Field } from "@/components/common/Field";
import { SectionCard } from "@/components/common/SectionCard";
import { ToolPicker, describeApps, resolveToolChoices } from "@/components/buttlr/ToolPicker";
import { ScopeEditor } from "@/components/buttlr/ScopeEditor";
import { ModelPicker } from "@/components/buttlr/ModelPicker";
import { ExecutionTimeline } from "@/components/buttlr/ExecutionTimeline";
import { ScheduleBadge, describeSchedule } from "@/components/buttlr/ScheduleBadge";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  useAvailableModelProviders,
  useCreateButtlr,
  useDeployButtlr,
  useDraftButtlr,
  useIntegrationCatalogue,
  useIntegrations,
  useMembers,
  useMeta,
  useRefineButtlr,
  useRunButtlr,
  useTeams,
  useTools,
  useExecutionStream,
} from "@/lib/queries";
import { DEPARTMENTS, PERMISSION_LEVELS, RISK_LEVELS, SCHEDULE_PRESETS } from "@/lib/constants";
import { humanize, toolLabel } from "@/lib/format";
import type {
  ApprovalMode,
  ApprovalPolicy,
  ButtlrCreate,
  Execution,
  GrantSubject,
  ModelConfig,
  Permission,
  PermissionGrant,
  RiskLevel,
  Schedule,
  ScheduleKind,
} from "@/lib/types";

/* ------------------------------------------------------------------ shared editors */

const AVATAR_CHOICES = ["🤖", "🛡️", "📬", "💰", "🎧", "🧾", "📊", "🧠", "🗂️", "📅", "🔍", "⚙️"];

const TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
  "Australia/Sydney",
];

const WEEKDAYS = [
  { value: "mon", label: "Monday" },
  { value: "tue", label: "Tuesday" },
  { value: "wed", label: "Wednesday" },
  { value: "thu", label: "Thursday" },
  { value: "fri", label: "Friday" },
  { value: "sat", label: "Saturday" },
  { value: "sun", label: "Sunday" },
];

const KIND_OPTIONS = SCHEDULE_PRESETS.map((preset) => ({ value: preset.value, label: preset.label }));

const USES_TIME: ScheduleKind[] = ["hourly", "daily", "weekly", "monthly"];
const USES_WEEKDAY: ScheduleKind[] = ["weekly"];
const USES_DAY_OF_MONTH: ScheduleKind[] = ["monthly"];
const USES_INTERVAL: ScheduleKind[] = ["interval"];
const USES_CRON: ScheduleKind[] = ["cron"];

/** Fills the fields the backend treats as optional so the editor always has a full object. */
export function normalizeSchedule(value?: Schedule | null): Schedule {
  return {
    enabled: value?.enabled ?? false,
    kind: value?.kind ?? "manual",
    timezone: value?.timezone || "UTC",
    at: value?.at ?? null,
    day_of_week: value?.day_of_week ?? null,
    day_of_month: value?.day_of_month ?? null,
    interval_minutes: value?.interval_minutes ?? null,
    run_at: value?.run_at ?? null,
    cron: value?.cron ?? null,
    business_hours_only: value?.business_hours_only ?? false,
  };
}

export function normalizeModel(value?: ModelConfig | null): ModelConfig {
  return (
    value ?? {
      provider: "auto",
      name: "auto",
      temperature: 0.2,
      max_tokens: 2048,
      fallback: [],
    }
  );
}

export function normalizePolicy(value?: ApprovalPolicy | null): ApprovalPolicy {
  return (
    value ?? {
      default_mode: "ask",
      rules: [],
      require_for_risk: "high",
      approver_permission: "approve",
      expiry_minutes: 1440,
    }
  );
}

function ErrorNote({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : "The configuration could not be generated.";
  return (
    <Alert tone="destructive" title="That did not work" icon={<AlertTriangle className="size-4" />}>
      {message}
    </Alert>
  );
}

/**
 * The readable schedule editor: pick a rhythm in words, fill only the fields that rhythm needs,
 * and always keep a plain-English summary on screen. Cron is an opt-in escape hatch, never the
 * default.
 */
export function ScheduleEditor({
  value,
  onChange,
  defaultTimezone,
}: {
  value: Schedule;
  onChange: (next: Schedule) => void;
  defaultTimezone: string;
}) {
  const schedule = normalizeSchedule(value);
  const patch = (partial: Partial<Schedule>) => onChange({ ...schedule, ...partial });

  const setKind = (kind: ScheduleKind) => {
    const enabled = kind !== "manual";
    patch({
      kind,
      enabled,
      at: USES_TIME.includes(kind) ? (schedule.at ?? "09:00") : null,
      day_of_week: USES_WEEKDAY.includes(kind) ? (schedule.day_of_week ?? "mon") : null,
      day_of_month: USES_DAY_OF_MONTH.includes(kind) ? (schedule.day_of_month ?? 1) : null,
      interval_minutes: USES_INTERVAL.includes(kind) ? (schedule.interval_minutes ?? 60) : null,
      cron: USES_CRON.includes(kind) ? (schedule.cron ?? "0 9 * * 1-5") : null,
    });
  };

  const timezoneOptions = useMemo(() => {
    const values = new Set<string>([defaultTimezone, schedule.timezone, ...TIMEZONES]);
    return [...values].map((zone) => ({ value: zone, label: zone }));
  }, [defaultTimezone, schedule.timezone]);

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4 rounded-md border border-border bg-muted/40 p-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium">Run it on a schedule</p>
          <p className="text-xs text-muted-foreground">
            {describeSchedule(schedule)}
            {schedule.enabled ? "" : " · off — runs only when someone starts it"}
          </p>
        </div>
        <Switch
          id="schedule-enabled"
          checked={schedule.enabled}
          onCheckedChange={(enabled) => patch({ enabled })}
          aria-label="Run on a schedule"
        />
      </div>

      <Field label="How often" htmlFor="schedule-kind">
        <Select
          id="schedule-kind"
          value={schedule.kind}
          onValueChange={(value) => setKind(value as ScheduleKind)}
          options={KIND_OPTIONS}
        />
      </Field>

      {USES_TIME.includes(schedule.kind) ? (
        <Field label="Time of day" htmlFor="schedule-at" hint="In the timezone chosen below.">
          <Input
            id="schedule-at"
            type="time"
            value={schedule.at ?? "09:00"}
            onChange={(event) => patch({ at: event.target.value || null })}
          />
        </Field>
      ) : null}

      {USES_WEEKDAY.includes(schedule.kind) ? (
        <Field label="Day of the week" htmlFor="schedule-weekday">
          <Select
            id="schedule-weekday"
            value={schedule.day_of_week ?? "mon"}
            onValueChange={(value) => patch({ day_of_week: value })}
            options={WEEKDAYS}
          />
        </Field>
      ) : null}

      {USES_DAY_OF_MONTH.includes(schedule.kind) ? (
        <Field label="Day of the month" htmlFor="schedule-dom">
          <Input
            id="schedule-dom"
            type="number"
            min={1}
            max={28}
            value={schedule.day_of_month ?? 1}
            onChange={(event) => patch({ day_of_month: Number(event.target.value) || null })}
          />
        </Field>
      ) : null}

      {USES_INTERVAL.includes(schedule.kind) ? (
        <Field label="Every how many minutes" htmlFor="schedule-interval">
          <Input
            id="schedule-interval"
            type="number"
            min={5}
            step={5}
            value={schedule.interval_minutes ?? 60}
            onChange={(event) => patch({ interval_minutes: Number(event.target.value) || null })}
          />
        </Field>
      ) : null}

      {USES_CRON.includes(schedule.kind) ? (
        <Field
          label="Cron expression"
          htmlFor="schedule-cron"
          hint="Five fields: minute hour day-of-month month day-of-week. Only needed for rhythms the options above cannot express."
        >
          <Input
            id="schedule-cron"
            value={schedule.cron ?? ""}
            placeholder="0 9 * * 1-5"
            onChange={(event) => patch({ cron: event.target.value || null })}
          />
        </Field>
      ) : null}

      <Field label="Timezone" htmlFor="schedule-tz">
        <Select
          id="schedule-tz"
          value={schedule.timezone}
          onValueChange={(value) => patch({ timezone: value })}
          options={timezoneOptions}
        />
      </Field>

      <div className="flex items-start justify-between gap-4 rounded-md border border-border p-3">
        <div className="min-w-0 space-y-0.5">
          <Label htmlFor="schedule-business-hours">Business hours only</Label>
          <p className="text-xs text-muted-foreground">
            Hold runs outside working hours in this timezone until the next working day.
          </p>
        </div>
        <Switch
          id="schedule-business-hours"
          checked={schedule.business_hours_only}
          onCheckedChange={(business_hours_only) => patch({ business_hours_only })}
        />
      </div>

      <p className="flex items-center gap-2 text-sm">
        <ScheduleBadge schedule={schedule} />
        <span className="text-xs text-muted-foreground">{schedule.timezone}</span>
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ permission rows */

const SUBJECT_OPTIONS: { value: GrantSubject; label: string }[] = [
  { value: "everyone", label: "Everyone" },
  { value: "role", label: "Organization role" },
  { value: "team", label: "Team" },
  { value: "user", label: "Member" },
];

const ROLE_OPTIONS = [
  { value: "owner", label: "Owner" },
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
];

function GrantsEditor({
  grants,
  onChange,
  teamOptions,
  memberOptions,
}: {
  grants: PermissionGrant[];
  onChange: (next: PermissionGrant[]) => void;
  teamOptions: { value: string; label: string }[];
  memberOptions: { value: string; label: string }[];
}) {
  const update = (index: number, partial: Partial<PermissionGrant>) => {
    onChange(grants.map((grant, i) => (i === index ? { ...grant, ...partial } : grant)));
  };

  const subjectOptions = (subjectType: GrantSubject) => {
    if (subjectType === "everyone") return [{ value: "everyone", label: "Everyone" }];
    if (subjectType === "role") return ROLE_OPTIONS;
    if (subjectType === "team") return teamOptions;
    return memberOptions;
  };

  return (
    <div className="space-y-3">
      {grants.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          No one is granted access yet. Add a row — the creator is granted admin automatically if
          you leave it empty.
        </p>
      ) : (
        <ul className="space-y-2">
          {grants.map((grant, index) => {
            const options = subjectOptions(grant.subject_type);
            return (
              <li
                key={`${grant.subject_type}-${index}`}
                className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center"
              >
                <Select
                  aria-label="Who the grant applies to"
                  value={grant.subject_type}
                  onValueChange={(value) => {
                    const subject_type = value as GrantSubject;
                    update(index, {
                      subject_type,
                      subject: subjectOptions(subject_type)[0]?.value ?? "",
                    });
                  }}
                  options={SUBJECT_OPTIONS}
                  className="sm:w-44"
                />
                <Select
                  aria-label="Subject"
                  value={grant.subject}
                  onValueChange={(value) => update(index, { subject: value })}
                  options={
                    options.some((option) => option.value === grant.subject)
                      ? options
                      : [{ value: grant.subject, label: grant.subject }, ...options]
                  }
                  className="sm:w-44"
                />
                <Select
                  aria-label="Permission level"
                  value={grant.permission}
                  onValueChange={(value) =>
                    update(index, {
                      permission: value as Permission,
                    })
                  }
                  options={PERMISSION_LEVELS.map((level) => ({
                    value: level.value,
                    label: level.label,
                    hint: level.description,
                  }))}
                  className="sm:flex-1"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove grant ${index + 1}`}
                  onClick={() => onChange(grants.filter((_, i) => i !== index))}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() =>
          onChange([
            ...grants,
            { subject_type: "team", subject: teamOptions[0]?.value ?? "", permission: "view" },
          ])
        }
      >
        <Plus aria-hidden="true" />
        Add a grant
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ approval policy */

const MODE_OPTIONS: { value: ApprovalMode; label: string }[] = [
  { value: "auto", label: "Run without asking" },
  { value: "ask", label: "Ask someone first" },
  { value: "deny", label: "Never allow" },
];

function PolicyEditor({
  policy,
  onChange,
  toolOptions,
}: {
  policy: ApprovalPolicy;
  onChange: (next: ApprovalPolicy) => void;
  toolOptions: { value: string; label: string }[];
}) {
  const patch = (partial: Partial<ApprovalPolicy>) => onChange({ ...policy, ...partial });

  return (
    <div className="space-y-4">
      <Field
        label="Default behaviour"
        htmlFor="policy-default"
        hint="Applied to every tool that has no rule of its own below."
      >
        <Select
          id="policy-default"
          value={policy.default_mode}
          onValueChange={(value) => patch({ default_mode: value as ApprovalMode })}
          options={MODE_OPTIONS}
        />
      </Field>

      <Field
        label="Always ask when a tool is at least this risky"
        htmlFor="policy-risk"
        hint="Risk comes from the tool catalogue, not from this Buttlr."
      >
        <Select
          id="policy-risk"
          value={policy.require_for_risk}
          onValueChange={(value) => patch({ require_for_risk: value as RiskLevel })}
          options={RISK_LEVELS.map((risk) => ({ value: risk, label: humanize(risk) }))}
        />
      </Field>

      <div className="space-y-2">
        <p className="text-sm font-medium">Rules for specific tools</p>
        {policy.rules.length === 0 ? (
          <p className="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
            No tool-specific rules. The default behaviour above applies to everything.
          </p>
        ) : (
          <ul className="space-y-2">
            {policy.rules.map((rule, index) => {
              const options = toolOptions.some((option) => option.value === rule.tool)
                ? toolOptions
                : [{ value: rule.tool, label: toolLabel(rule.tool) }, ...toolOptions];
              return (
                <li
                  key={`${rule.tool}-${index}`}
                  className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-center"
                >
                  <Select
                    aria-label="Tool the rule applies to"
                    value={rule.tool}
                    onValueChange={(value) =>
                      patch({
                        rules: policy.rules.map((item, i) =>
                          i === index ? { ...item, tool: value } : item,
                        ),
                      })
                    }
                    options={options}
                    className="sm:flex-1"
                  />
                  <Select
                    aria-label="Behaviour for this tool"
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
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove rule for ${toolLabel(rule.tool)}`}
                    onClick={() =>
                      patch({ rules: policy.rules.filter((_, i) => i !== index) })
                    }
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={toolOptions.length === 0}
          onClick={() =>
            patch({
              rules: [
                ...policy.rules,
                {
                  tool: toolOptions[0]?.value ?? "",
                  mode: "ask",
                  approver_roles: [],
                },
              ],
            })
          }
        >
          <Plus aria-hidden="true" />
          Add a rule
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ the wizard */

const EXAMPLES = [
  {
    label: "Pull request review",
    prompt:
      "Monitor our selected GitHub repositories every morning. Analyze new pull requests for bugs, security issues, missing tests and unresolved review comments. Summarize the important findings. If a critical issue is found, prepare a Jira ticket and ask the Engineering Lead for approval before creating it.",
  },
  {
    label: "Inbox triage",
    prompt:
      "Every weekday morning, read my inbox and sort the unread messages into urgent, needs a reply and for later. Draft a reply for the urgent ones and ask me before sending anything.",
  },
  {
    label: "Expense approvals",
    prompt:
      "Check submitted expenses every afternoon, flag anything above 500 dollars or missing a receipt, and ask the Finance Lead before approving a flagged expense.",
  },
  {
    label: "Support triage",
    prompt:
      "Triage support email every two hours during business hours. Group the messages by issue, spot anything urgent, and open a ticket for each new issue so the team can see it.",
  },
];

const STEPS = [
  { value: 1, label: "Describe" },
  { value: 2, label: "Review" },
  { value: 3, label: "Deploy" },
] as const;

function Stepper({ step }: { step: 1 | 2 | 3 }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Progress">
      {STEPS.map((item, index) => {
        const state = item.value < step ? "done" : item.value === step ? "current" : "todo";
        return (
          <li key={item.value} className="flex flex-1 items-center gap-2">
            <span className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={
                  state === "todo"
                    ? "flex size-7 shrink-0 items-center justify-center rounded-full border border-border text-xs font-medium text-muted-foreground"
                    : "flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
                }
              >
                {state === "done" ? <Check className="size-4" /> : item.value}
              </span>
              <span
                className={
                  state === "todo"
                    ? "text-sm text-muted-foreground"
                    : "text-sm font-medium text-foreground"
                }
              >
                {item.label}
              </span>
            </span>
            {index < STEPS.length - 1 ? (
              <span aria-hidden="true" className="h-px flex-1 bg-border" />
            ) : null}
          </li>
        );
      })}
      <li className="sr-only" aria-live="polite">
        Step {step} of 3: {STEPS.find((item) => item.value === step)?.label}
      </li>
    </ol>
  );
}

function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-0.5 border-b border-border py-2 last:border-b-0 sm:grid-cols-3 sm:gap-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground sm:pt-0.5">
        {label}
      </dt>
      <dd className="min-w-0 text-sm sm:col-span-2">{children}</dd>
    </div>
  );
}

export function ButtlrNewPage() {
  const navigate = useNavigate();
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;

  const meta = useMeta();
  const teams = useTeams(organizationId);
  const members = useMembers(organizationId);
  const tools = useTools();
  const integrations = useIntegrations(organizationId);
  const catalogue = useIntegrationCatalogue(organizationId);
  const availableModels = useAvailableModelProviders(organizationId);

  const draftButtlr = useDraftButtlr(organizationId ?? "");
  const refineButtlr = useRefineButtlr(organizationId ?? "");
  const createButtlr = useCreateButtlr(organizationId ?? "");
  const deployButtlr = useDeployButtlr(organizationId ?? "");
  const runButtlr = useRunButtlr(organizationId ?? "");

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [prompt, setPrompt] = useState("");
  const [teamId, setTeamId] = useState("");
  const [draft, setDraft] = useState<ButtlrCreate | null>(null);
  const [rationale, setRationale] = useState("");
  const [assumptions, setAssumptions] = useState<string[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [refineText, setRefineText] = useState("");
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [testExecution, setTestExecution] = useState<Execution | null>(null);

  const live = useExecutionStream(organizationId, testExecution?.id ?? null, testExecution);

  const defaultTimezone = meta.data?.default_timezone || "UTC";

  const teamOptions = useMemo(
    () => [
      { value: "", label: "No team" },
      ...(teams.data ?? []).map((team) => ({ value: team.id, label: `${team.emoji} ${team.name}` })),
    ],
    [teams.data],
  );

  const memberOptions = useMemo(
    () =>
      (members.data ?? []).map((member) => ({
        value: member.user_id,
        label: member.user?.display_name ?? member.user?.email ?? member.user_id,
      })),
    [members.data],
  );

  const toolCatalogue = tools.data?.tools ?? [];
  const toolOptions = useMemo(
    () => toolCatalogue.map((tool) => ({ value: tool.name, label: toolLabel(tool.name) })),
    [toolCatalogue],
  );

  const apps = useMemo(
    () => describeApps(catalogue.data ?? [], integrations.data ?? []),
    [catalogue.data, integrations.data],
  );
  const appNames = useMemo(() => new Map(apps.map((app) => [app.provider, app.name])), [apps]);

  // The work offered is the work a connected app can actually do; anything already
  // selected from an app with no connection stays visible so it can be removed.
  const { available: availableTools, detached: detachedTools } = useMemo(
    () => resolveToolChoices(toolCatalogue, apps, draft?.tools ?? []),
    [toolCatalogue, apps, draft?.tools],
  );

  const appsAreLoading = tools.isLoading || integrations.isLoading || catalogue.isLoading;
  const modelProviderIds = useMemo(
    () => (availableModels.data ?? []).map((entry) => entry.provider),
    [availableModels.data],
  );

  // The catalogue is the authority on which account a tool needs; the builder's own
  // `integrations` list carries tool-name prefixes the API does not accept.
  const providersForTools = useMemo(() => {
    const byName = new Map(
      toolCatalogue
        .filter((tool) => tool.integration)
        .map((tool) => [tool.name, tool.integration as string]),
    );
    return (names: string[]) => [
      ...new Set(names.map((name) => byName.get(name)).filter((provider): provider is string => Boolean(provider))),
    ];
  }, [toolCatalogue]);

  const connectedProviders = useMemo(
    () =>
      new Set(
        (integrations.data ?? [])
          .filter((integration) => integration.status === "connected")
          .map((integration) => integration.provider as string),
      ),
    [integrations.data],
  );

  const requiredProviders = useMemo(() => {
    if (!draft) return [];
    return providersForTools(draft.tools ?? []);
  }, [draft, providersForTools]);

  const missingIntegrations = useMemo(
    () => requiredProviders.filter((provider) => !connectedProviders.has(provider)),
    [requiredProviders, connectedProviders],
  );

  const missingAppNames = missingIntegrations.map(
    (provider) => appNames.get(provider) ?? humanize(provider),
  );

  const update = (patch: Partial<ButtlrCreate>) =>
    setDraft((current) => (current ? { ...current, ...patch } : current));

  const schedule = normalizeSchedule(draft?.schedule);
  const model = normalizeModel(draft?.model);
  const policy = normalizePolicy(draft?.approval_policy);
  const nameValid = (draft?.name.trim().length ?? 0) >= 2;
  const busy = createButtlr.isPending || deployButtlr.isPending || runButtlr.isPending;

  const handleGenerate = async () => {
    if (!organizationId) return;
    try {
      const response = await draftButtlr.mutateAsync({
        prompt: prompt.trim(),
        organization_id: organizationId,
        team_id: teamId || null,
      });
      setDraft({
        ...response.draft,
        model: normalizeModel(response.draft.model),
        schedule: normalizeSchedule(response.draft.schedule),
        approval_policy: normalizePolicy(response.draft.approval_policy),
      });
      setRationale(response.rationale);
      setAssumptions(response.assumptions);
      setMissing(response.missing);
      setCreatedId(null);
      setTestExecution(null);
      setStep(2);
    } catch {
      // The error is rendered below; the prompt is deliberately left untouched.
    }
  };

  const handleRefine = async () => {
    const instruction = refineText.trim();
    if (!draft || instruction.length < 3) return;
    try {
      const response = await refineButtlr.mutateAsync({ instruction, current: draft });
      setDraft({
        ...response.draft,
        model: normalizeModel(response.draft.model),
        schedule: normalizeSchedule(response.draft.schedule),
        approval_policy: normalizePolicy(response.draft.approval_policy),
      });
      setRationale(response.rationale);
      setAssumptions(response.assumptions);
      setMissing(response.missing);
      setRefineText("");
      setCreatedId(null);
      setTestExecution(null);
      toast.success("Configuration updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The change could not be applied.");
    }
  };

  const toPayload = (): ButtlrCreate => {
    if (!draft) throw new Error("No configuration yet");
    return {
      name: draft.name.trim(),
      avatar: draft.avatar || "🤖",
      role: draft.role || "AI Assistant",
      team_id: draft.team_id ?? null,
      department: draft.department ?? null,
      description: draft.description ?? "",
      objective: draft.objective ?? "",
      responsibilities: draft.responsibilities ?? [],
      instructions: draft.instructions ?? "",
      model,
      tools: draft.tools ?? [],
      integrations: requiredProviders,
      scope: draft.scope ?? {},
      schedule,
      approval_policy: policy,
      permissions: draft.permissions ?? [],
      memory_enabled: draft.memory_enabled ?? true,
      status: "draft",
    };
  };

  const handleCreate = async (thenDeploy: boolean) => {
    if (!draft || !nameValid) {
      toast.error("Give this Buttlr a name of at least two characters first.");
      return;
    }
    try {
      let id = createdId;
      let name = draft.name.trim();
      if (!id) {
        const created = await createButtlr.mutateAsync(toPayload());
        id = created.id;
        name = created.name;
        setCreatedId(created.id);
      }

      if (missingIntegrations.length > 0) {
        toast.success("Saved as a draft", {
          description: `Connect ${missingAppNames.join(", ")} before deploying.`,
        });
        navigate(`/buttlrs/${id}`);
        return;
      }

      if (thenDeploy) {
        await deployButtlr.mutateAsync(id);
        toast.success(`${name} is deployed`);
      } else {
        toast.success("Buttlr created");
      }
      navigate(`/buttlrs/${id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The Buttlr could not be created.");
    }
  };

  const handleTestRun = async () => {
    if (!nameValid) {
      toast.error("Give this Buttlr a name of at least two characters first.");
      return;
    }
    try {
      let id = createdId;
      if (!id) {
        const created = await createButtlr.mutateAsync(toPayload());
        id = created.id;
        setCreatedId(id);
      }
      const execution = await runButtlr.mutateAsync({
        buttlrId: id,
        payload: { dry_run: true },
      });
      setTestExecution(execution);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The test run could not be started.");
    }
  };

  /* ------------------------------------------------------------ step 1 */

  const renderDescribe = () => (
    <div className="space-y-6">
      <SectionCard
        title="Describe the job"
        description="Plain language is enough. Write what this Buttlr should do, where it should work and when it should run."
      >
        <div className="space-y-4">
          <Field
            label="What should this Buttlr do?"
            htmlFor="prompt"
            required
            hint="Ten characters or more. Include the systems it should use and how often it should run."
          >
            <Textarea
              id="prompt"
              rows={7}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Monitor our selected GitHub repositories every morning. Analyze new pull requests for bugs, security issues, missing tests and unresolved review comments. Summarize the important findings. If a critical issue is found, prepare a Jira ticket and ask the Engineering Lead for approval before creating it."
            />
          </Field>

          <Field label="Team" htmlFor="draft-team" hint="Optional. Scopes the work to one team.">
            <Select
              id="draft-team"
              value={teamId}
              onValueChange={setTeamId}
              options={teamOptions}
            />
          </Field>

          <div className="space-y-2">
            <p className="text-sm font-medium">Start from an example</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <Button
                  key={example.label}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setPrompt(example.prompt)}
                >
                  {example.label}
                </Button>
              ))}
            </div>
          </div>

          {draftButtlr.isPending ? (
            <div
              role="status"
              className="flex items-start gap-3 rounded-md border border-border bg-muted/60 p-3"
            >
              <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-primary" aria-hidden="true" />
              <div className="space-y-1">
                <p className="text-sm font-medium">Reading your request</p>
                <p className="text-sm text-muted-foreground">
                  Working out the name, role, tools, scope, schedule and approval policy. This takes a
                  few seconds.
                </p>
              </div>
            </div>
          ) : null}

          {draftButtlr.isError ? <ErrorNote error={draftButtlr.error} /> : null}

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => void handleGenerate()}
              loading={draftButtlr.isPending}
              disabled={prompt.trim().length < 10}
            >
              <Wand2 aria-hidden="true" />
              Generate configuration
            </Button>
            <Button asChild variant="ghost">
              <Link to="/buttlrs">
                <ArrowLeft aria-hidden="true" />
                Cancel
              </Link>
            </Button>
          </div>
        </div>
      </SectionCard>
    </div>
  );

  /* ------------------------------------------------------------ step 2 */

  const renderReview = () => {
    if (!draft) return null;
    return (
      <div className="space-y-6">
        <SectionCard
          title="What I assumed"
          description={`Written by the builder from your description. Everything below is editable.`}
        >
          <div className="space-y-3 text-sm">
            {rationale ? <p className="text-muted-foreground">{rationale}</p> : null}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <p className="font-medium">What I assumed</p>
                {assumptions.length === 0 ? (
                  <p className="text-muted-foreground">Nothing assumed beyond your description.</p>
                ) : (
                  <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                    {assumptions.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="space-y-1.5">
                <p className="font-medium">What is still open</p>
                {missing.length === 0 ? (
                  <p className="text-muted-foreground">Nothing outstanding.</p>
                ) : (
                  <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                    {missing.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </SectionCard>

        {missingIntegrations.length > 0 ? (
          <Alert
            tone="warning"
            title={`${missingAppNames.join(", ")} ${missingAppNames.length === 1 ? "is" : "are"} not connected yet`}
            icon={<Link2 className="size-4" />}
          >
            <span>
              This configuration uses {missingAppNames.join(", ")}. You can still create it now — it
              stays a draft until{" "}
              <Link to="/integrations" className="font-medium underline underline-offset-4">
                Open integrations
              </Link>
              .
            </span>
          </Alert>
        ) : null}

        <SectionCard title="Who this Buttlr is" description="Name, avatar, role and what it is for.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="draft-name" required>
              <Input
                id="draft-name"
                value={draft.name}
                maxLength={80}
                onChange={(event) => update({ name: event.target.value })}
              />
            </Field>
            <Field label="Role" htmlFor="draft-role">
              <Input
                id="draft-role"
                value={draft.role}
                onChange={(event) => update({ role: event.target.value })}
              />
            </Field>

            <div className="space-y-1.5 sm:col-span-2">
              <Label id="draft-avatar-label">Avatar</Label>
              <div
                role="radiogroup"
                aria-labelledby="draft-avatar-label"
                className="flex flex-wrap gap-2"
              >
                {AVATAR_CHOICES.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    role="radio"
                    aria-checked={draft.avatar === emoji}
                    aria-label={`Avatar ${emoji}`}
                    onClick={() => update({ avatar: emoji })}
                    className={
                      draft.avatar === emoji
                        ? "flex size-9 items-center justify-center rounded-full border-2 border-primary text-lg"
                        : "flex size-9 items-center justify-center rounded-full border border-border text-lg transition-colors hover:bg-accent"
                    }
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>

            <Field label="Department" htmlFor="draft-department">
              <Select
                id="draft-department"
                value={draft.department ?? ""}
                onValueChange={(value) => update({ department: value || null })}
                options={[
                  { value: "", label: "No department" },
                  ...DEPARTMENTS.map((department) => ({ value: department, label: department })),
                ]}
              />
            </Field>

            <Field label="Team" htmlFor="draft-team-edit">
              <Select
                id="draft-team-edit"
                value={draft.team_id ?? ""}
                onValueChange={(value) => update({ team_id: value || null })}
                options={teamOptions}
              />
            </Field>

            <Field label="Description" htmlFor="draft-description" className="sm:col-span-2">
              <Textarea
                id="draft-description"
                rows={2}
                value={draft.description ?? ""}
                onChange={(event) => update({ description: event.target.value })}
              />
            </Field>

            <Field label="Objective" htmlFor="draft-objective" className="sm:col-span-2">
              <Textarea
                id="draft-objective"
                rows={2}
                value={draft.objective ?? ""}
                onChange={(event) => update({ objective: event.target.value })}
              />
            </Field>

            <Field
              label="Responsibilities"
              htmlFor="draft-responsibility"
              className="sm:col-span-2"
              hint="What it is accountable for. Each line becomes one duty."
            >
              <div className="space-y-2">
                {(draft.responsibilities ?? []).map((item, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      aria-label={`Responsibility ${index + 1}`}
                      value={item}
                      onChange={(event) =>
                        update({
                          responsibilities: (draft.responsibilities ?? []).map((entry, i) =>
                            i === index ? event.target.value : entry,
                          ),
                        })
                      }
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove responsibility ${index + 1}`}
                      onClick={() =>
                        update({
                          responsibilities: (draft.responsibilities ?? []).filter(
                            (_, i) => i !== index,
                          ),
                        })
                      }
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    update({ responsibilities: [...(draft.responsibilities ?? []), ""] })
                  }
                >
                  <Plus aria-hidden="true" />
                  Add a responsibility
                </Button>
              </div>
            </Field>

            <Field
              label="Instructions"
              htmlFor="draft-instructions"
              className="sm:col-span-2"
              hint="How it should behave: tone, checks it must make, and what it must never do."
            >
              <Textarea
                id="draft-instructions"
                rows={8}
                value={draft.instructions ?? ""}
                onChange={(event) => update({ instructions: event.target.value })}
              />
            </Field>
          </div>
        </SectionCard>

        <SectionCard
          title="What it can use"
          description="Only the apps connected to this workspace are listed. Risk and permission come from the catalogue."
        >
          <ToolPicker
            tools={availableTools}
            detachedTools={detachedTools}
            apps={apps}
            loading={appsAreLoading}
            value={draft.tools ?? []}
            onChange={(next) => update({ tools: next })}
          />
        </SectionCard>

        <SectionCard
          title="Where it works"
          description="Pick exactly which repositories and projects it may touch."
        >
          <ScopeEditor
            scope={draft.scope ?? {}}
            onChange={(next) => update({ scope: next })}
            integrations={integrations.data ?? []}
            apps={apps}
            loading={appsAreLoading}
          />
        </SectionCard>

        <SectionCard title="When it runs" description="Pick a rhythm in plain words.">
          <ScheduleEditor
            value={schedule}
            defaultTimezone={defaultTimezone}
            onChange={(next) => update({ schedule: next })}
          />
        </SectionCard>

        <SectionCard
          title="Model"
          description="Auto uses the organization default. Name a provider only when you need a specific one."
        >
          <ModelPicker
            value={model}
            providers={modelProviderIds}
            onChange={(next) => update({ model: next })}
          />
        </SectionCard>

        <SectionCard
          title="Who may use it"
          description="Grants decide who can see it, ask it questions, start runs and change it."
        >
          <GrantsEditor
            grants={draft.permissions ?? []}
            onChange={(next) => update({ permissions: next })}
            teamOptions={teamOptions.filter((option) => option.value !== "")}
            memberOptions={memberOptions}
          />
        </SectionCard>

        <SectionCard
          title="When it must ask"
          description="Protects anything irreversible. Runs that need a decision pause and wait."
        >
          <PolicyEditor
            policy={policy}
            toolOptions={toolOptions}
            onChange={(next) => update({ approval_policy: next })}
          />
        </SectionCard>

        <SectionCard
          title="Refine"
          description="Describe a change in plain language and the builder applies it to this configuration."
        >
          <div className="space-y-3">
            <Field label="What should change?" htmlFor="refine">
              <Textarea
                id="refine"
                rows={3}
                value={refineText}
                onChange={(event) => setRefineText(event.target.value)}
                placeholder="Run it only on weekdays and ask before creating a Jira ticket."
              />
            </Field>
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleRefine()}
              loading={refineButtlr.isPending}
              disabled={refineText.trim().length < 3}
            >
              <Sparkles aria-hidden="true" />
              Apply
            </Button>
          </div>
        </SectionCard>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => setStep(3)}>
            Review the summary
            <ArrowRight aria-hidden="true" />
          </Button>
          <Button type="button" variant="ghost" onClick={() => setStep(1)}>
            <ArrowLeft aria-hidden="true" />
            Back to the description
          </Button>
        </div>
      </div>
    );
  };

  /* ------------------------------------------------------------ step 3 */

  const renderDeploy = () => {
    if (!draft) return null;
    return (
      <div className="space-y-6">
        <SectionCard title="Summary" description="Everything this Buttlr will do when deployed.">
          <dl className="divide-y-0">
            <SummaryRow label="Name">
              {draft.avatar} {draft.name}
            </SummaryRow>
            <SummaryRow label="Role">
              {draft.role}
              {draft.department ? ` · ${draft.department}` : ""}
            </SummaryRow>
            <SummaryRow label="Objective">{draft.objective || "Not set"}</SummaryRow>
            <SummaryRow label="Responsibilities">
              {(draft.responsibilities ?? []).length === 0 ? (
                "Not set"
              ) : (
                <ul className="list-disc space-y-0.5 pl-5">
                  {(draft.responsibilities ?? []).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </SummaryRow>
            <SummaryRow label="Tools">
              {(draft.tools ?? []).length === 0 ? (
                <span className="text-muted-foreground">None selected</span>
              ) : (
                <span className="flex flex-wrap gap-1.5">
                  {(draft.tools ?? []).map((tool) => (
                    <Badge key={tool} tone="outline">
                      {toolLabel(tool)}
                    </Badge>
                  ))}
                </span>
              )}
            </SummaryRow>
            <SummaryRow label="Apps">
              {requiredProviders.length === 0 ? (
                <span className="text-muted-foreground">None needed</span>
              ) : (
                <span className="flex flex-wrap gap-1.5">
                  {requiredProviders.map((provider) => (
                    <Badge
                      key={provider}
                      tone={connectedProviders.has(provider) ? "success" : "warning"}
                    >
                      {appNames.get(provider) ?? humanize(provider)}
                      {connectedProviders.has(provider) ? " · connected" : " · not connected"}
                    </Badge>
                  ))}
                </span>
              )}
            </SummaryRow>
            <SummaryRow label="Scope">
              {Object.keys(draft.scope ?? {}).length === 0 ? (
                <span className="text-muted-foreground">Everything the connected accounts allow</span>
              ) : (
                <span className="break-words">
                  {Object.keys(draft.scope ?? {}).map((key) => appNames.get(key) ?? humanize(key)).join(", ")}
                </span>
              )}
            </SummaryRow>
            <SummaryRow label="Schedule">
              <span className="flex flex-wrap items-center gap-2">
                <ScheduleBadge schedule={schedule} />
                <span className="text-xs text-muted-foreground">{schedule.timezone}</span>
              </span>
            </SummaryRow>
            <SummaryRow label="Model">
              {model.provider === "auto"
                ? "Auto (organization default)"
                : `${humanize(model.provider)} · ${model.name}`}
            </SummaryRow>
            <SummaryRow label="Approvals">
              <span className="flex flex-col gap-1">
                <span>
                  Default: {MODE_OPTIONS.find((mode) => mode.value === policy.default_mode)?.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  Anything at least {humanize(policy.require_for_risk)} risk is checked first.
                </span>
                {policy.rules.map((rule) => (
                  <span key={rule.tool} className="text-xs text-muted-foreground">
                    {toolLabel(rule.tool)}:{" "}
                    {MODE_OPTIONS.find((mode) => mode.value === rule.mode)?.label}
                  </span>
                ))}
              </span>
            </SummaryRow>
            <SummaryRow label="Access">
              {(draft.permissions ?? []).length === 0 ? (
                <span className="text-muted-foreground">Only you, as admin</span>
              ) : (
                <ul className="space-y-0.5">
                  {(draft.permissions ?? []).map((grant, index) => (
                    <li key={`${grant.subject_type}-${grant.subject}-${index}`}>
                      {humanize(grant.subject_type)} · {humanize(grant.subject)} →{" "}
                      {humanize(grant.permission)}
                    </li>
                  ))}
                </ul>
              )}
            </SummaryRow>
          </dl>
        </SectionCard>

        {missingIntegrations.length > 0 ? (
          <Alert
            tone="warning"
            title={`Connect ${missingAppNames.join(", ")} to deploy`}
            icon={<Link2 className="size-4" />}
          >
            <span>
              Creating now saves it as a draft. It can run a test, but it will not be deployed until{" "}
              <Link to="/integrations" className="font-medium underline underline-offset-4">
                the accounts are connected
              </Link>
              .
            </span>
          </Alert>
        ) : null}

        <SectionCard
          title="Test run"
          description="Runs the configuration end to end without changing anything outside Buttlr."
        >
          <div className="space-y-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleTestRun()}
              loading={runButtlr.isPending}
              disabled={busy}
            >
              <Sparkles aria-hidden="true" />
              Test run
            </Button>

            {live.execution ? (
              <div className="rounded-md border border-border p-3">
                <ExecutionTimeline execution={live.execution} live={live.isStreaming} />
              </div>
            ) : testExecution ? (
              <p className="text-sm text-muted-foreground">Preparing the run…</p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No test run yet. A dry run saves the configuration as a draft first if it does not
                exist.
              </p>
            )}
          </div>
        </SectionCard>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            onClick={() => void handleCreate(true)}
            loading={busy}
            disabled={!nameValid || deployButtlr.isPending}
          >
            Create &amp; deploy
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleCreate(false)}
            loading={busy}
            disabled={!nameValid || createButtlr.isPending}
          >
            Create Buttlr
          </Button>
          <Button type="button" variant="ghost" onClick={() => setStep(2)}>
            <ArrowLeft aria-hidden="true" />
            Back to the configuration
          </Button>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="New Buttlr"
        description="Describe the job. Review what the builder produced. Deploy when it looks right."
        back={{ to: "/buttlrs", label: "All Buttlrs" }}
      />

      <Stepper step={step} />

      {step === 1 ? renderDescribe() : null}
      {step === 2 ? renderReview() : null}
      {step === 3 ? renderDeploy() : null}
    </div>
  );
}