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
  const maxProb = Math.max(...dist.map((b) => b.prob));
  const isCrossSource = city.srcs.length > 1;

  const unit = city.high.unit === "C" ? "C" : "F";
  const modeDisplay = Math.round(city.high.mode);

  const bucketCount = dist.length;
  const srcLabel =
    city.srcs.length === 1 ? SOURCES[city.srcs[0]].label : "Polymarket";

  return (
    <div
      className="bg-white flex flex-col"
      style={{ borderRadius: 16, padding: 22, minHeight: 460 }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div
            style={{
              fontFamily: "monospace",
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
        {isCrossSource ? (
          <CrossSourceBadge />
        ) : (
          <SourceBadge src={city.srcs[0]} />
        )}
      </div>

      {/* Subtitle */}
      <div
        style={{
          fontFamily: "monospace",
          fontSize: 12,
          color: "#9CA3AF",
          marginTop: 8,
        }}
      >
        Tomorrow&apos;s high temperature &middot; Apr 20, 2026
      </div>

      {/* Peak display */}
      <div className="flex items-baseline" style={{ marginTop: 20, gap: 4 }}>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 64,
            fontWeight: 700,
            color,
            lineHeight: 1,
          }}
        >
          {modeDisplay}
        </span>
        <span
          style={{
            fontSize: 28,
            fontWeight: 500,
            color,
            lineHeight: 1,
          }}
        >
          &deg;{unit}
        </span>
      </div>

      <div className="flex items-baseline" style={{ marginTop: 8, gap: 8 }}>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 20,
            fontWeight: 600,
            color: "#374151",
          }}
        >
          {peak.prob}%
        </span>
        <span style={{ fontSize: 12, color: "#9CA3AF" }}>
          most likely bucket
        </span>
      </div>

      {/* Caption */}
      <div
        style={{
          fontSize: 13,
          color: "#6B7280",
          marginTop: 6,
          marginBottom: 16,
        }}
      >
        {peak.label} is the modal outcome
      </div>

      {/* Histogram */}
      <div className="flex-1 flex flex-col justify-end">
        <div className="flex items-end" style={{ height: 140, gap: 2 }}>
          {dist.map((bucket, i) => {
            const isPeak = i === peakIdx;
            const barHeight =
              maxProb > 0 ? (bucket.prob / maxProb) * 100 : 0;

            return (
              <div
                key={i}
                className="flex-1 flex flex-col items-center justify-end"
                style={{ height: "100%" }}
              >
                {/* Floating percentage label on peak */}
                {isPeak && (
                  <div
                    style={{
                      fontFamily: "monospace",
                      fontSize: 11,
                      fontWeight: 600,
                      color: "#374151",
                      marginBottom: 4,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {bucket.prob}%
                  </div>
                )}
                <div
                  style={{
                    width: "100%",
                    height: `${barHeight}%`,
                    minHeight: bucket.prob > 0 ? 2 : 0,
                    backgroundColor: isPeak ? color : color + "33",
                    borderRadius: "3px 3px 0 0",
                    transition: "height 300ms ease",
                  }}
                />
              </div>
            );
          })}
        </div>

        {/* X-axis labels */}
        <div className="flex" style={{ gap: 2, marginTop: 4 }}>
          {dist.map((bucket, i) => (
            <div
              key={i}
              className="flex-1 text-center"
              style={{
                fontFamily: "monospace",
                fontSize: 9,
                color: "#9CA3AF",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {bucket.label}
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div
        style={{
          fontFamily: "monospace",
          fontSize: 11,
          color: "#9CA3AF",
          marginTop: 16,
          textAlign: "center",
        }}
      >
        Click any pin on the map &middot; {bucketCount} outcome buckets (
        {srcLabel})
      </div>
    </div>
  );
}
