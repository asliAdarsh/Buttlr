import * as React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  back?: { to: string; label: string };
}

/**
 * The single page title. Exactly one `<h1>` per page, always here — the topbar
 * renders a `<p>` so the two never compete.
 */
export function PageHeader({
  title,
  description,
  actions,
  back,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <div
      className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between", className)}
      {...props}
    >
      <div className="min-w-0 space-y-1">
        {back ? (
          <Link
            to={back.to}
            className="-ml-2 inline-flex min-h-11 items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground sm:min-h-0 sm:-ml-2"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            {back.label}
          </Link>
        ) : null}
        <h1 className="text-xl font-semibold leading-7 tracking-tight text-foreground sm:text-2xl sm:leading-8">
          {title}
        </h1>
        {description ? (
          <p className="max-w-2xl text-sm leading-5 text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">{actions}</div>
      ) : null}
    </div>
  );
}