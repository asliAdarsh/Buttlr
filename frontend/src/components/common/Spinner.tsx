import * as React from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SpinnerProps extends React.HTMLAttributes<HTMLSpanElement> {}

export function Spinner({ className, ...props }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn("inline-flex shrink-0 text-muted-foreground", className)}
      {...props}
    >
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
    </span>
  );
}