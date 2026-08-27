/**
 * THE PLAYOFF GRID — players × rounds, the chance of reaching each.
 *
 * UX-P138, Alex's STRUCTURAL RULING 4: "Bracket tab = the PLAYOFF GRID —
 * players × rounds with the probability of reaching each, exactly like the
 * league playoff tables." Adopted. UX-P136 already measured why the tree
 * cannot be the answer on a phone (a 128 draw is ~1,360px wide and ~3,450px
 * tall in its first column alone at a 390px viewport), and UX-P137's answer —
 * one round at a time — turned the tab into a second match list. Ruling 4
 * removes the duplicate and gives the tab the one question a tree is actually
 * read for: **how far does this player get.**
 *
 * ALEX'S RULING 8 folds into this one: the advance-to-round questions ("Does
 * Gauff reach the semifinals?") are NOT props. They are cells. They were being
 * rendered as eight near-identical cards in a section reserved for interesting
 * questions, which is both the wrong home and the "repeating template" the
 * same ruling forbids. Here each one is a number in a column, which is what it
 * always was.
 *
 * ═══ THE ONE RULE THIS FILE IS BUILT AROUND: NO CELL IS EVER COMPUTED. ═══
 *
 * Every number in this grid is a price somebody quoted for exactly the
 * question its column asks. Nothing is multiplied, chained, or simulated.
 * That constraint is not fastidiousness — a grid of P(reach round N) is
 * *trivial* to fill by walking the draw and multiplying match odds, it would
 * look completely plausible, it would be dense where this one is sparse, and
 * every number in it would be a model output rendered in the type this app
 * reserves for a market price. The charter's reliability doctrine calls that
 * class by name: a projection that looks exactly like a result.
 *
 * So there are exactly three sources, and each answers its column literally:
 *
 *   1. **The next round** — the player's own undecided match price. If the
 *      market says Gauff wins today's match at 78%, then Gauff reaches the
 *      next round at 78%. Same question, same market, no arithmetic. This is
 *      the dense column.
 *   2. **A curated round** — the register's "Does <player> reach the <round>?"
 *      market, priced. Eight of these exist today across both draws. This is
 *      the sparse middle.
 *   3. **The title** — the championship board's own number, the same one the
 *      board and the chart print. Dense.
 *
 * Anything else is a hole, and a hole prints as a hole.
 */

import { ROUND_NAMES, reachColumnLabel, type RoundName } from "./bracket";
import { advanceMarketsForRound } from "./advanceToStage";
import type { MatchListEntry, MatchRoundKey } from "./matchList";
import type { PropMarket } from "./tournamentProps";
import type { TournamentBoardData } from "./tournament";

/**
 * ALEX'S RULING 3, applied. "Priced to get there" is gambling vocabulary —
 * *priced* is a trading verb and *get there* is a bet's payoff condition. This
 * is the probability sentence for the same fact.
 *
 * Runners-up considered and rejected, so the choice is arguable rather than
 * asserted: "Odds of reaching" (odds is the exact word the site's own
 * no-price-format rule exists to avoid), "How far they get" (a claim about the
 * future stated as fact), "Progression" (accurate, and jargon).
 */
export const GRID_SECTION_LABEL = "Chance of reaching";

/**
 * The title column is a DIFFERENT QUESTION and gets a different word.
 *
 * "Reach the final" and "win the title" are two markets, and one of them is
 * strictly harder. A grid whose last column silently switched from reaching to
 * winning under a shared header would be the exact defect UX-P137's ruling 2
 * was issued about, re-committed one tab over.
 */
export const GRID_TITLE_COLUMN_LABEL = "To win the title";

/**
 * How many reach columns fit a 390px phone beside the name.
 *
 * Measured against the layout rather than chosen: 390 − 32px page padding
 * = 358; the name column needs ~118px before a real surname truncates
 * ("Sørensen" with a seed badge); each numeric column needs 46px for `100%` in
 * tabular figures with breathing room. 118 + 4×46 = 302, plus gaps. Four
 * numeric columns fit and five do not. The last is always the title, so three
 * reach columns is the ceiling.
 *
 * THE CAP IS NEVER SILENT. `buildPlayoffGrid` reports `droppedColumns`, and
 * the component says how many rounds it is not showing. A grid that quietly
 * hid the semi-finals would read as "nobody prices the semi-finals".
 */
export const GRID_MAX_REACH_COLUMNS = 3;

export type GridCellState = "priced" | "unpriced" | "reached" | "out";

export interface GridCell {
  probability: number | null;
  isLive: boolean;
  state: GridCellState;
  /** Which of the three sources filled it — for the legend and for the guard. */
  origin: "match" | "curated" | "board" | null;
}

export interface GridRow {
  entityKey: string;
  displayName: string;
  seed: number | null;
  rank: number;
  cells: Record<string, GridCell>;
}

