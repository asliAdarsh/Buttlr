import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

import { cn } from "@/lib/utils";

/** Safe to render per-use: Radix keeps provider state scoped to each instance. */
export function TooltipProvider({
  children,
  delayDuration = 200,
}: {
  children: React.ReactNode;
  delayDuration?: number;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>{children}</TooltipPrimitive.Provider>
  );
}

export function Tooltip({
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Root>) {
  return (
    <TooltipProvider>
      <TooltipPrimitive.Root {...props}>{children}</TooltipPrimitive.Root>
    </TooltipProvider>
  );
}

export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(function TooltipContent({ className, sideOffset = 6, ...props }, ref) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-md border border-border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
});