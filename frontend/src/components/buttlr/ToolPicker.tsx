import { useMemo } from "react";
import { Lock, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { RiskBadge } from "@/components/common/RiskBadge";
import { humanize, toolLabel } from "@/lib/format";
import type { ToolDescription } from "@/lib/types";

export function ToolPicker({
  tools,
  value,
  onChange,
  disabled = false,
}: {
  tools: ToolDescription[];
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const groups = useMemo(() => {
    const map = new Map<string, ToolDescription[]>();
    for (const tool of tools) {
      const key = tool.integration ?? "Other";
      const bucket = map.get(key);
      if (bucket) bucket.push(tool);
      else map.set(key, [tool]);
    }
    return [...map.entries()].map(([integration, items]) => ({ integration, items }));
  }, [tools]);

  const toggle = (name: string) => {
    onChange(value.includes(name) ? value.filter((item) => item !== name) : [...value, name]);
  };

  if (tools.length === 0) {
    return (
      <p className="rounded-md border border-border border-dashed p-6 text-center text-sm text-muted-foreground">
        No tools are available. Connect an integration first — tools follow from the accounts you
        connect.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {groups.map((group) => {
        const allSelected = group.items.every((tool) => value.includes(tool.name));
        return (
          <section key={group.integration}>
            <div className="flex items-center justify-between gap-3 border-b border-border pb-2">
              <h4 className="text-sm font-medium">{humanize(group.integration)}</h4>
              <button
                type="button"
                className="text-xs font-medium text-primary hover:underline disabled:opacity-60"
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
                <li key={tool.name} className="flex items-start gap-2">
                  <input
                    id={`tool-${tool.name}`}
                    type="checkbox"
                    className="mt-1 size-4 rounded border-border accent-primary"
                    checked={value.includes(tool.name)}
                    disabled={disabled}
                    onChange={() => toggle(tool.name)}
                  />
                  <Label htmlFor={`tool-${tool.name}`} className="min-w-0 flex-1 space-y-1">
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
                    <span className="block text-xs text-muted-foreground">{tool.description}</span>
                    <span className="block text-xs text-muted-foreground">
                      Requires {tool.required_permission} permission
                    </span>
                  </Label>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
