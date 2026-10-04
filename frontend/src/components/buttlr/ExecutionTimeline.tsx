import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Loader2,
  MessageSquare,
  ShieldCheck,
  ShieldQuestion,
  ShieldX,
  Sparkles,
  Terminal,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/common/StatusPill";
import { cn } from "@/lib/utils";
import { formatCost, formatDuration, formatTokens, providerLabel, toolLabel } from "@/lib/format";
import type { Execution, ExecutionStep, StepStatus, StepType } from "@/lib/types";

const TYPE_ICON: Record<StepType, LucideIcon> = {
  status: Circle,
  thinking: Sparkles,
  tool_call: Wrench,
  tool_result: Terminal,
  approval_request: ShieldQuestion,
  approval_result: ShieldCheck,
  message: MessageSquare,
  error: AlertTriangle,
};

const STATUS_ICON: Record<StepStatus, LucideIcon> = {
  pending: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  skipped: Circle,
  blocked: ShieldX,
};

function StepRow({ step }: { step: ExecutionStep }) {
  const TypeIcon = TYPE_ICON[step.type] ?? Circle;
  const StatusIcon = STATUS_ICON[step.status] ?? Circle;
  const running = step.status === "running";
  const failed = step.status === "failed";
  const preformatted = step.type === "message" || step.type === "error";
  const detail = step.detail?.trim();

  return (
    <li className="flex gap-3">
      <span className="relative flex w-6 shrink-0 justify-center pt-1">
        <TypeIcon
          aria-hidden="true"
          className={cn(
            "size-4",
            failed ? "text-destructive" : "text-muted-foreground",
          )}
        />
      </span>

      <div className="min-w-0 flex-1 pb-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-sm font-medium">{step.title}</span>
          {step.tool ? (
            <Badge tone="outline" className="font-normal">
              {toolLabel(step.tool)}
            </Badge>
          ) : null}
          <span
            className={cn(
              "ml-auto inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground",
            )}
          >
            <StatusIcon
              aria-hidden="true"
              className={cn(
                "size-3.5",
                running && "animate-spin",
                failed && "text-destructive",
                step.status === "completed" && "text-success",
              )}
            />
            <span className="capitalize">{step.status}</span>
            {step.duration_ms != null ? ` · ${formatDuration(step.duration_ms)}` : ""}
          </span>
        </div>

        {detail ? (
          <p
            className={cn(
              "mt-1 break-words text-xs text-muted-foreground",
              preformatted ? "whitespace-pre-wrap" : "truncate",
            )}
          >
            {detail}
          </p>
        ) : null}

        {step.approval_id ? (
          <Link
            to="/approvals"
            className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
          >
            <ShieldQuestion aria-hidden="true" className="size-3" />
            View approval request
          </Link>
        ) : null}
      </div>
    </li>
  );
}

export function ExecutionTimeline({
  execution,
  live = false,
}: {
  execution: Execution;
  live?: boolean;
}) {
  const model = [providerLabel(execution.provider), execution.model].filter(Boolean).join(" · ");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2">
        <StatusPill status={execution.status} size="sm" />
        {live ? (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
            <Loader2 aria-hidden="true" className="size-3 animate-spin" />
            Live
          </span>
        ) : null}
        <span className="text-xs text-muted-foreground">{model || "Model not recorded"}</span>
        {execution.duration_ms != null ? (
          <span className="text-xs text-muted-foreground">
            {formatDuration(execution.duration_ms)}
          </span>
        ) : null}
      </div>

      <p className="text-sm">{execution.goal}</p>

      {execution.steps.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No steps recorded yet. {live ? "They appear here as the run progresses." : ""}
        </p>
      ) : (
        <ol className="relative">
          <span
            aria-hidden="true"
            className="absolute bottom-2 left-3 top-2 w-px bg-border"
          />
          {execution.steps.map((step) => (
            <StepRow key={`${step.index}-${step.type}`} step={step} />
          ))}
        </ol>
      )}

      {execution.output ? (
        <div className="rounded-md border border-border bg-muted/40 p-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Output
          </p>
          <p className="whitespace-pre-wrap break-words text-sm">{execution.output}</p>
        </div>
      ) : null}

      {execution.error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="mb-1 inline-flex items-center gap-1 text-xs font-medium text-destructive">
            <AlertTriangle aria-hidden="true" className="size-3" />
            Error
          </p>
          <p className="whitespace-pre-wrap break-words text-sm">{execution.error}</p>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
        <span>{formatTokens(execution.usage.total_tokens)} tokens</span>
        <span>{formatCost(execution.usage.estimated_cost_usd)}</span>
        <span>{execution.usage.calls} model calls</span>
      </div>
    </div>
  );
}
