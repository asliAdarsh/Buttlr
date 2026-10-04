import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Inbox, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { RiskBadge } from "@/components/common/RiskBadge";
import { ApprovalCard, describeApproval } from "@/components/buttlr/ApprovalCard";
import { useAuth } from "@/lib/auth";
import {
  useApprovalStats,
  useApprovals,
  useButtlrs,
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
type Counted = Exclude<FilterValue, "all">;

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
      applies(grant.subject_type, grant.subject) &&
      PERMISSION_RANK[grant.permission] >= PERMISSION_RANK.approve,
  );
}


function ApprovalItem({
  approval,
  organizationId,
  canDecide,
  checking,
  highlighted,
  onDecide,
  busy,
}: {
  approval: Approval;
  organizationId: string;
  canDecide: boolean;
  /** Permissions are still loading, so the verdict is not known yet. */
  checking: boolean;
  /** The request a notification linked to, so the eye lands on the right card. */
  highlighted: boolean;
  onDecide: (approval: Approval, granted: boolean, note?: string) => void;
  busy: boolean;
}) {
  // Only the decided ones: while a request is pending the run is knowingly paused.
  const execution = useExecution(
    organizationId,
    approval.status === "pending" ? null : approval.execution_id,
  );

  return (
    <li
      ref={(node) => {
        if (highlighted && node) node.scrollIntoView({ block: "center" });
      }}
      className={highlighted ? "scroll-mt-24 rounded-lg ring-2 ring-ring" : undefined}
    >
      <ApprovalCard
        approval={approval}
        canDecide={canDecide}
        checking={checking}
        loading={busy}
        execution={execution.data ?? null}
        onDecide={(granted, note) => onDecide(approval, granted, note)}
      />
    </li>
  );
}

/**
 * "Approve all" never skips a decision: the sheet lists every action, with its risk and
 * target, before anything is sent. High and critical requests are refused outright — a
 * person reads those one at a time.
 */
