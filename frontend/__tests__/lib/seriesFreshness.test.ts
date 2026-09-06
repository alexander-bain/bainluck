/**
 * A CHART DECLARES WHAT IT HOLDS (#2961, charts epic #2911).
 *
 * Every fixture below is production shape, and the two headline ones are
 * production DATA, read off `api.bainluck.com` on 2026-09-06 at ~19:1xZ:
 *
 *   • `/api/futures/16630403/history` "Yes" — n=359, median gap 1.00h, newest
 *     point 5.6h old, and a **345.6h hole** in the middle of an hourly run.
 *   • `/api/politics` presidential — n=51, median gap 8h, newest point 0.6h
 *     old, and a **≈220h hole**, on all eleven full-length rows.
 *
 * #2961's acceptance names both directions explicitly, because a chart that
 * always wears a note has just moved the problem: **a series past its own
 * cadence is marked, AND a series inside it is NOT.** Both are asserted here,
 * and the two production fixtures happen to be one of each — the futures
 * series is behind, the politics series is dead current and holed.
 */

import {
  GAP_CADENCE_MULTIPLE,
  MIN_POINTS_FOR_CADENCE,
  STALE_CADENCE_MULTIPLE,
  formatSpan,
  seriesFreshness,
  seriesHasHole,
} from "@/lib/seriesFreshness";

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 8, 6, 19, 15, 0);

/** `count` points ending `endsAgoMs` before NOW, evenly spaced by `gapMs`. */
function evenSeries(count: number, gapMs: number, endsAgoMs = 0): string[] {
  const end = NOW - endsAgoMs;
  return Array.from({ length: count }, (_, i) =>
    new Date(end - (count - 1 - i) * gapMs).toISOString(),
  );
}

describe("the cadence is read off the series, not hardcoded", () => {
  it("an hourly series 5.6h behind is marked; a DAILY series 5.6h behind is not", () => {
    // The whole reason a fixed hour threshold cannot work. Same age, same
    // point count, opposite verdicts — the only difference is the cadence each
    // series set for itself.
    const hourly = seriesFreshness(evenSeries(48, HOUR, 5.6 * HOUR), NOW);
    const daily = seriesFreshness(evenSeries(48, 24 * HOUR, 5.6 * HOUR), NOW);

    expect(hourly.state).toBe("stale");
    expect(daily.state).toBe("current");
    expect(daily.note).toBeNull();
  });

  it("uses the MEDIAN gap, so one hole cannot forgive the series that contains it", () => {
    // 40 hourly points with a single 300h hole: mean gap ≈ 8.4h, median 1h.
    // Under a mean cadence the 6h age is 0.7 medians and passes. Under the
    // median it is 6 and is marked. This is the futures series' exact shape.
    const points = [
      ...evenSeries(20, HOUR, 300 * HOUR + 20 * HOUR + 6 * HOUR),
      ...evenSeries(20, HOUR, 6 * HOUR),
    ];
    const f = seriesFreshness(points, NOW);

    expect(f.medianGapMs).toBe(HOUR);
    expect(f.state).toBe("stale");
  });
});

describe("production fixture — /api/futures/16630403/history, measured 2026-09-06", () => {
  // n=359, median 1.00h, age 5.62h, largest gap 345.6h. Reconstructed at the
  // measured shape rather than pasted at full length.
  const futures = [
    ...evenSeries(180, HOUR, 345.6 * HOUR + 178 * HOUR + 5.62 * HOUR),
    ...evenSeries(179, HOUR, 5.62 * HOUR),
  ];

  it("is marked, and the sentence names the age rather than predicting a recovery", () => {
    const f = seriesFreshness(futures, NOW);

    expect(f.state).toBe("stale");
    expect(f.note).toBe("Last number 5 hours ago");
    expect(f.note).not.toMatch(/will|soon|check back|updating/i);
  });

  it("its 345.6h interior hole is reported even though the trailing age is what it is marked for", () => {
    const f = seriesFreshness(futures, NOW);

    expect(f.largestGapMs).toBeGreaterThan(300 * HOUR);
    // `stale` wins the sentence; the hole is still available to a renderer.
    expect(seriesHasHole(f)).toBe(true);
  });
});

