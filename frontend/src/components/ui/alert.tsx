import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Every alert carries an icon *and* a text label, so the tone is never the only
 * thing telling the user what happened.
 */
const alertVariants = cva("flex gap-3 rounded-lg border p-4 text-sm", {
  variants: {
    tone: {
      info: "border-border bg-muted/60 text-foreground",
      success: "border-success/40 bg-success/10 text-foreground [&_svg]:text-success",
      warning: "border-warning/40 bg-warning/10 text-foreground [&_svg]:text-warning",
      destructive:
        "border-destructive/40 bg-destructive/10 text-foreground [&_svg]:text-destructive",
    },
  },
  defaultVariants: { tone: "info" },
});

const TONE_ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  destructive: XCircle,
} as const;

export interface AlertProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title">,
    VariantProps<typeof alertVariants> {
  title?: React.ReactNode;
  icon?: React.ReactNode;
}

export function Alert({ className, tone, title, icon, children, ...props }: AlertProps) {
  const resolved = tone ?? "info";
  const IconComponent = TONE_ICONS[resolved];

  return (
    <div
      // Only a problem interrupts a screen reader. Informational and success notes
      // are announced politely, so a page full of them is not read out on mount.
      role={resolved === "warning" || resolved === "destructive" ? "alert" : "status"}
      className={cn(alertVariants({ tone: resolved }), className)}
      {...props}
    >
      <span className="mt-0.5 shrink-0" aria-hidden="true">
        {icon ?? <IconComponent className="size-4" />}
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        {title ? <p className="font-medium leading-5">{title}</p> : null}
        {children ? <div className="text-sm leading-5 text-muted-foreground">{children}</div> : null}
      </div>
    </div>
  );
}