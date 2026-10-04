import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  CheckCircle2,
  CircleDot,
  Plug,
  ShieldCheck,
  UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import {
  useDecideApproval,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/queries";
import type { Notification, NotificationKind } from "@/lib/types";

const KIND_ICON: Record<NotificationKind, typeof Bell> = {
  approval_required: ShieldCheck,
  approval_decided: CheckCheck,
  execution_completed: CheckCheck,
  execution_failed: AlertTriangle,
  integration_error: Plug,
  member_added: UserPlus,
  system: CircleDot,
};

/**
 * The server links an approval as `/approvals/{id}`, but the app has no such route. The id
 * is pulled out so the person lands on the list with that request selected — and so the
 * Approve button knows what it is deciding.
 */
function approvalTarget(link: string | null | undefined): string | null {
  return link ? /^\/approvals\/([^/?#]+)$/.exec(link)?.[1] ?? null : null;
}

function resolveLink(link: string, approvalId: string | null): string {
  return approvalId
    ? `/approvals?status=all&approval=${encodeURIComponent(approvalId)}`
    : link;
}

export function NotificationBell() {
  const { activeOrganizationId } = useAuth();
  const navigate = useNavigate();
  const { data, isPending } = useNotifications(activeOrganizationId, { limit: 12 });
  const markAll = useMarkAllNotificationsRead(activeOrganizationId ?? "");
  const markRead = useMarkNotificationRead(activeOrganizationId ?? "");
  const decide = useDecideApproval(activeOrganizationId ?? "");

  const [open, setOpen] = useState(false);
  const [approving, setApproving] = useState<Notification | null>(null);

  const notifications = data ?? [];
  const unread = notifications.filter((item) => !item.read).length;

  const openLink = (item: Notification) => {
    const approvalId = approvalTarget(item.link);
    setOpen(false);
    if (item.link) navigate(resolveLink(item.link, approvalId));
  };

  const approveFromBell = async () => {
    if (!approving) return;
    const approvalId = approvalTarget(approving.link);
    const name = approving.title.replace(/ needs your approval$/, "");
    setApproving(null);
    if (!approvalId) {
      toast.error("This request could not be opened. Find it on the Approvals page.");
      return;
    }
    try {
      await decide.mutateAsync({ approvalId, granted: true });
      markRead.mutate(approving.id);
      toast.success(`Approved: ${name}. The run continues.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "That request could not be approved. Open it on the Approvals page.",
      );
    }
  };

  return (
    <>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
            <Bell aria-hidden="true" className="size-4" />
            {unread > 0 ? (
              <>
                <span
                  aria-hidden="true"
                  className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive"
                />
                <span className="sr-only">{unread} unread notifications</span>
              </>
            ) : null}
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="end"
          className="w-[min(22rem,calc(100vw-2rem))] p-0"
        >
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
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              Loading notifications…
            </p>
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
                // Only a live request can be approved from here; a decided one is a record.
                const approvalId =
                  item.kind === "approval_required" ? approvalTarget(item.link) : null;
                return (
                  <li
                    key={item.id}
                    className={cn(
                      "flex items-start gap-2.5 px-3 py-2.5 transition-colors hover:bg-muted",
                      !item.read && "bg-accent/40",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => openLink(item)}
                      className="flex min-w-0 flex-1 items-start gap-2.5 text-left"
                    >
                      <Icon
                        aria-hidden="true"
                        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">{item.title}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {item.body}
                        </span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {formatRelative(item.created_at)}
                          {!item.read ? " · unread" : ""}
                        </span>
                      </span>
                      {!item.read ? (
                        <span
                          aria-hidden="true"
                          className="mt-1.5 size-2 shrink-0 rounded-full bg-primary"
                        />
                      ) : null}
                    </button>

                    {approvalId ? (
                      <Button
                        type="button"
                        variant="success"
                        size="sm"
                        className="mt-0.5 shrink-0"
                        aria-label={`Approve: ${item.title}`}
                        onClick={() => {
                          // Close the menu first: a dialog opened on top of an open
                          // dropdown fights it for focus.
                          setOpen(false);
                          setApproving(item);
                        }}
                      >
                        <CheckCircle2 aria-hidden="true" />
                        Approve
                      </Button>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={approving !== null}
        onOpenChange={(next) => {
          if (!next) setApproving(null);
        }}
        title="Approve this request?"
        description={approving?.body}
        confirmLabel="Approve and run"
        onConfirm={approveFromBell}
        loading={decide.isPending}
      />
    </>
  );
}