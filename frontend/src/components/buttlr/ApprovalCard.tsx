import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FileJson,
  Lock,
  ShieldX,
  Wrench,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { RiskBadge } from "@/components/common/RiskBadge";
import { StatusPill } from "@/components/common/StatusPill";
import { cn } from "@/lib/utils";
import { formatDateTime, formatRelative, providerLabel, toolLabel } from "@/lib/format";
import type { Approval, Execution } from "@/lib/types";
import { ButtlrAvatar } from "./ButtlrAvatar";

/** Tool names are prefixed by the integration they belong to; several map to one app. */
const APP_BY_TOOL_PREFIX: Record<string, string> = {
  github: "GitHub",
  jira: "Jira",
  gmail: "Google",
  drive: "Google",
  sheets: "Google",
  calendar: "Google",
  docs: "Google",
};

function appFor(tool: string): string {
  const prefix = tool.includes(".") ? tool.split(".", 2)[0] : "";
  return APP_BY_TOOL_PREFIX[prefix] ?? providerLabel(prefix);
}

/** The server labels a target `repository=acme/backend`; a person only wants the value. */
function targetOf(resource?: string | null): string | null {
  if (!resource) return null;
  const value = (resource.includes("=") ? resource.slice(resource.indexOf("=") + 1) : resource).trim();
  return value === "" ? null : value;
}

/** "Create issue in acme/backend" — restates the action without opening anything. */
export function describeApproval(approval: Approval): string {
  const action = toolLabel(approval.tool);
  const target = targetOf(approval.resource);
  return target ? `${action} in ${target}` : action;
}

