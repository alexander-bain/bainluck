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
  Legend,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types ---

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

interface DailyByTask {
  date: string;
  poll_odds?: number;
  discover_events?: number;
  poll_futures?: number;
  [key: string]: string | number | undefined;
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
  snapshots_24h: number;
}

interface CoverageTrendEntry {
  date: string;
  sport: string;
  total: number;
  odds_api_pct: number;
  espn_pct: number;
  statpal_pct: number;
  espn_wp_pct?: number;
  model_pct?: number;
  kalshi_pct?: number;
  polymarket_pct?: number;
  is_future: boolean;
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
  last_duration_ms?: string;
  consecutive_failures?: string;
  last_error?: string;
  last_result_summary?: Record<string, unknown>;
}

interface DatabasePlan {
  name: string;
  storage_limit_gb: number;
  storage_used_gb: number;
  storage_pct: number;
  connections_limit: number;
}

interface TableSize {
  table: string;
  size_mb: number;
}

interface CryptoInfo {
  markets: number;
  outcomes: number;
  total_markets: number;
  total_outcomes: number;
  pct_of_markets: number;
  pct_of_outcomes: number;
}

interface DatabaseHealth {
  active_events: number;
  live_events: number;
  snapshots_last_hour: number;
  winprob_last_hour: number;
  db_size_mb: number;
  growth_rate_mb_per_day: number | null;
  days_until_full: number | null;
  plan: DatabasePlan;
  table_sizes?: TableSize[];
  crypto?: CryptoInfo;
}

