/**
 * #4888 — a dashed rule labelled `3` is not a label.
 *
 * WHAT A READER SAW. On `/events/14780138` (Patriots @ Seahawks, the 2026 NFL
 * season opener, Final) at 390px, the Win Probability chart drew two dashed
 * vertical rules captioned bare **`3`** and **`4`**. Nothing on the page says
 * those are quarters. Alex flagged it on his 2026-09-09 iPad pass, item 6.
 *
 * WHERE IT CAME FROM, measured rather than reasoned. `GET /api/events/14780138/
 * history` serves `period_markers` of exactly:
 *
 *   [{"period": "2", "source": "espn_box"}, {"period": "3", …}, {"period": "4", …}]
 *
 * Bare digits — no ordinal suffix, no unit noun. Every branch of
 * `normalizePeriodLabel` misses them (the plain-ordinal branch needs `st|nd|rd|th`)
 * except the "already short" test, whose alternation ends in `\d+` and returned
 * the digit unchanged.
 *
 * THE FIX IS SPORT-AWARE ON PURPOSE, and that is the thing most worth guarding.
 * `"3"` means Q3 in football, P3 in hockey and the 3rd inning in baseball, so a
 * helper that only sees the string cannot complete it. Two directions therefore
 * matter equally and both are asserted below: the completion happens when the
 * sport says what a period is, and it does NOT happen when the sport has no
 * honest completion (baseball) or is unknown. A test that only checked "3" → "Q3"
 * would pass just as well on a helper that hardcoded `Q`, which would silently
 * relabel every NHL and MLB chart.
 *
 * RED-FIRST, measured against the parent commit: `normalizePeriodLabel` there
 * takes one argument, so the second is ignored and `("3", "americanfootball_nfl")`
 * returns `"3"`. Every sport-completing assertion fails and every leave-it-alone
 * control passes — **7 failed, 8 passed of 15**. Named, because "7 failed" is only
 * evidence if you can say which seven: the five sport rows (football, ncaaf,
 * basketball, hockey, soccer), the overtime-number row, and the end-to-end
 * `derivePeriodBoundaries` row. The eight controls are green on BOTH sides, which
 * is what makes them controls rather than filler.
 *
 * AMENDED BY #4955 (ux/1191). The overtime-number row above was one of those
 * seven reds and now asserts the OPPOSITE — a bare `5` stays `5` rather than
 * becoming `Q5`, because a completion past regulation states a period that does
 * not exist. So the "7 failed of 15" measurement is no longer reproducible from
 * this file as it now stands: replayed against #4888's parent today it would read
 * 6 failed, 9 passed, the overtime row having moved from red to green. The
 * original number is left standing above because it is the record of what #4888
 * measured when it shipped, not a claim about this file's present contents. The
 * bound's own red-first measurement (10 of 18) is in
 * `periodMarkersRegulation4955.test.ts`.
 */

import { derivePeriodBoundaries, normalizePeriodLabel } from "../../lib/periodMarkers";

