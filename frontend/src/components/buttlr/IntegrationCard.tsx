import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw, Unplug } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { StatusPill } from "@/components/common/StatusPill";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { formatRelative } from "@/lib/format";
import type { IntegrationCatalogEntry, IntegrationPublic } from "@/lib/types";

export function IntegrationCard({
  integration,
  entry,
  onRefresh,
  onDisconnect,
  onUpdateScopes,
  busy = false,
}: {
  integration: IntegrationPublic;
  entry?: IntegrationCatalogEntry;
  onRefresh: () => void;
  onDisconnect: () => void;
  onUpdateScopes: (resourceIds: string[]) => void;
  busy?: boolean;
}) {
  const [selected, setSelected] = useState<string[]>(() =>
    integration.resources.filter((resource) => resource.selected).map((resource) => resource.id),
  );
  const [confirmOpen, setConfirmOpen] = useState(false);
  const connected = integration.status === "connected";

  const toggle = (id: string) => {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  return (
    <article className="rounded-lg border border-border bg-card p-4">
      <header className="flex flex-wrap items-center gap-3">
        <span aria-hidden="true" className="text-2xl">
          {entry?.logo ?? "🔌"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-semibold">
              {entry?.name ?? integration.display_name}
            </h3>
            <StatusPill status={integration.status} size="sm" />
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {integration.account ?? "No account connected"}
          </p>
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
        <fieldset className="mt-4">
          <legend className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Connected resources
          </legend>
          <ul className="mt-2 space-y-1.5">
            {integration.resources.map((resource) => (
              <li key={resource.id} className="flex items-center gap-2">
                <input
                  id={`resource-${integration.id}-${resource.id}`}
                  type="checkbox"
                  className="size-4 rounded border-border accent-primary"
                  checked={selected.includes(resource.id)}
                  disabled={!connected || busy}
                  onChange={() => toggle(resource.id)}
                />
                <Label htmlFor={`resource-${integration.id}-${resource.id}`} className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{resource.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {resource.kind}
                  </span>
                </Label>
              </li>
            ))}
          </ul>
          <div className="mt-3">
            <Button
              variant="secondary"
              size="sm"
              disabled={!connected || busy}
              onClick={() => onUpdateScopes(selected)}
            >
              Save resources
            </Button>
          </div>
        </fieldset>
      ) : null}

      <footer className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRefresh()}
          loading={busy}
        >
          <RefreshCw aria-hidden="true" className="mr-1.5 size-4" />
          Refresh
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setConfirmOpen(true)}>
          <Unplug aria-hidden="true" className="mr-1.5 size-4" />
          Disconnect
        </Button>
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
        <p className="mt-3 text-xs text-muted-foreground">
          Go to <Link to="/integrations" className="text-primary hover:underline">Integrations</Link>{" "}
          to reconnect this account.
        </p>
      ) : null}
    </article>
  );
}
