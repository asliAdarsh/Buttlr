import { Avatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import type { Buttlr } from "@/lib/types";

export function ButtlrAvatar({
  buttlr,
  size = "md",
}: {
  buttlr: Pick<Buttlr, "name" | "avatar">;
  size?: "xs" | "sm" | "md" | "lg";
}) {
  return (
    <span className={cn("shrink-0", size === "lg" && "ring-1 ring-border")}>
      <Avatar name={buttlr.name} emoji={buttlr.avatar} size={size} />
    </span>
  );
}
