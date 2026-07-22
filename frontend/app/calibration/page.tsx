"use client";

import { useState, useMemo } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import Link from "next/link";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchCalibration, fetchCalibrationExamples, CalibrationBucket, CalibrationExample } from "@/lib/api";
import ErrorState from "@/components/ErrorState";
import LoadingState from "@/components/LoadingState";
import CalibrationChart from "@/components/CalibrationChart";
import { ece, mce, monthYear } from "@/lib/calibrationMath";
import { getLeagueDisplay, LEAGUE_DISPLAY } from "@/lib/sportCategories";
import { SOURCE_COLORS as SOURCE_COLOR_REGISTRY, canonicalSourceKey } from "@/lib/sourceColors";

// L2-127 (Alex's Option 4): the 1,000-outcome floor USED to HIDE buckets from the
// By Source / By Category charts, which made a longshot category (golf, tennis)
// read like a broken page — a few dots in the corner. Alex's ruling: undo the
// hiding. This is now the THIN threshold, not a hide floor: buckets below it still
// render, as faded hollow dots with wide 95% CI bars (the existing n<30 visual
// convention, extended), so a casual reader sees "80% means 80%" with every bucket
// visible in its honest treatment — big solid dots = proven, ghost dots = small
// sample. Nothing is silently dropped.
const MIN_CHART_BUCKET_N = 1000;

// L2-103 Item 3b (Alex D5): a thin sub-league (e.g. icehockey_sweden_hockey_league,
// ~730 outcomes) must NOT collapse to its parent sport's display name ("Hockey"),
// because the parent sport is already graded in the Category Breakdown above — that
// made a niche chip read as "Hockey is still coming soon". Prefer the specific
// league label; only fall back to a prettified raw key for bare single-word
// categories (chess, commodities, health).
function nicheCatLabel(raw: string): string {
  if (raw.includes("_") || LEAGUE_DISPLAY[raw]) {
    // getLeagueDisplay returns proper-cased mapped names (SHL, NCAA Lacrosse) and
    // an ALL-CAPS generated fallback for unmapped keys — title-case the latter
    // while preserving short acronyms (NBA, UFL, NRL, AFL).
    return getLeagueDisplay(raw).replace(/\w\S*/g, (w) =>
      w.length <= 4 && w === w.toUpperCase()
        ? w
        : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
    );
  }
  return raw.replace(/_/g, " ");
}

const SPORT_KEY_MAP: Record<string, string> = {
  basketball_nba: "basketball", basketball_ncaab: "basketball",
  basketball_wnba: "basketball", basketball_nbl: "basketball",
  basketball_wncaab: "basketball", basketball_euroleague: "basketball",
  americanfootball_nfl: "football", americanfootball_ncaaf: "football",
  baseball_mlb: "baseball", icehockey_nhl: "hockey",
  soccer_epl: "soccer", soccer_usa_mls: "soccer",
  soccer_uefa_champs_league: "soccer", soccer_spain_la_liga: "soccer",
  soccer_germany_bundesliga: "soccer", soccer_italy_serie_a: "soccer",
  soccer_france_ligue_one: "soccer", soccer_uefa_europa_league: "soccer",
  mma_mixed_martial_arts: "mma", golf_pga: "golf", golf_lpga: "golf",
  cricket_ipl: "cricket", cricket_test_match: "cricket",
};

const DISPLAY_NAMES: Record<string, string> = {
  basketball: "Basketball", baseball: "Baseball", hockey: "Hockey",
  football: "Football", soccer: "Soccer", golf: "Golf", tennis: "Tennis",
  mma: "MMA", cricket: "Cricket", esports: "Esports", politics: "Politics",
  geopolitics: "Geopolitics", entertainment: "Entertainment",
  weather: "Weather", economics: "Economics", tech: "Tech",
  motorsports: "Motorsports",
};

const COLORS = [
  "#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed",
  "#db2777", "#0d9488", "#d97706", "#4f46e5", "#65a30d",
  "#0891b2", "#be185d", "#059669", "#9333ea", "#c2410c",
];

const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api: "Odds API",
  odds_api_spreads: "Spreads (Odds API)",
  odds_api_totals: "Totals (Odds API)",
  odds_api_bookmaker: "Per-Bookmaker (Odds API)",
};

function sourceLabel(src: string): string {
  return SOURCE_DISPLAY_NAMES[src] || src;
}

function normalizeCat(cat: string): string {
  if (SPORT_KEY_MAP[cat]) return SPORT_KEY_MAP[cat];
  const base = cat.split("_")[0];
  if (base === "americanfootball") return "football";
  if (base === "icehockey") return "hockey";
  return DISPLAY_NAMES[base] ? base : cat;
}

interface DrillInState {
  source: string;
  bucketLabel: string;
  bucketIdx: number;
  loading: boolean;
  error: boolean;
  examples: CalibrationExample[];
  note?: string | null;
}

interface AggBucket {
  midpoint: number;
  n: number;
  winners: number;
  avgProb: number;
  actual: number;
  error: number;
  bucket: string;
  ciLower: number;
  ciUpper: number;
}

function wilsonCI(wins: number, total: number, z = 1.96): [number, number] {
  if (total === 0) return [0, 0];
  const p = wins / total;
  const denom = 1 + (z * z) / total;
  const center = (p + (z * z) / (2 * total)) / denom;
  const spread = (z * Math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total)) / denom;
  return [Math.max(0, center - spread), Math.min(1, center + spread)];
}

