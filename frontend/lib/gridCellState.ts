/**
 * Championship-grid cell state normalization (L2-227).
 *
 * Queue 295 replaced the grid's runtime fuzzy market matching with explicit
 * per-league registers, and the serving payload now carries a typed `state` on
 * every cell. A registered cell can be:
 *
 *   live         — trading, carries a probability
 *   won          — authoritative terminal result (register `settled`/`won`)
 *   eliminated   — authoritative terminal result (register `settled`/`eliminated`)
 *   missing      — registered, but the source market is not currently there
 *   unavailable  — the cell cannot be vouched for (malformed / out-of-contract)
 *
 * These are the five reader states frozen by the C108 contract corpus
 * (`backend/tests/evals/fixtures/grid_register_contract.json` →
 * `application_repair_contract.reader_states`).
 *
 * This module is the single place the web app turns a raw payload cell into a
 * render decision, and it is deliberately fail-closed: anything it cannot
 * positively read as a live 0–1 probability renders as an honest empty state
 * rather than a number. That is what stops the two failure modes the register
 * exists to kill — a settled cell still showing a live-looking percentage, and
 * a missing cell silently rendering as 50% (or as a stale last-good value).
 *
 * Identity/rendering only: no ranking, blending, probability, or weighting
 * decision lives here.
 */

import type { ChampionshipGridCellSource } from "./types";

export type GridCellState =
  | "live"
  | "won"
  | "eliminated"
  | "missing"
  | "unavailable";

/** Accessible / tooltip name for each state. */
export const GRID_CELL_STATE_LABEL: Record<GridCellState, string> = {
  live: "Live probability",
  won: "Clinched",
  eliminated: "Eliminated",
  missing: "No market",
  unavailable: "Unavailable",
};

export interface RenderedGridCell {
  state: GridCellState;
  /** Non-null ONLY when state === "live". */
  probability: number | null;
  /** Non-null ONLY when state === "live". */
  trend24h: number | null;
  sources: ChampionshipGridCellSource[];
  isMinimumTick: boolean;
}

/**
 * The `status` vocabulary carried by `ProgressionParticipant`. `null` means
 * "live" and predates the register, so it stays the default for every producer
 * that does not know about grid cell states (the golf category page, the
 * backend's own progression endpoint).
 */
export type ProgressionCellStatus =
  | "clinched"
  | "eliminated"
  | "missing"
  | "unavailable"
  | null;

const TERMINAL_STATES = new Set<GridCellState>(["won", "eliminated"]);

/** A probability is only usable if it is a real number inside [0, 1]. */
function readProbability(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (value < 0 || value > 1) return null;
  return value;
}

function readTrend(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

/**
 * Drop source rows we cannot render. A poison source entry must not be able to
 * turn a tooltip into "NaN%" or throw while mapping.
 */
function readSources(value: unknown): ChampionshipGridCellSource[] {
  if (!Array.isArray(value)) return [];
  const out: ChampionshipGridCellSource[] = [];
  for (const raw of value) {
    if (!raw || typeof raw !== "object") continue;
    const s = raw as Record<string, unknown>;
    const probability = readProbability(s.probability);
    if (typeof s.source !== "string" || !s.source || probability === null) continue;
    out.push({ source: s.source, probability });
  }
  return out;
}

/**
 * Read the payload's declared state. Returns `undefined` when the payload does
 * not declare one at all (pre-register cached responses), and "unavailable"
 * when it declares something outside the contract — an unrecognized state is a
 * cell we cannot vouch for, not a cell we should guess about.
 */
function readDeclaredState(value: unknown): GridCellState | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return "unavailable";
  switch (value) {
    case "live":
    case "won":
    case "eliminated":
    case "missing":
    case "unavailable":
      return value;
    // The backend register vocabulary is won/eliminated; "clinched" is the
    // web/native display word for the same thing. Accept it so a future
    // producer using the display word cannot silently degrade to unavailable.
    case "clinched":
      return "won";
    default:
      return "unavailable";
  }
}

/**
 * Normalize one raw grid cell into an honest render decision.
 *
 * Never throws: a poison cell (null, string, array, wrong-typed fields) is a
 * "missing"/"unavailable" cell, so one bad cell can never blank a row or take
 * down the page.
 */