export interface GridColumn {
  key: MatchRoundKey | "title";
  /** "QF" — the header a phone can fit. */
  shortLabel: string;
  /** "To reach the quarter-finals" — the sentence, for `title=` and sr-only. */
  longLabel: string;
  kind: "reach" | "title";
}

export interface PlayoffGrid {
  columns: GridColumn[];
  rows: GridRow[];
  /** How many cells actually carry a number — the honesty counter. */
  pricedCells: number;
  totalCells: number;
  /** Reach rounds we hold prices for but could not fit. Never silent. */
  droppedColumns: GridColumn[];
}

/** The round a player reaches by WINNING a match in this one. `null` after the final. */
export function roundAfter(round: MatchRoundKey): RoundName | null {
  if (round === "qualifying") return "R128";
  const index = ROUND_NAMES.indexOf(round);
  if (index < 0 || index === ROUND_NAMES.length - 1) return null;
  return ROUND_NAMES[index + 1];
}

/**
 * "To reach the quarter-finals" — the column's full sentence (UX-P137, ruling
 * 2). Re-exported from `bracket.ts` rather than restated: two modules owning
 * one column's wording is how the two surfaces end up disagreeing about what a
 * number means, which is the defect ruling 2 was issued about.
 */
export { reachColumnLabel };

const SHORT_LABELS: Record<RoundName, string> = {
  R128: "R128",
  R64: "R64",
  R32: "R32",
  R16: "R16",
  QF: "QF",
  SF: "SF",
  F: "Final",
};

export interface NextRoundOdd {
  round: RoundName;
  probability: number;
  isLive: boolean;
}

/**
 * "Win your current match" = "reach the next round", read straight off the
 * match list.
 *
 * The only join that could go wrong here is the round arithmetic, so it is one
 * lookup in a fixed array rather than a computation: winning in the Round of
 * 64 reaches the Round of 32, and `roundAfter` has its own test in both
 * directions. A DECIDED match contributes nothing — its price has collapsed to
 * 1 or 0 and "100% to reach the next round" is a result wearing a forecast's
 * clothes.
 */
export function nextRoundOdds(entries: MatchListEntry[]): Record<string, NextRoundOdd> {
  const out: Record<string, NextRoundOdd> = {};
  for (const entry of entries) {
    if (entry.decided || !entry.coherent) continue;
    const round = roundAfter(entry.round);
    if (round === null) continue;
    for (const side of entry.sides) {
      if (side.entityKey === null) continue;
      if (side.matchProbability === null || !Number.isFinite(side.matchProbability)) continue;
      const existing = out[side.entityKey];
      // A player with two undecided matches in the feed is a data fault, not a
      // schedule. Keep the EARLIER round: it is the hurdle they face first, and
      // a grid that skipped it would claim a round had been reached.
      if (existing && ROUND_NAMES.indexOf(existing.round) <= ROUND_NAMES.indexOf(round)) {
        continue;
      }
      out[side.entityKey] = {
        round,
        probability: side.matchProbability,
        isLive: entry.isLive,
      };
    }
  }
  return out;
}

/**
 * Rounds a player has already reached, and the round they went out in.
 *
 * Empty on real data — we hold no results (see `SlateMatch.score`). The seam
 * exists so a reached cell can print a tick instead of a stale forecast the
 * day results land; until then every cell is a forecast or a hole, and the
 * grid says which.
 */
export interface GridProgress {
  reached: Record<string, RoundName[]>;
  outAt: Record<string, RoundName>;
}

export function gridProgressFromMatches(entries: MatchListEntry[]): GridProgress {
  const reached: Record<string, RoundName[]> = {};
  const outAt: Record<string, RoundName> = {};
  for (const entry of entries) {
    if (!entry.decided) continue;
    const next = roundAfter(entry.round);
    for (const side of entry.sides) {
      if (side.entityKey === null) continue;
      if (side.isWinner) {
        if (next !== null) {
          const list = reached[side.entityKey] ?? [];
          if (!list.includes(next)) list.push(next);
          reached[side.entityKey] = list;
        }
      } else if (entry.round !== "qualifying") {
        outAt[side.entityKey] = entry.round;
      }
    }
  }
  return { reached, outAt };
}

/**
 * The grid.
 *
 * Rows follow the BOARD's order, which is the title ranking, because that is
 * the order every other surface on this page already uses and two rankings of
 * one field is a divergence bug wearing a layout decision. Unpriced board rows
 * are kept: a registered player with no title price may still have a match
 * price today, and dropping them would make the dense column sparse.
 */
