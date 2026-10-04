import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Building2,
  Check,
  Code2,
  Cpu,
  Database,
  ExternalLink,
  Info,
  Lock,
  Mail,
  Monitor,
  Moon,
  Palette,
  Plug,
  ShieldCheck,
  Sun,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { DetailList } from "@/components/common/DetailList";
import { Field } from "@/components/common/Field";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatusPill } from "@/components/common/StatusPill";
import { useAuth } from "@/lib/auth";
import { useTheme, type Density, type ThemeMode } from "@/lib/theme";
import { ACCENTS } from "@/lib/constants";
import { api } from "@/lib/api";
import {
  useClearModelProvider,
  useModelProviders,
  useIntegrationCatalogue,
  useIntegrations,
  useMembers,
  useMeta,
  useOrganization,
  useUpdateMe,
  useSetModelProvider,
  useUpdateOrganization,
} from "@/lib/queries";
import { formatDate, formatRelative } from "@/lib/format";
import type {
  ModelProviderEntry,
  ModelProviderUpdate,
  Organization,
  OrganizationSettings,
  UserPreferences,
} from "@/lib/types";

const CATEGORIES = [
  { id: "account", label: "Account", icon: UserRound },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "notifications", label: "Notifications", icon: Mail },
  { id: "organization", label: "Organization", icon: Building2 },
  { id: "models", label: "AI & Models", icon: Cpu },
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "security", label: "Security", icon: ShieldCheck },
  { id: "privacy", label: "Privacy & Data", icon: Database },
  { id: "developer", label: "API & Developer", icon: Code2 },
] as const;

type CategoryId = (typeof CATEGORIES)[number]["id"];

const CATEGORY_IDS = new Set<string>(CATEGORIES.map((category) => category.id));

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];


const DENSITY_OPTIONS: { value: Density; label: string }[] = [
  { value: "comfortable", label: "Comfortable" },
  { value: "compact", label: "Compact" },
];

const NOTIFICATION_FLAGS: { key: keyof UserPreferences; label: string; description: string }[] = [
  {
    key: "in_app_notifications",
    label: "In-app notifications",
    description: "Show notifications in the bell menu and on the Activity page.",
  },
  {
    key: "email_notifications",
    label: "Email notifications",
    description: "Send the same notifications to your account email address.",
  },
  {
    key: "notify_on_approval",
    label: "Approval requests",
    description: "Be notified when a Buttlr asks for approval, and when someone decides.",
  },
  {
    key: "notify_on_completion",
    label: "Finished runs",
    description: "Be notified when a run completes.",
  },
  {
    key: "notify_on_failure",
    label: "Failed runs",
    description: "Be notified when a run fails.",
  },
];


const LOGO_EMOJIS = ["🏢", "🚀", "🧪", "🛠️", "📊", "🎯", "🌱", "🧭", "⚙️", "🗂️"];

