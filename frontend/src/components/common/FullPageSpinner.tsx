import { Loader2 } from "lucide-react";

export interface FullPageSpinnerProps {
  label?: string;
}

/**
 * Used only while the session itself is resolving — it gates the router, so
 * there is no page skeleton to shape it after. Pages that already have a layout
 * use skeletons instead.
 */
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