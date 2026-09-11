/**
 * #4955 — the completion #4888 added was unbounded, so it could assert a period
 * that does not exist.
 *
 * WHAT THIS IS A BOUNDARY ON. #4888 (`periodMarkersBareDigit4888.test.ts`) taught
 * `normalizePeriodLabel` to read a bare `3` as `Q3` when the sport says a period
 * is a quarter. That is right for every regulation period and wrong past the last
 * one: `n` was whatever digit arrived, so an NFL overtime rendered **`Q5`**, an
 * NHL overtime **`P4`**, and a soccer extra-time half **`3H`**. None of those
 * exist. Before #4888 those cases rendered a bare digit — unclear but true — so
 * for this slice the fix traded ambiguity for a false statement, the opposite
 * direction from the rest of it.
 *
 * `basketball_ncaab` IS THE SAME DEFECT ONE ROW UP, not a second issue. Men's
 * college basketball plays two 20-minute halves, and the single `/^basketball_/i`
 * row gave it quarters: a bare `1` read `Q1` in a competition with no quarters.
 * Raised by native/103 against the shipped Swift twin, which already carries the
 * per-sport bound; recorded on #4955 rather than filed a third time because it is
 * the same table and the same fix site.
 *
 * WHY BOTH DIRECTIONS ARE ASSERTED BELOW. A bound is a rule about what does NOT
 * happen, and a test that only checked `"5"` → `"5"` would pass on a helper that
 * had simply stopped completing anything — which would silently undo #4888 on
 * every chart. So every regulation row from #4888 is re-asserted here as a
 * control, green on BOTH sides of the change, and the out-of-range rows are the
 * red ones. Likewise the two college rows are a matched pair: NCAAB must MOVE to
 * halves and WNCAAB must NOT, because the row is an anchored prefix rather than a
 * substring, and `basketball_ncaab` is a prefix of neither.
 *
 * THE FALL-THROUGH IS ITS OWN ASSERTION. `basketball_ncaab` sits ABOVE the
 * generic `basketball_` row, so an NCAAB `3` matches a row that rejects it. The
 * first matching row has to win outright — if an out-of-range row fell through
 * instead of returning, NCAAB `3` would collect `Q3` from the row below and the
 * bound would leak on exactly the sport it was added for.
 *
 * RED-FIRST, MEASURED against the parent (`f3abb63a`, this file's lib as shipped
 * by #4888) rather than reasoned: **10 failed, 8 passed of 18**. Named, because
 * "10 failed" is only evidence if you can say which ten — five out-of-regulation
 * sport rows (football `Q5`, basketball `Q5`, hockey `P4`, soccer `3H`, WNCAAB
 * `Q5`), the two NCAAB rows (halves in regulation, and the fall-through past it),
 * the `0` row (`Q0` is as fabricated as `Q5`), and both end-to-end
 * `derivePeriodBoundaries` rows. The eight passing ones are the controls: the four
 * #4888 regulation completions, the WNCAAB anchor pair's quarters arm, baseball,
 * the unknown/absent sport row, and the noun-carrying labels.
 *
 * PROVENANCE OF THE BOUND. The table, the numbers and the `n > 0` guard mirror
 * `ios/Bain Luck/Bain Luck/Utilities/PeriodLabel.swift` (`barePeriodUnit`,
 * `barePeriod`), shipped for #4888 in PR #4925, so the two platforms read a bare
 * digit identically inside regulation. They still differ past it — iOS renders
 * its ordinal `5th` where web leaves `5` — which is flagged, not fixed: web
 * cannot follow without contradicting its own plain-ordinal branch, which
 * normalizes `"3rd"` → `"3"`. Tracked under #1834.
 *
 * NOT OBSERVED IN PRODUCTION, and said plainly rather than implied. #4955 records
 * that no live specimen with a bare period past regulation was found; the case is
 * derived from the mapping being unbounded. The NCAAB half is not hypothetical in
 * the same way — the sport plays halves whenever it plays — but no NCAAB chart
 * was photographed either, the season having not started.
 */

import { derivePeriodBoundaries, normalizePeriodLabel } from "../../lib/periodMarkers";

