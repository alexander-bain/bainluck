/**
 * A DECIDED BOARD STOPS CLAIMING LIVENESS (#6542, charts epic #2911).
 *
 * `https://bainluck.com/futures/61033331` at 390px, production 2026-09-16
 * 11:29Z: the banner said "This market has been settled. Resolved 9/16/2026."
 * and three lines later, inside the same card:
 *
 *     Last number 40 min ago
 *     ● Seattle   ● Chicago
 *     Settled.
 *
 * A liveness claim on a market that stopped existing three hours earlier — and
 * wrong on its own terms too: the stamp behind "40 min" was a re-poll of an
 * unchanged 0.99 at 10:49Z, while the probability last CHANGED at 06:50Z, and
 * the page's own glossary defines "last number" as when we last saw *a new
 * probability*.
 *
 * 🔴 THE SUPPRESSION IS IN THE `stale` ARM, NOT AT THE CAPTION, AND THAT IS THE
 * WHOLE DESIGN. `seriesFreshness` checks stale BEFORE gapped, so on a settled
 * board that is both behind and holed the age sentence is the only one that
 * renders. A bare `&& !settled` on the caption — the fix the report proposed —
 * would therefore delete the HOLE warning too and hand #2961 back its defect:
 * a flat run making its strongest claim by absence. Measured the same morning,
 * `/futures/110141` (settled 7/28) renders exactly that arm — "No numbers for
 * 33 days in this stretch" — and must keep it. The second test below is that
 * case, and it is the one to keep if this file is ever trimmed.
 */

import {
  seriesFreshness,
  seriesHasHole,
  MIN_POINTS_FOR_CADENCE,
} from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 16, 12, 0, 0);

/** `count` points ending `endsAgoMs` before NOW, evenly spaced by `gapMs`. */
function evenSeries(count: number, gapMs: number, endsAgoMs = 0): string[] {
  const end = NOW - endsAgoMs;
  return Array.from({ length: count }, (_, i) =>
    new Date(end - (count - 1 - i) * gapMs).toISOString(),
  );
}

/** An hourly run, 5.6h behind NOW, with no interior hole. */
const STALE_ONLY = evenSeries(48, HOUR, 5.6 * HOUR);

/**
 * An hourly run 5.6h behind NOW carrying a 345.6h hole — the shape of
 * `/api/futures/16630403/history`, the production fixture #2961 was built on.
 */
const STALE_AND_HOLED = [
  ...evenSeries(24, HOUR, 5.6 * HOUR + 345.6 * HOUR),
  ...evenSeries(24, HOUR, 5.6 * HOUR),
];

describe("#6542 — a settled board does not report how long ago its last number was", () => {
  test("SETTLED + behind: the liveness sentence is gone", () => {
    const live = seriesFreshness(STALE_ONLY, NOW);
    expect(live.state).toBe("stale");
    expect(live.note).toMatch(/^Last number /);

    const settled = seriesFreshness(STALE_ONLY, NOW, { settled: true });
    expect(settled.note).toBeNull();
    expect(settled.state).toBe("current");
  });

  test("🔴 SETTLED + behind AND holed: the HOLE warning survives", () => {
    // The whole reason this lives in the arm and not at the caption. #2961's
    // defect returns the moment this assertion is allowed to go null.
    const live = seriesFreshness(STALE_AND_HOLED, NOW);
    expect(live.state).toBe("stale"); // stale wins the precedence while live

    const settled = seriesFreshness(STALE_AND_HOLED, NOW, { settled: true });
    expect(settled.state).toBe("gapped");
    // Asserted by shape and against the series' own measured hole, not against
    // a span I typed: my first version of this line hardcoded "14d" from my own
    // arithmetic and was wrong about both the number and the wording.
    expect(settled.note).toMatch(/^No numbers for \d+ days in this stretch$/);
    expect(settled.largestGapMs).toBe(322.6 * HOUR);
  });

  test("CONTROL: a LIVE board is untouched — #2961 is not undone", () => {
    for (const s of [STALE_ONLY, STALE_AND_HOLED]) {
      expect(seriesFreshness(s, NOW)).toEqual(seriesFreshness(s, NOW, {}));
      expect(seriesFreshness(s, NOW, { settled: false })).toEqual(
        seriesFreshness(s, NOW),
      );
    }
  });

  test("CONTROL: the two-argument call the politics page makes is unchanged", () => {
    // `app/politics/page.tsx` calls this with no options at all, twice. If the
    // new parameter ever stops defaulting, those captions change silently.
    const f = seriesFreshness(STALE_ONLY, NOW);
    expect(f.note).toMatch(/^Last number /);
  });

  test("the measurements themselves never move — only what we SAY does", () => {
    // `seriesHasHole` and the line-breaking geometry read these. A settled
    // board must break its line in the same places a live one does.
    const live = seriesFreshness(STALE_AND_HOLED, NOW);
    const settled = seriesFreshness(STALE_AND_HOLED, NOW, { settled: true });
    expect(settled.n).toBe(live.n);
    expect(settled.ageMs).toBe(live.ageMs);
    expect(settled.medianGapMs).toBe(live.medianGapMs);
    expect(settled.largestGapMs).toBe(live.largestGapMs);
    expect(seriesHasHole(settled)).toBe(true);
    expect(seriesHasHole(settled)).toBe(seriesHasHole(live));
  });

  test("a settled board with too few points still says so", () => {
    // Deliberately NOT changed: "Only 2 numbers so far" qualifies the plot
    // rather than claiming liveness, and a two-point settled line is still a
    // two-point line. Pinned so the boundary is a decision, not an oversight.
    const thin = evenSeries(MIN_POINTS_FOR_CADENCE - 2, HOUR, 5.6 * HOUR);
    const f = seriesFreshness(thin, NOW, { settled: true });
    expect(f.state).toBe("thin");
    expect(f.note).toBe("Only 2 numbers so far");
  });
});

describe("#6542 — FuturesChart hands its settledness to the freshness read", () => {
  // Comments stripped: this file's own prose about `settled` would otherwise
  // satisfy the scan.
  const CODE = require("fs")
    .readFileSync(
      require("path").join(__dirname, "../../components/FuturesChart.tsx"),
      "utf8",
    )
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  test("the freshness call is given `settled`", () => {
    const start = CODE.indexOf("seriesFreshness(");
    expect(start).toBeGreaterThanOrEqual(0);
    // Slice to the call's own terminator rather than matching lazily across the
    // file: a `[\s\S]*?` form spanning hundreds of lines would happily find a
    // `{ settled }` belonging to something else entirely.
    const call = CODE.slice(start, CODE.indexOf(");", start));
    expect(call).toContain("{ settled }");
  });
});
