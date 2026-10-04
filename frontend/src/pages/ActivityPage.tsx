import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Bell,
  BellRing,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleSlash,
  History,
  PlugZap,
  UserPlus,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Field } from "@/components/common/Field";
import { PageHeader } from "@/components/common/PageHeader";
import { ActivityTimeline } from "@/components/buttlr/ActivityTimeline";
import { useAuth } from "@/lib/auth";
import {
  useAudit,
  useButtlrs,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/queries";
import { formatRelative } from "@/lib/format";
import type { NotificationKind } from "@/lib/types";

const PAGE_SIZE = 25;
const NOTIFICATION_LIMIT = 100;

/** The actions people actually look for, always offered even if nothing recent matches. */
const CURATED_ACTIONS = [
  "approval.requested",
  "approval.granted",
  "approval.rejected",
  "execution.started",
  "execution.completed",
  "execution.failed",
  "execution.cancelled",
  "buttlr.created",
  "buttlr.updated",
  "buttlr.deployed",
  "buttlr.paused",
  "buttlr.deleted",
  "integration.connected",
  "integration.disconnected",
  "member.invited",
  "member.removed",
  "member.role_changed",
  "organization.updated",
  "settings.updated",
  "team.created",
];

/**
 * Notifications carry server-built paths (`/buttlrs/:id/runs/:executionId`, `/approvals/:id`, …)
 * that predate the current route table. Map them onto real routes so every link goes somewhere.
 */
function resolveLink(link: string | null | undefined): string | null {
  if (!link) return null;
  const [path] = link.split("?", 2);
  const run = /^\/buttlrs\/([^/]+)\/runs\/([^/]+)$/.exec(path);
  if (run) return `/buttlrs/${run[1]}?tab=runs&execution=${run[2]}`;
  if (/^\/approvals\/[^/]+$/.test(path)) return "/approvals?status=all";
  if (/^\/organizations\/[^/]+\/members$/.test(path)) return "/settings?tab=organization";
  if (path === "/overview" || path === "/") return "/";
  return path.startsWith("/") ? path : null;
}

const KIND_ICON: Record<NotificationKind, typeof Bell> = {
  approval_required: BellRing,
  approval_decided: CheckCircle2,
  execution_completed: CheckCircle2,
  execution_failed: CircleSlash,
  integration_error: PlugZap,
  member_added: UserPlus,
  system: Users,
};

export function ActivityPage() {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;

  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "notifications" ? "notifications" : "audit";
  const action = searchParams.get("action") ?? "";
  const buttlrId = searchParams.get("buttlr_id") ?? "";
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  const unreadOnly = searchParams.get("unread") === "1";

  const audit = useAudit(
    organizationId,
    organizationId
      ? {
          action: action || undefined,
          buttlr_id: buttlrId || undefined,
          limit: PAGE_SIZE,
          offset,
        }
      : undefined,
  );
  const buttlrs = useButtlrs(organizationId);
  const notifications = useNotifications(organizationId, {
    unread_only: unreadOnly,
    limit: NOTIFICATION_LIMIT,
  });
  const markRead = useMarkNotificationRead(organizationId ?? "");
  const markAllRead = useMarkAllNotificationsRead(organizationId ?? "");

  const patchParams = (patch: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") params.delete(key);
      else params.set(key, value);
    }
    setSearchParams(params, { replace: true });
  };

  const actionOptions = useMemo(() => {
    const present = new Set((audit.data?.items ?? []).map((item) => item.action));
    const values = [...new Set([...CURATED_ACTIONS, ...present])].sort();
    return values.map((value) => ({ value, label: value.replace(/[._]/g, " ") }));
  }, [audit.data]);

  const buttlrOptions = useMemo(
    () => [
      { value: "", label: "All Buttlrs" },
      ...(buttlrs.data ?? []).map((buttlr) => ({
        value: buttlr.id,
        label: `${buttlr.avatar} ${buttlr.name}`.trim(),
      })),
    ],
    [buttlrs.data],
  );

  const handleMarkRead = async (id: string, title: string) => {
    try {
      await markRead.mutateAsync(id);
      toast.success(`“${title}” marked as read.`);
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The notification could not be marked as read.",
      );
    }
  };

  const handleMarkAllRead = async () => {
    try {
      const ack = await markAllRead.mutateAsync();
      toast.success(ack.message ?? "All notifications marked as read.");
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "Notifications could not be marked as read.",
      );
    }
  };

  const auditItems = audit.data?.items ?? [];
  const auditTotal = audit.data?.total ?? 0;
  const unreadCount = (notifications.data ?? []).filter((item) => !item.read).length;
  const canGoBack = offset > 0;
  const canGoForward = offset + PAGE_SIZE < auditTotal;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        description="Everything that happened in this organization, and what is waiting for you."
      />

      <Tabs
        value={tab}
        onValueChange={(value) => patchParams({ tab: value === "audit" ? null : value, offset: null })}
      >
        <TabsList>
          <TabsTrigger value="audit">
            <History aria-hidden="true" className="mr-1.5 size-4" />
            Audit log
          </TabsTrigger>
          <TabsTrigger value="notifications">
            <Bell aria-hidden="true" className="mr-1.5 size-4" />
            Notifications
            {unreadCount > 0 ? (
              <Badge tone="warning" className="ml-1.5">
                {unreadCount}
              </Badge>
            ) : null}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="audit">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Action" htmlFor="audit-action">
              <Select
                id="audit-action"
                value={action}
                onValueChange={(value) => patchParams({ action: value || null, offset: null })}
                options={[{ value: "", label: "All actions" }, ...actionOptions]}
              />
            </Field>
            <Field label="Buttlr" htmlFor="audit-buttlr">
              <Select
                id="audit-buttlr"
                value={buttlrId}
                onValueChange={(value) => patchParams({ buttlr_id: value || null, offset: null })}
                options={buttlrOptions}
              />
            </Field>
          </div>

          <div className="mt-4">
            {audit.isError ? (
              <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
            ) : auditItems.length === 0 ? (
              <EmptyState
                icon={History}
                title="No matching activity"
                description={
                  auditTotal === 0 && !action && !buttlrId
                    ? "Runs, approvals and configuration changes are recorded here as they happen."
                    : "No entries match these filters. Try a different action or Buttlr."
                }
                action={
                  action || buttlrId ? (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => patchParams({ action: null, buttlr_id: null, offset: null })}
                    >
                      Clear filters
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <ActivityTimeline items={auditItems} loading={audit.isLoading} />
            )}
          </div>

          {auditTotal > PAGE_SIZE ? (
            <nav aria-label="Audit log pages" className="mt-4 flex items-center justify-between gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoBack || audit.isFetching}
                onClick={() => patchParams({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
              >
                <ChevronLeft aria-hidden="true" className="mr-1 h-4 w-4" />
                Previous
              </Button>
              <span className="text-xs tabular-nums text-muted-foreground">
                {Math.min(offset + 1, auditTotal)}–{Math.min(offset + PAGE_SIZE, auditTotal)} of {auditTotal}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoForward || audit.isFetching}
                onClick={() => patchParams({ offset: String(offset + PAGE_SIZE) })}
              >
                Next
                <ChevronRight aria-hidden="true" className="ml-1 h-4 w-4" />
              </Button>
            </nav>
          ) : null}
        </TabsContent>

        <TabsContent value="notifications">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Switch
                id="unread-only"
                checked={unreadOnly}
                onCheckedChange={(checked) => patchParams({ unread: checked ? "1" : null })}
              />
              <Label htmlFor="unread-only" className="text-sm">
                Unread only
              </Label>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleMarkAllRead()}
              loading={markAllRead.isPending}
              disabled={(notifications.data ?? []).length === 0}
            >
              <CheckCheck aria-hidden="true" className="mr-1.5 h-4 w-4" />
              Mark all as read
            </Button>
          </div>

          <div className="mt-4">
            {notifications.isError ? (
              <ErrorState error={notifications.error} onRetry={() => void notifications.refetch()} />
            ) : (notifications.data ?? []).length === 0 ? (
              <EmptyState
                icon={Bell}
                title={unreadOnly ? "Nothing unread" : "No notifications yet"}
                description={
                  unreadOnly
                    ? "Everything in this organization has been read."
                    : "Approvals that need you, finished runs and integration problems arrive here."
                }
              />
            ) : (
              <ul className="space-y-3">
                {(notifications.data ?? []).map((notification) => {
                  const Icon = KIND_ICON[notification.kind] ?? Bell;
                  const href = resolveLink(notification.link);
                  return (
                    <li
                      key={notification.id}
                      className={
                        notification.read
                          ? "rounded-lg border border-border bg-card p-3 sm:p-4"
                          : "rounded-lg border border-primary/40 bg-primary/5 p-3 sm:p-4"
                      }
                    >
                      <div className="flex items-start gap-3">
                        <span
                          aria-hidden="true"
                          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
                        >
                          <Icon className="size-3.5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-medium">{notification.title}</p>
                            {!notification.read ? <Badge tone="primary">Unread</Badge> : null}
                          </div>
                          <p className="mt-1 break-words text-sm text-muted-foreground">
                            {notification.body}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-3">
                            <span className="text-xs text-muted-foreground">
                              {formatRelative(notification.created_at)}
                            </span>
                            {href ? (
                              <Link
                                to={href}
                                className="inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline"
                              >
                                Open
                                <ChevronRight aria-hidden="true" className="size-3" />
                              </Link>
                            ) : null}
                            {!notification.read ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 px-2 text-xs"
                                onClick={() => void handleMarkRead(notification.id, notification.title)}
                                loading={markRead.isPending}
                              >
                                <Check aria-hidden="true" className="mr-1 size-3" />
                                Mark as read
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}