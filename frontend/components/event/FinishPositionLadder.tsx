"use client";

// L2-116 RENDER ruling — golf finish-position markets (Top 5 / Top 10 / Top 20 /
// Make cut) render as a threshold-group ladder on the concept page. Each row is a
// competitor; each column is a placement question. The odds are the 0–100 POINT
// probabilities fused onto competitors by the golf aggregation
// (`top_5_prob`/`top_10_prob`/`top_20_prob`/`make_cut_prob`) — so no extra fetch.
// Probability-only, no source names, light tokens — same language as the
// leaderboard. Previously these markets were COUNTED by the header chip but had
// no renderer (invisible); this section makes "render everything you count" true.

// UX-1052 item 3: the DRAWING of this grid now lives in `PlacementGrid`, shared
// with the /sports feed card that replaced the five near-identical golf cards.
// Two surfaces asking one question ("who finishes where?") were about to grow
// two tables; the derivation below stays here because it is specific to the
// concept envelope, but the header, the cells, the "—" and the heat steps are
// one component.
import PlacementGrid from "@/components/PlacementGrid";
import {
  renderedFinishColumns,
  finishPositionRows,
} from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

interface FinishPositionLadderProps {
  data: EventConceptResponse;
  limit?: number;
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
      <PlacementGrid
        columns={columns.map((c) => ({ key: c.key, label: c.label }))}
        // The envelope fuses these as 0–100 POINTS; the shared grid speaks
        // fractions. Convert here rather than teaching the grid two scales.
        rows={rows.map(({ competitor, values }) => ({
          name: competitor.name,
          values: Object.fromEntries(
            columns.map((c) => [
              c.key,
              typeof values[c.key] === "number" ? (values[c.key] as number) / 100 : null,
            ]),
          ),
        }))}
      />
    </section>
  );
}
