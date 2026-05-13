"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  fetchSourceIntelligence,
  SourceIntelligenceData,
  SourceAccuracy,
  PairwiseDisagreement,
} from "@/lib/api";
import CalibrationChart from "@/components/CalibrationChart";
import DisagreementChart from "@/components/DisagreementChart";

const SOURCE_NAMES: Record<string, string> = {
  betting: "Betting Odds",
  espn: "ESPN",
  stat_model: "Bain Luck Model",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  mlb: "MLB Model",
};

const SOURCE_COLORS: Record<string, string> = {
  betting: "#374151",
  espn: "#f97316",
  stat_model: "#8b5cf6",
  kalshi: "#22c55e",
  polymarket: "#3b82f6",
  mlb: "#06b6d4",
};

const SPORT_NAMES: Record<string, string> = {
  basketball_nba: "NBA",
  basketball_ncaab: "NCAAB",
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAAF",
  baseball_mlb: "MLB",
  icehockey_nhl: "NHL",
  soccer_epl: "EPL",
  soccer_usa_mls: "MLS",
  mma_mixed_martial_arts: "MMA",
  basketball_wnba: "WNBA",
};

const ALL_SOURCES = ["betting", "espn", "stat_model", "kalshi", "polymarket", "mlb"] as const;

function sportLabel(key: string): string {
  return SPORT_NAMES[key] || key.split("_").pop()?.toUpperCase() || key;
}

