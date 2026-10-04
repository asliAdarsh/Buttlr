import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Bot,
  LayoutDashboard,
  LogOut,
  MoreHorizontal,
  Plug,
  Settings,
  ShieldCheck,
  User,
  Users,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useApprovalStats } from "@/lib/queries";
import { isActive, type NavItem } from "./nav";

const PRIMARY: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/buttlrs", label: "Buttlrs", icon: Bot },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/activity", label: "Activity", icon: Activity },
];

const MORE: NavItem[] = [
  { to: "/teams", label: "Teams", icon: Users },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

/**
 * Bottom navigation. The active item gets a rule above the icon as well as a
 * colour change, so the current page is never signalled by colour alone.
 */
function Slot({
  item,
  active,
  badge,
}: {
  item: NavItem;
  active: boolean;
  badge?: number;
}) {
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex min-h-14 flex-1 flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-xs font-medium transition-colors",
        active ? "text-foreground" : "text-muted-foreground",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "absolute inset-x-3 top-0 h-0.5 rounded-full bg-primary transition-opacity",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <span className="relative flex size-6 items-center justify-center">
        <item.icon className={cn("size-5", active && "text-primary")} />
        {badge ? (
          <span className="absolute -right-2 -top-1 inline-flex min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold tabular-nums text-primary-foreground">
            {badge}
          </span>
        ) : null}
        <span className="sr-only">{badge ? `${badge} approvals waiting` : ""}</span>
      </span>
      <span className="truncate leading-tight">{item.label}</span>
    </Link>
  );
}

export function MobileNav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { logout, activeOrganizationId } = useAuth();
  const { data: stats } = useApprovalStats(activeOrganizationId);
  const [open, setOpen] = useState(false);
  const pending = stats?.pending ?? 0;
  const moreActive = MORE.some((item) => isActive(item, pathname));

  const closeThen = (run: () => void) => () => {
    setOpen(false);
    run();
  };

  const sheetLink = (item: NavItem): ReactNode => (
    <li key={item.to}>
      <Link
        to={item.to}
        onClick={() => setOpen(false)}
        className={cn(
          "flex min-h-11 items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors hover:bg-muted",
          isActive(item, pathname) && "bg-muted font-medium text-foreground",
        )}
      >
        <item.icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        {item.label}
      </Link>
    </li>
  );

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background lg:hidden"
    >
      <ul className="mx-auto flex max-w-lg items-stretch gap-1 px-2 pb-[env(safe-area-inset-bottom)] pt-1">
        {PRIMARY.map((item) => (
          <li key={item.to} className="flex flex-1">
            <Slot
              item={item}
              active={isActive(item, pathname)}
              badge={item.to === "/approvals" ? pending : undefined}
            />
          </li>
        ))}
        <li className="flex flex-1">
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <button
                type="button"
                aria-label="More sections"
                aria-expanded={open}
                className={cn(
                  "relative flex min-h-14 w-full flex-col items-center justify-center gap-1 rounded-md px-1 py-2 text-xs font-medium transition-colors",
                  moreActive ? "text-foreground" : "text-muted-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute inset-x-3 top-0 h-0.5 rounded-full bg-primary transition-opacity",
                    moreActive ? "opacity-100" : "opacity-0",
                  )}
                />
                <MoreHorizontal className={cn("size-5", moreActive && "text-primary")} />
                <span className="leading-tight">More</span>
              </button>
            </DialogTrigger>
            <DialogContent className="max-sm:pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
              <DialogHeader>
                <DialogTitle>More</DialogTitle>
                <DialogDescription>Everything else in this workspace.</DialogDescription>
              </DialogHeader>
              <ul className="mt-4 space-y-1">
                {MORE.map(sheetLink)}
                <li>
                  <button
                    type="button"
                    onClick={closeThen(() => navigate("/settings?tab=account"))}
                    className="flex min-h-11 w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted"
                  >
                    <User aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                    Profile
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={closeThen(logout)}
                    className="flex min-h-11 w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-destructive transition-colors hover:bg-muted"
                  >
                    <LogOut aria-hidden="true" className="size-4 shrink-0" />
                    Sign out
                  </button>
                </li>
              </ul>
            </DialogContent>
          </Dialog>
        </li>
      </ul>
    </nav>
  );
}