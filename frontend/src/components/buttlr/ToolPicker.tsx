import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Lock, Plug, PlugZap, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/common/EmptyState";
import { RiskBadge } from "@/components/common/RiskBadge";
import { providerLabel, toolLabel } from "@/lib/format";
import type {
  IntegrationCatalogEntry,
  IntegrationPublic,
  ToolDescription,
} from "@/lib/types";

/** Everything the picker needs to name an app and say whether it can be used. */
export interface AppMeta {
  provider: string;
  name: string;
  logo: string;
  connected: boolean;
}

/** Tools that need no connected account of their own. */
const BUILTIN_GROUP = "builtin";

/**
 * One row per app in the catalogue: its display name, its logo, and whether this
 * workspace has a live connection to it. Shared and personal connections both
 * count, because either one can answer a call.
 */
export function describeApps(
  catalogue: IntegrationCatalogEntry[],
  integrations: IntegrationPublic[],
): AppMeta[] {
  const connected = new Set(
    integrations.filter((item) => item.status === "connected").map((item) => item.provider),
  );
  const meta = new Map<string, AppMeta>();
  for (const provider of [
    ...catalogue.map((entry) => entry.provider),
    ...integrations.map((item) => item.provider),
  ]) {
    if (meta.has(provider)) continue;
    const entry = catalogue.find((item) => item.provider === provider);
    meta.set(provider, {
      provider,
      name: entry?.name || providerLabel(provider),
      logo: entry?.logo || "🔌",
      connected: connected.has(provider),
    });
  }
  return [...meta.values()];
}

/**
 * Splits the catalogue in two: the work a connected app can actually do, and the
 * work that is already selected but unreachable because its app is not connected.
 * The second list is never dropped — the user has to be able to see and remove it.
 */
export function resolveToolChoices(
  tools: ToolDescription[],
  apps: AppMeta[],
  selected: string[],
): { available: ToolDescription[]; detached: ToolDescription[] } {
  const connected = new Set(apps.filter((app) => app.connected).map((app) => app.provider));
  const chosen = new Set(selected);
  const available: ToolDescription[] = [];
  const detached: ToolDescription[] = [];
  for (const tool of tools) {
    if (!tool.integration || connected.has(tool.integration)) available.push(tool);
    else if (chosen.has(tool.name)) detached.push(tool);
  }
  return { available, detached };
}

function ToolRow({
  tool,
  checked,
  disabled,
  onToggle,
}: {
  tool: ToolDescription;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <li className="flex items-start gap-3 rounded-md px-1 py-1 hover:bg-muted/40 sm:px-0">
      <input
        id={`tool-${tool.name}`}
        type="checkbox"
        className="mt-1 size-4 shrink-0 cursor-pointer rounded border-border accent-primary disabled:cursor-not-allowed"
        checked={checked}
        disabled={disabled}
        onChange={onToggle}
      />
      <Label htmlFor={`tool-${tool.name}`} className="min-w-0 flex-1 cursor-pointer space-y-1">
        <span className="flex flex-wrap items-center gap-1.5">
          <Wrench aria-hidden="true" className="size-3.5 text-muted-foreground" />
          <span className="text-sm font-medium">{toolLabel(tool.name)}</span>
          {tool.read_only ? (
            <Badge tone="muted" className="font-normal">
              <Lock aria-hidden="true" className="mr-1 size-3" />
              Read-only
            </Badge>
          ) : null}
          <RiskBadge risk={tool.risk} />
        </span>
        <span className="block text-xs leading-4 text-muted-foreground">{tool.description}</span>
        <span className="block text-xs leading-4 text-muted-foreground">
          Requires {tool.required_permission} permission
        </span>
      </Label>
    </li>
  );
}

