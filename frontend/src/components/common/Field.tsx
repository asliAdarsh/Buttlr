import * as React from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface FieldProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  required?: boolean;
  children: React.ReactNode;
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  required,
  children,
  className,
  ...props
}: FieldProps) {
  const describedBy = [htmlFor ? `${htmlFor}-hint` : undefined, htmlFor ? `${htmlFor}-error` : undefined]
    .filter(Boolean)
    .join(" ")
    .trim();

  return (
    <div className={cn("space-y-1.5", className)} {...props}>
      <Label htmlFor={htmlFor}>
        {label}
        {required ? (
          <span className="ml-0.5 text-destructive" aria-hidden="true">
            *
          </span>
        ) : null}
      </Label>
      {hint ? (
        <p id={htmlFor ? `${htmlFor}-hint` : undefined} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
      <div aria-describedby={describedBy || undefined}>{children}</div>
      {error ? (
        <p id={htmlFor ? `${htmlFor}-error` : undefined} className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}