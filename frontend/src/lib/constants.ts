import type { Permission, RiskLevel, ScheduleKind } from "@/lib/types";

export const DEPARTMENTS: string[] = [
  "Engineering",
  "Finance",
  "HR",
  "Marketing",
  "Sales",
  "Customer Support",
  "Operations",
];

export const ACCENTS: { value: "violet" | "blue" | "emerald" | "rose" | "amber"; label: string }[] = [
  { value: "violet", label: "Violet" },
  { value: "blue", label: "Blue" },
  { value: "emerald", label: "Emerald" },
  { value: "rose", label: "Rose" },
  { value: "amber", label: "Amber" },
];

export const SCHEDULE_PRESETS: { value: ScheduleKind; label: string }[] = [
  { value: "manual", label: "Only when someone starts it" },
  { value: "once", label: "Once at a specific time" },
  { value: "hourly", label: "Every hour" },
  { value: "daily", label: "Every day" },
  { value: "weekly", label: "Every week" },
  { value: "monthly", label: "Every month" },
  { value: "interval", label: "Every N minutes" },
  { value: "cron", label: "Custom (cron)" },
];

export const RISK_LEVELS: RiskLevel[] = ["low", "medium", "high", "critical"];

export const PERMISSION_LEVELS: { value: Permission; label: string; description: string }[] = [
  {
    value: "view",
    label: "View",
    description: "Can see this Buttlr and its past runs, but cannot change anything or start it.",
  },
  {
    value: "ask",
    label: "Ask",
    description: "Can send questions to this Buttlr and read its answers.",
  },
  {
    value: "approve",
    label: "Approve",
    description: "Can decide whether a run continues when it asks for approval.",
  },
  {
    value: "execute",
    label: "Execute",
    description: "Can start runs and cancel runs that are still waiting.",
  },
  {
    value: "configure",
    label: "Configure",
    description: "Can change this Buttlr's instructions, schedule, tools and approval policy.",
  },
  {
    value: "admin",
    label: "Admin",
    description: "Full control, including deleting this Buttlr and managing who it works for.",
  },
];