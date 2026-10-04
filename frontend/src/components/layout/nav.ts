import {
  Activity,
  BarChart3,
  Bot,
  LayoutDashboard,
  Plug,
  Settings,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Matches nested routes too, e.g. `/buttlrs/new` keeps "Buttlrs" active. */
  match?: (pathname: string) => boolean;
  end?: boolean;
}

/** Sidebar order is frozen: primary navigation, then organization settings. */
export const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/buttlrs", label: "Buttlrs", icon: Bot },
  { to: "/teams", label: "Teams", icon: Users },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];

export const ORGANIZATION_NAV: NavItem[] = [
  { to: "/settings", label: "Settings", icon: Settings },
];

export const ALL_NAV: NavItem[] = [...PRIMARY_NAV, ...ORGANIZATION_NAV];

export function isActive(item: NavItem, pathname: string): boolean {
  if (item.end) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

export function sectionTitle(pathname: string): string {
  const match = ALL_NAV.find((item) => isActive(item, pathname));
  if (match) return match.label;
  if (pathname.startsWith("/buttlrs")) return "Buttlrs";
  return "Buttlr";
}