function BatchDialog({
  open,
  onOpenChange,
  approvals,
  onConfirm,
  loading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  approvals: Approval[];
  onConfirm: (note?: string) => void;
  loading: boolean;
}) {
  const [note, setNote] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Approve {approvals.length} requests?</DialogTitle>
          <DialogDescription>
            Each of these runs as soon as you confirm. Read the list — anything high or
            critical risk is not included and still needs its own decision.
          </DialogDescription>
        </DialogHeader>

        <ul className="mt-3 max-h-60 space-y-2 overflow-y-auto">
          {approvals.map((approval) => (
            <li
              key={approval.id}
              className="rounded-md border border-border bg-muted/40 p-2.5 text-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="min-w-0 font-medium text-foreground">
                  {approval.buttlr_name}
                </span>
                <RiskBadge risk={approval.risk} />
              </div>
              <p className="mt-0.5 text-muted-foreground">{describeApproval(approval)}</p>
            </li>
          ))}
        </ul>

        <div className="mt-3 space-y-1.5">
          <Label htmlFor="batch-note">Note for all {approvals.length} (optional)</Label>
          <Textarea
            id="batch-note"
            rows={2}
            value={note}
            placeholder="Recorded against every request in this batch."
            onChange={(event) => setNote(event.target.value)}
          />
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="success"
            loading={loading}
            onClick={() => onConfirm(note.trim() === "" ? undefined : note.trim())}
          >
            Approve {approvals.length}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ApprovalsPage() {
  const { activeOrganization, user } = useAuth();
  const organizationId = activeOrganization?.id ?? null;

  const [searchParams, setSearchParams] = useSearchParams();
  const filter = filterFromParams(searchParams.get("status"));
  const offset = Math.max(0, Number(searchParams.get("offset") ?? "0") || 0);
  // A notification links to one request; the list scrolls to it once it is on screen.
  const focusId = searchParams.get("approval");
  const [batchOpen, setBatchOpen] = useState(false);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  const stats = useApprovalStats(organizationId);
  const members = useMembers(organizationId);
  // One list read answers "may I decide this?" for every card, so batching can honour it.
  const buttlrs = useButtlrs(organizationId);
  const approvals = useApprovals(
    organizationId,
    organizationId
      ? { status: filter === "all" ? undefined : filter, limit: PAGE_SIZE, offset }
      : undefined,
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
    params.delete("approval");
  };

  const setOffset = (next: number) => {
    const params = new URLSearchParams(searchParams);
    if (next <= 0) params.delete("offset");
    else params.set("offset", String(next));
    setSearchParams(params, { replace: true });
  };

  const handleDecide = useCallback(
    async (approval: Approval, granted: boolean, note?: string) => {
      setDecidingId(approval.id);
      try {
        await decide.mutateAsync({ approvalId: approval.id, granted, note });
        toast.success(
          granted
            ? `Approved: ${describeApproval(approval)}. The run continues.`
            : `Rejected: ${describeApproval(approval)}. The Buttlr was told why.`,
        );
      } catch (error) {
        // The card keeps the note it had, so nothing the person typed is lost.
        toast.error(
          error instanceof Error && error.message
            ? error.message
            : "The decision could not be saved. Refresh and try again.",
        );
      } finally {
        setDecidingId(null);
      }
    },
    [decide],
  );

  const page = approvals.data;
  const items = useMemo(() => page?.items ?? [], [page]);
  const total = page?.total ?? 0;
  const canGoBack = offset > 0;
  const canGoForward = offset + PAGE_SIZE < total;

  const counts = stats.data;
  const countFor = (key: FilterValue): number | null =>
    key === "all" ? null : (counts?.[key as Counted] ?? null);

  const grantsLoading = !isAdmin && buttlrs.isLoading;

  const decidable = useCallback(
    (approval: Approval) => {
      if (isAdmin) return true;
      const buttlr = (buttlrs.data ?? []).find((entry) => entry.id === approval.buttlr_id);
      return buttlr ? hasApproveGrant(buttlr.permissions, user?.id, role, teamIds) : false;
    },
    [buttlrs.data, isAdmin, role, teamIds, user?.id],
  );

  // Batching is deliberately limited to what a person can wave through at a glance: a
  // request they may not decide is never swept up, and neither is a high-risk one.
  const batchable = useMemo(
    () =>
      filter === "pending" && !grantsLoading
        ? items.filter(
            (approval) =>
              approval.status === "pending" &&
              approval.risk !== "high" &&
              approval.risk !== "critical" &&
              decidable(approval),
          )
        : [],
    [decidable, filter, grantsLoading, items],
  );

  const runBatch = async (note?: string) => {
    let done = 0;
    let failed = 0;
    for (const approval of batchable) {
      try {
        await decide.mutateAsync({ approvalId: approval.id, granted: true, note });
        done += 1;
      } catch {
        failed += 1;
      }
    }
    setBatchOpen(false);
    if (failed === 0) {
      toast.success(`Approved ${done} requests. Each run continues.`);
    } else {
      toast.error(
        `Approved ${done} of ${batchable.length}. ${failed} could not be saved — open them to decide again.`,
      );
    }
  };

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
        actions={
          batchable.length > 1 ? (
            <Button type="button" variant="outline" onClick={() => setBatchOpen(true)}>
              <Zap aria-hidden="true" />
              Approve {batchable.length} low-risk
            </Button>
          ) : null
        }
      />

      <p className="-mt-2 text-sm text-muted-foreground">
        {stats.isLoading ? (
          "Checking what is waiting…"
        ) : stats.data?.pending ? (
          `${stats.data.pending} ${stats.data.pending === 1 ? "request is" : "requests are"} waiting for a decision.`
        ) : (
          "Nothing is waiting for a decision."
        )}
      </p>

      {/* A filter row, not tabs — each button states its own pressed state. */}
      <div
        role="group"
        aria-label="Filter approvals by status"
        className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0"
      >
        {FILTERS.map((entry) => {
          const count = countFor(entry.value);
          const selected = filter === entry.value;
          return (
            <button
              key={entry.value}
              type="button"
              aria-pressed={selected}
              onClick={() => setFilter(entry.value)}
              className={
                selected
                  ? "inline-flex shrink-0 items-center gap-1.5 rounded-md bg-card px-3 py-2 text-sm font-medium text-foreground shadow-sm"
                  : "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              }
            >
              {entry.label}
              {count === null ? null : (
                <span
                  className={
                    selected
                      ? "rounded-full bg-primary/10 px-1.5 py-0.5 text-xs tabular-nums text-primary"
                      : "rounded-full bg-muted px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground"
                  }
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
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
                canDecide={approval.status !== "pending" || decidable(approval)}
                checking={grantsLoading && approval.status === "pending"}
                highlighted={approval.id === focusId}
                onDecide={(target, granted, note) => void handleDecide(target, granted, note)}
                busy={decide.isPending && decidingId === approval.id}
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

      <BatchDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        approvals={batchable}
        onConfirm={(note) => void runBatch(note)}
        loading={decide.isPending}
      />
    </div>
  );
}