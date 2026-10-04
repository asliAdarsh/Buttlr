import { useNavigate } from "react-router-dom";
import { Building2, Check, ChevronsUpDown, Plus } from "lucide-react";
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
        <button
          type="button"
          className="flex min-h-11 max-w-[52vw] items-center justify-start gap-2 rounded-md px-2 text-sm transition-colors hover:bg-muted lg:h-9 lg:max-w-[220px]"
          aria-label={`Switch organization. Currently ${activeOrganization?.name ?? "none selected"}`}
        >
          <span aria-hidden="true" className="shrink-0 leading-none">
            {activeOrganization?.logo_emoji ?? "🏢"}
          </span>
          <span className="truncate font-medium text-foreground">
            {activeOrganization?.name ?? "Select organization"}
          </span>
          <ChevronsUpDown aria-hidden="true" className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Organizations</DropdownMenuLabel>
        {organizations.length === 0 ? (
          <p className="px-2 py-1.5 text-xs text-muted-foreground">
            <Building2 aria-hidden="true" className="mr-1 inline size-3" />
            You are not a member of any organization yet.
          </p>
        ) : (
          organizations.map((org) => (
            <DropdownMenuItem
              key={org.id}
              onSelect={() => setActiveOrganization(org.id)}
              className={cn(org.id === activeOrganizationId && "bg-muted")}
            >
              <span aria-hidden="true">{org.logo_emoji}</span>
              <span className="truncate">{org.name}</span>
              {org.id === activeOrganizationId ? (
                <>
                  <Check aria-hidden="true" className="ml-auto size-4" />
                  <span className="sr-only">(current)</span>
                </>
              ) : null}
            </DropdownMenuItem>
          ))
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/onboarding")}>
          <Plus aria-hidden="true" className="size-4" />
          Create organization
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}