import { useLocation } from "react-router-dom";
import { OrgSwitcher } from "./OrgSwitcher";
import { NotificationBell } from "./NotificationBell";
import { UserMenu } from "./UserMenu";
import { sectionTitle } from "./nav";

/**
 * A quiet band above the content. It names the section for orientation but is
 * deliberately not a heading — the page owns its `<h1>` — and it carries no
 * fill beyond a hairline border.
 */
export function Topbar() {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
        <span aria-hidden="true" className="text-lg leading-none lg:hidden">
          🫙
        </span>
        <p className="truncate text-sm font-medium text-muted-foreground">{sectionTitle(pathname)}</p>
        <div className="ml-auto flex items-center gap-1">
          <OrgSwitcher />
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}