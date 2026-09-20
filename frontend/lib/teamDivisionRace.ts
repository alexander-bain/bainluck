/**
 * Pure helpers that turn a league championship-grid payload into the team page's
 * "Division race" grid (L2-162).
 *
 * The team endpoint doesn't ship rival probabilities, but the existing
 * `/api/playoffs/{slug}` championship grid already carries every team's per-stage
 * merged probability plus `division`/`conference` metadata. We reuse it: filter
 * to the current team's division WITHIN ITS CONFERENCE (#6992 — the division name
 * alone is not a unique pool in MLB), project the Division / Playoffs / Champion
 * columns, and mark the current team's row so the page can highlight it.
 *
 * Kept side-effect-free and SSR-safe so it is unit-testable and generalizes
 * across MLB/NBA/NFL/NHL without any league-specific branching.
 */
import type { ChampionshipGridResponse, ChampionshipGridTeam } from "./types";
import type { ProgressionCellStatus } from "./gridCellState";
import {
  isTerminalStatus,
  progressionSortValue,
  progressionStatusFor,
  renderGridCell,
} from "./gridCellState";

export type DivisionRaceSortKey = "division" | "playoffs" | "championship";
export type DivisionRaceStatusKey =
  | "divisionStatus"
  | "playoffsStatus"
  | "championshipStatus";

/** The status field that belongs to each probability field. */
export const DIVISION_RACE_STATUS_KEY: Record<DivisionRaceSortKey, DivisionRaceStatusKey> = {
  division: "divisionStatus",
  playoffs: "playoffsStatus",
  championship: "championshipStatus",
};

export interface DivisionRaceRow {
  teamId: number | null;
  name: string;
  shortName: string;
  color: string | null;
  logoUrl: string | null;
  isTeam: boolean;
  /**
   * 0–1 merged probabilities; null when the column is absent for this team AND
   * null, by contract, whenever the paired status is terminal — a settled cell
   * states a result and publishes no number. Read the status before concluding
   * a null here means "no data" (#7522).
   */
  division: number | null;
  playoffs: number | null;
  championship: number | null;
  /**
   * The render state of each column, from the same `renderGridCell` the two
   * championship grids use. `null` is the live/no-state default, so a payload
   * that predates the register behaves exactly as it did before.
   */
  divisionStatus: ProgressionCellStatus;
  playoffsStatus: ProgressionCellStatus;
  championshipStatus: ProgressionCellStatus;
}

export interface DivisionRace {
  divisionLabel: string;
  /** Season label (e.g. "2026-27") for the header SEASON CHIP. Null/absent when
   *  the grid payload doesn't carry one — the chip is then gracefully hidden, never
   *  guessed (#241 backend provides it). */
  season: string | null;
  rows: DivisionRaceRow[];
  /** Which of the projected columns actually have data (drives header render). */
  hasDivision: boolean;
  hasPlayoffs: boolean;
  hasChampionship: boolean;
  /** L2-174 Item 3c — settled-means-settled on race grids. True when the
   *  championship column is fully decided (every team at 0/1); the grid then
   *  renders GRADED — the champion crowned, not a live probability race. */
  championshipResolved: boolean;
}

