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
  const gridCols = `minmax(120px,1fr) ${shown.map(() => "72px").join(" ")}`;

  return (
    <section className="mb-8">
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        Division Race · {race.divisionLabel}
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
