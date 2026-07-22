"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import AdminCockpit from "@/components/admin/AdminCockpit";
import SentinelsCard from "@/components/admin/SentinelsCard";
import PageHeader from "@/components/admin/PageHeader";
import MetricSection from "@/components/admin/MetricSection";
import DiagnosisCard from "@/components/admin/DiagnosisCard";
import DenominatorTooltip from "@/components/admin/DenominatorTooltip";
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
  score_fetch?: number;
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
  expected_sources?: Record<string, boolean>;
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

interface DbSizeTrendEntry {
  date: string;
  size_mb: number;
}

interface DeadTupleInfo {
  table: string;
  live_tuples: number;
  dead_tuples: number;
  dead_pct: number;
  last_autovacuum: string | null;
}

interface DatabaseHealth {
  active_events?: number;
  live_events?: number;
  snapshots_last_hour?: number;
  winprob_last_hour?: number;
  db_size_mb?: number;
  growth_rate_mb_per_day: number | null;
  days_until_full: number | null;
  plan?: DatabasePlan;
  table_sizes?: TableSize[];
  dead_tuples?: DeadTupleInfo[];
  total_dead_tuples?: number;
  total_live_tuples?: number;
  dead_tuple_pct?: number;
  size_trend?: DbSizeTrendEntry[];
  error?: string;
}

interface MatchingMetricsEntry {
  date: string;
  coverage_pct: number;
  major_coverage_pct: number;
  kalshi_coverage_pct: number;
  polymarket_coverage_pct: number;
  total_events: number;
  matched_events: number;
}

