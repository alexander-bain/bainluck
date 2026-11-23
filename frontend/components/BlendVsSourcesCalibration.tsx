"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import CalibrationChart from "@/components/CalibrationChart";
import { CalibrationCardNote } from "@/components/CalibrationCardNote";
import {
  fetchBlendVsSourcesCalibration,
  type BlendVsSourceBucket,
  type BlendVsSourceCommonSet,
  type BlendVsSourceMetrics,
  type BlendVsSourcesCalibrationData,
} from "@/lib/api";
import { sourceHex, sourceLabel } from "@/lib/sourceColors";

const HORIZONS = [
  { key: "start", label: "At Start" },
  { key: "t_minus_1h", label: "1h Before" },
  { key: "t_minus_6h", label: "6h Before" },
  { key: "t_minus_24h", label: "24h Before" },
] as const;

const MIN_SHARED_SET_GAMES = 25;
const THIN_BUCKET_FLOOR = 30;

function toChartPoints(buckets: BlendVsSourceBucket[], includeCI: boolean) {
  return buckets.map(b => ({
    midpoint: b.midpoint,
    actual: Math.round(b.actual * 1000) / 10,
    n: b.n,
    bucket: b.bucket,
    error: Math.round(b.error * 10) / 10,
    ciLower: includeCI && b.ci_lower != null ? Math.round(b.ci_lower * 10) / 10 : undefined,
    ciUpper: includeCI && b.ci_upper != null ? Math.round(b.ci_upper * 10) / 10 : undefined,
  }));
}

export function pickDefaultCommonSetIndex(sets: BlendVsSourceCommonSet[]): number {
  if (!sets.length) return 0;
  let bestIdx = 0;
  let bestKey: [number, number] = [-1, -1];
  sets.forEach((s, idx) => {
    if (s.n_games < MIN_SHARED_SET_GAMES) return;
    const key: [number, number] = [s.sources.length, s.n_games];
    if (key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) {
      bestKey = key;
      bestIdx = idx;
    }
  });
  return bestKey[0] >= 0 ? bestIdx : 0;
}

function formatCommonSetLabel(setItem: BlendVsSourceCommonSet): string {
  const names = setItem.sources.map(s => sourceLabel(s)).join(" + ");
  return `${names} (${setItem.n_games.toLocaleString()})`;
}

