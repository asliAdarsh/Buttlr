import * as React from "react";

import { cn } from "@/lib/utils";

export interface DetailListItem {
  label: string;
  value: React.ReactNode;
}

export interface DetailListProps extends React.HTMLAttributes<HTMLDListElement> {
  items: DetailListItem[];
  /** Render the value as a monospace token (URLs, ids, model names). */
  mono?: boolean;
}

/**
 * Label/value pairs in one rhythm, used wherever settings or a detail panel
 * needs to explain a value. Stacks on a phone without any horizontal scrolling.
 */
export function DetailList({ items, mono = false, className, ...props }: DetailListProps) {
  return (
    <dl className={cn("divide-y divide-border", className)} {...props}>
      {items.map((item) => (
        <div
          key={item.label}
          className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 first:pt-0 last:pb-0"
        >
          <dt className="text-sm text-muted-foreground">{item.label}</dt>
          <dd
            className={cn(
              "min-w-0 text-sm text-foreground",
              mono ? "font-mono text-xs break-all" : "text-right",
            )}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}