function CategoryNav({
  current,
  onSelect,
}: {
  current: CategoryId;
  onSelect: (id: CategoryId) => void;
}) {
  return (
    <nav aria-label="Settings categories" className="md:sticky md:top-20 md:self-start">
      <ul className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:block md:space-y-1 md:overflow-visible md:px-0">
        {CATEGORIES.map((category) => {
          const Icon = category.icon;
          const active = category.id === current;
          return (
            <li key={category.id} className="shrink-0">
              <button
                type="button"
                aria-current={active ? "page" : undefined}
                onClick={() => onSelect(category.id)}
                className={
                  active
                    ? "flex min-h-11 w-full items-center gap-2 whitespace-nowrap rounded-md bg-muted px-3 py-2 text-sm font-medium text-foreground sm:min-h-0"
                    : "flex min-h-11 w-full items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:min-h-0"
                }
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                {category.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; icon?: LucideIcon }[];
  onChange: (value: T) => void;
  disabled?: boolean;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex w-full rounded-md bg-muted p-1 sm:inline-flex sm:w-auto"
    >
      {options.map((option) => {
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={value === option.value}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={
              value === option.value
                ? "inline-flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-sm bg-card px-3 py-1.5 text-sm font-medium text-foreground ring-1 ring-border sm:min-h-0 sm:flex-none"
                : "inline-flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-sm px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground sm:min-h-0 sm:flex-none"
            }
          >
            {Icon ? <Icon aria-hidden="true" className="size-4" /> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function SettingRow({
  label,
  description,
  htmlFor,
  children,
}: {
  label: string;
  description: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col items-stretch gap-3 py-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
      <div className="min-w-0 sm:flex-1">
        <Label htmlFor={htmlFor} className="leading-5">
          {label}
        </Label>
        <p className="mt-1 text-xs leading-4 text-muted-foreground">{description}</p>
      </div>
      <div className="shrink-0 self-end sm:self-auto">{children}</div>
    </div>
  );
}

function AccountSection() {
  const { user, applyUser } = useAuth();
  const updateMe = useUpdateMe();
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [title, setTitle] = useState(user?.title ?? "");
  const [photoUrl, setPhotoUrl] = useState(user?.photo_url ?? "");

  if (!user) return null;

  const dirty =
    displayName !== (user.display_name ?? "") ||
    title !== (user.title ?? "") ||
    photoUrl !== (user.photo_url ?? "");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!displayName.trim()) {
      toast.error("Your display name cannot be empty.");
      return;
    }
    try {
      const updated = await updateMe.mutateAsync({
        display_name: displayName.trim(),
        title: title.trim() || null,
        photo_url: photoUrl.trim() || null,
      });
      applyUser(updated);
      toast.success("Your profile was saved.");
    } catch (error) {
      toast.error(
        error instanceof Error && error.message ? error.message : "Your profile could not be saved.",
      );
    }
  };

  return (
    <SectionCard
      title="Account"
      description="How you appear to everyone else in this organization."
    >
      <form className="space-y-5" onSubmit={submit}>
        <div className="flex items-center gap-3">
          <Avatar name={user.display_name} src={user.photo_url ?? undefined} size="lg" />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{user.display_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user.email}</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Display name" htmlFor="account-name" required>
            <Input
              id="account-name"
              value={displayName}
              autoComplete="name"
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </Field>
          <Field label="Job title" htmlFor="account-title" hint="Shown next to your name.">
            <Input
              id="account-title"
              value={title}
              autoComplete="organization-title"
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>
        </div>

        <Field
          label="Email address"
          htmlFor="account-email"
          hint="Your sign-in identity. Change it with whoever manages authentication for this deployment."
        >
          <Input id="account-email" value={user.email} readOnly disabled />
        </Field>

        <Field
          label="Photo URL"
          htmlFor="account-photo"
          hint="A link to an image. Leave it empty to use your initials."
        >
          <Input
            id="account-photo"
            type="url"
            inputMode="url"
            value={photoUrl}
            placeholder="https://…"
            onChange={(event) => setPhotoUrl(event.target.value)}
          />
        </Field>

        <div className="flex justify-end">
          <Button type="submit" loading={updateMe.isPending} disabled={!dirty}>
            Save profile
          </Button>
        </div>
      </form>
    </SectionCard>
  );
}

function AppearanceSection() {
  const { user, applyUser } = useAuth();
  const { theme, accent, density, resolvedTheme, setTheme, setAccent, setDensity } = useTheme();
  const updateMe = useUpdateMe();

  const persist = async (patch: Partial<UserPreferences>) => {
    if (!user) return;
    try {
      const updated = await updateMe.mutateAsync({
        preferences: { ...user.preferences, ...patch },
      });
      applyUser(updated);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "This preference could not be saved to your profile.",
      );
    }
  };

  const busy = updateMe.isPending;

  return (
    <SectionCard
      title="Appearance"
      description="Changes apply immediately in this browser and are also saved to your profile."
    >
      <div className="divide-y divide-border">
        <SettingRow
          label="Theme"
          description={
            theme === "system"
              ? `Following your device — currently ${resolvedTheme}.`
              : `Always ${resolvedTheme}.`
          }
        >
          <Segmented
            label="Theme"
            value={theme}
            options={THEME_OPTIONS}
            disabled={busy}
            onChange={(next) => {
              setTheme(next);
              void persist({ theme: next });
            }}
          />
        </SettingRow>

        <SettingRow label="Accent" description="The colour used for primary actions and highlights.">
          <div role="radiogroup" aria-label="Accent colour" className="flex flex-wrap gap-2">
            {ACCENTS.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={accent === option.value}
                disabled={busy}
                onClick={() => {
                  setAccent(option.value);
                  void persist({ accent: option.value });
                }}
                className={
                  accent === option.value
                    ? "flex min-h-11 items-center gap-1.5 rounded-md border border-primary bg-muted px-3 py-2 text-xs font-medium text-foreground sm:min-h-0 sm:py-1"
                    : "flex min-h-11 items-center gap-1.5 rounded-md border border-border px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:min-h-0 sm:py-1"
                }
              >
                {accent === option.value ? <Check aria-hidden="true" className="size-3" /> : null}
                {option.label}
              </button>
            ))}
          </div>
        </SettingRow>

        <SettingRow
          label="Density"
          description="Compact tightens spacing throughout the app. Comfortable gives lists more room."
        >
          <Segmented
            label="Density"
            value={density}
            options={DENSITY_OPTIONS}
            disabled={busy}
            onChange={(next) => {
              setDensity(next);
              void persist({ density: next });
            }}
          />
        </SettingRow>
      </div>
    </SectionCard>
  );
}

function NotificationsSection() {
  const { user, applyUser } = useAuth();
  const updateMe = useUpdateMe();

  const toggle = async (key: keyof UserPreferences, checked: boolean) => {
    if (!user) return;
    try {
      const updated = await updateMe.mutateAsync({
        preferences: { ...user.preferences, [key]: checked },
      });
      applyUser(updated);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "That notification setting could not be saved.",
      );
    }
  };

  if (!user) return null;

  return (
    <SectionCard
      title="Notifications"
      description="What Buttlr tells you about, and where."
      actions={updateMe.isPending ? <Badge tone="muted">Saving…</Badge> : undefined}
    >
      <div className="divide-y divide-border">
        {NOTIFICATION_FLAGS.map((flag) => (
          <SettingRow
            key={flag.key}
            label={flag.label}
            description={flag.description}
            htmlFor={`notify-${flag.key}`}
          >
            <Switch
              id={`notify-${flag.key}`}
              checked={Boolean(user.preferences[flag.key])}
              disabled={updateMe.isPending}
              onCheckedChange={(checked) => void toggle(flag.key, checked)}
            />
          </SettingRow>
        ))}
      </div>
    </SectionCard>
  );
}

function OrganizationForm({
  organization,
  canManage,
}: {
  organization: Organization;
  canManage: boolean;
}) {
  const updateOrganization = useUpdateOrganization(organization.id);
  const [name, setName] = useState(organization.name);
  const [description, setDescription] = useState(organization.description ?? "");
  const [emoji, setEmoji] = useState(organization.logo_emoji);
  const [settings, setSettings] = useState<OrganizationSettings>(organization.settings);

  const dirty =
    name !== organization.name ||
    description !== (organization.description ?? "") ||
    emoji !== organization.logo_emoji ||
    JSON.stringify(settings) !== JSON.stringify(organization.settings);

  const setSetting = <K extends keyof OrganizationSettings>(key: K, value: OrganizationSettings[K]) => {
    setSettings((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      toast.error("The organization needs a name.");
      return;
    }
    if (!settings.default_model.trim()) {
      toast.error("The default model cannot be empty.");
      return;
    }
    try {
      await updateOrganization.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        logo_emoji: emoji,
        settings,
      });
      toast.success("Organization settings saved.");
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The organization could not be saved.",
      );
    }
  };

  const busy = updateOrganization.isPending;

  return (
    <form className="space-y-5" onSubmit={submit}>
      {!canManage ? (
        <Alert tone="info" icon={<Lock className="size-4" />} title="Read-only for your role">
          Only owners and admins can change these values. You are seeing what your organization uses today.
        </Alert>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_7rem]">
        <Field label="Name" htmlFor="org-name" required>
          <Input
            id="org-name"
            value={name}
            disabled={!canManage}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label="Logo emoji" htmlFor="org-emoji">
          <Input
            id="org-emoji"
            value={emoji}
            disabled={!canManage}
            maxLength={8}
            onChange={(event) => setEmoji(event.target.value)}
          />
        </Field>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {LOGO_EMOJIS.map((option) => (
          <button
            key={option}
            type="button"
            aria-label={`Use ${option} as the organization logo`}
            aria-pressed={emoji === option}
            disabled={!canManage}
            onClick={() => setEmoji(option)}
            className={
              emoji === option
                ? "flex min-h-11 min-w-11 items-center justify-center rounded-md border border-primary bg-muted px-2 py-1 text-base sm:min-h-0 sm:min-w-0"
                : "flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border px-2 py-1 text-base transition-colors hover:bg-muted disabled:opacity-50 sm:min-h-0 sm:min-w-0"
            }
          >
            {option}
          </button>
        ))}
      </div>

      <Field
        label="Description"
        htmlFor="org-description"
        hint="What this organization uses Buttlrs for."
      >
        <Textarea
          id="org-description"
          rows={3}
          value={description}
          disabled={!canManage}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>

      <Separator />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Default model" htmlFor="org-default-model" hint="Used when a Buttlr is set to Auto.">
          <Input
            id="org-default-model"
            value={settings.default_model}
            disabled={!canManage}
            onChange={(event) => setSetting("default_model", event.target.value)}
          />
        </Field>
        <Field
          label="Data retention (days)"
          htmlFor="org-data-retention"
          hint="How long run output and results are kept."
        >
          <Input
            id="org-data-retention"
            type="number"
            min={1}
            value={settings.data_retention_days}
            disabled={!canManage}
            onChange={(event) =>
              setSetting("data_retention_days", Math.max(1, Number(event.target.value) || 1))
            }
          />
        </Field>
        <Field
          label="Log retention (days)"
          htmlFor="org-log-retention"
          hint="How long audit entries are kept."
        >
          <Input
            id="org-log-retention"
            type="number"
            min={1}
            value={settings.log_retention_days}
            disabled={!canManage}
            onChange={(event) =>
              setSetting("log_retention_days", Math.max(1, Number(event.target.value) || 1))
            }
          />
        </Field>
      </div>

      <div className="divide-y divide-border rounded-lg border border-border px-3 py-1">
        <SettingRow
          label="Allow local models"
          description="Let Buttlrs use a model served by Ollama on your own machines."
          htmlFor="org-allow-local"
        >
          <Switch
            id="org-allow-local"
            checked={settings.allow_local_models}
            disabled={!canManage || busy}
            onCheckedChange={(checked) => setSetting("allow_local_models", checked)}
          />
        </SettingRow>
        <SettingRow
          label="Require approval for high risk"
          description="Stop any run at a high-risk step until someone approves it."
          htmlFor="org-require-approval"
        >
          <Switch
            id="org-require-approval"
            checked={settings.require_approval_for_high_risk}
            disabled={!canManage || busy}
            onCheckedChange={(checked) => setSetting("require_approval_for_high_risk", checked)}
          />
        </SettingRow>
        <SettingRow
          label="Audit log"
          description="Record every configuration change, approval and integration event."
          htmlFor="org-audit-enabled"
        >
          <Switch
            id="org-audit-enabled"
            checked={settings.audit_enabled}
            disabled={!canManage || busy}
            onCheckedChange={(checked) => setSetting("audit_enabled", checked)}
          />
        </SettingRow>
      </div>

      {canManage ? (
        <div className="flex justify-end">
          <Button type="submit" loading={busy} disabled={!dirty}>
            Save organization
          </Button>
        </div>
      ) : null}
    </form>
  );
}

function OrganizationSection() {
  const { activeOrganizationId, user, organizations } = useAuth();
  const members = useMembers(activeOrganizationId);
  const organization = useOrganization(activeOrganizationId);

  const role = (members.data ?? []).find((member) => member.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const current = organization.data ?? organizations.find((entry) => entry.id === activeOrganizationId) ?? null;

  if (!current) {
    return (
      <SectionCard title="Organization" description="Name, defaults and data rules.">
        <p className="text-sm text-muted-foreground">No organization is selected.</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      title="Organization"
      description={`${current.logo_emoji} ${current.name} · created ${formatDate(current.created_at)}`}
    >
      <OrganizationForm
        key={`${current.id}:${current.updated_at}`}
        organization={current}
        canManage={canManage}
      />
    </SectionCard>
  );
}

const KIND_BADGE: Record<string, { label: string; tone: "primary" | "warning" | "outline" | "muted" }> = {
  cloud: { label: "Cloud", tone: "primary" },
  local: { label: "Local", tone: "warning" },
  builtin: { label: "Built-in", tone: "outline" },
};

function statusLine(entry: ModelProviderEntry): string {
  if (entry.source === "workspace") return "Set by this workspace";
  if (entry.source === "deployment") return "Set for this deployment";
  return "Not configured";
}

function ProviderCard({ entry, canManage }: { entry: ModelProviderEntry; canManage: boolean }) {
  const kind = KIND_BADGE[entry.kind] ?? { label: entry.kind, tone: "muted" };
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [confirming, setConfirming] = useState(false);

  const { activeOrganizationId } = useAuth();
  const orgId = activeOrganizationId ?? "";
  const save = useSetModelProvider(orgId);
  const clear = useClearModelProvider(orgId);

  const editable = entry.provider !== "heuristic";
  const showEndpoint = entry.requires_base_url || entry.provider === "openai";
  const endpointPlaceholder =
    entry.provider === "ollama" ? "http://localhost:11434" : "https://your-gateway/v1";
  const canRemove = editable && entry.configured && entry.source === "workspace";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload: ModelProviderUpdate = {};
    if (entry.requires_key && apiKey.trim()) payload.api_key = apiKey.trim();
    if (showEndpoint && baseUrl.trim()) payload.base_url = baseUrl.trim();
    if (model.trim()) payload.model = model.trim();

    try {
      await save.mutateAsync({ provider: entry.provider, payload });
      setApiKey("");
      setBaseUrl("");
      setModel("");
      toast.success(`${entry.name} saved.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : `${entry.name} could not be saved.`,
      );
    }
  };

  const remove = async () => {
    try {
      await clear.mutateAsync(entry.provider);
      toast.success(`${entry.name} removed.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : `${entry.name} could not be removed.`,
      );
    }
  };

  return (
    <li className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Cpu aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        <p className="text-sm font-medium">{entry.name}</p>
        <Badge tone={kind.tone}>{kind.label}</Badge>
      </div>

      <p className="mt-1.5 text-xs leading-4 text-muted-foreground">{entry.description}</p>

      <dl className="mt-3 flex flex-col gap-1 text-xs">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <dt className="text-muted-foreground">Status</dt>
          <dd
            className={
              entry.configured ? "font-medium text-success" : "text-muted-foreground"
            }
          >
            {statusLine(entry)}
          </dd>
        </div>
        {entry.model ? (
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-muted-foreground">Model</dt>
            <dd className="min-w-0 break-all font-mono text-xs text-muted-foreground">
              {entry.model}
            </dd>
          </div>
        ) : null}
        {entry.base_url ? (
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-muted-foreground">Endpoint</dt>
            <dd className="min-w-0 break-all font-mono text-xs text-muted-foreground">
              {entry.base_url}
            </dd>
          </div>
        ) : null}
        {entry.requires_key ? (
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <dt className="text-muted-foreground">API key</dt>
            <dd className="text-muted-foreground">
              {entry.configured ? "Saved" : "Not saved"}
            </dd>
          </div>
        ) : null}
      </dl>

      {entry.note ? <p className="mt-2 text-xs leading-4 text-muted-foreground">{entry.note}</p> : null}

      {canManage && editable ? (
        <form className="mt-4 space-y-4 border-t border-border pt-4" onSubmit={submit}>
          {entry.requires_key ? (
            <Field
              label="API key"
              htmlFor={`model-${entry.provider}-key`}
              hint="Leave blank to keep the saved key."
            >
              <Input
                id={`model-${entry.provider}-key`}
                type="password"
                autoComplete="off"
                value={apiKey}
                placeholder="Paste the key"
                onChange={(event) => setApiKey(event.target.value)}
              />
            </Field>
          ) : null}

          {showEndpoint ? (
            <Field
              label={entry.requires_base_url ? "Endpoint" : "Endpoint (optional)"}
              htmlFor={`model-${entry.provider}-base-url`}
              hint={
                entry.requires_base_url
                  ? "Where the model server is listening."
                  : "Optional: override the default address if you use an OpenAI-compatible gateway."
              }
            >
              <Input
                id={`model-${entry.provider}-base-url`}
                type="url"
                inputMode="url"
                value={baseUrl}
                placeholder={entry.base_url ?? endpointPlaceholder}
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </Field>
          ) : null}

          <Field
            label="Model"
            htmlFor={`model-${entry.provider}-model`}
            hint="This is the model your Buttlrs will call."
          >
            <Input
              id={`model-${entry.provider}-model`}
              value={model}
              placeholder={entry.model ?? "Model name"}
              onChange={(event) => setModel(event.target.value)}
            />
          </Field>

          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <Button type="submit" size="sm" className="min-h-11 sm:min-h-0" loading={save.isPending}>
              Save
            </Button>
            {canRemove ? (
              <Button
                type="button"
                size="sm"
                className="min-h-11 sm:min-h-0"
                variant="outline"
                onClick={() => setConfirming(true)}
              >
                Remove
              </Button>
            ) : null}
            {entry.docs_url ? (
              <a
                href={entry.docs_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-11 items-center text-xs font-medium text-primary hover:underline sm:min-h-0"
              >
                Get a key
              </a>
            ) : null}
          </div>

          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title={`Remove ${entry.name}?`}
            description="Buttlrs fall back to the deployment's configuration, or to the built-in planner if there is none."
            confirmLabel="Remove"
            destructive
            loading={clear.isPending}
            onConfirm={remove}
          />
        </form>
      ) : null}

      {canManage && !editable ? (
        <p className="mt-3 border-t border-border pt-3 text-xs leading-4 text-muted-foreground">
          The built-in planner needs no credentials and cannot be changed. It is always available, so a Buttlr
          keeps working when no other provider is set.
        </p>
      ) : null}
    </li>
  );
}

function ModelsSection() {
  const { activeOrganizationId, user } = useAuth();
  const members = useMembers(activeOrganizationId);
  const providers = useModelProviders(activeOrganizationId);
  const organization = useOrganization(activeOrganizationId);

  const role = (members.data ?? []).find((member) => member.user_id === user?.id)?.role;
  const canManage = role === "owner" || role === "admin";
  const entries = providers.data ?? [];

  return (
    <SectionCard title="AI & Models" description="The models your Buttlrs can work with.">
      <p className="text-sm text-muted-foreground">
        Give Buttlrs a cloud provider key, or point them at a model server on your own infrastructure so your
        data never leaves it. The built-in planner is always available as the fallback, so a Buttlr still works
        with no provider set at all.
      </p>

      {!canManage ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Only owners and admins can change these. You are seeing what this organization uses today.
        </p>
      ) : null}

      <div className="mt-4">
        {providers.isPending ? (
          <ul className="space-y-4">
            {[0, 1, 2].map((row) => (
              <li key={row}>
                <Skeleton className="h-44 w-full rounded-lg" />
              </li>
            ))}
          </ul>
        ) : providers.isError ? (
          <ErrorState
            error={providers.error}
            title="Providers could not be loaded"
            onRetry={() => void providers.refetch()}
          />
        ) : (
          <ul className="space-y-4">
            {entries.map((entry) => (
              <ProviderCard key={entry.provider} entry={entry} canManage={canManage} />
            ))}
          </ul>
        )}
      </div>

      <Separator className="my-4" />

      <DetailList
        items={[
          {
            label: "Organization default model",
            value: <span className="font-mono text-xs">{organization.data?.settings.default_model ?? "—"}</span>,
          },
          {
            label: "Local models allowed",
            value: organization.data?.settings.allow_local_models ? "Yes" : "No",
          },
        ]}
      />
      <p className="mt-2 text-xs text-muted-foreground">
        The default model is an organization setting, so change it under{" "}
        <Link to="/settings?tab=organization" className="font-medium text-primary hover:underline">
          Organization
        </Link>
        . Saved keys are encrypted and never shown again.
      </p>
    </SectionCard>
  );
}

function IntegrationsSection() {
  const { activeOrganizationId } = useAuth();
  const integrations = useIntegrations(activeOrganizationId);
  const catalogue = useIntegrationCatalogue(activeOrganizationId);
  const entryByProvider = useMemo(
    () => new Map((catalogue.data ?? []).map((entry) => [entry.provider, entry])),
    [catalogue.data],
  );
  const connections = integrations.data ?? [];

  return (
    <SectionCard
      title="Integrations"
      description="Accounts this organization has connected."
      actions={
        <Button asChild variant="outline" size="sm">
          <Link to="/integrations">Manage integrations</Link>
        </Button>
      }
    >
      {connections.length === 0 ? (
        <Alert tone="info" icon={<Plug className="size-4" />}>
          Nothing is connected. Buttlrs that use GitHub, Jira or Google Workspace cannot run until an
          account is connected.
        </Alert>
      ) : (
        <ul className="divide-y divide-border">
          {connections.map((integration) => (
            <li
              key={integration.id}
              className="flex min-h-11 flex-wrap items-center justify-between gap-x-3 gap-y-1 py-3"
            >
              <div className="min-w-0 flex-1 basis-40">
                <p className="truncate text-sm font-medium leading-5">
                  {entryByProvider.get(integration.provider)?.name ?? integration.display_name}
                </p>
                <p className="truncate text-xs leading-4 text-muted-foreground">
                  {integration.account ?? "No account"}
                  {integration.last_used_at
                    ? ` · last used ${formatRelative(integration.last_used_at)}`
                    : " · never used"}
                </p>
              </div>
              <div className="shrink-0">
                <StatusPill status={integration.status} size="sm" />
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function SecuritySection() {
  const { user } = useAuth();
  const meta = useMeta();
  const authMode = meta.data?.auth_mode ?? "dev";
  const devMode = authMode === "dev";

  return (
    <SectionCard
      title="Security"
      description="How this session was established, and what happens when it ends."
    >
      <DetailList
        items={[
          {
            label: "Authentication mode",
            value: (
              <span className="flex flex-wrap items-center justify-end gap-2">
                {devMode ? "Development sign-in" : "Firebase"}
                <Badge tone={devMode ? "warning" : "success"}>
                  <Info aria-hidden="true" />
                  {devMode ? "No identity provider" : "External identity provider"}
                </Badge>
              </span>
            ),
          },
          {
            label: "This session",
            value: devMode
              ? "Issued by Buttlr itself from an email address — there is no password."
              : "Issued by Firebase from your identity provider.",
          },
          {
            label: "Token expiry",
            value: (
              <span className="text-muted-foreground">
                {devMode
                  ? "Development tokens last for the window set by DEV_AUTH_TTL_HOURS on the server, which this page cannot read. When a token stops working, Buttlr clears it and asks you to sign in again."
                  : "Firebase controls token lifetime. When a token stops working, Buttlr clears it and asks you to sign in again."}
              </span>
            ),
          },
          {
            label: "Last seen",
            value: user?.last_seen_at ? formatRelative(user.last_seen_at) : "—",
          },
        ]}
      />

      <Separator className="my-4" />

      <Alert tone="info" icon={<Activity className="size-4" />} title="Every action is recorded">
        Approvals, configuration changes, run starts and integration events are written to the audit log,
        which owners and admins read on the Activity page.
      </Alert>
    </SectionCard>
  );
}

function PrivacySection() {
  const { activeOrganizationId } = useAuth();
  const organization = useOrganization(activeOrganizationId);
  const settings = organization.data?.settings;

  return (
    <SectionCard title="Privacy & Data" description="What this organization keeps, and for how long.">
      <DetailList
        items={[
          {
            label: "Run data",
            value: (
              <>
                {settings ? `${settings.data_retention_days} days` : "—"} — steps, tool parameters, results
                and output for every run.
              </>
            ),
          },
          {
            label: "Audit log",
            value: (
              <>
                {settings ? `${settings.log_retention_days} days` : "—"} — who did what, when, and to which
                Buttlr.
              </>
            ),
          },
          {
            label: "Buttlr memory",
            value: (
              <span className="text-muted-foreground">
                Kept per Buttlr when its memory is enabled, so it can recall earlier conversations. It never
                leaves your organization.
              </span>
            ),
          },
        ]}
      />

      <p className="mt-4 text-xs text-muted-foreground">
        Retention windows are set by organization owners under{" "}
        <Link to="/settings?tab=organization" className="font-medium text-primary hover:underline">
          Organization
        </Link>
        . The audit trail itself lives on the{" "}
        <Link to="/activity" className="font-medium text-primary hover:underline">
          Activity page
        </Link>
        .
      </p>
    </SectionCard>
  );
}

function DeveloperSection() {
  const meta = useMeta();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.meta.health,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
  const status = health.data;
  const healthy = health.isSuccess && status?.status === "ok" && status.store_healthy;

  const statusBadge = health.isError ? (
    <Badge tone="destructive">
      <Info aria-hidden="true" />
      Unreachable
    </Badge>
  ) : health.isPending ? (
    <Badge tone="muted">Checking…</Badge>
  ) : healthy ? (
    <Badge tone="success">
      <Check aria-hidden="true" />
      Healthy
    </Badge>
  ) : (
    <Badge tone="warning">
      <Info aria-hidden="true" />
      Degraded
    </Badge>
  );

  return (
    <SectionCard
      title="API & Developer"
      description="Where this app talks to Buttlr, and whether the service is healthy."
      actions={
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={health.isFetching}
          onClick={() => void health.refetch()}
        >
          <Wrench aria-hidden="true" className="mr-1.5 h-4 w-4" />
          Re-check
        </Button>
      }
    >
      <DetailList
        items={[
          { label: "API base URL", value: <span className="font-mono text-xs">{baseUrl}</span> },
          {
            label: "API reference",
            value: (
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
              >
                /docs
                <ExternalLink aria-hidden="true" className="size-3" />
              </a>
            ),
          },
          { label: "Service status", value: statusBadge },
          {
            label: "Store backend",
            value: (
              <>
                {status?.store ?? meta.data?.store_backend ?? "—"}
                {status ? (status.store_healthy ? " · reachable" : " · unreachable") : ""}
              </>
            ),
          },
          {
            label: "Scheduler",
            value: status
              ? status.scheduler
                ? "Running — scheduled Buttlrs fire on time."
                : "Disabled — scheduled Buttlrs do not run."
              : meta.data?.scheduler_enabled
                ? "Running."
                : "Disabled.",
          },
          {
            label: "Runs in progress",
            value: <span className="tabular-nums">{status?.running_executions ?? "—"}</span>,
          },
          {
            label: "Version",
            value: (
              <>
                {status?.version ?? meta.data?.version ?? "—"}
                {meta.data?.environment ? ` · ${meta.data.environment}` : ""}
              </>
            ),
          },
        ]}
      />
    </SectionCard>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const current: CategoryId =
    requested && CATEGORY_IDS.has(requested) ? (requested as CategoryId) : "account";

  const select = (id: CategoryId) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", id);
    setSearchParams(params, { replace: true });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Your profile, this organization's defaults, and what this deployment can do."
      />

      <div className="grid gap-6 md:grid-cols-[14rem_minmax(0,1fr)]">
        <CategoryNav current={current} onSelect={select} />
        <div className="min-w-0 space-y-6">
          {current === "account" ? (
            <AccountSection key={`${user?.id ?? "none"}:${user?.updated_at ?? ""}`} />
          ) : null}
          {current === "appearance" ? <AppearanceSection /> : null}
          {current === "notifications" ? <NotificationsSection /> : null}
          {current === "organization" ? <OrganizationSection /> : null}
          {current === "models" ? <ModelsSection /> : null}
          {current === "integrations" ? <IntegrationsSection /> : null}
          {current === "security" ? <SecuritySection /> : null}
          {current === "privacy" ? <PrivacySection /> : null}
          {current === "developer" ? <DeveloperSection /> : null}
        </div>
      </div>
    </div>
  );
}