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

/**
 * Label, control, then the hint underneath. When `htmlFor` is given, the hint
 * and error ids are attached to the control itself so a screen reader announces
 * them with the field rather than as loose text.
 */
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
  const hintId = htmlFor ? `${htmlFor}-hint` : undefined;
  const errorId = htmlFor ? `${htmlFor}-error` : undefined;
  const describedBy = [error ? errorId : undefined, hint ? hintId : undefined]
    .filter(Boolean)
    .join(" ")
    .trim();

  const control =
    React.isValidElement(children) && describedBy
      ? React.cloneElement(children as React.ReactElement<{ "aria-describedby"?: string }>, {
          "aria-describedby": describedBy,
        })
      : children;

  return (
    <div className={cn("space-y-2", className)} {...props}>
      <Label htmlFor={htmlFor}>
        {label}
        {required ? (
          <>
            <span className="ml-0.5 text-destructive" aria-hidden="true">
              *
            </span>
            <span className="sr-only"> (required)</span>
          </>
        ) : null}
      </Label>
      {control}
      {error ? (
        <p id={errorId} className="text-xs leading-4 text-destructive">
          {error}
        </p>
      ) : null}
      {hint ? (
        <p id={hintId} className="text-xs leading-4 text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}