"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface QuotaBudget {
  total: number;
  days_in_month: number;
  day_of_month: number;
  days_remaining: number;
  linear_daily_budget: number;
  pace_48h_daily: number;
  projected_eom: number;
  projected_surplus: number;
}

interface QuotaCurrent {
  remaining: number;
  used: number;
  total: number;
  pct_used: number;
  health: string;
  updated_at: string;
}

interface DailyUsage {
  date: string;
  daily_requests: number;
  cumulative: number;
}

interface SourceCoverage {
  sport: string;
  total: number;
  live: number;
  odds_api: number;
  espn: number;
  statpal: number;
  espn_wp: number;
  model: number;
  mlb: number;
  kalshi: number;
  polymarket: number;
}

interface FuturesCoverage {
  sport: string;
  total_markets: number;
  odds_api: number;
  kalshi: number;
  polymarket: number;
  datagolf: number;
}

interface TaskMetric {
  task: string;
  health: string;
  successes_24h: number;
  failures_24h: number;
  last_success_at?: string;
  last_failure_at?: string;
  last_duration_ms?: string;
  consecutive_failures?: string;
  last_error?: string;
  last_result_summary?: Record<string, unknown>;
}

interface DatabaseHealth {
  active_events: number;
  live_events: number;
  snapshots_last_hour: number;
  winprob_last_hour: number;
  db_size_mb: number;
}

interface DashboardData {
  generated_at: string;
  quota: {
    current: QuotaCurrent;
    daily_usage: DailyUsage[];
    budget: QuotaBudget;
  };
  source_coverage: SourceCoverage[];
  futures_coverage: FuturesCoverage[];
  worker: {
    worker_status: string;
    heartbeat_age_seconds: number | null;
    overall_health: string;
    critical_tasks: string[];
    degraded_tasks: string[];
    tasks: TaskMetric[];
  };
  database: DatabaseHealth;
}

function healthColor(health: string): string {
  switch (health) {
    case "healthy": return "text-green-500";
    case "degraded": return "text-yellow-500";
    case "critical":
    case "worker_down":
    case "unhealthy": return "text-red-500";
    default: return "text-text-muted";
  }
}

function healthBg(health: string): string {
  switch (health) {
    case "healthy": return "bg-green-500/10 border-green-500/20";
    case "degraded": return "bg-yellow-500/10 border-yellow-500/20";
    case "critical":
    case "worker_down":
    case "unhealthy": return "bg-red-500/10 border-red-500/20";
    default: return "bg-surface-elevated border-surface-border";
  }
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
  return n.toLocaleString();
}

function timeAgo(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return mins + "m ago";
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + "h ago";
  return Math.floor(hrs / 24) + "d ago";
}

function CoverageCell({ val, total }: { val: number; total: number }) {
  const pctVal = total > 0 ? Math.round((val / total) * 100) : 0;
  if (val === 0) return <td className="text-right py-1.5 px-1"><span className="text-text-muted/30">-</span></td>;
  return (
    <td className="text-right py-1.5 px-1">
      <span className={pctVal >= 80 ? "text-green-400" : pctVal >= 40 ? "text-yellow-400" : "text-text-muted"}>
        {pctVal}%
      </span>
    </td>
  );
}

