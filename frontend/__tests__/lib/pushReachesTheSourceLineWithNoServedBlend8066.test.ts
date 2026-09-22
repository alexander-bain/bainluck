// #8066's remainder (#920): a single-source live page keeps its push speed.
//
// THE SHAPE. The backend serves `aggregate_line` only where it blended two or
// more sources. #920 merged the stream's published blend into that same array,
// so on a Kalshi-only match two pushed frames drew a 2-vertex line under the
// blend's name on top of the real one. #8066 fixed the chart: the blend line
// now requires the blend to be the BACKEND's (`backendBlendServed`).
//
// That is right, and it leaves the page slower than it was. With no blend line
// drawn, the only line on that plot is the source's own — and nothing was
// feeding it, so it advanced on the 32 s poll while the page was holding a
// reading three seconds old. `live_blend_refresh` stamps `source_value` from
// the same reading it persists as `win_prob_history[<source>][].home_probability`,
// so the frame already carries the number that series wants.
//
// WHAT MUST NOT HAPPEN while paying that back, each with its own case below:
//   • the blend's value landing on the source's line (they are two numbers);
//   • a series minted out of pushed frames — the #8066 defect wearing the
//     source's face instead of the blend's;
//   • a reading inserted behind the backend's synthetic `live_edge` endpoint,
//     which would draw the line backwards;
//   • the served SWR payload mutated in place;
//   • a new object on every render for a page where nothing was added.
//
// Handed over by ux/1443, who owns the chart and measured the cost.