describe("#4955 a bare period number is completed only inside regulation", () => {
  // ---- THE DEFECT: past regulation, the unit is not asserted ----

  test("football has no Q5 — an overtime digit stays bare", () => {
    expect(normalizePeriodLabel("5", "americanfootball_nfl")).toBe("5");
    expect(normalizePeriodLabel("6", "americanfootball_ncaaf")).toBe("6");
  });

  test("basketball has no Q5 — OT1 stays bare", () => {
    expect(normalizePeriodLabel("5", "basketball_nba")).toBe("5");
    expect(normalizePeriodLabel("7", "basketball_wnba")).toBe("7");
  });

  test("hockey has no P4 — overtime stays bare", () => {
    expect(normalizePeriodLabel("4", "icehockey_nhl")).toBe("4");
    expect(normalizePeriodLabel("5", "icehockey_nhl")).toBe("5");
  });

  test("soccer has no third half — extra time stays bare", () => {
    expect(normalizePeriodLabel("3", "soccer_epl")).toBe("3");
    expect(normalizePeriodLabel("4", "soccer_uefa_champs_league")).toBe("4");
  });

  test("zero is not a period in any sport", () => {
    // `^\d+$` matches "0", and Q0 is as fabricated as Q5.
    expect(normalizePeriodLabel("0", "americanfootball_nfl")).toBe("0");
    expect(normalizePeriodLabel("0", "icehockey_nhl")).toBe("0");
  });

  // ---- THE DEFECT, one row up: men's college plays HALVES ----

  test("men's college basketball counts in halves, not quarters", () => {
    expect(normalizePeriodLabel("1", "basketball_ncaab")).toBe("1H");
    expect(normalizePeriodLabel("2", "basketball_ncaab")).toBe("2H");
  });

  test("an NCAAB overtime does not fall through to the quarters row below it", () => {
    // The bound only holds if the FIRST matching row wins outright. If an
    // out-of-range row fell through, `basketball_ncaab` "3" would pick up `Q3`
    // from the generic `basketball_` row and the bound would leak on the one
    // sport the row above was added for.
    expect(normalizePeriodLabel("3", "basketball_ncaab")).toBe("3");
    expect(normalizePeriodLabel("4", "basketball_ncaab")).toBe("4");
  });

  test("the college rows are ANCHORED PREFIXES: WNCAAB keeps its quarters", () => {
    // Women's college basketball plays four quarters. `basketball_ncaab` is not
    // a prefix of `basketball_wncaab`, so the halves row must not claim it — a
    // substring test would, and would relabel every NCAAW chart.
    expect(normalizePeriodLabel("1", "basketball_wncaab")).toBe("Q1");
    expect(normalizePeriodLabel("4", "basketball_wncaab")).toBe("Q4");
  });

  test("and WNCAAB is bounded at four like the rest of basketball", () => {
    expect(normalizePeriodLabel("5", "basketball_wncaab")).toBe("5");
  });

  // ---- CONTROLS: every #4888 regulation completion still happens ----
  // Green on BOTH sides of the change. Without these, a helper that had simply
  // stopped completing anything would pass every assertion above.

  test("football keeps all four quarters", () => {
    expect(normalizePeriodLabel("1", "americanfootball_nfl")).toBe("Q1");
    expect(normalizePeriodLabel("2", "americanfootball_nfl")).toBe("Q2");
    expect(normalizePeriodLabel("3", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("4", "americanfootball_nfl")).toBe("Q4");
  });

  test("pro basketball keeps all four quarters", () => {
    expect(normalizePeriodLabel("1", "basketball_nba")).toBe("Q1");
    expect(normalizePeriodLabel("4", "basketball_nba")).toBe("Q4");
  });

  test("hockey keeps all three periods", () => {
    expect(normalizePeriodLabel("1", "icehockey_nhl")).toBe("P1");
    expect(normalizePeriodLabel("3", "icehockey_nhl")).toBe("P3");
  });

  test("soccer keeps both halves", () => {
    expect(normalizePeriodLabel("1", "soccer_usa_mls")).toBe("1H");
    expect(normalizePeriodLabel("2", "soccer_usa_mls")).toBe("2H");
  });

  test("baseball is still absent from the table, at every inning", () => {
    // A bare inning cannot be completed honestly (T3 and B3 are different
    // moments), so it is not bounded — it is never completed at all.
    expect(normalizePeriodLabel("3", "baseball_mlb")).toBe("3");
    expect(normalizePeriodLabel("9", "baseball_mlb")).toBe("9");
    expect(normalizePeriodLabel("11", "baseball_mlb")).toBe("11");
  });

  test("an unknown or absent sport still leaves the digit alone", () => {
    expect(normalizePeriodLabel("3", "tennis_atp")).toBe("3");
    expect(normalizePeriodLabel("3", undefined)).toBe("3");
    expect(normalizePeriodLabel("3", null)).toBe("3");
    expect(normalizePeriodLabel("3", "")).toBe("3");
  });

  test("labels that name their own unit are read from the noun, not the bound", () => {
    // The bound applies ONLY to a bare digit. An explicit overtime noun already
    // says what it is and must keep saying it.
    expect(normalizePeriodLabel("Overtime", "americanfootball_nfl")).toBe("OT");
    expect(normalizePeriodLabel("2nd Overtime", "basketball_nba")).toBe("OT2");
    expect(normalizePeriodLabel("4th Quarter", "americanfootball_nfl")).toBe("Q4");
  });

  // ---- END TO END: the boundary a chart actually draws ----

  test("a chart's overtime rule is captioned by its bare digit, not by Q5", () => {
    const markers = [
      { timestamp: "2026-09-11T00:00:00Z", period: "4" },
      { timestamp: "2026-09-11T00:40:00Z", period: "5" },
    ];
    const boundaries = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      undefined,
      markers,
      "americanfootball_nfl",
    );
    expect(boundaries.map((b) => b.label)).toEqual(["Q4", "5"]);
  });

  test("an NCAAB chart's regulation rules are captioned as halves", () => {
    const markers = [
      { timestamp: "2026-09-11T00:00:00Z", period: "1" },
      { timestamp: "2026-09-11T00:30:00Z", period: "2" },
    ];
    const boundaries = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      undefined,
      markers,
      "basketball_ncaab",
    );
    expect(boundaries.map((b) => b.label)).toEqual(["1H", "2H"]);
  });
});