function aggregateBuckets(
  buckets: CalibrationBucket[],
  filter?: (b: CalibrationBucket) => boolean
): AggBucket[] {
  const agg: Record<number, { n: number; winners: number; sumProb: number; sumSqErr: number }> = {};
  for (const b of buckets) {
    if (filter && !filter(b)) continue;
    const idx = b.bucket_idx;
    if (!agg[idx]) agg[idx] = { n: 0, winners: 0, sumProb: 0, sumSqErr: 0 };
    agg[idx].n += b.n;
    agg[idx].winners += b.winners;
    agg[idx].sumProb += b.sum_prob;
    agg[idx].sumSqErr += b.sum_sq_err;
  }
  return Object.entries(agg)
    .map(([idx, a]) => {
      const i = parseInt(idx);
      const avgProb = a.sumProb / a.n;
      const actual = a.winners / a.n;
      const [ciLo, ciHi] = wilsonCI(a.winners, a.n);
      return {
        midpoint: i * 10 + 5,
        n: a.n,
        winners: a.winners,
        avgProb: Math.round(avgProb * 1000) / 10,
        actual: Math.round(actual * 1000) / 10,
        error: Math.round((actual - avgProb) * 1000) / 10,
        bucket: `${i * 10}-${i * 10 + 10}%`,
        ciLower: Math.round(ciLo * 1000) / 10,
        ciUpper: Math.round(ciHi * 1000) / 10,
      };
    })
    .sort((a, b) => a.midpoint - b.midpoint);
}

function brierScore(buckets: CalibrationBucket[], filter?: (b: CalibrationBucket) => boolean): number {
  let n = 0, sq = 0;
  for (const b of buckets) {
    if (filter && !filter(b)) continue;
    n += b.n;
    sq += b.sum_sq_err;
  }
  return n > 0 ? sq / n : 0;
}