import {
  rememberLiveChartFrame,
  mergeLiveChartHistory,
  type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { LiveStreamFrame } from "@/lib/liveStreamController";
import { classifySeriesSupport } from "@/lib/chartObservationSupport";
import type { WinProbHistoryPoint } from "@/lib/types";

const t = (s: number) => new Date(Date.UTC(2026, 8, 22, 20, 0, s)).toISOString();

/** A published frame: blend `p`, and the venue reading behind it. */
const frame = (
  s: number, p: number, sourceValue: number | null, source = "kalshi",
): LiveStreamFrame => ({
  event_id: 42, p, source, source_value: sourceValue,
  updated_at: t(s), status: "live",
});

const wp = (s: number, v: number, extra = {}): WinProbHistoryPoint => ({
  timestamp: t(s), home_probability: v, away_probability: 1 - v, ...extra,
});

/** The payload a single-source live page is served: no blend, one series. */
const singleSource = () => ({
  win_prob_history: { kalshi: [wp(0, .5), wp(30, .52)] },
  win_prob_sources: { kalshi: { display_name: "Kalshi" } },
});

const buffer = (...frames: LiveStreamFrame[]): LiveChartFrame[] =>
  frames.reduce<LiveChartFrame[]>((pts, f) => rememberLiveChartFrame(pts, f, 42), []);

describe("#8066 remainder: with no backend blend, push extends the source's own line", () => {
  it("appends the session's readings to the served series at their own times", () => {
    const served = singleSource();
    const result = mergeLiveChartHistory(served, buffer(
      frame(35, .61, .61), frame(40, .64, .64),
    ))!;
    expect(result.win_prob_history.kalshi).toEqual([
      wp(0, .5), wp(30, .52),
      { timestamp: t(35), home_probability: .61, away_probability: null },
      { timestamp: t(40), home_probability: .64, away_probability: null },
    ]);
  });

  it("plots the SOURCE's price on the source's line, never the blend's", () => {
    // The two disagree here on purpose. `p` is the answer the hero renders;
    // `source_value` is what this feed said. A mutant that appends
    // `home_probability` (the blend) passes every other case in this file.
    const result = mergeLiveChartHistory(singleSource(), buffer(frame(35, .90, .61)))!;
    const added = result.win_prob_history.kalshi.at(-1)!;
    expect(added.home_probability).toBe(.61);
    expect(result.win_prob_history.kalshi.map(p => p.home_probability)).not.toContain(.90);
  });

  it("is an observation, not a delivery: no live_edge, and nothing carried forward", () => {
    // `chartObservationSupport` reads `live_edge` to tell the backend's
    // synthetic right edge from a real reading, and this IS a real reading —
    // the price was fetched, stamped and committed before it was published.
    // `away_probability` is null because the frame carries none; taking the
    // previous point's would invent a number, and on a draw-priced sport an
    // actively wrong one.
    const added = mergeLiveChartHistory(singleSource(), buffer(frame(35, .61, .61)))!
      .win_prob_history.kalshi.at(-1)!;
    expect(added.live_edge).toBeUndefined();
    expect(added.away_probability).toBeNull();
  });

  it("never mints a series the backend did not serve", () => {
    // Polymarket publishes for this event; the payload carries no polymarket
    // history. Two pushed frames must not become a 2-vertex line with no
    // legend entry and no colour.
    const served = { win_prob_history: { kalshi: [wp(0, .5)] } };
    const result = mergeLiveChartHistory(served, buffer(
      frame(35, .61, .61, "polymarket"), frame(40, .62, .62, "polymarket"),
    ))!;
    expect(Object.keys(result.win_prob_history)).toEqual(["kalshi"]);
    expect(result.win_prob_history).toBe(served.win_prob_history);
  });

  it("does not extend a series that was served empty", () => {
    const served = { win_prob_history: { kalshi: [] as WinProbHistoryPoint[] } };
    expect(mergeLiveChartHistory(served, buffer(frame(35, .61, .61)))!.win_prob_history)
      .toBe(served.win_prob_history);
  });

  it("extends only the series that published the reading", () => {
    const served = {
      win_prob_history: { kalshi: [wp(0, .5)], polymarket: [wp(0, .48)] },
    };
    const result = mergeLiveChartHistory(served, buffer(frame(35, .61, .61)))!;
    expect(result.win_prob_history.kalshi).toHaveLength(2);
    expect(result.win_prob_history.polymarket).toBe(served.win_prob_history.polymarket);
  });

  it("never inserts behind the served edge, including the synthetic live edge", () => {
    // A live payload ends in the backend's `live_edge` point at "now" carrying
    // the LAST REAL value. A reading stamped a moment before it is already
    // behind a stale endpoint: appending it would draw 0.52 → 0.61 → 0.52.
    const served = {
      win_prob_history: { kalshi: [wp(0, .5), wp(30, .52, { live_edge: true })] },
    };
    const result = mergeLiveChartHistory(served, buffer(
      frame(25, .61, .61), frame(30, .62, .62), frame(35, .63, .63),
    ))!;
    expect(result.win_prob_history.kalshi.map(p => p.timestamp))
      .toEqual([t(0), t(30), t(35)]);
    expect(result.win_prob_history.kalshi.at(-1)!.home_probability).toBe(.63);
    const times = result.win_prob_history.kalshi.map(p => Date.parse(p.timestamp));
    expect([...times].sort((a, b) => a - b)).toEqual(times);
  });

  it("leaves the source series exactly as served once the backend has a blend", () => {
    // Where a blend IS served it is the primary line and #920's aggregate
    // merge already carries the push. Touching the source series there would
    // widen this change onto every multi-source page for no reader gain.
    const served = {
      aggregate_line: [{ timestamp: t(0), home_probability: .5 }],
      win_prob_history: { kalshi: [wp(0, .5)] },
    };
    const result = mergeLiveChartHistory(served, buffer(frame(35, .61, .61)))!;
    expect(result.win_prob_history).toBe(served.win_prob_history);
    expect(result.aggregate_line).toHaveLength(2);
  });

  it("keeps the blend's array plot-shaped — the source reading never leaks in", () => {
    const result = mergeLiveChartHistory(
      { aggregate_line: [{ timestamp: t(0), home_probability: .5 }] },
      buffer(frame(35, .61, .65)),
    )!;
    expect(result.aggregate_line).toEqual([
      { timestamp: t(0), home_probability: .5 },
      { timestamp: t(35), home_probability: .61 },
    ]);
  });

  it("does not mutate the served response, its record or its arrays", () => {
    // `servedHistory` is SWR's cached object. Mutating it would make the
    // served edge move under the next merge, so the same frames would be
    // appended again on every render.
    const series = Object.freeze([wp(0, .5)]) as unknown as WinProbHistoryPoint[];
    const served = Object.freeze({
      win_prob_history: Object.freeze({ kalshi: series }),
    }) as unknown as { win_prob_history: Record<string, WinProbHistoryPoint[]> };
    const result = mergeLiveChartHistory(served, buffer(frame(35, .61, .61)))!;
    expect(result.win_prob_history.kalshi).toHaveLength(2);
    expect(served.win_prob_history.kalshi).toHaveLength(1);
    expect(result.win_prob_history).not.toBe(served.win_prob_history);
  });

  it("hands the source line the same array back when no frame carried a reading", () => {
    // A frame with no usable `source_value` is still a blend observation — it
    // goes on collecting for the hero and the sparkline — but it has nothing
    // to say about the source's line, and handing that line a new array on
    // every render would rebuild every chart memo downstream for nothing.
    const served = singleSource();
    for (const bad of [null, NaN, Infinity, -.01, 1.4]) {
      expect(mergeLiveChartHistory(served, buffer(frame(35, .61, bad)))!.win_prob_history)
        .toBe(served.win_prob_history);
    }
    // A payload with no source history at all is not a crash and not a mint.
    expect(mergeLiveChartHistory({ win_prob_history: null }, buffer(frame(35, .61, .61)))!
      .win_prob_history).toBeNull();
  });

  it("does not make the chart draw its own gap markers over the readings it added", () => {
    // THE ONE THIS CHANGE COULD PLAUSIBLY BREAK DOWNSTREAM. `OddsChart` feeds
    // every `win_prob_history` point to `classifySeriesSupport`, which derives
    // each series' own in-game cadence as the median gap between consecutive
    // observations and calls anything longer than 15x that a hole. Push lands
    // ~5s apart where the persisted series is on a 45s snapshot clock, so the
    // readings appended here DROP that median — and a tightened bound applied
    // to the sparse points before them would paint a gap over history that was
    // perfectly well supported a moment earlier. `SUPPORT_FLOOR_S` (600s) is
    // what stops it, so it is asserted here rather than assumed: the interval
    // between the served points is 180s — a flat market's heartbeat write —
    // and 15 x 5s is 75s, so the tightened bound WOULD indict it.
    const served = {
      win_prob_history: {
        kalshi: [wp(0, .5), wp(180, .52)],
      },
    };
    const merged = mergeLiveChartHistory(served, buffer(
      frame(185, .61, .61), frame(190, .64, .64), frame(195, .66, .66),
    ))!;
    const observations = merged.win_prob_history.kalshi.map(p => ({
      atMs: Date.parse(p.timestamp), synthetic: p.live_edge === true,
    }));
    const opts = { gameStartMs: Date.parse(t(0)), domainEndMs: Date.parse(t(195)) };

    expect(classifySeriesSupport(observations, opts).unsupported).toEqual([]);
    expect(classifySeriesSupport(observations, opts).lastObservedMs)
      .toBe(Date.parse(t(195)));
    // The control that keeps the assertion above honest: drop the floor and
    // the 180s interval IS indicted, which is the mechanism this case claims
    // is being held off. Without this, the same test passes on a series whose
    // cadence never tightened and proves nothing.
    expect(classifySeriesSupport(observations, { ...opts, floorS: 0 }).unsupported)
      .toEqual([{ fromMs: Date.parse(t(0)), toMs: Date.parse(t(180)), kind: "interior" }]);
  });

  it("buffers the source reading on the same validity bar as the blend", () => {
    expect(buffer(frame(35, .61, .61))[0]).toEqual({
      timestamp: t(35), home_probability: .61, source: "kalshi", source_probability: .61,
    });
    // Unusable source readings do not disqualify a good blend observation.
    expect(buffer(frame(35, .61, null))[0]).toEqual({
      timestamp: t(35), home_probability: .61,
    });
    expect(buffer(frame(35, .61, .61, ""))[0].source).toBeUndefined();
  });
});