export default function BlendVsSourcesCalibration() {
  const { data } = useSWR<BlendVsSourcesCalibrationData>(
    "/api/calibration/blend-vs-sources",
    fetchBlendVsSourcesCalibration,
    { revalidateOnFocus: false, dedupingInterval: 300000 },
  );

  const [selectedHorizon, setSelectedHorizon] = useState<string | null>(null);
  const [focusPairSource, setFocusPairSource] = useState<string | null>(null);
  const [selectedCommonIdx, setSelectedCommonIdx] = useState<number | null>(null);
  const [isolatedCurve, setIsolatedCurve] = useState<string | null>(null);

  const availableHorizons = useMemo(() => {
    if (!data || data.schema !== "blend-vs-sources/1" || data.status !== "ready") {
      return [];
    }
    return HORIZONS.filter(h => (data.horizons?.[h.key]?.n_events ?? 0) > 0);
  }, [data]);

  if (
    !data ||
    data.schema !== "blend-vs-sources/1" ||
    data.status !== "ready" ||
    availableHorizons.length === 0
  ) {
    return null;
  }

  const activeHorizon =
    selectedHorizon && availableHorizons.some(h => h.key === selectedHorizon)
      ? selectedHorizon
      : availableHorizons[0].key;
  const horizonData = data.horizons[activeHorizon];
  const pairwise = horizonData.per_source_matched ?? [];
  const commonSets = horizonData.common_source_sets ?? [];

  const activePair =
    focusPairSource ? pairwise.find(r => r.source === focusPairSource) ?? null : null;
  const defaultCommonIdx = pickDefaultCommonSetIndex(commonSets);
  const safeCommonIdx =
    selectedCommonIdx != null && selectedCommonIdx >= 0 && selectedCommonIdx < commonSets.length
      ? selectedCommonIdx
      : defaultCommonIdx;
  const activeCommon = !activePair && commonSets.length > 0 ? commonSets[safeCommonIdx] : null;

  const seriesEntries: Array<{ key: string; label: string; color: string; metrics: BlendVsSourceMetrics }> = [];
  if (activePair) {
    seriesEntries.push({
      key: "blend",
      label: `${sourceLabel("blend")} (${activePair.blend.n_games.toLocaleString()})`,
      color: sourceHex("blend"),
      metrics: activePair.blend,
    });
    seriesEntries.push({
      key: activePair.source,
      label: `${sourceLabel(activePair.source)} (${activePair.source_metrics.n_games.toLocaleString()})`,
      color: sourceHex(activePair.source),
      metrics: activePair.source_metrics,
    });
  } else if (activeCommon) {
    seriesEntries.push({
      key: "blend",
      label: `${sourceLabel("blend")} (${activeCommon.blend.n_games.toLocaleString()})`,
      color: sourceHex("blend"),
      metrics: activeCommon.blend,
    });
    for (const src of activeCommon.sources) {
      const m = activeCommon.by_source[src];
      if (!m) continue;
      seriesEntries.push({
        key: src,
        label: `${sourceLabel(src)} (${m.n_games.toLocaleString()})`,
        color: sourceHex(src),
        metrics: m,
      });
    }
  } else if (pairwise.length > 0) {
    const first = pairwise[0];
    seriesEntries.push({
      key: "blend",
      label: `${sourceLabel("blend")} (${first.blend.n_games.toLocaleString()})`,
      color: sourceHex("blend"),
      metrics: first.blend,
    });
    seriesEntries.push({
      key: first.source,
      label: `${sourceLabel(first.source)} (${first.source_metrics.n_games.toLocaleString()})`,
      color: sourceHex(first.source),
      metrics: first.source_metrics,
    });
  }

  const effectiveEntries =
    isolatedCurve && seriesEntries.some(e => e.key === isolatedCurve)
      ? seriesEntries.filter(e => e.key === isolatedCurve)
      : seriesEntries;

  const includeCI = effectiveEntries.length <= 2;
  const chartSeries = effectiveEntries.map(entry => ({
    data: toChartPoints(entry.metrics.buckets, includeCI),
    color: entry.color,
    label: entry.label,
  }));

  const matchedGamesCount = activePair
    ? activePair.n_games
    : activeCommon
      ? activeCommon.n_games
      : (pairwise[0]?.n_games ?? 0);

  return (
    <section
      id="blend-vs-sources"
      className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4"
      data-testid="calibration-blend-vs-sources-section"
      data-smoothing={data.smoothing}
      data-active-horizon={activeHorizon}
      data-matched-games={matchedGamesCount}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 className="text-title-3 text-text-primary">Blend vs Contributing Sources</h2>
        <span className="text-xs text-text-muted tabular-nums" data-testid="blend-vs-sources-game-count">
          {matchedGamesCount.toLocaleString()} identical games &middot; no smoothing
        </span>
      </div>

      <p className="text-xs text-text-muted mb-3">
        Bain Luck&rsquo;s recorded game blend plotted beside each contributing source on the exact
        same games, using raw 10% buckets with counts and no smoothing.
      </p>

      <CalibrationCardNote label="How this comparison works">
        <p className="text-xs text-text-muted leading-relaxed">
          For every completed game recorded since Nov 6, 2026, each pre-game checkpoint takes the
          exact source bag published at or before that cutoff and scores Bain Luck alongside each
          individual source on the identical set of games (no cross-bin smoothing). Click any row in
          the matched table below to focus the 2-way comparison against that source, or pick a single
          curve to display every bin&rsquo;s sample count directly on the plot.
        </p>
      </CalibrationCardNote>

      {/* Horizon selector */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {HORIZONS.map(h => {
          const count = data.horizons?.[h.key]?.n_events ?? 0;
          if (count === 0) return null;
          const active = activeHorizon === h.key;
          return (
            <button
              key={h.key}
              type="button"
              onClick={() => {
                setSelectedHorizon(h.key);
                setFocusPairSource(null);
                setSelectedCommonIdx(null);
                setIsolatedCurve(null);
              }}
              data-testid={`blend-vs-sources-horizon-${h.key}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                active
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-deep text-text-secondary hover:text-text-primary"
              }`}
            >
              {h.label} ({count.toLocaleString()})
            </button>
          );
        })}
      </div>

      {/* Shared source set selector or active pairwise reset + per-curve count focus */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {commonSets.slice(0, 3).map((setItem, idx) => {
          const active = !activePair && safeCommonIdx === idx && !isolatedCurve;
          return (
            <button
              key={setItem.sources.join(",")}
              type="button"
              onClick={() => {
                setFocusPairSource(null);
                setSelectedCommonIdx(idx);
                setIsolatedCurve(null);
              }}
              className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
                active
                  ? "border-accent-brand text-accent-brand bg-surface-deep font-medium"
                  : "border-surface-border text-text-muted hover:text-text-primary"
              }`}
            >
              {formatCommonSetLabel(setItem)}
            </button>
          );
        })}
        {activePair && (
          <button
            type="button"
            onClick={() => {
              setFocusPairSource(null);
              setIsolatedCurve(null);
            }}
            className="px-2.5 py-1 rounded-md text-xs border border-accent-brand text-accent-brand bg-surface-deep font-medium"
          >
            &larr; All shared sources
          </button>
        )}
        {seriesEntries.length > 1 && (
          <span className="ml-auto flex flex-wrap items-center gap-1">
            {seriesEntries.map(entry => {
              const isolated = isolatedCurve === entry.key;
              return (
                <button
                  key={entry.key}
                  type="button"
                  onClick={() => setIsolatedCurve(isolated ? null : entry.key)}
                  title="Show every 10% bucket count directly on this curve"
                  className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                    isolated
                      ? "border-text-primary text-text-primary bg-surface-deep font-medium"
                      : "border-surface-border text-text-muted hover:text-text-primary"
                  }`}
                >
                  {sourceLabel(entry.key)} bins
                </button>
              );
            })}
          </span>
        )}
      </div>

      <CalibrationChart
        series={chartSeries}
        width={700}
        height={360}
        thinFloor={THIN_BUCKET_FLOOR}
        showAllN
      />

      {pairwise.length > 0 && (
        <div className="mt-4 overflow-x-auto scroll-shadow-x">
          <table className="w-full text-[13px] sm:text-sm" data-testid="blend-vs-sources-table">
            <thead>
              <tr className="text-left text-xs text-text-muted normal-case sm:uppercase tracking-normal sm:tracking-wide border-b border-surface-border">
                <th className="pb-2 pr-2 sm:pr-4">Source</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Games</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Blend ECE</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Source ECE</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Blend Brier</th>
                <th className="pb-2 text-right">Source Brier</th>
              </tr>
            </thead>
            <tbody>
              {pairwise.map(row => {
                const isSelected = focusPairSource === row.source;
                return (
                  <tr
                    key={row.source}
                    onClick={() => {
                      setFocusPairSource(isSelected ? null : row.source);
                      setIsolatedCurve(null);
                    }}
                    data-testid={`blend-vs-sources-row-${row.source}`}
                    className={`border-b border-surface-border/60 cursor-pointer transition-colors ${
                      isSelected ? "bg-surface-deep" : "hover:bg-surface-deep/50"
                    }`}
                  >
                    <td className="py-2 pr-2 sm:pr-4 font-medium text-text-primary whitespace-nowrap">
                      {sourceLabel(row.source)}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums text-text-secondary">
                      {row.n_games.toLocaleString()}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums font-medium text-text-primary">
                      {row.blend.ece !== null ? `${row.blend.ece.toFixed(1)}pp` : "\u2014"}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums text-text-secondary">
                      {row.source_metrics.ece !== null ? `${row.source_metrics.ece.toFixed(1)}pp` : "\u2014"}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums font-medium text-text-primary">
                      {row.blend.brier !== null ? row.blend.brier.toFixed(4) : "\u2014"}
                    </td>
                    <td className="py-2 text-right tabular-nums text-text-secondary">
                      {row.source_metrics.brier !== null ? row.source_metrics.brier.toFixed(4) : "\u2014"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