function normName(s: string | null | undefined): string {
  return (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * Project one payload cell onto the row's (probability, status) pair.
 *
 * #7522 — this used to read `merged_probability` and nothing else. A terminal
 * cell carries `{"merged_probability": null, "state": "won"}` by contract, so a
 * club that had CLINCHED landed on the same null as "no market" and the page
 * printed "—" for it: the strongest answer we had, rendered as the absence of
 * one. Routing through `renderGridCell` — the single place the web app turns a
 * raw cell into a render decision, already used by both championship grids —
 * keeps the number for live cells and carries the result for settled ones, so
 * the three grids cannot say different things about the same cell.
 */
function cellOf(
  team: ChampionshipGridTeam,
  key: string,
): { probability: number | null; status: ProgressionCellStatus } {
  const raw = team.cells?.[key];
  // An absent column is not an honest "no market" verdict about this club — it
  // is simply a column this grid does not project. Keep the pre-register
  // behaviour (a bare null, no status) so `hasDivision` & co. still hide it.
  if (raw === undefined) return { probability: null, status: null };
  const cell = renderGridCell(raw);
  return {
    probability: cell.state === "live" ? cell.probability : null,
    status: progressionStatusFor(cell.state),
  };
}

/** Locate the current team within the grid by id first, then normalized name. */
function findTeam(
  teams: ChampionshipGridTeam[],
  teamId: number,
  teamName: string,
): ChampionshipGridTeam | null {
  const byId = teams.find((t) => t.team_id != null && t.team_id === teamId);
  if (byId) return byId;
  const target = normName(teamName);
  return teams.find((t) => normName(t.name) === target) ?? null;
}

/**
 * Build the division-race grid for a team, or null when it can't be shown
 * honestly (grid missing, team not in grid, or team has no division peers).
 * Rows are sorted by `sortKey` descending (defaults to championship), with the
 * current team's division taken from the grid metadata.
 */
export function buildDivisionRace(
  grid: ChampionshipGridResponse | null | undefined,
  teamId: number,
  teamName: string,
  sortKey: DivisionRaceSortKey = "championship",
): DivisionRace | null {
  if (!grid || grid.error || !Array.isArray(grid.teams) || grid.teams.length === 0) {
    return null;
  }
  const me = findTeam(grid.teams, teamId, teamName);
  if (!me || !me.division) return null;

  // #6992 — the pool is the (conference, division) PAIR, not the division name.
  // MLB serves `division` UNQUALIFIED ("East"/"Central"/"West") with the league in
  // `conference`, so keying on the name alone matched BOTH leagues' East: ten teams,
  // two ~certain division leaders (Rays 94% and Braves 98%), and a DIVISION column
  // summing to 206%. All three MLB divisions, all 30 team pages. NFL pre-qualifies
  // its names ("AFC East") and NBA/NHL names are unique across conferences, so the
  // extra clause narrows nothing there — measured on all four live grids.
  // Fail open when the grid doesn't carry OUR conference: we cannot narrow honestly,
  // and comparing against a null would drop every peer and silently empty the
  // section. Same rule the `div_rank` label already follows on the team page — a
  // number must name the pool it was counted over.
  const peers = grid.teams.filter(
    (t) => t.division === me.division && (!me.conference || t.conference === me.conference),
  );
  if (peers.length < 2) return null;

  const meId = me.team_id;
  const meNorm = normName(me.name);
  const rows: DivisionRaceRow[] = peers.map((t) => {
    const isTeam =
      (meId != null && t.team_id === meId) ||
      (meId == null && normName(t.name) === meNorm);
    const division = cellOf(t, "division");
    const playoffs = cellOf(t, "make_playoffs");
    const championship = cellOf(t, "championship");
    return {
      teamId: t.team_id,
      name: t.name,
      shortName: t.short_name || t.name,
      color: t.primary_color,
      logoUrl: t.logo_url,
      isTeam,
      division: division.probability,
      playoffs: playoffs.probability,
      championship: championship.probability,
      divisionStatus: division.status,
      playoffsStatus: playoffs.status,
      championshipStatus: championship.status,
    };
  });

  const sorted = sortDivisionRows(rows, sortKey);

  // The championship column carries a derived `resolved` flag (#927): true when
  // every team is decided (0/1). When it's set the labeled season is over, so the
  // race grid renders graded with the champion crowned rather than a live race.
  const champCol = Array.isArray(grid.columns)
    ? grid.columns.find((c) => c.key === "championship")
    : undefined;
  const championshipResolved = champCol?.resolved === true;

  return {
    divisionLabel: me.division,
    // Only surface a real season string; empty/whitespace collapses to null so the
    // chip stays hidden rather than rendering a blank pill.
    season: typeof grid.season === "string" && grid.season.trim() ? grid.season.trim() : null,
    rows: sorted,
    // #7522 — a column counts as present when ANY row has a number OR a result.
    // Testing the number alone was safe only while terminal cells were being
    // deleted upstream; now that they are published, a division whose race is
    // over carries a number nowhere and the whole column would have vanished
    // from the page at the exact moment it became certain.
    hasDivision: columnHasContent(rows, "division"),
    hasPlayoffs: columnHasContent(rows, "playoffs"),
    hasChampionship: columnHasContent(rows, "championship"),
    championshipResolved,
  };
}

/** True when any row in this column carries a number or a settled result. */
function columnHasContent(rows: DivisionRaceRow[], key: DivisionRaceSortKey): boolean {
  const statusKey = DIVISION_RACE_STATUS_KEY[key];
  return rows.some((r) => r[key] !== null || isTerminalStatus(r[statusKey]));
}

/**
 * Sort rows by a column descending; cells with nothing to say sink to the
 * bottom. Stable enough.
 *
 * #7522 — a clinched cell has no number, so sorting on the number alone filed
 * the one club that had already won the thing BELOW every longshot still
 * quoting 0.1%. `progressionSortValue` is the same weighting the championship
 * grids use: clinched sorts as certainty, eliminated/missing/unavailable sort
 * where a null already sorted. Live rows are untouched.
 */
export function sortDivisionRows(
  rows: DivisionRaceRow[],
  sortKey: DivisionRaceSortKey,
): DivisionRaceRow[] {
  const statusKey = DIVISION_RACE_STATUS_KEY[sortKey];
  return [...rows].sort(
    (a, b) =>
      progressionSortValue(b[sortKey], b[statusKey]) -
      progressionSortValue(a[sortKey], a[statusKey]),
  );
}
