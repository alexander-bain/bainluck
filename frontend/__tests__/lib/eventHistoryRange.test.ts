/**
 * #6948 — the event page defers the pre-kickoff half of its history payload and must still be able
 * to ask for it back.
 *
 * WHY THESE ASSERTIONS AND NOT A RENDER. The rule lives in a client component the frontend jest
 * environment cannot render, so the alternative to a pure module was a source scan — and the two
 * defects this rule exists to prevent are both DYNAMIC (an oscillating fetch key, a duplicate
 * request on a cohort). A source scan can see neither. The module is pure precisely so these can be
 * stated as behaviour.
 */

import { EVENT_BOOT_HISTORY_RANGE, eventBootPaths } from "@/lib/event/detailBoot";
import {
  effectiveChartRange,
  historyRangeParam,
  nextFullHistoryLatch,
  type ChartTimeRange,
} from "@/lib/event/historyRange";

describe("#6948 · the first paint asks for the trimmed body", () => {
  it("sends range=since_start while no wider body has been requested", () => {
    expect(historyRangeParam(false)).toBe("since_start");
  });

  it("sends NO range parameter once the whole journey is wanted", () => {
    // Not "all", not "" — the route treats any unrecognised value as "serve everything", but
    // depending on that leniency instead of on the documented contract is how a client breaks when
    // the leniency is tightened.
    expect(historyRangeParam(true)).toBeUndefined();
  });

  it("returns the very token the boot parks, not a second spelling of it", () => {
    // The whole of LAT-P171/P172: two builders that must stay equal. If this ever fails, the parked
    // URL and the first-paint URL differ and every cold load pays for a duplicate request.
    expect(historyRangeParam(false)).toBe(EVENT_BOOT_HISTORY_RANGE);
    const historyPath = eventBootPaths(15293206).find((p) => p.includes("/history"));
    expect(historyPath).toContain(`&range=${historyRangeParam(false)}`);
  });
});

describe("#6948 · the latch rises when the reader's range needs points that were dropped", () => {
  it("rises on 'all' when the server says it actually omitted points", () => {
    expect(nextFullHistoryLatch(false, "all", true)).toBe(true);
  });

  it("stays down on 'live', which is the range the trimmed body was built for", () => {
    expect(nextFullHistoryLatch(false, "live", true)).toBe(false);
  });

  it("stays down on 'all' when nothing was omitted — the scheduled-game cohort", () => {
    // THE DUPLICATE-REQUEST GUARD. A scheduled game's chart also defaults to "all", but the route
    // already served it everything (no post-kickoff point to trim to). Keying the request on the
    // range alone would re-fetch an identical body for most "all" charts on the site.
    expect(nextFullHistoryLatch(false, "all", false)).toBe(false);
  });

  it("stays down when the flag is absent — an older payload is not a trimmed one", () => {
    // Strictly `true`. `undefined` must not be guessed at, and the client must never re-derive this
    // by looking for points older than commence_time: a series that legitimately has none is
    // indistinguishable from a trimmed one.
    expect(nextFullHistoryLatch(false, "all", undefined)).toBe(false);
  });
});

describe("#6948 · the settling range, not the state variable", () => {
  // THE DEFECT THIS PINS WAS LIVE IN THIS SHIP'S OWN FIRST DRAFT, and no unit assertion could see
  // it — it took driving a real browser. `defaultChartTimeRange` answers "all" whenever it cannot
  // find enough post-kickoff points, and before the payload lands it is looking at `undefined`, so
  // every event page passes through an "all" that means "no data yet". The latch fired there, and
  // KC-DEN 14638896 fetched the trimmed body AND the full body on every load — strictly more work
  // than before the ship.

  it("ignores the stale state variable while the range is still evidence-driven", () => {
    // The exact frame: state still holds the no-data "all", the evidence memo has already seen the
    // payload and says "live".
    expect(effectiveChartRange(false, "all", "live")).toBe("live");
    expect(nextFullHistoryLatch(false, effectiveChartRange(false, "all", "live"), true)).toBe(false);
  });

  it("follows the evidence when the evidence itself wants the whole journey", () => {
    expect(effectiveChartRange(false, "live", "all")).toBe("all");
    expect(nextFullHistoryLatch(false, effectiveChartRange(false, "live", "all"), true)).toBe(true);
  });

  it("hands the reader's own choice back, whatever the evidence says", () => {
    // Includes OddsChart's `nothingToDrawInLiveWindow` self-reset (#6349): it routes through the
    // page's setter, so it marks the range user-set and must be honoured like a tap.
    expect(effectiveChartRange(true, "all", "live")).toBe("all");
    expect(effectiveChartRange(true, "live", "all")).toBe("live");
  });

  it("latches on the reader's tap even when the evidence would have said 'live'", () => {
    // The headline path: a finished game whose chart opened on "Since Start" and whose reader then
    // asks for the whole journey.
    expect(nextFullHistoryLatch(false, effectiveChartRange(true, "all", "live"), true)).toBe(true);
  });
});

