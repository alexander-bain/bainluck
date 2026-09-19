"use client";

import Link from "next/link";
import type { ChampionshipPathEntry } from "@/lib/api";
import { pathSeason } from "@/lib/teamSeason";
import { teamTextColor } from "@/lib/teamColors";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";

// ---------------------------------------------------------------------------
// Championship-path progression (L2-162). The team's path to a title shown as a
// connected Division → Conference → Championship progression (each step harder
// than the last), replacing the flat 3-card grid. Team color drives the number
// + bar accent. Steps deep-link to the underlying futures market.
// ---------------------------------------------------------------------------

// Progression order runs easiest → hardest. Backend tiers: 4 = Division,
// 2 = Conference/Pennant, 1 = Championship. We render in that ascending
// difficulty order regardless of the payload's tier ordering.
//
// #1752: this card carried the caption "Each step conditions on the one before
// it." It is false — a wild card reaches a conference final without winning its
// division — and the payload proves it: of the 47 teams that serve BOTH a
// division and a conference step, 14 (30%) are INVERTED, the division number
// below the conference one (measured on production 2026-09-19). The caption was
// invisible while `championship_path` was empty for every team; the moment that
// was repaired it would have appeared, false, on 332 pages. Removed rather than
// reworded — D34: the reader gets the labels and the numbers, not method prose.
const PROGRESSION_ORDER = [4, 2, 1];

function orderForProgression(
  entries: ChampionshipPathEntry[],
): ChampionshipPathEntry[] {
  return [...entries].sort(
    (a, b) => PROGRESSION_ORDER.indexOf(a.tier) - PROGRESSION_ORDER.indexOf(b.tier),
  );
}

function Step({
  entry,
  color,
}: {
  entry: ChampionshipPathEntry;
  color: string | null;
}) {
  const pct = entry.probability !== null ? Math.round(entry.probability * 100) : null;
  return (
    <Link
      href={`/futures/${entry.market_id}`}
      className="flex-1 min-w-[110px] flex flex-col gap-1.5 group"
    >
      <span className="text-[11px] font-semibold text-text-secondary group-hover:text-text-primary transition-colors">
        Win {entry.label}
      </span>
      <div className="flex items-baseline gap-1.5">
        <span
          className="font-mono font-bold text-2xl leading-none tabular-nums"
          style={{ color: teamTextColor(color) || undefined }}
        >
          {pct !== null ? `${pct}%` : "—"}
        </span>
        {/* UX-P275: `!== 0` admitted a move that rounds to nothing, so a rounding
            residue produced a coloured "+0.0". `isRenderedMove` gates on the
            printed string instead. */}
        {isRenderedMove(entry.movement) && (
          <span
            className={`text-[11px] font-mono ${
              entry.movement! > 0 ? "text-accent-live" : "text-accent-danger"
            }`}
          >
            {/* #5659 — the unit, for the same reason as the ladder rungs. This
                one is the worst-placed of the family: the bare number sits in
                the SAME flex row as `{pct}%` rendered at text-2xl, so "+9.7"
                reads as a percentage by direct association with the number
                beside it rather than merely by column. */}
            {entry.movement! > 0 ? "+" : "-"}
            {formatMovementPoints(entry.movement)} pts
          </span>
        )}
      </div>
      <div className="h-1 rounded-full bg-surface-elevated overflow-hidden">
        <div
          style={{
            width: `${pct ?? 0}%`,
            backgroundColor: color || undefined,
          }}
          className={color ? "h-full" : "h-full bg-accent-brand"}
        />
      </div>
    </Link>
  );
}

export function TeamChampionshipPath({
  entries,
  color,
}: {
  entries: ChampionshipPathEntry[];
  color: string | null;
}) {
  const ordered = orderForProgression(entries);
  // L2-169: season chip bound to #242's per-entry season — declares which season
  // the path describes, rendered only when the entries agree on one (else hidden).
  const season = pathSeason(entries);
  return (
    <div className="bg-surface-card border border-surface-border rounded-card p-5 flex flex-col gap-3.5">
      <div className="flex items-center gap-2">
        <span className="text-[15px] font-semibold text-text-primary">Championship path</span>
        {season && (
          <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold tracking-wide text-text-muted">
            {season}
          </span>
        )}
      </div>
      <div className="flex items-stretch gap-2 flex-wrap">
        {ordered.map((entry, i) => (
          <div key={entry.tier} className="flex items-center gap-2 flex-1 min-w-[110px]">
            <Step entry={entry} color={color} />
            {i < ordered.length - 1 && (
              <span className="text-text-muted text-sm flex-shrink-0" aria-hidden>
                →
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
