import { format, formatDistanceToNowStrict, isValid, parseISO } from "date-fns";

function toDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = parseISO(value);
  return isValid(parsed) ? parsed : null;
}

/** Local date + time, e.g. "4 Oct, 09:04". */
export function formatDateTime(value?: string | null): string {
  const date = toDate(value);
  return date ? format(date, "d MMM, HH:mm") : "—";
}

/** Local date only, e.g. "4 Oct 2026". */
export function formatDate(value?: string | null): string {
  const date = toDate(value);
  return date ? format(date, "d MMM yyyy") : "—";
}

/** "3 minutes ago" — falls back to a dash when there is no timestamp. */
export function formatRelative(value?: string | null): string {
  const date = toDate(value);
  if (!date) return "never";
  return `${formatDistanceToNowStrict(date)} ago`;
}

export function formatDuration(ms?: number | null): string {
  if (ms === undefined || ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function formatTokens(count?: number | null): string {
  if (!count) return "0";
  if (count < 1000) return String(count);
  if (count < 1_000_000) return `${(count / 1000).toFixed(1)}k`;
  return `${(count / 1_000_000).toFixed(2)}M`;
}

export function formatCost(usd?: number | null): string {
  if (!usd) return "$0.00";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

/** "monday" → "Monday", "waiting_approval" → "Waiting approval". */
export function humanize(value?: string | null): string {
  if (!value) return "—";
  const cleaned = value.replace(/[_-]+/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/** "github.list_pull_requests" → "List pull requests". */
export function toolLabel(tool?: string | null): string {
  if (!tool) return "—";
  const [, action] = tool.includes(".") ? tool.split(".", 2) : ["", tool];
  return humanize(action.replace(/_/g, " "));
}

const PROVIDER_LABELS: Record<string, string> = {
  github: "GitHub",
  google: "Google",
  jira: "Jira",
};

export function providerLabel(provider?: string | null): string {
  if (!provider) return "—";
  return PROVIDER_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1);
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

const TONES: Record<string, string> = {
  active: "success",
  completed: "success",
  connected: "success",
  approved: "success",
  running: "primary",
  queued: "primary",
  waiting_approval: "warning",
  pending: "warning",
  draft: "muted",
  paused: "warning",
  disabled: "muted",
  failed: "destructive",
  error: "destructive",
  rejected: "destructive",
  expired: "muted",
  cancelled: "muted",
  blocked: "warning",
  low: "muted",
  medium: "warning",
  high: "destructive",
  critical: "destructive",
};

export type Tone = "success" | "primary" | "warning" | "destructive" | "muted";

export function toneFor(value?: string | null): Tone {
  if (!value) return "muted";
  return (TONES[value] as Tone | undefined) ?? "muted";
}