describe("production fixture — /api/politics presidential, measured 2026-09-06", () => {
  // n=51, median 8h, age 0.56h, largest gap 219.9h. The case every
  // newest-point threshold passes: it is completely up to date and mostly hole.
  const politics = [
    ...evenSeries(25, 8 * HOUR, 219.9 * HOUR + 25 * 8 * HOUR + 0.56 * HOUR),
    ...evenSeries(26, 8 * HOUR, 0.56 * HOUR),
  ];

  it("is NOT called behind — 0.56h on an 8h cadence is current", () => {
    const f = seriesFreshness(politics, NOW);
    expect(f.ageMs).toBeLessThan(HOUR);
    expect(f.state).not.toBe("stale");
  });

  it("is marked for the hole instead, and the sentence says how wide", () => {
    const f = seriesFreshness(politics, NOW);

    expect(f.state).toBe("gapped");
    expect(f.medianGapMs).toBe(8 * HOUR);
    expect(f.note).toBe("No numbers for 9 days in this stretch");
  });
});

describe("the other direction — a healthy series says nothing", () => {
  it("an on-cadence hourly series is current and carries no note", () => {
    const f = seriesFreshness(evenSeries(60, HOUR), NOW);

    expect(f.state).toBe("current");
    expect(f.note).toBeNull();
    expect(seriesHasHole(f)).toBe(false);
  });

  it("one skipped beat is normal operation, not a hole", () => {
    // A single doubled gap in an hourly run: 2h against a 6× threshold.
    const points = [...evenSeries(30, HOUR, 31 * HOUR), ...evenSeries(30, HOUR)];
    expect(seriesFreshness(points, NOW).state).toBe("current");
  });

  it("a fast series is not marked for a lapse smaller than the absolute floor", () => {
    // 2-minute cadence × 4 = 8 minutes, which the 15-minute floor overrides.
    const twoMin = 2 * 60 * 1000;
    expect(seriesFreshness(evenSeries(60, twoMin, 10 * 60 * 1000), NOW).state).toBe("current");
  });

  it("is silent right up to its own threshold and speaks just past it", () => {
    const justInside = seriesFreshness(
      evenSeries(40, HOUR, STALE_CADENCE_MULTIPLE * HOUR - 60_000),
      NOW,
    );
    const justOutside = seriesFreshness(
      evenSeries(40, HOUR, STALE_CADENCE_MULTIPLE * HOUR + 60_000),
      NOW,
    );

    expect(justInside.state).toBe("current");
    expect(justOutside.state).toBe("stale");
  });
});

describe("the states that are not a cadence judgement", () => {
  it("no points at all", () => {
    const f = seriesFreshness([], NOW);
    expect(f.state).toBe("empty");
    expect(f.note).toBe("No numbers yet");
    // The measured instance: /api/politics serves DeSantis and Rubio at n=0.
    expect(seriesFreshness(null, NOW).state).toBe("empty");
    expect(seriesFreshness(undefined, NOW).state).toBe("empty");
  });

  it("too few points to have a cadence — the measured n=3 rows", () => {
    // J.D. Vance and Ted Cruz, /api/politics, n=3 at the same visual weight as
    // their n=51 neighbours.
    const f = seriesFreshness(evenSeries(3, 7 * HOUR, 3.5 * HOUR), NOW);

    expect(f.state).toBe("thin");
    expect(f.note).toBe("Only 3 numbers so far");
    expect(f.medianGapMs).toBeNull();
    expect(MIN_POINTS_FOR_CADENCE).toBeGreaterThan(3);
  });

  it("points that exist but cannot be dated are UNDATED, never current", () => {
    // gotcha #53 on a render path: unreadable is not healthy.
    const f = seriesFreshness(["not a date", null, {}, "also not a date"], NOW);

    expect(f.state).toBe("undated");
    expect(f.note).toBe("These numbers aren't dated");
    expect(f.state).not.toBe("current");
  });

  it("survives every junk input a payload can carry without throwing", () => {
    // The caller is a render path; a throw here is a blank page.
    expect(() => seriesFreshness([NaN, Infinity, "", "1999-13-45"], NOW)).not.toThrow();
    expect(seriesFreshness([NaN, Infinity, ""], NOW).state).toBe("undated");
  });
});

