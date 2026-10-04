import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";

import { cn } from "@/lib/utils";

export interface SwitchProps
  extends Omit<React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>, "onChange"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
}

export const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  SwitchProps
>(function Switch({ className, checked, onCheckedChange, disabled, id, ...props }, ref) {
  return (
    <SwitchPrimitive.Root
      ref={ref}
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      className={cn(
        "peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          "pointer-events-none block size-5 rounded-full bg-background shadow transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0",
        )}
      />
    </SwitchPrimitive.Root>
  );
});