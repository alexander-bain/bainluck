/**
 * #8831 — the game chart's right edge read `T9 B8`.
 *
 * Production, `/events/15318645` (Astros @ Athletics, final 6–5), 390px,
 * 2026-09-26 14:35Z: the Win Probability chart's inning captions read
 * `… T8 … T9 B8` left to right. The markers were correct and in order
 * (Bottom 8th 04:20:14Z, Top 9th 04:30:14Z). Only the captions had swapped
 * places. `T9` was last, so `anchorPeriodLabels` flipped it onto row 1 and it
 * grew leftward. `B8`, on row 0, grew rightward from a rule ten minutes
 * earlier, and one label's ink (about 22 min on this chart) is wider than ten
 * minutes. The captions never touched, being on different rows, so neither
 * #7371's nor #7876's check could see them trade places.
 *
 * The one invariant a reader relies on is guarded directly here: **captions
 * start in the order their markers happened.** The first case is the page's own
 * shape. The sweep replays this game's markers minute by minute through both
 * layout passes, as a live page grows. That is where the defect lives, since
 * the newest marker is always the one that flips.
 *
 * RED-FIRST, measured: against the parent commit this file scores 3 failed,
 * 2 passed of 5. The specimen, the flip arm and the sweep fail (the sweep on
 * 36 of its 158 frames). The two controls pass.
 */
import {
  anchorPeriodLabels,
  collapseDuplicateTransitions,
  normalizePeriodLabel,
  placePeriodLabels,
  PERIOD_LABEL_INK_FRACTION,
} from "@/lib/periodMarkers";

/** Verbatim `period_markers` from `/api/events/15318645/history`, 2026-09-26. */
const MARKERS: Array<[string, string]> = [
  ["2026-09-26T01:41:13Z", "Top 1st"],
  ["2026-09-26T01:47:13Z", "Middle 1st"],
  ["2026-09-26T01:49:13Z", "Bottom 1st"],
  ["2026-09-26T01:56:13Z", "End 1st"],
  ["2026-09-26T01:59:13Z", "Top 2nd"],
  ["2026-09-26T02:07:13Z", "Middle 2nd"],
  ["2026-09-26T02:11:14Z", "Bottom 2nd"],
  ["2026-09-26T02:22:14Z", "Top 3rd"],
  ["2026-09-26T02:27:14Z", "Middle 3rd"],
  ["2026-09-26T02:28:14Z", "Bottom 3rd"],
  ["2026-09-26T02:39:14Z", "End 3rd"],
  ["2026-09-26T02:40:14Z", "Top 4th"],
  ["2026-09-26T02:47:14Z", "Middle 4th"],
  ["2026-09-26T02:49:14Z", "Bottom 4th"],
  ["2026-09-26T02:58:14Z", "End 4th"],
  ["2026-09-26T02:59:14Z", "Top 5th"],
  ["2026-09-26T03:06:14Z", "Middle 5th"],
  ["2026-09-26T03:08:14Z", "Bottom 5th"],
  ["2026-09-26T03:13:14Z", "End 5th"],
  ["2026-09-26T03:14:14Z", "Top 6th"],
  ["2026-09-26T03:19:14Z", "Middle 6th"],
  ["2026-09-26T03:21:14Z", "Bottom 6th"],
  ["2026-09-26T03:40:14Z", "End 6th"],
  ["2026-09-26T03:41:14Z", "Top 7th"],
  ["2026-09-26T03:48:14Z", "Middle 7th"],
  ["2026-09-26T03:50:14Z", "Bottom 7th"],
  ["2026-09-26T03:57:14Z", "Top 8th"],
  ["2026-09-26T04:18:14Z", "Middle 8th"],
  ["2026-09-26T04:20:14Z", "Bottom 8th"],
  ["2026-09-26T04:30:14Z", "Top 9th"],
];

const START = Date.parse("2026-09-26T01:40:00Z"); // first pitch
const END = Date.parse("2026-09-26T04:37:00Z"); // last reading

/**
 * The domain the page's frame implies. The chart's own extent (its `chartData`)
 * is not in the payload, but the frame pins it: B8 kept its left anchor (more
 * than one ink from the right rule), T9 flipped (less than one ink), and T9
 * cleared T7 on row 1 (two inks back). With the right rule at 04:50 that makes
 * the ink 19.8–24.5 min. 175 min gives 22.05 min, inside that range, and every
 * one of those three facts holds on the parent. The page's shape is reproduced,
 * not assumed.
 */
const PAGE_END = Date.parse("2026-09-26T04:50:00Z");
const PAGE_SPAN = 175 * 60_000;
const PAGE_INK = PAGE_SPAN * PERIOD_LABEL_INK_FRACTION;

