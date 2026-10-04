import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { MobileNav } from "./MobileNav";

export function AppShell() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="lg:flex">
        <div className="fixed inset-y-0 left-0 z-40 hidden lg:block">
          <Sidebar />
        </div>

        <div className="flex min-w-0 flex-1 flex-col lg:pl-[264px]">
          <Topbar />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-20 pt-6 sm:px-6 lg:px-8 lg:pb-10">
            <Outlet />
          </main>
        </div>
      </div>

      <MobileNav />
    </div>
  );
}
