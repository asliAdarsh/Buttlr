import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useApprovalStats } from "@/lib/queries";
import { PRIMARY_NAV, ORGANIZATION_NAV, isActive, type NavItem } from "./nav";
import { UserMenu } from "./UserMenu";

/**
 * Desktop rail. Groups are labelled, the active item is a quiet fill plus a
 * weight change, and every row is a comfortable hit area. Nothing here
 * competes with the page: no shadows, no fills beyond the active row.
 */
export function Sidebar() {
  const { activeOrganization } = useAuth();
  const { pathname } = useLocation();
  const { data: stats } = useApprovalStats(activeOrganization?.id ?? null);
  const pending = stats?.pending ?? 0;

  const renderItem = (item: NavItem) => {
    const active = isActive(item, pathname);
    return (
      <li key={item.to}>
        <Link
          to={item.to}
          aria-current={active ? "page" : undefined}
          className={cn(
            "flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
            active
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          )}
        >
          <item.icon
            aria-hidden="true"
            className={cn("size-4 shrink-0", active ? "text-foreground" : "text-muted-foreground/80")}
          />
          <span className="truncate">{item.label}</span>
          {item.to === "/approvals" && pending > 0 ? (
            <span className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-medium tabular-nums text-primary-foreground">
              {pending}
              <span className="sr-only"> approvals waiting</span>
            </span>
          ) : null}
        </Link>
      </li>
    );
  };

  return (
    <aside className="hidden h-screen w-64 shrink-0 flex-col border-r border-border bg-card lg:flex">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
        <span aria-hidden="true" className="text-lg leading-none">
          🫙
        </span>
        <span className="truncate text-sm font-semibold">
          {activeOrganization?.name ?? "Buttlr"}
        </span>
      </div>

      <nav aria-label="Primary" className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">{PRIMARY_NAV.map(renderItem)}</ul>

        <p className="px-3 pb-1 pt-6 text-xs font-medium uppercase tracking-wide text-muted-foreground/80">
          Organization
        </p>
        <ul className="space-y-1">{ORGANIZATION_NAV.map(renderItem)}</ul>
      </nav>

      <div className="border-t border-border p-3">
        <UserMenu />
      </div>
    </aside>
  );
}