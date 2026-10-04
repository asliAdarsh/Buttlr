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
        "relative flex flex-1 flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[11px] font-medium transition-colors",
        active ? "text-accent-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "flex size-8 items-center justify-center rounded-md",
          active && "bg-accent",
        )}
      >
        <item.icon className="size-4" />
      </span>
      <span className="truncate leading-tight">{item.label}</span>
      {badge ? (
        <span className="absolute right-1/4 top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
          {badge}
          <span className="sr-only"> approvals waiting</span>
        </span>
      ) : null}
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
          "flex items-center gap-3 rounded-md px-3 py-3 text-sm transition-colors hover:bg-muted",
          isActive(item, pathname) && "bg-accent text-accent-foreground",
        )}
      >
        <item.icon aria-hidden="true" className="size-4 shrink-0" />
        {item.label}
      </Link>
    </li>
  );

  return (
    <nav
      aria-label="Primary"
      className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 backdrop-blur lg:hidden"
    >
      <ul className="mx-auto flex max-w-lg items-stretch gap-0.5 px-2 py-1.5">
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
                className={cn(
                  "flex w-full flex-col items-center gap-0.5 rounded-md px-1 py-1.5 text-[11px] font-medium transition-colors",
                  moreActive ? "text-accent-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-8 items-center justify-center rounded-md",
                    moreActive && "bg-accent",
                  )}
                >
                  <MoreHorizontal className="size-4" />
                </span>
                <span className="leading-tight">More</span>
              </button>
            </DialogTrigger>
            <DialogContent className="bottom-0 left-0 right-0 top-auto max-h-[85vh] translate-x-0 translate-y-0 rounded-b-none rounded-t-xl border-b-0 sm:left-auto sm:right-4 sm:top-auto sm:h-auto sm:max-w-sm sm:translate-y-0 sm:rounded-lg sm:border-b">
              <DialogHeader>
                <DialogTitle>More</DialogTitle>
                <DialogDescription>Everything else in this workspace.</DialogDescription>
              </DialogHeader>
              <ul className="space-y-0.5">
                {MORE.map(sheetLink)}
                <li>
                  <button
                    type="button"
                    onClick={closeThen(() => navigate("/settings?tab=profile"))}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left text-sm transition-colors hover:bg-muted"
                  >
                    <User aria-hidden="true" className="size-4 shrink-0" />
                    Profile
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={closeThen(logout)}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-3 text-left text-sm text-destructive transition-colors hover:bg-muted"
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
