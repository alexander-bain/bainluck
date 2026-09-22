// #7982 — AN MLB CHART DREW END-OF-INNING MARKERS AS BARE DIGITS.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/15316384`, 390px, both charts. The period strip read
//
//     T1  B1  B2  T4  T5  B5  T6  T7  8  T9
//
// and on `/events/15315582`
//
//     T1  T2  T3  B3  4  T6  T7  T8  9
//
// Every marker names its half-inning except one or two, which are bare numbers.
// A reader cannot tell what `8` means with `T7` and `T9` either side of it, and
// it is not a half-inning at all — it is the END of the 8th, a marker the code
// has always said it does not draw.
//
// ── WHY THE BRANCH THAT SAYS SO NEVER RAN ────────────────────────────────────
//
// `normalizePeriodLabel` matched `^(top|bottom|mid(?:dle)?|end)\s+(\d+)` and
// returned "" for the `end` arm, under a comment reading "Skip 'Middle' and
// 'End' to avoid chart clutter". But ~27 lines earlier:
//
//     const isEnd = /^end\s+(?:of\s+)?/i.test(s);
//     s = s.replace(/^(?:end|start)\s+(?:of\s+)?/i, "");
//
// The strip has already removed the word, so the alternation's `end` arm never
// saw an input beginning with "end" — UNREACHABLE FOR EVERY FORM. `"End 8th"`
// reached it as `"8th"`, `"End of 8th Inning"` as `"8th Inning"`; neither
// matches a pattern anchored on `top|bottom|…`, both fell through to the
// plain-ordinal branch, and that returns the bare number. `Middle` was fine —
// nothing strips it. The two halves of one comment behaved differently, which
// is why reading the comment told you the opposite of what the code did.
//
// ── WHY THE DROP IS UNCONDITIONAL ON SPORT ───────────────────────────────────
//
// The ordinal branch is shared, so the question worth measuring before moving
// it was whether some other sport needs an end-of-period ordinal. Measured on
// ux/1433's 70-event / 7-sport corpus with the REAL function, before and after:
//
//     sport                   end-strings   became ""   before -> after
//     baseball_mlb                    242         242   bare digits -> dropped
//     basketball_wnba                 127           0   /Q1 /Q3 /Q4  unchanged
//     americanfootball_ncaaf           71           0   /Q1 /Q2 /Q3 /Q4 unchanged
//     americanfootball_nfl             36           0   /Q1 /Q3 /Q4  unchanged
//     icehockey_nhl                    33           0   /P1 /P2 /P3  unchanged
//     soccer_epl, mma                   0           0   emits none
//
//     charts changed: 10 of 70, every one baseball.  LABELS GAINED: NONE.
//
// Every non-baseball end marker carries its unit word and is consumed by
// `qMatch`/`pMatch` into `/Q3`, `/P1` long before the ordinal branch. So the
// sport gate would have been dead weight — and leaving it off is the safe
// direction for a shape nobody has seen: an unrecognised `End of Nth` becomes a
// hole rather than a confident `N` claiming period N STARTED where it ended.
//
// ── WHAT THIS GUARD PINS ─────────────────────────────────────────────────────
//
// The label rule is pure, so this exercises it directly on production strings
// rather than rendering. The specimen below is `/events/15316384`'s real
// `period_markers`, all 29 rows, carrying BOTH spellings (`End 1st` and `End of
// 1st Inning`) — the reason it is inlined rather than read from
// `artifacts/ux-1433/corpus/` is that the corpus is untracked and a test that
// reads an untracked path does not fail on CI, it fails to START.
//
// Distinct from #7960, whose bare-number return for a START ordinal is correct
// and deliberate and is asserted here so this change cannot quietly revert it.

import {
  normalizePeriodLabel,
  derivePeriodBoundaries,
} from "@/lib/periodMarkers";

const MLB = "baseball_mlb";

