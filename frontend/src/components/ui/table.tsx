import * as React from "react";

import { cn } from "@/lib/utils";

/** Plain elements so consumers can compose; wrap in `overflow-x-auto` themselves. */

export const Table = React.forwardRef<HTMLTableElement, React.TableHTMLAttributes<HTMLTableElement>>(
  function Table({ className, ...props }, ref) {
    return (
      <table ref={ref} className={cn("w-full caption-bottom border-collapse text-sm", className)} {...props} />
    );
  },
);

export const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(function TableHeader({ className, ...props }, ref) {
  return <thead ref={ref} className={cn("[&_tr]:border-b", className)} {...props} />;
});

export const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(function TableBody({ className, ...props }, ref) {
  return <tbody ref={ref} className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
});

export const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(function TableRow({ className, ...props }, ref) {
  return (
    <tr
      ref={ref}
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/60 data-[state=selected]:bg-muted",
        className,
      )}
      {...props}
    />
  );
});

export const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(function TableHead({ className, ...props }, ref) {
  return (
    <th
      ref={ref}
      scope="col"
      className={cn(
        "sticky top-0 z-10 bg-card h-10 whitespace-nowrap px-3 text-left align-middle text-xs font-medium uppercase tracking-wide text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
});

export const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(function TableCell({ className, ...props }, ref) {
  return <td ref={ref} className={cn("px-3 py-2.5 align-middle", className)} {...props} />;
});