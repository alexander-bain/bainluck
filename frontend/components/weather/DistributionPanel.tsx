"use client";

import Link from "next/link";
import { type CityData, tempColorC, toC, SOURCES, tomorrowDateStr } from "./data";
import { SourceBadge, CrossSourceBadge } from "./SourceBadge";

interface DistributionPanelProps {
  city: CityData;
}

export default function DistributionPanel({ city }: DistributionPanelProps) {
  const tempC = toC(city);
  const color = tempColorC(tempC);
  const dist = city.high.dist;
  const peakIdx = dist.reduce(
    (best, b, i) => (b.prob > dist[best].prob ? i : best),
    0,
  );
  const peak = dist[peakIdx];
  const isCrossSource = city.srcs.length > 1 && !!city.kalshiHigh;

  const unit = city.high.unit === "C" ? "C" : "F";
  const modeDisplay = Math.round(city.high.mode);

  const kalshiDist = city.kalshiHigh?.dist;

  const allProbs = [
    ...dist.map(b => b.prob),
    ...(kalshiDist ? kalshiDist.map(b => b.prob) : []),
  ];
  const maxProb = Math.max(...allProbs);

  return (
    <div
      className="bg-surface-card flex flex-col border border-surface-border"
      style={{ borderRadius: 16, padding: 22, minHeight: 460 }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div
            className="font-mono"
            style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}
          >
            {city.region}
          </div>
          <div style={{ fontSize: 24, fontWeight: 600, color: "var(--text-primary)" }}>
            {city.name}
          </div>
        </div>
        {isCrossSource ? <CrossSourceBadge /> : <SourceBadge src={city.srcs[0]} />}
      </div>

      <div className="font-mono" style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
        Tomorrow&apos;s high temperature &middot; {tomorrowDateStr()}
      </div>

      {/* Peak display */}
      <div className="flex items-baseline" style={{ marginTop: 20, gap: 4 }}>
        <span className="font-mono" style={{ fontSize: 64, fontWeight: 700, color, lineHeight: 1 }}>
          {modeDisplay}
        </span>
        <span style={{ fontSize: 28, fontWeight: 500, color, lineHeight: 1 }}>&deg;{unit}</span>
      </div>

      <div className="flex items-baseline" style={{ marginTop: 8, gap: 8 }}>
        <span className="font-mono" style={{ fontSize: 20, fontWeight: 600, color: "var(--text-secondary)" }}>
          {peak.prob}%
        </span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>most likely bucket</span>
      </div>

      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, marginBottom: 16 }}>
        {peak.label} is the modal outcome
      </div>

      {/* Histogram */}
      <div className="flex-1 flex flex-col justify-end">
        {isCrossSource && kalshiDist ? (
          <GroupedBarHistogram polyDist={dist} kalshiDist={kalshiDist} maxProb={maxProb} />
        ) : (
          <SingleSourceHistogram dist={dist} maxProb={maxProb} peakIdx={peakIdx} color={color} />
        )}
      </div>

      {/* Legend */}
      {isCrossSource && (
        <div className="flex items-center justify-center gap-5" style={{ marginTop: 12, fontSize: 11, color: "var(--text-secondary)" }}>
          <span className="flex items-center gap-1.5">
            <span style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: SOURCES.polymarket.color }} />
            Polymarket
          </span>
          <span className="flex items-center gap-1.5">
            <span style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: SOURCES.kalshi.color }} />
            Kalshi
          </span>
        </div>
      )}

      <div
        className="font-mono"
        style={{ fontSize: 11, color: "var(--text-muted)", marginTop: isCrossSource ? 6 : 16, textAlign: "center" }}
      >
        {city.marketId ? (
          <Link
            href={`/futures/${city.marketId}`}
            className="inline-flex items-center gap-1 text-accent-brand hover:underline"
            style={{ fontSize: 11 }}
          >
            View probability timeline
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="inline">
              <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </Link>
        ) : (
          <>
            Click any pin on the map &middot; {dist.length} outcome buckets
            {city.srcs.length > 1 ? " (Polymarket)" : ` (${SOURCES[city.srcs[0]].label})`}
          </>
        )}
      </div>
    </div>
  );
}

/* ── Single-source histogram ─────────────────────────────────────────── */