type Anchored = { timestamp: string; label: string; labelRow: number; labelPosition: string };

/** Where a caption STARTS: at its rule, or one ink left of it when flipped. */
const leftEdge = (b: Anchored, ink: number) =>
  Date.parse(b.timestamp) - (b.labelPosition === "insideTopRight" ? ink : 0);

/** The captions in the order a reader meets them, left to right. */
const readingOrder = (out: Anchored[], ink: number) =>
  [...out].sort((a, b) => leftEdge(a, ink) - leftEdge(b, ink)).map((b) => b.label);

const byTime = (out: Anchored[]) => out.map((b) => b.label);

const mark = (iso: string, label: string, labelRow: number) => ({ timestamp: iso, label, labelRow });

describe("#8831 captions read in the order the innings happened", () => {
  it("the specimen: T9 no longer starts left of B8", () => {
    // The tail as the win-probability chart handed it to the anchor pass: its
    // category axis had put T8 and B8 on row 0 and T9 on row 1.
    const out = anchorPeriodLabels(
      [
        mark("2026-09-26T03:41:14Z", "T7", 1),
        mark("2026-09-26T03:57:14Z", "T8", 0),
        mark("2026-09-26T04:20:14Z", "B8", 0),
        mark("2026-09-26T04:30:14Z", "T9", 1),
      ],
      PAGE_SPAN,
      PAGE_END,
    );
    expect(readingOrder(out, PAGE_INK)).toEqual(byTime(out));
    // The newest marker keeps its caption. B8 has only 23 min of room behind it
    // on row 0, short of the two inks a flip needs, so it is B8 that is dropped.
    expect(byTime(out)).toEqual(["T7", "T8", "T9"]);
    expect(out[out.length - 1].labelPosition).toBe("insideTopRight");
  });

  it("flips the predecessor instead, keeping both captions, when its row has room", () => {
    const out = anchorPeriodLabels(
      [
        mark("2026-09-26T03:20:00Z", "B6", 0),
        mark("2026-09-26T04:20:14Z", "B8", 0),
        mark("2026-09-26T04:30:14Z", "T9", 1),
      ],
      PAGE_SPAN,
      PAGE_END,
    );
    expect(byTime(out)).toEqual(["B6", "B8", "T9"]);
    expect(out.map((b) => b.labelPosition)).toEqual([
      "insideTopLeft",
      "insideTopRight",
      "insideTopRight",
    ]);
    expect(readingOrder(out, PAGE_INK)).toEqual(byTime(out));
  });

  it("every frame of this game, replayed live, reads in order", () => {
    const markers = collapseDuplicateTransitions(
      MARKERS.map(([timestamp, period]) => ({
        timestamp,
        label: normalizePeriodLabel(period, "baseball_mlb"),
      })),
    );
    const bad: string[] = [];
    let frames = 0;
    for (let now = START + 20 * 60_000; now <= END; now += 60_000) {
      const span = Math.max(now - START, 30 * 60_000);
      const ink = span * PERIOD_LABEL_INK_FRACTION;
      const seen = markers.filter((m) => Date.parse(m.timestamp) <= now);
      const out = anchorPeriodLabels(placePeriodLabels(seen, span), span, now) as Anchored[];
      frames++;
      if (readingOrder(out, ink).join(" ") !== byTime(out).join(" ")) {
        bad.push(`${new Date(now).toISOString().slice(11, 16)} ${readingOrder(out, ink).join(" ")}`);
      }
    }
    expect(frames).toBe(158);
    expect(bad).toEqual([]);
  });
});

describe("#8831 controls: what the rule must NOT touch", () => {
  it("an other-row predecessor more than one ink back keeps its caption and anchor", () => {
    const input = [mark("2026-09-26T03:57:14Z", "T8", 0), mark("2026-09-26T04:30:14Z", "T9", 1)];
    const out = anchorPeriodLabels(input, PAGE_SPAN, PAGE_END);
    expect(byTime(out)).toEqual(["T8", "T9"]);
    expect(out.map((b) => b.labelPosition)).toEqual(["insideTopLeft", "insideTopRight"]);
  });

  it("a chart with no flipped marker is unchanged", () => {
    const input = [
      mark("2026-09-26T02:00:00Z", "T2", 0),
      mark("2026-09-26T02:10:00Z", "B2", 1),
      mark("2026-09-26T03:00:00Z", "T5", 0),
    ];
    const out = anchorPeriodLabels(input, PAGE_SPAN, PAGE_END);
    expect(out.map(({ labelPosition, ...b }) => b)).toEqual(input);
    expect(out.every((b) => b.labelPosition === "insideTopLeft")).toBe(true);
  });
});
