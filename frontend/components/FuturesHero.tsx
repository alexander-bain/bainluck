"use client";

import { formatProbability } from "@/lib/api";

interface FuturesHeroProps {
  name: string;
  probability: number | null;
  outcomeName?: string;
  movement?: number | null;
  movementLabel?: string;
  sourceCount?: number;
  resolveDate?: string;
  categoryEmoji?: string;
  categoryLabel?: string;
  sparklinePoints?: number[];
  isMultiOutcome?: boolean;
  /** #883 L2-49: resolved (settled) market. Suppresses the live movement pill
   *  and labels the featured outcome as the final result, so a settled market
   *  never reads like an ongoing "58%". */
  resolved?: boolean;
  /** Whether the featured outcome won (for the resolved chip styling). */
  resolvedWon?: boolean;
}

export function FuturesHero({
  name,
  probability,
  outcomeName,
  movement,
  movementLabel,
  sourceCount,
  resolveDate,
  categoryEmoji,
  categoryLabel,
  sparklinePoints,
  isMultiOutcome,
  resolved = false,
  resolvedWon,
}: FuturesHeroProps) {
  const pct = probability != null ? Math.round(probability * 100) : null;
  const movementUp = movement != null && movement > 0;
  // Resolved markets show the final result, not a live movement pill.
  const movementStr =
    !resolved && movement != null && Math.abs(movement) >= 0.1
      ? `${movementUp ? "↑" : "↓"} ${Math.abs(movement).toFixed(1)} pts`
      : null;

  return (
    <div className="mb-6">
      {/* Category breadcrumb */}
      {categoryLabel && (
        <div className="flex items-center gap-2 mb-3 text-[11px] text-text-muted tracking-wide">
          {categoryEmoji && <span>{categoryEmoji}</span>}
          <span className="uppercase font-semibold tracking-[0.04em]">{categoryLabel}</span>
        </div>
      )}

      {/* Market title */}
      <h1 className="text-xl font-semibold leading-snug text-text-primary tracking-tight mb-4 max-w-2xl">
        {name}
      </h1>

      {/* Probability hero */}
      {pct != null && (
        <div className="flex items-end justify-between mb-3">
          <div>
            <div className="flex items-baseline gap-[1px] font-mono font-bold tracking-[-0.04em] text-text-primary leading-none">
              <span className="text-[56px]">{pct}</span>
              <span className="text-[26px]">%</span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              {outcomeName && (
                <span className="text-[13px] font-semibold text-text-primary">{outcomeName}</span>
              )}
              {resolved && (
                <span
                  className={`text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                    resolvedWon
                      ? "bg-accent-live/15 text-accent-live"
                      : "bg-text-muted/15 text-text-secondary"
                  }`}
                >
                  {resolvedWon ? "Won" : "Resolved"}
                </span>
              )}
              {movementStr && (
                <span
                  className={`font-mono text-[12px] font-bold ${
                    movementUp ? "text-accent-live" : "text-accent-danger"
                  }`}
                >
                  {movementStr}
                </span>
              )}
            </div>
          </div>

          {/* Mini sparkline */}
          {sparklinePoints && sparklinePoints.length >= 3 && (
            <svg viewBox="0 0 116 50" width={116} height={50} className="overflow-visible">
              <path
                d={sparklinePoints
                  .map((p, i) => {
                    const x = (i / (sparklinePoints.length - 1)) * 112 + 2;
                    const y = 48 - p * 46;
                    return `${i === 0 ? "M" : "L"}${x.toFixed(0)},${y.toFixed(0)}`;
                  })
                  .join(" ")}
                fill="none"
                stroke="var(--accent-brand)"
                strokeWidth={1.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {sparklinePoints.length > 0 && (
                <circle
                  cx={114}
                  cy={48 - sparklinePoints[sparklinePoints.length - 1] * 46}
                  r={2.6}
                  fill="var(--accent-brand)"
                />
              )}
            </svg>
          )}
        </div>
      )}

      {/* Yes/No probability bar */}
      {pct != null && !isMultiOutcome && (
        <div className="flex h-[9px] gap-0.5 mb-2">
          <div
            className="rounded-full bg-accent-brand shadow-inner"
            style={{ width: `${pct}%` }}
          />
          <div className="rounded-full bg-text-muted/30 flex-1" />
        </div>
      )}

      {/* Source aggregation footer */}
      {sourceCount != null && sourceCount > 0 && (
        <div className="flex items-center gap-2 mt-4 pt-3.5 border-t border-surface-border">
          <div className="flex gap-[2px]">
            {Array.from({ length: Math.min(sourceCount, 5) }).map((_, i) => (
              <span
                key={i}
                className="w-[5px] h-[5px] rounded-full bg-accent-futures"
                style={{ opacity: 1 - i * 0.2 }}
              />
            ))}
          </div>
          <span className="text-[12px] text-text-secondary">
            Aggregated from <strong className="text-text-primary font-semibold">{sourceCount} sources</strong>
          </span>
        </div>
      )}

      {/* Resolution date */}
      {resolveDate && (
        <div className="text-[11px] text-text-muted mt-2">{resolveDate}</div>
      )}
    </div>
  );
}
