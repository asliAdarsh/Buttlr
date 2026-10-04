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

export function PageHeader({
  title,
  description,
  actions,
  back,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", className)} {...props}>
      <div className="min-w-0 space-y-1">
        {back ? (
          <Link
            to={back.to}
            className="inline-flex items-center gap-1 rounded-md text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            {back.label}
          </Link>
        ) : null}
        <h1 className="text-xl font-semibold text-foreground sm:text-2xl">{title}</h1>
        {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}