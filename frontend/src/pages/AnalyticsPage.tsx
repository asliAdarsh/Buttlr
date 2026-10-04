import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity as ActivityIcon,
  BadgeCheck,
  Coins,
  Clock,
  Cpu,
  Gauge,
  Timer,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatCard } from "@/components/common/StatCard";
import { useAuth } from "@/lib/auth";
import { useAnalytics } from "@/lib/queries";
import { formatCost, formatDuration, formatTokens, providerLabel, toolLabel } from "@/lib/format";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

const CHART_COLORS = {
  primary: "hsl(var(--primary))",
  success: "hsl(var(--success))",
  destructive: "hsl(var(--destructive))",
  muted: "hsl(var(--muted-foreground))",
  grid: "hsl(var(--border))",
  foreground: "hsl(var(--foreground))",
};

function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "0 min";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = minutes / 60;
  return hours < 10 ? `${hours.toFixed(1)} h` : `${Math.round(hours)} h`;
}

function percent(value: number): string {
  if (!Number.isFinite(value)) return "0%";
  const scaled = value <= 1 ? value * 100 : value;
  return `${Math.round(scaled)}%`;
}

export function AnalyticsPage() {
  const { activeOrganization } = useAuth();
  const organizationId = activeOrganization?.id ?? null;
  const [period, setPeriod] = useState("30");
  const analytics = useAnalytics(organizationId, Number(period));
  const data = analytics.data;

  const toolData = useMemo(
    () =>
      (data?.by_tool ?? []).map((row) => ({
        ...row,
        failureLabel: row.failures > 0 ? `${row.failures} failed` : "",
      })),
    [data],
  );

  const hasRuns = (data?.executions_total ?? 0) > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description={`How your Buttlrs have performed${activeOrganization ? ` in ${activeOrganization.name}` : ""}.`}
        actions={
          <div className="flex items-center gap-2">
            <Label htmlFor="analytics-period" className="text-sm text-muted-foreground">
              Period
            </Label>
            <Select
              id="analytics-period"
              value={period}
              onValueChange={setPeriod}
              options={PERIODS}
              className="w-44"
            />
          </div>
        }
      />

      {analytics.isError ? (
        <ErrorState error={analytics.error} onRetry={() => void analytics.refetch()} />
      ) : !analytics.isLoading && !hasRuns ? (
        <EmptyState
          icon={ActivityIcon}
          title="Run a Buttlr to see analytics"
          description="Once a Buttlr has finished a run, this page shows how long runs take, what they cost, which tools they reach for and which models answer."
          action={
            <Button asChild>
              <Link to="/buttlrs">Go to Buttlrs</Link>
            </Button>
          }
        />
      ) : (
        <>
          <section aria-label="Key numbers" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatCard
              label="Runs"
              value={data?.executions_total ?? 0}
              hint={`${data?.executions_completed ?? 0} completed · ${data?.executions_failed ?? 0} failed`}
              icon={ActivityIcon}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Success rate"
              value={percent(data?.success_rate ?? 0)}
              tone={(data?.success_rate ?? 0) >= 0.9 ? "success" : "warning"}
              hint="Completed as a share of all runs"
              icon={BadgeCheck}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Average duration"
              value={formatDuration(data?.avg_duration_ms ?? 0)}
              hint="Mean wall-clock time per run"
              icon={Timer}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Tokens"
              value={formatTokens(data?.total_tokens ?? 0)}
              hint="Input and output across every run"
              icon={Cpu}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Estimated cost"
              value={formatCost(data?.estimated_cost_usd ?? 0)}
              hint="Based on the configured per-token rates"
              icon={Coins}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Approval time"
              value={formatMinutes(data?.avg_approval_minutes ?? 0)}
              hint="Mean wait before a request was decided"
              icon={Clock}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Approvals"
              value={(data?.approvals_approved ?? 0) + (data?.approvals_rejected ?? 0)}
              hint={`${data?.approvals_approved ?? 0} approved · ${data?.approvals_rejected ?? 0} rejected · ${data?.approvals_pending ?? 0} waiting`}
              icon={Gauge}
              loading={analytics.isLoading}
            />
            <StatCard
              label="Time saved"
              value={formatMinutes(data?.estimated_minutes_saved ?? 0)}
              hint="Manual effort these runs replaced"
              icon={TrendingUp}
              tone="success"
              loading={analytics.isLoading}
            />
          </section>

          <SectionCard
            title="Runs over time"
            description={`Completed and failed runs per day over the ${PERIODS.find((entry) => entry.value === period)?.label.toLowerCase()}.`}
          >
            {(data?.timeline ?? []).length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No runs in this period. Widen the period or start a Buttlr.
              </p>
            ) : (
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data?.timeline} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <defs>
                      <linearGradient id="completedFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_COLORS.success} stopOpacity={0.45} />
                        <stop offset="95%" stopColor={CHART_COLORS.success} stopOpacity={0.05} />
                      </linearGradient>
                      <linearGradient id="failedFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_COLORS.destructive} stopOpacity={0.45} />
                        <stop offset="95%" stopColor={CHART_COLORS.destructive} stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="label"
                      stroke={CHART_COLORS.muted}
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      allowDecimals={false}
                      stroke={CHART_COLORS.muted}
                      fontSize={11}
                      tickLine={false}
                      axisLine={false}
                      width={40}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--popover))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "0.5rem",
                        color: "hsl(var(--popover-foreground))",
                        fontSize: "0.75rem",
                      }}
                      labelStyle={{ color: CHART_COLORS.foreground }}
                    />
                    <Area
                      type="monotone"
                      dataKey="completed"
                      name="Completed"
                      stroke={CHART_COLORS.success}
                      strokeWidth={2}
                      fill="url(#completedFill)"
                    />
                    <Area
                      type="monotone"
                      dataKey="failed"
                      name="Failed"
                      stroke={CHART_COLORS.destructive}
                      strokeWidth={2}
                      fill="url(#failedFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </SectionCard>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard
              title="Tool usage"
              description="How often each tool was called, and how often it failed."
            >
              {(data?.by_tool ?? []).length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No tools were called in this period.
                </p>
              ) : (
                <div className="h-[240px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={toolData}
                      layout="vertical"
                      margin={{ top: 4, right: 28, left: 8, bottom: 4 }}
                    >
                      <CartesianGrid stroke={CHART_COLORS.grid} strokeDasharray="3 3" horizontal={false} />
                      <XAxis
                        type="number"
                        allowDecimals={false}
                        stroke={CHART_COLORS.muted}
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="tool"
                        stroke={CHART_COLORS.muted}
                        fontSize={11}
                        tickLine={false}
                        axisLine={false}
                        width={112}
                        tickFormatter={(value: string) => toolLabel(value)}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: "0.5rem",
                          color: "hsl(var(--popover-foreground))",
                          fontSize: "0.75rem",
                        }}
                        labelStyle={{ color: CHART_COLORS.foreground }}
                        formatter={(value, name): [string, string] => [
                          String(value),
                          name === "failures" ? "Failed calls" : "Calls",
                        ]}
                      />
                      <Bar dataKey="calls" fill={CHART_COLORS.primary} radius={[0, 4, 4, 0]} barSize={14} />
                      <Bar
                        dataKey="failures"
                        fill={CHART_COLORS.destructive}
                        radius={[0, 4, 4, 0]}
                        barSize={14}
                      >
                        <LabelList
                          dataKey="failureLabel"
                          position="right"
                          fontSize={11}
                          fill={CHART_COLORS.muted}
                        />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {toolData.length > 0 ? (
                <>
                  <p className="mt-3 text-xs text-muted-foreground">
                    Each tool has two bars: calls in the accent colour, failed calls in red with the count
                    printed beside them.
                  </p>
                  <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
                    {toolData.map((row) => (
                      <li key={row.tool} className="flex items-center justify-between gap-3 text-xs">
                        <span className="min-w-0 truncate">{toolLabel(row.tool)}</span>
                        <span className="shrink-0 tabular-nums text-muted-foreground">
                          {row.calls} calls
                          {row.failures > 0 ? (
                            <span className="text-destructive"> · {row.failures} failed</span>
                          ) : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </SectionCard>

            <SectionCard
              title="Models"
              description="Which models answered, and what they cost."
            >
              {(data?.by_model ?? []).length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No model usage was recorded in this period.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Model</TableHead>
                        <TableHead className="text-right">Calls</TableHead>
                        <TableHead className="text-right">Tokens</TableHead>
                        <TableHead className="text-right">Cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(data?.by_model ?? []).map((row) => (
                        <TableRow key={`${row.provider}-${row.model}`}>
                          <TableCell>
                            <span className="block font-medium">{row.model}</span>
                            <span className="block text-xs text-muted-foreground">
                              {providerLabel(row.provider)}
                            </span>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{row.calls}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatTokens(row.input_tokens + row.output_tokens)}
                          </TableCell>
                          <TableCell className="text-right tabular-nums">
                            {formatCost(row.estimated_cost_usd)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}