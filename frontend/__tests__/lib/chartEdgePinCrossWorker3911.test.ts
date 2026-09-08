import {
  PINNABLE_HERO_SOURCE,
  pinChartEdgeToHero,
} from "@/lib/chartEdgePin";

// #3911 / CERT-2243 — THE CROSS-WORKER REGRESSION.
//
// The page fires `/events/{id}` and `/events/{id}/history` as two HTTP
// requests. `_event_detail_cache` is module-global and therefore PROCESS-local,
// so on production those two requests can land on different web workers:
//
//   worker A  has a cached detail payload from before the venues moved
//             -> hero 0.40
//   worker B  has an empty cache and computes the edge from live rows
//             -> pinned edge 0.10
//
// Both are individually correct and the reader sees 40% written over a curve
// ending at 10%. Reproduced by the cert bus at exactly those numbers. No amount
// of agreement inside one process fixes a disagreement between two, so the pin
// happens where both payloads meet: the page.
//
// The fixtures below ARE that topology — the hero and the line are built
// independently, as two workers would build them, and never from one source of
// truth in the test.

const HERO_FROM_WORKER_A = {
  hero_probability: 0.4,
  hero_probability_source: "blend",
};

const HISTORY_FROM_WORKER_B = {
  aggregate_line: [
    { timestamp: "2026-09-08T10:18:00+00:00", home_probability: 0.62 },
    { timestamp: "2026-09-08T10:19:00+00:00", home_probability: 0.1 },
  ],
  blend_edge_pinned: true,
};

const edge = (h: { aggregate_line?: Array<{ home_probability: number }> | null }) =>
  h.aggregate_line?.[h.aggregate_line.length - 1]?.home_probability;

describe("#3911 the page renders one number when two workers answered", () => {
  it("moves the pinned edge onto the hero the page was actually served", () => {
    const pinned = pinChartEdgeToHero(HISTORY_FROM_WORKER_B, HERO_FROM_WORKER_A);

    expect(edge(pinned!)).toBe(0.4);
    expect(edge(pinned!)).toBe(HERO_FROM_WORKER_A.hero_probability);
    // The negative control: what the reader saw before this existed, and the
    // reason 0.4 above is not a tautology.
    expect(edge(HISTORY_FROM_WORKER_B)).toBe(0.1);
  });

  it("leaves every earlier bucket alone — history stays honest", () => {
    const pinned = pinChartEdgeToHero(HISTORY_FROM_WORKER_B, HERO_FROM_WORKER_A);

    expect(pinned!.aggregate_line!.map((p) => p.home_probability)).toEqual([
      0.62, 0.4,
    ]);
    expect(pinned!.aggregate_line![0].timestamp).toBe(
      "2026-09-08T10:18:00+00:00"
    );
  });

  it("does not write through SWR's cached object", () => {
    const served = {
      ...HISTORY_FROM_WORKER_B,
      aggregate_line: HISTORY_FROM_WORKER_B.aggregate_line.map((p) => ({ ...p })),
    };
    pinChartEdgeToHero(served, HERO_FROM_WORKER_A);

    // Mutating in place would edit the cache entry every other consumer reads,
    // changing a number under a component that never re-rendered.
    expect(edge(served)).toBe(0.1);
  });
});

describe("#3911 the pin stands down wherever the server did", () => {
  it("does nothing when the server did not pin the edge", () => {
    // A settled row, or a pre-match line whose newest bucket is genuinely in
    // the past. That edge says 'at 8:34 PM it was 38%', not '38% now', and
    // overwriting it is #1561 rebuilt.
    const unpinned = { ...HISTORY_FROM_WORKER_B, blend_edge_pinned: false };

    expect(pinChartEdgeToHero(unpinned, HERO_FROM_WORKER_A)).toBe(unpinned);
  });

  it("does nothing for a hero that is not the blend", () => {
    for (const source of ["final", "opening", "final-unresolved", null]) {
      const hero = { ...HERO_FROM_WORKER_A, hero_probability_source: source };
      expect(pinChartEdgeToHero(HISTORY_FROM_WORKER_B, hero)).toBe(
        HISTORY_FROM_WORKER_B
      );
    }
    expect(PINNABLE_HERO_SOURCE).toBe("blend");
  });

  it("does nothing when there is no hero, no line, or no payload", () => {
    expect(pinChartEdgeToHero(HISTORY_FROM_WORKER_B, undefined)).toBe(
      HISTORY_FROM_WORKER_B
    );
    expect(
      pinChartEdgeToHero(HISTORY_FROM_WORKER_B, {
        hero_probability: null,
        hero_probability_source: "blend",
      })
    ).toBe(HISTORY_FROM_WORKER_B);
    const noLine = { aggregate_line: null, blend_edge_pinned: true };
    expect(pinChartEdgeToHero(noLine, HERO_FROM_WORKER_A)).toBe(noLine);
    expect(pinChartEdgeToHero(undefined, HERO_FROM_WORKER_A)).toBeUndefined();
  });

  it("returns the same object when the two workers already agreed", () => {
    // The common case — one worker served both — must allocate nothing, or
    // every poll hands React a new object and re-renders the chart.
    const agreed = {
      aggregate_line: [{ timestamp: "2026-09-08T10:19:00+00:00", home_probability: 0.4 }],
      blend_edge_pinned: true,
    };

    expect(pinChartEdgeToHero(agreed, HERO_FROM_WORKER_A)).toBe(agreed);
  });
});

describe("#3911 the page is wired to the pin", () => {
  it("derives historyData through pinChartEdgeToHero, not straight from SWR", () => {
    const fs = require("fs");
    const path = require("path");
    const page = fs.readFileSync(
      path.join(__dirname, "../../app/events/[id]/page.tsx"),
      "utf8"
    );

    // The SWR result is named `servedHistory` and every downstream consumer
    // reads the derived `historyData`, so a future edit cannot reintroduce the
    // split by adding one more reader.
    expect(page).toContain("data: servedHistory,");
    expect(page).toContain("pinChartEdgeToHero(servedHistory, event)");
    expect(page).not.toContain("data: historyData,");
  });
});
