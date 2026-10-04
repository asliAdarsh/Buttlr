import { CalendarClock, Clock, PlayCircle, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Schedule } from "@/lib/types";

/** Short, concrete label for a schedule, e.g. "Every 30 minutes · Mon–Fri". */
export function describeSchedule(schedule: Schedule): string {
  const days = schedule.day_of_week ? schedule.day_of_week.split(",").map((d) => d.trim()) : [];
  const weekday = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

  switch (schedule.kind) {
    case "manual":
      return "Runs on request";
    case "once":
      return schedule.run_at ? `Once at ${schedule.run_at}` : "Once";
    case "interval":
      return schedule.interval_minutes
        ? `Every ${schedule.interval_minutes} minutes`
        : "On an interval";
    case "hourly":
      return schedule.at ? `Hourly at ${schedule.at}` : "Every hour";
    case "daily":
      return schedule.at ? `Daily at ${schedule.at}` : "Every day";
    case "weekly":
      return days.length ? `Weekly on ${days.map(weekday).join(", ")}` : "Every week";
    case "monthly":
      return schedule.day_of_month
        ? `Monthly on day ${schedule.day_of_month}`
        : "Every month";
    case "cron":
      return schedule.cron ? `Cron ${schedule.cron}` : "Cron schedule";
  }
}

export function ScheduleBadge({ schedule }: { schedule: Schedule }) {
  const label = describeSchedule(schedule);
  const Icon = !schedule.enabled
    ? PlayCircle
    : schedule.kind === "cron" || schedule.kind === "interval"
      ? Zap
      : schedule.kind === "manual"
        ? Clock
        : CalendarClock;

  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs leading-5",
        !schedule.enabled && "text-muted-foreground",
      )}
      title={`${label}${schedule.enabled ? "" : " (paused)"} · ${schedule.timezone}`}
    >
      <Icon aria-hidden="true" className="size-3 shrink-0" />
      <span className="truncate">{schedule.enabled ? label : "Schedule paused"}</span>
      <span className="sr-only">{schedule.enabled ? "" : ", schedule paused"}</span>
    </span>
  );
}