import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertTriangle, ExternalLink, Info, Plug, PlugZap } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Field } from "@/components/common/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { IntegrationCard } from "@/components/buttlr/IntegrationCard";
import { useAuth } from "@/lib/auth";
import {
  useConnectToken,
  useDisconnectIntegration,
  useIntegrationCatalogue,
  useIntegrations,
  useMeta,
  useRefreshIntegration,
  useUpdateIntegrationScopes,
} from "@/lib/queries";
import { api, ApiError } from "@/lib/api";
import { providerLabel } from "@/lib/format";
import type { IntegrationCatalogEntry, IntegrationProvider, IntegrationPublic } from "@/lib/types";

type ConnectProvider = Extract<IntegrationProvider, "github" | "jira">;

interface ConnectResult {
  integration: IntegrationPublic;
  selected: string[];
}

function ConnectDialogBody({
  entry,
  organizationId,
  onClose,
}: {
  entry: IntegrationCatalogEntry;
  organizationId: string;
  onClose: () => void;
}) {
  const connect = useConnectToken(organizationId);
  const updateScopes = useUpdateIntegrationScopes(organizationId);

  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [result, setResult] = useState<ConnectResult | null>(null);

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
    try {
      const integration = await connect.mutateAsync({
        provider,
        token: token.trim(),
        ...(provider === "jira" ? { base_url: baseUrl.trim(), email: email.trim() } : {}),
      });
      const initial = integration.resources
        .filter((resource) => resource.selected)
        .map((resource) => resource.id);
      setResult({ integration, selected: initial });
      toast.success(`${entry.name} connected as ${integration.account ?? "your account"}.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : `${entry.name} could not be connected. Check the credentials and try again.`,
      );
    }
  };

  const saveScopes = async () => {
    if (!result) return;
    try {
      await updateScopes.mutateAsync({
        integrationId: result.integration.id,
        payload: { resource_ids: result.selected },
      });
      toast.success(`Saved the resources ${entry.name} can reach.`);
      onClose();
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
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
            <ul className="mt-2 max-h-64 space-y-1.5 overflow-y-auto pr-1">
              {resources.map((resource) => (
                <li key={resource.id} className="flex items-center gap-2">
                  <input
                    id={`connect-resource-${resource.id}`}
                    type="checkbox"
                    className="size-5 shrink-0 rounded border-border accent-primary"
                    checked={selected.includes(resource.id)}
                    onChange={() => toggle(resource.id)}
                  />
                  <Label htmlFor={`connect-resource-${resource.id}`} className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{resource.name}</span>
                    {resource.kind ? (
                      <span className="block truncate text-xs text-muted-foreground">{resource.kind}</span>
                    ) : null}
                  </Label>
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
          Connect
        </Button>
      </DialogFooter>
    </>
  );
}

export function IntegrationsPage() {
  const { activeOrganizationId, setActiveOrganization } = useAuth();
  const organizationId = activeOrganizationId;

  const [searchParams, setSearchParams] = useSearchParams();
  const connectedParam = searchParams.get("connected");
  const orgParam = searchParams.get("org");
  const catalogue = useIntegrationCatalogue(organizationId);
  const integrations = useIntegrations(organizationId);
  const meta = useMeta();
  const disconnect = useDisconnectIntegration(organizationId ?? "");
  const refresh = useRefreshIntegration(organizationId ?? "");
  const updateScopes = useUpdateIntegrationScopes(organizationId ?? "");

  const [connecting, setConnecting] = useState<IntegrationCatalogEntry | null>(null);
  const [googleBusy, setGoogleBusy] = useState(false);
  const handledParam = useRef<string | null>(null);

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

  const entryByProvider = useMemo(() => {
    const map = new Map<IntegrationProvider, IntegrationCatalogEntry>();
    for (const entry of catalogue.data ?? []) map.set(entry.provider, entry);
    return map;
  }, [catalogue.data]);

  const connections = integrations.data ?? [];
  const connectedProviders = new Set(connections.map((item) => item.provider));
  const available = (catalogue.data ?? []).filter((entry) => !connectedProviders.has(entry.provider));

  const startGoogleOAuth = async () => {
    if (!organizationId) return;
    setGoogleBusy(true);
    try {
      const { authorization_url } = await api.integrations.oauthStart(organizationId, "google");
      window.location.assign(authorization_url);
    } catch (error) {
      setGoogleBusy(false);
      toast.error(
        error instanceof ApiError && error.isForbidden
          ? "Only organization owners and admins can connect Google Workspace."
          : error instanceof Error && error.message
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

  const googleOAuthEnabled = meta.data?.google_oauth_enabled ?? false;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrations"
        description="Accounts Buttlrs act on your behalf. Nothing is shared until you connect and choose what to expose."
      />

      {integrations.isError ? (
        <ErrorState error={integrations.error} onRetry={() => void integrations.refetch()} />
      ) : catalogue.isError ? (
        <ErrorState error={catalogue.error} onRetry={() => void catalogue.refetch()} />
      ) : (
        <>
          <SectionCard
            title="Connected"
            description="These accounts are available to every Buttlr in this organization. Use the checkboxes to limit what each one can reach."
          >
            {connections.length === 0 ? (
              <EmptyState
                icon={PlugZap}
                title="Nothing connected yet"
                description="Connect an account below. Buttlrs that use these tools cannot run until one is connected."
              />
            ) : (
              <ul className="grid gap-4 lg:grid-cols-2">
                {connections.map((integration) => (
                  <li key={integration.id}>
                    <IntegrationCard
                      integration={integration}
                      entry={entryByProvider.get(integration.provider)}
                      busy={disconnect.isPending || refresh.isPending || updateScopes.isPending}
                      onRefresh={() => void handleRefresh(integration)}
                      onDisconnect={() => void handleDisconnect(integration)}
                      onUpdateScopes={(resourceIds) =>
                        void handleUpdateScopes(integration, resourceIds)
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard
            title="Available"
            description="Connect an account to unlock the tools it provides."
          >
            {catalogue.isLoading ? (
              <ul className="grid gap-4 lg:grid-cols-2">
                {Array.from({ length: 2 }).map((_, index) => (
                  <li key={index}>
                    <Skeleton className="h-40 w-full rounded-lg" />
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
                        <span aria-hidden="true" className="text-2xl">
                          {entry.logo}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="truncate text-sm font-semibold">{entry.name}</h3>
                            <Badge tone="muted">{entry.category}</Badge>
                            {entry.coming_soon ? <Badge tone="warning">Coming soon</Badge> : null}
                            {!entry.coming_soon && !entry.available ? (
                              <Badge tone="muted">Unavailable</Badge>
                            ) : null}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{entry.description}</p>
                        </div>
                      </header>

                      {entry.tools.length > 0 ? (
                        <p className="text-xs text-muted-foreground">
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
                      ) : isGoogle && !googleOAuthEnabled ? (
                        <Alert
                          tone="warning"
                          title="Google sign-in is not configured"
                          icon={<AlertTriangle className="size-4" />}
                        >
                          Google Workspace connects through OAuth, which needs client credentials on the
                          server. Set <code className="font-mono">GOOGLE_OAUTH_CLIENT_ID</code> and{" "}
                          <code className="font-mono">GOOGLE_OAUTH_CLIENT_SECRET</code> in the environment,
                          then restart the API. Until then this connection cannot be started.
                        </Alert>
                      ) : (
                        <div className="mt-auto">
                          <Button
                            type="button"
                            onClick={() =>
                              isGoogle
                                ? void startGoogleOAuth()
                                : setConnecting(entry as IntegrationCatalogEntry)
                            }
                            loading={isGoogle ? googleBusy : false}
                          >
                            <Plug aria-hidden="true" className="mr-1.5 size-4" />
                            {isGoogle ? "Connect with Google" : `Connect ${entry.name}`}
                          </Button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}

            <p className="mt-4 text-xs text-muted-foreground">
              Connections are encrypted at rest and scoped to this organization. The API reference for
              these endpoints is at{" "}
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline"
              >
                /docs
                <ExternalLink aria-hidden="true" className="size-3" />
              </a>
              .
            </p>
          </SectionCard>
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
              onClose={() => setConnecting(null)}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}