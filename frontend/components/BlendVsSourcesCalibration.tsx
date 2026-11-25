"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { CalibrationCardNote } from "@/components/CalibrationCardNote";
import {
  fetchBlendVsSourcesCalibration,
  type BlendVsSourceBucket,
  type BlendVsSourceCommonSet,
  type BlendVsSourcePairwise,
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

interface AlignedBand {
  bucketIdx: number;
  rangeLabel: string;
  startLabel: string;
  blendError: number | null;
  sourceError: number | null;
  n: number;
  blendN: number | null;
  sourceN: number | null;
}

function alignPanelBands(
  blendBuckets: BlendVsSourceBucket[],
  sourceBuckets: BlendVsSourceBucket[],
): AlignedBand[] {
  const byBlend = new Map<number, BlendVsSourceBucket>();
  const bySource = new Map<number, BlendVsSourceBucket>();
  for (const b of blendBuckets) byBlend.set(b.bucket_idx, b);
  for (const s of sourceBuckets) bySource.set(s.bucket_idx, s);

  const idxs = Array.from(new Set([...byBlend.keys(), ...bySource.keys()])).sort((a, b) => a - b);
  return idxs.map(idx => {
    const bb = byBlend.get(idx);
    const sb = bySource.get(idx);
    const lo = idx * 10;
    const hi = (idx + 1) * 10;
    return {
      bucketIdx: idx,
      rangeLabel: `${lo}%–${hi}%`,
      startLabel: `${lo}%`,
      blendError: bb ? Math.round(bb.error * 10) / 10 : null,
      sourceError: sb ? Math.round(sb.error * 10) / 10 : null,
      n: sb?.n ?? bb?.n ?? 0,
      blendN: bb?.n ?? null,
      sourceN: sb?.n ?? null,
    };
  });
}

function symmetricErrorBound(bands: AlignedBand[]): number {
  let maxAbs = 4;
  for (const b of bands) {
    if (b.blendError !== null) maxAbs = Math.max(maxAbs, Math.abs(b.blendError));
    if (b.sourceError !== null) maxAbs = Math.max(maxAbs, Math.abs(b.sourceError));
  }
  if (maxAbs <= 4) return 4;
  if (maxAbs <= 12) return Math.ceil(maxAbs / 2) * 2;
  return Math.ceil(maxAbs / 5) * 5;
}

function dodgeLabelPair(
  rawY1: number,
  rawY2: number,
  minGap: number,
  minY: number,
  maxY: number,
): [number, number] {
  const swapped = rawY1 > rawY2;
  let upper = swapped ? rawY2 : rawY1;
  let lower = swapped ? rawY1 : rawY2;
  upper = Math.max(minY, Math.min(maxY - minGap, upper));
  lower = Math.max(minY + minGap, Math.min(maxY, lower));
  const gap = lower - upper;
  if (gap < minGap) {
    const need = minGap - gap;
    const mid = (upper + lower) / 2;
    upper = Math.max(minY, Math.min(maxY - minGap, mid - minGap / 2));
    lower = Math.min(maxY, upper + minGap);
    if (lower - upper < minGap) {
      upper = Math.max(minY, lower - minGap);
    }
    void need;
  }
  return swapped ? [lower, upper] : [upper, lower];
}

function formatPoints(ece: number | null): string {
  return ece !== null ? `${ece.toFixed(1)} points` : "\u2014";
}

function formatGameCountExplanation(
  pairwise: BlendVsSourcePairwise[],
  commonSets: BlendVsSourceCommonSet[],
): string {
  if (pairwise.length < 2) {
    return "Each comparison uses every game both Bain Luck and that source covered.";
  }
  const sorted = [...pairwise].sort((a, b) => b.n_games - a.n_games);
  const largest = sorted[0];
  const smallest = sorted[sorted.length - 1];
  if (largest.n_games === smallest.n_games) {
    return `Every comparison covered the same ${largest.n_games.toLocaleString()} games.`;
  }
  const bestCommonIdx = pickDefaultCommonSetIndex(commonSets);
  const shared = commonSets[bestCommonIdx];
  const coveredSources = pairwise.map(r => r.source);
  const coversAll =
    shared != null && coveredSources.every(src => shared.sources.includes(src));
  const overlapText = shared
    ? ` (${coversAll ? `all ${shared.sources.length} sources` : `${shared.sources.length} sources`} overlapped on the same ${shared.n_games.toLocaleString()} games)`
    : "";
  return (
    `Each comparison uses every game both Bain Luck and that source covered — ` +
    `${sourceLabel(largest.source)} covered ${largest.n_games.toLocaleString()} games while ` +
    `${sourceLabel(smallest.source)} covered ${smallest.n_games.toLocaleString()} games${overlapText}.`
  );
}

function SourceMissPanel({
  row,
  highlighted,
  onSelect,
}: {
  row: BlendVsSourcePairwise;
  highlighted: boolean;
  onSelect: () => void;
}) {
  const srcName = sourceLabel(row.source);
  const srcColor = sourceHex(row.source);
  const bands = alignPanelBands(row.blend.buckets, row.source_metrics.buckets);
  const yBound = symmetricErrorBound(bands);
  const maxBandN = Math.max(1, ...bands.map(b => b.n));

  // SVG coordinate system — right zone holds direct line labels (no legend row above plot).
  const width = 438;
  const height = 224;
  const plotLeft = 34;
  const plotRight = 294;
  const plotTop = 18;
  const plotBottom = 128;
  const plotW = plotRight - plotLeft;
  const plotH = plotBottom - plotTop;
  const yZero = plotTop + plotH / 2;
  const xLabelAxisY = 144;
  const xUnitY = 158;
  const countRowY = 212;
  const barBaseY = 198;
  const maxBarH = 20;
  const colStep = bands.length > 0 ? plotW / bands.length : plotW;
  const xAt = (i: number) =>
    bands.length <= 1 ? plotLeft + plotW / 2 : plotLeft + colStep * (i + 0.5);
  const yAt = (err: number) => {
    const clamped = Math.max(-yBound, Math.min(yBound, err));
    return yZero - (clamped / yBound) * (plotH / 2);
  };

  const blendPts = bands
    .map((b, i) => (b.blendError !== null ? { x: xAt(i), y: yAt(b.blendError), err: b.blendError, b } : null))
    .filter((p): p is NonNullable<typeof p> => p !== null);
  const srcPts = bands
    .map((b, i) => (b.sourceError !== null ? { x: xAt(i), y: yAt(b.sourceError), err: b.sourceError, b } : null))
    .filter((p): p is NonNullable<typeof p> => p !== null);

  const blendPolyline = blendPts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const srcPolyline = srcPts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  const lastBlendPt = blendPts[blendPts.length - 1];
  const lastSrcPt = srcPts[srcPts.length - 1];
  const rawBlendEndY = lastBlendPt ? lastBlendPt.y : yZero - 10;
  const rawSrcEndY = lastSrcPt ? lastSrcPt.y : yZero + 10;
  const [blendLabelY, srcLabelY] = dodgeLabelPair(
    rawBlendEndY,
    rawSrcEndY,
    16,
    plotTop + 8,
    plotBottom - 8,
  );
  const endLabelX =
    Math.max(lastBlendPt?.x ?? plotRight, lastSrcPt?.x ?? plotRight) + 12;

  const useStartTicks = bands.length > 4;
  const barW = Math.min(20, Math.max(8, colStep * 0.52));
  const yTicks = [yBound, 0, -yBound];

  return (
    <article
      data-testid={`blend-vs-sources-panel-${row.source}`}
      onClick={onSelect}
      className={`rounded-lg border p-3.5 bg-surface-card transition-colors ${
        highlighted ? "border-text-primary" : "border-surface-border"
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1.5">
        <h3 className="text-sm font-semibold text-text-primary">
          Bain Luck vs {srcName}
        </h3>
        <span className="text-xs text-text-muted tabular-nums">
          the same {row.n_games.toLocaleString()} games
        </span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto block select-none"
        role="img"
        aria-label={`Bain Luck (${formatPoints(row.blend.ece)}) vs ${srcName} (${formatPoints(row.source_metrics.ece)}) across ${row.n_games.toLocaleString()} games`}
      >
        {/* Horizontal gridlines + dashed 0 centerline */}
        {yTicks.map(val => {
          const y = yAt(val);
          const isZero = val === 0;
          const label = val > 0 ? `+${val}` : String(val);
          return (
            <g key={val}>
              <line
                x1={plotLeft}
                x2={plotRight}
                y1={y}
                y2={y}
                stroke={isZero ? "var(--text-secondary)" : "var(--surface-border)"}
                strokeWidth={isZero ? 1.1 : 0.75}
                strokeDasharray={isZero ? "3 3" : undefined}
              />
              <text
                x={plotLeft - 6}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize="10"
                fill="var(--text-muted)"
              >
                {label}
              </text>
            </g>
          );
        })}

        {/* Vertical column guides + x-axis labels + below-axis sample strip */}
        {bands.map((b, i) => {
          const cx = xAt(i);
          const barH = Math.max(3, (b.n / maxBandN) * maxBarH);
          const tickText = useStartTicks ? b.startLabel : b.rangeLabel;
          return (
            <g key={b.bucketIdx}>
              <title>
                {`${b.rangeLabel}: ${b.n.toLocaleString()} games` +
                  (b.blendError !== null ? `, Bain Luck ${b.blendError > 0 ? "+" : ""}${b.blendError.toFixed(1)} points` : "") +
                  (b.sourceError !== null ? `, ${srcName} ${b.sourceError > 0 ? "+" : ""}${b.sourceError.toFixed(1)} points` : "")}
              </title>
              <line
                x1={cx}
                x2={cx}
                y1={plotTop}
                y2={plotBottom}
                stroke="var(--surface-elevated)"
                strokeWidth={0.8}
              />
              <text
                x={cx}
                y={xLabelAxisY}
                textAnchor="middle"
                fontSize={useStartTicks ? "9.5" : "10"}
                fill="var(--text-muted)"
              >
                {tickText}
              </text>
              <rect
                x={cx - barW / 2}
                y={barBaseY - barH}
                width={barW}
                height={barH}
                rx={2}
                fill="var(--surface-border)"
              />
              <text
                x={cx}
                y={countRowY}
                textAnchor="middle"
                fontSize="9.5"
                fill="var(--text-secondary)"
              >
                {b.n.toLocaleString()}
              </text>
            </g>
          );
        })}

        {/* Band unit caption directly beneath x-axis tick row */}
        <text
          x={(plotLeft + plotRight) / 2}
          y={xUnitY}
          textAnchor="middle"
          fontSize="9"
          fill="var(--text-muted)"
        >
          {useStartTicks ? "bands of 10 points (start of each 10% band)" : "bands of 10 points"}
        </text>

        {/* Left label for the sample-count strip strictly below the plot */}
        <text
          x={plotLeft - 6}
          y={countRowY}
          textAnchor="end"
          fontSize="9.5"
          fill="var(--text-muted)"
        >
          games
        </text>

        {/* Competitor dashed line + hollow circles */}
        {srcPts.length > 1 && (
          <polyline
            points={srcPolyline}
            fill="none"
            stroke={srcColor}
            strokeWidth={2}
            strokeDasharray="5 3"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {srcPts.map(p => (
          <circle
            key={`src-${p.b.bucketIdx}`}
            cx={p.x}
            cy={p.y}
            r={3.5}
            fill="var(--surface-card)"
            stroke={srcColor}
            strokeWidth={2}
          />
        ))}

        {/* Bain Luck heavier solid line + filled circles */}
        {blendPts.length > 1 && (
          <polyline
            points={blendPolyline}
            fill="none"
            stroke="var(--calibration-bainluck)"
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        {blendPts.map(p => (
          <circle
            key={`bl-${p.b.bucketIdx}`}
            cx={p.x}
            cy={p.y}
            r={3.8}
            fill="var(--calibration-bainluck)"
            stroke="var(--surface-card)"
            strokeWidth={1.5}
          />
        ))}

        {/* Direct right-end labels on the marks (no legend row above the plot) */}
        {lastBlendPt && (
          <line
            x1={lastBlendPt.x + 4}
            y1={lastBlendPt.y}
            x2={endLabelX - 3}
            y2={blendLabelY}
            stroke="var(--calibration-bainluck)"
            strokeWidth={1}
            strokeOpacity={0.5}
          />
        )}
        {lastSrcPt && (
          <line
            x1={lastSrcPt.x + 4}
            y1={lastSrcPt.y}
            x2={endLabelX - 3}
            y2={srcLabelY}
            stroke={srcColor}
            strokeWidth={1}
            strokeOpacity={0.5}
          />
        )}
        <text
          x={endLabelX}
          y={blendLabelY}
          dominantBaseline="middle"
          fontSize="10"
          fontWeight="600"
          fill="var(--calibration-bainluck)"
          data-testid={`panel-end-label-bainluck-${row.source}`}
        >
          {`Bain Luck ${formatPoints(row.blend.ece)}`}
        </text>
        <text
          x={endLabelX}
          y={srcLabelY}
          dominantBaseline="middle"
          fontSize="10"
          fontWeight="600"
          fill={srcColor}
          data-testid={`panel-end-label-${row.source}`}
        >
          {`${srcName} ${formatPoints(row.source_metrics.ece)}`}
        </text>
      </svg>
    </article>
  );
}

export default function BlendVsSourcesCalibration() {
  const { data } = useSWR<BlendVsSourcesCalibrationData>(
    "/api/calibration/blend-vs-sources",
    fetchBlendVsSourcesCalibration,
    { revalidateOnFocus: false, dedupingInterval: 300000 },
  );

  const [selectedHorizon, setSelectedHorizon] = useState<string | null>(null);
  const [highlightedSource, setHighlightedSource] = useState<string | null>(null);

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
  const countExplanation = formatGameCountExplanation(pairwise, commonSets);

  return (
    <section
      id="blend-vs-sources"
      className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4"
      data-testid="calibration-blend-vs-sources-section"
      data-smoothing={data.smoothing}
      data-active-horizon={activeHorizon}
      data-matched-games={horizonData.n_events}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h2 className="text-title-3 text-text-primary">Bain Luck vs Each Source</h2>
        <span className="text-xs text-text-muted tabular-nums" data-testid="blend-vs-sources-game-count">
          Raw 10% bands &middot; no smoothing
        </span>
      </div>

      <p className="text-xs text-text-secondary mb-1.5 leading-relaxed">
        For each 10% probability band, how far Bain Luck and each source sat from &ldquo;said X%,
        happened X%&rdquo; (in points above or below zero), scored on the exact same games.
      </p>

      <p className="text-xs text-text-muted mb-2.5 leading-relaxed">
        {countExplanation}
      </p>

      <CalibrationCardNote label="How this comparison works">
        <div className="space-y-2 text-xs text-text-muted leading-relaxed">
          <p>
            At each pre-game checkpoint, every game uses only the inputs recorded at or before
            that cutoff, comparing Bain Luck beside each individual source on the exact same
            games in raw 10% probability bands with no smoothing. Points above 0 mean teams won more
            often than forecast; points below 0 mean they won less often.
          </p>
          {pairwise.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left border-b border-surface-border text-text-secondary">
                    <th className="py-1 pr-3">Source</th>
                    <th className="py-1 pr-3 text-right">Bain Luck Brier</th>
                    <th className="py-1 pr-3 text-right">Source Brier</th>
                    <th className="py-1 pr-3 text-right">Bain Luck log-loss</th>
                    <th className="py-1 text-right">Source log-loss</th>
                  </tr>
                </thead>
                <tbody>
                  {pairwise.map(row => (
                    <tr key={row.source} className="border-b border-surface-border/50">
                      <td className="py-1 pr-3 text-text-primary">{sourceLabel(row.source)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums text-text-primary">
                        {row.blend.brier !== null ? row.blend.brier.toFixed(4) : "\u2014"}
                      </td>
                      <td className="py-1 pr-3 text-right tabular-nums">
                        {row.source_metrics.brier !== null ? row.source_metrics.brier.toFixed(4) : "\u2014"}
                      </td>
                      <td className="py-1 pr-3 text-right tabular-nums text-text-primary">
                        {row.blend.log_loss !== null ? row.blend.log_loss.toFixed(4) : "\u2014"}
                      </td>
                      <td className="py-1 text-right tabular-nums">
                        {row.source_metrics.log_loss !== null ? row.source_metrics.log_loss.toFixed(4) : "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CalibrationCardNote>

      {/* Horizon selector */}
      <div className="flex flex-wrap items-center gap-2 mb-2.5">
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
                setHighlightedSource(null);
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

      <p className="text-xs text-text-muted mb-3">
        Vertical axis: miss in points (0 = right on; closer to the dashed 0 line is better).
        Sample counts (games per band) sit below each chart.
      </p>

      {/* 4 small miss panels: 2x2 desktop, 1x4 mobile */}
      {pairwise.length > 0 && (
        <div
          className="grid grid-cols-1 md:grid-cols-2 gap-3.5"
          data-testid="blend-vs-sources-panels"
        >
          {pairwise.map(row => (
            <SourceMissPanel
              key={row.source}
              row={row}
              highlighted={highlightedSource === row.source}
              onSelect={() =>
                setHighlightedSource(
                  highlightedSource === row.source ? null : row.source,
                )
              }
            />
          ))}
        </div>
      )}

      {/* Plain 4-column summary table */}
      {pairwise.length > 0 && (
        <div className="mt-4 overflow-x-auto scroll-shadow-x">
          <table className="w-full text-[13px] sm:text-sm" data-testid="blend-vs-sources-table">
            <thead>
              <tr className="text-left text-xs text-text-muted normal-case sm:uppercase tracking-normal sm:tracking-wide border-b border-surface-border">
                <th className="pb-2 pr-2 sm:pr-4">Source</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Same games</th>
                <th className="pb-2 pr-2 sm:pr-4 text-right">Bain Luck typical miss</th>
                <th className="pb-2 text-right">Source typical miss</th>
              </tr>
            </thead>
            <tbody>
              {pairwise.map(row => {
                const isSelected = highlightedSource === row.source;
                return (
                  <tr
                    key={row.source}
                    onClick={() =>
                      setHighlightedSource(isSelected ? null : row.source)
                    }
                    data-testid={`blend-vs-sources-row-${row.source}`}
                    className={`border-b border-surface-border/60 cursor-pointer transition-colors ${
                      isSelected ? "bg-surface-deep" : "hover:bg-surface-deep/50"
                    }`}
                  >
                    <td className="py-2 pr-2 sm:pr-4 font-medium text-text-primary whitespace-nowrap">
                      <span
                        aria-hidden="true"
                        className="inline-block w-2 h-2 rounded-full mr-2 align-middle"
                        style={{ backgroundColor: sourceHex(row.source) }}
                      />
                      {sourceLabel(row.source)}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums text-text-secondary">
                      {row.n_games.toLocaleString()}
                    </td>
                    <td className="py-2 pr-2 sm:pr-4 text-right tabular-nums font-medium text-text-primary">
                      {formatPoints(row.blend.ece)}
                    </td>
                    <td className="py-2 text-right tabular-nums text-text-secondary">
                      {formatPoints(row.source_metrics.ece)}
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
