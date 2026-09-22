/**
 * #7960 — a marker that reads `8th Inning` is a sentence in a strip of chips.
 *
 * WHAT A READER SAW. `/events/15316384` (Nationals @ Tigers, MLB, Final 9–2) at
 * 390px. The win-probability chart's marker strip read
 * `T1 1 T3 T4 T5 B5 T6 T7 8th Inning` with `T9` underneath it. Measured off the
 * rendered SVG with `getBoundingClientRect()`
 * (`tools/period-label-ink-collision-7940.mjs`, frame
 * `artifacts/ux-1431/7940/mlb-home-won-9to2-chart0.png`): the odd label is
 * **57px wide on a 252px plot** — 23% of the chart — against 7–15px for every
 * sibling, and it runs over the column `T9` is drawn in.
 *
 * WHERE IT CAME FROM. `normalizePeriodLabel`'s last line is `return s`, which is
 * the right default for a label we do not recognise: an unknown shape reaches
 * the chart verbatim rather than vanishing. So a missing branch does not fail
 * loudly, it PRINTS. `"8th Inning"` missed every branch — the quarter/period/
 * half ones want a different unit, the half-inning one wants a `Top`/`Bottom`
 * prefix, and the plain-ordinal one is anchored so the trailing ` Inning`
 * defeats it.
 *
 * ⭐ THE DEFECT IS A WIDTH, WHICH IS WHY NOTHING CAUGHT IT. The label is
 * present, correctly spelled, on the right rule, at the right instant and on a
 * sensible row — every existing channel (`data-period-labels`,
 * `data-period-label-rows`, `data-period-times`) reads healthy on it. Only its
 * size is wrong, and no guard was asking about size.
 *
 * WHY IT RETURNS `"8"` AND NOT `"T8"`. The verbose form does not say which
 * half-inning it is. Inferring `Top` to make the label match its neighbours
 * would be #7901 in miniature: asserting a fact nobody observed, for tidiness.
 * The bare number is also what the plain-ordinal branch already yields, so the
 * `1`, `4` and `8` on that same chart are this value's precedent.
 *
 * RED-FIRST, checked against the parent commit: there the regex is
 * `/^(\d+)(?:st|nd|rd|th)$/i`, so `"8th Inning"` returns `"8th Inning"` and the
 * first assertion below fails. The bare-number and unknown-label controls pass
 * on both sides — they exist to stop the fix over-reaching, not to prove it.
 */
import {
  normalizePeriodLabel,
} from "@/lib/periodMarkers";

