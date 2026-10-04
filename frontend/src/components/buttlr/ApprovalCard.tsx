import { useState } from "react";
import { Lock, ShieldX, Timer, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { RiskBadge } from "@/components/common/RiskBadge";
import { StatusPill } from "@/components/common/StatusPill";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDateTime } from "@/lib/format";
import type { Approval } from "@/lib/types";
import { ButtlrAvatar } from "./ButtlrAvatar";

function minutesLeft(expiresAt?: string | null): number | null {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (Number.isNaN(ms)) return null;
  return Math.round(ms / 60_000);
}

export function ApprovalCard({
  approval,
  canDecide,
  onDecide,
  loading = false,
}: {
  approval: Approval;
  canDecide: boolean;
  onDecide: (granted: boolean, note?: string) => void;
  loading?: boolean;
}) {
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const pending = approval.status === "pending";
  const left = minutesLeft(approval.expires_at);

  const decide = (granted: boolean) => {
    const trimmed = note.trim();
    onDecide(granted, trimmed === "" ? undefined : trimmed);
  };

  return (
    <article className="rounded-lg border border-border bg-card p-4">
      <header className="flex flex-wrap items-center gap-2">
        <RiskBadge risk={approval.risk} />
        <StatusPill status={approval.status} size="sm" />
        <span className="ml-auto text-xs text-muted-foreground">
          {formatDateTime(approval.requested_at)}
        </span>
      </header>

      <div className="mt-3 flex items-center gap-2">
        <ButtlrAvatar buttlr={{ name: approval.buttlr_name, avatar: "" }} size="xs" />
        <span className="truncate text-sm font-medium">{approval.buttlr_name}</span>
      </div>

      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex gap-2">
          <dt className="w-20 shrink-0 text-muted-foreground">Action</dt>
          <dd className="min-w-0 flex-1">
            {approval.action}
            {approval.tool ? (
              <span className="ml-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Wrench aria-hidden="true" className="size-3" />
                {approval.tool}
              </span>
            ) : null}
          </dd>
        </div>
        {approval.resource ? (
          <div className="flex gap-2">
            <dt className="w-20 shrink-0 text-muted-foreground">Resource</dt>
            <dd className="min-w-0 flex-1 break-words">{approval.resource}</dd>
          </div>
        ) : null}
        <div className="flex gap-2">
          <dt className="w-20 shrink-0 text-muted-foreground">Reason</dt>
          <dd className="min-w-0 flex-1 break-words">{approval.reason}</dd>
        </div>
      </dl>

      {left !== null && pending ? (
        <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Timer aria-hidden="true" className="size-3" />
          {left > 0 ? `Expires in ${left} minutes` : "Expiring now"}
        </p>
      ) : null}

      {pending ? (
        <div className="mt-4 space-y-3">
          {showNote ? (
            <div className="space-y-1.5">
              <Label htmlFor={`approval-note-${approval.id}`}>Note (optional)</Label>
              <Textarea
                id={`approval-note-${approval.id}`}
                value={note}
                rows={3}
                placeholder="Why you made this decision — recorded in the audit trail."
                onChange={(event) => setNote(event.target.value)}
              />
            </div>
          ) : (
            <button
              type="button"
              className="text-xs font-medium text-primary hover:underline"
              onClick={() => setShowNote(true)}
            >
              Add a note
            </button>
          )}

          {canDecide ? (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => decide(true)} loading={loading} variant="success">
                Approve
              </Button>
              <Button onClick={() => decide(false)} loading={loading} variant="destructive">
                <ShieldX aria-hidden="true" className="mr-1.5 size-4" />
                Reject
              </Button>
            </div>
          ) : (
            <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex">
                    <Button variant="outline" disabled>
                      <Lock aria-hidden="true" className="mr-1.5 size-4" />
                      Approval
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  Your organization role does not allow approving requests at this level.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3 text-sm">
          <p className="font-medium">
            {approval.status === "approved" ? "Approved" : "Rejected"} by{" "}
            {approval.decided_by_name ?? "a member of this organization"}
            {approval.decided_at ? ` · ${formatDateTime(approval.decided_at)}` : ""}
          </p>
          {approval.decision_note ? (
            <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{approval.decision_note}</p>
          ) : (
            <p className="mt-1 text-muted-foreground">No note was left.</p>
          )}
        </div>
      )}
    </article>
  );
}
