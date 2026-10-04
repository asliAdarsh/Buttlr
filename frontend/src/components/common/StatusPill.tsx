import {
  Ban,
  CheckCircle2,
  CircleDot,
  Clock,
  FileEdit,
  Loader2,
  PauseCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { humanize, toneFor, type Tone } from "@/lib/format";
import type {
  ApprovalStatus,
  ButtlrStatus,
  ExecutionStatus,
  IntegrationStatus,
} from "@/lib/types";

export type StatusValue = ButtlrStatus | ExecutionStatus | ApprovalStatus | IntegrationStatus;

const ICONS: Record<string, LucideIcon> = {
  active: CheckCircle2,
  completed: CheckCircle2,
  connected: CheckCircle2,
  approved: CheckCircle2,
  running: Loader2,
  queued: CircleDot,
  waiting_approval: Clock,
  pending: Clock,
  paused: PauseCircle,
  blocked: PauseCircle,
  failed: XCircle,
  error: XCircle,
  rejected: XCircle,
  draft: FileEdit,
  disabled: Ban,
  cancelled: Ban,
  expired: Ban,
};

function textFor(status: StatusValue): string {
  return status === "waiting_approval" ? "Waiting approval" : humanize(status);
}

export interface StatusPillProps {
  status: StatusValue;
  size?: "sm" | "md";
}

/** Always an icon *and* a word: the tone reinforces the meaning, it never carries it. */
export function StatusPill({ status, size = "md" }: StatusPillProps) {
  const tone: Tone = toneFor(status);
  const Icon = ICONS[status] ?? CircleDot;

  return (
    <Badge
      tone={tone}
      className={size === "sm" ? "px-1.5 py-0 text-[11px] leading-4" : undefined}
    >
      <Icon className={status === "running" ? "animate-spin" : undefined} aria-hidden="true" />
      {textFor(status)}
    </Badge>
  );
}