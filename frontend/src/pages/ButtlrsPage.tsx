import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bot, FilterX, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { ButtlrCard } from "@/components/buttlr/ButtlrCard";
import { useAuth } from "@/lib/auth";
import { useButtlrs, useTeams } from "@/lib/queries";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "disabled", label: "Disabled" },
];

export function ButtlrsPage() {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const teams = useTeams(organizationId);
  const [searchParams, setSearchParams] = useSearchParams();

  const searchParam = searchParams.get("q") ?? "";
  const statusParam = searchParams.get("status") ?? "all";
  const teamParam = searchParams.get("team") ?? "all";

  const [search, setSearch] = useState(searchParam);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search === searchParam) return;
      const next = new URLSearchParams(searchParams);
      if (search.trim()) next.set("q", search.trim());
      else next.delete("q");
      setSearchParams(next, { replace: true });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, searchParam, searchParams, setSearchParams]);

  const filters = useMemo(() => {
    const next: { team_id?: string; status?: string; q?: string } = {};
    if (teamParam !== "all") next.team_id = teamParam;
    if (statusParam !== "all") next.status = statusParam;
    if (searchParam) next.q = searchParam;
    return next;
  }, [searchParam, statusParam, teamParam]);

  const buttlrs = useButtlrs(organizationId, filters);

  const teamOptions = [
    { value: "all", label: "All teams" },
    ...(teams.data ?? []).map((team) => ({ value: team.id, label: `${team.emoji} ${team.name}` })),
  ];

  const hasFilters =
    searchParam.length > 0 || statusParam !== "all" || teamParam !== "all";

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (!value || value === "all") next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  };

  const clearFilters = () => {
    setSearch("");
    setSearchParams(new URLSearchParams(), { replace: true });
  };

  const list = buttlrs.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Buttlrs"
        description="Everyone working in this organization."
        actions={
          <Button asChild>
            <Link to="/buttlrs/new">
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              Create Buttlr
            </Link>
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search Buttlrs"
            placeholder="Search by name, role or objective"
            className="pl-9"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Select
          aria-label="Filter by status"
          value={statusParam}
          onValueChange={(value) => updateParam("status", value)}
          options={STATUS_OPTIONS}
          className="sm:w-44"
        />
        <Select
          aria-label="Filter by team"
          value={teamParam}
          onValueChange={(value) => updateParam("team", value)}
          options={teamOptions}
          className="sm:w-48"
        />
      </div>

      {buttlrs.isError ? (
        <ErrorState error={buttlrs.error} onRetry={() => void buttlrs.refetch()} />
      ) : buttlrs.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-36 w-full rounded-lg" />
          ))}
        </div>
      ) : list.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {list.map((buttlr) => (
            <ButtlrCard key={buttlr.id} buttlr={buttlr} href={`/buttlrs/${buttlr.id}`} />
          ))}
        </div>
      ) : hasFilters ? (
        <EmptyState
          icon={FilterX}
          title="No Buttlrs match these filters"
          description="Try a different search term, status or team."
          action={
            <Button type="button" variant="outline" onClick={clearFilters}>
              Clear filters
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={Bot}
          title="No Buttlrs yet"
          description="Describe a job in your own words. Buttlr writes the instructions, the schedule and the approval policy."
          action={
            <Button asChild>
              <Link to="/buttlrs/new">
                <Plus className="mr-2 h-4 w-4" aria-hidden />
                Create Buttlr
              </Link>
            </Button>
          }
        />
      )}
    </div>
  );
}