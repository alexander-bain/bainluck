// The golf field row — the ranked list a reader sees after opening a tournament
// on `/categories/golf`.
//
// EXTRACTED FROM THE PAGE BY UX-P161, and not for tidiness. The guard beside it
// has to render THIS component (`reference_plant_must_hit_the_render`: a
// pure-lib assertion over `formatProbability` stayed green for the entire time
// this row printed `0%`), and a Next.js route file may only export the reserved
// names — exporting `GolferRow` from `app/categories/golf/page.tsx` fails the
// typecheck ratchet with `Property 'GolferRow' is incompatible with index
// signature`. The move is what makes the row testable at all.
//
// `MovementBadge`, `SOURCE_META`, `SOURCE_LABELS` and `SourceDots` came with it
// because the page used them for nothing else.

"use client";

import { formatProbability } from "@/lib/api";
import { sourceHex } from "@/lib/sourceColors";
import type { GolfGolfer } from "@/lib/types";

// ============================================================================
// Movement Badge
// ============================================================================

function MovementBadge({ movement }: { movement: number | null }) {
  if (movement === null || Math.abs(movement) < 0.005) return null;
  const isUp = movement > 0;
  const delta = Math.abs(Math.round(movement * 100));
  return (
    <span
      className={`text-[10px] font-medium px-1 py-0.5 rounded ${
        isUp
          ? "text-green-400 bg-green-400/10"
          : "text-red-400 bg-red-400/10"
      }`}
    >
      {isUp ? "\u25B2" : "\u25BC"}
      {delta}%
    </span>
  );
}

// ============================================================================
// Golfer Row
// ============================================================================

// Exported for the guard beside this page. A pure-lib assertion over
// `formatProbability` stays green even if this row goes back to printing its own
// `Math.round`, which is exactly the state the queue found — so the test renders
// THIS component (`reference_plant_must_hit_the_render`).
export function GolferRow({
  golfer,
  tournamentKey,
  showSourceBreakdown,
}: {
  golfer: GolfGolfer;
  tournamentKey: string;
  showSourceBreakdown?: boolean;
}) {
  // UX-P046's floor, finally reaching this surface: `pct` stays the GEOMETRY
  // (the bar below is a width, and a width may round to nothing), but the
  // printed number goes through `formatProbability` so a live golfer priced at
  // 0.3% reads `<1%` rather than `0%`. Measured on production 2026-08-29
  // (`GET /api/golf`): all 15 rows of the Rogers Charity Classic field printed
  // `0%` over real Kalshi odds of 0.003 — a ranked list telling the reader every
  // player in it is impossible.
  const pct = Math.round(golfer.probability * 100);
  const barWidth = Math.max(pct, 2);
  const isLeader = golfer.rank === 1;
  const sourceCount = Object.keys(golfer.sources).length;

  // Compute model-vs-market divergence
  const modelProb = golfer.sources["datagolf_model"];
  const marketProbs = Object.entries(golfer.sources)
    .filter(([k]) => SOURCE_META[k]?.type === "market")
    .map(([, v]) => v);
  const avgMarketProb =
    marketProbs.length > 0
      ? marketProbs.reduce((a, b) => a + b, 0) / marketProbs.length
      : null;
  const divergence =
    modelProb != null && avgMarketProb != null
      ? modelProb - avgMarketProb
      : null;
  const hasDivergence = divergence != null && Math.abs(divergence) > 0.03;

  return (
    <div>
      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-mono w-5 text-right ${
            isLeader ? "text-[#006747] font-bold" : "text-text-muted"
          }`}
        >
          {golfer.rank}
        </span>
        <span
          className={`text-sm flex-1 truncate ${
            isLeader ? "text-text-primary font-medium" : "text-text-secondary"
          }`}
        >
          {golfer.name}
        </span>
        {hasDivergence && (
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
              divergence! > 0
                ? "bg-amber-500/15 text-amber-400"
                : "bg-blue-500/15 text-blue-400"
            }`}
            title={`DataGolf model ${divergence! > 0 ? "higher" : "lower"} than market consensus by ${Math.round(Math.abs(divergence!) * 100)}%`}
          >
            {divergence! > 0 ? "Model +" : "Model "}
            {Math.round(divergence! * 100)}%
          </span>
        )}
        <MovementBadge movement={golfer.movement_24h} />
        <span className="text-sm font-mono text-text-primary w-10 text-right">
          {formatProbability(golfer.probability)}
        </span>
        {sourceCount > 1 && (
          <SourceDots sources={golfer.sources} />
        )}
      </div>
      <div className="ml-7 mr-16 mt-0.5 mb-0.5">
        <div className="h-1 bg-surface-elevated rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${barWidth}%`,
              backgroundColor: isLeader ? "#006747" : "#2d8659",
              opacity: isLeader ? 1 : 0.6,
            }}
          />
        </div>
      </div>
      {showSourceBreakdown && sourceCount > 1 && (
        <div className="ml-7 mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {Object.entries(golfer.sources)
            .sort(([, a], [, b]) => b - a)
            .map(([source, prob]) => {
              const meta = SOURCE_META[source];
              return (
                <span key={source} className="text-[10px] text-text-muted">
                  {source === "odds_api"
                    ? "Sportsbooks"
                    : source === "kalshi"
                      ? "Kalshi"
                      : source === "polymarket"
                        ? "Polymarket"
                        : source === "datagolf_model"
                          ? "DG Model"
                          : source}
                  {meta?.type === "model" && (
                    <span className="ml-0.5 text-amber-400/70 text-[9px]">M</span>
                  )}
                  {/* Same floor as the row above. A source that priced this
                      golfer at all must not be quoted as having priced them at
                      zero — the per-source line is the reader's evidence that
                      the number is real. */}
                  : {formatProbability(prob)}
                </span>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Source Dots
// ============================================================================

/** Source metadata: type (model vs market). Colors come from the one registry. */
const SOURCE_META: Record<string, { color: string; type: "model" | "market" }> = {
  odds_api: { color: sourceHex("odds_api"), type: "market" },
  kalshi: { color: sourceHex("kalshi"), type: "market" },
  polymarket: { color: sourceHex("polymarket"), type: "market" },
  datagolf_model: { color: sourceHex("datagolf_model"), type: "model" },
};

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  datagolf_model: "DG Model",
};

function SourceDots({ sources }: { sources: Record<string, number> }) {
  return (
    <div className="flex gap-1 items-center">
      {Object.keys(sources).map((s) => {
        const meta = SOURCE_META[s];
        const label = SOURCE_LABELS[s] || s;
        const pct = (sources[s] * 100).toFixed(1);
        return (
          <span
            key={s}
            title={`${label}: ${pct}%`}
            className={`w-1.5 h-1.5 rounded-full inline-block cursor-help ${
              meta?.type === "model" ? "ring-1 ring-amber-400/50" : ""
            }`}
            style={{ backgroundColor: meta?.color || "#6b7280" }}
          />
        );
      })}
    </div>
  );
}
