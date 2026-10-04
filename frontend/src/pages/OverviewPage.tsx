import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Bot,
  CalendarCheck,
  Clock,
  Plug,
  Timer,
  Plus,
  Users,
  UsersRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import { SectionCard } from "@/components/common/SectionCard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { ButtlrCard } from "@/components/buttlr/ButtlrCard";
import { ActivityTimeline } from "@/components/buttlr/ActivityTimeline";
import { StatusPill } from "@/components/common/StatusPill";
import { useAuth } from "@/lib/auth";
import { useApprovalStats, useDashboard } from "@/lib/queries";
import { formatDuration, formatRelative } from "@/lib/format";

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round((minutes / 60) * 10) / 10;
  return `${hours} h`;
}

export function OverviewPage() {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const dashboard = useDashboard(organizationId);
  const approvalStats = useApprovalStats(organizationId);

  const loading = dashboard.isLoading;
  const data = dashboard.data;

  if (dashboard.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Overview" description={activeOrganization?.name} />
        <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      </div>
    );
  }

  const singleButtlrOrg = (data?.buttlrs_total ?? 0) === 1;
  const singleButtlrPending = singleButtlrOrg ? (approvalStats.data?.pending ?? 0) : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description={
          data?.organization
            ? `${data.organization.logo_emoji} ${data.organization.name}`
            : (activeOrganization?.name ?? undefined)
        }
        actions={
          <Button asChild>
            <Link to="/buttlrs/new">
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              Create Buttlr
            </Link>
          </Button>
        }
      />

      {data && data.integrations_connected === 0 && (
        <Alert
          tone="warning"
          title="No integrations connected"
          icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
        >
          <span>
            Buttlrs cannot read or write anything until an integration is connected.{" "}
            <Link to="/integrations" className="font-medium underline underline-offset-4">
              Open integrations
            </Link>
            .
          </span>
        </Alert>
      )}

      <section aria-label="Key numbers" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {loading ? (
          ["Active Buttlrs", "Teams", "Members", "Pending approvals", "Runs today", "Time saved"].map(
            (label) => (
              <StatCard key={label} label={label} value="" loading />
            ),
          )
        ) : (
          <>
            <StatCard
              label="Active Buttlrs"
              value={`${data?.buttlrs_active ?? 0}/${data?.buttlrs_total ?? 0}`}
              hint={
                (data?.buttlrs_running ?? 0) > 0
                  ? `${data?.buttlrs_running} running right now`
                  : undefined
              }
              icon={Bot}
            />
            <StatCard
              label="Teams"
              value={data?.teams_total ?? 0}
              hint="Groups that supervise Buttlrs"
              icon={UsersRound}
            />
            <StatCard
              label="Members"
              value={data?.members_total ?? 0}
              hint="People with access"
              icon={Users}
            />
            <Link to="/approvals" className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <StatCard
                label="Pending approvals"
                value={data?.approvals_pending ?? 0}
                hint={
                  (data?.approvals_pending ?? 0) > 0
                    ? "Waiting for a decision"
                    : "Nothing waiting"
                }
                icon={CalendarCheck}
                tone={(data?.approvals_pending ?? 0) > 0 ? "warning" : "default"}
              />
            </Link>
            <StatCard
              label="Runs today"
              value={data?.executions_today ?? 0}
              hint={
                (data?.executions_failed_today ?? 0) > 0
                  ? `${data?.executions_failed_today} failed`
                  : "No failures"
              }
              icon={Clock}
              tone={(data?.executions_failed_today ?? 0) > 0 ? "destructive" : "default"}
            />
            <StatCard
              label="Time saved"
              value={formatMinutes(data?.estimated_minutes_saved ?? 0)}
              hint="Estimated, from completed runs"
              icon={Timer}
            />
          </>
        )}
      </section>

      <SectionCard
        title="Your Buttlrs"
        description="Everyone working in this organization right now."
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link to="/buttlrs">View all</Link>
          </Button>
        }
      >
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-36 w-full rounded-lg" />
            ))}
          </div>
        ) : data && data.buttlrs.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.buttlrs.map((buttlr) => (
              <ButtlrCard
                key={buttlr.id}
                buttlr={buttlr}
                href={`/buttlrs/${buttlr.id}`}
                pendingApprovals={singleButtlrOrg ? singleButtlrPending : 0}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Bot}
            title="Create your first Buttlr"
            description="Describe a job in your own words. Buttlr writes the instructions, the schedule and the approval policy."
            action={
              <Button asChild>
                <Link to="/buttlrs/new">
                  <Plus className="mr-2 h-4 w-4" aria-hidden />
                  Create Buttlr
                </Link>
              </Button>
            }
          />
        )}
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-5">
        <SectionCard
          title="Recent runs"
          description="The last executions across every Buttlr."
          className="lg:col-span-3"
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link to="/activity">Activity</Link>
            </Button>
          }
        >
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }, (_, index) => (
                <Skeleton key={index} className="h-14 w-full rounded-md" />
              ))}
            </div>
          ) : data && data.recent_executions.length > 0 ? (
            <ul className="divide-y divide-border">
              {data.recent_executions.map((execution) => (
                <li key={execution.id}>
                  <Link
                    to={`/buttlrs/${execution.buttlr_id}`}
                    className="flex flex-col gap-1 py-3 transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex-row sm:items-center sm:gap-3 sm:px-2"
                  >
                    <StatusPill status={execution.status} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-foreground">
                        {execution.buttlr_name}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {execution.goal}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                      {execution.duration_ms ? (
                        <span className="tabular-nums">{formatDuration(execution.duration_ms)}</span>
                      ) : null}
                      <span>{formatRelative(execution.created_at)}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Clock}
              title="No runs yet"
              description="Once a Buttlr is deployed and starts, its runs show up here."
            />
          )}
        </SectionCard>

        <SectionCard
          title="Recent activity"
          description="A record of everything that changed."
          className="lg:col-span-2"
          actions={
            <Button asChild variant="ghost" size="sm">
              <Link to="/activity">View all</Link>
            </Button>
          }
        >
          <ActivityTimeline items={data?.recent_audit ?? []} loading={loading} />
        </SectionCard>
      </div>

      <Link
        to="/integrations"
        className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="flex items-center gap-3">
          <Plug className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="text-sm text-foreground">
            {data
              ? `${data.integrations_connected}/${data.integrations_total} integrations connected`
              : "Integrations"}
          </span>
        </span>
        <span className="text-sm font-medium text-primary">Manage</span>
      </Link>
    </div>
  );
}