export default function CalibrationPage() {
  usePageTracking({ pageType: "calibration", pageTitle: "Calibration" });
  useScrollDepth({ pageType: "calibration" });
  useEngagementTime({ pageType: "calibration" });

  const { data, error } = useSWR("calibration-data", fetchCalibration, {
    refreshInterval: 300000,
  });

  const [activeSource, setActiveSource] = useState<string | null>(null);
  const [activeCat, setActiveCat] = useState<string | null>(null);
  const priceCohort: "all" | "closing" | "opening" = "all";
  // L2-74 §C (#940): default to the WELL-TRADED view; a visible toggle layers in
  // thin/untraded markets. The toggle never hides — counts are shown in both states.
  const [includeThin, setIncludeThin] = useState(false);

  // L2-103 Item 2: per-bucket drill-in — click a point on the By Source chart to
  // sample the real outcomes inside it (reader-trust: verify any bucket yourself).
  const [drillIn, setDrillIn] = useState<DrillInState | null>(null);
  const openDrillIn = async (source: string, bucketLabel: string, bucketIdx: number) => {
    setDrillIn({ source, bucketLabel, bucketIdx, loading: true, error: false, examples: [] });
    try {
      const res = await fetchCalibrationExamples(source, bucketIdx, !includeThin);
      setDrillIn({
        source, bucketLabel, bucketIdx,
        loading: false, error: false,
        examples: res.examples, note: res.note ?? null,
      });
    } catch {
      setDrillIn({ source, bucketLabel, bucketIdx, loading: false, error: true, examples: [] });
    }
  };

  const normalized = useMemo(() => {
    if (!data) return null;
    return data.buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
  }, [data]);

  const overallBrier = useMemo(() => normalized ? brierScore(normalized) : 0, [normalized]);

  const movedBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, b => b.price_moved === true) : [], [normalized]);
  const unchangedBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, b => b.price_moved === false) : [], [normalized]);
  const movedN = useMemo(() => movedBuckets.reduce((s, b) => s + b.n, 0), [movedBuckets]);
  const unchangedN = useMemo(() => unchangedBuckets.reduce((s, b) => s + b.n, 0), [unchangedBuckets]);
  const movedECE = useMemo(() => ece(movedBuckets), [movedBuckets]);
  const unchangedECE = useMemo(() => ece(unchangedBuckets), [unchangedBuckets]);

  // L2-74 §C: the main chart/table default to WELL-TRADED — exclude never-moved
  // outcomes (price_moved===false); keep real trades (true) + sportsbook consensus
  // (null, always a live line). The "include thin/untraded" toggle shows all.
  const cohortFilter = useMemo<((b: CalibrationBucket) => boolean) | undefined>(() => {
    if (includeThin) return undefined;
    return (b: CalibrationBucket) => b.price_moved !== false;
  }, [includeThin]);
  const fullN = useMemo(() =>
    normalized ? normalized.reduce((s, b) => s + b.n, 0) : 0, [normalized]);
  const wellTradedN = useMemo(() =>
    normalized ? normalized.filter(b => b.price_moved !== false).reduce((s, b) => s + b.n, 0) : 0,
    [normalized]);
  const cohortBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, cohortFilter) : [], [normalized, cohortFilter]);
  const cohortMCE = useMemo(() => mce(cohortBuckets), [cohortBuckets]);
  const cohortECE = useMemo(() => ece(cohortBuckets), [cohortBuckets]);
  const cohortBrier = useMemo(() =>
    normalized ? brierScore(normalized, cohortFilter) : 0, [normalized, cohortFilter]);
  const cohortN = useMemo(() =>
    normalized ? normalized.filter(b => !cohortFilter || cohortFilter(b)).reduce((s, b) => s + b.n, 0) : 0,
    [normalized, cohortFilter]);

  const sources = useMemo(() => {
    if (!normalized) return [];
    return [...new Set(normalized.map(b => b.source))].sort(
      (a, b) => normalized.filter(x => x.source === b).reduce((s, x) => s + x.n, 0)
        - normalized.filter(x => x.source === a).reduce((s, x) => s + x.n, 0)
    );
  }, [normalized]);

  // #997: minimum-sample bar comes from the API (Redis-tunable) so web + native
  // gate on the same threshold. Fall back to 1000 if an older cached payload or
  // the in-request fallback omits it — never regress to the noisy 100 floor.
  const minCategoryOutcomes = data?.min_category_outcomes ?? 1000;

  const categories = useMemo(() => {
    if (!normalized) return [];
    const catMap: Record<string, number> = {};
    for (const b of normalized) {
      catMap[b.category] = (catMap[b.category] || 0) + b.n;
    }
    return Object.entries(catMap)
      .filter(([, n]) => n >= minCategoryOutcomes)
      .sort(([, a], [, b]) => b - a)
      .map(([cat]) => cat)
      .slice(0, 15);
  }, [normalized, minCategoryOutcomes]);

  // Per-source metrics for the comparison section
  const sourceMetrics = useMemo(() => {
    if (!normalized) return [];
    return sources.map(src => {
      const srcBuckets = aggregateBuckets(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b)));
      const srcN = normalized.filter(b => b.source === src && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0);
      const srcMCE = mce(srcBuckets);
      const srcECE = ece(srcBuckets);
      const srcBrier = brierScore(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b)));
      const bucketsInBand = srcBuckets.filter(b => Math.abs(b.error) <= 5).length;
      return { source: src, n: srcN, mce: srcMCE, ece: srcECE, brier: srcBrier, bucketsInBand, totalBuckets: srcBuckets.length };
    });
  }, [normalized, sources, cohortFilter]);

  // Per-category metrics for the breakdown table
  const categoryMetrics = useMemo(() => {
    if (!normalized) return [];
    return categories.map(cat => {
      const catBuckets = aggregateBuckets(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b)));
      const catN = normalized.filter(b => b.category === cat && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0);
      const catMCE = mce(catBuckets);
      const catECE = ece(catBuckets);
      const catBrier = brierScore(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b)));
      return { category: cat, n: catN, mce: catMCE, ece: catECE, brier: catBrier };
    });
  }, [normalized, categories, cohortFilter]);

  if (error) {
    return (
      <div className="max-w-6xl mx-auto">
        <ErrorState message="Failed to load calibration data" onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!data || !normalized) {
    return (
      <div className="max-w-6xl mx-auto">
        <LoadingState message="Loading calibration data..." />
      </div>
    );
  }

  const topCats = categories.slice(0, 3).map(c =>
    `${DISPLAY_NAMES[c] || c} (${normalized.filter(b => b.category === c).reduce((s, b) => s + b.n, 0).toLocaleString()})`
  ).join(", ");

  // L2-127 (Alex's Option 4): show EVERY populated bucket — no floor filter. A
  // small-sample bucket renders as a faded hollow dot with a wide 95% CI bar (the
  // thin convention, threshold = MIN_CHART_BUCKET_N), never silently hidden. The
  // label count is the full source/category total, as before.
  const sourceChartData = (activeSource ? [activeSource] : sources).map((src, i) => ({
    data: aggregateBuckets(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b))),
    color: SOURCE_COLOR_REGISTRY[canonicalSourceKey(src)]?.hex || COLORS[i % COLORS.length],
    label: `${sourceLabel(src)} (${normalized.filter(b => b.source === src && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0).toLocaleString()})`,
  }));

  const catChartData = (activeCat ? [activeCat] : categories.slice(0, 5)).map((cat, i) => ({
    data: aggregateBuckets(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b))),
    color: COLORS[i % COLORS.length],
    label: `${DISPLAY_NAMES[cat] || cat} (${normalized.filter(b => b.category === cat && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0).toLocaleString()})`,
  }));

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="max-w-6xl mx-auto space-y-8 pb-12">
      {/* Hero */}
      <div className="text-center space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Do Prediction Markets Predict Anything?</h1>
        <p className="text-text-secondary max-w-2xl mx-auto">
          We analyzed {cohortN.toLocaleString()}{includeThin ? "" : " well-traded"} resolved
          predictions{includeThin ? "" : ` (${fullN.toLocaleString()} including thinly-traded)`} across
          Kalshi, Polymarket, and sportsbook odds (moneylines, spreads, and totals). The answer: when markets say
          something has a 30% chance of happening, it happens about 30% of the time.
        </p>
        <p className="text-xs text-text-muted">
          {data.date_range?.start && data.date_range?.end
            ? `Data ${monthYear(data.date_range.start)}–${monthYear(data.date_range.end)}`
            : `${data.total_outcomes.toLocaleString()} resolved outcomes`}
          {" · Updated "}
          {data.generated_at
            ? new Date(data.generated_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
            : "hourly"}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard label="Resolved Outcomes" value={cohortN.toLocaleString()}
          detail={includeThin
            ? `all incl. thinly-traded · ${fullN.toLocaleString()} total`
            : `well-traded (default) · ${fullN.toLocaleString()} total incl. thin`} />
        <StatCard label="Calibration Error (ECE)"
          value={`${cohortECE.toFixed(1)}pp`}
          detail={`n-weighted · worst-bucket (MCE) ${cohortMCE.toFixed(1)}pp`}
          valueClass={cohortECE < 3 ? "text-green-600" : cohortECE < 5 ? "text-blue-600" : "text-orange-600"} />
        <StatCard label="Brier Score" value={cohortBrier.toFixed(4)}
          detail="0 = oracle, lower = better" />
        <StatCard label="Sources" value={String(sources.length)}
          detail={sources.map(sourceLabel).join(", ")} />
        <StatCard label="Categories" value={String(categories.length)}
          detail={topCats} />
      </div>

      {/* Well-traded / thin toggle (L2-74 §C, #940) — governs every table + curve below */}
      <div className="flex flex-wrap items-center gap-3 bg-surface-card rounded-xl px-4 py-3 border border-surface-border">
        <div className="text-sm text-text-secondary">
          {includeThin ? (
            <>Showing <strong className="text-text-primary">all markets</strong> ({fullN.toLocaleString()}), including thin/untraded.</>
          ) : (
            <>Showing <strong className="text-text-primary">well-traded markets</strong> ({wellTradedN.toLocaleString()}) &mdash; where real trading moved the price. Thin/untraded markets can be noisy.</>
          )}
        </div>
        <button
          onClick={() => setIncludeThin(v => !v)}
          className="ml-auto text-xs font-medium px-3 py-1.5 rounded-full border border-surface-border text-text-secondary hover:text-text-primary hover:border-text-muted transition-colors whitespace-nowrap"
        >
          {includeThin
            ? "Well-traded only"
            : `Include thin/untraded (+${(fullN - wellTradedN).toLocaleString()})`}
        </button>
      </div>

      {/* Source Comparison */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">Source Comparison</h2>
        <p className="text-xs text-text-muted mb-4">
          How each data source performs independently, sorted by ECE.{" "}
          <strong className="text-text-secondary">ECE</strong> (n-weighted error) is the headline
          metric &mdash; it reflects the outcomes users actually see. MCE (equal-weighted) is a
          secondary &ldquo;worst-bucket sensitivity&rdquo; stat where a tiny bucket counts as much
          as a huge one. Lower is better.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4 text-right">Outcomes</th>
                <th className="pb-2 pr-4 text-right">ECE</th>
                <th className="pb-2 pr-4 text-right" title="Max/worst-bucket sensitivity (equal-weighted): a small bucket counts as much as a large one, so it over-reacts to thin samples.">
                  MCE&nbsp;<span className="text-text-muted/60">&#9432;</span>
                </th>
                <th className="pb-2 pr-4 text-right">Brier</th>
                <th className="pb-2 text-right">Buckets within 5pp</th>
              </tr>
            </thead>
            <tbody>
              {[...sourceMetrics].sort((a, b) => a.ece - b.ece).map(sm => (
                <tr key={sm.source} className="border-t border-surface-border">
                  <td className="py-2.5 pr-4 font-medium text-text-primary">{sourceLabel(sm.source)}</td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{sm.n.toLocaleString()}</td>
                  <td className={`py-2.5 pr-4 text-right tabular-nums font-semibold ${
                    sm.ece < 3 ? "text-green-600" : sm.ece < 5 ? "text-blue-600" : "text-orange-600"
                  }`}>
                    {sm.ece.toFixed(1)}pp
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums text-text-muted">
                    {sm.mce.toFixed(1)}pp
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{sm.brier.toFixed(4)}</td>
                  <td className="py-2.5 text-right tabular-nums">
                    {sm.bucketsInBand}/{sm.totalBuckets}
                  </td>
                </tr>
              ))}
              <tr className="border-t-2 border-surface-border font-semibold">
                <td className="py-2.5 pr-4 text-text-primary">Combined</td>
                <td className="py-2.5 pr-4 text-right tabular-nums">{cohortN.toLocaleString()}</td>
                <td className={`py-2.5 pr-4 text-right tabular-nums ${
                  cohortECE < 3 ? "text-green-600" : cohortECE < 5 ? "text-blue-600" : "text-orange-600"
                }`}>
                  {cohortECE.toFixed(1)}pp
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums text-text-muted">
                  {cohortMCE.toFixed(1)}pp
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums">{cohortBrier.toFixed(4)}</td>
                <td className="py-2.5 text-right tabular-nums">
                  {cohortBuckets.filter(b => Math.abs(b.error) <= 5).length}/{cohortBuckets.length}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* How We Compare */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">How We Compare</h2>
        <p className="text-xs text-text-muted mb-4">
          Our aggregate MCE compared to published calibration benchmarks from academic research and forecasting platforms.
        </p>
        <div className="space-y-3">
          {[
            { label: priceCohort === "closing" ? "Bain Luck (closing line)" : priceCohort === "opening" ? "Bain Luck (opening price)" : "Bain Luck (all sources)", mce: cohortMCE, n: cohortN, highlight: true, ci: priceCohort === "all" ? `${data.mce_ci_lower.toFixed(1)}-${data.mce_ci_upper.toFixed(1)}pp` : undefined },
            { label: "Metaculus (self-reported)", mce: 2.5, n: null, highlight: false },
            { label: "Iowa Electronic Markets (Berg et al. 2008)", mce: 1.5, n: null, highlight: false },
            { label: "Academic consensus range (Arrow et al. 2008)", mce: 3.5, n: null, highlight: false, range: "2-5pp" },
          ].map(row => {
            const barWidth = Math.min(100, (row.mce / 10) * 100);
            return (
              <div key={row.label}>
                <div className="flex justify-between items-baseline text-sm mb-1">
                  <span className={row.highlight ? "font-semibold text-text-primary" : "text-text-secondary"}>
                    {row.label}
                  </span>
                  <span className={`tabular-nums text-xs ${
                    row.mce < 4 ? "text-green-600" : row.mce < 6 ? "text-blue-600" : "text-orange-600"
                  } font-semibold`}>
                    {row.range || `${row.mce.toFixed(1)}pp`}
                    {"ci" in row && row.ci ? ` (95% CI: ${row.ci})` : ""}
                    {row.n ? ` | ${row.n.toLocaleString()} outcomes` : ""}
                  </span>
                </div>
                <div className="h-2 bg-surface-secondary rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${row.highlight ? "bg-blue-500" : "bg-text-muted"}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-text-muted mt-4">
          Lower is better. Most prediction markets achieve 2-5pp MCE. Values below 4pp are considered excellent calibration.
        </p>
      </section>

      {/* Calibration curve + trading-activity story (L2-80 Item 2: merged into ONE
          section. The standalone well-traded curve was redundant — the page-level
          toggle banner above already carries the well-traded default, and the split
          curve's green "price moved" series IS the well-traded set. Falls back to a
          single cohort curve when the moved/unchanged split isn't available, so the
          page always shows a headline curve.) */}
      {movedN > 0 && unchangedN > 0 ? (
        <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
          <h2 className="text-title-3 text-text-primary mb-1">Does Trading Activity Matter?</h2>
          <p className="text-xs text-text-muted mb-4">
            The calibration curve, split by whether real trading moved the price. Points on the
            diagonal = perfect calibration; above = outcomes happened <em>more</em> than predicted,
            below = <em>less</em>. Shaded band = &plusmn;5pp and point size reflects sample count.
            Outcomes where the price moved (active trading) are dramatically better calibrated than
            outcomes stuck at their opening price.
          </p>
          <CalibrationChart
            series={[
              { data: movedBuckets, color: "#16a34a", label: `Price moved (${movedN.toLocaleString()})` },
              { data: unchangedBuckets, color: "#dc2626", label: `Price unchanged (${unchangedN.toLocaleString()})` },
            ]}
            width={700}
            height={400}
            thinFloor={MIN_CHART_BUCKET_N}
          />
          <div className="grid grid-cols-2 gap-3 mt-4">
            <StatCard label="Active Trading"
              value={`${movedECE.toFixed(1)}pp`}
              detail={`${movedN.toLocaleString()} outcomes`}
              valueClass="text-green-600" />
            <StatCard label="Opening Price Only"
              value={`${unchangedECE.toFixed(1)}pp`}
              detail={`${unchangedN.toLocaleString()} outcomes`}
              valueClass="text-orange-600" />
          </div>
          {movedECE > 0 && unchangedECE > 0 && (
            <p className="text-sm text-text-secondary mt-3 text-center">
              Markets with active trading are <strong>{(unchangedECE / movedECE).toFixed(1)}x</strong> more
              accurately calibrated than markets using opening prices alone.
            </p>
          )}
        </section>
      ) : (
        <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
          <h2 className="text-title-3 text-text-primary mb-1">
            {includeThin ? "All-Markets" : "Well-Traded"} Calibration Curve
          </h2>
          <p className="text-xs text-text-muted mb-4">
            Points on the diagonal = perfect calibration. Above = outcomes happened <em>more</em> than
            predicted. Below = <em>less</em>. Shaded band = &plusmn;5pp. Point size reflects sample count.
          </p>
          <CalibrationChart
            series={[{
              data: cohortBuckets,
              color: includeThin ? "#2563eb" : "#16a34a",
              label: `${includeThin ? "All markets" : "Well-traded"} (${cohortN.toLocaleString()})`,
            }]}
            width={700}
            height={400}
            thinFloor={MIN_CHART_BUCKET_N}
          />
        </section>
      )}

      {/* Table */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Calibration Table</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Bucket</th>
                <th className="pb-2 pr-4 text-right">N</th>
                <th className="pb-2 pr-4 text-right">Avg Predicted</th>
                <th className="pb-2 pr-4 text-right">Actual Rate</th>
                <th className="pb-2 pr-4 text-right">95% CI</th>
                <th className="pb-2 text-right">Error</th>
              </tr>
            </thead>
            <tbody>
              {cohortBuckets.map(b => (
                <tr key={b.bucket} className="border-t border-surface-border">
                  <td className="py-2 pr-4">{b.bucket}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.n.toLocaleString()}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.avgProb}%</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.actual}%</td>
                  <td className="py-2 pr-4 text-right tabular-nums text-text-muted">
                    {b.ciLower.toFixed(1)}-{b.ciUpper.toFixed(1)}%
                  </td>
                  <td className={`py-2 text-right tabular-nums ${
                    Math.abs(b.error) < 3 ? "text-text-muted" : b.error > 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {b.error > 0 ? "+" : ""}{b.error}pp
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* By Source */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">By Source</h2>
        <p className="text-xs text-text-muted mb-4">
          Every source gets the same treatment: error bars are the 95% CI (wider = less
          certain). Every bucket is shown &mdash; well-sampled buckets are solid dots,
          small-sample ones (&lt;{MIN_CHART_BUCKET_N.toLocaleString()} outcomes) are faded
          hollow dots with wide error bars, so you can see exactly how much data stands
          behind each point rather than having any hidden. Select a source
          tab to see per-bucket sample counts{activeSource ? " and click a point for examples" : ""}.
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="All" active={!activeSource} onClick={() => { setActiveSource(null); setDrillIn(null); }} />
          {sources.map(s => (
            <TabButton key={s} label={sourceLabel(s)} active={activeSource === s} onClick={() => { setActiveSource(s); setDrillIn(null); }} />
          ))}
        </div>
        <CalibrationChart
          series={sourceChartData}
          width={700}
          height={340}
          thinFloor={MIN_CHART_BUCKET_N}
          showAllN
          onPointClick={activeSource ? (_, pt) => openDrillIn(activeSource, pt.bucket, Math.floor(pt.midpoint / 10)) : undefined}
        />
        <BucketExamples
          state={drillIn}
          onClose={() => setDrillIn(null)}
          sourceLabel={sourceLabel}
        />
      </section>

      {/* By Category */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">By Category</h2>
        <p className="text-xs text-text-muted mb-4">
          Same treatment as By Source: 95% CI error bars, and every bucket shown &mdash;
          small-sample ones (&lt;{MIN_CHART_BUCKET_N.toLocaleString()} outcomes) as faded
          hollow dots with wide error bars, never hidden. Select a category tab to see
          per-bucket sample counts.
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="Top 5" active={!activeCat} onClick={() => setActiveCat(null)} />
          {categories.map(c => (
            <TabButton key={c} label={DISPLAY_NAMES[c] || c} active={activeCat === c} onClick={() => setActiveCat(c)} />
          ))}
        </div>
        <CalibrationChart series={catChartData} width={700} height={340} thinFloor={MIN_CHART_BUCKET_N} showAllN />
      </section>

      {/* L2-80 Item 1: the standalone per-category chart grid was removed — the
          tabbed "By Category" explorer above owns per-category curves, and the
          Category Breakdown table below is the scannable summary. One section per job. */}

      {/* Category Breakdown Table */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">Category Breakdown</h2>
        <p className="text-xs text-text-muted mb-4">
          Calibration metrics by market category. Categories with fewer than {minCategoryOutcomes.toLocaleString()} resolved outcomes are excluded &mdash; a sub-category chart below that sample size is statistical noise, not a calibration signal.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Category</th>
                <th className="pb-2 pr-4 text-right">Outcomes</th>
                <th className="pb-2 pr-4 text-right">ECE</th>
                <th className="pb-2 pr-4 text-right" title="Worst-bucket sensitivity (equal-weighted).">MCE&nbsp;<span className="text-text-muted/60">&#9432;</span></th>
                <th className="pb-2 text-right">Brier</th>
              </tr>
            </thead>
            <tbody>
              {[...categoryMetrics].sort((a, b) => a.ece - b.ece).map(cm => (
                <tr key={cm.category} className="border-t border-surface-border">
                  <td className="py-2 pr-4 font-medium text-text-primary">
                    {DISPLAY_NAMES[cm.category] || cm.category}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">{cm.n.toLocaleString()}</td>
                  <td className={`py-2 pr-4 text-right tabular-nums font-semibold ${
                    cm.ece < 3 ? "text-green-600" : cm.ece < 5 ? "text-blue-600" : "text-orange-600"
                  }`}>
                    {cm.ece.toFixed(1)}pp
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums text-text-muted">
                    {cm.mce.toFixed(1)}pp
                  </td>
                  <td className="py-2 text-right tabular-nums">{cm.brier.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Too-thin-to-grade honest note (L2-80 Item 4) — answers the friends-and-family
          skeptic ("what about the weird / novelty / long-shot markets?") without faking
          a curve. Fully payload-driven from small_sample_categories (real counts), so
          the native app inherits the same honest note with no extra logic. */}
      {data.small_sample_categories && data.small_sample_categories.length > 0 && (() => {
        const thin = [...data.small_sample_categories].sort((a, b) => b.outcomes - a.outcomes);
        const thinTotal = thin.reduce((s, c) => s + c.outcomes, 0);
        const examples = thin.slice(0, 8);
        const catLabel = nicheCatLabel;
        return (
          <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
            <h2 className="text-title-3 text-text-primary mb-1">What About Niche &amp; Long-Shot Markets?</h2>
            <p className="text-sm text-text-secondary mb-3">
              Fair question &mdash; what about the offbeat ones (one-off culture bets, novelty props,
              minor leagues)? A calibration curve is only honest with enough resolved outcomes behind it, so
              we don&rsquo;t publish one for any category below{" "}
              {minCategoryOutcomes.toLocaleString()} resolved outcomes &mdash; under that bar it&rsquo;s
              statistical noise, not a signal. Right now{" "}
              <strong className="text-text-primary">{thin.length}</strong>{" "}
              {thin.length === 1 ? "category is" : "categories are"} still accumulating
              ({thinTotal.toLocaleString()} outcomes and counting). The moment one crosses the bar it
              appears above automatically &mdash; no fake curve until we can stand behind it.
            </p>
            <p className="text-xs text-text-muted mb-2 uppercase tracking-wide">Closest to the bar</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {examples.map(c => (
                <span
                  key={c.category}
                  className="text-xs px-2.5 py-1 rounded-full bg-surface-deep text-text-secondary border border-surface-border capitalize"
                >
                  {catLabel(c.category)}{" "}
                  <span className="tabular-nums text-text-muted normal-case">{c.outcomes.toLocaleString()}</span>
                </span>
              ))}
              {thin.length > examples.length && (
                <span className="text-xs px-2.5 py-1 text-text-muted">
                  +{(thin.length - examples.length).toLocaleString()} more
                </span>
              )}
            </div>
            <p className="text-xs text-text-muted">
              How we&rsquo;ll know it&rsquo;s ready: see{" "}
              <a href="#methodology" className="text-accent-brand hover:underline">How We Measure This</a>{" "}
              for the sample-size bar and full methodology.
            </p>
          </section>
        );
      })()}

      {/* Data corrections log (L2-74 §E — trust panel; L2-80 Item 3: collapsed into a
          <details> closed by default and clearly labeled technical — too detailed to
          show expanded in every view. Content unchanged.) */}
      {data.corrections && data.corrections.length > 0 && (
        <section className="bg-surface-card rounded-xl border border-surface-border">
          <details className="group">
            <summary className="cursor-pointer list-none p-5 flex items-center justify-between gap-3 select-none">
              <span className="flex items-baseline gap-2">
                <span className="text-title-3 text-text-primary">Technical: data corrections log</span>
                <span className="text-xs text-text-muted tabular-nums">({data.corrections.length})</span>
              </span>
              <span className="text-text-muted text-sm transition-transform group-open:rotate-180" aria-hidden="true">&#9662;</span>
            </summary>
            <div className="px-5 pb-5">
              <p className="text-xs text-text-muted mb-4">
                A calibration page is only trustworthy if it fixes its own mistakes. Every data-quality
                correction we&rsquo;ve made &mdash; with dates and rows affected &mdash; is on the record here.
                See <a href="#methodology" className="text-accent-brand hover:underline">How We Measure This</a> for the full methodology.
              </p>
              <ul className="space-y-0">
                {data.corrections.map((c, i) => (
                  <li
                    key={`${c.date}-${i}`}
                    className="flex flex-col sm:flex-row sm:items-baseline gap-0.5 sm:gap-3 border-t border-surface-border py-3 first:border-0 first:pt-0"
                  >
                    <span className="text-xs font-mono text-text-muted whitespace-nowrap w-24 shrink-0">{c.date}</span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-text-primary">
                        {c.title}
                        {c.rows != null && (
                          <span className="ml-2 text-xs font-normal text-text-muted tabular-nums">
                            {c.rows.toLocaleString()} rows
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-text-secondary">{c.description}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </details>
        </section>
      )}

      {/* Further Reading */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Further Reading</h2>
        <p className="text-sm text-text-secondary mb-3">
          Our findings are consistent with decades of academic research on prediction market accuracy:
        </p>
        <ul className="space-y-3 text-sm text-text-secondary">
          <li><strong className="text-text-primary">Arrow et al., &ldquo;The Promise of Prediction Markets&rdquo;</strong> (2008, <em>Science</em>) &mdash; 22 leading economists argued that prediction markets are &ldquo;among the most accurate forecasting mechanisms known.&rdquo; <a href="https://www.science.org/doi/10.1126/science.1157679" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Berg, Nelson &amp; Rietz, &ldquo;Prediction Market Accuracy in the Long Run&rdquo;</strong> (2008) &mdash; The Iowa Electronic Markets predicted presidential outcomes within 1.5pp, outperforming 74% of polls. <a href="https://doi.org/10.1016/j.ijforecast.2008.03.007" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Tetlock &amp; Gardner, <em>Superforecasting</em></strong> (2015) &mdash; The foundational work on calibration. Well-calibrated forecasters can be identified by exactly the kind of curve shown above. <a href="https://en.wikipedia.org/wiki/Superforecasting" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Learn more &rarr;</a></li>
          <li><strong className="text-text-primary">Wolfers &amp; Zitzewitz, &ldquo;Prediction Markets&rdquo;</strong> (2004, <em>J. Econ. Perspectives</em>) &mdash; Comprehensive survey showing prediction markets produce well-calibrated estimates across domains. <a href="https://doi.org/10.1257/0895330041371321" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Metaculus Track Record</strong> &mdash; The forecasting platform publishes its calibration curve publicly, achieving ~2-3pp mean calibration error. <a href="https://www.metaculus.com/questions/track-record/" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">See their data &rarr;</a></li>
        </ul>
      </section>

      {/* Methodology */}
      <section id="methodology" className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4">
        <h2 className="text-title-3 text-text-primary mb-3">How We Measure This</h2>
        <ul className="space-y-3 text-sm text-text-secondary">
          <li><strong className="text-text-primary">What&rsquo;s a calibration curve?</strong> We group every resolved prediction by its opening probability (0-10%, 10-20%, etc.) and check what percentage actually came true. If markets are well-calibrated, the points follow the diagonal line &mdash; a 30% prediction happens 30% of the time.</li>
          <li><strong className="text-text-primary">How do we know who won?</strong> For sports, we use final scores &mdash; no ambiguity. For prediction markets (Kalshi, Polymarket), a market&rsquo;s final price settles at $1.00 (happened) or $0.00 (didn&rsquo;t happen) when it resolves.</li>
          <li><strong className="text-text-primary">Which probability do we use?</strong> For events with a known start time (sports games, tournaments), we use <strong>closing line prices</strong> &mdash; the last traded price before the event begins. This is the <a href="https://doi.org/10.1016/j.ijforecast.2008.03.007" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">academic gold standard</a> for calibration because it captures all available information at the moment of truth. For sports, we use vig-removed consensus closing odds across 20+ bookmakers. For prediction markets linked to events (Kalshi, Polymarket game markets), we use the last traded price before the event starts. For markets without a fixed event start time (elections, economics, entertainment), we use the <strong>opening price after initial trading settles</strong> &mdash; the most conservative and honest measure. A year-long market&rsquo;s accuracy depends on when you measure, so a single closing line would be misleading.</li>
          <li><strong className="text-text-primary">What&rsquo;s a Brier score?</strong> It measures the average squared error of every prediction. If you predicted 70% and it happened, your error for that prediction is (0.70 - 1.0)&sup2; = 0.09. Average that across all predictions: 0 is perfect, 0.25 is random guessing. Ours is {overallBrier.toFixed(2)}.</li>
          <li><strong className="text-text-primary">What&rsquo;s included?</strong> {data.total_outcomes.toLocaleString()} resolved outcomes{data.date_range?.start && data.date_range?.end ? ` from ${monthYear(data.date_range.start)}–${monthYear(data.date_range.end)}` : ""} across Kalshi, Polymarket, and sportsbook odds (via The Odds API). That published total is lower than the raw resolved-outcome count because we exclude markets that can&rsquo;t form an honest prediction &mdash; see the exclusions below. We only include markets where real trading occurred &mdash; outcomes with zero bids or no trading volume are excluded, because a price without participants isn&rsquo;t a prediction. Data refreshes hourly.</li>
          {data.liquidity_filter && (data.liquidity_filter.kalshi_included + data.liquidity_filter.kalshi_excluded > 0) && (
            <li>
              <strong className="text-text-primary">Liquidity filter (Kalshi).</strong>{" "}
              {data.liquidity_filter.rule}{" "}
              <span className="text-text-primary">
                {data.liquidity_filter.kalshi_included.toLocaleString()} included
              </span>{" "}
              &middot;{" "}
              <span className="text-text-muted">
                {data.liquidity_filter.kalshi_excluded.toLocaleString()} excluded
              </span>{" "}
              ({(100 * data.liquidity_filter.kalshi_excluded / (data.liquidity_filter.kalshi_included + data.liquidity_filter.kalshi_excluded)).toFixed(0)}% of the Kalshi set). A skeptical auditor can re-include them &mdash; we publish both counts so the filter is never silent.
            </li>
          )}
          {/* L2-103 Item 4: the other read-side exclusions that pull the raw count
              down to the published total — surfaced so the drop is never silent. */}
          {data.esports_multi_bundle_filter && data.esports_multi_bundle_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Esports match-bundle filter.</strong>{" "}
              {data.esports_multi_bundle_filter.rule}{" "}
              <span className="text-text-muted">{data.esports_multi_bundle_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.soccer_2way_filter && data.soccer_2way_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Soccer 2-way (draw-omission) filter.</strong>{" "}
              {data.soccer_2way_filter.rule}{" "}
              <span className="text-text-muted">{data.soccer_2way_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.void_filter && data.void_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Void filter (did-not-play / withdrew).</strong>{" "}
              {data.void_filter.rule}{" "}
              <span className="text-text-muted">{data.void_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.exclusion_symmetry && (
            <li>
              <strong className="text-text-primary">Never-traded exclusions differ by source (and we say so).</strong>{" "}
              Kalshi excludes <em>every</em> never-traded outcome (any price); Polymarket only excludes never-traded
              outcomes near 0.50 (the Gamma synthetic-placeholder band). So a Polymarket outcome that never traded but
              sits outside that band is still counted.{" "}
              <span className="text-text-muted">
                {data.exclusion_symmetry.poly_never_traded_excluded_by_band.toLocaleString()} poly never-traded already
                excluded by the placeholder band; {data.exclusion_symmetry.poly_never_traded_in_curve.toLocaleString()} still
                counted (the residual asymmetry). We publish the count so it&rsquo;s never silent.
              </span>
            </li>
          )}
          <li><strong className="text-text-primary">When did we start publishing this?</strong> We began publicly publishing and documenting these calibration metrics in July 2026. The underlying work &mdash; closing-line capture, resolution, devigging, and the exclusion rules above &mdash; long predates that date. July 2026 is when we started showing our work, not when the measurement began.</li>
        </ul>
      </section>

      {/* Footer */}
      <footer className="text-center text-xs text-text-muted pt-4 border-t border-surface-border">
        <p>
          {cohortN.toLocaleString()} resolved outcomes &middot; {sources.length} sources &middot; {categories.length} categories
          {priceCohort !== "all" && ` (${priceCohort === "closing" ? "closing line" : "opening price"} cohort)`}
        </p>
        <p className="mt-1">
          <Link href="/about" className="text-accent-brand hover:underline">About Bain Luck</Link>
        </p>
      </footer>
    </div>
    </ErrorBoundary>
  );
}

function StatCard({ label, value, detail, valueClass }: {
  label: string; value: string; detail: string; valueClass?: string;
}) {
  return (
    <div className="bg-surface-card rounded-xl p-3 border border-surface-border">
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
      <div className={`text-xl font-bold ${valueClass || "text-text-primary"}`}>{value}</div>
      <div className="text-[11px] text-text-muted mt-0.5 leading-tight">{detail}</div>
    </div>
  );
}

// L2-103 Item 2: unobtrusive per-bucket drill-in panel — shows 3-5 real sample
// outcomes so a skeptic can verify what any bucket is made of.
function BucketExamples({ state, onClose, sourceLabel }: {
  state: DrillInState | null;
  onClose: () => void;
  sourceLabel: (s: string) => string;
}) {
  if (!state) return null;
  const fmtDate = (d: string | null) => {
    if (!d) return "—";
    const dt = new Date(d);
    return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };
  return (
    <div className="mt-4 rounded-lg border border-surface-border bg-surface-deep p-4">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <div className="text-sm font-medium text-text-primary">
          Sample outcomes &mdash; {sourceLabel(state.source)}, {state.bucketLabel} bucket
        </div>
        <button
          onClick={onClose}
          className="text-xs text-text-muted hover:text-text-primary shrink-0"
          aria-label="Close examples"
        >
          Close &times;
        </button>
      </div>
      {state.loading ? (
        <div className="text-xs text-text-muted py-2">Loading examples&hellip;</div>
      ) : state.error ? (
        <div className="text-xs text-accent-danger py-2">Couldn&rsquo;t load examples. Try again.</div>
      ) : state.examples.length === 0 ? (
        <div className="text-xs text-text-muted py-2">
          {state.note || "No individual examples available for this source/bucket."}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-text-muted uppercase tracking-wide">
                  <th className="pb-1.5 pr-3">Market</th>
                  <th className="pb-1.5 pr-3">Outcome</th>
                  <th className="pb-1.5 pr-3 text-right">Predicted</th>
                  <th className="pb-1.5 pr-3 text-right">Result</th>
                  <th className="pb-1.5 text-right">Settled</th>
                </tr>
              </thead>
              <tbody>
                {state.examples.map((ex, i) => (
                  <tr key={i} className="border-t border-surface-border align-top">
                    <td className="py-1.5 pr-3 text-text-secondary max-w-[260px] truncate" title={ex.market_name}>{ex.market_name}</td>
                    <td className="py-1.5 pr-3 text-text-secondary max-w-[160px] truncate" title={ex.outcome_name}>{ex.outcome_name}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-text-primary">{(ex.price * 100).toFixed(1)}%</td>
                    <td className={`py-1.5 pr-3 text-right font-medium ${
                      /^(yes|won|true)$/i.test(ex.result) ? "text-green-600" : "text-red-600"
                    }`}>{ex.result}</td>
                    <td className="py-1.5 text-right tabular-nums text-text-muted whitespace-nowrap">{fmtDate(ex.settle_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-text-muted mt-2">A representative sample &mdash; not the full bucket.</p>
        </>
      )}
    </div>
  );
}

function TabButton({ label, active, onClick }: {
  label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
        active
          ? "bg-text-primary text-surface-deep"
          : "bg-surface-deep text-text-secondary hover:text-text-primary"
      }`}
    >
      {label}
    </button>
  );
}
