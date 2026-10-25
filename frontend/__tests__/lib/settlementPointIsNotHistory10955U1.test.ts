/**
 * #10955 U1 — A SETTLEMENT POINT IS NOT RECORDED HISTORY, UPSTREAM OF THE CHART EITHER.
 *
 * Step 2 (PR #11436) taught `FuturesChart` to split the `bookmaker: "settlement"`
 * point off before it counts, scales or draws. Lane1's review (0721Z) named the
 * wrappers that read the same `/history` payload BEFORE the chart does and still
 * counted the result as a reading:
 *
 *   - `lib/chartWindow.ts` — `latestSnapshotTime` anchors every range window and
 *     `availableRanges` decides which chips exist. A 20-hour history whose result
 *     is stamped 3 days later grew a "1D" chip that existed only because of the
 *     stamp, and that chip opened onto a day with no readings in it.
 *   - `lib/golfWinnerChart.ts` `isDrawableHistory` — "the chart's own
 *     drawability test". One reading plus a result said drawable, the chart said
 *     sparse, and the golf hub stopped on a sparse market instead of walking on.
 *
 * Controlled examples, fixed anchors (gotcha #44). A real reading at 0 or 1 is
 * still a reading: only the point KIND excludes, never the value.
 */

import {
  availableRanges,
  latestSnapshotTime,
  windowOutcomeHistory,
} from "@/lib/chartWindow";
import { isDrawableHistory } from "@/lib/golfWinnerChart";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const START = Date.UTC(2026, 9, 10, 0, 0, 0);
const LAST_REAL = START + 20 * HOUR; // 20 hours of real readings
const RESULT_AT = LAST_REAL + 3 * DAY; // the result, stamped 3 days later

const pt = (at: number, p: number, bookmaker = "consensus"): FuturesHistoryPoint => ({
  timestamp: new Date(at).toISOString(),
  probability: p,
  american_odds: null,
  bookmaker,
});
const leg = (id: number, history: FuturesHistoryPoint[]): FuturesOutcomeHistory => ({
  outcome_id: id,
  name: `Leg ${id}`,
  history,
});

const realYes = Array.from({ length: 21 }, (_, i) => pt(START + i * HOUR, 0.4 + 0.01 * i));
const realNo = Array.from({ length: 21 }, (_, i) => pt(START + i * HOUR, 0.6 - 0.01 * i));

/** The reviewer's example: 20 h real, each leg's result 3 days later. */
const SETTLED = [
  leg(1, [...realYes, pt(RESULT_AT, 1, "settlement")]),
  leg(2, [...realNo, pt(RESULT_AT, 0, "settlement")]),
];
/** The same field without its results. */
const CONTROL = [leg(1, realYes), leg(2, realNo)];

const keys = (outcomes: FuturesOutcomeHistory[], hasStart = false) =>
  availableRanges(outcomes, hasStart).map((r) => r.key);

describe("U1 chartWindow: the result neither anchors the window nor makes a chip", () => {
  it("the window anchors on the last REAL reading, not the result stamp", () => {
    expect(latestSnapshotTime(SETTLED)).toBe(LAST_REAL);
    expect(latestSnapshotTime(SETTLED)).toBe(latestSnapshotTime(CONTROL));
  });

  it("no 1D chip exists only because of the result stamp", () => {
    // 20 h of data is narrower than a day: the control offers All alone.
    expect(keys(CONTROL)).toEqual(["all"]);
    expect(keys(SETTLED)).toEqual(keys(CONTROL));
    expect(keys(SETTLED)).not.toContain("1D");
  });

  it("a result stamped BEFORE the first reading does not widen the span either", () => {
    // A schedule-derived stamp can predate the market's first recorded reading.
    const early = [
      leg(1, [pt(START - 3 * DAY, 1, "settlement"), ...realYes]),
      leg(2, [pt(START - 3 * DAY, 0, "settlement"), ...realNo]),
    ];
    expect(keys(early)).toEqual(["all"]);
  });

  it("a 1D window over the settled field keeps every real reading (never an empty day)", () => {
    const windowed = windowOutcomeHistory(SETTLED, "1D");
    const realIn = (o: FuturesOutcomeHistory) => o.history.filter((p) => p.bookmaker !== "settlement");
    expect(realIn(windowed[0])).toHaveLength(realYes.length);
    expect(realIn(windowed[1])).toHaveLength(realNo.length);
    // The result rides through for the chart to split off — it is not dropped here.
    expect(windowed[0].history.some((p) => p.bookmaker === "settlement")).toBe(true);
  });

  it("a long real history still offers its real chips, with or without the result", () => {
    const long = Array.from({ length: 41 }, (_, i) => pt(START + i * DAY, 0.5));
    const withResult = [leg(1, [...long, pt(START + 40 * DAY + 3 * DAY, 1, "settlement")])];
    expect(keys([leg(1, long)])).toEqual(["all", "1M", "1W", "1D"]);
    expect(keys(withResult)).toEqual(["all", "1M", "1W", "1D"]);
  });

  it("HEALTHY: a real reading at 0% or 100% still anchors and spans — the kind excludes, not the value", () => {
    const zeroHundred = [
      leg(1, [pt(START, 0.5), pt(START + 3 * DAY, 1)]),
      leg(2, [pt(START, 0.5), pt(START + 3 * DAY, 0)]),
    ];
    expect(latestSnapshotTime(zeroHundred)).toBe(START + 3 * DAY);
    expect(keys(zeroHundred)).toEqual(["all", "1D"]);
  });

  it("IDENTITY: a field with no result is returned as the same array for All and Since-start without a start", () => {
    expect(windowOutcomeHistory(CONTROL, "all")).toBe(CONTROL);
    expect(windowOutcomeHistory(SETTLED, "all")).toBe(SETTLED);
    expect(windowOutcomeHistory(SETTLED, "since_start", null)).toBe(SETTLED);
  });

  it("a field that is ONLY results has no anchor", () => {
    expect(latestSnapshotTime([leg(1, [pt(RESULT_AT, 1, "settlement")])])).toBeNull();
  });
});

describe("U1 golf: one reading plus a result is not a drawable history", () => {
  const response = (outcomes: FuturesOutcomeHistory[]) => ({ outcomes });

  it("one real reading + a settlement point ⇒ not drawable (the walk moves on)", () => {
    expect(isDrawableHistory(response([leg(1, [pt(START, 0.3), pt(RESULT_AT, 1, "settlement")])]))).toBe(false);
  });

  it("two real readings at two times + a settlement point ⇒ drawable", () => {
    expect(
      isDrawableHistory(response([leg(1, [pt(START, 0.3), pt(LAST_REAL, 0.4), pt(RESULT_AT, 1, "settlement")])])),
    ).toBe(true);
  });

  it("HEALTHY: real 0% and 100% readings count as readings", () => {
    expect(isDrawableHistory(response([leg(1, [pt(START, 0), pt(LAST_REAL, 1)])]))).toBe(true);
  });

  it("CONTROL: one real reading alone stays not drawable, as before", () => {
    expect(isDrawableHistory(response([leg(1, [pt(START, 0.3)])]))).toBe(false);
  });
});
