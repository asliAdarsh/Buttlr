import { Link } from "react-router-dom";
import { Bot, ChevronRight, Cog, User } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative, humanize } from "@/lib/format";
import type { ActorType, AuditLog } from "@/lib/types";

const ACTOR_ICON: Record<ActorType, typeof User> = {
  user: User,
  buttlr: Bot,
  system: Cog,
};

export function ActivityTimeline({
  items,
  loading = false,
}: {
  items: AuditLog[];
  loading?: boolean;
}) {
  if (loading) {
    return (
      <ul className="space-y-4">
        {Array.from({ length: 5 }).map((_, index) => (
          <li key={index} className="flex gap-3">
            <Skeleton className="size-7 shrink-0 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </li>
        ))}
      </ul>
    );
  }

  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-muted/30 p-6 text-center text-sm leading-5 text-muted-foreground">
        Nothing has happened here yet. Runs, approvals and configuration changes are recorded as they
        occur.
      </p>
    );
  }

  return (
    <ol className="relative">
      <span aria-hidden="true" className="absolute bottom-2 left-[13px] top-2 w-px bg-border" />
      {items.map((item) => {
        const Icon = ACTOR_ICON[item.actor_type] ?? User;
        return (
          <li key={item.id} className="relative flex gap-3 pb-4 last:pb-0">
            <span
              aria-hidden="true"
              className="z-10 flex size-7 shrink-0 items-center justify-center rounded-full border border-border bg-card"
            >
              <Icon className="size-3.5 text-muted-foreground" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-5 break-words">{item.summary}</p>
              <p className="mt-0.5 text-xs leading-4 text-muted-foreground">
                <span className="font-medium text-foreground">
                  {item.actor_name ?? item.actor_type}
                </span>
                {" · "}
                {humanize(item.action.replace(/\./g, " "))}
                {" · "}
                {formatRelative(item.created_at)}
              </p>
              {item.execution_id ? (
                <Link
                  to={`/buttlrs/${item.buttlr_id}?tab=runs&execution=${item.execution_id}`}
                  className="mt-1.5 inline-flex min-h-11 items-center gap-0.5 text-xs font-medium text-primary hover:underline sm:min-h-0"
                >
                  Open run
                  <ChevronRight aria-hidden="true" className="size-3" />
                </Link>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}