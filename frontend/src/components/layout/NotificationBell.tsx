import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  CircleDot,
  Plug,
  ShieldCheck,
  UserPlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import { useMarkAllNotificationsRead, useNotifications } from "@/lib/queries";
import type { NotificationKind } from "@/lib/types";

const KIND_ICON: Record<NotificationKind, typeof Bell> = {
  approval_required: ShieldCheck,
  approval_decided: CheckCheck,
  execution_completed: CheckCheck,
  execution_failed: AlertTriangle,
  integration_error: Plug,
  member_added: UserPlus,
  system: CircleDot,
};

export function NotificationBell() {
  const { activeOrganizationId } = useAuth();
  const navigate = useNavigate();
  const { data, isPending } = useNotifications(activeOrganizationId, { limit: 12 });
  const markAll = useMarkAllNotificationsRead(activeOrganizationId ?? "");

  const notifications = data ?? [];
  const unread = notifications.filter((item) => !item.read).length;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
          <Bell aria-hidden="true" className="size-4" />
          {unread > 0 ? (
            <>
              <span aria-hidden="true" className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive" />
              <span className="sr-only">{unread} unread notifications</span>
            </>
          ) : null}
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-[min(20rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
          <button
            type="button"
            className="rounded text-xs font-medium text-primary hover:underline disabled:opacity-60"
            disabled={unread === 0 || markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            Mark all as read
          </button>
        </div>
        <DropdownMenuSeparator className="my-0" />

        {isPending ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">Loading notifications…</p>
        ) : notifications.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <Bell aria-hidden="true" className="mx-auto mb-2 size-5 text-muted-foreground" />
            <p className="text-sm font-medium">No notifications yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Approval requests and finished runs show up here.
            </p>
          </div>
        ) : (
          <ul className="max-h-80 overflow-y-auto">
            {notifications.map((item) => {
              const Icon = KIND_ICON[item.kind] ?? CircleDot;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (item.link) navigate(item.link);
                    }}
                    className={cn(
                      "flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-muted",
                      !item.read && "bg-accent/40",
                    )}
                  >
                    <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{item.title}</span>
                      <span className="block truncate text-xs text-muted-foreground">{item.body}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {formatRelative(item.created_at)}
                        {!item.read ? " · unread" : ""}
                      </span>
                    </span>
                    {!item.read ? (
                      <span aria-hidden="true" className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