describe("#6948 · the page feeds the latch the SETTLING range, not the state variable", () => {
  // A SOURCE SCAN, and it says so — `app/events/[id]/page.tsx` is a client component this jest
  // environment cannot render, so the wiring between two correct pure functions has no other
  // assertable surface.
  //
  // IT EARNS ITS PLACE BY MUTATION. With the two functions above fully guarded, replacing
  // `effectiveChartRange(...)` with the raw `chartTimeRange` at the call site left the entire suite
  // GREEN — and that is not a hypothetical edit, it is precisely the defect that was live in this
  // ship's first draft and cost KC-DEN a double fetch on every load. A hole a mutant walks through
  // is a hole.
  function readPageSource(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs") as typeof import("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path") as typeof import("path");
    const file = path.join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx");
    const src = fs.readFileSync(file, "utf8");
    // A scan whose target vanished must go RED, not silently pass over an empty string.
    if (src.trim().length === 0) throw new Error(`source scan target is empty: ${file}`);
    return src;
  }

  it("composes the two helpers rather than passing the raw chartTimeRange", () => {
    const src = readPageSource().replace(/\s+/g, " ");
    expect(src).toContain("nextFullHistoryLatch( prev, effectiveChartRange(");
  });

  it("gives effectiveChartRange the user-set flag and both ranges, in that order", () => {
    const src = readPageSource().replace(/\s+/g, " ");
    expect(src).toContain(
      "effectiveChartRange(chartRangeUserSet, chartTimeRange, evidenceChartTimeRange)"
    );
  });
});

describe("#6948 · the latch is one-way, which is what makes the feature terminate", () => {
  it("stays up after the full body arrives reporting pre_window_omitted false", () => {
    // THE OSCILLATION. `pre_window_omitted: false` is the full body's own signature AND the
    // condition for not needing it. Were the latch derived fresh each render it would fall here,
    // the SWR key would flip back, the cached trimmed body would be served, the flag would read
    // true again, and the page would fetch forever.
    expect(nextFullHistoryLatch(true, "all", false)).toBe(true);
  });

  it("stays up when the reader goes back to 'live'", () => {
    // Returning to "Since Start" must not throw away the journey we already paid for; the next tap
    // on "All" has to be instant.
    expect(nextFullHistoryLatch(true, "live", false)).toBe(true);
    expect(nextFullHistoryLatch(true, "live", undefined)).toBe(true);
  });

  it("cannot be lowered by ANY input, stated over the whole domain rather than by example", () => {
    const ranges: ChartTimeRange[] = ["all", "live"];
    const flags: (boolean | undefined)[] = [true, false, undefined];
    for (const range of ranges) {
      for (const flag of flags) {
        expect(nextFullHistoryLatch(true, range, flag)).toBe(true);
      }
    }
  });

  it("is idempotent: feeding its own output back never changes the answer", () => {
    // The property the effect relies on — it runs on every dependency change, so a rule that
    // disagreed with itself on a second pass would be a render loop.
    const ranges: ChartTimeRange[] = ["all", "live"];
    const flags: (boolean | undefined)[] = [true, false, undefined];
    for (const range of ranges) {
      for (const flag of flags) {
        const once = nextFullHistoryLatch(false, range, flag);
        expect(nextFullHistoryLatch(once, range, flag)).toBe(once);
      }
    }
  });
});
