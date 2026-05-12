"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchCalibration, CalibrationBucket } from "@/lib/api";
import CalibrationChart from "@/components/CalibrationChart";

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

function normalizeCat(cat: string): string {
  if (SPORT_KEY_MAP[cat]) return SPORT_KEY_MAP[cat];
  const base = cat.split("_")[0];
  if (base === "americanfootball") return "football";
  if (base === "icehockey") return "hockey";
  return DISPLAY_NAMES[base] ? base : cat;
}

interface AggBucket {
  midpoint: number;
  n: number;
  winners: number;
  avgProb: number;
  actual: number;
  error: number;
  bucket: string;
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
      return {
        midpoint: i * 10 + 5,
        n: a.n,
        winners: a.winners,
        avgProb: Math.round(avgProb * 1000) / 10,
        actual: Math.round(actual * 1000) / 10,
        error: Math.round((actual - avgProb) * 1000) / 10,
        bucket: `${i * 10}-${i * 10 + 10}%`,
      };
    })
    .sort((a, b) => a.midpoint - b.midpoint);
}

function mce(cal: AggBucket[]): number {
  if (!cal.length) return 0;
  return cal.reduce((s, b) => s + Math.abs(b.error), 0) / cal.length;
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

  const normalized = useMemo(() => {
    if (!data) return null;
    return data.buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
  }, [data]);

  const overall = useMemo(() => normalized ? aggregateBuckets(normalized) : [], [normalized]);
  const overallMCE = useMemo(() => mce(overall), [overall]);
  const overallBrier = useMemo(() => normalized ? brierScore(normalized) : 0, [normalized]);

  const sources = useMemo(() => {
    if (!normalized) return [];
    return [...new Set(normalized.map(b => b.source))].sort(
      (a, b) => normalized.filter(x => x.source === b).reduce((s, x) => s + x.n, 0)
        - normalized.filter(x => x.source === a).reduce((s, x) => s + x.n, 0)
    );
  }, [normalized]);

  const categories = useMemo(() => {
    if (!normalized) return [];
    const catMap: Record<string, number> = {};
    for (const b of normalized) {
      catMap[b.category] = (catMap[b.category] || 0) + b.n;
    }
    return Object.entries(catMap)
      .filter(([, n]) => n >= 100)
      .sort(([, a], [, b]) => b - a)
      .map(([cat]) => cat)
      .slice(0, 15);
  }, [normalized]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto py-20 text-center">
        <p className="text-text-secondary">Failed to load calibration data.</p>
      </div>
    );
  }

  if (!data || !normalized) {
    return (
      <div className="max-w-4xl mx-auto py-20 text-center">
        <div className="inline-block w-8 h-8 border-2 border-surface-border border-t-accent-brand rounded-full animate-spin" />
        <p className="text-text-muted mt-3 text-sm">Loading calibration data...</p>
      </div>
    );
  }

  const pctBetter = Math.max(0, Math.round((1 - overallBrier / 0.25) * 100));
  const topCats = categories.slice(0, 3).map(c =>
    `${DISPLAY_NAMES[c] || c} (${normalized.filter(b => b.category === c).reduce((s, b) => s + b.n, 0).toLocaleString()})`
  ).join(", ");

  const sourceChartData = (activeSource ? [activeSource] : sources).map((src, i) => ({
    data: aggregateBuckets(normalized, b => b.source === src),
    color: COLORS[i % COLORS.length],
    label: `${src} (${normalized.filter(b => b.source === src).reduce((s, b) => s + b.n, 0).toLocaleString()})`,
  }));

  const catChartData = (activeCat ? [activeCat] : categories.slice(0, 5)).map((cat, i) => ({
    data: aggregateBuckets(normalized, b => b.category === cat),
    color: COLORS[i % COLORS.length],
    label: `${DISPLAY_NAMES[cat] || cat} (${normalized.filter(b => b.category === cat).reduce((s, b) => s + b.n, 0).toLocaleString()})`,
  }));

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      {/* Hero */}
      <div className="text-center space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Do Prediction Markets Predict Anything?</h1>
        <p className="text-text-secondary">
          Calibration analysis of {data.total_outcomes.toLocaleString()} resolved outcomes
          across {data.total_markets.toLocaleString()} markets
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard label="Resolved Outcomes" value={data.total_outcomes.toLocaleString()}
          detail={`${data.total_markets.toLocaleString()} markets`} />
        <StatCard label="Mean Calibration Error"
          value={`${overallMCE.toFixed(1)}pp`}
          detail={overallMCE < 4 ? "Excellent" : overallMCE < 8 ? "Good" : "Fair"}
          valueClass={overallMCE < 4 ? "text-green-600" : overallMCE < 8 ? "text-blue-600" : "text-orange-600"} />
        <StatCard label="Brier Score" value={overallBrier.toFixed(4)}
          detail={`${pctBetter}% better than guessing`} />
        <StatCard label="Sources" value={String(sources.length)}
          detail={sources.join(", ")} />
        <StatCard label="Categories" value={String(categories.length)}
          detail={topCats} />
      </div>

      {/* Overall calibration curve */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">Overall Calibration Curve</h2>
        <p className="text-xs text-text-muted mb-4">
          Points on the diagonal = perfect calibration. Above = outcomes happened <em>more</em> than predicted. Below = <em>less</em>.
          Shaded band = &plusmn;5pp. Point size reflects sample count.
        </p>
        <CalibrationChart
          series={[{
            data: overall,
            color: "#2563eb",
            label: `All Markets (${data.total_outcomes.toLocaleString()})`,
          }]}
          width={700}
          height={400}
        />
      </section>

      {/* Table */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Calibration Table</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Bucket</th>
                <th className="pb-2 pr-4 text-right">N</th>
                <th className="pb-2 pr-4 text-right">Avg Opening</th>
                <th className="pb-2 pr-4 text-right">Actual Rate</th>
                <th className="pb-2 text-right">Error</th>
              </tr>
            </thead>
            <tbody>
              {overall.map(b => (
                <tr key={b.bucket} className="border-t border-surface-border">
                  <td className="py-2 pr-4">{b.bucket}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.n.toLocaleString()}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.avgProb}%</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.actual}%</td>
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
        <h2 className="text-title-3 text-text-primary mb-3">By Source</h2>
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="All" active={!activeSource} onClick={() => setActiveSource(null)} />
          {sources.map(s => (
            <TabButton key={s} label={s} active={activeSource === s} onClick={() => setActiveSource(s)} />
          ))}
        </div>
        <CalibrationChart series={sourceChartData} width={700} height={340} />
      </section>

      {/* By Category */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">By Category</h2>
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="Top 5" active={!activeCat} onClick={() => setActiveCat(null)} />
          {categories.map(c => (
            <TabButton key={c} label={DISPLAY_NAMES[c] || c} active={activeCat === c} onClick={() => setActiveCat(c)} />
          ))}
        </div>
        <CalibrationChart series={catChartData} width={700} height={340} />
      </section>

      {/* Category cards grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {categories.slice(0, 10).map((cat, i) => {
          const catBuckets = aggregateBuckets(normalized, b => b.category === cat);
          const catN = normalized.filter(b => b.category === cat).reduce((s, b) => s + b.n, 0);
          const catMCE = mce(catBuckets);
          return (
            <div key={cat} className="bg-surface-card rounded-xl p-4 border border-surface-border">
              <div className="flex justify-between items-baseline mb-2">
                <h3 className="text-sm font-semibold text-text-primary">{DISPLAY_NAMES[cat] || cat}</h3>
                <span className="text-xs text-text-muted">{catN.toLocaleString()} outcomes &middot; MCE: {catMCE.toFixed(1)}pp</span>
              </div>
              <CalibrationChart
                series={[{ data: catBuckets, color: COLORS[i % COLORS.length], label: "" }]}
                width={420} height={240} showLegend={false}
              />
            </div>
          );
        })}
      </div>

      {/* Further Reading */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Further Reading</h2>
        <p className="text-sm text-text-secondary mb-3">
          Our findings are consistent with decades of academic research on prediction market accuracy:
        </p>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li><strong className="text-text-primary">Arrow et al., &ldquo;The Promise of Prediction Markets&rdquo; (2008, <em>Science</em>)</strong> &mdash; A letter signed by 22 leading economists arguing that prediction markets are &ldquo;among the most accurate forecasting mechanisms known.&rdquo;</li>
          <li><strong className="text-text-primary">Berg, Nelson &amp; Rietz, &ldquo;Prediction Market Accuracy in the Long Run&rdquo; (2008)</strong> &mdash; The Iowa Electronic Markets predicted US presidential outcomes within 1.5 percentage points, outperforming 74% of polls.</li>
          <li><strong className="text-text-primary">Tetlock &amp; Gardner, <em>Superforecasting</em> (2015)</strong> &mdash; The foundational work on calibration in forecasting. Well-calibrated forecasters can be identified by their calibration curves.</li>
          <li><strong className="text-text-primary">Wolfers &amp; Zitzewitz, &ldquo;Prediction Markets&rdquo; (2004, <em>J. Econ. Perspectives</em>)</strong> &mdash; Prediction markets produce well-calibrated probability estimates across politics, sports, and entertainment.</li>
          <li><strong className="text-text-primary">Metaculus Track Record</strong> &mdash; The forecasting platform publishes its calibration curve publicly, achieving ~2-3pp mean calibration error.</li>
        </ul>
      </section>

      {/* Methodology */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Methodology &amp; Limitations</h2>
        <ul className="space-y-2 text-sm text-text-secondary">
          <li><strong className="text-text-primary">Winner inference:</strong> Winners are inferred from <code className="text-xs bg-surface-deep px-1 rounded">current_probability &ge; 0.95</code> on resolved markets. A backfill task is progressively setting explicit winner flags from settlement data.</li>
          <li><strong className="text-text-primary">Opening vs. closing line:</strong> We use first-seen price, which may be days before resolution. The academic gold standard is the &ldquo;closing line&rdquo; at event start, which would likely show even better calibration.</li>
          <li><strong className="text-text-primary">Market reconstruction:</strong> Polymarket decomposes multi-outcome events into binary sub-markets. We reconstruct these using <code className="text-xs bg-surface-deep px-1 rounded">group_id</code> when 3+ markets share a group.</li>
          <li><strong className="text-text-primary">Sources:</strong> Covers Kalshi, Polymarket, and The Odds API (game moneylines from sportsbooks). Data updates hourly.</li>
        </ul>
      </section>

      {/* Footer */}
      <footer className="text-center text-xs text-text-muted pt-4 border-t border-surface-border">
        <p>
          {data.total_outcomes.toLocaleString()} resolved outcomes &middot; {sources.length} sources &middot; {categories.length} categories
        </p>
        <p className="mt-1">
          <Link href="/about" className="text-accent-brand hover:underline">About Bain Luck</Link>
        </p>
      </footer>
    </div>
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
