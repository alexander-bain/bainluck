"use client";

// L2-116 RENDER ruling — golf finish-position markets (Top 5 / Top 10 / Top 20 /
// Make cut) render as a threshold-group ladder on the concept page. Each row is a
// competitor; each column is a placement question. The odds are the 0–100 POINT
// probabilities fused onto competitors by the golf aggregation
// (`top_5_prob`/`top_10_prob`/`top_20_prob`/`make_cut_prob`) — so no extra fetch.
// Probability-only, no source names, light tokens — same language as the
// leaderboard. Previously these markets were COUNTED by the header chip but had
// no renderer (invisible); this section makes "render everything you count" true.

import {
  renderedFinishColumns,
  finishPositionRows,
} from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

interface FinishPositionLadderProps {
  data: EventConceptResponse;
  limit?: number;
}

/** Format a 0–100 point probability as a whole-percent, "—" when absent. */
function fmtPts(v: number | null): string {
  return v == null ? "—" : `${Math.round(v)}%`;
}

/** Colour a placement probability like the win column: brand for the confident
 *  end, muted for the long shots — a light heat gradient without raw palette. */
function ptsClass(v: number | null): string {
  if (v == null) return "text-text-muted";
  if (v >= 50) return "text-text-primary font-semibold";
  if (v >= 15) return "text-text-primary";
  return "text-text-secondary";
}

export default function FinishPositionLadder({
  data,
  limit = 20,
}: FinishPositionLadderProps) {
  const columns = renderedFinishColumns(data);
  if (columns.length === 0) return null;
  const rows = finishPositionRows(data, columns, limit);
  if (rows.length === 0) return null;

  // Grid: player name + one column per rendered placement question. Horizontal
  // scroll on mobile (a 5-column table doesn't fit a phone), grid on desktop.
  return (
    <section
      id="finish"
      className="bg-surface-card rounded-card shadow-card p-6"
    >
      <h2 className="text-title-3 font-semibold text-text-primary mb-1">
        Finish position
      </h2>
      <p className="text-xs text-text-muted mb-4">
        Chance to finish inside each cutoff.
      </p>
      <div className="overflow-x-auto -mx-1 px-1">
        <div className="min-w-[22rem]">
          {/* Column header */}
          <div className="flex items-center gap-2 px-1 pb-1.5 text-[10px] uppercase tracking-wide text-text-muted">
            <span className="flex-1 min-w-0">Player</span>
            {columns.map((col) => (
              <span
                key={col.type}
                className="w-16 text-right shrink-0"
              >
                {col.label}
              </span>
            ))}
          </div>
          <div className="divide-y divide-surface-border/40">
            {rows.map(({ competitor, values }, i) => (
              <div
                key={`${competitor.name}-${i}`}
                className="flex items-center gap-2 py-2 text-sm"
              >
                <span className="flex-1 min-w-0 truncate text-text-primary">
                  {competitor.name}
                </span>
                {columns.map((col) => (
                  <span
                    key={col.type}
                    className={`w-16 text-right shrink-0 font-mono tabular-nums ${ptsClass(
                      values[col.key],
                    )}`}
                  >
                    {fmtPts(values[col.key])}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
