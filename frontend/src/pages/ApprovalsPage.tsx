import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Inbox, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { StatusPill } from "@/components/common/StatusPill";
import { ApprovalCard } from "@/components/buttlr/ApprovalCard";
import { useAuth } from "@/lib/auth";
import {
  useApprovalStats,
  useApprovals,
  useButtlr,
  useDecideApproval,
  useExecution,
  useMembers,
} from "@/lib/queries";
import type { Approval, Permission } from "@/lib/types";

const PAGE_SIZE = 25;

/** Weakest → strongest, mirroring `PERMISSION_ORDER` on the server. */
const PERMISSION_RANK: Record<Permission, number> = {
  view: 0,
  ask: 1,
  approve: 2,
  execute: 3,
  configure: 4,
  admin: 5,
};

const FILTERS = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "expired", label: "Expired" },
  { value: "all", label: "All" },
] as const;

type FilterValue = (typeof FILTERS)[number]["value"];

function filterFromParams(value: string | null): FilterValue {
  const match = FILTERS.find((filter) => filter.value === value);
  return match ? match.value : "pending";
}

/**
 * Owners and admins always decide. Anyone else needs a grant of `approve` or higher on the
 * Buttlr that raised the request — checked against the grants that apply to them.
 */
function hasApproveGrant(
  permissions: { subject_type: string; subject: string; permission: Permission }[],
  userId: string | undefined,
  role: string | undefined,
  teamIds: string[],
): boolean {
  const applies = (subjectType: string, subject: string): boolean => {
    switch (subjectType) {
      case "everyone":
        return true;
      case "user":
        return Boolean(userId) && subject === userId;
      case "team":
        return teamIds.includes(subject);
      case "role":
        return Boolean(role) && subject === role;
      default:
        return false;
    }
  };
  return permissions.some(
    (grant) =>
      applies(grant.subject_type, grant.subject) && PERMISSION_RANK[grant.permission] >= PERMISSION_RANK.approve,
  );
}

function ApprovalItem({
  approval,
  organizationId,
  userId,
  role,
  teamIds,
  isAdmin,
  onDecide,
  busy,
}: {
  approval: Approval;
  organizationId: string;
  userId?: string;
  role?: string;
  teamIds: string[];
  isAdmin: boolean;
  onDecide: (approval: Approval, granted: boolean, note?: string) => void;
  busy: boolean;
}) {
  const buttlr = useButtlr(organizationId, approval.buttlr_id);
  const execution = useExecution(
    organizationId,
    approval.status === "pending" ? null : approval.execution_id,
  );

  const canDecide =
    approval.status !== "pending" ||
    isAdmin ||
    (buttlr.data
      ? hasApproveGrant(buttlr.data.permissions, userId, role, teamIds)
      : false);

  return (
    <li className="space-y-2">
      {/* One-tap decisions on a phone: full-width, 48px-tall controls on small screens. */}
      <div className="max-sm:[&_button]:h-12 max-sm:[&_button]:w-full max-sm:[&_button]:justify-center">
        <ApprovalCard
          approval={approval}
          canDecide={canDecide}
          loading={busy}
          onDecide={(granted, note) => onDecide(approval, granted, note)}
        />
      </div>
      {approval.status !== "pending" ? (
        <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-muted-foreground">
          <span>Run</span>
          {execution.data ? <StatusPill status={execution.data.status} size="sm" /> : null}
          <Link
            to={`/buttlrs/${approval.buttlr_id}?tab=runs&execution=${approval.execution_id}`}
            className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline"
          >
            Open run
            <ChevronRight aria-hidden="true" className="size-3" />
          </Link>
        </div>
      ) : null}
    </li>
  );
}

