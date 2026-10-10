"use client";

import { useState } from "react";
import type { MarketMapProps } from "../MarketMap";
import { ladderGraded, gradedLadderVisibleRows } from "../MarketMap";
import { posOnRail } from "@/lib/marketMapUtils";

export default function CompactMarketMap({
  title,
  subtitle,
  headline,
  rangeMin,
  rangeMax,
  density,
  axisLabels,
  zeroPosition,
  markers,
  ladder,
  status,
  bandDrawsShape,
  variant,
}: MarketMapProps) {
  const [expanded, setExpanded] = useState(false);
  const graded = ladderGraded(ladder);
  const gradedRows = gradedLadderVisibleRows(ladder);
  const nearest = [...ladder]
    .sort((a, b) => Math.abs(a.probability - 50) - Math.abs(b.probability - 50))
    .slice(0, 5);
  const shown = expanded
    ? ladder
    : ladder.filter((row, index) =>
        graded
          ? gradedRows == null || gradedRows.has(index)
          : nearest.includes(row),
      );
  // Resolved prices are not a pregame distribution. Final maps compare
  // the supplied expectation and final markers on a plain number line.
  const drawsDensity = bandDrawsShape && status !== "done";
  const carriesRail = drawsDensity || markers.length > 0;
  const peak = Math.max(...density, 0);
  const caption = graded
    ? "Each line vs the final"
    : `${status === "done" ? "Last quote" : "Chance"} of ${variant === "total" ? "going over" : "winning by"}`;
  return (
    <section className="bg-surface-card rounded-xl border border-surface-border p-4 sm:p-5">
      <div className="flex flex-wrap justify-between items-baseline gap-2">
        <h3 className="text-base font-semibold">{title}</h3>
        <span className="text-sm font-semibold text-text-primary">
          {headline}
        </span>
      </div>
      <p className="text-xs text-text-secondary mt-1">{subtitle}</p>
      <div className="grid sm:grid-cols-2 gap-4 sm:gap-8">
        <div>
          {carriesRail && (
            <div className="mt-4">
              <div className="relative h-16 mx-2" aria-hidden="true">
                {drawsDensity && peak > 0 && (
                  <svg
                    viewBox="0 0 100 40"
                    preserveAspectRatio="none"
                    className="absolute inset-0 w-full h-full text-accent-brand/25"
                  >
                    <path
                      fill="currentColor"
                      d={`M0 40 ${density.map((v, i) => `L${(i * 100) / Math.max(1, density.length - 1)} ${40 - (v / peak) * 36}`).join(" ")} L100 40 Z`}
                    />
                  </svg>
                )}
                <div className="absolute bottom-0 inset-x-0 h-px bg-surface-border" />
                {zeroPosition != null && (
                  <div
                    className="absolute inset-y-0 border-l border-dashed border-text-muted"
                    style={{
                      left: `${posOnRail(zeroPosition, rangeMin, rangeMax)}%`,
                    }}
                  />
                )}
                {markers.map((marker) => (
                  <div
                    key={marker.key}
                    className={`absolute bottom-0 w-1 rounded-t h-10 ${marker.type === "pre" ? "bg-text-muted" : marker.type === "actual" ? "bg-accent-brand" : "bg-text-primary"}`}
                    style={{
                      left: `${posOnRail(marker.value, rangeMin, rangeMax)}%`,
                    }}
                  />
                ))}
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] gap-3 text-xs text-text-secondary mt-2">
                <span>{axisLabels.left}</span>
                <span>{axisLabels.mid}</span>
                <span className="text-right">{axisLabels.right}</span>
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4">
            {markers
              .filter((m) => !m.hideTile)
              .map((marker) => (
                <div key={marker.key} className="flex items-baseline gap-2">
                  <span
                    className={`w-2 h-2 rounded-full ${marker.type === "pre" ? "bg-text-muted" : marker.type === "actual" ? "bg-accent-brand" : "bg-text-primary"}`}
                  />
                  <span className="text-xs text-text-secondary">
                    {marker.label}
                  </span>
                  <strong className="font-mono tabular-nums text-sm">
                    {marker.displayValue}
                  </strong>
                </div>
              ))}
          </div>
        </div>
        {ladder.length > 0 && (
          <div className="mt-4 border-t border-surface-border pt-3">
            <h4 className="text-xs font-medium text-text-secondary mb-2">
              {caption}
            </h4>
            {shown.map((row, index) => (
              <div
                key={`${row.label}-${index}`}
                className="grid grid-cols-[minmax(0,1fr)_minmax(40px,1fr)_auto] gap-3 items-center min-h-9 text-xs"
              >
                <span className="text-text-primary">{row.label}</span>
                {graded ? (
                  <span className="col-span-2 text-right font-medium">
                    {row.outcome === "cleared" ? "cleared" : "not cleared"}
                  </span>
                ) : (
                  <>
                    <div
                      aria-hidden="true"
                      className="h-1.5 rounded-full bg-surface-elevated overflow-hidden"
                    >
                      <div
                        className="h-full bg-accent-brand"
                        style={{ width: `${row.probability}%` }}
                      />
                    </div>
                    <strong className="font-mono tabular-nums w-10 text-right">
                      {row.probability}%
                    </strong>
                  </>
                )}
              </div>
            ))}
            {ladder.length > shown.length || expanded ? (
              <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="min-h-11 text-sm font-semibold text-text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
              >
                {expanded ? "Show fewer lines" : `All ${ladder.length} lines`}
              </button>
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}