export function ToolPicker({
  tools,
  value,
  onChange,
  apps = [],
  detachedTools = [],
  loading = false,
  disabled = false,
}: {
  /** Only the work a connected app can do. */
  tools: ToolDescription[];
  value: string[];
  onChange: (next: string[]) => void;
  /** Catalogue names and logos, plus the connected flag per app. */
  apps?: AppMeta[];
  /** Selected tools whose app has no live connection. */
  detachedTools?: ToolDescription[];
  loading?: boolean;
  disabled?: boolean;
}) {
  const appFor = useMemo(() => {
    const map = new Map(apps.map((app) => [app.provider, app]));
    map.set(BUILTIN_GROUP, {
      provider: BUILTIN_GROUP,
      name: "Built-in",
      logo: "🧠",
      connected: true,
    });
    return map;
  }, [apps]);

  // Same shape for both lists: one bucket per app, in the order the tools arrive.
  const bucket = (list: ToolDescription[]) => {
    const groups = new Map<string, ToolDescription[]>();
    for (const tool of list) {
      const key = tool.integration ?? BUILTIN_GROUP;
      const existing = groups.get(key);
      if (existing) existing.push(tool);
      else groups.set(key, [tool]);
    }
    return [...groups.entries()].map(([key, items]) => ({
      key,
      name: appFor.get(key)?.name ?? providerLabel(key),
      logo: appFor.get(key)?.logo ?? "🔌",
      items,
    }));
  };

  const groups = useMemo(() => bucket(tools), [tools, appFor]);
  const detachedGroups = useMemo(() => bucket(detachedTools), [detachedTools, appFor]);

  const toggle = (name: string) => {
    onChange(value.includes(name) ? value.filter((item) => item !== name) : [...value, name]);
  };

  if (loading && groups.length === 0 && detachedGroups.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-muted/30 p-6 text-center text-sm leading-5 text-muted-foreground">
        Checking which apps are connected…
      </p>
    );
  }

  if (groups.length === 0 && detachedGroups.length === 0) {
    return (
      <EmptyState
        icon={Plug}
        title="No apps connected yet"
        description="A Buttlr can only use apps that are connected to this workspace. Connect one to pick the work it can do — you can still save this Buttlr as a draft in the meantime."
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

  return (
    <div className="space-y-6">
      {groups.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-muted/30 p-4 text-sm leading-5 text-muted-foreground">
          Nothing to pick yet — no app is connected to this workspace.{" "}
          <Link to="/integrations" className="font-medium text-primary hover:underline">
            Connect an app
          </Link>
          .
        </p>
      ) : null}

      {groups.map((group) => {
        const allSelected = group.items.every((tool) => value.includes(tool.name));
        return (
          <section key={group.key}>
            <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
              <h4 className="flex min-w-0 items-center gap-2 text-sm font-medium">
                <span aria-hidden="true">{group.logo}</span>
                <span className="truncate">{group.name}</span>
              </h4>
              <button
                type="button"
                className="-mr-2 inline-flex min-h-11 shrink-0 items-center rounded-md px-2 text-xs font-medium text-primary hover:underline disabled:opacity-60 sm:min-h-0"
                disabled={disabled}
                onClick={() =>
                  onChange(
                    allSelected
                      ? value.filter((name) => !group.items.some((tool) => tool.name === name))
                      : [...new Set([...value, ...group.items.map((tool) => tool.name)])],
                  )
                }
              >
                {allSelected ? "Clear all" : "Select all"}
              </button>
            </div>

            <ul className="mt-2 space-y-2">
              {group.items.map((tool) => (
                <ToolRow
                  key={tool.name}
                  tool={tool}
                  checked={value.includes(tool.name)}
                  disabled={disabled}
                  onToggle={() => toggle(tool.name)}
                />
              ))}
            </ul>
          </section>
        );
      })}

      {detachedGroups.map((group) => (
        <section key={`detached-${group.key}`}>
          <div className="flex flex-wrap items-center gap-2 border-b border-border pb-2">
            <h4 className="flex min-w-0 items-center gap-2 text-sm font-medium">
              <span aria-hidden="true">{group.logo}</span>
              <span className="truncate">{group.name}</span>
            </h4>
            <Badge tone="warning" className="font-normal">
              <PlugZap aria-hidden="true" className="mr-1 size-3" />
              Not connected
            </Badge>
            <button
              type="button"
              className="-mr-2 ml-auto inline-flex min-h-11 shrink-0 items-center rounded-md px-2 text-xs font-medium text-primary hover:underline disabled:opacity-60 sm:min-h-0"
              disabled={disabled}
              onClick={() =>
                onChange(value.filter((name) => !group.items.some((tool) => tool.name === name)))
              }
            >
              Remove these
            </button>
          </div>

          <p className="mt-2 text-xs leading-4 text-muted-foreground">
            {group.name} is selected here but has no connected account, so these cannot run until
            one is connected. They stay selected until you remove them.{" "}
            <Link to="/integrations" className="font-medium text-primary hover:underline">
              Open integrations
            </Link>
            .
          </p>

          <ul className="mt-2 space-y-2">
            {group.items.map((tool) => (
              <ToolRow
                key={tool.name}
                tool={tool}
                checked
                disabled={disabled}
                onToggle={() => toggle(tool.name)}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}