export function buildPlayoffGrid(options: {
  board: TournamentBoardData | null;
  propMarkets?: PropMarket[];
  matches?: MatchListEntry[];
  draw: string;
  progress?: GridProgress;
  maxReachColumns?: number;
}): PlayoffGrid {
  const board = options.board;
  const empty: PlayoffGrid = {
    columns: [],
    rows: [],
    pricedCells: 0,
    totalCells: 0,
    droppedColumns: [],
  };
  if (!board || board.rows.length === 0) return empty;

  const maxReach = options.maxReachColumns ?? GRID_MAX_REACH_COLUMNS;
  const matches = options.matches ?? [];
  const nextOdds = nextRoundOdds(matches);
  const progress = options.progress ?? gridProgressFromMatches(matches);

  /** (entityKey, round) -> curated advance market price. */
  const curated = new Map<string, { probability: number; isLive: boolean }>();
  for (const round of ROUND_NAMES) {
    for (const entry of advanceMarketsForRound(options.propMarkets ?? [], round, options.draw)) {
      // `advanceSubject` recovers a SURNAME from the curated question ("Does
      // Alcaraz reach the semifinals?" -> "Alcaraz"); the board carries full
      // names. Matching on the board row whose name ends with the subject is
      // the join, and it is deliberately strict about direction: a subject
      // must be a suffix of exactly one board name or the cell is dropped. A
      // curated market attached to the wrong player is worse than one attached
      // to nobody, because it renders as a confident answer.
      const subject = entry.displayName.trim().toLowerCase();
      const candidates = board.rows.filter((row) => {
        const name = row.display_name.trim().toLowerCase();
        return name === subject || name.endsWith(` ${subject}`);
      });
      if (candidates.length !== 1) continue;
      curated.set(`${candidates[0].entity_key}|${round}`, {
        probability: entry.probability,
        isLive: entry.isLive,
      });
    }
  }

  // Which reach rounds are worth a column: any round some cell can fill.
  const roundsWithData = ROUND_NAMES.filter((round) => {
    if (Object.values(nextOdds).some((odd) => odd.round === round)) return true;
    for (const row of board.rows) {
      if (curated.has(`${row.entity_key}|${round}`)) return true;
      if ((progress.reached[row.entity_key] ?? []).includes(round)) return true;
    }
    return false;
  });

  const reachColumns: GridColumn[] = roundsWithData.map((round) => ({
    key: round,
    shortLabel: SHORT_LABELS[round],
    longLabel: reachColumnLabel(round),
    kind: "reach" as const,
  }));

  const kept = reachColumns.slice(0, maxReach);
  const droppedColumns = reachColumns.slice(maxReach);

  const titleColumn: GridColumn = {
    key: "title",
    shortLabel: "Title",
    longLabel: GRID_TITLE_COLUMN_LABEL,
    kind: "title",
  };
  const columns = [...kept, titleColumn];

  let pricedCells = 0;
  const rows: GridRow[] = board.rows.map((row) => {
    const cells: Record<string, GridCell> = {};
    const isOut = progress.outAt[row.entity_key] !== undefined;

    for (const column of kept) {
      const round = column.key as RoundName;
      if ((progress.reached[row.entity_key] ?? []).includes(round)) {
        cells[column.key] = {
          probability: null,
          isLive: false,
          state: "reached",
          origin: null,
        };
        continue;
      }
      if (isOut) {
        cells[column.key] = { probability: null, isLive: false, state: "out", origin: null };
        continue;
      }
      const own = nextOdds[row.entity_key];
      if (own && own.round === round) {
        cells[column.key] = {
          probability: own.probability,
          isLive: own.isLive,
          state: "priced",
          origin: "match",
        };
        pricedCells += 1;
        continue;
      }
      const hit = curated.get(`${row.entity_key}|${round}`);
      if (hit) {
        cells[column.key] = {
          probability: hit.probability,
          isLive: hit.isLive,
          state: "priced",
          origin: "curated",
        };
        pricedCells += 1;
        continue;
      }
      cells[column.key] = { probability: null, isLive: false, state: "unpriced", origin: null };
    }

    if (isOut) {
      cells.title = { probability: null, isLive: false, state: "out", origin: null };
    } else if (row.probability !== null && Number.isFinite(row.probability)) {
      cells.title = {
        probability: row.probability,
        isLive: row.probability_is_live === true,
        state: "priced",
        origin: "board",
      };
      pricedCells += 1;
    } else {
      cells.title = { probability: null, isLive: false, state: "unpriced", origin: null };
    }

    return {
      entityKey: row.entity_key,
      displayName: row.display_name,
      seed: row.seed,
      rank: row.rank,
      cells,
    };
  });

  return {
    columns,
    rows,
    pricedCells,
    totalCells: rows.length * columns.length,
    droppedColumns,
  };
}

/** `58%`, or `null` — the caller renders the hole, so it can say what a hole is. */
export function formatGridCell(cell: GridCell): string | null {
  if (cell.state === "reached") return "✓";
  if (cell.state === "out") return "—";
  if (cell.probability === null || !Number.isFinite(cell.probability)) return null;
  return `${Math.round(cell.probability * 100)}%`;
}