interface GameStateSportRow {
  sport_key: string;
  total_events: number;
  min_indicators: number;
  max_indicators: number;
  avg_indicators: number;
  zero_count: number;
  expected: number | null;
  type: "fixed" | "variable";
  met?: number;
  under?: number;
  over?: number;
  pct_met?: number;
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
  matching_metrics?: MatchingMetricsEntry[];
  game_state_coverage?: GameStateSportRow[];
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

function safeNumber(n: number | null | undefined, fallback = 0): number {
  return typeof n === "number" && Number.isFinite(n) ? n : fallback;
}

function formatMaybeNum(n: number | null | undefined): string {
  return safeNumber(n).toLocaleString();
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

function CoverageCell({ val, total, expected = true }: { val: number; total: number; expected?: boolean }) {
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

// L2-129 Item 1 — THE ACTION RULE, cockpit-wide. Every non-green badge on a
// self-fetching card (LinkRate/DataQuality/GridHealth/PREQ) gets a sentence:
// what it means + what to do + the tracked pointer. Mirrors AdminCockpit's
// tileAction so "Needs attention" never dead-ends without a place to look.
function CardAction({ tone, children }: { tone: "danger" | "warn" | "muted"; children: React.ReactNode }) {
  const cls =
    tone === "danger"
      ? "border-accent-danger/30 bg-accent-danger/10 text-accent-danger"
      : tone === "warn"
        ? "border-yellow-500/30 bg-yellow-500/10 text-yellow-600"
        : "border-surface-border bg-surface-elevated text-text-muted";
  return (
    <div className={"mt-3 rounded-lg border px-2.5 py-2 text-micro leading-relaxed " + cls}>
      {children}
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

  // Quota polling anomaly alerts
  const dailyUsage = data.quota?.daily_usage || [];
  if (dailyUsage.length >= 2) {
    const recentDays = dailyUsage.slice(-2);
    const avgRecent = recentDays.reduce((s: number, d: { daily_requests: number }) => s + d.daily_requests, 0) / recentDays.length;
    const latestDay = dailyUsage[dailyUsage.length - 1];

    if (avgRecent < 20000) {
      items.push({
        icon: "!",
        text: "Polling critically low: averaging " + formatNum(Math.round(avgRecent)) + "/day over last 2 days. Expected 60-80K/day. Check worker health and sport 404 caches.",
        severity: "crit",
      });
    } else if (avgRecent < 50000) {
      items.push({
        icon: "!",
        text: "Polling below expected: averaging " + formatNum(Math.round(avgRecent)) + "/day over last 2 days. Expected 60-80K/day.",
        severity: "warn",
      });
    }

    if (latestDay && latestDay.daily_requests > 350000) {
      items.push({
        icon: "!",
        text: "Polling spike: " + formatNum(latestDay.daily_requests) + " requests today (" + latestDay.date + "). Budget is " + formatNum(data.quota.budget.linear_daily_budget) + "/day. Risk of triggering conservation mode.",
        severity: "crit",
      });
    } else if (latestDay && latestDay.daily_requests > 200000) {
      items.push({
        icon: "!",
        text: "Elevated polling: " + formatNum(latestDay.daily_requests) + " requests today. Monitor for runaway loop.",
        severity: "warn",
      });
    }
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

    // Generate budget for every day of the month (UTC-based)
    const utcNow = new Date();
    const utcMonth = String(utcNow.getUTCMonth() + 1).padStart(2, "0");
    const monthPrefix = `${utcNow.getUTCFullYear()}-${utcMonth}-`;
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
            <Line type="linear" dataKey="used" stroke="#22c55e" strokeWidth={2} dot={false} name="used" connectNulls={false} />
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
      const total = d.daily_requests;
      if (task) {
        const tracked = (task.poll_odds || 0) + (task.discover_events || 0) + (task.poll_futures || 0) + (task.score_fetch || 0);
        if (tracked > 0) {
          const scale = total / tracked;
          return {
            date: d.date,
            poll_odds: Math.round((task.poll_odds || 0) * scale),
            discover_events: Math.round((task.discover_events || 0) * scale),
            poll_futures: Math.round((task.poll_futures || 0) * scale),
            score_fetch: Math.round((task.score_fetch || 0) * scale),
          };
        }
      }
      return {
        date: d.date,
        poll_odds: total,
        discover_events: 0,
        poll_futures: 0,
        score_fetch: 0,
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
                  score_fetch: "Scores",
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
                  score_fetch: "Scores",
                };
                return labels[value] || value;
              }}
              wrapperStyle={{ fontSize: 11 }}
            />
            <Bar dataKey="poll_odds" stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]} />
            <Bar dataKey="discover_events" stackId="a" fill="#f59e0b" radius={[0, 0, 0, 0]} />
            <Bar dataKey="poll_futures" stackId="a" fill="#8b5cf6" radius={[0, 0, 0, 0]} />
            <Bar dataKey="score_fetch" stackId="a" fill="#10b981" radius={[3, 3, 0, 0]} />
            <ReferenceLine y={dailyBudget} stroke="#ef4444" strokeDasharray="6 3" label={{ value: "Budget", fill: "#ef4444", fontSize: 10, position: "right" }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function GameStateCoverageChart({ data }: { data: GameStateSportRow[] }) {
  const fixedSports = data
    .filter((d) => d.type === "fixed" && d.total_events > 0)
    .sort((a, b) => (b.pct_met ?? 0) - (a.pct_met ?? 0));
  const variableSports = data
    .filter((d) => d.type === "variable" && d.total_events > 0)
    .sort((a, b) => b.total_events - a.total_events);

  if (!fixedSports.length && !variableSports.length) return null;

  const sportLabel = (key: string) => {
    const parts = key.split("_");
    return parts.length > 1 ? parts.slice(1).join(" ").toUpperCase() : key.toUpperCase();
  };

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Game State Indicators by Sport</h3>
      <p className="text-xs text-text-muted mb-3">Period/quarter/inning coverage for completed events (14 days)</p>

      {fixedSports.length > 0 && (
        <div className="space-y-1.5 mb-4">
          {fixedSports.map((s) => {
            const total = s.total_events;
            const met = s.met ?? 0;
            const under = s.under ?? 0;
            const over = s.over ?? 0;
            const pctMet = total > 0 ? (met / total) * 100 : 0;
            const pctUnder = total > 0 ? (under / total) * 100 : 0;
            const pctOver = total > 0 ? (over / total) * 100 : 0;

            return (
              <div key={s.sport_key} className="flex items-center gap-2">
                <span className="text-xs text-text-secondary w-20 truncate text-right" title={s.sport_key}>
                  {sportLabel(s.sport_key)}
                </span>
                <div className="flex-1 flex h-4 rounded overflow-hidden bg-surface-elevated">
                  {pctMet > 0 && (
                    <div
                      className="bg-emerald-500 transition-all"
                      style={{ width: `${pctMet}%` }}
                      title={`Met (=${s.expected}): ${met} events`}
                    />
                  )}
                  {pctUnder > 0 && (
                    <div
                      className="bg-amber-400 transition-all"
                      style={{ width: `${pctUnder}%` }}
                      title={`Under (<${s.expected}): ${under} events`}
                    />
                  )}
                  {pctOver > 0 && (
                    <div
                      className="bg-sky-400 transition-all"
                      style={{ width: `${pctOver}%` }}
                      title={`Over (>${s.expected}): ${over} events`}
                    />
                  )}
                </div>
                <span className="text-xs text-text-muted w-12 text-right">{Math.round(pctMet)}%</span>
                <span className="text-xs text-text-muted w-8 text-right">{total}</span>
              </div>
            );
          })}
          <div className="flex items-center gap-3 mt-2 text-[10px] text-text-muted">
            <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Met</span>
            <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-400" /> Under</span>
            <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-sm bg-sky-400" /> Over (OT)</span>
          </div>
        </div>
      )}

      {variableSports.length > 0 && (
        <div>
          <p className="text-xs text-text-muted mb-1">Variable-round sports</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-muted border-b border-surface-border">
                <th className="text-left py-1 font-medium">Sport</th>
                <th className="text-right py-1 font-medium">Events</th>
                <th className="text-right py-1 font-medium">Avg</th>
                <th className="text-right py-1 font-medium">Min</th>
                <th className="text-right py-1 font-medium">Max</th>
              </tr>
            </thead>
            <tbody>
              {variableSports.map((s) => (
                <tr key={s.sport_key} className="border-b border-surface-border/50">
                  <td className="py-1 text-text-secondary">{sportLabel(s.sport_key)}</td>
                  <td className="py-1 text-right text-text-muted">{s.total_events}</td>
                  <td className="py-1 text-right text-text-primary">{s.avg_indicators}</td>
                  <td className="py-1 text-right text-text-muted">{s.min_indicators}</td>
                  <td className="py-1 text-right text-text-muted">{s.max_indicators}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MatchingCoverageChart({ data }: { data: MatchingMetricsEntry[] }) {
  if (!data.length) return null;

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">Prediction Market Coverage</h3>
      <p className="text-xs text-text-muted mb-3">% of active events matched to Kalshi/Polymarket</p>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.map((d) => ({ ...d, date: d.date.slice(5) }))} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#888" }} interval={Math.max(1, Math.floor(data.length / 8))} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#888" }} tickFormatter={(v: number) => v + "%"} />
            <Tooltip
              contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
              formatter={(val: number, name: string) => {
                const labels: Record<string, string> = {
                  major_coverage_pct: "Major Sports",
                  coverage_pct: "All Sports",
                  kalshi_coverage_pct: "Kalshi",
                  polymarket_coverage_pct: "Polymarket",
                };
                return [val + "%", labels[name] || name];
              }}
            />
            <Legend
              formatter={(value: string) => {
                const labels: Record<string, string> = {
                  major_coverage_pct: "Major Sports",
                  coverage_pct: "All Sports",
                };
                return labels[value] || value;
              }}
              wrapperStyle={{ fontSize: 11 }}
            />
            <ReferenceLine y={100} stroke="#22c55e" strokeDasharray="4 2" label="" />
            <Line type="linear" dataKey="major_coverage_pct" stroke="#f59e0b" strokeWidth={2} dot={false} name="major_coverage_pct" />
            <Line type="linear" dataKey="coverage_pct" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="coverage_pct" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface LinkRateSport {
  sport: string;
  total: number;
  linked: number;
  link_rate: number;
  open_total: number;
  open_linked: number;
  open_link_rate: number;
}
interface LinkRateSource {
  totals: { total: number; linked: number; link_rate_pct: number; open_total: number; open_linked: number; open_link_rate_pct: number };
  by_sport: LinkRateSport[];
}
interface LinkRateData {
  overall: { total_game_markets: number; linked: number; link_rate_pct: number };
  kalshi: LinkRateSource;
  polymarket: LinkRateSource;
}

function LinkRateCard({ secret }: { secret: string }) {
  const { data } = useSWR<LinkRateData>(
    secret ? ["link-rate", secret] : null,
    () =>
      adminFetch("/api/admin/prediction-markets/link-rate", secret)
        .then((r) => r.ok ? r.json() : null),
    { refreshInterval: 300000 }
  );

  if (!data) return null;

  const rateColor = (pct: number) =>
    pct >= 80 ? "text-green-400" : pct >= 50 ? "text-yellow-400" : "text-red-400";

  const barWidth = (pct: number) => Math.max(2, Math.min(100, pct));

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-1">
        Game Market Link Rate{" "}
        <DenominatorTooltip
          numerator="Open game-level markets with event_id set"
          denominator="Open game-level markets from event-covered sports"
          exclusions={["Season futures (MVP, champion, winner)", "Stale Kalshi settlements past game date", "Non-sport categories (politics, crypto, weather)"]}
          note="Headline rate uses open markets only."
        />
      </h3>
      <p className="text-xs text-text-muted mb-3">
        % of open sports game markets linked to events
      </p>
      <div className="grid grid-cols-2 gap-3 mb-3">
        {(["kalshi", "polymarket"] as const).map((src) => {
          const s = data[src];
          return (
            <div key={src} className="text-center">
              <span className={"text-2xl font-bold " + rateColor(s.totals.open_link_rate_pct)}>
                {s.totals.open_link_rate_pct}%
              </span>
              <div className="text-xs text-text-muted capitalize">{src}</div>
              <div className="text-micro text-text-muted">
                {s.totals.open_linked.toLocaleString()} / {s.totals.open_total.toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>
      {(["kalshi", "polymarket"] as const).map((src) => {
        const s = data[src];
        return (
          <div key={src} className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-text-secondary capitalize">{src}</span>
              <span className={"text-xs font-bold " + rateColor(s.totals.open_link_rate_pct)}>
                {s.totals.open_link_rate_pct}%
              </span>
            </div>
            <div className="space-y-0.5">
              {s.by_sport.slice(0, 8).map((sp) => (
                <div key={sp.sport} className="flex items-center gap-2 text-xs">
                  <span className="w-16 text-text-muted truncate">{sp.sport}</span>
                  <div className="flex-1 h-3 bg-surface-elevated rounded-full overflow-hidden">
                    <div
                      className={
                        "h-full rounded-full " +
                        (sp.open_link_rate >= 80 ? "bg-green-500/60" : sp.open_link_rate >= 50 ? "bg-yellow-500/60" : "bg-red-500/60")
                      }
                      style={{ width: barWidth(sp.open_link_rate) + "%" }}
                    />
                  </div>
                  <span className={"w-10 text-right font-mono " + rateColor(sp.open_link_rate)}>
                    {sp.open_link_rate}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {/* L2-129 Item 1 — action rule: a sub-80% link rate is not a dead end. */}
      {(() => {
        const low = (["kalshi", "polymarket"] as const)
          .filter((s) => data[s].totals.open_link_rate_pct < 80)
          .map((s) => `${s} ${data[s].totals.open_link_rate_pct}%`);
        if (low.length === 0) return null;
        const worst = Math.min(data.kalshi.totals.open_link_rate_pct, data.polymarket.totals.open_link_rate_pct);
        return (
          <CardAction tone={worst < 50 ? "danger" : "warn"}>
            <strong>{low.join(", ")}</strong> of open game markets aren&rsquo;t linked to events — unlinked
            markets don&rsquo;t appear on event pages or feed the blend. Do this: check the 15-min{" "}
            <code>match_prediction_markets</code> task (Pass 1 Kalshi ticker scan / Pass 2 Polymarket name
            match) and the ticker→sport maps in <code>sport_keys.py</code> — a low rate concentrated in one
            sport (bars above) is usually a missing ticker prefix, not a matching regression. Drill in:{" "}
            <a href="/admin/matching" className="underline">/admin/matching</a>.
          </CardAction>
        );
      })()}
    </div>
  );
}

function DatabaseCard({ db }: { db: DatabaseHealth }) {
  const pct = db.plan?.storage_pct || 0;
  const health = pct >= 95 ? "critical" : pct >= 80 ? "warning" : "healthy";
  const dbSizeMb = safeNumber(db.db_size_mb);
  const snapshotsLastHour = safeNumber(db.snapshots_last_hour);
  const winprobLastHour = safeNumber(db.winprob_last_hour);

  return (
    <div className={"rounded-xl border p-4 " + healthBg(health)}>
      <h3 className="text-sm font-semibold text-text-primary mb-2">Database Storage</h3>
      {db.error && (
        <div className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 p-2 text-xs text-red-500">
          Database health query failed: {db.error}
        </div>
      )}
      <div className="flex items-end gap-2 mb-2">
        <span className={"text-3xl font-bold " + healthColor(health)}>
          {db.plan?.storage_used_gb || (dbSizeMb / 1024).toFixed(1)} GB
        </span>
        <span className="text-sm text-text-muted mb-1">/ {db.plan?.storage_limit_gb || 10} GB</span>
      </div>
      {/* Progress bar — split into live (solid) and dead (striped) */}
      {(() => {
        const deadPct = db.dead_tuple_pct || 0;
        const livePct = Math.min(pct, 100) * (1 - deadPct / 100);
        const deadWidth = Math.min(pct, 100) * (deadPct / 100);
        const barColor = pct >= 95 ? "bg-red-500" : pct >= 80 ? "bg-yellow-500" : "bg-green-500";
        const deadColor = pct >= 95 ? "bg-red-300" : pct >= 80 ? "bg-yellow-300" : "bg-green-300";
        return (
          <div className="h-3 bg-surface-border rounded-full overflow-hidden mb-3 flex">
            <div className={"h-full transition-all " + barColor + (deadWidth > 0 ? "" : " rounded-full")} style={{ width: livePct + "%" }} />
            {deadWidth > 0.5 && (
              <div className={"h-full rounded-r-full transition-all " + deadColor} style={{ width: deadWidth + "%", backgroundImage: "repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(255,255,255,0.3) 2px, rgba(255,255,255,0.3) 4px)" }} />
            )}
          </div>
        );
      })()}
      {db.dead_tuple_pct != null && db.dead_tuple_pct > 0 && (
        <div className="text-[10px] text-text-muted mb-2 -mt-1">
          {((pct * (100 - db.dead_tuple_pct)) / 100).toFixed(0)}% live + {((pct * db.dead_tuple_pct) / 100).toFixed(1)}% reclaimable
        </div>
      )}
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
          <span className="text-text-secondary font-medium">{snapshotsLastHour.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-text-muted">WinProb snapshots/hr: </span>
          <span className="text-text-secondary font-medium">{winprobLastHour.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-text-muted">Live events: </span>
          <span className="text-green-400 font-medium">{formatMaybeNum(db.live_events)}</span>
        </div>
        <div>
          <span className="text-text-muted">Active events: </span>
          <span className="text-text-secondary font-medium">{formatMaybeNum(db.active_events)}</span>
        </div>
      </div>
      {/* Table sizes breakdown */}
      {db.table_sizes && db.table_sizes.length > 0 && (
        <div className="mt-3 border-t border-surface-border/50 pt-2">
          <div className="text-micro text-text-muted uppercase tracking-wider mb-2">Storage by Table</div>
          <div className="space-y-1">
            {db.table_sizes.filter((t: TableSize) => t.size_mb > 10).map((t: TableSize) => {
              const pctOfTotal = dbSizeMb > 0 ? Math.round(t.size_mb / dbSizeMb * 100) : 0;
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
      {/* Dead tuples (space reclaimable by VACUUM) */}
      {db.dead_tuples && db.dead_tuples.length > 0 && (
        <div className="mt-3 border-t border-surface-border/50 pt-2">
          <div className="flex items-center justify-between mb-2">
            <div className="text-micro text-text-muted uppercase tracking-wider">Dead Tuples (Reclaimable Space)</div>
            {db.dead_tuple_pct != null && (
              <span className={"text-xs font-medium " + (db.dead_tuple_pct > 20 ? "text-yellow-400" : "text-text-muted")}>
                {db.dead_tuple_pct}% dead
              </span>
            )}
          </div>
          <div className="space-y-1">
            {db.dead_tuples.filter((t: DeadTupleInfo) => t.dead_tuples > 1000).map((t: DeadTupleInfo) => (
              <div key={t.table} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-text-secondary w-40 truncate">{t.table}</span>
                <div className="flex-1 h-2 bg-surface-border rounded-full overflow-hidden">
                  <div className="h-full rounded-full flex">
                    <div className="h-full bg-green-500/60 rounded-l-full" style={{ width: (100 - t.dead_pct) + "%" }} />
                    <div className="h-full bg-yellow-500/60 rounded-r-full" style={{ width: t.dead_pct + "%" }} />
                  </div>
                </div>
                <span className="text-text-muted w-28 text-right">
                  {t.dead_tuples > 1000000 ? (t.dead_tuples / 1000000).toFixed(1) + "M" : t.dead_tuples > 1000 ? Math.round(t.dead_tuples / 1000) + "K" : t.dead_tuples} dead ({t.dead_pct}%)
                </span>
              </div>
            ))}
          </div>
          {db.dead_tuples[0]?.last_autovacuum && (
            <div className="text-[10px] text-text-muted mt-1">
              Last autovacuum: {new Date(db.dead_tuples[0].last_autovacuum).toLocaleString()}
            </div>
          )}
        </div>
      )}
      {/* Storage trend chart */}
      {db.size_trend && db.size_trend.length > 1 && (
        <div className="mt-3 border-t border-surface-border/50 pt-2">
          <div className="text-micro text-text-muted uppercase tracking-wider mb-2">Storage Trend</div>
          <div className="h-36">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={db.size_trend.map((d) => ({
                  date: d.date.slice(5),
                  size_gb: +(d.size_mb / 1024).toFixed(2),
                }))}
                margin={{ top: 5, right: 10, bottom: 5, left: 10 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#888" }} interval={Math.max(1, Math.floor(db.size_trend.length / 6))} />
                <YAxis tick={{ fontSize: 9, fill: "#888" }} domain={[0, db.plan.storage_limit_gb]} tickFormatter={(v: number) => v + " GB"} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8, fontSize: 12 }}
                  formatter={(val: number) => [val.toFixed(2) + " GB", "Used"]}
                />
                <ReferenceLine y={db.plan.storage_limit_gb} stroke="#ef4444" strokeDasharray="4 2" label={{ value: "Limit", fill: "#ef4444", fontSize: 9, position: "right" }} />
                <Line type="linear" dataKey="size_gb" stroke="#8b5cf6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
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
                type="linear"
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
                  <CoverageCell key={s.key} val={row[s.key]} total={row.total} expected={row.expected_sources?.[s.key] ?? true} />
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

  const { secret } = useAdminAuth();

  const { data, error, isLoading } = useSWR<DashboardData>(
    ["admin-dashboard", secret],
    () =>
      adminFetchJSON<DashboardData>("/api/admin/dashboard", secret),
    { refreshInterval: 60000 }
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <PageHeader
          question="Is the system healthy?"
          status={
            error ? "critical"
            : isLoading ? "loading"
            : data?.worker?.overall_health === "critical" ? "critical"
            : data?.worker?.overall_health !== "healthy" || (data?.quota?.budget?.projected_surplus ?? 1) < 0 ? "warning"
            : "good"
          }
          summary={
            isLoading ? "Loading dashboard..."
            : error ? error.message
            : `${data?.source_coverage?.length ?? 0} sports tracked · ${data?.quota?.current?.health ?? "unknown"} quota`
          }
          ideal="All workers healthy, quota on budget, all sources reporting."
          subtitle="Operations Dashboard"
        />
        {data && (
          <span className="text-micro text-text-muted">
            Auto-refreshes every 60s &middot; Updated {new Date(data.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Alex Cockpit (L2-102): quick site-health view, what's waiting on Alex,
          and the quick human-eval queue. Renders above the full ops dashboard;
          all existing sub-pages stay reachable via the sidebar. */}
      <AdminCockpit />

      {/* L2-153: the sentinel family's own cockpit presence — a silent guard
          (no run cached / stale beyond 1.5× its beat) reads RED so it can't go
          dark unnoticed (the r236 catch). Reads the three /last endpoints. */}
      <SentinelsCard />

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg">{error.message}</div>
      )}
      {isLoading && <div className="text-sm text-text-muted animate-pulse">Loading dashboard...</div>}

      {data && (
        <>
          {/* IA order (L2-142 Item 2): the cockpit's reds-with-actions render
              first (inside <AdminCockpit /> above), Key Takeaways second, and the
              System Diagnosis + full detail sections below. The first screenful
              answers "what needs anyone's attention." */}
          <KeyTakeaways data={data} />

          <DiagnosisCard />

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

          <MetricSection
            question="Is the Odds API budget on track?"
            status={(data.quota.budget.projected_surplus ?? 1) < 0 ? "warning" : "good"}
            summary={`${data.quota.current.pct_used}% used · ${Math.round(data.quota.budget.projected_surplus ?? 0).toLocaleString()} projected surplus`}
            ideal="Positive surplus projected through end of month."
            action={(data.quota.budget.projected_surplus ?? 1) < 0
              ? "Projected to overspend the 5M/mo Odds API quota. Do this: cut Tier-3 polling frequency in SPORT_POLLING_TIERS or tighten the circuit-breaker thresholds (LIVE_ONLY/FULL_STOP in tasks/redis_state.py), and check the burn chart for the task driving the spend. Quota bills per events×market_types×regions (gotcha #11)."
              : undefined}
          >
          {/* Quota + burn charts */}
          <div className="grid md:grid-cols-2 gap-4">
            <QuotaChart data={data.quota.daily_usage} budget={data.quota.budget} />
            <DailyBurnChart data={data.quota.daily_usage} byTask={data.quota.daily_by_task || []} dailyBudget={data.quota.budget.linear_daily_budget} />
          </div>

          </MetricSection>

          <MetricSection
            question="Are infrastructure and markets healthy?"
            status={data.database?.days_until_full !== null && (data.database?.days_until_full ?? 999) < 30 ? "warning" : "good"}
            summary={`DB: ${data.database?.db_size_mb ?? '?'}MB · ${data.database?.plan?.connections_limit ?? '?'} max connections`}
            ideal="Database growing sustainably, all markets linked."
            action={data.database?.days_until_full !== null && (data.database?.days_until_full ?? 999) < 30
              ? `Database is ~${data.database?.days_until_full} days from full at the current write rate. Do this: prune odds_snapshots / win_prob_snapshots retention or bump the Heroku Postgres plan. The Snapshots/hr and WinProb/hr tiles below show what's driving growth.`
              : undefined}
          >
          {/* Database + coverage side by side */}
          <div className="grid md:grid-cols-2 gap-4">
            {data.matching_metrics && data.matching_metrics.length > 0 && (
              <MatchingCoverageChart data={data.matching_metrics} />
            )}
            <LinkRateCard secret={secret} />
            {data.game_state_coverage && data.game_state_coverage.length > 0 && (
              <GameStateCoverageChart data={data.game_state_coverage} />
            )}
            <DatabaseCard db={data.database} />
            <div className="space-y-4">
              <StatCard
                label="Snapshots/hr"
                value={formatMaybeNum(data.database?.snapshots_last_hour)}
                sub="Odds readings written to DB per hour"
                detail={"At ~500 bytes/row, this adds roughly " + Math.round(safeNumber(data.database?.snapshots_last_hour) * 500 / 1024 / 1024 * 24) + " MB/day to the database."}
              />
              <StatCard
                label="WinProb/hr"
                value={formatMaybeNum(data.database?.winprob_last_hour)}
                sub="Win probability snapshots per hour"
                detail="From ESPN, stat model, Kalshi, Polymarket, and MLB sources during live games."
              />
            </div>
          </div>

          </MetricSection>

          {/* Source coverage trend */}
          <CoverageTrendChart data={data.coverage_trend || []} />

          <MetricSection
            question="Do we have data from all sources?"
            status={data.source_coverage.some((s: SourceCoverage) => s.odds_api === 0 && s.total > 0) ? "warning" : "good"}
            summary={`${data.source_coverage.length} sports tracked`}
            ideal="All expected sources reporting for each sport."
            action={data.source_coverage.some((s: SourceCoverage) => s.odds_api === 0 && s.total > 0)
              ? `Zero Odds API coverage for: ${data.source_coverage.filter((s: SourceCoverage) => s.odds_api === 0 && s.total > 0).map((s: SourceCoverage) => s.sport).join(", ") || "see the table below"}. Do this: check that sport's polling tier and the quota circuit breaker — a genuinely dark Odds API source means ingestion is dropping games, not a matching bug.`
              : undefined}
          >
          <SourceCoverageTable data={data.source_coverage} />
          <FuturesCoverageTable data={data.futures_coverage} />

          </MetricSection>

          <MetricSection
            question="Is our classification and grid data accurate?"
            status="good"
            summary="Classification and grid health"
            ideal="All markets classified. Grid accuracy above 95%."
          >
          <DataQualityCard secret={secret} />
          <GridHealthCard secret={secret} />

          </MetricSection>

          {/* PREQ Performance */}
          <PREQCard secret={secret} />

          <MetricSection
            question="Are all workers healthy?"
            status={data.worker.overall_health === "critical" ? "critical" : data.worker.overall_health !== "healthy" ? "warning" : "good"}
            summary={`${data.worker.critical_tasks.length} critical · ${data.worker.degraded_tasks.length} degraded`}
            ideal="All essential tasks running successfully every cycle."
            action={data.worker.critical_tasks.length > 0
              ? `Critical (no recent success): ${data.worker.critical_tasks.join(", ")}. Do this: check the Celery dashboard for the last error + a SIGKILL/soft-timeout (global task_time_limit=300, gotcha), and purge a backed-up queue if depth is high. The task table below shows last-run + success counts.`
              : data.worker.degraded_tasks.length > 0
                ? `Degraded (intermittent failures): ${data.worker.degraded_tasks.join(", ")}. Do this: check the task table below for each one's last error and success rate; a task run < once/24h is usually beat-schedule starvation, not a crash.`
                : undefined}
          >
          <TasksTable tasks={data.worker.tasks} />

          </MetricSection>

          {/* Monthly costs */}
          <ProjectCosts />
        </>
      )}
    </div>
  );
}

// --- Data Quality Card ---

interface DataQualityReport {
  status: string;
  timestamp?: string;
  period?: string;
  alerts?: string[];
  message?: string;
  checks?: {
    classification?: {
      total_markets_24h: number;
      tier_distribution: Record<string, number>;
      unclassified_count: number;
      unclassified_rate: number;
    };
    unclassified_samples?: { name: string; source: string }[];
    team_linking?: {
      total_outcomes: number;
      linked_outcomes: number;
      unlinked_rate: number;
      scope?: string;
      non_sport_markets?: number;
    };
    source_distribution?: Record<string, number>;
  };
}

function DataQualityCard({ secret }: { secret: string }) {
  const { data, error, mutate } = useSWR<DataQualityReport>(
    ["data-quality", secret],
    () =>
      adminFetch("/api/admin/data-quality", secret)
        .then((r) => r.json()),
    { refreshInterval: 300000 } // 5 min
  );

  const [checking, setChecking] = useState(false);

  const runCheck = async () => {
    setChecking(true);
    try {
      const r = await adminFetch(
        "/api/admin/data-quality/check",
        secret,
        { method: "POST" }
      );
      const report = await r.json();
      mutate(report, false);
    } finally {
      setChecking(false);
    }
  };

  if (error) return null;
  if (!data) return null;
  if (data.status === "no_data" && !data.checks) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-primary">Data Quality</h3>
          <span
            onClick={runCheck}
            className="text-micro px-2 py-1 rounded bg-surface-elevated border border-surface-border text-text-muted cursor-pointer hover:text-text-primary"
          >
            {checking ? "Checking..." : "Run Check"}
          </span>
        </div>
        <p className="text-xs text-text-muted">{data.message || "No report yet."}</p>
      </div>
    );
  }

  const cls = data.checks?.classification;
  const linking = data.checks?.team_linking;
  const samples = data.checks?.unclassified_samples || [];
  const statusHealth = data.status === "healthy" ? "healthy" : data.status === "warning" ? "warning" : data.status === "critical" ? "critical" : "healthy";

  return (
    <div className={"rounded-xl border p-4 " + healthBg(statusHealth)}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Data Quality
          <span className={"ml-2 text-micro font-normal " + healthColor(statusHealth)}>
            {statusHealth.toUpperCase()}
          </span>
        </h3>
        <div className="flex items-center gap-3">
          {data.timestamp && (
            <span className="text-micro text-text-muted">{timeAgo(data.timestamp)}</span>
          )}
          <span
            onClick={runCheck}
            className="text-micro px-2 py-1 rounded bg-surface-elevated border border-surface-border text-text-muted cursor-pointer hover:text-text-primary"
          >
            {checking ? "..." : "Refresh"}
          </span>
        </div>
      </div>

      {/* Alerts */}
      {data.alerts && data.alerts.length > 0 && (
        <div className="space-y-1 mb-3">
          {data.alerts.map((alert, i) => (
            <div key={i} className="text-xs p-2 rounded-lg bg-red-500/10 text-red-400">
              {alert}
            </div>
          ))}
        </div>
      )}

      {/* L2-129 Item 1 — action rule: a WARNING/CRITICAL status gets a where-to-look sentence. */}
      {statusHealth !== "healthy" && (
        <CardAction tone={statusHealth === "critical" ? "danger" : "warn"}>
          {cls && cls.unclassified_rate > 0.15
            ? `${(cls.unclassified_rate * 100).toFixed(1)}% of the last 24h of markets are unclassified`
            : "Classification/linking quality is degraded"}
          {" "}— unclassified markets don&rsquo;t land in the right category, feed, or grid. Do this: hit{" "}
          <strong>Copy backlog prompt</strong> below (it traces each sample to <code>sport_keys.py</code>{" "}
          KALSHI_TICKER_TO_SPORT_KEY / <code>compute_market_tier()</code>), then add the missing ticker
          prefix or name pattern. The alerts and sample rows here name the exact markets to fix.
        </CardAction>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {cls && (
          <>
            <div className="text-center">
              <div className="text-lg font-bold text-text-primary">{cls.total_markets_24h}</div>
              <div className="text-micro text-text-muted">Markets (24h)</div>
            </div>
            <div className="text-center">
              <div className={"text-lg font-bold " + (cls.unclassified_rate > 0.15 ? "text-yellow-400" : cls.unclassified_rate > 0.3 ? "text-red-400" : "text-green-400")}>
                {(cls.unclassified_rate * 100).toFixed(1)}%
              </div>
              <div className="text-micro text-text-muted">Unclassified</div>
            </div>
          </>
        )}
        {linking && (
          <div className="text-center">
            <div className={"text-lg font-bold " + (linking.unlinked_rate > 0.4 ? "text-yellow-400" : "text-green-400")}>
              {((1 - linking.unlinked_rate) * 100).toFixed(0)}%
            </div>
            <div className="text-micro text-text-muted">Sports Team Linked</div>
          </div>
        )}
      </div>

      {/* Non-sport context */}
      {linking?.non_sport_markets != null && linking.non_sport_markets > 0 && (
        <div className="text-micro text-text-muted mb-3 text-center">
          {linking.non_sport_markets.toLocaleString()} non-sport markets excluded from linking metric
        </div>
      )}

      {/* Tier distribution */}
      {cls && (
        <div className="mb-3">
          <div className="text-micro text-text-muted mb-1">Tier Distribution</div>
          <div className="flex gap-1 h-4 rounded overflow-hidden">
            {["1", "2", "3", "4", "5"].map((tier) => {
              const count = cls.tier_distribution[tier] || 0;
              const pct = cls.total_markets_24h > 0 ? (count / cls.total_markets_24h) * 100 : 0;
              if (pct < 1) return null;
              const colors: Record<string, string> = {
                "1": "bg-green-500",
                "2": "bg-blue-500",
                "3": "bg-purple-500",
                "4": "bg-yellow-500",
                "5": "bg-red-400",
              };
              return (
                <div
                  key={tier}
                  className={colors[tier] + " relative group"}
                  style={{ width: pct + "%" }}
                  title={"Tier " + tier + ": " + count + " (" + pct.toFixed(0) + "%)"}
                >
                  <span className="absolute inset-0 flex items-center justify-center text-micro text-white font-medium opacity-0 group-hover:opacity-100">
                    T{tier}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex gap-3 mt-1 text-micro text-text-muted">
            <span><span className="inline-block w-2 h-2 rounded-sm bg-green-500 mr-0.5" />Championship</span>
            <span><span className="inline-block w-2 h-2 rounded-sm bg-blue-500 mr-0.5" />Conference</span>
            <span><span className="inline-block w-2 h-2 rounded-sm bg-purple-500 mr-0.5" />Award</span>
            <span><span className="inline-block w-2 h-2 rounded-sm bg-yellow-500 mr-0.5" />Division</span>
            <span><span className="inline-block w-2 h-2 rounded-sm bg-red-400 mr-0.5" />Other</span>
          </div>
        </div>
      )}

      {/* Unclassified samples */}
      {samples.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <div className="text-micro text-text-muted">Unclassified Markets (sample)</div>
            <span
              onClick={() => {
                const lines = samples.map((s) => `- "${s.name}" (${s.source})`).join("\n");
                const guesses = samples.map((s) => {
                  const n = s.name.toLowerCase();
                  if (/total|spread|over|under|half|quarter|inning|first \d|f5/i.test(s.name))
                    return { ...s, guess: "Game prop — needs is_game_prop() pattern or ticker prefix mapping" };
                  if (/map|round|game \d|match/i.test(s.name))
                    return { ...s, guess: "Esports match prop — needs esports event source or manual sport tagging" };
                  if (/double|triple|hit|strikeout|run|home run|foul/i.test(s.name))
                    return { ...s, guess: "Player/team stat prop — needs stat-type classification in compute_market_tier()" };
                  if (/vs\.?|at /i.test(s.name) && !/will|release/i.test(s.name))
                    return { ...s, guess: "Game matchup — likely missing from KALSHI_TICKER_TO_SPORT_KEY or Polymarket sport detection" };
                  if (/champion|winner|mvp|award|playoff/i.test(s.name))
                    return { ...s, guess: "Season futures — needs llm_sport_category assignment or ticker mapping" };
                  return { ...s, guess: "Non-sport or novel market — may need new category or manual exclusion" };
                });
                const analysis = guesses.map((g) => `- "${g.name}" (${g.source})\n  → ${g.guess}`).join("\n");
                const prompt = `## Unclassified Markets Analysis\n\nThe admin dashboard shows ${cls?.unclassified_count ?? samples.length} unclassified markets (${((cls?.unclassified_rate ?? 0) * 100).toFixed(1)}% of 24h intake). Here are samples with suspected root causes:\n\n${analysis}\n\n### Suggested fixes:\n1. Review \`utils/sport_keys.py\` KALSHI_TICKER_TO_SPORT_KEY for missing ticker prefixes\n2. Review \`tasks/kalshi.py\` _categorize_kalshi_market() for name patterns that should match\n3. Review \`utils/market_label_normalization.py\` compute_market_tier() for unhandled market types\n4. Check if any are non-sport markets that should be added to _NON_SPORT_CATEGORIES\n\nPlease investigate each sample, trace the classification path, and add fixes to the backlog.`;
                navigator.clipboard.writeText(prompt);
                alert("Copied analysis prompt to clipboard!");
              }}
              className="text-micro px-2 py-1 rounded bg-accent-futures/10 text-accent-futures cursor-pointer hover:bg-accent-futures/20 transition-colors"
            >
              📋 Copy backlog prompt
            </span>
          </div>
          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {samples.map((s, i) => {
              let guess = "";
              if (/total|spread|over|under|half|quarter|inning|first \d|f5/i.test(s.name))
                guess = "game prop";
              else if (/map|round|game \d|match/i.test(s.name))
                guess = "esports";
              else if (/double|triple|hit|strikeout|run|home run|foul/i.test(s.name))
                guess = "stat prop";
              else if (/vs\.?|at /i.test(s.name) && !/will|release/i.test(s.name))
                guess = "matchup";
              else if (/champion|winner|mvp|award|playoff/i.test(s.name))
                guess = "season futures";
              else
                guess = "non-sport?";
              return (
                <div key={i} className="flex items-center text-xs py-0.5 gap-2">
                  <span className="text-text-secondary flex-1 truncate" title={s.name}>{s.name}</span>
                  <span className="text-micro px-1.5 py-0.5 rounded bg-surface-elevated text-text-muted shrink-0">{guess}</span>
                  <span className="text-micro text-text-muted shrink-0">{s.source}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


// --- Grid Health (audit scores) ---

interface GridAuditResult {
  scores: Record<string, number>;
  avg_score: number | null;
  fetched_at?: string;
  grids: Record<string, {
    health_score?: number;
    findings?: { check: string; severity: string; description: string; details?: Record<string, unknown> }[];
    status?: string;
    error?: string;
  }>;
}

function GridHealthCard({ secret }: { secret: string }) {
  const { data, error, mutate } = useSWR<GridAuditResult>(
    ["grid-health", secret],
    () =>
      adminFetch("/api/admin/audit/all", secret)
        .then((r) => r.json()),
    { refreshInterval: 600000 } // 10 min
  );

  const [checking, setChecking] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);

  // Track when data was fetched
  if (data && !fetchedAt) {
    setFetchedAt(new Date().toISOString());
  }

  const refresh = async () => {
    setChecking(true);
    try {
      const r = await adminFetch(
        "/api/admin/audit/all",
        secret
      );
      const report = await r.json();
      mutate(report, false);
      setFetchedAt(new Date().toISOString());
    } finally {
      setChecking(false);
    }
  };

  if (error) return null;

  const scoreColor = (s: number) =>
    s >= 90 ? "text-green-400" : s >= 70 ? "text-yellow-400" : "text-red-400";
  const scoreBg = (s: number) =>
    s >= 90 ? "border-green-500/20" : s >= 70 ? "border-yellow-500/20" : "border-red-500/20";
  const severityIcon = (s: string) =>
    s === "critical" ? "🔴" : s === "warning" ? "🟡" : "🔵";

  const allFindings = data?.grids
    ? Object.entries(data.grids).flatMap(([grid, v]) =>
        (v.findings || []).map((f) => ({ ...f, grid }))
      )
    : [];

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Grid Health
          {data?.avg_score != null && (
            <span className={"ml-2 text-sm font-bold " + scoreColor(data.avg_score)}>
              {data.avg_score}/100
            </span>
          )}
        </h3>
        <div className="flex items-center gap-3">
          {fetchedAt && !checking && (
            <span className="text-micro text-text-muted">{timeAgo(fetchedAt)}</span>
          )}
          <span
            onClick={refresh}
            className={"text-micro px-2 py-1 rounded bg-surface-elevated border border-surface-border cursor-pointer hover:text-text-primary transition-colors " + (checking ? "text-accent-brand animate-pulse" : "text-text-muted")}
          >
            {checking ? "Auditing…" : data ? "Refresh" : "Run Audit"}
          </span>
        </div>
      </div>

      {!data && !checking && (
        <p className="text-xs text-text-muted">Click &quot;Run Audit&quot; to check grid health across all leagues.</p>
      )}
      {checking && !data && (
        <p className="text-xs text-text-muted animate-pulse">Running audit across NBA, NHL, MLB, Golf...</p>
      )}

      {data?.scores && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          {["nba", "nhl", "mlb", "golf"].map((g) => {
            const score = data.scores[g];
            if (score == null) return (
              <div key={g} className="text-center p-2 rounded border border-surface-border">
                <div className="text-xs font-bold text-text-muted uppercase">{g}</div>
                <div className="text-sm text-text-muted">—</div>
              </div>
            );
            return (
              <a key={g} href={"/playoffs/" + g} className={"text-center p-2 rounded border " + scoreBg(score) + " hover:bg-surface-elevated transition-colors"}>
                <div className="text-xs font-bold text-text-muted uppercase">{g}</div>
                <div className={"text-lg font-bold " + scoreColor(score)}>{score}</div>
              </a>
            );
          })}
        </div>
      )}

      {/* Show findings for any grid scoring below 90 */}
      {data?.grids && Object.entries(data.grids)
        .filter(([, v]) => (v.findings?.length ?? 0) > 0)
        .map(([grid, v]) => (
          <div key={grid} className="mb-2">
            <div className="text-micro font-semibold text-text-secondary uppercase mb-1">{grid} findings</div>
            <div className="space-y-0.5 max-h-32 overflow-y-auto">
              {v.findings!.slice(0, 8).map((f, i) => (
                <div key={i} className="text-xs text-text-muted flex gap-1.5">
                  <span className="shrink-0">{severityIcon(f.severity)}</span>
                  <span className="truncate" title={f.description}>{f.description}</span>
                </div>
              ))}
              {(v.findings!.length > 8) && (
                <div className="text-micro text-text-muted">+{v.findings!.length - 8} more</div>
              )}
            </div>
          </div>
        ))
      }

      {/* L2-129 Item 1 — action rule, honest to CLAUDE.md: a sub-90 raw score is
          NOT proof of a defect (this score cried wolf before the Grid Sentinel). */}
      {data?.avg_score != null && data.avg_score < 90 && (
        <CardAction tone={data.avg_score < 70 ? "danger" : "warn"}>
          Score <strong>{data.avg_score}/100</strong> — but a sub-90 raw score is not itself a defect.
          The Grid Sentinel classifies each finding as REAL (monotonicity, over-100% sums, empty/stale
          grid), EXPLAINED (a season-window artifact), or WATCH (source disagreement — blend-hidden,
          never RED). Do this: read the findings above and the Grid tile on the cockpit for the verdict;
          only a REAL finding warrants an issue. Blend-hidden Kalshi/Polymarket disagreement is expected
          here, not actionable.
        </CardAction>
      )}

      {/* Generate backlog prompt button */}
      {allFindings.length > 0 && (
        <div className="mt-2 pt-2 border-t border-surface-border flex justify-end">
          <span
            onClick={() => {
              const scores = data?.scores
                ? Object.entries(data.scores).map(([g, s]) => `- ${g.toUpperCase()}: ${s}/100`).join("\n")
                : "";
              const findingsList = allFindings
                .map((f) => `- [${f.severity.toUpperCase()}] ${f.grid.toUpperCase()}: ${f.description}`)
                .join("\n");
              const prompt = `## Grid Health Audit Findings\n\nOverall score: ${data?.avg_score ?? "?"}/100\n\nPer-grid scores:\n${scores}\n\n### Findings (${allFindings.length} total):\n${findingsList}\n\n### Action requested:\nFor each finding above:\n1. Identify the root cause in the backend code (likely in \`routes/playoffs.py\`, \`config/league_configs.py\`, or \`tasks/prediction_market_matching.py\`)\n2. Determine if it's a real data issue, a classification bug, or expected behavior\n3. For real issues, add a fix to the backlog with file paths and suggested approach\n4. For source disagreements (e.g., Polymarket vs Kalshi), note whether it's a data freshness issue or a genuine coverage gap`;
              navigator.clipboard.writeText(prompt);
              alert("Copied grid health prompt to clipboard!");
            }}
            className="text-micro px-2 py-1 rounded bg-accent-futures/10 text-accent-futures cursor-pointer hover:bg-accent-futures/20 transition-colors"
          >
            📋 Copy backlog prompt
          </span>
        </div>
      )}
    </div>
  );
}

// --- PREQ Performance Card ---

interface HealthReadyResponse {
  status: string;
  checks: {
    database?: string;
    redis?: string;
    last_polls?: Record<string, string | null>;
    odds_api?: Record<string, unknown>;
  };
}

function PREQCard({ secret }: { secret: string }) {
  const [latencies, setLatencies] = useState<Record<string, number | null>>({});
  const [measuring, setMeasuring] = useState(false);
  const [cacheStatus, setCacheStatus] = useState<Record<string, string>>({});
  const { data: healthData } = useSWR<HealthReadyResponse>(
    "health-ready",
    () => fetch(API_URL + "/health/ready").then((r) => r.json()),
    { refreshInterval: 300000 }
  );

  const measureLatency = async () => {
    setMeasuring(true);
    const endpoints = [
      { name: "Feed", path: "/api/feed?limit=10" },
      { name: "Events", path: "/api/sports" },
      { name: "Playoffs", path: "/api/playoffs/nba" },
      { name: "Golf", path: "/api/golf" },
      { name: "Health", path: "/health/ready" },
    ];
    const results: Record<string, number | null> = {};
    const cache: Record<string, string> = {};
    for (const ep of endpoints) {
      try {
        const res = await fetch(API_URL + ep.path);
        const rt = res.headers.get("X-Response-Time");
        results[ep.name] = rt ? parseInt(rt) : null;
        const cc = res.headers.get("Cache-Control");
        cache[ep.name] = cc || "none";
      } catch {
        results[ep.name] = null;
      }
    }
    setLatencies(results);
    setCacheStatus(cache);
    setMeasuring(false);
  };

  const latencyColor = (ms: number | null) => {
    if (ms === null) return "text-text-muted";
    if (ms < 200) return "text-green-400";
    if (ms < 500) return "text-yellow-400";
    return "text-red-400";
  };

  const polls = healthData?.checks?.last_polls;

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          PREQ Performance
          {healthData && (
            <span className={"ml-2 text-micro font-normal " + (healthData.checks?.redis === "ok" ? "text-green-400" : "text-red-400")}>
              {healthData.status === "ready" ? "ALL HEALTHY" : "DEGRADED"}
            </span>
          )}
        </h3>
        <span
          onClick={measureLatency}
          className={"text-micro px-2 py-1 rounded bg-surface-elevated border border-surface-border cursor-pointer hover:text-text-primary transition-colors " + (measuring ? "text-accent-brand animate-pulse" : "text-text-muted")}
        >
          {measuring ? "Measuring…" : Object.keys(latencies).length > 0 ? "Re-measure" : "Measure Latency"}
        </span>
      </div>

      {/* Infrastructure status */}
      {healthData && (
        <div className="flex gap-4 mb-3 text-xs">
          <span className="flex items-center gap-1">
            <span className={"w-2 h-2 rounded-full " + (healthData.checks?.database === "ok" ? "bg-green-400" : "bg-red-400")} />
            DB
          </span>
          <span className="flex items-center gap-1">
            <span className={"w-2 h-2 rounded-full " + (healthData.checks?.redis === "ok" ? "bg-green-400" : "bg-red-400")} />
            Redis
          </span>
          {healthData.checks?.odds_api && (
            <span className="flex items-center gap-1">
              <span className={"w-2 h-2 rounded-full " + ((healthData.checks.odds_api as Record<string, string>).status === "ok" ? "bg-green-400" : "bg-yellow-400")} />
              Odds API
            </span>
          )}
        </div>
      )}

      {/* L2-129 Item 1 — action rule: a DEGRADED badge names the culprit + what it breaks. */}
      {healthData && healthData.status !== "ready" && (
        <CardAction tone="danger">
          Infra reports <strong>DEGRADED</strong> —{" "}
          {healthData.checks?.redis !== "ok"
            ? "Redis isn't OK, which freezes Celery beats + caching (feed latency spikes and no-timeout clients can hang a task loop, gotcha #39)"
            : healthData.checks?.database !== "ok"
              ? "the database isn't OK, which blocks every read/write path"
              : "a health check isn't OK"}
          . Do this: check the Heroku add-on and worker dynos for the red dot above; the DB/Redis/Odds-API
          dots and last-poll times show which source is stale. Source: <code>/health/ready</code>.
        </CardAction>
      )}

      {/* Latency measurements */}
      {Object.keys(latencies).length > 0 && (
        <div className="mb-3">
          <div className="text-micro text-text-muted mb-1">Endpoint Latency</div>
          <div className="space-y-1">
            {Object.entries(latencies).map(([name, ms]) => (
              <div key={name} className="flex items-center gap-2 text-xs">
                <span className="w-16 text-text-muted">{name}</span>
                <div className="flex-1 h-3 bg-surface-elevated rounded-full overflow-hidden">
                  <div
                    className={"h-full rounded-full " + (ms !== null && ms < 200 ? "bg-green-500/60" : ms !== null && ms < 500 ? "bg-yellow-500/60" : "bg-red-500/60")}
                    style={{ width: ms !== null ? Math.min(100, (ms / 1000) * 100) + "%" : "2%" }}
                  />
                </div>
                <span className={"w-14 text-right font-mono " + latencyColor(ms)}>
                  {ms !== null ? ms + "ms" : "err"}
                </span>
                <span className="w-16 text-right text-micro text-text-muted truncate" title={cacheStatus[name]}>
                  {cacheStatus[name]?.includes("max-age") ? "cached" : "no-cache"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last poll timestamps */}
      {polls && (
        <div>
          <div className="text-micro text-text-muted mb-1">Last Source Polls</div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-1 text-xs">
            {Object.entries(polls).map(([source, ts]) => (
              <div key={source} className="flex items-center gap-1.5">
                <span className={"w-2 h-2 rounded-full " + (ts ? "bg-green-400" : "bg-text-muted")} />
                <span className="text-text-muted capitalize">{source.replace("_", " ")}</span>
                <span className="text-text-muted ml-auto">{ts ? timeAgo(ts) : "—"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!healthData && Object.keys(latencies).length === 0 && (
        <p className="text-xs text-text-muted">Click &quot;Measure Latency&quot; to benchmark endpoint response times.</p>
      )}
    </div>
  );
}


// --- Project Costs ---

interface CostItem {
  name: string;
  category: "infrastructure" | "data" | "ai" | "services";
  monthly: number;
  note?: string;
  variable?: boolean;
}

const PROJECT_COSTS: CostItem[] = [
  { name: "Web dyno (Standard-1X)", category: "infrastructure", monthly: 25 },
  { name: "Scheduler dyno (Standard-1X)", category: "infrastructure", monthly: 25 },
  { name: "Worker-background (Standard-1X)", category: "infrastructure", monthly: 25 },
  { name: "Worker-realtime (Standard-2X)", category: "infrastructure", monthly: 50 },
  { name: "PostgreSQL (Standard-0)", category: "infrastructure", monthly: 50, note: "64 GB" },
  { name: "Redis (Premium-0)", category: "infrastructure", monthly: 15 },
  { name: "Domain (bainluck.com)", category: "infrastructure", monthly: 1, note: "~$12/year" },
  { name: "The Odds API", category: "data", monthly: 119, note: "5M requests/mo quota", variable: true },
  { name: "StatPal API", category: "data", monthly: 99, note: "300K requests/day" },
  { name: "DataGolf API", category: "data", monthly: 30, note: "Golf predictions + live" },
  { name: "OpenAI (GPT-4o-mini)", category: "ai", monthly: 5, note: "LLM classification", variable: true },
  { name: "Vercel (Frontend)", category: "services", monthly: 0, note: "Free tier" },
  { name: "Firebase Auth", category: "services", monthly: 0, note: "Free tier" },
  { name: "Google Analytics 4", category: "services", monthly: 0, note: "Free" },
  { name: "ESPN API", category: "services", monthly: 0, note: "Free (undocumented)" },
  { name: "MLB Stats API", category: "services", monthly: 0, note: "Free" },
  { name: "Kalshi API", category: "services", monthly: 0, note: "Free (API key)" },
  { name: "Polymarket API", category: "services", monthly: 0, note: "Free (no key)" },
  { name: "TMDB API", category: "services", monthly: 0, note: "Free (Oscars posters)" },
  { name: "Apple Developer Program", category: "services", monthly: 8.25, note: "$99/year for TestFlight" },
];

const CATEGORY_LABELS: Record<string, string> = {
  infrastructure: "Infrastructure (Heroku)",
  data: "Data Providers",
  ai: "AI / LLM",
  services: "Other Services",
};

const CATEGORY_COLORS: Record<string, string> = {
  infrastructure: "bg-blue-500",
  data: "bg-emerald-500",
  ai: "bg-purple-500",
  services: "bg-text-muted",
};

function ProjectCosts() {
  const total = PROJECT_COSTS.reduce((s, c) => s + c.monthly, 0);
  const byCategory = PROJECT_COSTS.reduce<Record<string, { items: CostItem[]; subtotal: number }>>((acc, item) => {
    if (!acc[item.category]) acc[item.category] = { items: [], subtotal: 0 };
    acc[item.category].items.push(item);
    acc[item.category].subtotal += item.monthly;
    return acc;
  }, {});

  const paidTotal = PROJECT_COSTS.filter(c => c.monthly > 0).reduce((s, c) => s + c.monthly, 0);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">Monthly Project Costs</h3>
        <div className="text-right">
          <span className="text-2xl font-bold text-text-primary">${total.toFixed(0)}</span>
          <span className="text-xs text-text-muted ml-1">/month</span>
        </div>
      </div>

      <div className="h-4 bg-surface-border rounded-full overflow-hidden flex mb-3">
        {["infrastructure", "data", "ai"].map(cat => {
          const pct = byCategory[cat] ? (byCategory[cat].subtotal / paidTotal) * 100 : 0;
          if (pct <= 0) return null;
          return (
            <div
              key={cat}
              className={"h-full " + CATEGORY_COLORS[cat]}
              style={{ width: pct + "%" }}
              title={CATEGORY_LABELS[cat] + ": $" + (byCategory[cat]?.subtotal || 0)}
            />
          );
        })}
      </div>

      <div className="flex gap-4 mb-4 text-micro text-text-muted">
        {["infrastructure", "data", "ai"].map(cat => (
          <div key={cat} className="flex items-center gap-1">
            <span className={"inline-block w-2.5 h-2.5 rounded-sm " + CATEGORY_COLORS[cat]} />
            {CATEGORY_LABELS[cat]} (${byCategory[cat]?.subtotal || 0})
          </div>
        ))}
      </div>

      <div className="space-y-4">
        {["infrastructure", "data", "ai", "services"].map(cat => {
          const group = byCategory[cat];
          if (!group) return null;
          return (
            <div key={cat}>
              <div className="text-micro text-text-muted uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                <span className={"inline-block w-2 h-2 rounded-sm " + CATEGORY_COLORS[cat]} />
                {CATEGORY_LABELS[cat]}
                <span className="ml-auto font-semibold">${group.subtotal.toFixed(0)}</span>
              </div>
              <div className="space-y-0.5">
                {group.items.map(item => (
                  <div key={item.name} className="flex items-center text-xs py-0.5">
                    <span className="text-text-secondary flex-1">{item.name}</span>
                    {item.note && <span className="text-text-muted text-micro mr-3 hidden sm:inline">{item.note}</span>}
                    <span className={"font-medium tabular-nums " + (item.monthly > 0 ? "text-text-primary" : "text-green-600")}>
                      {item.monthly > 0 ? "$" + item.monthly.toFixed(0) : "Free"}
                    </span>
                    {item.variable && <span className="text-micro text-text-muted ml-1">~</span>}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 border-t border-surface-border flex justify-between text-xs text-text-muted">
        <span>Annual projection</span>
        <span className="font-semibold text-text-primary">${(total * 12).toFixed(0)}/year</span>
      </div>
    </div>
  );
}