describe("arithmetic that has bitten this codebase before", () => {
  it("accepts unsorted input without inventing a hole from the disorder", () => {
    const ordered = evenSeries(40, HOUR);
    const shuffled = [...ordered].reverse();

    expect(seriesFreshness(shuffled, NOW)).toEqual(seriesFreshness(ordered, NOW));
  });

  it("a point stamped in the future is clock skew, not a negative age", () => {
    const f = seriesFreshness(evenSeries(40, HOUR, -30 * 60 * 1000), NOW);
    expect(f.ageMs).toBe(0);
    expect(f.state).toBe("current");
  });

  it("spans round DOWN, so a hole is never flattered into a smaller one", () => {
    // Same rule as `freshnessAge` next door — "8 days" must never read "7".
    expect(formatSpan(9.9 * 24 * HOUR)).toBe("9 days");
    expect(formatSpan(47.9 * HOUR)).toBe("47 hours");
    expect(formatSpan(1 * HOUR)).toBe("1 hour");
    expect(formatSpan(59 * 60 * 1000)).toBe("59 min");
    expect(formatSpan(0)).toBe("0 min");
    expect(formatSpan(-5)).toBe("0 min");
  });

  it("a span is never suffixed 'ago' — a hole did not happen relative to now", () => {
    expect(formatSpan(345.6 * HOUR)).not.toMatch(/ago/);
  });
});

describe("no rendered sentence uses our own vocabulary at the reader", () => {
  // JARGON_BANS: "stale" is our price_state enum. TRADING_VOCAB_BANS: the word
  // is PROBABILITY, never "price". These surfaces are outside the bundle gate's
  // hard scope, so this is the only thing standing between the rulings and the
  // copy — assert it here rather than assuming coverage elsewhere.
  const everyNote = [
    seriesFreshness([], NOW),
    seriesFreshness(["junk"], NOW),
    seriesFreshness(evenSeries(3, HOUR), NOW),
    seriesFreshness(evenSeries(40, HOUR, 40 * HOUR), NOW),
    seriesFreshness([...evenSeries(20, HOUR, 300 * HOUR), ...evenSeries(20, HOUR)], NOW),
  ]
    .map((f) => f.note)
    .filter((n): n is string => n !== null);

  it("covers every note-bearing state", () => {
    expect(everyNote.length).toBe(5);
  });

  it.each(everyNote)("%s — no banned vocabulary, no promise about later", (note) => {
    expect(note).not.toMatch(/\bstale\b/i);
    expect(note).not.toMatch(/\b(un)?pric(e|es|ed|ing)\b/i);
    expect(note).not.toMatch(/\bwill\b|\bcheck back\b|\bcoming soon\b|\bsoon\b/i);
  });
});

describe("seriesHasHole answers the rendering question, not the reader's", () => {
  it("is false for states that never establish a cadence", () => {
    expect(seriesHasHole(seriesFreshness([], NOW))).toBe(false);
    expect(seriesHasHole(seriesFreshness(evenSeries(3, HOUR), NOW))).toBe(false);
    expect(seriesHasHole(seriesFreshness(["junk"], NOW))).toBe(false);
  });

  it("is true for a holed series whether or not it is also behind", () => {
    const holedAndCurrent = [...evenSeries(20, HOUR, 300 * HOUR), ...evenSeries(20, HOUR)];
    const holedAndBehind = [
      ...evenSeries(20, HOUR, 300 * HOUR + 40 * HOUR),
      ...evenSeries(20, HOUR, 40 * HOUR),
    ];

    expect(seriesFreshness(holedAndCurrent, NOW).state).toBe("gapped");
    expect(seriesFreshness(holedAndBehind, NOW).state).toBe("stale");
    expect(seriesHasHole(seriesFreshness(holedAndCurrent, NOW))).toBe(true);
    expect(seriesHasHole(seriesFreshness(holedAndBehind, NOW))).toBe(true);
  });

  it("respects the same 6x threshold the state does", () => {
    expect(GAP_CADENCE_MULTIPLE).toBe(6);
    // One interior gap in an hourly run, sized either side of 6x by a minute.
    const withGap = (gapMs: number) => [
      ...evenSeries(20, HOUR, gapMs + 19 * HOUR),
      ...evenSeries(20, HOUR),
    ];

    expect(seriesHasHole(seriesFreshness(withGap(GAP_CADENCE_MULTIPLE * HOUR - 60_000), NOW))).toBe(
      false,
    );
    expect(seriesHasHole(seriesFreshness(withGap(GAP_CADENCE_MULTIPLE * HOUR + 60_000), NOW))).toBe(
      true,
    );
  });
});
