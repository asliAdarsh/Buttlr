import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw, Unplug } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { StatusPill } from "@/components/common/StatusPill";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { formatRelative, providerLabel } from "@/lib/format";
import type {
  IntegrationCatalogEntry,
  IntegrationPublic,
  OAuthClientPublic,
} from "@/lib/types";

const MANAGE_HINT = "Only the account's owner or an organisation admin can manage this connection";

export function IntegrationCard({
  integration,
  entry,
  onRefresh,
  onDisconnect,
  onUpdateScopes,
  busy = false,
  canManage = true,
  oauthClient = null,
}: {
  integration: IntegrationPublic;
  entry?: IntegrationCatalogEntry;
  onRefresh: () => void;
  onDisconnect: () => void;
  onUpdateScopes: (resourceIds: string[]) => void;
  busy?: boolean;
  canManage?: boolean;
  oauthClient?: OAuthClientPublic | null;
}) {

  const [selected, setSelected] = useState<string[]>(() =>
    integration.resources.filter((resource) => resource.selected).map((resource) => resource.id),
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const connected = integration.status === "connected";
  const readOnly = !canManage;
  const owner = integration.owner_name?.trim();

  // A wrapped span keeps the tooltip reachable by keyboard around a disabled button.
  const guarded = (label: string, node: ReactNode) => (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex" tabIndex={0} aria-label={`${label} — ${MANAGE_HINT}`}>
          {node}
        </span>
      </TooltipTrigger>
      <TooltipContent>{MANAGE_HINT}</TooltipContent>
    </Tooltip>
  );

  const toggle = (id: string) => {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  return (
    <article className="flex flex-col rounded-lg border border-border bg-card p-4">
      <header className="flex flex-wrap items-center gap-3">
        <span aria-hidden="true" className="text-2xl leading-none">
          {entry?.logo ?? "🔌"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              {entry?.name ?? integration.display_name}
            </h3>
            <StatusPill status={integration.status} size="sm" />
            {integration.scope === "personal" ? (
              <Badge tone="muted">{owner ? `${owner}'s account` : "Your account"}</Badge>
            ) : (
              <Badge tone="primary">Shared with the workspace</Badge>
            )}
          </div>
          <p className="truncate text-xs leading-4 text-muted-foreground">
            {integration.account ?? "No account connected"}
          </p>
          {oauthClient ? (
            <p className="mt-1 text-xs leading-4 text-muted-foreground">
              {oauthClient.configured
                ? oauthClient.source === "workspace"
                  ? `Sign-in uses this workspace's own ${providerLabel(integration.provider)} app`
                  : `Sign-in uses this deployment's ${providerLabel(integration.provider)} app`
                : `${providerLabel(integration.provider)} sign-in is not configured for this workspace`}
            </p>
          ) : null}
        </div>
      </header>

      {integration.error ? (
        <Alert tone="destructive" className="mt-3" icon={<AlertTriangle className="size-4" />}>
          {integration.error}
        </Alert>
      ) : null}

      {integration.scopes.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {integration.scopes.map((scope) => (
            <Badge key={scope} tone="outline" className="font-normal">
              {scope}
            </Badge>
          ))}
        </div>
      ) : null}

      {!connected ? (
        <Alert tone="warning" className="mt-3" icon={<AlertTriangle className="size-4" />} title="Reconnect required">
          {integration.status === "expired"
            ? "The access grant expired. Reconnect to let this Buttlr use the account again."
            : "This account is not connected. Reconnect it before running anything that uses these tools."}
        </Alert>
      ) : null}

      {integration.resources.length > 0 ? (
        <fieldset className="mt-5">
          <legend className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Connected resources
          </legend>
          <ul className="mt-2 space-y-1">
            {integration.resources.map((resource) => (
              <li
                key={resource.id}
                className="flex min-h-11 items-center gap-3 rounded-md px-1 py-1 hover:bg-muted/40 sm:min-h-0 sm:px-0"
              >
                <input
                  id={`resource-${integration.id}-${resource.id}`}
                  type="checkbox"
                  className="size-4 shrink-0 cursor-pointer rounded border-border accent-primary disabled:cursor-not-allowed"
                  checked={selected.includes(resource.id)}
                  disabled={readOnly || !connected || busy}
                  onChange={() => toggle(resource.id)}
                />
                <Label
                  htmlFor={`resource-${integration.id}-${resource.id}`}
                  className="min-w-0 flex-1 cursor-pointer"
                >
                  <span className="block truncate text-sm">{resource.name}</span>
                  <span className="block truncate text-xs leading-4 text-muted-foreground">
                    {resource.kind}
                  </span>
                </Label>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {readOnly ? (
              guarded(
                "Save resources",
                <Button variant="secondary" size="sm" disabled>
                  Save resources
                </Button>,
              )
            ) : (
              <Button
                variant="secondary"
                size="sm"
                disabled={!connected || busy}
                onClick={() => onUpdateScopes(selected)}
              >
                Save resources
              </Button>
            )}
            {readOnly ? (
              <span className="text-xs leading-4 text-muted-foreground">{MANAGE_HINT}</span>
            ) : null}
          </div>
        </fieldset>
      ) : null}

      <footer className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
        {readOnly ? (
          guarded(
            "Refresh",
            <Button variant="outline" size="sm" disabled>
              <RefreshCw aria-hidden="true" className="mr-1.5 size-4" />
              Refresh
            </Button>,
          )
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRefresh()}
            loading={busy}
          >
            <RefreshCw aria-hidden="true" className="mr-1.5 size-4" />
            Refresh
          </Button>
        )}
        {readOnly ? (
          guarded(
            "Disconnect",
            <Button variant="ghost" size="sm" disabled>
              <Unplug aria-hidden="true" className="mr-1.5 size-4" />
              Disconnect
            </Button>,
          )
        ) : (
          <Button variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
            <Unplug aria-hidden="true" className="mr-1.5 size-4" />
            Disconnect
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          Last used {formatRelative(integration.last_used_at)}
        </span>
      </footer>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Disconnect ${integration.display_name}?`}
        description="Buttlrs that rely on these tools will stop working until the account is connected again."
        confirmLabel="Disconnect"
        destructive
        loading={busy}
        onConfirm={() => {
          setConfirmOpen(false);
          onDisconnect();
        }}
      />

      {!connected ? (
        <p className="mt-3 text-xs leading-4 text-muted-foreground">
          Go to <Link to="/integrations" className="text-primary hover:underline">Integrations</Link>{" "}
          to reconnect this account.
        </p>
      ) : null}
    </article>
  );
}
