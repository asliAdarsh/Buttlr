import { Link } from "react-router-dom";
import { Clock, ShieldQuestion, TrendingUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/common/StatusPill";
import { cn } from "@/lib/utils";
import { formatRelative, toolLabel } from "@/lib/format";
import type { Buttlr } from "@/lib/types";
import { ButtlrAvatar } from "./ButtlrAvatar";
import { ScheduleBadge } from "./ScheduleBadge";

export function ButtlrCard({
  buttlr,
  href,
  pendingApprovals,
  className,
}: {
  buttlr: Buttlr;
  href?: string;
  pendingApprovals?: number;
  className?: string;
}) {
  const pending = pendingApprovals ?? buttlr.stats.pending_approvals;
  const successRate =
    buttlr.stats.total_runs > 0
      ? Math.round((buttlr.stats.successful_runs / buttlr.stats.total_runs) * 100)
      : null;
  const subtitle = [buttlr.role, buttlr.department].filter(Boolean).join(" · ");

  return (
    <Link
      to={href ?? `/buttlrs/${buttlr.id}`}
      className={cn(
        "block rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40 hover:ring-1 hover:ring-ring/40",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <ButtlrAvatar buttlr={buttlr} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="truncate text-sm font-semibold">{buttlr.name}</span>
            <StatusPill status={buttlr.status} size="sm" />
          </div>
          {subtitle ? (
            <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
      </div>

      <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{buttlr.objective}</p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <ScheduleBadge schedule={buttlr.schedule} />
        {buttlr.tools.slice(0, 3).map((tool) => (
          <Badge key={tool} tone="muted" className="font-normal">
            {toolLabel(tool)}
          </Badge>
        ))}
        {buttlr.tools.length > 3 ? (
          <Badge tone="muted" className="font-normal">
            +{buttlr.tools.length - 3}
          </Badge>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Clock aria-hidden="true" className="size-3" />
          Last run {formatRelative(buttlr.stats.last_run_at)}
        </span>
        <span className="inline-flex items-center gap-1">
          <TrendingUp aria-hidden="true" className="size-3" />
          {successRate === null ? "No runs yet" : `${successRate}% success`}
        </span>
        {pending > 0 ? (
          <span className="inline-flex items-center gap-1 font-medium text-warning">
            <ShieldQuestion aria-hidden="true" className="size-3" />
            {pending} waiting
          </span>
        ) : null}
      </div>
    </Link>
  );
}
