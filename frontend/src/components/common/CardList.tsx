import * as React from "react";

import { cn } from "@/lib/utils";

export interface CardListProps extends React.HTMLAttributes<HTMLUListElement> {}

/**
 * A table rendered as a list of cards. Used together with a real `<Table>` in a
 * `hidden md:block` wrapper: below `md` the rows become stacked key/value
 * blocks, at `md` and up the table takes over.
 */
export function CardList({ className, ...props }: CardListProps) {
  return <ul className={cn("grid gap-2 md:hidden", className)} {...props} />;
}

export interface CardListItemProps extends React.LiHTMLAttributes<HTMLLIElement> {}

export function CardListItem({ className, ...props }: CardListItemProps) {
  return (
    <li
      className={cn("rounded-lg border border-border bg-card p-3 text-sm", className)}
      {...props}
    />
  );
}

export interface KeyValueProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  children: React.ReactNode;
}

/** One stacked key/value block, the phone stand-in for a table cell. */
export function KeyValue({ label, children, className, ...props }: KeyValueProps) {
  return (
    <div
      className={cn("flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5", className)}
      {...props}
    >
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="min-w-0 text-sm text-foreground">{children}</span>
    </div>
  );
}