describe("#4888 a bare period number names its own unit", () => {
  // ---- the defect, by sport ----

  test("football: the served '3' becomes Q3", () => {
    expect(normalizePeriodLabel("3", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("4", "americanfootball_nfl")).toBe("Q4");
  });

  test("college football is the same sport family, not a special case", () => {
    expect(normalizePeriodLabel("2", "americanfootball_ncaaf")).toBe("Q2");
  });

  test("basketball also counts in quarters", () => {
    expect(normalizePeriodLabel("1", "basketball_nba")).toBe("Q1");
  });

  test("hockey counts in periods, not quarters", () => {
    expect(normalizePeriodLabel("3", "icehockey_nhl")).toBe("P3");
  });

  test("soccer counts in halves, and the digit leads", () => {
    expect(normalizePeriodLabel("2", "soccer_epl")).toBe("2H");
  });

  test("overtime numbers do NOT complete — REVERSED by #4955, see below", () => {
    // THIS ASSERTION USED TO READ `.toBe("Q5")`, and the reversal is the point
    // rather than a tidy-up, so it is edited in place rather than deleted.
    //
    // #4888 pinned `Q5` deliberately: "the unit is what the sport counts in; the
    // fix does not try to be clever about whether period 5 is regulation. ESPN
    // sends OT as its own string ('Overtime'), which an earlier branch already
    // handles." The second sentence is the load-bearing one and it is a claim
    // about the DATA, not the mapping — it says a bare `5` never arrives. But the
    // bare-digit path exists precisely because ESPN's box-score fallback does not
    // send the verbose string (that is the whole of #4888: event 14780138 served
    // `"2"`, `"3"`, `"4"` from `espn_box`), so nothing guarantees the fallback
    // spells overtime out when it spelled the quarters as digits.
    //
    // If it does arrive, `Q5` is not ambiguous-but-true like the bare digit it
    // replaced — it is false, since football has no fifth quarter. #4955 rules
    // that a completion is made only inside regulation. Bound, table and the full
    // reasoning: `periodMarkersRegulation4955.test.ts`.
    expect(normalizePeriodLabel("5", "americanfootball_nfl")).toBe("5");
  });

  // ---- the leave-it-alone half: equally load-bearing ----

  test("CONTROL: baseball keeps the bare digit — 'T3' and 'B3' are different moments", () => {
    // A bare inning number cannot be completed honestly: the digit does not say
    // top or bottom. Inventing a half would be worse than the bare number.
    expect(normalizePeriodLabel("3", "baseball_mlb")).toBe("3");
  });

  test("CONTROL: an unknown sport changes nothing", () => {
    expect(normalizePeriodLabel("3", "lacrosse_pll")).toBe("3");
  });

  test("CONTROL: no sport argument is the old behaviour, exactly", () => {
    // Backward compatibility is the reason the parameter is optional — any
    // caller that has not been threaded must not change what it renders.
    expect(normalizePeriodLabel("3")).toBe("3");
    expect(normalizePeriodLabel("3", null)).toBe("3");
    expect(normalizePeriodLabel("3", "")).toBe("3");
  });

  test("CONTROL: labels that already name their unit are untouched by the sport", () => {
    // These are the other members of the "already short" set. If the bare-digit
    // branch were placed wrongly it could swallow them.
    expect(normalizePeriodLabel("Q3", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("P2", "icehockey_nhl")).toBe("P2");
    expect(normalizePeriodLabel("HT", "soccer_epl")).toBe("HT");
    expect(normalizePeriodLabel("OT", "americanfootball_nfl")).toBe("OT");
    expect(normalizePeriodLabel("2H", "soccer_epl")).toBe("2H");
  });

  test("CONTROL: the verbose forms still win, and the sport does not disturb them", () => {
    expect(normalizePeriodLabel("3rd Quarter", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("End of 3rd Quarter", "americanfootball_nfl")).toBe("/Q3");
    expect(normalizePeriodLabel("Top 3rd", "baseball_mlb")).toBe("T3");
    expect(normalizePeriodLabel("2nd Period", "icehockey_nhl")).toBe("P2");
  });

  test("CONTROL: the plain-ordinal branch is unchanged — '3rd' is not a bare digit", () => {
    // This branch sits directly above the new one and is the near-miss that made
    // the bug hard to see; it needs a suffix, so it never saw "3".
    expect(normalizePeriodLabel("3rd", "americanfootball_nfl")).toBe("3");
  });

  test("CONTROL: golf rounds are not periods", () => {
    expect(normalizePeriodLabel("R2", "golf_pga")).toBe("R2");
  });

  // ---- end to end, through the function the chart actually calls ----

  test("the real payload's markers reach the chart as quarters", () => {
    // The exact three rows production served for event 14780138, timestamps and
    // all — including the two that share a capture stamp.
    const served = [
      { timestamp: "2026-09-10T00:24:28.214933+00:00", period: "2" },
      { timestamp: "2026-09-10T00:24:28.214933+00:00", period: "3" },
      { timestamp: "2026-09-10T02:44:55.073599+00:00", period: "4" },
    ];
    const boundaries = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      undefined,
      served,
      "americanfootball_nfl",
    );
    expect(boundaries.map((b) => b.label)).toEqual(["Q2", "Q3", "Q4"]);
  });

  test("the same payload with no sport still renders, unlabelled — the old picture", () => {
    // Proves the end-to-end path is threading the argument rather than the
    // helper having been hardcoded: same rows, no sport, old output.
    const served = [
      { timestamp: "2026-09-10T00:24:28.214933+00:00", period: "2" },
      { timestamp: "2026-09-10T02:44:55.073599+00:00", period: "4" },
    ];
    const boundaries = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      undefined,
      served,
    );
    expect(boundaries.map((b) => b.label)).toEqual(["2", "4"]);
  });
});
