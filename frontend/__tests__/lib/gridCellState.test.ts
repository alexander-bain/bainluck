// L2-227: the championship grid's cell-state normalizer.
//
// The vocabulary under test is frozen by the C108 contract corpus
// (backend/tests/evals/fixtures/grid_register_contract.json →
// application_repair_contract.reader_states + rendered_state_matrix). The rule
// this file exists to hold: only a live cell may carry a number. Everything
// else — settled, missing, malformed — renders a state, never a probability.

import {
  renderGridCell,
  progressionStatusFor,
  progressionSortValue,
  GRID_CELL_STATE_LABEL,
  type GridCellState,
} from "../../lib/gridCellState";

// The five leagues share one adapter and one renderer, so the state table is
// league-independent; the league axis is exercised at the page level in
// gridRegisterRendering.test.tsx.
const LEAGUES = ["nba", "nhl", "mlb", "nfl", "golf"] as const;

describe("renderGridCell — C108 rendered_state_matrix", () => {
  const CASES: {
    name: string;
    raw: unknown;
    state: GridCellState;
    probability: number | null;
  }[] = [
    {
      name: "register live → live with its number",
      raw: { merged_probability: 0.22, sources: [], trend_24h: 0.01, state: "live" },
      state: "live",
      probability: 0.22,
    },
    {
      name: "register settled/won → won, no number",
      raw: { merged_probability: null, sources: [], trend_24h: null, state: "won" },
      state: "won",
      probability: null,
    },
    {
      name: "register settled/eliminated → eliminated, no number",
      raw: { merged_probability: null, sources: [], trend_24h: null, state: "eliminated" },
      state: "eliminated",
      probability: null,
    },
    {
      name: "register missing → missing, no number",
      raw: { merged_probability: null, sources: [], trend_24h: null, state: "missing" },
      state: "missing",
      probability: null,
    },
    {
      name: "register unavailable → unavailable, no number",
      raw: { merged_probability: null, sources: [], trend_24h: null, state: "unavailable" },
      state: "unavailable",
      probability: null,
    },
  ];

  test.each(CASES)("$name", ({ raw, state, probability }) => {
    const cell = renderGridCell(raw);
    expect(cell.state).toBe(state);
    expect(cell.probability).toBe(probability);
  });

  test("a terminal cell NEVER keeps a stale probability, even if the payload sends one", () => {
    for (const state of ["won", "eliminated"]) {
      const cell = renderGridCell({ merged_probability: 0.97, trend_24h: 0.4, state });
      expect(cell.state).toBe(state);
      expect(cell.probability).toBeNull();
      expect(cell.trend24h).toBeNull();
    }
  });

  test("a missing cell never renders 50% or any other fallback number", () => {
    const cell = renderGridCell({ merged_probability: 0.5, state: "missing" });
    expect(cell.state).toBe("missing");
    expect(cell.probability).toBeNull();
  });
});

describe("renderGridCell — fail-closed on malformed input", () => {
  const POISON: { name: string; raw: unknown }[] = [
    { name: "null cell", raw: null },
    { name: "undefined cell", raw: undefined },
    { name: "string cell", raw: "0.42" },
    { name: "number cell", raw: 0.42 },
    { name: "array cell", raw: [0.42] },
    { name: "empty object", raw: {} },
  ];

  test.each(POISON)("$name → missing, no number, no throw", ({ raw }) => {
    const cell = renderGridCell(raw);
    expect(cell.state).toBe("missing");
    expect(cell.probability).toBeNull();
    expect(cell.sources).toEqual([]);
  });

  const UNVOUCHABLE: { name: string; raw: unknown }[] = [
    { name: "unknown state word", raw: { state: "banana", merged_probability: 0.3 } },
    { name: "non-string state", raw: { state: 7, merged_probability: 0.3 } },
    { name: "live with a string probability", raw: { state: "live", merged_probability: "0.3" } },
    { name: "live with NaN", raw: { state: "live", merged_probability: NaN } },
    { name: "live with Infinity", raw: { state: "live", merged_probability: Infinity } },
    { name: "live above 1", raw: { state: "live", merged_probability: 1.4 } },
    { name: "live below 0", raw: { state: "live", merged_probability: -0.2 } },
    { name: "live with a null probability", raw: { state: "live", merged_probability: null } },
  ];

  test.each(UNVOUCHABLE)("$name → unavailable, never a number", ({ raw }) => {
    const cell = renderGridCell(raw);
    expect(cell.state).toBe("unavailable");
    expect(cell.probability).toBeNull();
  });

  test("poison source rows are dropped, not rendered as NaN", () => {
    const cell = renderGridCell({
      state: "live",
      merged_probability: 0.3,
      sources: [
        { source: "kalshi", probability: 0.31 },
        { source: "polymarket", probability: "0.29" },
        { source: "", probability: 0.2 },
        null,
        "odds_api",
        { source: "datagolf", probability: NaN },
        { source: "odds_api", probability: 0.28 },
      ],
    });
    expect(cell.sources).toEqual([
      { source: "kalshi", probability: 0.31 },
      { source: "odds_api", probability: 0.28 },
    ]);
  });

  test("a non-array sources field does not throw", () => {
    expect(renderGridCell({ state: "live", merged_probability: 0.3, sources: "kalshi" }).sources).toEqual([]);
  });
});

