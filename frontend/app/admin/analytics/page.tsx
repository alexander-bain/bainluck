"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import PageHeader from "@/components/admin/PageHeader";
import MetricSection from "@/components/admin/MetricSection";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types ---

interface EngagementSummary {
  totalUsers: number;
  totalSessions: number;
  totalPageViews: number;
  avgDailyUsers: number;
  avgSessionDuration: number;
  avgBounceRate: number;
}

interface DailyEngagement {
  date: string;
  activeUsers: string;
  sessions: string;
  averageSessionDuration: string;
  bounceRate: string;
  screenPageViews: string;
  engagedSessions: string;
}

interface OverviewData {
  period: string;
  engagement: {
    summary: EngagementSummary;
    daily: DailyEngagement[];
  };
  topPages: Array<{
    pagePath: string;
    screenPageViews: string;
    activeUsers: string;
    averageSessionDuration: string;
  }>;
}

interface DiscoverEvent {
  eventName: string;
  eventCount: string;
  totalUsers: string;
}

interface DiscoverData {
  period: string;
  discoverPages: Array<{
    pagePath: string;
    screenPageViews: string;
    activeUsers: string;
  }>;
  discoverEvents: DiscoverEvent[];
  dailyTrend: Array<{
    date: string;
    screenPageViews: string;
    activeUsers: string;
  }>;
}

interface FunnelStep {
  stage: string;
  events: number;
  users: number;
  conversionRate: number;
}

interface FunnelEvent {
  eventName: string;
  stage: string;
  eventCount: number;
  totalUsers: number;
}

interface FunnelData {
  period: string;
  funnel: FunnelStep[];
  eventBreakdown: FunnelEvent[];
  dailyTrend: Array<{
    date: string;
    visit: number;
    interact: number;
    guess: number;
    signup: number;
  }>;
  byDevice: Array<{
    device: string;
    visit: number;
    interact: number;
    guess: number;
    signup: number;
  }>;
}

interface RetentionDay {
  date: string;
  new: number;
  returning: number;
  newSessions: number;
  returningSessions: number;
}

interface RetentionData {
  period: string;
  summary: {
    totalNewUsers: number;
    totalReturningUsers: number;
    retentionRate: number;
  };
  daily: RetentionDay[];
}

interface RealtimeData {
  activeUsers: number;
  topActivePages: Array<{
    page: string;
    activeUsers: number;
  }>;
}

interface PageRow {
  path: string;
  section: string;
  views: number;
  users: number;
  avgDuration: number;
  bounceRate: number;
  engagedSessions: number;
}

interface SectionSummary {
  section: string;
  views: number;
  users: number;
  engagedSessions: number;
  pageCount: number;
}

interface PagesData {
  period: string;
  pages: PageRow[];
  sections: SectionSummary[];
  dailyBySection: Array<Record<string, string | number>>;
}

// --- Helpers ---

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return Math.round(seconds) + "s";
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return mins + "m " + secs + "s";
}

function formatDate(dateStr: string): string {
  // YYYYMMDD or YYYY-MM-DD -> MM/DD
  const clean = dateStr.replace(/-/g, "");
  if (clean.length === 8) {
    return clean.slice(4, 6) + "/" + clean.slice(6, 8);
  }
  return dateStr.slice(5);
}

const STAGE_LABELS: Record<string, string> = {
  visit: "Visit",
  interact: "Interact",
  guess: "Guess",
  signup: "Sign Up",
};

const STAGE_COLORS: Record<string, string> = {
  visit: "#3b82f6",
  interact: "#f59e0b",
  guess: "#22c55e",
  signup: "#8b5cf6",
};

const SECTION_COLORS: Record<string, string> = {
  discover: "#3b82f6",
  sports: "#22c55e",
  weather: "#06b6d4",
  politics: "#ef4444",
  entertainment: "#f59e0b",
  economics: "#8b5cf6",
  futures: "#ec4899",
  calibration: "#6366f1",
  teams: "#14b8a6",
  admin: "#6b7280",
  other: "#9ca3af",
};