export default function SourceIntelligencePage() {
  usePageTracking({ pageType: "source_intelligence", pageTitle: "Source Intelligence" });
  useScrollDepth({ pageType: "source_intelligence" });
  useEngagementTime({ pageType: "source_intelligence" });

  const { data, error, isLoading } = useSWR<SourceIntelligenceData>(
    "source-intelligence",
    fetchSourceIntelligence,
    { refreshInterval: 300_000, keepPreviousData: true }
  );

  const [pairSportFilter, setPairSportFilter] = useState<string>("all");

  const bestSource = useMemo(() => {
    if (!data?.source_accuracy?.length) return null;
    return data.source_accuracy.reduce((best, s) =>
      s.brier < best.brier ? s : best
    );
  }, [data]);

  const sourceLeaderboard = useMemo(() => {
    if (!data?.disagreements?.pairwise) return [];
    const wins: Record<string, { wins: number; total: number }> = {};
    for (const pw of data.disagreements.pairwise) {
      if (!wins[pw.source_a]) wins[pw.source_a] = { wins: 0, total: 0 };
      if (!wins[pw.source_b]) wins[pw.source_b] = { wins: 0, total: 0 };
      wins[pw.source_a].total += pw.count;
      wins[pw.source_b].total += pw.count;
      wins[pw.source_a].wins += Math.round(pw.a_closer_pct * pw.count);
      wins[pw.source_b].wins += Math.round((1 - pw.a_closer_pct) * pw.count);
    }
    return Object.entries(wins)
      .map(([source, { wins: w, total }]) => ({
        source,
        winRate: total > 0 ? w / total : 0,
        total,
      }))
      .sort((a, b) => b.winRate - a.winRate);
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-text-muted text-sm">Loading analysis...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-text-muted text-sm">
          Unable to load source intelligence data.{" "}
          <button onClick={() => window.location.reload()} className="underline">
            Retry
          </button>
        </div>
      </div>
    );
  }

  const { coverage, source_accuracy, disagreements, case_studies } = data;

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-8">
      {/* Hero */}
      <section className="text-center pt-4 pb-2">
        <h1 className="text-2xl md:text-3xl font-bold text-text-primary tracking-tight">
          When Sources Disagree, Who&apos;s Right?
        </h1>
        <p className="mt-3 text-text-secondary text-sm md:text-base leading-relaxed max-w-2xl mx-auto">
          We identified {coverage.total_events.toLocaleString()} sporting events with dense,
          overlapping coverage from multiple probability sources — sportsbooks, prediction
          markets, and statistical models. For each event, we compare closing probabilities
          to the actual outcome and measure which source was closest to the truth.
        </p>
        <p className="mt-2 text-text-muted text-xs">
          Updated {new Date(data.generated_at).toLocaleDateString("en-US", {
            month: "long", day: "numeric", year: "numeric",
          })}
        </p>
      </section>

      {/* Stat Cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Events Analyzed" value={coverage.total_events.toLocaleString()} />
        <StatCard
          label="Multi-Source"
          value={coverage.multi_source_events.toLocaleString()}
          sub={`${Math.round((coverage.multi_source_events / coverage.total_events) * 100)}% of events`}
        />
        <StatCard
          label="Disagreement Rate"
          value={`${(disagreements.rate_5pp * 100).toFixed(1)}%`}
          sub="of matched observations"
        />
        <StatCard
          label="Most Accurate"
          value={bestSource ? (SOURCE_NAMES[bestSource.source] || bestSource.source) : "—"}
          sub={bestSource ? `Brier ${bestSource.brier.toFixed(3)} ± ${(bestSource.brier_ci || 0).toFixed(3)}` : ""}
        />
      </section>

      {/* Source Coverage */}
      <Card title="The Data" subtitle="Which sources cover which sports?">
        {/* Source overlap distribution */}
        <div className="mb-5">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
            Events by Number of Sources
          </h4>
          <div className="flex items-end gap-1.5 h-24">
            {coverage.by_source_count.map((d) => {
              const maxEvents = Math.max(...coverage.by_source_count.map(x => x.events));
              const heightPct = (d.events / maxEvents) * 100;
              return (
                <div key={d.sources} className="flex-1 flex flex-col items-center gap-0.5">
                  <span className="text-[10px] text-text-muted">{d.events.toLocaleString()}</span>
                  <div
                    className="w-full bg-accent-brand/20 rounded-t"
                    style={{ height: `${Math.max(heightPct, 4)}%` }}
                  />
                  <span className="text-[10px] text-text-secondary font-medium">{d.sources}</span>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-text-muted text-center mt-1">Number of sources per event</p>
        </div>

        {/* Coverage heatmap table */}
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-muted">
                <th className="text-left py-1.5 px-2 font-medium">Sport</th>
                {ALL_SOURCES.map(src => (
                  <th key={src} className="text-center py-1.5 px-1.5 font-medium">
                    {SOURCE_NAMES[src]?.split(" ")[0] || src}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {coverage.by_sport.slice(0, 12).map((row) => (
                <tr key={row.sport} className="border-t border-surface-border/50">
                  <td className="py-1.5 px-2 font-medium text-text-secondary">
                    {sportLabel(row.sport)}
                  </td>
                  {ALL_SOURCES.map(src => {
                    const val = row[src as keyof typeof row] as number;
                    const pct = row.total > 0 ? val / row.total : 0;
                    return (
                      <td key={src} className="text-center py-1.5 px-1.5">
                        {val > 0 ? (
                          <span
                            className="inline-block rounded px-1.5 py-0.5 text-[10px] font-medium"
                            style={{
                              backgroundColor: `rgba(16,185,129,${Math.max(pct * 0.3, 0.05)})`,
                              color: pct > 0.5 ? "#065f46" : "#6b7280",
                            }}
                          >
                            {val.toLocaleString()}
                          </span>
                        ) : (
                          <span className="text-text-muted/40">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Overall Accuracy */}
      <Card
        title="Source Accuracy"
        subtitle="How accurate is each source's closing probability?"
      >
        {/* Brier score comparison */}
        <div className="space-y-2 mb-5">
          {source_accuracy.map((sa) => (
            <div key={sa.source} className="flex items-center gap-3">
              <span className="text-xs text-text-secondary w-24 text-right font-medium">
                {SOURCE_NAMES[sa.source] || sa.source}
              </span>
              <div className="flex-1 h-5 bg-surface-elevated rounded-full overflow-hidden relative">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(((0.25 - sa.brier) / 0.25) * 100, 100)}%`,
                    backgroundColor: SOURCE_COLORS[sa.source] || "#6b7280",
                    opacity: 0.7,
                  }}
                />
                <span className="absolute right-2 top-0.5 text-[10px] text-text-muted font-medium">
                  {sa.brier.toFixed(3)} &plusmn; {(sa.brier_ci || 0).toFixed(3)}
                </span>
              </div>
              <span className="text-[10px] text-text-muted w-16">
                n={sa.observations.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-text-muted">
          Brier score measures accuracy (lower is better). A coin flip scores 0.25; perfect prediction scores 0.
          Based on each source&apos;s final probability before game completion.
        </p>

        {/* Mini calibration curves */}
        <div className="mt-4">
          <CalibrationChart
            series={source_accuracy.map(sa => ({
              label: SOURCE_NAMES[sa.source] || sa.source,
              color: SOURCE_COLORS[sa.source] || "#6b7280",
              data: sa.buckets.map(b => ({
                midpoint: b.idx * 10 + 5,
                actual: Math.round(b.actual * 1000) / 10,
                n: b.n,
                bucket: `${b.idx * 10}-${b.idx * 10 + 10}%`,
                error: Math.round((b.actual - b.avg_prob) * 1000) / 10,
              })),
            }))}
            height={320}
          />
        </div>
      </Card>

      {/* Disagreement Analysis */}
      <Card
        title="When Sources Disagree"
        subtitle={`Sources diverge >5pp in ${(disagreements.rate_5pp * 100).toFixed(1)}% of matched observations`}
      >
        {/* Disagreement rate by sport */}
        <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
          Disagreement Rate by Sport
        </h4>
        <div className="space-y-1.5 mb-4">
          {disagreements.by_sport.slice(0, 10).map((s) => (
            <div key={s.sport} className="flex items-center gap-2">
              <span className="text-xs text-text-secondary w-16 text-right font-medium">
                {sportLabel(s.sport)}
              </span>
              <div className="flex-1 h-4 bg-surface-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500/60 rounded-full"
                  style={{ width: `${Math.min(s.rate_5pp * 300, 100)}%` }}
                />
              </div>
              <span className="text-[10px] text-text-muted w-12 text-right">
                {(s.rate_5pp * 100).toFixed(1)}%
              </span>
            </div>
          ))}
        </div>

        {/* Magnitude distribution */}
        <div className="grid grid-cols-3 gap-3 mt-4">
          <MiniStat
            label=">5pp"
            value={`${(disagreements.rate_5pp * 100).toFixed(1)}%`}
            color="#f59e0b"
          />
          <MiniStat
            label=">10pp"
            value={`${(disagreements.rate_10pp * 100).toFixed(1)}%`}
            color="#ef4444"
          />
          <MiniStat
            label=">20pp"
            value={`${(disagreements.rate_20pp * 100).toFixed(1)}%`}
            color="#991b1b"
          />
        </div>
      </Card>

      {/* Who Was Right */}
      <Card
        title="Who Was Right?"
        subtitle="When sources disagree >5pp, which was closer to the outcome?"
      >
        {/* Source leaderboard */}
        {sourceLeaderboard.length > 0 && (
          <div className="mb-5">
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">
              Head-to-Head Leaderboard
            </h4>
            <div className="space-y-1.5">
              {sourceLeaderboard.map((s, i) => (
                <div key={s.source} className="flex items-center gap-2">
                  <span className="text-xs text-text-muted w-4 text-right">{i + 1}.</span>
                  <span className="text-xs text-text-secondary w-28 font-medium">
                    {SOURCE_NAMES[s.source] || s.source}
                  </span>
                  <div className="flex-1 h-4 bg-surface-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${s.winRate * 100}%`,
                        backgroundColor: SOURCE_COLORS[s.source] || "#6b7280",
                        opacity: 0.6,
                      }}
                    />
                  </div>
                  <span className="text-xs text-text-secondary font-medium w-12 text-right">
                    {(s.winRate * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-text-muted mt-1.5">
              Win rate: how often each source was closer to the actual outcome across all pairwise disagreements.
            </p>
          </div>
        )}

        {/* Pairwise table */}
        <PairwiseTable
          pairs={disagreements.pairwise}
          sportFilter={pairSportFilter}
          onSportChange={setPairSportFilter}
        />
      </Card>

      {/* Case Studies */}
      {case_studies.length > 0 && (
        <Card title="Dramatic Disagreements" subtitle="Events where sources diverged the most">
          <div className="space-y-6">
            {case_studies.map((cs) => (
              <div key={cs.event_id} className="space-y-2">
                <div className="flex items-baseline justify-between gap-2 flex-wrap">
                  <div>
                    <Link
                      href={`/events/${cs.event_id}`}
                      className="text-sm font-semibold text-text-primary hover:text-accent-brand transition-colors"
                    >
                      {cs.away_team} @ {cs.home_team}
                    </Link>
                    <span className="text-xs text-text-muted ml-2">
                      {sportLabel(cs.sport)} &middot; {cs.score}
                    </span>
                  </div>
                  <span className="text-xs font-medium text-amber-600">
                    {(cs.max_divergence * 100).toFixed(0)}pp peak divergence
                  </span>
                </div>
                <DisagreementChart
                  timeSeries={cs.series}
                  homeWon={cs.home_won}
                  homeTeam={cs.home_team}
                  awayTeam={cs.away_team}
                  height={240}
                />
                {cs.date && (
                  <p className="text-[10px] text-text-muted text-right">
                    {new Date(cs.date).toLocaleDateString("en-US", {
                      month: "short", day: "numeric", year: "numeric",
                    })}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Methodology */}
      <Card title="Methodology">
        <div className="text-xs text-text-secondary leading-relaxed space-y-3">
          <p>
            <strong>Well-covered events only.</strong> We only analyze events where at least two
            sources each have 20+ probability snapshots during live play. Events with thin or
            sporadic coverage are excluded entirely — if a major game lacks dense multi-source
            data, we treat that as a pipeline issue to fix, not sparse data to analyze.
          </p>
          <p>
            <strong>Ground truth.</strong> For each completed game, the actual outcome is binary:
            home team won or lost. Draws are excluded. Each source&apos;s closing probability is
            compared to this 0/1 outcome to determine absolute error.
          </p>
          <p>
            <strong>Closing probability.</strong> The accuracy section uses each source&apos;s
            final probability reading before game completion. This differs from the{" "}
            <Link href="/calibration" className="text-accent-brand hover:underline">
              calibration page
            </Link>
            , which uses opening prices — both views are informative.
          </p>
          <p>
            <strong>Case studies.</strong> Disagreement charts use the median probability per
            source to rank events (robust to transient spikes), then show the full time-series
            scoped to live game time only. Only sources with 20+ readings appear in the chart.
          </p>
          <p>
            <strong>Sources.</strong> Sportsbook consensus (median across 5-15 books via The Odds API),
            ESPN&apos;s proprietary model, our statistical model (nflfastR/Poisson-based), Kalshi
            (CFTC-regulated prediction market), Polymarket (CLOB prediction market), and the
            MLB Stats API model (baseball only).
          </p>
        </div>
      </Card>

      {/* Footer */}
      <div className="text-center text-xs text-text-muted space-x-4 pt-2 pb-4">
        <Link href="/calibration" className="hover:text-accent-brand transition-colors">
          Calibration Analysis
        </Link>
        <Link href="/about" className="hover:text-accent-brand transition-colors">
          About Bain Luck
        </Link>
      </div>
    </div>
  );
}

/* ── Subcomponents ── */

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4 text-center">
      <div className="text-xl md:text-2xl font-bold text-text-primary">{value}</div>
      <div className="text-xs text-text-muted mt-0.5">{label}</div>
      {sub && <div className="text-[10px] text-text-muted/70 mt-0.5">{sub}</div>}
    </div>
  );
}

function Card({ title, subtitle, children }: {
  title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <section className="bg-surface-card rounded-xl border border-surface-border p-5">
      <h2 className="text-lg font-bold text-text-primary">{title}</h2>
      {subtitle && (
        <p className="text-xs text-text-muted mt-0.5 mb-4">{subtitle}</p>
      )}
      {!subtitle && <div className="h-3" />}
      {children}
    </section>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-surface-elevated rounded-lg p-3 text-center">
      <div className="text-lg font-bold" style={{ color }}>{value}</div>
      <div className="text-[10px] text-text-muted">{label} divergence</div>
    </div>
  );
}

function PairwiseTable({ pairs, sportFilter, onSportChange }: {
  pairs: PairwiseDisagreement[];
  sportFilter: string;
  onSportChange: (s: string) => void;
}) {
  const allSports = useMemo(() => {
    const sports = new Set<string>();
    for (const pw of pairs) {
      for (const s of Object.keys(pw.by_sport)) sports.add(s);
    }
    return Array.from(sports).sort();
  }, [pairs]);

  const filteredPairs = useMemo(() => {
    if (sportFilter === "all") return pairs;
    return pairs
      .map(pw => {
        const sportData = pw.by_sport[sportFilter];
        if (!sportData) return null;
        return { ...pw, count: sportData.comparisons, a_closer_pct: sportData.a_closer_pct };
      })
      .filter((pw): pw is PairwiseDisagreement => pw !== null && pw.count >= 20);
  }, [pairs, sportFilter]);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide">
          Pairwise Head-to-Head
        </h4>
        <select
          value={sportFilter}
          onChange={(e) => onSportChange(e.target.value)}
          className="text-xs border border-surface-border rounded-lg px-2 py-1 bg-surface-card text-text-secondary"
        >
          <option value="all">All Sports</option>
          {allSports.map(s => (
            <option key={s} value={s}>{sportLabel(s)}</option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted border-b border-surface-border">
              <th className="text-left py-1.5 px-2 font-medium">Source A</th>
              <th className="text-left py-1.5 px-2 font-medium">Source B</th>
              <th className="text-right py-1.5 px-2 font-medium">Disagreements</th>
              <th className="text-right py-1.5 px-2 font-medium">Avg Gap</th>
              <th className="text-center py-1.5 px-2 font-medium">A Wins</th>
            </tr>
          </thead>
          <tbody>
            {filteredPairs.map((pw) => {
              const aWin = pw.a_closer_pct > 0.52;
              const bWin = pw.a_closer_pct < 0.48;
              return (
                <tr key={`${pw.source_a}-${pw.source_b}`}
                  className="border-t border-surface-border/50">
                  <td className="py-1.5 px-2 font-medium text-text-secondary">
                    {SOURCE_NAMES[pw.source_a] || pw.source_a}
                  </td>
                  <td className="py-1.5 px-2 font-medium text-text-secondary">
                    {SOURCE_NAMES[pw.source_b] || pw.source_b}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {pw.count.toLocaleString()}
                  </td>
                  <td className="py-1.5 px-2 text-right text-text-muted">
                    {(pw.avg_divergence * 100).toFixed(1)}pp
                  </td>
                  <td className="py-1.5 px-2 text-center">
                    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      aWin ? "bg-emerald-50 text-emerald-700" :
                      bWin ? "bg-red-50 text-red-700" :
                      "bg-gray-50 text-gray-600"
                    }`}>
                      {(pw.a_closer_pct * 100).toFixed(1)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {filteredPairs.length === 0 && (
        <p className="text-xs text-text-muted text-center py-4">
          Insufficient data for this filter (minimum 20 disagreements required).
        </p>
      )}
    </div>
  );
}
