import { Shield, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { humanize, toneFor, type Tone } from "@/lib/format";
import type { RiskLevel } from "@/lib/types";

const TONE: Record<RiskLevel, Tone> = {
  low: "muted",
  medium: "warning",
  high: "destructive",
  critical: "destructive",
};

export interface RiskBadgeProps {
  risk: RiskLevel;
}

/** Shield plus the written level, so severity never depends on colour alone. */
export function RiskBadge({ risk }: RiskBadgeProps) {
  const tone = TONE[risk] ?? toneFor(risk);
  const Icon = risk === "low" ? Shield : ShieldAlert;

  return (
    <Badge tone={tone} className={risk === "high" || risk === "critical" ? "font-semibold" : undefined}>
      <Icon aria-hidden="true" />
      {humanize(risk)}
    </Badge>
  );
}