interface DashboardData {
  generated_at: string;
  quota: {
    current: QuotaCurrent;
    daily_usage: DailyUsage[];
    daily_by_task: DailyByTask[];
    budget: QuotaBudget;
  };
  source_coverage: SourceCoverage[];
  coverage_trend: CoverageTrendEntry[];
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

// --- Helpers ---

function healthColor(health: string): string {
  switch (health) {
    case "healthy": return "text-green-500";
    case "degraded": case "warning": return "text-yellow-500";
    case "critical": case "worker_down": case "unhealthy": return "text-red-500";
    default: return "text-text-muted";
  }
}

function healthBg(health: string): string {
  switch (health) {
    case "healthy": return "bg-green-500/10 border-green-500/20";
    case "degraded": case "warning": return "bg-yellow-500/10 border-yellow-500/20";
    case "critical": case "worker_down": case "unhealthy": return "bg-red-500/10 border-red-500/20";
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

// --- Components ---

function StatCard({
  label,
  value,
  sub,
  health,
  detail,
}: {
  label: string;
  value: string;
  sub?: string;
  health?: string;
  detail?: string;
}) {
  return (
    <div className={"rounded-xl border p-4 " + (health ? healthBg(health) : "bg-surface-card border-surface-border")}>
      <div className="text-micro text-text-muted uppercase tracking-wider">{label}</div>
      <div className={"text-2xl font-bold mt-1 " + (health ? healthColor(health) : "text-text-primary")}>
        {value}
      </div>
      {sub && <div className="text-xs text-text-muted mt-0.5">{sub}</div>}
      {detail && <div className="text-micro text-text-muted mt-1 leading-relaxed">{detail}</div>}
    </div>
  );
}

function KeyTakeaways({ data }: { data: DashboardData }) {
  const items: { icon: string; text: string; severity: "ok" | "warn" | "crit" }[] = [];

  // Quota
  const surplus = data.quota.budget.projected_surplus;
  if (surplus < 0) {
    items.push({
      icon: "!",
      text: "Odds API projected to exceed 5M budget by " + formatNum(Math.abs(surplus)) + " at current 48h pace (" + formatNum(data.quota.budget.pace_48h_daily) + "/day). Budget allows " + formatNum(data.quota.budget.linear_daily_budget) + "/day.",
      severity: "crit",
    });
  } else if (data.quota.current.pct_used > 85) {
    items.push({
      icon: "!",
      text: "Odds API at " + data.quota.current.pct_used + "% but pace is sustainable. Projected to finish " + formatNum(surplus) + " under budget.",
      severity: "warn",
    });
  } else {
    items.push({ icon: "✓", text: "Odds API quota on track. " + formatNum(surplus) + " under budget at current pace.", severity: "ok" });
  }

  // Database
  if (data.database.plan) {
    const pct = data.database.plan.storage_pct;
    const daysLeft = data.database.days_until_full;
    if (pct >= 85) {
      items.push({
        icon: "!",
        text: "Database at " + pct + "% capacity (" + data.database.plan.storage_used_gb + " / " + data.database.plan.storage_limit_gb + " GB). " +
          (daysLeft ? "~" + daysLeft + " days until full at current write rate." : "Growth rate unknown.") +
          " Consider running snapshot collapse or upgrading plan.",
        severity: pct >= 95 ? "crit" : "warn",
      });
    }
  }

  // Worker
  if (data.worker.critical_tasks.length > 0) {
    items.push({
      icon: "!",
      text: "Critical task failures: " + data.worker.critical_tasks.join(", ") + ". These have failed 5+ times consecutively.",
      severity: "crit",
    });
  }
  if (data.worker.worker_status !== "healthy") {
    items.push({ icon: "!", text: "Worker is " + data.worker.worker_status + ". Tasks may not be running.", severity: "crit" });
  }

  // Source coverage gaps for major sports
  const majorSports = ["basketball_nba", "americanfootball_nfl", "icehockey_nhl", "baseball_mlb", "basketball_ncaab"];
  for (const row of data.source_coverage) {
    if (majorSports.includes(row.sport)) {
      const kalshiPct = row.total > 0 ? Math.round((row.kalshi / row.total) * 100) : 0;
      const polyPct = row.total > 0 ? Math.round((row.polymarket / row.total) * 100) : 0;
      if (kalshiPct < 20 && polyPct < 20) {
        const shortSport = row.sport.split("_").pop();
        items.push({
          icon: "~",
          text: shortSport!.toUpperCase() + " has low prediction market coverage (Kalshi " + kalshiPct + "%, Polymarket " + polyPct + "%).",
          severity: "warn",
        });
      }
    }
  }

  if (items.length === 0) {
    items.push({ icon: "✓", text: "All systems healthy. No issues detected.", severity: "ok" });
  }

  const severityColors = {
    ok: "text-green-400",
    warn: "text-yellow-400",
    crit: "text-red-400",
  };
  const severityBg = {
    ok: "bg-green-500/5",
    warn: "bg-yellow-500/5",
    crit: "bg-red-500/5",
  };

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-2">Key Takeaways</h3>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div key={i} className={"flex gap-2 text-xs p-2 rounded-lg " + severityBg[item.severity]}>
            <span className={"font-bold shrink-0 " + severityColors[item.severity]}>{item.icon}</span>
            <span className="text-text-secondary">{item.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function QuotaChart({ data, budget }: { data: DailyUsage[]; budget: QuotaBudget }) {
  const chartData = useMemo(() => {
    if (!data.length) return [];

    // Build budget line: straight from day 1 to last day of month
    const budgetPerDay = budget.total / budget.days_in_month;
    const points: Record<string, { date: string; budget: number; used?: number; projected?: number }> = {};

    // Generate budget for every day of the month
    const monthPrefix = data[0]?.date.slice(0, 8) || "2026-03-";
    for (let d = 1; d <= budget.days_in_month; d++) {
      const dateStr = monthPrefix + String(d).padStart(2, "0");
      const label = dateStr.slice(5); // MM-DD
      points[label] = {
        date: label,
        budget: Math.round(budgetPerDay * d),
      };
    }

    // Overlay actuals
    for (const d of data) {
      const label = d.date.slice(5);
      if (points[label]) {
        points[label].used = d.cumulative;
      }
    }

    // Add projection: dotted from last actual to EOM
    const lastActual = data[data.length - 1];
    if (lastActual) {
      const lastLabel = lastActual.date.slice(5);
      const eomLabel = monthPrefix.slice(5) + String(budget.days_in_month).padStart(2, "0");
      if (points[lastLabel]) {
        points[lastLabel].projected = lastActual.cumulative;
      }
      if (points[eomLabel]) {
        points[eomLabel].projected = budget.projected_eom;
      }
    }

    return Object.values(points).sort((a, b) => a.date.localeCompare(b.date));
  }, [data, budget]);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Odds API Quota</h3>
      <p className="text-xs text-text-muted mb-3">
        Cumulative usage vs. {formatNum(budget.total)} monthly budget
      </p>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#888" }} interval={Math.max(1, Math.floor(chartData.length / 8))} />
            <YAxis tickFormatter={formatNum} tick={{ fontSize: 10, fill: "#888" }} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#aaa" }}
              formatter={(val: number, name: string) => [formatNum(val), name === "budget" ? "Budget" : name === "used" ? "Actual" : "Projected"]}
            />
            <Line type="linear" dataKey="budget" stroke="#555" strokeDasharray="6 3" dot={false} name="budget" connectNulls />
            <Line type="monotone" dataKey="used" stroke="#22c55e" strokeWidth={2} dot={false} name="used" connectNulls={false} />
            <Line type="linear" dataKey="projected" stroke="#ef4444" strokeDasharray="4 2" strokeWidth={2} dot={false} name="projected" connectNulls />
            <ReferenceLine y={budget.total} stroke="#ef4444" strokeDasharray="2 2" label="" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DailyBurnChart({ data, byTask, dailyBudget }: { data: DailyUsage[]; byTask: DailyByTask[]; dailyBudget: number }) {
  // Merge daily usage with per-task breakdown for last 14 days
  const chartData = useMemo(() => {
    const recent = data.slice(-14);
    const taskMap = new Map(byTask.map((d) => [d.date, d]));

    return recent.map((d) => {
      const task = taskMap.get(d.date);
      // If we have task breakdown, use it; otherwise show total as "other"
      if (task && ((task.poll_odds || 0) + (task.discover_events || 0) + (task.poll_futures || 0)) > 0) {
        return {
          date: d.date,
          poll_odds: task.poll_odds || 0,
          discover_events: task.discover_events || 0,
          poll_futures: task.poll_futures || 0,
        };
      }
      return {
        date: d.date,
        poll_odds: d.daily_requests,
        discover_events: 0,
        poll_futures: 0,
      };
    });
  }, [data, byTask]);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Daily API Burn by Task</h3>
      <p className="text-xs text-text-muted mb-3">Breakdown: live polling, discovery, and futures (last 14 days)</p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fontSize: 10, fill: "#888" }} />
            <YAxis tickFormatter={formatNum} tick={{ fontSize: 10, fill: "#888" }} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              formatter={(val: number, name: string) => {
                const labels: Record<string, string> = {
                  poll_odds: "Live Polling",
                  discover_events: "Discovery",
                  poll_futures: "Futures",
                };
                return [formatNum(val), labels[name] || name];
              }}
            />
            <Legend
              formatter={(value: string) => {
                const labels: Record<string, string> = {
                  poll_odds: "Live Polling",
                  discover_events: "Discovery",
                  poll_futures: "Futures",
                };
                return labels[value] || value;
              }}
              wrapperStyle={{ fontSize: 11 }}
            />
            <Bar dataKey="poll_odds" stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]} />
            <Bar dataKey="discover_events" stackId="a" fill="#f59e0b" radius={[0, 0, 0, 0]} />
            <Bar dataKey="poll_futures" stackId="a" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
            <ReferenceLine y={dailyBudget} stroke="#ef4444" strokeDasharray="6 3" label={{ value: "Budget", fill: "#ef4444", fontSize: 10, position: "right" }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DatabaseCard({ db }: { db: DatabaseHealth }) {
  const pct = db.plan?.storage_pct || 0;
  const health = pct >= 95 ? "critical" : pct >= 80 ? "warning" : "healthy";

  return (
    <div className={"rounded-xl border p-4 " + healthBg(health)}>
      <h3 className="text-sm font-semibold text-text-primary mb-2">Database Storage</h3>
      <div className="flex items-end gap-2 mb-2">
        <span className={"text-3xl font-bold " + healthColor(health)}>
          {db.plan?.storage_used_gb || (db.db_size_mb / 1024).toFixed(1)} GB
        </span>
        <span className="text-sm text-text-muted mb-1">/ {db.plan?.storage_limit_gb || 10} GB</span>
      </div>
      {/* Progress bar */}
      <div className="h-3 bg-surface-border rounded-full overflow-hidden mb-3">
        <div
          className={"h-full rounded-full transition-all " + (pct >= 95 ? "bg-red-500" : pct >= 80 ? "bg-yellow-500" : "bg-green-500")}
          style={{ width: Math.min(pct, 100) + "%" }}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-text-muted">Plan: </span>
          <span className="text-text-secondary font-medium">{db.plan?.name || "unknown"}</span>
        </div>
        <div>
          <span className="text-text-muted">Growth: </span>
          <span className="text-text-secondary font-medium">
            {db.growth_rate_mb_per_day ? db.growth_rate_mb_per_day + " MB/day" : "calculating..."}
          </span>
        </div>
        <div>
          <span className="text-text-muted">Days until full: </span>
          <span className={"font-medium " + (db.days_until_full && db.days_until_full < 14 ? "text-red-400" : db.days_until_full && db.days_until_full < 30 ? "text-yellow-400" : "text-text-secondary")}>
            {db.days_until_full ? "~" + db.days_until_full : "unknown"}
          </span>
        </div>
        <div>
          <span className="text-text-muted">Connections: </span>
          <span className="text-text-secondary font-medium">{db.plan?.connections_limit || 20} max</span>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs border-t border-surface-border/50 pt-2">
        <div>
          <span className="text-text-muted">Odds snapshots/hr: </span>
          <span className="text-text-secondary font-medium">{db.snapshots_last_hour.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-text-muted">WinProb snapshots/hr: </span>
          <span className="text-text-secondary font-medium">{db.winprob_last_hour.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-text-muted">Live events: </span>
          <span className="text-green-400 font-medium">{db.live_events}</span>
        </div>
        <div>
          <span className="text-text-muted">Active events: </span>
          <span className="text-text-secondary font-medium">{db.active_events.toLocaleString()}</span>
        </div>
      </div>
      {/* Table sizes breakdown */}
      {db.table_sizes && db.table_sizes.length > 0 && (
        <div className="mt-3 border-t border-surface-border/50 pt-2">
          <div className="text-micro text-text-muted uppercase tracking-wider mb-2">Storage by Table</div>
          <div className="space-y-1">
            {db.table_sizes.filter((t: TableSize) => t.size_mb > 10).map((t: TableSize) => {
              const pctOfTotal = Math.round(t.size_mb / db.db_size_mb * 100);
              return (
                <div key={t.table} className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-text-secondary w-40 truncate">{t.table}</span>
                  <div className="flex-1 h-2 bg-surface-border rounded-full overflow-hidden">
                    <div className="h-full bg-accent-futures/60 rounded-full" style={{ width: pctOfTotal + "%" }} />
                  </div>
                  <span className="text-text-muted w-20 text-right">{t.size_mb >= 1024 ? (t.size_mb / 1024).toFixed(1) + " GB" : Math.round(t.size_mb) + " MB"} ({pctOfTotal}%)</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {/* Crypto footprint */}
      {db.crypto && db.crypto.markets > 0 && (
        <div className="mt-3 border-t border-surface-border/50 pt-2">
          <div className="text-micro text-text-muted uppercase tracking-wider mb-1">Crypto Footprint</div>
          <div className="text-xs text-text-secondary">
            <span className="font-medium text-yellow-400">{db.crypto.pct_of_markets}%</span> of futures markets ({db.crypto.markets.toLocaleString()} / {db.crypto.total_markets.toLocaleString()})
            {" · "}
            <span className="font-medium text-yellow-400">{db.crypto.pct_of_outcomes}%</span> of futures outcomes ({db.crypto.outcomes.toLocaleString()} / {db.crypto.total_outcomes.toLocaleString()})
          </div>
        </div>
      )}
    </div>
  );
}

function CoverageTrendChart({ data }: { data: CoverageTrendEntry[] }) {
  const [selectedSport, setSelectedSport] = useState<string | null>(null);

  // Group by sport, pick sports with most data
  const sportGroups = useMemo(() => {
    const groups: Record<string, CoverageTrendEntry[]> = {};
    for (const entry of data) {
      if (!groups[entry.sport]) groups[entry.sport] = [];
      groups[entry.sport].push(entry);
    }
    return groups;
  }, [data]);

  const sportNames = Object.keys(sportGroups).sort((a, b) =>
    (sportGroups[b]?.length || 0) - (sportGroups[a]?.length || 0)
  );

  const activeSport = selectedSport || sportNames[0] || "";
  const sportData = sportGroups[activeSport] || [];

  const chartData = useMemo(() => {
    return sportData.map((d) => ({
      date: d.date.slice(5), // MM-DD
      "Odds API": d.odds_api_pct,
      ESPN: d.espn_pct,
      StatPal: d.statpal_pct,
      "ESPN WP": d.espn_wp_pct ?? null,
      Model: d.model_pct ?? null,
      Kalshi: d.kalshi_pct ?? null,
      Polymarket: d.polymarket_pct ?? null,
      isFuture: d.is_future,
      events: d.total,
    }));
  }, [sportData]);

  if (!data.length) return null;

  const sportLabel = (s: string) => {
    const parts = s.split("_");
    return parts[parts.length - 1]?.toUpperCase() || s;
  };

  const sourceColors: Record<string, string> = {
    "Odds API": "#3b82f6",
    ESPN: "#f59e0b",
    StatPal: "#8b5cf6",
    "ESPN WP": "#22c55e",
    Model: "#06b6d4",
    Kalshi: "#ef4444",
    Polymarket: "#ec4899",
  };

  // Find the index where future starts for reference line
  const futureIdx = chartData.findIndex((d) => d.isFuture);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-text-primary">Source Coverage Trend</h3>
        <div className="flex gap-1 flex-wrap">
          {sportNames.map((s) => (
            <span
              key={s}
              onClick={() => setSelectedSport(s)}
              className={
                "text-micro px-2 py-0.5 rounded-full cursor-pointer select-none border " +
                (s === activeSport
                  ? "bg-accent-futures/20 border-accent-futures text-accent-futures"
                  : "bg-surface-elevated border-surface-border text-text-muted hover:text-text-secondary")
              }
            >
              {sportLabel(s)}
            </span>
          ))}
        </div>
      </div>
      <p className="text-xs text-text-muted mb-3">
        % of {sportLabel(activeSport)} events covered by each source (past 14d + future scheduled).
        Dashed region = future events (no win-prob data yet).
      </p>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#888" }} interval={Math.max(1, Math.floor(chartData.length / 10))} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#888" }} tickFormatter={(v: number) => v + "%"} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: "#aaa" }}
              formatter={(val: any, name: string) => [val != null ? val + "%" : "n/a", name]}
              labelFormatter={(label: string, payload: any[]) => {
                const p = payload?.[0]?.payload;
                return label + (p ? " (" + p.events + " events" + (p.isFuture ? ", future" : "") + ")" : "");
              }}
            />
            {futureIdx > 0 && (
              <ReferenceLine x={chartData[futureIdx]?.date} stroke="#666" strokeDasharray="4 2" label="" />
            )}
            {Object.entries(sourceColors).map(([name, color]) => (
              <Line
                key={name}
                type="monotone"
                dataKey={name}
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                connectNulls={false}
              />
            ))}
            <Legend wrapperStyle={{ fontSize: 10 }} />
          </LineChart>
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
              <th className="text-right py-2 px-1 text-text-muted font-medium" title="Odds snapshots written in last 24h">Snaps/24h</th>
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
                <td className="text-right py-1.5 px-1 text-text-muted">
                  {row.snapshots_24h > 0 ? formatNum(row.snapshots_24h) : "-"}
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

// --- Main ---

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
            Auto-refreshes every 60s &middot; Updated {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg">{error.message}</div>
      )}
      {isLoading && <div className="text-sm text-text-muted animate-pulse">Loading dashboard...</div>}

      {data && (
        <>
          {/* Key takeaways */}
          <KeyTakeaways data={data} />

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
              label="48h Burn Rate"
              value={formatNum(data.quota.budget.pace_48h_daily) + "/day"}
              sub={"Budget: " + formatNum(data.quota.budget.linear_daily_budget) + "/day"}
              health={data.quota.budget.pace_48h_daily > data.quota.budget.linear_daily_budget * 1.1 ? "warning" : "healthy"}
              detail="Average daily API calls over the last 48 hours. Should stay below the daily budget line."
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
              detail={data.worker.tasks.length + " tasks tracked. " + data.worker.tasks.filter((t) => t.successes_24h > 0).length + " ran in last 24h."}
            />
          </div>

          {/* Quota + burn charts */}
          <div className="grid md:grid-cols-2 gap-4">
            <QuotaChart data={data.quota.daily_usage} budget={data.quota.budget} />
            <DailyBurnChart data={data.quota.daily_usage} byTask={data.quota.daily_by_task || []} dailyBudget={data.quota.budget.linear_daily_budget} />
          </div>

          {/* Database + coverage side by side */}
          <div className="grid md:grid-cols-2 gap-4">
            <DatabaseCard db={data.database} />
            <div className="space-y-4">
              <StatCard
                label="Snapshots/hr"
                value={data.database.snapshots_last_hour.toLocaleString()}
                sub="Odds readings written to DB per hour"
                detail={"At ~500 bytes/row, this adds roughly " + Math.round(data.database.snapshots_last_hour * 500 / 1024 / 1024 * 24) + " MB/day to the database."}
              />
              <StatCard
                label="WinProb/hr"
                value={data.database.winprob_last_hour.toLocaleString()}
                sub="Win probability snapshots per hour"
                detail="From ESPN, stat model, Kalshi, Polymarket, and MLB sources during live games."
              />
            </div>
          </div>

          {/* Source coverage trend */}
          <CoverageTrendChart data={data.coverage_trend || []} />

          {/* Source coverage */}
          <SourceCoverageTable data={data.source_coverage} />
          <FuturesCoverageTable data={data.futures_coverage} />

          {/* Worker tasks */}
          <TasksTable tasks={data.worker.tasks} />
        </>
      )}
    </div>
  );
}
