"use client";

import { useMemo, useState, type CSSProperties } from "react";
import type { DivisionRace, DivisionRaceRow, DivisionRaceSortKey } from "@/lib/teamDivisionRace";
import { DIVISION_RACE_STATUS_KEY, sortDivisionRows } from "@/lib/teamDivisionRace";
import { GRID_CELL_TERMINAL_GLYPH } from "@/lib/gridCellState";
import { probabilityCellText } from "@/lib/probabilityCellText";

// ---------------------------------------------------------------------------
// Division-race grid (L2-162). Compact rivals × (Division / Playoffs / Champion)
// table, sortable, with the current team's row highlighted in team color.
// Renders nothing when the race can't be shown honestly (caller passes null).
// Mobile-first: the table scrolls horizontally inside a card on narrow screens.
// ---------------------------------------------------------------------------

// #7710 — these cells ARE the playoffs grid's cells, so they print what it
// prints.
//
// `buildDivisionRace` builds this table from `GET /api/playoffs/{league}`, the
// same payload `/playoffs/mlb` renders through `probabilityCellText` (#7670,
// #7692). This renderer had its own bare `Math.round(v * 100)`, so the two
// surfaces gave a reader two different answers for one number: measured on
// production 2026-09-21, of 52 live MLB grid cells, five sat strictly inside
// (0, 1) and printed `0%` here while the playoffs page printed `0.4%` / `<0.1%`
// for the same cell. Baltimore's `pennant` and `championship` at `0.0005` and
// Toronto's `championship` at `0.0035` each appear on all five AL East team
// pages, under the `✕` we use for clubs that really are out.
//
// So: `probabilityCellText`, not `formatProbabilityPercent`. The grid keeps the
// decimal where the decimal is the whole of the information. The row-shaped
// cards on this page (`TeamChampionshipPath`, `TeamPropFamilies`) speak the
// other vocabulary, which is why the split is stated in both places.
//
// The terminal states never reach here — `cellContent` returns the ✓/✕ glyph
// first — so a number arriving at this function is a live one, and `100%` stays
// reserved for the cells whose payload states an absolute.
function pct(v: number | null): string {
  return v === null ? "—" : probabilityCellText(v);
}

/**
 * What one column of one row shows, and what a screen reader hears (#7522).
 *
 * "Settled means settled": a club that has clinched shows the same ✓ the
 * championship grids show, and one that is out shows the same ✕ — never a
 * number, and never the "—" that means "we have nothing". The em-dash is
 * reserved for exactly that: no market, or a cell we cannot vouch for.
 *
 * The glyph carries its meaning in `aria-label`/`title` rather than in text
 * beside it: the column is 3.5rem wide at every breakpoint (#7023 measured what
 * happens when something widens it), so "✓ Clinched" would wrap the header and
 * re-flow every number on the row.
 */
function cellContent(
  row: DivisionRaceRow,
  key: DivisionRaceSortKey,
): { text: string; label: string | null; tone: string } {
  const status = row[DIVISION_RACE_STATUS_KEY[key]];
  if (status === "clinched") {
    return {
      text: GRID_CELL_TERMINAL_GLYPH.clinched,
      label: "Clinched",
      tone: "text-emerald-600",
    };
  }
  if (status === "eliminated") {
    return {
      text: GRID_CELL_TERMINAL_GLYPH.eliminated,
      label: "Eliminated",
      tone: "text-text-secondary/40",
    };
  }
  const value = row[key];
  return {
    text: pct(value),
    label: value === null ? "No market" : null,
    // Same tones the championship grids use for the same states, so an "—" we
    // have nothing for cannot read as LOUDER than a result we are sure of.
    tone: value === null ? "text-text-secondary/40" : "text-text-primary",
  };
}

// #7023: the sort marker used to be a trailing "↓" INSIDE the label. It only ever
// points down (`sortDivisionRows` has no direction toggle), so it said nothing the
// colour did not — and it cost 15px in a 56px column, which wrapped "CHAMPION ↓"
// onto two lines and made the header row change height whenever a reader sorted by
// a different column. The active column is now marked by colour + an underline,
// neither of which takes horizontal space, and the label never wraps.
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
      aria-pressed={active}
      className={`text-right text-[10px] font-semibold uppercase tracking-wide whitespace-nowrap transition-colors ${
        active
          ? "text-text-primary underline decoration-2 underline-offset-4"
          : "text-text-muted hover:text-text-secondary"
      }`}
    >
      {label}
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
  // #7522 — the champion used to be found by `championship >= 0.999`. A won cell
  // publishes NO number by contract, so the moment the producer started sending
  // real results (#7387) the crown would have gone to nobody on exactly the
  // grids that had a champion to crown. Read the result first, keep the numeric
  // test for producers that still send 1.0 without a state.
  const championName = isSettled
    ? rows.find(
        (r) => r.championshipStatus === "clinched" || (r.championship ?? 0) >= 0.999,
      )?.name ?? null
    : null;
  // L2-164: the name column used to be `minmax(120px,1fr)`, so on a wide card it
  // flex-grew to absorb ALL leftover width — shoving the number columns to the far
  // right and opening the dead space Alex flagged. Now the name column hugs its
  // content and a trailing `1fr` spacer soaks up the extra width AFTER the numbers,
  // so team names and their numbers sit together on the left.
  //
  // #7023: this template is declared ONCE, on the table, and every line subgrids
  // onto it. It used to be set on each line separately, and `max-content` is
  // resolved per grid container — so a row whose team name was long resolved a
  // wider name track than a row whose name was short, and every number after it
  // slid right. Measured on production 2026-09-18: the AFC East table put its four
  // `%` columns at four different x positions (18px apart at 390px, 50px at
  // 1280px), and the header labels sat 18px left of the numbers they label.
  const gridCols = `minmax(0,max-content) ${shown.map(() => "3.5rem").join(" ")} minmax(0,1fr)`;
  // Shared by the header line and every row via `--divrace-cols` (globals.css).
  const lineStyle = { "--divrace-cols": gridCols } as CSSProperties;

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
      <div className="bg-surface-card border border-surface-border rounded-card overflow-x-auto scroll-shadow-x">
        <div
          data-divrace-table
          className="min-w-[280px] grid gap-x-1.5 sm:gap-x-2"
          style={{ gridTemplateColumns: gridCols }}
        >
          {/* Header row */}
          <div
            className="divrace-line items-center px-3 sm:px-4 py-2.5 border-b border-surface-border"
            style={lineStyle}
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
              className="divrace-line items-center px-3 sm:px-4 py-2.5 border-b border-surface-border/60 last:border-b-0"
              style={{
                ...lineStyle,
                ...(row.isTeam && teamColor
                  ? {
                      backgroundColor: `${teamColor}0D`,
                      // #7023: an inset shadow, not `border-left`. A border on a
                      // subgrid line insets that line's tracks by its width, so a
                      // 3px accent would shift this one row's numbers 3px left of
                      // every other row's. The shadow paints the same 3px bar and
                      // takes no layout.
                      boxShadow: `inset 3px 0 0 0 ${teamColor}`,
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
              {shown.map((c) => {
                const cell = cellContent(row, c.key);
                return (
                  <span
                    key={c.key}
                    className={`text-right font-mono font-bold text-sm tabular-nums ${cell.tone}`}
                    {...(cell.label ? { title: cell.label, "aria-label": cell.label } : {})}
                  >
                    {cell.text}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