function SingleSourceHistogram({
  dist,
  maxProb,
  peakIdx,
  color,
}: {
  dist: Array<{ label: string; prob: number }>;
  maxProb: number;
  peakIdx: number;
  color: string;
}) {
  return (
    <>
      <div className="flex items-end" style={{ height: 140, gap: 2 }}>
        {dist.map((bucket, i) => {
          const isPeak = i === peakIdx;
          const barHeight = maxProb > 0 ? (bucket.prob / maxProb) * 100 : 0;
          return (
            <div
              key={i}
              className="flex-1 flex flex-col items-center justify-end group relative"
              style={{ height: "100%", cursor: bucket.prob > 0 ? "pointer" : "default" }}
            >
              {/* Tooltip on hover */}
              {bucket.prob > 0 && (
                <div
                  className="absolute -top-6 left-1/2 -translate-x-1/2 hidden group-hover:block font-mono px-1.5 py-0.5 rounded bg-gray-800 text-white whitespace-nowrap z-10"
                  style={{ fontSize: 10, fontWeight: 600 }}
                >
                  {bucket.prob}%
                </div>
              )}
              {/* Always-visible label on peak */}
              {isPeak && (
                <div className="font-mono" style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                  {bucket.prob}%
                </div>
              )}
              <div
                style={{
                  width: "100%",
                  height: `${barHeight}%`,
                  minHeight: bucket.prob > 0 ? 3 : 0,
                  backgroundColor: color,
                  opacity: isPeak ? 1 : 0.35 + (bucket.prob / maxProb) * 0.45,
                  borderRadius: "3px 3px 0 0",
                  transition: "height 300ms ease, opacity 150ms ease",
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex" style={{ gap: 2, marginTop: 4 }}>
        {dist.map((bucket, i) => (
          <div key={i} className="flex-1 text-center font-mono" style={{ fontSize: 9, color: "var(--text-muted)" }}>
            {bucket.label}
          </div>
        ))}
      </div>
    </>
  );
}

/* ── Grouped bar histogram (cross-source) ────────────────────────────── */

function GroupedBarHistogram({
  polyDist,
  kalshiDist,
  maxProb,
}: {
  polyDist: Array<{ label: string; prob: number }>;
  kalshiDist: Array<{ label: string; prob: number }>;
  maxProb: number;
}) {
  const polyColor = SOURCES.polymarket.color;
  const kalshiColor = SOURCES.kalshi.color;

  const polyPeakIdx = polyDist.reduce((best, b, i) => (b.prob > polyDist[best].prob ? i : best), 0);
  const kalshiPeakIdx = kalshiDist.reduce((best, b, i) => (b.prob > kalshiDist[best].prob ? i : best), 0);

  // Map each Kalshi bucket to Polymarket bucket indices.
  // Kalshi has 6 buckets spanning the same temp range as Poly's 11.
  // We distribute each Kalshi bucket across ~2 Poly slots.
  const kalshiPerSlot = polyDist.length / kalshiDist.length;
  const kalshiByPolyIdx = polyDist.map((_, pi) => {
    const ki = Math.min(Math.floor(pi / kalshiPerSlot), kalshiDist.length - 1);
    return { prob: kalshiDist[ki].prob, isPeak: ki === kalshiPeakIdx, ki };
  });

  return (
    <>
      <div className="flex items-end" style={{ height: 140, gap: 1 }}>
        {polyDist.map((bucket, i) => {
          const polyH = maxProb > 0 ? (bucket.prob / maxProb) * 100 : 0;
          const kalshi = kalshiByPolyIdx[i];
          const kalshiH = maxProb > 0 ? (kalshi.prob / maxProb) * 100 : 0;
          const polyIsPeak = i === polyPeakIdx;

          const containerH = Math.max(polyH, kalshiH);
          return (
            <div key={i} className="flex-1 flex flex-col items-center justify-end group relative" style={{ height: "100%", cursor: "pointer" }}>
              {/* Tooltip on hover — shows both values */}
              <div
                className="absolute -top-7 left-1/2 -translate-x-1/2 hidden group-hover:flex items-center gap-1.5 font-mono px-2 py-1 rounded bg-gray-800 text-white whitespace-nowrap z-10"
                style={{ fontSize: 10, fontWeight: 600 }}
              >
                <span style={{ color: "#93C5FD" }}>{bucket.prob}%</span>
                <span style={{ color: "var(--text-secondary)" }}>/</span>
                <span style={{ color: "#86EFAC" }}>{kalshi.prob}%</span>
              </div>

              {/* Peak labels */}
              {(polyIsPeak || kalshi.isPeak) && (
                <div className="flex gap-0.5 mb-1" style={{ fontSize: 9, fontWeight: 600 }}>
                  {polyIsPeak && <span style={{ color: SOURCES.polymarket.fg }}>{bucket.prob}%</span>}
                  {kalshi.isPeak && i === polyDist.findIndex((_, j) => kalshiByPolyIdx[j].ki === kalshiPeakIdx) && (
                    <span style={{ color: SOURCES.kalshi.fg }}>{kalshi.prob}%</span>
                  )}
                </div>
              )}

              {/* Paired bars */}
              <div className="flex items-end gap-px w-full" style={{ height: containerH > 0 ? `${containerH}%` : 0 }}>
                <div
                  style={{
                    flex: 1,
                    height: polyH > 0 && containerH > 0 ? `${(polyH / containerH) * 100}%` : 0,
                    minHeight: bucket.prob > 0 ? 3 : 0,
                    backgroundColor: polyColor,
                    opacity: 0.4 + (bucket.prob / maxProb) * 0.5,
                    borderRadius: "2px 0 0 0",
                  }}
                />
                <div
                  style={{
                    flex: 1,
                    height: kalshiH > 0 && containerH > 0 ? `${(kalshiH / containerH) * 100}%` : 0,
                    minHeight: kalshi.prob > 0 ? 3 : 0,
                    backgroundColor: kalshiColor,
                    opacity: 0.35 + (kalshi.prob / maxProb) * 0.5,
                    borderRadius: "0 2px 0 0",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* X-axis labels — show every other to reduce clutter */}
      <div className="flex" style={{ gap: 1, marginTop: 4 }}>
        {polyDist.map((bucket, i) => (
          <div key={i} className="flex-1 text-center font-mono" style={{ fontSize: 8, color: "var(--text-muted)" }}>
            {i % 2 === 0 || i === polyDist.length - 1 ? bucket.label : ""}
          </div>
        ))}
      </div>
    </>
  );
}
