import * as React from "react";
import * as SeparatorPrimitive from "@radix-ui/react-separator";

import { cn } from "@/lib/utils";

export interface SeparatorProps
  extends React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root> {}

export const Separator = React.forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  SeparatorProps
>(function Separator({ className, orientation = "horizontal", decorative = true, ...props }, ref) {
  return (
    <SeparatorPrimitive.Root
      ref={ref}
      orientation={orientation}
      decorative={decorative}
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className,
      )}
      {...props}
    />
  );
});