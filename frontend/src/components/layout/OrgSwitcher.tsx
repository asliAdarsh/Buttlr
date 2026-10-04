import { useNavigate } from "react-router-dom";
import { Building2, Check, ChevronsUpDown, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

export function OrgSwitcher() {
  const { organizations, activeOrganization, activeOrganizationId, setActiveOrganization } =
    useAuth();
  const navigate = useNavigate();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 max-w-[52vw] justify-start gap-2 px-2 lg:max-w-[220px]"
          aria-label="Switch organization"
        >
          <span aria-hidden="true" className="shrink-0">
            {activeOrganization?.logo_emoji ?? "🏢"}
          </span>
          <span className="truncate text-sm font-medium">
            {activeOrganization?.name ?? "Select organization"}
          </span>
          <ChevronsUpDown aria-hidden="true" className="ml-auto size-3.5 shrink-0 opacity-60" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Organizations</DropdownMenuLabel>
        {organizations.map((org) => (
          <DropdownMenuItem
            key={org.id}
            onSelect={() => setActiveOrganization(org.id)}
            className={cn(org.id === activeOrganizationId && "bg-accent text-accent-foreground")}
          >
            <span aria-hidden="true">{org.logo_emoji}</span>
            <span className="truncate">{org.name}</span>
            {org.id === activeOrganizationId ? (
              <Check aria-hidden="true" className="ml-auto size-4" />
            ) : null}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/onboarding")}>
          <Plus aria-hidden="true" className="size-4" />
          Create organization
        </DropdownMenuItem>
        {organizations.length === 0 ? (
          <p className="px-2 py-1.5 text-xs text-muted-foreground">
            <Building2 aria-hidden="true" className="mr-1 inline size-3" />
            You are not a member of any organization yet.
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
