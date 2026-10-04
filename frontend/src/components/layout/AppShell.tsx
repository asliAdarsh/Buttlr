import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { MobileNav } from "./MobileNav";

/**
 * One column on a phone, a fixed rail plus content from `lg`. The main column
 * reserves room for the bottom navigation so nothing ends up underneath it.
 */
export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="lg:flex">
        <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">
          <Sidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
          <Topbar />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 pt-6 pb-[calc(5rem+env(safe-area-inset-bottom))] sm:px-6 lg:px-8 lg:pb-12">
            <Outlet />
          </main>
        </div>
      </div>

      <MobileNav />
    </div>
  );
}