import { Shield } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { humanize, toneFor, type Tone } from "@/lib/format";
import type { RiskLevel } from "@/lib/types";

const TONE: Record<RiskLevel, Tone> = {
  low: "muted",
  medium: "warning",
  high: "destructive",
  critical: "destructive",
};

const RING: Record<RiskLevel, string> = {
  low: "",
  medium: "",
  high: "border-destructive/60 font-semibold",
  critical: "border-destructive font-semibold",
};

export interface RiskBadgeProps {
  risk: RiskLevel;
}

export function RiskBadge({ risk }: RiskBadgeProps) {
  const tone = TONE[risk] ?? toneFor(risk);

  return (
    <Badge tone={tone} className={RING[risk]}>
      <Shield aria-hidden="true" />
      {humanize(risk)}
    </Badge>
  );
}