function StatCard({
  label,
  value,
  sub,
  health,
}: {
  label: string;
  value: string;
  sub?: string;
  health?: string;
}) {
  return (
    <div className={"rounded-xl border p-4 " + (health ? healthBg(health) : "bg-surface-card border-surface-border")}>
      <div className="text-micro text-text-muted uppercase tracking-wider">{label}</div>
      <div className={"text-2xl font-bold mt-1 " + (health ? healthColor(health) : "text-text-primary")}>
        {value}
      </div>
      {sub && <div className="text-xs text-text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

function QuotaChart({ data, budget }: { data: DailyUsage[]; budget: QuotaBudget }) {
  const chartData = useMemo(() => {
    if (!data.length) return [];
    const points = data.map((d) => {
      const dayNum = parseInt(d.date.split("-")[2]);
      const linearBudget = Math.round(budget.total / budget.days_in_month * dayNum);
      return {
        date: d.date.slice(5),
        used: d.cumulative,
        budget: linearBudget,
      };
    });
    points.push({
      date: String(budget.days_in_month).padStart(2, "0") + " (proj)",
      used: undefined as unknown as number,
      budget: budget.total,
    });
    return points;
  }, [data, budget]);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Odds API Quota</h3>
      <p className="text-xs text-text-muted mb-3">
        Cumulative usage vs. linear budget ({formatNum(budget.total)} monthly)
      </p>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#888" }} interval="preserveStartEnd" />
            <YAxis tickFormatter={formatNum} tick={{ fontSize: 10, fill: "#888" }} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#aaa" }}
              formatter={(val: number) => [formatNum(val), ""]}
            />
            <Line type="monotone" dataKey="budget" stroke="#555" strokeDasharray="6 3" dot={false} name="Linear Budget" />
            <Line type="monotone" dataKey="used" stroke="#22c55e" strokeWidth={2} dot={false} name="Actual Usage" />
            <ReferenceLine y={budget.total} stroke="#ef4444" strokeDasharray="2 2" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DailyBurnChart({ data }: { data: DailyUsage[] }) {
  const recent = data.slice(-14);
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Daily API Burn</h3>
      <p className="text-xs text-text-muted mb-3">Requests per day (last 14 days)</p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={recent} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fontSize: 10, fill: "#888" }} />
            <YAxis tickFormatter={formatNum} tick={{ fontSize: 10, fill: "#888" }} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              formatter={(val: number) => [formatNum(val), "Requests"]}
            />
            <Bar dataKey="daily_requests" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function SourceCoverageTable({ data }: { data: SourceCoverage[] }) {
  const sources = [
    { key: "odds_api", label: "Odds API" },
    { key: "espn", label: "ESPN ID" },
    { key: "espn_wp", label: "ESPN WP" },
    { key: "model", label: "BL Model" },
    { key: "mlb", label: "MLB" },
    { key: "statpal", label: "StatPal" },
    { key: "kalshi", label: "Kalshi" },
    { key: "polymarket", label: "Poly" },
  ] as const;

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Event Source Coverage</h3>
      <p className="text-xs text-text-muted mb-3">% of events (last 7 days) with data from each source</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="text-left py-2 px-1 text-text-muted font-medium">Sport</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Events</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Live</th>
              {sources.map((s) => (
                <th key={s.key} className="text-right py-2 px-1 text-text-muted font-medium">{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.sport} className="border-b border-surface-border/50 hover:bg-surface-elevated/30">
                <td className="py-1.5 px-1 font-mono text-text-secondary">{row.sport}</td>
                <td className="text-right py-1.5 px-1 text-text-primary font-medium">{row.total}</td>
                <td className="text-right py-1.5 px-1">
                  {row.live > 0 && <span className="text-green-400 font-medium">{row.live}</span>}
                </td>
                {sources.map((s) => (
                  <CoverageCell key={s.key} val={row[s.key]} total={row.total} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FuturesCoverageTable({ data }: { data: FuturesCoverage[] }) {
  const sources = [
    { key: "odds_api", label: "Odds API" },
    { key: "kalshi", label: "Kalshi" },
    { key: "polymarket", label: "Polymarket" },
    { key: "datagolf", label: "DataGolf" },
  ] as const;

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Futures Source Coverage</h3>
      <p className="text-xs text-text-muted mb-3">Open futures markets by source (non-game markets)</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="text-left py-2 px-1 text-text-muted font-medium">Sport</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Markets</th>
              {sources.map((s) => (
                <th key={s.key} className="text-right py-2 px-1 text-text-muted font-medium">{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.sport} className="border-b border-surface-border/50 hover:bg-surface-elevated/30">
                <td className="py-1.5 px-1 font-mono text-text-secondary">{row.sport}</td>
                <td className="text-right py-1.5 px-1 text-text-primary font-medium">{row.total_markets}</td>
                {sources.map((s) => {
                  const val = row[s.key];
                  return (
                    <td key={s.key} className="text-right py-1.5 px-1">
                      {val > 0 ? (
                        <span className="text-text-secondary">{val}</span>
                      ) : (
                        <span className="text-text-muted/30">-</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TasksTable({ tasks }: { tasks: TaskMetric[] }) {
  const [showAll, setShowAll] = useState(false);
  const sorted = useMemo(() => {
    const healthOrder: Record<string, number> = { critical: 0, degraded: 1, healthy: 2, no_data: 3 };
    return [...tasks].sort((a, b) => (healthOrder[a.health] ?? 9) - (healthOrder[b.health] ?? 9));
  }, [tasks]);
  const visible = showAll ? sorted : sorted.slice(0, 15);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Worker Tasks (24h)</h3>
      <p className="text-xs text-text-muted mb-3">
        {tasks.filter((t) => t.health === "healthy").length} healthy,{" "}
        {tasks.filter((t) => t.health === "degraded").length} degraded,{" "}
        {tasks.filter((t) => t.health === "critical").length} critical
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="text-left py-2 px-1 text-text-muted font-medium">Task</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Health</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">OK</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Fail</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Last</th>
              <th className="text-right py-2 px-1 text-text-muted font-medium">Duration</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((t) => (
              <tr key={t.task} className="border-b border-surface-border/50 hover:bg-surface-elevated/30">
                <td className="py-1.5 px-1 font-mono text-text-secondary">{t.task}</td>
                <td className={"text-right py-1.5 px-1 font-medium " + healthColor(t.health)}>
                  {t.health === "healthy" ? "OK" : t.health.toUpperCase()}
                </td>
                <td className="text-right py-1.5 px-1 text-green-400">{t.successes_24h}</td>
                <td className="text-right py-1.5 px-1">
                  {t.failures_24h > 0 ? (
                    <span className="text-red-400">{t.failures_24h}</span>
                  ) : (
                    <span className="text-text-muted/30">0</span>
                  )}
                </td>
                <td className="text-right py-1.5 px-1 text-text-muted">
                  {t.last_success_at ? timeAgo(t.last_success_at) : "-"}
                </td>
                <td className="text-right py-1.5 px-1 text-text-muted">
                  {t.last_duration_ms ? (parseInt(t.last_duration_ms) / 1000).toFixed(1) + "s" : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sorted.length > 15 && (
        <span
          onClick={() => setShowAll(!showAll)}
          className="text-xs text-accent-futures mt-2 cursor-pointer hover:underline inline-block"
        >
          {showAll ? "Show less" : "Show all " + sorted.length + " tasks"}
        </span>
      )}
    </div>
  );
}

export default function AdminDashboard() {
  usePageTracking({ pageType: "admin_dashboard", pageTitle: "Operations Dashboard" });
  useScrollDepth({ pageType: "admin_dashboard" });
  useEngagementTime({ pageType: "admin_dashboard" });

  const [secret, setSecret] = useState("");
  const [submittedSecret, setSubmittedSecret] = useState<string | null>(null);

  const { data, error, isLoading } = useSWR<DashboardData>(
    submittedSecret ? ["admin-dashboard", submittedSecret] : null,
    () =>
      fetch(API_URL + "/api/admin/dashboard?secret=" + encodeURIComponent(submittedSecret!))
        .then((r) => {
          if (!r.ok) throw new Error("API error: " + r.status);
          return r.json();
        }),
    { refreshInterval: 60000 }
  );

  if (!submittedSecret) {
    return (
      <div className="max-w-md mx-auto mt-20 space-y-4">
        <h1 className="text-lg font-bold text-text-primary">Operations Dashboard</h1>
        <p className="text-sm text-text-muted">Enter admin secret to view backend metrics.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSubmittedSecret(secret);
          }}
          className="flex gap-2"
        >
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Admin secret"
            className="flex-1 px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary"
          />
          <span
            onClick={() => setSubmittedSecret(secret)}
            className="px-4 py-2 rounded-lg bg-text-primary text-surface-deep text-sm font-medium cursor-pointer select-none"
          >
            Load
          </span>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">Operations Dashboard</h1>
        {data && (
          <span className="text-micro text-text-muted">
            Updated {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg">{error.message}</div>
      )}
      {isLoading && <div className="text-sm text-text-muted animate-pulse">Loading dashboard...</div>}

      {data && (
        <>
          {/* Top stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard
              label="Odds API Used"
              value={data.quota.current.pct_used + "%"}
              sub={formatNum(data.quota.current.used) + " / " + formatNum(data.quota.current.total)}
              health={data.quota.current.health}
            />
            <StatCard
              label="EOM Projection"
              value={formatNum(data.quota.budget.projected_eom)}
              sub={
                data.quota.budget.projected_surplus >= 0
                  ? formatNum(data.quota.budget.projected_surplus) + " under budget"
                  : formatNum(Math.abs(data.quota.budget.projected_surplus)) + " OVER budget"
              }
              health={data.quota.budget.projected_surplus >= 0 ? "healthy" : "critical"}
            />
            <StatCard
              label="Worker"
              value={data.worker.overall_health.replace("_", " ")}
              sub={
                data.worker.heartbeat_age_seconds != null
                  ? "Heartbeat " + data.worker.heartbeat_age_seconds + "s ago"
                  : "No heartbeat"
              }
              health={data.worker.overall_health}
            />
            <StatCard
              label="Database"
              value={data.database.db_size_mb + " MB"}
              sub={data.database.live_events + " live, " + data.database.active_events + " active"}
            />
          </div>

          {/* Quota charts */}
          <div className="grid md:grid-cols-2 gap-4">
            <QuotaChart data={data.quota.daily_usage} budget={data.quota.budget} />
            <DailyBurnChart data={data.quota.daily_usage} />
          </div>

          {/* Source coverage: events + futures */}
          <SourceCoverageTable data={data.source_coverage} />
          <FuturesCoverageTable data={data.futures_coverage} />

          {/* Worker tasks */}
          <TasksTable tasks={data.worker.tasks} />

          {/* Bottom stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Snapshots/hr" value={data.database.snapshots_last_hour.toLocaleString()} />
            <StatCard label="WinProb/hr" value={data.database.winprob_last_hour.toLocaleString()} />
            <StatCard label="48h Pace" value={formatNum(data.quota.budget.pace_48h_daily) + "/day"} />
            <StatCard label="Daily Budget" value={formatNum(data.quota.budget.linear_daily_budget) + "/day"} />
          </div>
        </>
      )}
    </div>
  );
}
