"use client";

import Link from "next/link";
import type { ChampionshipPathEntry } from "@/lib/api";
import { pathSeason } from "@/lib/teamSeason";

// ---------------------------------------------------------------------------
// Championship-path progression (L2-162). The team's path to a title shown as a
// connected Division → Conference → Championship progression (each step harder
// than the last), replacing the flat 3-card grid. Team color drives the number
// + bar accent. Steps deep-link to the underlying futures market.
// ---------------------------------------------------------------------------

// Progression order runs easiest → hardest. Backend tiers: 4 = Division,
// 2 = Conference/Pennant, 1 = Championship. We render in that ascending
// difficulty order regardless of the payload's tier ordering.
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
          style={{ color: color || undefined }}
        >
          {pct !== null ? `${pct}%` : "—"}
        </span>
        {entry.movement !== null && entry.movement !== 0 && (
          <span
            className={`text-[11px] font-mono ${
              entry.movement > 0 ? "text-accent-live" : "text-accent-danger"
            }`}
          >
            {entry.movement > 0 ? "+" : ""}
            {(entry.movement * 100).toFixed(1)}
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
      <span className="text-xs text-text-muted">
        Each step conditions on the one before it.
      </span>
    </div>
  );
}
