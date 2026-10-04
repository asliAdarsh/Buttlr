import * as React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
  hint?: string;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange"> {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  "aria-label"?: string;
}

/**
 * Native `<select>` so it works everywhere (including mobile pickers), with a
 * chevron painted over the right edge. Pair it with `<Label htmlFor={id}>`.
 */
export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { value, onValueChange, options, placeholder, disabled, className, id, ...props },
  ref,
) {
  return (
    <div className={cn("relative", className)}>
      <select
        ref={ref}
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onValueChange(event.target.value)}
        className={cn(
          "h-10 w-full appearance-none rounded-md border border-input bg-background px-3 pr-9 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",
        )}
        {...props}
      >
        {placeholder ? (
          <option value="" disabled>
            {placeholder}
          </option>
        ) : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.hint ? `${option.label} — ${option.hint}` : option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
});

export const NativeSelect = Select;