export function ApprovalsPage() {
  const { activeOrganization, user } = useAuth();
  const organizationId = activeOrganization?.id ?? null;

  const [searchParams, setSearchParams] = useSearchParams();
  const filter = filterFromParams(searchParams.get("status"));
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);

  const stats = useApprovalStats(organizationId);
  const members = useMembers(organizationId);
  const approvals = useApprovals(
    organizationId,
    organizationId ? { status: filter === "all" ? undefined : filter, limit: PAGE_SIZE, offset } : undefined,
  );
  const decide = useDecideApproval(organizationId ?? "");

  const membership = useMemo(
    () => (members.data ?? []).find((member) => member.user_id === user?.id),
    [members.data, user?.id],
  );
  const role = membership?.role;
  const isAdmin = role === "owner" || role === "admin";
  const teamIds = membership?.team_ids ?? [];

  const setFilter = (next: FilterValue) => {
    const params = new URLSearchParams(searchParams);
    if (next === "pending") params.delete("status");
    else params.set("status", next);
    params.delete("offset");
    setSearchParams(params, { replace: true });
  };

  const setOffset = (next: number) => {
    const params = new URLSearchParams(searchParams);
    if (next <= 0) params.delete("offset");
    else params.set("offset", String(next));
    setSearchParams(params, { replace: true });
  };

  const handleDecide = async (approval: Approval, granted: boolean, note?: string) => {
    try {
      await decide.mutateAsync({ approvalId: approval.id, granted, note });
      toast.success(
        granted
          ? `${approval.buttlr_name} approved: ${approval.action}. The tool will run and the Buttlr continues.`
          : `${approval.buttlr_name} rejected: ${approval.action}. The tool will not run, and the Buttlr has been told why.`,
      );
    } catch (error) {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : "The decision could not be saved. Refresh and try again.",
      );
    }
  };

  const page = approvals.data;
  const items = page?.items ?? [];
  const total = page?.total ?? 0;
  const canGoBack = offset > 0;
  const canGoForward = offset + PAGE_SIZE < total;

  const emptyCopy: Record<FilterValue, { title: string; description: string }> = {
    pending: {
      title: "Nothing is waiting for you",
      description:
        "When a Buttlr reaches a step its approval policy protects, it appears here and waits for a decision.",
    },
    approved: {
      title: "No approvals granted yet",
      description: "Requests you approve are listed here with the note you left.",
    },
    rejected: {
      title: "Nothing has been rejected",
      description: "Requests you turn down are listed here with the reason you gave.",
    },
    expired: {
      title: "Nothing expired",
      description:
        "Approvals that go unanswered past their expiry are listed here, and the run they belonged to has stopped.",
    },
    all: {
      title: "No approval requests yet",
      description: "Run a Buttlr that needs approval and its requests will be recorded here.",
    },
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        description="Requests from Buttlrs that cannot continue until someone decides."
      />

      <section aria-label="Approval totals" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {FILTERS.filter((entry) => entry.value !== "all").map((entry) => {
          const key = entry.value as "pending" | "approved" | "rejected" | "expired";
          return (
            <button
              key={entry.value}
              type="button"
              onClick={() => setFilter(entry.value)}
              aria-pressed={filter === entry.value}
              className="rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <StatCard
                label={entry.label}
                value={
                  stats.data
                    ? stats.data[key]
                    : stats.isLoading
                      ? ""
                      : "0"
                }
                loading={stats.isLoading}
                tone={
                  key === "rejected"
                    ? "destructive"
                    : key === "pending"
                      ? "warning"
                      : key === "approved"
                        ? "success"
                        : "default"
                }
                icon={key === "pending" ? ShieldCheck : undefined}
              />
            </button>
          );
        })}
      </section>

      <div
        role="tablist"
        aria-label="Approval status"
        className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0"
      >
        {FILTERS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            role="tab"
            aria-selected={filter === entry.value}
            onClick={() => setFilter(entry.value)}
            className={
              filter === entry.value
                ? "shrink-0 rounded-md bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm"
                : "shrink-0 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            {entry.label}
          </button>
        ))}
      </div>

      {approvals.isError ? (
        <ErrorState error={approvals.error} onRetry={() => void approvals.refetch()} />
      ) : approvals.isLoading ? (
        <ul className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <li key={index}>
              <Skeleton className="h-52 w-full rounded-lg" />
            </li>
          ))}
        </ul>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={emptyCopy[filter].title}
          description={emptyCopy[filter].description}
          action={
            <Button asChild variant="outline">
              <Link to="/buttlrs">Go to Buttlrs</Link>
            </Button>
          }
        />
      ) : (
        <>
          <ul className="space-y-4">
            {items.map((approval) => (
              <ApprovalItem
                key={approval.id}
                approval={approval}
                organizationId={organizationId ?? ""}
                userId={user?.id}
                role={role}
                teamIds={teamIds}
                isAdmin={isAdmin}
                onDecide={(target, granted, note) => void handleDecide(target, granted, note)}
                busy={decide.isPending}
              />
            ))}
          </ul>

          {total > PAGE_SIZE ? (
            <nav aria-label="Approval pages" className="flex items-center justify-between gap-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoBack || approvals.isFetching}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                <ChevronLeft aria-hidden="true" className="mr-1 h-4 w-4" />
                Previous
              </Button>
              <span className="text-xs text-muted-foreground tabular-nums">
                {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)} of {total}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!canGoForward || approvals.isFetching}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
                <ChevronRight aria-hidden="true" className="ml-1 h-4 w-4" />
              </Button>
            </nav>
          ) : null}
        </>
      )}
    </div>
  );
}