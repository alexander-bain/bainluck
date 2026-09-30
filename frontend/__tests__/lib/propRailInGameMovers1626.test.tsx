/**
 * #1626 slice 2 — "What's moving" lists only rows that moved.
 *
 * Production, CWS @ HOU `15321836`, live, 2026-09-30 22:45Z (banked 23:04Z,
 * 3–4): the in-game rail LED with `Sean Burke: 5+ hits allowed — opened 42% ·
 * now 42%`, served `0.425 → 0.42`. The rail ranks by raw travel and filled its
 * five slots with whatever came next, so a row whose own bar prints both ends
 * the same sat under a header promising movement. Alex, 9/29, on THE
 * DIVERGENCE: "way more compact".
 *
 * The rule reuses the pregame movement tier's predicate (`direction !==
 * "flat"`, #8754's printed-number line), so the rail and the picture agree.
 * Both directions are asserted (gotcha #43): the flat row leaves, every mover
 * stays, nothing becomes unreachable, and pregame/settled do not move.
 */

import { renderToStaticMarkup } from "react-dom/server";
import PropDivergenceRail from "@/components/PropDivergenceRail";
import {
  RAIL_MAX_ROWS,
  selectDivergenceDetail,
  selectDivergenceRows,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import specimen from "../fixtures/eventPlayerProps.15321836.live-1626.json";

const ROWS = specimen as unknown as PlayerPropRow[];
const BURKE = "Sean Burke: 5+ hits allowed";
const MOVERS = [
  "Christian Walker: 1+ home runs",
  "Colson Montgomery: 1+ home runs",
  "Hunter Brown: 9+ strikeouts",
  "Miguel Vargas: 1+ home runs",
];

function detail(rows: readonly PlayerPropRow[], status: string) {
  const d = selectDivergenceDetail({ playerProps: rows, status });
  return [...d.offScript, ...d.onScript, ...d.ungraded];
}

/** Every row pinned to its own pregame mark: a board where nothing has moved. */
function frozen(rows: readonly PlayerPropRow[]): PlayerPropRow[] {
  return rows.map((r) => {
    const mark = (r as PlayerPropRow & { pregame_mark?: number | null }).pregame_mark;
    return mark == null ? r : ({ ...r, over_probability: mark } as PlayerPropRow);
  });
}

describe("#1626 slice 2 — the specimen", () => {
  it("is the row production led with: flat, and the biggest raw travel on the board", () => {
    const burke = detail(ROWS, "live").find((r) => r.label === BURKE)!;
    expect([burke.pregameMark, burke.current, burke.direction]).toEqual([0.425, 0.42, "flat"]);
    // Tied at the top by raw travel with every mover — which is why the
    // key-order tiebreak could put it first.
    const top = Math.max(...detail(ROWS, "live").map((r) => r.travel));
    expect(burke.travel).toBeCloseTo(top, 9);
  });

  it("is off \"What's moving\"; the four movers are on it, in the same order", () => {
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });
    const labels = res.rows.map((r) => r.label);
    expect(labels).not.toContain(BURKE);
    expect(labels).toEqual(MOVERS);
    expect(res.rows.every((r) => r.direction !== "flat")).toBe(true);
  });

  it("stays reachable: eligible still counts it and the detail view still lists it", () => {
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });
    expect(res.eligible).toBe(24);
    expect(res.notSelected).toBe(20);
    expect(detail(ROWS, "live").map((r) => r.label)).toContain(BURKE);
  });

  it("renders under the header with the honest count, and Burke nowhere on the rail", () => {
    const html = renderToStaticMarkup(<PropDivergenceRail playerProps={ROWS} status="live" />);
    expect(html).toContain("What&#x27;s moving");
    expect(html).toContain("4 of 24");
    expect(html).not.toContain("Sean Burke");
    for (const m of MOVERS) expect(html).toContain(m);
  });
});

describe("#1626 slice 2 — a board where nothing has moved", () => {
  const still = frozen(ROWS);

  it("puts no row under \"What's moving\" and ends clean, so the rail renders nothing", () => {
    const res = selectDivergenceRows({ playerProps: still, status: "live" });
    expect(res.rows).toHaveLength(0);
    expect(res.emptyReason).toBe("clean");
    expect(res.eligible).toBe(24);
    expect(renderToStaticMarkup(<PropDivergenceRail playerProps={still} status="live" />)).toBe("");
  });

  it("pregame the same frozen board still fills THE SCRIPT — the rule is in-game only", () => {
    const res = selectDivergenceRows({ playerProps: still, status: "scheduled" });
    expect(res.pregame).toBe(true);
    expect(res.rows.length).toBe(RAIL_MAX_ROWS);
    expect(res.rows.every((r) => r.direction === "flat")).toBe(true);
  });
});
