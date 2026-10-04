import * as React from "react";

import { cn } from "@/lib/utils";

export interface FilterBarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Controls. On a phone they sit in one row that scrolls inside this bar only. */
  children: React.ReactNode;
  /** Rendered at the end of the row, pinned outside the scroll area (e.g. "Clear"). */
  trailing?: React.ReactNode;
}

/**
 * Search and filters in one band. Below `sm` the controls scroll horizontally
 * inside this element — the page itself never scrolls sideways.
 */
export function FilterBar({ children, trailing, className, ...props }: FilterBarProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar sm:flex-wrap sm:overflow-visible sm:pb-0",
        className,
      )}
      {...props}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">{children}</div>
      {trailing ? <div className="flex shrink-0 items-center gap-2">{trailing}</div> : null}
    </div>
  );
}