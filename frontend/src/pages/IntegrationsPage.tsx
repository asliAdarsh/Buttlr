import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ChevronDown,
  ExternalLink,
  Info,
  Plug,
  PlugZap,
} from "lucide-react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CopyButton } from "@/components/common/CopyButton";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Field } from "@/components/common/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { IntegrationCard } from "@/components/buttlr/IntegrationCard";
import { useAuth } from "@/lib/auth";
import {
  useClearOauthClient,
  useConnectToken,
  useDisconnectIntegration,
  useIntegrationCatalogue,
  useIntegrations,
  useMembers,
  useOauthClients,
  useRefreshIntegration,
  useSetOauthClient,
  useUpdateIntegrationScopes,
} from "@/lib/queries";
import { api } from "@/lib/api";
import { providerLabel } from "@/lib/format";
import type {
  IntegrationCatalogEntry,
  IntegrationProvider,
  IntegrationPublic,
  IntegrationScope,
  OAuthClientPublic,
} from "@/lib/types";

type ConnectProvider = Extract<IntegrationProvider, "github" | "jira">;
type OAuthProvider = Extract<IntegrationProvider, "github" | "google">;

const OAUTH_PROVIDERS: OAuthProvider[] = ["github", "google"];

interface ConnectResult {
  integration: IntegrationPublic;
  selected: string[];
}

/**
 * Who a new connection belongs to. The second option only exists for owners and admins —
 * the API rejects it for everyone else.
 */
function ScopeChoice({
  idPrefix,
  value,
  onChange,
  canShare,
  disabled = false,
}: {
  idPrefix: string;
  value: IntegrationScope;
  onChange: (scope: IntegrationScope) => void;
  canShare: boolean;
  disabled?: boolean;
}) {
  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Who can use this account
      </legend>
      <div className="space-y-2">
        <label
          htmlFor={`${idPrefix}-personal`}
          className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
            value === "personal"
              ? "border-primary bg-primary/5 ring-1 ring-primary"
              : "border-border hover:bg-muted"
          }`}
        >
          <input
            id={`${idPrefix}-personal`}
            type="radio"
            name={`${idPrefix}-scope`}
            className="mt-0.5 size-4 shrink-0 accent-primary"
            checked={value === "personal"}
            onChange={() => onChange("personal")}
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium leading-5">Just me</span>
            <span className="block text-xs leading-4 text-muted-foreground">
              Connected to your account. Only your Buttlrs use it.
            </span>
          </span>
        </label>
        {canShare ? (
          <label
            htmlFor={`${idPrefix}-organization`}
            className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
              value === "organization"
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border hover:bg-muted"
            }`}
          >
            <input
              id={`${idPrefix}-organization`}
              type="radio"
              name={`${idPrefix}-scope`}
              className="mt-0.5 size-4 shrink-0 accent-primary"
              checked={value === "organization"}
              onChange={() => onChange("organization")}
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium leading-5">Everyone in the workspace</span>
              <span className="block text-xs leading-4 text-muted-foreground">
                One shared account every member&apos;s Buttlrs can use. Owners and admins manage it.
              </span>
            </span>
          </label>
        ) : null}
      </div>
    </fieldset>
  );
}

