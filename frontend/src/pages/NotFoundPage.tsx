import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <span
        aria-hidden="true"
        className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <Compass className="size-6" />
      </span>
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">404</p>
        <h1 className="text-xl font-semibold text-foreground sm:text-2xl">
          This page doesn't exist
        </h1>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          The address you followed doesn't match anything in Buttlr. It may have been renamed, or the link
          may have a typo.
        </p>
      </div>
      <Button asChild>
        <Link to="/">Back to Overview</Link>
      </Button>
    </div>
  );
}