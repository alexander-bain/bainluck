"use client";

import { type CityData, tempColorC, toC, SOURCES } from "./data";
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
  const kalshiPeakIdx = kalshiDist
    ? kalshiDist.reduce((best, b, i) => (b.prob > kalshiDist[best].prob ? i : best), 0)
    : -1;

  const allProbs = [
    ...dist.map(b => b.prob),
    ...(kalshiDist ? kalshiDist.map(b => b.prob) : []),
  ];
  const maxProb = Math.max(...allProbs);

  return (
    <div
      className="bg-white flex flex-col border border-surface-border"
      style={{ borderRadius: 16, padding: 22, minHeight: 460 }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div
            className="font-mono"
            style={{
              fontSize: 11,
              color: "#9CA3AF",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 4,
            }}
          >
            {city.region}
          </div>
          <div style={{ fontSize: 24, fontWeight: 600, color: "#111827" }}>
            {city.name}
          </div>
        </div>
        {isCrossSource ? <CrossSourceBadge /> : <SourceBadge src={city.srcs[0]} />}
      </div>

      {/* Subtitle */}
      <div
        className="font-mono"
        style={{ fontSize: 12, color: "#9CA3AF", marginTop: 8 }}
      >
        Tomorrow&apos;s high temperature &middot; Apr 20, 2026
      </div>

      {/* Peak display */}
      <div className="flex items-baseline" style={{ marginTop: 20, gap: 4 }}>
        <span
          className="font-mono"
          style={{ fontSize: 64, fontWeight: 700, color, lineHeight: 1 }}
        >
          {modeDisplay}
        </span>
        <span style={{ fontSize: 28, fontWeight: 500, color, lineHeight: 1 }}>
          &deg;{unit}
        </span>
      </div>

      <div className="flex items-baseline" style={{ marginTop: 8, gap: 8 }}>
        <span
          className="font-mono"
          style={{ fontSize: 20, fontWeight: 600, color: "#374151" }}
        >
          {peak.prob}%
        </span>
        <span style={{ fontSize: 12, color: "#9CA3AF" }}>
          most likely bucket
        </span>
      </div>

      <div style={{ fontSize: 13, color: "#6B7280", marginTop: 6, marginBottom: 16 }}>
        {peak.label} is the modal outcome
      </div>

      {/* Histogram */}
      <div className="flex-1 flex flex-col justify-end">
        {isCrossSource && kalshiDist ? (
          <CrossSourceHistogram
            polyDist={dist}
            kalshiDist={kalshiDist}
            maxProb={maxProb}
            polyPeakIdx={peakIdx}
            kalshiPeakIdx={kalshiPeakIdx}
          />
        ) : (
          <SingleSourceHistogram
            dist={dist}
            maxProb={maxProb}
            peakIdx={peakIdx}
            color={color}
          />
        )}
      </div>

      {/* Legend + Footer */}
      {isCrossSource && (
        <div
          className="flex items-center justify-center gap-4"
          style={{ marginTop: 10, fontSize: 11, color: "#6B7280" }}
        >
          <span className="flex items-center gap-1.5">
            <span style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: SOURCES.polymarket.color, opacity: 0.55 }} />
            Polymarket (11 buckets)
          </span>
          <span className="flex items-center gap-1.5">
            <span style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: SOURCES.kalshi.color, opacity: 0.55 }} />
            Kalshi (6 buckets)
          </span>
        </div>
      )}

      <div
        className="font-mono"
        style={{ fontSize: 11, color: "#9CA3AF", marginTop: isCrossSource ? 8 : 16, textAlign: "center" }}
      >
        Click any pin on the map
        {!isCrossSource && ` · ${dist.length} outcome buckets (${city.srcs.length === 1 ? SOURCES[city.srcs[0]].label : "Polymarket"})`}
      </div>
    </div>
  );
}

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
              className="flex-1 flex flex-col items-center justify-end"
              style={{ height: "100%" }}
            >
              {isPeak && (
                <div className="font-mono" style={{ fontSize: 11, fontWeight: 600, color: "#374151", marginBottom: 4 }}>
                  {bucket.prob}%
                </div>
              )}
              <div
                style={{
                  width: "100%",
                  height: `${barHeight}%`,
                  minHeight: bucket.prob > 0 ? 2 : 0,
                  backgroundColor: isPeak ? color : color + "55",
                  borderRadius: "3px 3px 0 0",
                  transition: "height 300ms ease",
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex" style={{ gap: 2, marginTop: 4 }}>
        {dist.map((bucket, i) => (
          <div
            key={i}
            className="flex-1 text-center font-mono"
            style={{ fontSize: 9, color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {bucket.label}
          </div>
        ))}
      </div>
    </>
  );
}

function CrossSourceHistogram({
  polyDist,
  kalshiDist,
  maxProb,
  polyPeakIdx,
  kalshiPeakIdx,
}: {
  polyDist: Array<{ label: string; prob: number }>;
  kalshiDist: Array<{ label: string; prob: number }>;
  maxProb: number;
  polyPeakIdx: number;
  kalshiPeakIdx: number;
}) {
  const polyColor = SOURCES.polymarket.color;
  const kalshiColor = SOURCES.kalshi.color;

  const polyCount = polyDist.length;
  const kalshiCount = kalshiDist.length;
  const totalSlots = polyCount;

  const kalshiBarWidth = totalSlots / kalshiCount;

  return (
    <>
      <div style={{ position: "relative", height: 140 }}>
        {/* Polymarket bars (front, narrower, blue) */}
        <div
          className="flex items-end"
          style={{ position: "absolute", inset: 0, gap: 2, zIndex: 2 }}
        >
          {polyDist.map((bucket, i) => {
            const barHeight = maxProb > 0 ? (bucket.prob / maxProb) * 100 : 0;
            const isPeak = i === polyPeakIdx;
            return (
              <div
                key={i}
                className="flex-1 flex flex-col items-center justify-end"
                style={{ height: "100%" }}
              >
                {isPeak && (
                  <div
                    className="font-mono"
                    style={{ fontSize: 10, fontWeight: 600, color: SOURCES.polymarket.fg, marginBottom: 3 }}
                  >
                    {bucket.prob}%
                  </div>
                )}
                <div
                  style={{
                    width: "70%",
                    height: `${barHeight}%`,
                    minHeight: bucket.prob > 0 ? 2 : 0,
                    backgroundColor: polyColor,
                    opacity: isPeak ? 0.7 : 0.4,
                    borderRadius: "2px 2px 0 0",
                    transition: "height 300ms ease",
                  }}
                />
              </div>
            );
          })}
        </div>

        {/* Kalshi bars (back, wider, green) */}
        <div
          className="flex items-end"
          style={{ position: "absolute", inset: 0, zIndex: 1 }}
        >
          {kalshiDist.map((bucket, i) => {
            const barHeight = maxProb > 0 ? (bucket.prob / maxProb) * 100 : 0;
            const isPeak = i === kalshiPeakIdx;
            const widthPct = (kalshiBarWidth / totalSlots) * 100;
            return (
              <div
                key={i}
                className="flex flex-col items-center justify-end"
                style={{ width: `${widthPct}%`, height: "100%" }}
              >
                {isPeak && (
                  <div
                    className="font-mono"
                    style={{ fontSize: 10, fontWeight: 600, color: SOURCES.kalshi.fg, marginBottom: 3 }}
                  >
                    {bucket.prob}%
                  </div>
                )}
                <div
                  style={{
                    width: "85%",
                    height: `${barHeight}%`,
                    minHeight: bucket.prob > 0 ? 2 : 0,
                    backgroundColor: kalshiColor,
                    opacity: isPeak ? 0.55 : 0.25,
                    borderRadius: "3px 3px 0 0",
                    transition: "height 300ms ease",
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* X-axis: show Polymarket labels (finer grain) */}
      <div className="flex" style={{ gap: 2, marginTop: 4 }}>
        {polyDist.map((bucket, i) => (
          <div
            key={i}
            className="flex-1 text-center font-mono"
            style={{ fontSize: 9, color: "#9CA3AF", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {bucket.label}
          </div>
        ))}
      </div>
    </>
  );
}