function ConnectDialogBody({
  entry,
  organizationId,
  canShare,
  onClose,
}: {
  entry: IntegrationCatalogEntry;
  organizationId: string;
  canShare: boolean;
  onClose: () => void;
}) {
  const connect = useConnectToken(organizationId);
  const updateScopes = useUpdateIntegrationScopes(organizationId);

  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [scope, setScope] = useState<IntegrationScope>("personal");
  const [result, setResult] = useState<ConnectResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const provider = entry.provider as ConnectProvider;
  const resources = result?.integration.resources ?? [];
  const selected = result?.selected ?? [];

  const toggle = (id: string) => {
    if (!result) return;
    setResult({
      ...result,
      selected: result.selected.includes(id)
        ? result.selected.filter((item) => item !== id)
        : [...result.selected, id],
    });
  };

  const submit = async () => {
    setError(null);
    try {
      const integration = await connect.mutateAsync({
        provider,
        token: token.trim(),
        scope,
        ...(provider === "jira" ? { base_url: baseUrl.trim(), email: email.trim() } : {}),
      });
      const initial = integration.resources
        .filter((resource) => resource.selected)
        .map((resource) => resource.id);
      setResult({ integration, selected: initial });
      toast.success(
        scope === "organization"
          ? `${entry.name} connected for the whole workspace.`
          : `${entry.name} connected as ${integration.account ?? "your account"}.`,
      );
    } catch (caught) {
      // Persisted next to the fields: a toast would vanish while the dialog stays open, and
      // the user still has a token to fix.
      setError(
        caught instanceof Error && caught.message
          ? caught.message
          : `${entry.name} could not be connected. Check the credentials and try again.`,
      );
    }
  };

  const saveScopes = async () => {
    if (!result) return;
    setError(null);
    try {
      await updateScopes.mutateAsync({
        integrationId: result.integration.id,
        payload: { resource_ids: result.selected },
      });
      toast.success(`Saved the resources ${entry.name} can reach.`);
      onClose();
    } catch (caught) {
      setError(
        caught instanceof Error && caught.message
          ? caught.message
          : "The selected resources could not be saved.",
      );
    }
  };

  if (result) {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Choose what {entry.name} can reach</DialogTitle>
          <DialogDescription>
            A Buttlr only sees the {entry.name.toLowerCase()} items you select here. Nothing is shared until
            you save.
          </DialogDescription>
        </DialogHeader>

        {resources.length === 0 ? (
          <Alert tone="info" className="mt-4">
            No items were discovered for this account. Save to continue — you can pick items later from the
            connection card.
          </Alert>
        ) : (
          <fieldset className="mt-4">
            <legend className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {provider === "github" ? "Repositories" : "Resources"}
            </legend>
            <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto pr-1">
              {resources.map((resource) => (
                <li key={resource.id}>
                  <label
                    htmlFor={`connect-resource-${resource.id}`}
                    className="flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 hover:bg-muted"
                  >
                    <input
                      id={`connect-resource-${resource.id}`}
                      type="checkbox"
                      className="size-5 shrink-0 rounded border-border accent-primary"
                      checked={selected.includes(resource.id)}
                      onChange={() => toggle(resource.id)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm leading-5">{resource.name}</span>
                      {resource.kind ? (
                        <span className="block truncate text-xs leading-4 text-muted-foreground">
                          {resource.kind}
                        </span>
                      ) : null}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        )}

        {resources.length > 0 && selected.length === 0 ? (
          <Alert
            tone="warning"
            className="mt-3"
            icon={<AlertTriangle className="size-4" />}
            title="Nothing is selected"
          >
            With no items selected, Buttlrs will connect but every tool call will fail until you pick at
            least one.
          </Alert>
        ) : null}

        {error ? (
          <Alert
            tone="destructive"
            className="mt-3"
            icon={<AlertTriangle className="size-4" />}
            title="That didn't work"
          >
            {error}
          </Alert>
        ) : null}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={updateScopes.isPending}>
            Skip for now
          </Button>
          <Button type="button" onClick={() => void saveScopes()} loading={updateScopes.isPending}>
            Save {selected.length > 0 ? `${selected.length} selected` : "empty selection"}
          </Button>
        </DialogFooter>
      </>
    );
  }
  return (
    <>
      <DialogHeader>
        <DialogTitle>Connect {entry.name}</DialogTitle>
        <DialogDescription>{entry.description}</DialogDescription>
      </DialogHeader>

      <div className="mt-4 space-y-4">
        <ScopeChoice
          idPrefix={`connect-${provider}`}
          value={scope}
          onChange={setScope}
          canShare={canShare}
        />

        {provider === "github" ? (
          <Field
            label="Personal access token"
            htmlFor="github-token"
            required
            hint="A fine-grained token with read access to the repositories you want a Buttlr to work in is enough. The token is stored encrypted and never shown again."
          >
            <Input
              id="github-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="github_pat_…"
            />
          </Field>
        ) : (
          <>
            <Field
              label="Site URL"
              htmlFor="jira-base-url"
              required
              hint="Your Jira site, for example https://yourteam.atlassian.net"
            >
              <Input
                id="jira-base-url"
                type="url"
                inputMode="url"
                autoComplete="off"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder="https://yourteam.atlassian.net"
              />
            </Field>
            <Field label="Email" htmlFor="jira-email" required hint="The address on your Jira account.">
              <Input
                id="jira-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
              />
            </Field>
            <Field
              label="API token"
              htmlFor="jira-token"
              required
              hint="Create one in Jira under your profile → Security → API tokens."
            >
              <Input
                id="jira-token"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(event) => setToken(event.target.value)}
              />
            </Field>
          </>
        )}
      </div>

      {error ? (
        <Alert
          tone="destructive"
          className="mt-4"
          icon={<AlertTriangle className="size-4" />}
          title={`${entry.name} could not be connected`}
        >
          {error}
        </Alert>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={connect.isPending}>
          Cancel
        </Button>
        <Button
          type="button"
          onClick={() => void submit()}
          loading={connect.isPending}
          disabled={token.trim().length < 8 || (provider === "jira" && (!baseUrl.trim() || !email.trim()))}
        >
          {scope === "organization" ? "Connect for the workspace" : "Connect"}
        </Button>
      </DialogFooter>
    </>
  );
}

/**
 * Register the workspace's own OAuth app, so connecting a provider needs no deployment secret.
 * The redirect URI shown here is the one the server will accept the callback on.
 */
function OAuthAppForm({
  provider,
  client,
  organizationId,
}: {
  provider: OAuthProvider;
  client: OAuthClientPublic | undefined;
  organizationId: string;
}) {
  const setClient = useSetOauthClient(organizationId);
  const clearClient = useClearOauthClient(organizationId);

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);

  const name = providerLabel(provider);
  const hasWorkspaceApp = client?.source === "workspace";
  // The server owns this value: it is the same URL it will accept the callback on.
  const redirectUri = client?.redirect_uri ?? "";

  const save = async () => {
    try {
      await setClient.mutateAsync({
        provider,
        payload: {
          client_id: clientId.trim(),
          client_secret: clientSecret.trim() || undefined,
        },
      });
      setClientId("");
      setClientSecret("");
      toast.success(`This workspace now signs in to ${name} with its own OAuth app.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : `The ${name} OAuth app could not be saved.`,
      );
    }
  };

  const remove = async () => {
    setConfirmRemove(false);
    try {
      await clearClient.mutateAsync(provider);
      toast.success(`Removed this workspace's ${name} OAuth app.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : `The ${name} OAuth app could not be removed.`,
      );
    }
  };

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold leading-5">{name}</h3>
        {client?.configured ? (
          <Badge tone={hasWorkspaceApp ? "primary" : "muted"}>
            {hasWorkspaceApp ? "This workspace's own app" : "This deployment's app"}
          </Badge>
        ) : (
          <Badge tone="warning">No OAuth app</Badge>
        )}
      </div>

      {client?.configured && !hasWorkspaceApp ? (
        <p className="mt-1 text-xs leading-4 text-muted-foreground">
          Using this deployment&apos;s app
          {client.masked_client_id ? ` (${client.masked_client_id})` : ""}. Register your own below
          to use a workspace app instead.
        </p>
      ) : client?.configured ? (
        <p className="mt-1 text-xs leading-4 text-muted-foreground">
          Saved for this workspace
          {client.masked_client_id ? ` (${client.masked_client_id})` : ""}. The secret is stored
          encrypted and never shown again.
        </p>
      ) : (
        <p className="mt-1 text-xs leading-4 text-muted-foreground">
          {name} sign-in needs an OAuth app. Without one, {name} cannot be connected here.
        </p>
      )}

      <div className="mt-4 space-y-4">
        <Field
          label="Redirect URI"
          htmlFor={`oauth-redirect-${provider}`}
          hint="Copy this into the OAuth app's callback URL field. It must match exactly."
        >
          <div className="flex items-center gap-2">
            <Input
              id={`oauth-redirect-${provider}`}
              readOnly
              value={redirectUri}
              onFocus={(event) => event.currentTarget.select()}
              className="min-w-0 flex-1 font-mono text-xs"
            />
            <CopyButton value={redirectUri} label="Copy" className="shrink-0" />
          </div>
        </Field>

        <Field
          label="Client ID"
          htmlFor={`oauth-client-id-${provider}`}
          required
          hint={hasWorkspaceApp ? "Enter a new client ID to replace the saved one." : undefined}
        >
          <Input
            id={`oauth-client-id-${provider}`}
            autoComplete="off"
            spellCheck={false}
            value={clientId}
            onChange={(event) => setClientId(event.target.value)}
          />
        </Field>

        <Field
          label="Client secret"
          htmlFor={`oauth-client-secret-${provider}`}
          required={!hasWorkspaceApp}
          hint={
            hasWorkspaceApp
              ? "Leave this empty to keep the secret already saved."
              : "From the OAuth app's settings. Stored encrypted, never shown again."
          }
        >
          <Input
            id={`oauth-client-secret-${provider}`}
            type="password"
            autoComplete="off"
            value={clientSecret}
            onChange={(event) => setClientSecret(event.target.value)}
          />
        </Field>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => void save()}
          loading={setClient.isPending}
          disabled={clientId.trim().length === 0}
        >
          Save
        </Button>
        {hasWorkspaceApp ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setConfirmRemove(true)}
            disabled={clearClient.isPending}
          >
            Remove
          </Button>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title={`Remove this workspace's ${name} OAuth app?`}
        description="Sign-in for this workspace falls back to the deployment's app. Existing connections keep working."
        confirmLabel="Remove"
        destructive
        loading={clearClient.isPending}
        onConfirm={() => void remove()}
      />
    </div>
  );
}

function OAuthAppsSection({
  organizationId,
  open,
  onOpenChange,
}: {
  organizationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const clients = useOauthClients(organizationId);

  return (
    <SectionCard
      title="OAuth apps"
      description="Connecting a Google or GitHub account with sign-in needs an OAuth app. A workspace can register its own here instead of using the one this deployment ships with."
      actions={
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onOpenChange(!open)}
          aria-expanded={open}
          aria-controls="oauth-apps-body"
        >
          <ChevronDown
            aria-hidden="true"
            className={`size-4 transition-transform ${open ? "rotate-180" : ""}`}
          />
          {open ? "Hide" : "Show"}
        </Button>
      }
    >
      <div id="oauth-apps-body" hidden={!open} className="space-y-4">
        <div className="rounded-lg border border-border bg-muted/40 p-3 text-xs leading-4 text-muted-foreground">
          <p className="font-medium text-foreground">How to get these two values</p>
          <ol className="mt-2 list-decimal space-y-1 pl-4">
            <li>
              <span className="font-medium text-foreground">Google</span>: Google Cloud Console →
              APIs &amp; Services → Credentials → <em>Create credentials</em> → <em>OAuth client ID</em> →
              Web application. Add the redirect URI shown below to it, exactly.
            </li>
            <li>
              <span className="font-medium text-foreground">GitHub</span>: Settings → Developer
              settings → OAuth Apps → <em>New OAuth App</em>, and paste the redirect URI shown below
              as the callback URL.
            </li>
            <li>Paste the client ID and secret here, then press Connect on the app above.</li>
          </ol>
          <p className="mt-2">
            Already on Firebase? Its Google sign-in provider <em>is</em> a Google OAuth client:
            Firebase console → Authentication → Sign-in method → Google → Web SDK configuration
            gives you a client ID and secret you can use here (add the redirect URI to that client
            in Google Cloud).
          </p>
        </div>
        {clients.isLoading ? (
          <div className="space-y-4">
            {OAUTH_PROVIDERS.map((provider) => (
              <Skeleton key={provider} className="h-96 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {OAUTH_PROVIDERS.map((provider) => (
              <OAuthAppForm
                key={provider}
                provider={provider}
                organizationId={organizationId}
                client={(clients.data ?? []).find((item) => item.provider === provider)}
              />
            ))}
          </div>
        )}
      </div>
    </SectionCard>
  );
}

export function IntegrationsPage() {
  const { activeOrganizationId, setActiveOrganization, user } = useAuth();
  const organizationId = activeOrganizationId;

  const [searchParams, setSearchParams] = useSearchParams();
  const connectedParam = searchParams.get("connected");
  const orgParam = searchParams.get("org");
  const oauthErrorParam = searchParams.get("oauth_error");
  const catalogue = useIntegrationCatalogue(organizationId);
  const integrations = useIntegrations(organizationId);
  const members = useMembers(organizationId);
  const clients = useOauthClients(organizationId);
  const disconnect = useDisconnectIntegration(organizationId ?? "");
  const refresh = useRefreshIntegration(organizationId ?? "");
  const updateScopes = useUpdateIntegrationScopes(organizationId ?? "");

  const [connecting, setConnecting] = useState<IntegrationCatalogEntry | null>(null);
  const [googleScope, setGoogleScope] = useState<IntegrationScope>("personal");
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [oauthOpen, setOauthOpen] = useState(false);
  const handledParam = useRef<string | null>(null);

  // A provider can bounce the user back with a reason (a wrong client secret, an unregistered
  // redirect URI). Show it where they are, and keep it until they dismiss it.
  const clearOauthError = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("oauth_error");
    setSearchParams(params, { replace: true });
  };

  const openOauthApps = () => {
    setOauthOpen(true);
    window.requestAnimationFrame(() => {
      document.getElementById("oauth-apps-body")?.scrollIntoView({ block: "center" });
    });
  };

  // The OAuth callback lands back here with ?connected=<provider>&org=<organizationId>. Follow the
  // organization it connected for, then clear both parameters.
  useEffect(() => {
    if (!connectedParam) return;
    if (handledParam.current === connectedParam) return;
    handledParam.current = connectedParam;
    toast.success(
      `${providerLabel(connectedParam)} finished connecting. Choose what it can reach below.`,
    );
    if (orgParam && orgParam !== activeOrganizationId) setActiveOrganization(orgParam);
    void integrations.refetch();
    void catalogue.refetch();
    const params = new URLSearchParams(searchParams);
    params.delete("connected");
    params.delete("org");
    setSearchParams(params, { replace: true });
  }, [
    connectedParam,
    orgParam,
    activeOrganizationId,
    setActiveOrganization,
    integrations,
    catalogue,
    searchParams,
    setSearchParams,
  ]);

  const role = (members.data ?? []).find((member) => member.user_id === user?.id)?.role;
  const isAdmin = role === "owner" || role === "admin";

  const entryByProvider = useMemo(() => {
    const map = new Map<IntegrationProvider, IntegrationCatalogEntry>();
    for (const entry of catalogue.data ?? []) map.set(entry.provider, entry);
    return map;
  }, [catalogue.data]);

  const oauthClientByProvider = useMemo(() => {
    const map = new Map<IntegrationProvider, OAuthClientPublic>();
    for (const item of clients.data ?? []) map.set(item.provider, item);
    return map;
  }, [clients.data]);

  const connections = integrations.data ?? [];
  const connectedProviders = new Set(connections.map((item) => item.provider));
  const available = (catalogue.data ?? []).filter((entry) => !connectedProviders.has(entry.provider));
  const sharedConnections = connections.filter((item) => item.scope !== "personal");
  const personalConnections = connections.filter((item) => item.scope === "personal");
  // The empty state's one action: the first catalogue entry the connect dialog can actually open
  // (Google goes through OAuth instead, and unlaunched entries have nothing to connect).
  const firstConnectable =
    available.find((entry) => entry.provider !== "google" && entry.available && !entry.coming_soon) ??
    null;

  const startGoogleOAuth = async () => {
    if (!organizationId) return;
    setGoogleBusy(true);
    setGoogleError(null);
    try {
      const { authorization_url } = await api.integrations.oauthStart(
        organizationId,
        "google",
        googleScope,
      );
      window.location.assign(authorization_url);
    } catch (error) {
      setGoogleBusy(false);
      setGoogleError(
        error instanceof Error && error.message
          ? error.message
          : "Google sign-in could not be started.",
      );
    }
  };

  const handleDisconnect = async (integration: IntegrationPublic) => {
    try {
      await disconnect.mutateAsync(integration.id);
      toast.success(`${integration.display_name} disconnected.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The connection could not be removed.",
      );
    }
  };

  const handleRefresh = async (integration: IntegrationPublic) => {
    try {
      await refresh.mutateAsync(integration.id);
      toast.success(`${integration.display_name} refreshed.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The connection could not be refreshed.",
      );
    }
  };

  const handleUpdateScopes = async (integration: IntegrationPublic, resourceIds: string[]) => {
    try {
      await updateScopes.mutateAsync({ integrationId: integration.id, payload: { resource_ids: resourceIds } });
      toast.success(`${integration.display_name} resources saved.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The selected resources could not be saved.",
      );
    }
  };

  const busy = disconnect.isPending || refresh.isPending || updateScopes.isPending;

  const renderConnection = (integration: IntegrationPublic) => (
    <li key={integration.id}>
      <IntegrationCard
        integration={integration}
        entry={entryByProvider.get(integration.provider)}
        busy={busy}
        canManage={
          isAdmin || (integration.scope === "personal" && integration.owner_id === user?.id)
        }
        oauthClient={oauthClientByProvider.get(integration.provider) ?? null}
        onRefresh={() => void handleRefresh(integration)}
        onDisconnect={() => void handleDisconnect(integration)}
        onUpdateScopes={(resourceIds) => void handleUpdateScopes(integration, resourceIds)}
      />
    </li>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrations"
        description="Accounts Buttlrs act on your behalf. Connect your own; owners and admins can also connect one shared account for the workspace."
      />

      {oauthErrorParam ? (
        <Alert tone="destructive" title="That connection did not finish">
          <div className="space-y-3">
            <p>{oauthErrorParam}</p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" onClick={openOauthApps}>
                Set up the OAuth app
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={clearOauthError}>
                Dismiss
              </Button>
            </div>
          </div>
        </Alert>
      ) : null}

      {integrations.isError ? (
        <ErrorState error={integrations.error} onRetry={() => void integrations.refetch()} />
      ) : catalogue.isError ? (
        <ErrorState error={catalogue.error} onRetry={() => void catalogue.refetch()} />
      ) : (
        <>
          {connections.length === 0 ? (
            <SectionCard
              title="Connected"
              description="Accounts available to the Buttlrs in this organization."
            >
              <EmptyState
                icon={PlugZap}
                title="Nothing connected yet"
                description="Connect an account below. Buttlrs that use these tools cannot run until one is connected."
                action={
                  firstConnectable ? (
                    <Button
                      type="button"
                      onClick={() => setConnecting(firstConnectable)}
                      className="min-h-11 sm:min-h-0"
                    >
                      <Plug aria-hidden="true" className="mr-1.5 size-4" />
                      Connect {firstConnectable.name}
                    </Button>
                  ) : null
                }
              />
            </SectionCard>
          ) : null}

          {sharedConnections.length > 0 ? (
            <SectionCard
              title="Shared with the workspace"
              description="One account every member's Buttlrs can use. Owners and admins manage it."
            >
              <ul className="grid gap-4 lg:grid-cols-2">
                {sharedConnections.map(renderConnection)}
              </ul>
            </SectionCard>
          ) : null}

          {personalConnections.length > 0 ? (
            <SectionCard
              title="Your connections"
              description="Accounts connected by each person. A Buttlr only uses the connections of the person it belongs to."
            >
              <ul className="grid gap-4 lg:grid-cols-2">
                {personalConnections.map(renderConnection)}
              </ul>
            </SectionCard>
          ) : null}

          <SectionCard
            title="Available"
            description="Connect an account to unlock the tools it provides."
          >
            {catalogue.isLoading ? (
              <ul className="grid gap-4 lg:grid-cols-2">
                {Array.from({ length: 2 }).map((_, index) => (
                  <li key={index}>
                    <Skeleton className="h-52 w-full rounded-lg" />
                  </li>
                ))}
              </ul>
            ) : available.length === 0 ? (
              <EmptyState
                icon={Plug}
                title="Every available integration is connected"
                description="Disconnect one above if a Buttlr needs a different account."
              />
            ) : (
              <ul className="grid gap-4 lg:grid-cols-2">
                {available.map((entry) => {
                  const isGoogle = entry.provider === "google";
                  return (
                    <li
                      key={entry.provider}
                      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
                    >
                      <header className="flex items-start gap-3">
                        <span aria-hidden="true" className="text-2xl leading-none">
                          {entry.logo}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="truncate text-sm font-semibold leading-5">{entry.name}</h3>
                            <Badge tone="muted">{entry.category}</Badge>
                            {entry.coming_soon ? <Badge tone="warning">Coming soon</Badge> : null}
                            {!entry.coming_soon && !entry.available ? (
                              <Badge tone="muted">Unavailable</Badge>
                            ) : null}
                          </div>
                          <p className="mt-1 text-sm leading-5 text-muted-foreground">
                            {entry.description}
                          </p>
                        </div>
                      </header>

                      {entry.tools.length > 0 ? (
                        <p className="text-xs leading-4 text-muted-foreground">
                          Unlocks {entry.tools.length} {entry.tools.length === 1 ? "tool" : "tools"}:{" "}
                          {entry.tools.slice(0, 4).join(", ")}
                          {entry.tools.length > 4 ? ", …" : ""}
                        </p>
                      ) : null}

                      {entry.coming_soon || !entry.available ? (
                        <Alert tone="info" icon={<Info aria-hidden="true" className="size-4" />}>
                          {entry.coming_soon
                            ? `${entry.name} is not ready to connect on this deployment yet.`
                            : `${entry.name} cannot be connected right now. Check the API logs for the reason.`}
                        </Alert>
                      ) : isGoogle ? (
                        <>
                          <ScopeChoice
                            idPrefix="google"
                            value={googleScope}
                            onChange={setGoogleScope}
                            canShare={isAdmin}
                            disabled={googleBusy}
                          />
                          {googleError ? (
                            <Alert tone="warning" title="Google sign-in could not start">
                              <div className="space-y-3">
                                <p>{googleError}</p>
                                {isAdmin ? (
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={openOauthApps}
                                  >
                                    Set up the OAuth app
                                  </Button>
                                ) : null}
                              </div>
                            </Alert>
                          ) : null}
                          <div className="mt-auto">
                            <Button
                              type="button"
                              onClick={() => void startGoogleOAuth()}
                              loading={googleBusy}
                            >
                              <Plug aria-hidden="true" className="mr-1.5 size-4" />
                              Connect with Google
                            </Button>
                          </div>
                        </>
                      ) : (
                        <div className="mt-auto">
                          <Button
                            type="button"
                            onClick={() => setConnecting(entry as IntegrationCatalogEntry)}
                          >
                            <Plug aria-hidden="true" className="mr-1.5 size-4" />
                            Connect {entry.name}
                          </Button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}

            <p className="mt-4 text-xs leading-4 text-muted-foreground">
              Connections are encrypted at rest and scoped to this organization. The API reference for
              these endpoints is at{" "}
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              >
                /docs
                <ExternalLink aria-hidden="true" className="size-3" />
              </a>
              .
            </p>
          </SectionCard>

          {isAdmin && organizationId ? (
            <OAuthAppsSection
              organizationId={organizationId}
              open={oauthOpen}
              onOpenChange={setOauthOpen}
            />
          ) : null}
        </>
      )}

      <Dialog
        open={connecting !== null}
        onOpenChange={(open) => {
          if (!open) setConnecting(null);
        }}
      >
        <DialogContent>
          {connecting && organizationId ? (
            <ConnectDialogBody
              key={connecting.provider}
              entry={connecting}
              organizationId={organizationId}
              canShare={isAdmin}
              onClose={() => setConnecting(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}