/** `/events/15316384` period_markers, production, 2026-09-21. */
const SPECIMEN_15316384: Array<{ timestamp: string; period: string }> = [
  { timestamp: "2026-09-21T22:40:33.118316+00:00", period: "Top 1st" },
  { timestamp: "2026-09-21T22:47:33.144241+00:00", period: "End of 1st Inning" },
  { timestamp: "2026-09-21T22:48:33.263011+00:00", period: "Bottom 1st" },
  { timestamp: "2026-09-21T22:59:33.097192+00:00", period: "End 1st" },
  { timestamp: "2026-09-21T23:03:33.151006+00:00", period: "Top 2nd" },
  { timestamp: "2026-09-21T23:08:33.138155+00:00", period: "Bottom 2nd" },
  { timestamp: "2026-09-21T23:14:33.186170+00:00", period: "End 2nd" },
  { timestamp: "2026-09-21T23:16:33.192465+00:00", period: "Top 3rd" },
  { timestamp: "2026-09-21T23:22:33.214999+00:00", period: "End of 3rd Inning" },
  { timestamp: "2026-09-21T23:24:33.228362+00:00", period: "Bottom 3rd" },
  { timestamp: "2026-09-21T23:27:33.223102+00:00", period: "Top 4th" },
  { timestamp: "2026-09-21T23:36:33.236595+00:00", period: "End of 4th Inning" },
  { timestamp: "2026-09-21T23:38:33.215754+00:00", period: "Bottom 4th" },
  { timestamp: "2026-09-21T23:44:33.186586+00:00", period: "End 4th" },
  { timestamp: "2026-09-21T23:46:33.185987+00:00", period: "Top 5th" },
  { timestamp: "2026-09-21T23:52:33.218695+00:00", period: "Bottom 5th" },
  { timestamp: "2026-09-22T00:08:49.460397+00:00", period: "Top 6th" },
  { timestamp: "2026-09-22T00:16:49.518308+00:00", period: "End of 6th Inning" },
  { timestamp: "2026-09-22T00:18:49.517808+00:00", period: "Bottom 6th" },
  { timestamp: "2026-09-22T00:24:49.530255+00:00", period: "End 6th" },
  { timestamp: "2026-09-22T00:27:49.554457+00:00", period: "Top 7th" },
  { timestamp: "2026-09-22T00:30:49.539275+00:00", period: "End of 7th Inning" },
  { timestamp: "2026-09-22T00:31:49.550329+00:00", period: "Bottom 7th" },
  { timestamp: "2026-09-22T00:38:49.553460+00:00", period: "End 7th" },
  { timestamp: "2026-09-22T00:40:49.593948+00:00", period: "Top 8th" },
  { timestamp: "2026-09-22T00:47:49.730249+00:00", period: "End of 8th Inning" },
  { timestamp: "2026-09-22T00:51:52.048687+00:00", period: "Bottom 8th" },
  { timestamp: "2026-09-22T00:55:49.582077+00:00", period: "End 8th" },
  { timestamp: "2026-09-22T01:01:49.572076+00:00", period: "Top 9th" },
];