describe("#7960 — the verbose inning form is a marker, not a caption", () => {
  it("normalises `8th Inning` to the same bare number the ordinal form yields", () => {
    expect(normalizePeriodLabel("8th Inning")).toBe("8");
    // The value is not merely short — it is the SAME value the sibling shape
    // produces, which is what makes the strip uniform rather than just smaller.
    expect(normalizePeriodLabel("8th Inning")).toBe(normalizePeriodLabel("8th"));
  });

  it("covers the ordinal spellings and the suffixless form ESPN also sends", () => {
    expect(normalizePeriodLabel("1st Inning")).toBe("1");
    expect(normalizePeriodLabel("2nd Inning")).toBe("2");
    expect(normalizePeriodLabel("3rd Inning")).toBe("3");
    expect(normalizePeriodLabel("9 Inning")).toBe("9");
    // Case and whitespace are the renderer's problem, not the reader's.
    expect(normalizePeriodLabel("  8TH INNING  ")).toBe("8");
    expect(normalizePeriodLabel("8th inning")).toBe("8");
  });

  it("produces a label the width of its siblings, which is the actual defect", () => {
    // Asserted as a LENGTH rather than a value, because "57px on a 252px plot"
    // is what the reader saw and a value assertion alone would pass on a fix
    // that returned some other long string.
    const siblings = ["T5", "B5", "T6", "T7", "T9"].map((l) => normalizePeriodLabel(l));
    const longestSibling = Math.max(...siblings.map((s) => s.length));
    expect(normalizePeriodLabel("8th Inning").length).toBeLessThanOrEqual(longestSibling);
    expect("8th Inning".length).toBeGreaterThan(longestSibling * 3);
  });

  // ── Controls. These pass on BOTH sides of the fix; they fail on an
  // over-reaching one, which is the only way this branch can do damage.

  it("CONTROL: a bare digit still reaches #4888's sport-aware completion", () => {
    // The new alternation requires an ordinal suffix or the unit. If it ever
    // accepts a bare number, this branch swallows it before `labelBarePeriod`
    // sees it and every NFL chart silently loses `Q3` -> `3`.
    expect(normalizePeriodLabel("3", "americanfootball_nfl")).toBe("Q3");
    expect(normalizePeriodLabel("3", "icehockey_nhl")).toBe("P3");
    // Baseball has no honest completion, so the digit stays a digit (#4888).
    expect(normalizePeriodLabel("3", "baseball_mlb")).toBe("3");
    expect(normalizePeriodLabel("3")).toBe("3");
  });

  it("CONTROL: the half-inning form still wins, and still says which half", () => {
    expect(normalizePeriodLabel("Top 8th")).toBe("T8");
    expect(normalizePeriodLabel("Bottom 5th")).toBe("B5");
    // `Middle` is deliberately dropped to keep the strip to half-inning STARTS;
    // a widened ordinal branch must not resurrect it.
    expect(normalizePeriodLabel("Middle 8th")).toBe("");
  });

  it("`End 8th` is DROPPED — the open question this control left has been settled by #7982", () => {
    // 🪤 THIS CONTROL WAS WRITTEN ASSERTING `""` AND IT FAILED — against the
    // PARENT COMMIT as well as this one, which is the only reason it was worth
    // a test of its own. It then pinned `"8"`, the value master produced, and
    // said in as many words that whether `"8"` was RIGHT (against `""`, or a
    // `/8` end-marker) was a live question this ship would not settle.
    //
    // #7982 settled it: `""`. The reasoning the control recorded was the whole
    // case — `iMatch` lists `end` among the prefixes it drops, but the `isEnd`
    // detection ~30 lines above STRIPS `^(?:end|start)\s+(?:of\s+)?` before
    // `iMatch` runs, so by then the string is `"8th"` and the plain-ordinal
    // branch answers it. That branch now returns `""` when `isEnd`, and the
    // dead `|end` alternative is gone rather than left to mislead a third
    // reader. `"End 8"` lands one branch further on (no suffix, no unit) and is
    // dropped there for the same reason, so the two spellings agree.
    //
    // Measured over ux/1433's 70-event / 7-sport corpus: 10 charts changed, all
    // baseball; no non-baseball end marker reaches either branch (they carry
    // their unit word and become `/Q3`, `/P1`); no label gained anywhere.
    expect(normalizePeriodLabel("End 8th")).toBe("");
    expect(normalizePeriodLabel("End 8")).toBe("");
    // The START forms this file exists to protect are untouched — a drop that
    // reached them would be a #7960 regression, not a #7982 fix.
    expect(normalizePeriodLabel("8th Inning")).toBe("8");
    expect(normalizePeriodLabel("8th")).toBe("8");
  });

  it("CONTROL: an unknown label is still returned verbatim, not truncated to a digit", () => {
    // The anchor is what keeps this true. Without it, `^(\d+)…inning` would
    // match a prefix and print "7" for a label that means something else.
    expect(normalizePeriodLabel("8th Inning Stretch")).toBe("8th Inning Stretch");
    expect(normalizePeriodLabel("7th Inning Stretch")).toBe("7th Inning Stretch");
    expect(normalizePeriodLabel("Rain Delay")).toBe("Rain Delay");
  });

  it("CONTROL: the other sports' units are untouched by a branch about innings", () => {
    expect(normalizePeriodLabel("1st Quarter")).toBe("Q1");
    expect(normalizePeriodLabel("End of 1st Quarter")).toBe("/Q1");
    expect(normalizePeriodLabel("2nd Period")).toBe("P2");
    expect(normalizePeriodLabel("1st Half")).toBe("1H");
    expect(normalizePeriodLabel("Halftime")).toBe("HT");
    expect(normalizePeriodLabel("Overtime")).toBe("OT");
  });
});
