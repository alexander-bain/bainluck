"use client";

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

      {/* Resolved hero (#883 L2-53, Alex ruling): the winner name + "Won" chip is
          the story — NO big percentage on a settled market (the last-traded price
          read as a bug). The price journey stays in the trend chart below. */}
      {resolved && (
        <div className="mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            {outcomeName && (
              <span className="text-2xl font-semibold text-text-primary tracking-tight">{outcomeName}</span>
            )}
            <span
              className={`text-[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
                resolvedWon
                  ? "bg-accent-live/15 text-accent-live"
                  : "bg-text-muted/15 text-text-secondary"
              }`}
            >
              {resolvedWon ? "Won" : "Resolved"}
            </span>
          </div>
          {/* Upset note (pure copy, no new data): a low last price before winning. */}
          {resolvedWon && pct != null && pct < 25 && (
            <p className="text-[13px] text-text-secondary mt-1.5">Markets gave this just {pct}%.</p>
          )}
        </div>
      )}

      {/* Live probability hero (big blended number) — unresolved markets only.
          Hero C (L2-161, the design's declared ships variant): when the hero
          outcome's recent history is available, the 7-day curve sits *behind*
          the 64px numeral as ambient texture (area fill + faint line), hinting
          at the trend chart below without competing with it. The number stays
          the loudest thing on the page. Falls back cleanly to a plain numeral
          when there's no usable series. Ambient uses accent-brand — the single
          blended line, never a per-source overlay (blend-only ruling). */}
      {!resolved && pct != null && (
        <>
          {sparklinePoints && sparklinePoints.length >= 3 ? (
            <div className="relative h-[96px] mb-3">
              <AmbientHistory points={sparklinePoints} />
              <div className="absolute left-0 bottom-1 flex items-baseline gap-[1px] font-mono font-bold tracking-[-0.045em] text-text-primary leading-none">
                <span className="text-[64px]">{pct}</span>
                <span className="text-[28px]">%</span>
              </div>
              <div className="absolute right-0 bottom-2 flex flex-col items-end gap-1.5">
                {movementStr && (
                  <span
                    className={`inline-flex items-center font-mono text-[13px] font-bold px-2 py-0.5 rounded-full ${
                      movementUp
                        ? "text-accent-live bg-accent-live/15"
                        : "text-accent-danger bg-accent-danger/15"
                    }`}
                  >
                    {movementStr}
                  </span>
                )}
                {outcomeName && (
                  <span className="text-[13px] font-semibold text-text-primary">{outcomeName}</span>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-end justify-between mb-3">
              <div>
                <div className="flex items-baseline gap-[1px] font-mono font-bold tracking-[-0.045em] text-text-primary leading-none">
                  <span className="text-[64px]">{pct}</span>
                  <span className="text-[28px]">%</span>
                </div>
                <div className="flex items-center gap-2 mt-2">
                  {outcomeName && (
                    <span className="text-[13px] font-semibold text-text-primary">{outcomeName}</span>
                  )}
                  {movementStr && (
                    <span
                      className={`inline-flex items-center font-mono text-[12px] font-bold px-2 py-0.5 rounded-full ${
                        movementUp
                          ? "text-accent-live bg-accent-live/15"
                          : "text-accent-danger bg-accent-danger/15"
                      }`}
                    >
                      {movementStr}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* Yes/No probability bar — live only (a settled market shows no live bar) */}
      {!resolved && pct != null && !isMultiOutcome && (
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

/**
 * Ambient history layer (L2-161, Hero C). The hero outcome's recent probability
 * curve as quiet texture behind the numeral: a faint area fill + a 50%-opacity
 * line on a fixed 0–1 domain (no auto-scale — movement stays honestly
 * proportional, matching the trend chart's fixed-axis principle). accent-brand,
 * single blended line. Renders nothing below 3 points.
 */
function AmbientHistory({ points }: { points: number[] }) {
  if (points.length < 3) return null;
  const W = 392;
  const H = 96;
  const n = points.length;
  // Fixed 0–1 domain (top padding so the peak never clips the numeral baseline).
  const top = 8;
  const usable = H - top;
  const xy = points.map((p, i) => {
    const x = (i / (n - 1)) * W;
    const y = top + (1 - Math.min(1, Math.max(0, p))) * usable;
    return [x, y] as const;
  });
  const line = xy.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${W},${H} L0,${H} Z`;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="absolute inset-0 w-full h-full overflow-visible"
      aria-hidden
    >
      <path d={area} fill="var(--accent-brand)" fillOpacity={0.07} />
      <path
        d={line}
        fill="none"
        stroke="var(--accent-brand)"
        strokeOpacity={0.5}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