describe("#7982 — an end-of-inning marker is dropped, not numbered", () => {
  // Both spellings production actually sends, in both the terse and verbose
  // forms. These are the strings that painted `8` and `9` on the strip.
  test.each([
    "End 1st", "End 2nd", "End 3rd", "End 4th", "End 5th",
    "End 6th", "End 7th", "End 8th", "End 9th",
    "End of 1st Inning", "End of 3rd Inning", "End of 4th Inning",
    "End of 7th Inning", "End of 8th Inning",
  ])("%s is dropped", (raw) => {
    expect(normalizePeriodLabel(raw, MLB)).toBe("");
  });

  test("the case the comment always got right still works", () => {
    expect(normalizePeriodLabel("Middle 3rd", MLB)).toBe("");
    expect(normalizePeriodLabel("Mid 3rd", MLB)).toBe("");
  });

  // 🔴 THE SECOND SPELLING, which lands one branch further on: no ordinal
  // suffix and no unit, so `ordMatch` never sees it and the bare-number branch
  // does. Zero occurrences in the corpus, so this is a consistency arm — but it
  // is the worse half of the defect, because `labelBarePeriod` COMPLETES a bare
  // number from the sport and would print a confident start label for an end.
  test("the bare `End N` spelling is dropped too", () => {
    expect(normalizePeriodLabel("End 8", MLB)).toBe("");
    expect(normalizePeriodLabel("End of 8", MLB)).toBe("");
  });

  test("a bare end marker does not get COMPLETED into a false start label", () => {
    // Without the `isEnd` arm this is `Q3` — a quarter asserted to begin at the
    // moment it was observed to finish. That is the failure mode #4888's
    // sport-completion introduces for this input class, and it is why the drop
    // sits on the bare branch and not only on the ordinal one.
    expect(normalizePeriodLabel("End of 3", "americanfootball_nfl")).toBe("");
    expect(normalizePeriodLabel("End 1", "icehockey_nhl")).toBe("");
    // #4888 itself is untouched: a bare START number still completes.
    expect(normalizePeriodLabel("3", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("1", "icehockey_nhl")).toBe("P1");
  });

  // 🔴 THE ARM THAT MAKES THE FIX FALSIFIABLE RATHER THAN A DELETION.
  // "return '' more often" passes every assertion above. These are the labels a
  // too-wide drop would take with it, so a fix that reaches past end-markers
  // fails here instead of silently emptying the strip.
  test("a half-inning START is untouched", () => {
    expect(normalizePeriodLabel("Top 8th", MLB)).toBe("T8");
    expect(normalizePeriodLabel("Bottom 8th", MLB)).toBe("B8");
    expect(normalizePeriodLabel("Top 1st", MLB)).toBe("T1");
  });

  test("#7960's bare-number return for a START ordinal is not reverted", () => {
    // The whole inning, no half named — deliberately `8`, not `T8`.
    expect(normalizePeriodLabel("8th Inning", MLB)).toBe("8");
    expect(normalizePeriodLabel("3rd", MLB)).toBe("3");
    // And "Start of" is not "End of": the strip consumes both words, only one
    // of them means the period is over.
    expect(normalizePeriodLabel("Start of 8th Inning", MLB)).toBe("8");
  });

  test("an unrecognised shape still falls through verbatim", () => {
    // `return s` is the documented default and #7960's trap; anchoring matters.
    expect(normalizePeriodLabel("8th Inning Stretch", MLB)).toBe("8th Inning Stretch");
  });

  // 🔴 CROSS-SPORT. The ordinal branch is shared; these are the 267 corpus
  // end-strings that must NOT have changed, one per distinct shape.
  test.each([
    ["End of 1st Quarter", "americanfootball_nfl", "/Q1"],
    ["End of 3rd Quarter", "americanfootball_ncaaf", "/Q3"],
    ["End of 4th Quarter", "basketball_wnba", "/Q4"],
    ["End of 1st Period", "icehockey_nhl", "/P1"],
    ["End of 2nd Half", "soccer_epl", "/2H"],
  ])("%s (%s) still reads %s", (raw, sport, expected) => {
    expect(normalizePeriodLabel(raw, sport)).toBe(expected);
  });

  test("the start/end distinction those carry is still a distinction", () => {
    expect(normalizePeriodLabel("1st Quarter", "americanfootball_nfl")).toBe("Q1");
    expect(normalizePeriodLabel("End of 1st Quarter", "americanfootball_nfl")).toBe("/Q1");
  });
});

describe("#7982 — the specimen's chart strip", () => {
  const strip = () =>
    derivePeriodBoundaries(undefined, undefined, undefined, SPECIMEN_15316384, MLB).map(
      (b) => b.label,
    );

  test("no bare digit survives on /events/15316384", () => {
    // BEFORE (this same call on master):
    //   T1 1 B1 T2 B2 2 T3 3 B3 T4 4 B4 T5 B5 T6 6 B6 T7 7 B7 T8 8 B8 T9
    expect(strip()).toEqual([
      "T1", "B1", "T2", "B2", "T3", "B3", "T4", "B4",
      "T5", "B5", "T6", "B6", "T7", "B7", "T8", "B8", "T9",
    ]);
  });

  test("every surviving marker names its half-inning", () => {
    // The property the reader actually has: no label on an MLB strip may be a
    // number that does not say which half of which inning it is.
    for (const label of strip()) expect(label).toMatch(/^[TB]\d+$/);
  });

  test("this REMOVED markers and invented none", () => {
    // Guards the other direction from the equality above: a fix that dropped
    // the bare digits but also renamed or added a marker would be caught here
    // even if someone later loosened the exact list.
    const before = [
      "T1", "1", "B1", "T2", "B2", "2", "T3", "3", "B3", "T4", "4", "B4",
      "T5", "B5", "T6", "6", "B6", "T7", "7", "B7", "T8", "8", "B8", "T9",
    ];
    const after = strip();
    expect(after.filter((l) => !before.includes(l))).toEqual([]);
    expect(before.filter((l) => !after.includes(l))).toEqual([
      "1", "2", "3", "4", "6", "7", "8",
    ]);
  });
});
