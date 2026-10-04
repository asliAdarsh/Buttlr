import { useLocation } from "react-router-dom";
import { OrgSwitcher } from "./OrgSwitcher";
import { NotificationBell } from "./NotificationBell";
import { UserMenu } from "./UserMenu";
import { sectionTitle } from "./nav";

export function Topbar() {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
        <span aria-hidden="true" className="text-lg lg:hidden">
          🫙
        </span>
        <h1 className="truncate text-sm font-semibold lg:text-base">{sectionTitle(pathname)}</h1>
        <div className="ml-auto flex items-center gap-1">
          <OrgSwitcher />
          <NotificationBell />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
