"use client";

import { useMemo, useState } from "react";
import type { DivisionRace, DivisionRaceSortKey } from "@/lib/teamDivisionRace";
import { sortDivisionRows } from "@/lib/teamDivisionRace";

// ---------------------------------------------------------------------------
// Division-race grid (L2-162). Compact rivals × (Division / Playoffs / Champion)
// table, sortable, with the current team's row highlighted in team color.
// Renders nothing when the race can't be shown honestly (caller passes null).
// Mobile-first: the table scrolls horizontally inside a card on narrow screens.
// ---------------------------------------------------------------------------

function pct(v: number | null): string {
  return v === null ? "—" : `${Math.round(v * 100)}%`;
}

function SortHeader({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-right text-[10px] font-semibold uppercase tracking-wide transition-colors ${
        active ? "text-text-primary" : "text-text-muted hover:text-text-secondary"
      }`}
    >
      {label} {active ? "↓" : ""}
    </button>
  );
}

export function TeamDivisionRace({
  race,
  teamColor,
}: {
  race: DivisionRace;
  teamColor: string | null;
}) {
  const [sortKey, setSortKey] = useState<DivisionRaceSortKey>("championship");
  const rows = useMemo(() => sortDivisionRows(race.rows, sortKey), [race.rows, sortKey]);

  // Column layout adapts to which columns actually carry data.
  const cols: { key: DivisionRaceSortKey; label: string; show: boolean }[] = [
    { key: "division", label: "Division", show: race.hasDivision },
    { key: "playoffs", label: "Playoffs", show: race.hasPlayoffs },
    { key: "championship", label: "Champion", show: race.hasChampionship },
  ];
  const shown = cols.filter((c) => c.show);
  // L2-174 Item 3c — settled-means-settled: when the championship column is
  // decided, the grid is graded. Crown the champion (championship === 1) and mark
  // the header FINAL instead of framing it as a live race.
  const isSettled = race.championshipResolved;
  const championName = isSettled
    ? rows.find((r) => (r.championship ?? 0) >= 0.999)?.name ?? null
    : null;
  // L2-164: the name column used to be `minmax(120px,1fr)`, so on a wide card it
  // flex-grew to absorb ALL leftover width — shoving the number columns to the far
  // right and opening the dead space Alex flagged. Now the name column hugs its
  // content and a trailing `1fr` spacer soaks up the extra width AFTER the numbers,
  // so team names and their numbers sit together on the left.
  const gridCols = `minmax(110px,max-content) ${shown.map(() => "3.5rem").join(" ")} minmax(0,1fr)`;

  return (
    <section className="mb-8">
      <h2 className="flex items-center gap-2 text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        <span>Division Race · {race.divisionLabel}</span>
        {race.season && (
          <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold tracking-wide text-text-muted normal-case">
            {race.season}
          </span>
        )}
        {isSettled && (
          <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-[10px] font-semibold tracking-wide text-text-muted">
            FINAL
          </span>
        )}
      </h2>
      <div className="bg-surface-card border border-surface-border rounded-card overflow-x-auto">
        <div className="min-w-[360px]">
          {/* Header row */}
          <div
            className="grid items-center px-4 py-2.5 border-b border-surface-border gap-2"
            style={{ gridTemplateColumns: gridCols }}
          >
            <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
              Team
            </span>
            {shown.map((c) => (
              <SortHeader
                key={c.key}
                label={c.label}
                active={sortKey === c.key}
                onClick={() => setSortKey(c.key)}
              />
            ))}
          </div>
          {/* Body rows */}
          {rows.map((row) => (
            <div
              key={`${row.teamId ?? row.name}`}
              className="grid items-center px-4 py-2.5 border-b border-surface-border/60 gap-2 last:border-b-0"
              style={{
                gridTemplateColumns: gridCols,
                ...(row.isTeam && teamColor
                  ? {
                      backgroundColor: `${teamColor}0D`,
                      borderLeft: `3px solid ${teamColor}`,
                    }
                  : {}),
              }}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="w-5 h-5 rounded flex items-center justify-center text-[8px] font-bold text-white flex-shrink-0"
                  style={{ backgroundColor: row.color || "#6B7280" }}
                >
                  {row.shortName.slice(0, 3).toUpperCase()}
                </span>
                <span
                  className={`text-[13px] truncate ${
                    row.isTeam ? "font-bold text-text-primary" : "font-medium text-text-secondary"
                  }`}
                >
                  {row.name}
                </span>
                {championName === row.name && (
                  <span className="flex-shrink-0" title="Champion" aria-label="Champion">
                    🏆
                  </span>
                )}
              </div>
              {shown.map((c) => (
                <span
                  key={c.key}
                  className="text-right font-mono font-bold text-sm text-text-primary tabular-nums"
                >
                  {pct(row[c.key])}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
