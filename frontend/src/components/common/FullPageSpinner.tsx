import { Loader2 } from "lucide-react";

export interface FullPageSpinnerProps {
  label?: string;
}

export function FullPageSpinner({ label = "Loading…" }: FullPageSpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-[60vh] w-full flex-col items-center justify-center gap-3 p-8 text-muted-foreground"
    >
      <Loader2 className="size-6 animate-spin" aria-hidden="true" />
      <p className="text-sm">{label}</p>
    </div>
  );
}