describe("renderGridCell — pre-register payloads (no state field)", () => {
  test("a number with no declared state is still live", () => {
    const cell = renderGridCell({ merged_probability: 0.18, trend_24h: -0.02, sources: [] });
    expect(cell.state).toBe("live");
    expect(cell.probability).toBe(0.18);
    expect(cell.trend24h).toBe(-0.02);
  });

  test("no number and no declared state is missing, not 0", () => {
    const cell = renderGridCell({ merged_probability: null, sources: [] });
    expect(cell.state).toBe("missing");
    expect(cell.probability).toBeNull();
  });

  test("the native/web display word 'clinched' is accepted as won", () => {
    expect(renderGridCell({ state: "clinched", merged_probability: 1 }).state).toBe("won");
  });

  test("boundary probabilities 0 and 1 stay live — the market can still move", () => {
    expect(renderGridCell({ state: "live", merged_probability: 0 }).probability).toBe(0);
    expect(renderGridCell({ state: "live", merged_probability: 1 }).probability).toBe(1);
  });
});

describe("progressionStatusFor + sort weight", () => {
  test("maps register states onto the existing status vocabulary", () => {
    expect(progressionStatusFor("live")).toBeNull();
    expect(progressionStatusFor("won")).toBe("clinched");
    expect(progressionStatusFor("eliminated")).toBe("eliminated");
    expect(progressionStatusFor("missing")).toBe("missing");
    expect(progressionStatusFor("unavailable")).toBe("unavailable");
  });

  test("a clinched champion sorts above every live cell", () => {
    expect(progressionSortValue(null, "clinched")).toBeGreaterThan(
      progressionSortValue(0.999, null),
    );
  });

  test("terminal-out and empty states sort below every live cell", () => {
    for (const status of ["eliminated", "missing", "unavailable"] as const) {
      expect(progressionSortValue(null, status)).toBeLessThan(progressionSortValue(0, null));
    }
  });

  test("live cells keep their existing sort behaviour exactly", () => {
    expect(progressionSortValue(0.4, null)).toBe(0.4);
    expect(progressionSortValue(null, null)).toBe(-1);
    expect(progressionSortValue(undefined, null)).toBe(-1);
    expect(progressionSortValue(NaN, null)).toBe(-1);
  });
});

describe("every state has an accessible name", () => {
  test.each(["live", "won", "eliminated", "missing", "unavailable"] as GridCellState[])(
    "%s",
    (state) => {
      expect(GRID_CELL_STATE_LABEL[state]).toBeTruthy();
    },
  );
});

describe("league independence", () => {
  // Every league flows through the same normalizer, so the same fixture must
  // produce the same decision regardless of which grid it came from.
  test.each(LEAGUES)("%s settled cell drops its number", () => {
    const cell = renderGridCell({ merged_probability: 0.83, state: "won" });
    expect(cell.state).toBe("won");
    expect(cell.probability).toBeNull();
  });
});