/** A ticking clock for the expiry countdown; only runs while the request is live. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function expiryLabel(msLeft: number): string {
  if (msLeft <= 0) return "Past its expiry — this run has stopped";
  const minutes = Math.ceil(msLeft / 60_000);
  if (minutes < 60) return `Expires in ${minutes} min`;
  return `Expires in ${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

type Intent = "approve" | "reject" | "note";

export function ApprovalCard({
  approval,
  canDecide,
  checking = false,
  onDecide,
  loading = false,
  execution = null,
}: {
  approval: Approval;
  canDecide: boolean;
  /** Permissions are still loading, so the verdict is not known yet. */
  checking?: boolean;
  onDecide: (granted: boolean, note?: string) => void;
  loading?: boolean;
  /** The run this request belongs to, once it has been decided. */
  execution?: Execution | null;
}) {
  const [note, setNote] = useState("");
  const [sheet, setSheet] = useState<Intent | null>(null);
  const [showParams, setShowParams] = useState(false);
  const noteId = useId();

  const pending = approval.status === "pending";
  const target = targetOf(approval.resource);
  const now = useNow(pending && Boolean(approval.expires_at));
  const msLeft = approval.expires_at
    ? new Date(approval.expires_at).getTime() - now
    : Number.NaN;
  const hasCountdown = pending && Number.isFinite(msLeft);
  // Low and medium risk approve straight away; anything that writes somewhere, and every
  // rejection, restates the action in a sheet first so the tap is never a guess.
  const confirmFirst = approval.risk === "high" || approval.risk === "critical";
  const paramEntries = Object.keys(approval.params ?? {});
  const busy = loading || checking;

  const submit = (granted: boolean) => {
    const trimmed = note.trim();
    setSheet(null);
    onDecide(granted, trimmed === "" ? undefined : trimmed);
  };

  const approve = () => (confirmFirst ? setSheet("approve") : submit(true));

  const lockedReason = checking
    ? "Checking what you are allowed to decide…"
    : "Your role does not allow approving requests from this Buttlr.";

  // Only ever rendered when the person may decide, so the buttons carry no lock state.
  const decisionButtons = (
    <div className="grid grid-cols-2 gap-2">
      <Button
        type="button"
        variant="destructive"
        className="max-sm:h-12"
        disabled={busy}
        onClick={() => setSheet("reject")}
      >
        <ShieldX aria-hidden="true" />
        Reject
      </Button>
      <Button
        type="button"
        variant="success"
        className="max-sm:h-12"
        loading={loading}
        disabled={busy}
        onClick={approve}
      >
        <CheckCircle2 aria-hidden="true" />
        Approve
      </Button>
    </div>
  );

  return (
    <article
      aria-label={`${appFor(approval.tool)}: ${describeApproval(approval)}`}
      className={cn(
        "rounded-lg border border-border bg-card p-4",
        pending && "border-l-4 border-l-primary",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {appFor(approval.tool)}
          </p>
          <h3 className="text-base font-semibold leading-tight text-foreground">
            {toolLabel(approval.tool)}
          </h3>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <RiskBadge risk={approval.risk} />
          <StatusPill status={approval.status} size="sm" />
        </div>
      </div>

      {target ? (
        <p className="mt-2 break-all font-mono text-sm text-foreground">{target}</p>
      ) : null}

      {approval.action && approval.action !== toolLabel(approval.tool) ? (
        <p className="mt-2 text-sm text-muted-foreground">{approval.action}</p>
      ) : null}

      <p className="mt-2 text-sm text-foreground">
        <span className="font-medium text-muted-foreground">Why: </span>
        {approval.reason}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <ButtlrAvatar buttlr={{ name: approval.buttlr_name, avatar: "" }} size="xs" />
          <span className="font-medium text-foreground">{approval.buttlr_name}</span>
          <span>requested</span>
          <time dateTime={approval.requested_at} title={formatDateTime(approval.requested_at)}>
            {formatRelative(approval.requested_at)}
          </time>
        </span>
        {hasCountdown ? (
          <span
            className={cn(
              "inline-flex items-center gap-1",
              msLeft <= 0
                ? "text-destructive"
                : msLeft <= 10 * 60_000
                  ? "text-warning"
                  : undefined,
            )}
          >
            <Clock aria-hidden="true" className="size-3" />
            {expiryLabel(msLeft)}
          </span>
        ) : null}
      </div>

      {paramEntries.length > 0 ? (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={showParams}
            aria-controls={showParams ? `params-${approval.id}` : undefined}
            onClick={() => setShowParams((open) => !open)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
          >
            <FileJson aria-hidden="true" className="size-3.5" />
            {showParams ? "Hide details" : "Show details"}
            <ChevronDown
              aria-hidden="true"
              className={cn("size-3.5 transition-transform", showParams && "rotate-180")}
            />
          </button>
          {showParams ? (
            <>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Exactly what will be sent to {appFor(approval.tool)}.
              </p>
              <pre
                id={`params-${approval.id}`}
                className="mt-1.5 max-h-56 overflow-y-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground"
              >
                {JSON.stringify(approval.params, null, 2)}
              </pre>
            </>
          ) : null}
        </div>
      ) : null}

      {pending ? (
        <div className="mt-4 space-y-3">
          {canDecide ? (
            <>
              {decisionButtons}
              <button
                type="button"
                className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                onClick={() => setSheet("note")}
              >
                <Wrench aria-hidden="true" className="size-3.5" />
                Add a note to this decision
              </button>
            </>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex w-full">
                  <Button variant="outline" className="w-full max-sm:h-12" disabled>
                    <Lock aria-hidden="true" />
                    {checking ? "Checking…" : "Not yours to decide"}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{lockedReason}</TooltipContent>
            </Tooltip>
          )}
        </div>
      ) : (
        <div
          className={cn(
            "mt-4 rounded-md border p-3 text-sm",
            approval.status === "approved"
              ? "border-success/40 bg-success/5"
              : "border-border bg-muted/40",
          )}
        >
          <p className="flex items-start gap-2 font-medium text-foreground">
            {approval.status === "approved" ? (
              <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <XCircle aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-destructive" />
            )}
            <span>
              {approval.status === "approved" ? "Approved" : "Rejected"} ·{" "}
              {describeApproval(approval)}
            </span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {approval.status === "approved"
              ? `${approval.buttlr_name} continues from here.`
              : `The tool did not run, and ${approval.buttlr_name} was told why.`}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {approval.decided_by_name ?? "Someone"} ·{" "}
            {approval.decided_at ? formatDateTime(approval.decided_at) : "just now"}
          </p>
          {approval.decision_note ? (
            <p className="mt-2 whitespace-pre-wrap border-l-2 border-border pl-2 text-muted-foreground">
              {approval.decision_note}
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">No note was left.</p>
          )}

          {execution ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-xs text-muted-foreground">
              <span>Run</span>
              <StatusPill status={execution.status} size="sm" />
              <Link
                to={`/buttlrs/${approval.buttlr_id}?tab=runs&execution=${approval.execution_id}`}
                className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline"
              >
                Open run
                <ChevronRight aria-hidden="true" className="size-3" />
              </Link>
            </div>
          ) : null}
        </div>
      )}

      {/* On a phone this renders as a bottom sheet, so the note never shifts the list. */}
      <Dialog
        open={sheet !== null}
        onOpenChange={(open) => {
          if (!open) setSheet(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {sheet === "approve"
                ? "Approve this action?"
                : sheet === "reject"
                  ? "Reject this action?"
                  : "Add a note, then decide"}
            </DialogTitle>
            <DialogDescription>
              {sheet === "approve"
                ? `${approval.buttlr_name} will run ${describeApproval(approval)} in ${appFor(approval.tool)} straight away.`
                : sheet === "reject"
                  ? `${approval.buttlr_name} will not be able to ${describeApproval(approval)}. It is told the note you leave here.`
                  : `Leave a note for ${approval.buttlr_name}, then approve or reject ${describeApproval(approval)}.`}
            </DialogDescription>
          </DialogHeader>

          <dl className="mt-3 space-y-1.5 rounded-md border border-border bg-muted/40 p-3 text-sm">
            <div className="flex gap-2">
              <dt className="w-16 shrink-0 text-muted-foreground">Risk</dt>
              <dd>
                <RiskBadge risk={approval.risk} />
              </dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-16 shrink-0 text-muted-foreground">Target</dt>
              <dd className="min-w-0 flex-1 break-all">{target ?? "—"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="w-16 shrink-0 text-muted-foreground">Why</dt>
              <dd className="min-w-0 flex-1">{approval.reason}</dd>
            </div>
          </dl>

          <div className="mt-3 space-y-1.5">
            <Label htmlFor={noteId}>Note (optional)</Label>
            <Textarea
              id={noteId}
              autoFocus
              rows={3}
              value={note}
              placeholder="Recorded in the audit trail and shown to the Buttlr."
              onChange={(event) => setNote(event.target.value)}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={loading}
              onClick={() => setSheet(null)}
            >
              Cancel
            </Button>
            {sheet === "note" ? (
              <>
                <Button
                  type="button"
                  variant="destructive"
                  loading={loading}
                  onClick={() => submit(false)}
                >
                  Reject
                </Button>
                <Button
                  type="button"
                  variant="success"
                  loading={loading}
                  onClick={() => submit(true)}
                >
                  Approve
                </Button>
              </>
            ) : (
              <Button
                type="button"
                variant={sheet === "approve" ? "success" : "destructive"}
                loading={loading}
                onClick={() => submit(sheet === "approve")}
              >
                {sheet === "approve" ? "Approve and run" : "Reject"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </article>
  );
}