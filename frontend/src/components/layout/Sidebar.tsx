import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { useApprovalStats } from "@/lib/queries";
import { PRIMARY_NAV, ORGANIZATION_NAV, isActive } from "./nav";
import { UserMenu } from "./UserMenu";

export function Sidebar() {
  const { activeOrganization } = useAuth();
  const { pathname } = useLocation();
  const { data: stats } = useApprovalStats(activeOrganization?.id ?? null);
  const pending = stats?.pending ?? 0;

  return (
    <aside className="hidden lg:flex h-screen w-[264px] shrink-0 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <span aria-hidden="true" className="text-lg">
          🫙
        </span>
        <span className="truncate text-sm font-semibold">
          {activeOrganization?.name ?? "Buttlr"}
        </span>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto p-3">
        <ul className="space-y-0.5">
          {PRIMARY_NAV.map((item) => {
            const active = isActive(item, pathname);
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <item.icon aria-hidden="true" className="size-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                  {item.to === "/approvals" && pending > 0 ? (
                    <span className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-medium text-primary-foreground">
                      {pending}
                      <span className="sr-only"> approvals waiting</span>
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>

        <p className="px-3 pb-1 pt-5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Organization
        </p>
        <ul className="space-y-0.5">
          {ORGANIZATION_NAV.map((item) => {
            const active = isActive(item, pathname);
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-accent text-accent-foreground font-medium"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <item.icon aria-hidden="true" className="size-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-3">
        <UserMenu />
      </div>
    </aside>
  );
}
