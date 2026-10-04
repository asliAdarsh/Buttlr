import { useMemo } from "react";
import { Label } from "@/components/ui/label";
import { providerLabel } from "@/lib/format";
import type { IntegrationPublic } from "@/lib/types";

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

export function ScopeEditor({
  scope,
  onChange,
  integrations,
}: {
  scope: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  integrations: IntegrationPublic[];
}) {
  const connected = useMemo(
    () => integrations.filter((integration) => integration.status === "connected"),
    [integrations],
  );

  const covered = new Set<string>(connected.map((integration) => integration.provider));

  const write = (provider: string, resourceIds: string[]) => {
    const next = { ...scope };
    const previous =
      scope[provider] && typeof scope[provider] === "object"
        ? (scope[provider] as Record<string, unknown>)
        : {};
    next[provider] = { ...previous, resources: resourceIds };
    onChange(next);
  };

  if (connected.length === 0) {
    return (
      <p className="rounded-md border border-border border-dashed p-6 text-center text-sm text-muted-foreground">
        Scope is set per connected account. Connect an integration to choose which repositories and
        projects this Buttlr may reach.
      </p>
    );
  }

  const extraKeys = Object.keys(scope).filter((key) => !covered.has(key));

  return (
    <div className="space-y-5">
      {connected.map((integration) => {
        const selected = readResourceIds(scope[integration.provider]);
        return (
          <fieldset key={integration.id}>
            <legend className="text-sm font-medium">
              {integration.display_name}
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {providerLabel(integration.provider)}
              </span>
            </legend>
            {integration.resources.length === 0 ? (
              <p className="mt-1 text-xs text-muted-foreground">
                This account has not reported any resources yet.
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {integration.resources.map((resource) => (
                  <li key={resource.id} className="flex items-center gap-2">
                    <input
                      id={`scope-${integration.id}-${resource.id}`}
                      type="checkbox"
                      className="size-4 rounded border-border accent-primary"
                      checked={selected.includes(resource.id)}
                      onChange={() =>
                        write(
                          integration.provider,
                          selected.includes(resource.id)
                            ? selected.filter((id) => id !== resource.id)
                            : [...selected, resource.id],
                        )
                      }
                    />
                    <Label
                      htmlFor={`scope-${integration.id}-${resource.id}`}
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
