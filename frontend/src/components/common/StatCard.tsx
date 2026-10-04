import * as React from "react";
import type { LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon?: LucideIcon;
  tone?: "default" | "success" | "warning" | "destructive";
  loading?: boolean;
}

const TONE_TEXT = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
} as const;

/**
 * One statistic. The label is always present — colour and the number alone never
 * carry the meaning, so a value is readable without relying on tone.
 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  loading = false,
  className,
  ...props
}: StatCardProps) {
  return (
    <Card className={cn("p-4", className)} {...props}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground/70" aria-hidden="true" /> : null}
      </div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-20" />
      ) : (
        <p className={cn("mt-1 text-2xl font-semibold leading-8 tabular-nums", TONE_TEXT[tone])}>
          {value}
        </p>
      )}
      {hint && !loading ? (
        <p className="mt-1 text-xs leading-4 text-muted-foreground">{hint}</p>
      ) : null}
    </Card>
  );
}