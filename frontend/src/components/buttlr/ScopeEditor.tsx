import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Plug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/common/EmptyState";
import { providerLabel } from "@/lib/format";
import type { AppMeta } from "@/components/buttlr/ToolPicker";
import type { IntegrationPublic, IntegrationResource } from "@/lib/types";

function readResourceIds(value: unknown): string[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const resources = record.resources;
  if (Array.isArray(resources)) return resources.filter((id): id is string => typeof id === "string");
  if (Array.isArray(record.repository_ids)) {
    return record.repository_ids.filter((id): id is string => typeof id === "string");
  }
  return [];
}

/** What each app lets you narrow down. Google has no container: the account is the scope. */
const SCOPE_NOUN: Record<string, string> = {
  github: "repositories",
  jira: "projects",
};

const SCOPE_HINT: Record<string, string> = {
  github: "GitHub tools only reach the repositories ticked here.",
  jira: "Jira tools only reach the projects ticked here.",
};

export function ScopeEditor({
  scope,
  onChange,
  integrations,
  apps = [],
  loading = false,
}: {
  scope: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  integrations: IntegrationPublic[];
  /** Catalogue names and logos; only connected apps are offered. */
  apps?: AppMeta[];
  loading?: boolean;
}) {
  const appFor = useMemo(() => new Map(apps.map((app) => [app.provider, app])), [apps]);

  const connected = integrations.filter((integration) => integration.status === "connected");

  // Two connections can share a provider (a workspace one and a personal one).
  // Scope is written per provider, so merge their resources into a single list.
  const groups = useMemo(() => {
    const byProvider = new Map<string, IntegrationResource[]>();
    for (const integration of connected) {
      const existing = byProvider.get(integration.provider);
      if (existing) existing.push(...integration.resources);
      else byProvider.set(integration.provider, [...integration.resources]);
    }
    return [...byProvider.entries()].map(([provider, resources]) => ({
      provider,
      name: appFor.get(provider)?.name ?? providerLabel(provider),
      logo: appFor.get(provider)?.logo ?? "🔌",
      resources,
      accounts: connected
        .filter((integration) => integration.provider === provider)
        .map((integration) => integration.account || integration.display_name)
        .filter((account): account is string => Boolean(account)),
    }));
  }, [connected, appFor]);

  const covered = new Set<string>(groups.map((group) => group.provider));

  const write = (provider: string, resourceIds: string[]) => {
    const next = { ...scope };
    const previous =
      scope[provider] && typeof scope[provider] === "object"
        ? (scope[provider] as Record<string, unknown>)
        : {};
    next[provider] = { ...previous, resources: resourceIds };
    onChange(next);
  };

  if (loading && groups.length === 0) {
    return (
      <p className="rounded-md border border-border border-dashed p-6 text-center text-sm text-muted-foreground">
        Checking which apps are connected…
      </p>
    );
  }

  if (groups.length === 0) {
    return (
      <EmptyState
        icon={Plug}
        title="No apps connected yet"
        description="Scope is set per connected account. Connect an app to choose which repositories and projects this Buttlr may reach — you can still save it as a draft in the meantime."
        action={
          <Button asChild size="sm">
            <Link to="/integrations">
              <Plug aria-hidden="true" />
              Connect an app
            </Link>
          </Button>
        }
      />
    );
  }

  // Anything stored under a key we cannot edit here survives untouched.
  const extraKeys = Object.keys(scope).filter((key) => !covered.has(key));

  return (
    <div className="space-y-5">
      {groups.map((group) => {
        const selected = readResourceIds(scope[group.provider]);
        const noun = SCOPE_NOUN[group.provider];
        return (
          <fieldset key={group.provider}>
            <legend className="flex min-w-0 items-center gap-2 text-sm font-medium">
              <span aria-hidden="true">{group.logo}</span>
              <span className="truncate">{group.name}</span>
            </legend>
            {group.accounts.length > 0 && SCOPE_HINT[group.provider] ? (
              <p className="text-xs text-muted-foreground">
                {group.accounts.join(" · ")} · {SCOPE_HINT[group.provider]}
              </p>
            ) : null}

            {group.resources.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {noun
                  ? `This account has not reported any ${noun} yet.`
                  : "Nothing to narrow down: the connected account is the whole of its reach."}
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {group.resources.map((resource) => (
                  <li key={`${group.provider}-${resource.id}`} className="flex items-center gap-2">
                    <input
                      id={`scope-${group.provider}-${resource.id}`}
                      type="checkbox"
                      className="size-4 shrink-0 rounded border-border accent-primary"
                      checked={selected.includes(resource.id)}
                      onChange={() =>
                        write(
                          group.provider,
                          selected.includes(resource.id)
                            ? selected.filter((id) => id !== resource.id)
                            : [...selected, resource.id],
                        )
                      }
                    />
                    <Label
                      htmlFor={`scope-${group.provider}-${resource.id}`}
                      className="min-w-0 flex-1"
                    >
                      <span className="block truncate text-sm">{resource.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {resource.kind}
                      </span>
                    </Label>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
        );
      })}

      {extraKeys.length > 0 ? (
        <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
          <p className="font-medium text-foreground">Other scope keys</p>
          <p className="mt-1 text-muted-foreground">
            These keys are stored but not editable here. They are preserved exactly as written:{" "}
            {extraKeys.join(", ")}.
          </p>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">
            {JSON.stringify(
              Object.fromEntries(extraKeys.map((key) => [key, scope[key]])),
              null,
              2,
            )}
          </pre>
        </div>
      ) : null}
    </div>
  );
}