// --- Stat Card ---

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="text-[10px] text-text-muted uppercase tracking-wider">
        {label}
      </div>
      <div className="text-2xl font-bold text-text-primary mt-1">{value}</div>
      {sub && <div className="text-xs text-text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

// --- Tab components ---

function OverviewTab({
  data,
  pagesData,
}: {
  data: OverviewData;
  pagesData: PagesData | undefined;
}) {
  const { summary, daily } = data.engagement;

  const chartData = useMemo(
    () =>
      daily.map((d) => ({
        date: formatDate(d.date),
        users: parseInt(d.activeUsers),
        sessions: parseInt(d.sessions),
        pageViews: parseInt(d.screenPageViews),
        duration: parseFloat(d.averageSessionDuration),
        bounce: parseFloat(d.bounceRate) * 100,
      })),
    [daily]
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Total Users"
          value={formatNum(summary.totalUsers)}
          sub={formatNum(summary.avgDailyUsers) + " daily avg"}
        />
        <StatCard
          label="Total Sessions"
          value={formatNum(summary.totalSessions)}
        />
        <StatCard
          label="Avg Session Duration"
          value={formatDuration(summary.avgSessionDuration)}
        />
        <StatCard
          label="Bounce Rate"
          value={summary.avgBounceRate + "%"}
          sub="Lower is better"
        />
      </div>

      <MetricSection
        question="How are daily active users trending?"
        status="good"
        summary={formatNum(summary.avgDailyUsers) + " daily avg"}
        ideal="Growing or stable DAU trend."
        defaultExpanded
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(1, Math.floor(chartData.length / 8))}
              />
              <YAxis tick={{ fontSize: 10, fill: "#888" }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="users"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="Users"
              />
              <Line
                type="monotone"
                dataKey="sessions"
                stroke="#22c55e"
                strokeWidth={1.5}
                dot={false}
                name="Sessions"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>

      <MetricSection
        question="Which pages get the most traffic?"
        status="good"
        summary={data.topPages.length + " pages tracked"}
        ideal="Discover and event detail pages leading."
        defaultExpanded
      >
        {pagesData && pagesData.sections.length > 0 && (
          <div className="mb-4">
            <h4 className="text-xs font-semibold text-text-primary mb-2">
              Traffic by Section
            </h4>
            <div className="space-y-1.5">
              {pagesData.sections.map((s) => {
                const maxViews = pagesData.sections[0]?.views || 1;
                const pct = Math.round((s.views / maxViews) * 100);
                return (
                  <div key={s.section} className="flex items-center gap-2">
                    <span className="text-xs text-text-secondary w-24 text-right capitalize">
                      {s.section}
                    </span>
                    <div className="flex-1 h-4 bg-surface-elevated rounded overflow-hidden">
                      <div
                        className="h-full rounded transition-all"
                        style={{
                          width: pct + "%",
                          backgroundColor:
                            SECTION_COLORS[s.section] || "#9ca3af",
                        }}
                      />
                    </div>
                    <span className="text-xs text-text-muted w-16 text-right">
                      {formatNum(s.views)}
                    </span>
                    <span className="text-xs text-text-muted w-14 text-right">
                      {formatNum(s.users)} u
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Page
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Views
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Users
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Avg Duration
                </th>
              </tr>
            </thead>
            <tbody>
              {data.topPages.slice(0, 25).map((page) => (
                <tr
                  key={page.pagePath}
                  className="border-b border-surface-border/50 hover:bg-surface-elevated/30"
                >
                  <td className="py-1.5 px-2 font-mono text-text-secondary truncate max-w-[300px]">
                    {page.pagePath}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-primary font-medium">
                    {formatNum(parseInt(page.screenPageViews))}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {formatNum(parseInt(page.activeUsers))}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {formatDuration(parseFloat(page.averageSessionDuration))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </MetricSection>
    </div>
  );
}

function DiscoverTab({ data }: { data: DiscoverData }) {
  const dailyChartData = useMemo(
    () =>
      data.dailyTrend.map((d) => ({
        date: formatDate(d.date),
        views: parseInt(d.screenPageViews),
        users: parseInt(d.activeUsers),
      })),
    [data.dailyTrend]
  );

  const eventRows = useMemo(
    () =>
      data.discoverEvents
        .map((e) => ({
          name: e.eventName,
          count: parseInt(e.eventCount),
          users: parseInt(e.totalUsers),
        }))
        .sort((a, b) => b.count - a.count),
    [data.discoverEvents]
  );

  const totalEvents = useMemo(
    () => eventRows.reduce((s, e) => s + e.count, 0),
    [eventRows]
  );
  const totalUsers = useMemo(
    () => Math.max(...eventRows.map((e) => e.users), 0),
    [eventRows]
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Discover Events"
          value={formatNum(totalEvents)}
          sub={data.period + " period"}
        />
        <StatCard
          label="Unique Users"
          value={formatNum(totalUsers)}
          sub="Interacted with Discover"
        />
        <StatCard
          label="Event Types"
          value={String(eventRows.length)}
          sub="Distinct event names tracked"
        />
        <StatCard
          label="Discover Pages"
          value={String(data.discoverPages.length)}
          sub="Pages with Discover traffic"
        />
      </div>

      <MetricSection
        question="How is Discover traffic trending?"
        status="good"
        summary={formatNum(totalUsers) + " users"}
        ideal="Steady or growing daily Discover engagement."
        defaultExpanded
      >
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={dailyChartData}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(1, Math.floor(dailyChartData.length / 8))}
              />
              <YAxis tick={{ fontSize: 10, fill: "#888" }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Area
                type="monotone"
                dataKey="users"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.15}
                strokeWidth={2}
                name="Users"
              />
              <Area
                type="monotone"
                dataKey="views"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.08}
                strokeWidth={1.5}
                name="Page Views"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>

      <MetricSection
        question="Which Discover events fire most?"
        status="good"
        summary={eventRows.length + " event types"}
        ideal="Card views and swipes dominating, with healthy guess completion."
        defaultExpanded
      >
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Event
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Count
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Users
                </th>
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Distribution
                </th>
              </tr>
            </thead>
            <tbody>
              {eventRows.map((e) => {
                const pct =
                  totalEvents > 0
                    ? Math.round((e.count / totalEvents) * 100)
                    : 0;
                return (
                  <tr
                    key={e.name}
                    className="border-b border-surface-border/50 hover:bg-surface-elevated/30"
                  >
                    <td className="py-1.5 px-2 font-mono text-text-secondary">
                      {e.name}
                    </td>
                    <td className="py-1.5 px-2 text-right text-text-primary font-medium">
                      {formatNum(e.count)}
                    </td>
                    <td className="py-1.5 px-2 text-right text-text-muted">
                      {formatNum(e.users)}
                    </td>
                    <td className="py-1.5 px-2">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-surface-elevated rounded-full overflow-hidden max-w-[120px]">
                          <div
                            className="h-full bg-accent-brand/60 rounded-full"
                            style={{ width: Math.max(2, pct) + "%" }}
                          />
                        </div>
                        <span className="text-text-muted w-8 text-right">
                          {pct}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </MetricSection>
    </div>
  );
}

function FunnelTab({ data }: { data: FunnelData }) {
  const dailyChartData = useMemo(
    () =>
      data.dailyTrend.map((d) => ({
        ...d,
        date: formatDate(d.date),
      })),
    [data.dailyTrend]
  );

  return (
    <div className="space-y-4">
      {/* Funnel visualization */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-4">
          Conversion Funnel
        </h3>
        <div className="space-y-2">
          {data.funnel.map((step, i) => {
            const maxUsers = data.funnel[0]?.users || 1;
            const widthPct = Math.max(
              8,
              Math.round((step.users / maxUsers) * 100)
            );
            return (
              <div key={step.stage} className="flex items-center gap-3">
                <span className="text-xs text-text-secondary w-16 text-right font-medium">
                  {STAGE_LABELS[step.stage] || step.stage}
                </span>
                <div className="flex-1 relative">
                  <div
                    className="h-10 rounded-lg flex items-center px-3 transition-all"
                    style={{
                      width: widthPct + "%",
                      backgroundColor: STAGE_COLORS[step.stage] || "#888",
                      opacity: 0.8,
                    }}
                  >
                    <span className="text-xs font-bold text-white">
                      {formatNum(step.users)} users
                    </span>
                  </div>
                </div>
                <div className="w-20 text-right">
                  {i > 0 ? (
                    <span
                      className={
                        "text-xs font-medium " +
                        (step.conversionRate >= 50
                          ? "text-green-600"
                          : step.conversionRate >= 20
                          ? "text-yellow-600"
                          : "text-red-600")
                      }
                    >
                      {step.conversionRate}%
                    </span>
                  ) : (
                    <span className="text-xs text-text-muted">100%</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-[10px] text-text-muted mt-3">
          Conversion rates show drop-off between each stage.
        </p>
      </div>

      {/* Device breakdown */}
      {data.byDevice.length > 0 && (
        <MetricSection
          question="How does the funnel differ by device?"
          status="good"
          summary={data.byDevice.length + " device types"}
          ideal="Mobile and desktop funnels both healthy."
          defaultExpanded
        >
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-surface-border">
                  <th className="text-left py-2 px-2 text-text-muted font-medium">
                    Device
                  </th>
                  {Object.keys(STAGE_LABELS).map((stage) => (
                    <th
                      key={stage}
                      className="text-right py-2 px-2 text-text-muted font-medium"
                    >
                      {STAGE_LABELS[stage]}
                    </th>
                  ))}
                  <th className="text-right py-2 px-2 text-text-muted font-medium">
                    Conv %
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.byDevice.map((d) => {
                  const conv =
                    d.visit > 0
                      ? Math.round((d.interact / d.visit) * 100)
                      : 0;
                  return (
                    <tr
                      key={d.device}
                      className="border-b border-surface-border/50"
                    >
                      <td className="py-1.5 px-2 text-text-secondary capitalize font-medium">
                        {d.device}
                      </td>
                      <td className="py-1.5 px-2 text-right text-text-primary">
                        {formatNum(d.visit)}
                      </td>
                      <td className="py-1.5 px-2 text-right text-text-primary">
                        {formatNum(d.interact)}
                      </td>
                      <td className="py-1.5 px-2 text-right text-text-primary">
                        {formatNum(d.guess)}
                      </td>
                      <td className="py-1.5 px-2 text-right text-text-primary">
                        {formatNum(d.signup)}
                      </td>
                      <td className="py-1.5 px-2 text-right font-medium text-text-secondary">
                        {conv}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </MetricSection>
      )}

      {/* Daily funnel trend */}
      <MetricSection
        question="How is the funnel trending daily?"
        status="good"
        summary={dailyChartData.length + " days"}
        ideal="All funnel stages growing together."
        defaultExpanded
      >
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={dailyChartData}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(
                  1,
                  Math.floor(dailyChartData.length / 8)
                )}
              />
              <YAxis tick={{ fontSize: 10, fill: "#888" }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {Object.entries(STAGE_COLORS).map(([stage, color]) => (
                <Line
                  key={stage}
                  type="monotone"
                  dataKey={stage}
                  stroke={color}
                  strokeWidth={stage === "visit" ? 2 : 1.5}
                  dot={false}
                  name={STAGE_LABELS[stage]}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>

      {/* Event breakdown */}
      <MetricSection
        question="Which specific events drive the funnel?"
        status="good"
        summary={data.eventBreakdown.length + " event types"}
        ideal="Higher/Lower play events well-represented."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Event
                </th>
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Stage
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Count
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Users
                </th>
              </tr>
            </thead>
            <tbody>
              {data.eventBreakdown.slice(0, 20).map((e) => (
                <tr
                  key={e.eventName}
                  className="border-b border-surface-border/50"
                >
                  <td className="py-1.5 px-2 font-mono text-text-secondary">
                    {e.eventName}
                  </td>
                  <td className="py-1.5 px-2">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-[10px] font-medium text-white"
                      style={{
                        backgroundColor:
                          STAGE_COLORS[e.stage] || "#888",
                      }}
                    >
                      {STAGE_LABELS[e.stage] || e.stage}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-primary font-medium">
                    {formatNum(e.eventCount)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {formatNum(e.totalUsers)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </MetricSection>
    </div>
  );
}

function RetentionTab({ data }: { data: RetentionData }) {
  const chartData = useMemo(
    () =>
      data.daily.map((d) => ({
        date: formatDate(d.date),
        new: d.new,
        returning: d.returning,
        total: d.new + d.returning,
      })),
    [data.daily]
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <StatCard
          label="New Users"
          value={formatNum(data.summary.totalNewUsers)}
          sub={data.period + " period"}
        />
        <StatCard
          label="Returning Users"
          value={formatNum(data.summary.totalReturningUsers)}
          sub={data.period + " period"}
        />
        <StatCard
          label="Return Rate"
          value={data.summary.retentionRate + "%"}
          sub="Returning / total users"
        />
      </div>

      <MetricSection
        question="Are users coming back?"
        status={data.summary.retentionRate >= 20 ? "good" : "warning"}
        summary={data.summary.retentionRate + "% return rate"}
        ideal="Return rate above 30% and growing."
        defaultExpanded
      >
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(1, Math.floor(chartData.length / 8))}
              />
              <YAxis tick={{ fontSize: 10, fill: "#888" }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area
                type="monotone"
                dataKey="returning"
                stackId="1"
                stroke="#22c55e"
                fill="#22c55e"
                fillOpacity={0.3}
                name="Returning"
              />
              <Area
                type="monotone"
                dataKey="new"
                stackId="1"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.3}
                name="New"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>

      {/* Daily return rate */}
      <MetricSection
        question="What is the daily return rate?"
        status="good"
        summary="Daily ratio of returning to total users"
        ideal="Consistent or improving return rate."
      >
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData.map((d) => ({
                ...d,
                returnRate:
                  d.total > 0
                    ? Math.round((d.returning / d.total) * 100)
                    : 0,
              }))}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(1, Math.floor(chartData.length / 8))}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 10, fill: "#888" }}
                tickFormatter={(v: number) => v + "%"}
              />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(val: number) => [val + "%", "Return Rate"]}
              />
              <Line
                type="monotone"
                dataKey="returnRate"
                stroke="#8b5cf6"
                strokeWidth={2}
                dot={false}
                name="Return Rate"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>
    </div>
  );
}

function RealtimeTab({ data }: { data: RealtimeData }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <StatCard
          label="Active Users Right Now"
          value={String(data.activeUsers)}
          sub="Real-time"
        />
        <StatCard
          label="Active Pages"
          value={String(data.topActivePages.length)}
          sub="Pages with live traffic"
        />
      </div>

      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-3">
          Active Pages
        </h3>
        {data.topActivePages.length > 0 ? (
          <div className="space-y-1.5">
            {data.topActivePages.map((p) => {
              const maxUsers = data.topActivePages[0]?.activeUsers || 1;
              const pct = Math.max(
                4,
                Math.round((p.activeUsers / maxUsers) * 100)
              );
              return (
                <div key={p.page} className="flex items-center gap-2">
                  <span className="text-xs font-mono text-text-secondary w-48 truncate text-right">
                    {p.page}
                  </span>
                  <div className="flex-1 h-4 bg-surface-elevated rounded overflow-hidden">
                    <div
                      className="h-full bg-accent-live/60 rounded transition-all"
                      style={{ width: pct + "%" }}
                    />
                  </div>
                  <span className="text-xs text-text-primary font-medium w-8 text-right">
                    {p.activeUsers}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-text-muted">No active pages right now.</p>
        )}
      </div>
    </div>
  );
}

function PageEngagementTab({ data }: { data: PagesData }) {
  const [sectionFilter, setSectionFilter] = useState("all");

  const filteredPages = useMemo(
    () =>
      sectionFilter === "all"
        ? data.pages
        : data.pages.filter((p) => p.section === sectionFilter),
    [data.pages, sectionFilter]
  );

  const sectionDailyData = useMemo(() => {
    const topSections = data.sections.slice(0, 6).map((s) => s.section);
    return data.dailyBySection.map((d) => {
      const row: Record<string, string | number> = {
        date: formatDate(String(d.date)),
      };
      for (const s of topSections) {
        row[s] = (d[s] as number) || 0;
      }
      return row;
    });
  }, [data]);

  const topSections = data.sections.slice(0, 6).map((s) => s.section);

  return (
    <div className="space-y-4">
      {/* Section trend chart */}
      <MetricSection
        question="How is traffic distributed across sections?"
        status="good"
        summary={data.sections.length + " sections"}
        ideal="Discover leading, with growing category page traffic."
        defaultExpanded
      >
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={sectionDailyData}
              margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(0,0,0,0.06)"
              />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#888" }}
                interval={Math.max(
                  1,
                  Math.floor(sectionDailyData.length / 8)
                )}
              />
              <YAxis tick={{ fontSize: 10, fill: "#888" }} />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {topSections.map((section) => (
                <Area
                  key={section}
                  type="monotone"
                  dataKey={section}
                  stackId="1"
                  stroke={SECTION_COLORS[section] || "#888"}
                  fill={SECTION_COLORS[section] || "#888"}
                  fillOpacity={0.2}
                  strokeWidth={1.5}
                  name={section}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </MetricSection>

      {/* Page table with section filter */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary">
            Page-Level Engagement
          </h3>
          <select
            value={sectionFilter}
            onChange={(e) => setSectionFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
          >
            <option value="all">All sections</option>
            {data.sections.map((s) => (
              <option key={s.section} value={s.section}>
                {s.section} ({s.pageCount})
              </option>
            ))}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border">
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Path
                </th>
                <th className="text-left py-2 px-2 text-text-muted font-medium">
                  Section
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Views
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Users
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Avg Duration
                </th>
                <th className="text-right py-2 px-2 text-text-muted font-medium">
                  Bounce
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredPages.slice(0, 50).map((p) => (
                <tr
                  key={p.path}
                  className="border-b border-surface-border/50 hover:bg-surface-elevated/30"
                >
                  <td className="py-1.5 px-2 font-mono text-text-secondary truncate max-w-[250px]">
                    {p.path}
                  </td>
                  <td className="py-1.5 px-2">
                    <span
                      className="inline-block w-2 h-2 rounded-full mr-1"
                      style={{
                        backgroundColor:
                          SECTION_COLORS[p.section] || "#888",
                      }}
                    />
                    <span className="text-text-muted capitalize">
                      {p.section}
                    </span>
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-primary font-medium">
                    {formatNum(p.views)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {formatNum(p.users)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {formatDuration(p.avgDuration)}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {p.bounceRate}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// --- Main Page ---

type Tab = "overview" | "discover" | "funnel" | "retention" | "pages" | "realtime";

export default function AnalyticsPage() {
  usePageTracking({
    pageType: "admin_analytics",
    pageTitle: "Admin: Product Analytics",
  });
  useScrollDepth({ pageType: "admin_analytics" });
  useEngagementTime({ pageType: "admin_analytics" });

  const { secret } = useAdminAuth();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [period, setPeriod] = useState("7d");

  // --- Data fetching ---
  const fetcher = (url: string) =>
    adminFetch(url, secret).then((r) => {
      if (!r.ok) throw new Error("API error: " + r.status);
      return r.json();
    });

  const makeUrl = (endpoint: string, params?: Record<string, string>) => {
    const p = new URLSearchParams({ period, ...params });
    return `/api/admin/analytics/${endpoint}?${p}`;
  };

  const { data: overviewData, error: overviewError, isLoading: overviewLoading } =
    useSWR<OverviewData>(
      activeTab === "overview" ? makeUrl("overview") : null,
      fetcher,
      { refreshInterval: 300000 }
    );

  const { data: discoverData, error: discoverError, isLoading: discoverLoading } =
    useSWR<DiscoverData>(
      activeTab === "discover" ? makeUrl("discover") : null,
      fetcher,
      { refreshInterval: 300000 }
    );

  const { data: funnelData, error: funnelError, isLoading: funnelLoading } =
    useSWR<FunnelData>(
      activeTab === "funnel" ? makeUrl("funnel") : null,
      fetcher,
      { refreshInterval: 300000 }
    );

  const retentionPeriod = period === "7d" ? "7d" : "30d";
  const { data: retentionData, error: retentionError, isLoading: retentionLoading } =
    useSWR<RetentionData>(
      activeTab === "retention"
        ? makeUrl("retention", { period: retentionPeriod })
        : null,
      fetcher,
      { refreshInterval: 300000 }
    );

  const { data: realtimeData, error: realtimeError, isLoading: realtimeLoading } =
    useSWR<RealtimeData>(
      activeTab === "realtime"
        ? "/api/admin/analytics/realtime"
        : null,
      fetcher,
      { refreshInterval: 30000 }
    );

  const { data: pagesData, error: pagesError, isLoading: pagesLoading } =
    useSWR<PagesData>(
      activeTab === "overview" || activeTab === "pages"
        ? makeUrl("pages")
        : null,
      fetcher,
      { refreshInterval: 300000 }
    );

  const currentError =
    activeTab === "overview"
      ? overviewError
      : activeTab === "discover"
      ? discoverError
      : activeTab === "funnel"
      ? funnelError
      : activeTab === "retention"
      ? retentionError
      : activeTab === "realtime"
      ? realtimeError
      : pagesError;

  const currentLoading =
    activeTab === "overview"
      ? overviewLoading
      : activeTab === "discover"
      ? discoverLoading
      : activeTab === "funnel"
      ? funnelLoading
      : activeTab === "retention"
      ? retentionLoading
      : activeTab === "realtime"
      ? realtimeLoading
      : pagesLoading;

  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "discover", label: "Discover" },
    { key: "funnel", label: "Funnel" },
    { key: "retention", label: "Retention" },
    { key: "pages", label: "Pages" },
    { key: "realtime", label: "Realtime" },
  ];

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <PageHeader
          question="How are users engaging with Bain Luck?"
          status={currentError ? "critical" : currentLoading ? "loading" : "good"}
          summary={
            currentLoading
              ? "Loading analytics..."
              : currentError
              ? currentError.message
              : "GA4 product analytics"
          }
          ideal="Growing DAU, strong Discover engagement, healthy conversion funnel."
          subtitle="Product Analytics"
        />
      </div>

      {/* Period + Tab controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1 border-b border-surface-border pb-px">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={
                "px-4 py-2 text-sm font-medium rounded-t-lg transition-colors " +
                (activeTab === tab.key
                  ? "text-accent-brand border-b-2 border-accent-brand bg-accent-brand/5"
                  : "text-text-muted hover:text-text-secondary")
              }
            >
              {tab.label}
            </button>
          ))}
        </div>
        {activeTab !== "realtime" && (
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
          >
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        )}
      </div>

      {/* Error */}
      {currentError && (
        <div className="bg-surface-card border border-accent-danger/40 text-accent-danger rounded-lg p-3 text-sm">
          {currentError.message}
        </div>
      )}

      {/* Loading */}
      {currentLoading && (
        <div className="text-sm text-text-muted animate-pulse">
          Loading analytics data from GA4...
        </div>
      )}

      {/* Tab content */}
      {activeTab === "overview" && overviewData && (
        <OverviewTab data={overviewData} pagesData={pagesData} />
      )}
      {activeTab === "discover" && discoverData && (
        <DiscoverTab data={discoverData} />
      )}
      {activeTab === "funnel" && funnelData && (
        <FunnelTab data={funnelData} />
      )}
      {activeTab === "retention" && retentionData && (
        <RetentionTab data={retentionData} />
      )}
      {activeTab === "pages" && pagesData && (
        <PageEngagementTab data={pagesData} />
      )}
      {activeTab === "realtime" && realtimeData && (
        <RealtimeTab data={realtimeData} />
      )}
    </div>
  );
}