export function renderGridCell(raw: unknown): RenderedGridCell {
  const empty = (state: GridCellState): RenderedGridCell => ({
    state,
    probability: null,
    trend24h: null,
    sources: [],
    isMinimumTick: false,
  });

  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return empty("missing");
  }

  const cell = raw as Record<string, unknown>;
  const declared = readDeclaredState(cell.state);
  const probability = readProbability(cell.merged_probability);
  const sources = readSources(cell.sources);
  const isMinimumTick = cell.is_minimum_tick === true;

  // Terminal cells carry a result, never a number — "settled means settled".
  if (declared && TERMINAL_STATES.has(declared)) {
    return { ...empty(declared), sources, isMinimumTick };
  }

  if (declared === "missing" || declared === "unavailable") {
    return { ...empty(declared), sources, isMinimumTick };
  }

  if (declared === "live") {
    // A live cell with no usable number cannot be shown as live. Fail closed.
    if (probability === null) return { ...empty("unavailable"), sources, isMinimumTick };
    return {
      state: "live",
      probability,
      trend24h: readTrend(cell.trend_24h),
      sources,
      isMinimumTick,
    };
  }

  // No declared state (pre-register payload): infer from the number alone.
  if (probability === null) return { ...empty("missing"), sources, isMinimumTick };
  return {
    state: "live",
    probability,
    trend24h: readTrend(cell.trend_24h),
    sources,
    isMinimumTick,
  };
}

/** The per-stage maps a `ProgressionParticipant` is built from. */
export interface ProgressionCellMaps {
  probabilities: Record<string, number | null>;
  changes_24h: Record<string, number | null>;
  status: Record<string, ProgressionCellStatus>;
  sources_data: Record<string, ChampionshipGridCellSource[]>;
  minimum_ticks: Record<string, boolean>;
}

/**
 * Turn one championship-grid team's `cells` map into the per-stage maps the
 * progression table renders from. Shared by /playoffs/[sport] and
 * /sport/[sport]/[league] so the five grids cannot drift apart.
 *
 * Never throws — a poison `cells` value yields empty maps, and a poison cell
 * yields an honest empty cell, so one bad entry cannot blank a row.
 */
export function gridCellsToProgression(cells: unknown): ProgressionCellMaps {
  const out: ProgressionCellMaps = {
    probabilities: {},
    changes_24h: {},
    status: {},
    sources_data: {},
    minimum_ticks: {},
  };
  if (!cells || typeof cells !== "object" || Array.isArray(cells)) return out;

  for (const [colKey, rawCell] of Object.entries(cells as Record<string, unknown>)) {
    const cell = renderGridCell(rawCell);
    out.probabilities[colKey] = cell.probability;
    out.changes_24h[colKey] = cell.trend24h;
    out.status[colKey] = progressionStatusFor(cell.state);
    if (cell.sources.length) out.sources_data[colKey] = cell.sources;
    if (cell.isMinimumTick) out.minimum_ticks[colKey] = true;
  }
  return out;
}

/** Map a render state onto the `ProgressionParticipant.status` vocabulary. */
export function progressionStatusFor(state: GridCellState): ProgressionCellStatus {
  switch (state) {
    case "won":
      return "clinched";
    case "eliminated":
      return "eliminated";
    case "missing":
      return "missing";
    case "unavailable":
      return "unavailable";
    case "live":
    default:
      return null;
  }
}

/**
 * Sort weight for a stage cell.
 *
 * Terminal results have no probability, so sorting on the raw number alone
 * would file a clinched champion below a 0.1% longshot. A won cell sorts as
 * certainty, everything without a number sorts below every live cell — which
 * is exactly where `?? -1` already put them. Live cells are unchanged, so this
 * is display fidelity for terminal states, not a ranking change.
 */
export function progressionSortValue(
  probability: number | null | undefined,
  status: ProgressionCellStatus,
): number {
  if (status === "clinched") return 1;
  if (status === "eliminated" || status === "missing" || status === "unavailable") return -1;
  return typeof probability === "number" && Number.isFinite(probability) ? probability : -1;
}
