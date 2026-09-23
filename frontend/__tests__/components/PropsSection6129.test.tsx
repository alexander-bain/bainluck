/**
 * #6129 — WHAT HIT SAID ONE THING 85 TIMES AND ITS 85 QUESTIONS NONE.
 *
 * Production LOOK of `/events/14637256` (Giants 28 — Cowboys 20, Sunday night
 * football) at 390px on 2026-09-14, then measured in the live DOM:
 *
 *   > WHAT HIT  Props
 *   > The pregame script. No grades published for these props.
 *   > TOUCHDOWNS
 *   >   Najee Harris: 1+     Resolved · grading unavailable
 *   >   Darnell Moone…       Resolved · grading unavailable
 *   >   George Picken…       Resolved · grading unavailable
 *   > RUSHING YARDS
 *   >   Najee Harris: 1…     Resolved · grading unavailable
 *   >   Najee Harris: 1…     Resolved · grading unavailable
 *   >   Najee Harris: 2…     Resolved · grading unavailable
 *   >   … × 85
 *
 * The backend graded 0 of 85 player props (`hit`, `is_winner` and
 * `resolution_source` all null on every row of
 * `/api/events/14637256/game-markets`), so every row took the ungraded branch:
 *
 *   · 85 of 85 rows carried the chip, each 198px wide on a 390px phone;
 *   · that left the label span 108px, and 77 of 85 labels (91%) were clipped;
 *   · the 85 rows collapsed to 35 distinct visible strings, 63 of them sharing
 *     their visible text with a sibling — ten rows reading `Malachi Fields:…`,
 *     nine `Jake Ferguson…`, seven `CeeDee Lamb:…`.
 *
 * Every label in this section ends in the number that distinguishes it
 * (`Najee Harris: 10+` … `: 80+`), so the clip lands precisely on the only part
 * the reader needs.
 *
 * ── THE RULING WAS ALREADY WRITTEN, FOR THE SIBLING BRANCH ───────────────────
 *
 * D102 / #4530 removed the identical chip (`pregame mark pending`, 89 of 298
 * rows of an NFL page) from `ScriptValue`, one function up, on the grounds that
 * *"the summary states the reason ONCE for the whole group; repeating it per row
 * is the diagnostic prose notice 34 is about."* `GradedValue` is the same shape
 * and was simply never revisited. The section's blurb — `GRADED_BLURB_UNGRADED`,
 * which #1650 put there for exactly this state — is the summary.
 *
 * ── WHY EVERY POSITIVE ASSERTION IS PAIRED (gotcha #43) ──────────────────────
 *
 * A change that deleted the chip outright would satisfy "the ungraded list is
 * quiet". So each test below has a control in which the chip MUST survive:
 *
 *   1. a MIXED list — one graded row, one not. The blurb then claims grades, so
 *      the ungraded row is the only place a reader can learn it was not graded.
 *   2. a row that is individually `settled` inside a LIVE section. Its section
 *      blurb is THE DIVERGENCE's and makes no statement about grading.
 *   3. the graded rows themselves keep their verdicts in every case.
 *
 * And the width claim is asserted as a claim about MARKUP, not about pixels:
 * jsdom has no layout, so the test that would "prove" 108px cannot exist here.
 * What it can prove is that the row emits the label and no longer emits a
 * competing fixed-width sibling — which is the whole mechanism. The pixel
 * numbers above are the production measurement and are quoted, not re-derived.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import { propResultLabel, SETTLED_NO_GRADE_LABEL } from "../../lib/propGrade";

/**
 * The production family, verbatim from the payload — same player, same suffix
 * grammar, so a fix that only works on short labels cannot pass.
 */
const UNGRADED_LADDER: PropMark[] = [
  { key: 1, label: "Najee Harris: 10+", pregame_mark: 0.5, current: 0.52, graded_result: null },
  { key: 2, label: "Najee Harris: 15+", pregame_mark: 0.4, current: 0.44, graded_result: null },
  { key: 3, label: "Najee Harris: 20+", pregame_mark: 0.3, current: 0.31, graded_result: null },
  { key: 4, label: "Malachi Fields: 50+", pregame_mark: 0.2, current: 0.21, graded_result: null },
  { key: 5, label: "Malachi Fields: 60+", pregame_mark: 0.1, current: 0.12, graded_result: null },
];

/** Control: the same list with ONE row graded, which is a legitimate page. */
const MIXED: PropMark[] = [
  { key: 1, label: "Najee Harris: 10+", pregame_mark: 0.5, current: 1, graded_result: "hit" },
  { key: 2, label: "Najee Harris: 15+", pregame_mark: 0.4, current: 0.44, graded_result: null },
];

function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#6129 · WHAT HIT states 'no grades published' once, not once per row", () => {
  test("an ungraded settled list carries the sentence in the blurb and nowhere else", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNGRADED_LADDER} state="graded" />);
    const text = visibleText(html);

    // The section still names itself and still states the fact — once.
    expect(text).toContain("What hit");
    expect(text).toContain("No grades published for these props.");
    expect(text.split("No grades published").length - 1).toBe(1);

    // And not one row repeats it.
    expect(text).not.toContain(SETTLED_NO_GRADE_LABEL);
    expect(text).not.toContain("grading unavailable");
  });

  test("every question keeps its own name — the rungs are distinguishable again", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNGRADED_LADDER} state="graded" />);
    const text = visibleText(html);
    for (const item of UNGRADED_LADDER) {
      // UX-P036 strips the family name from a rung, so assert the half that
      // distinguishes the row — the suffix the 198px chip was clipping off.
      const suffix = item.label.split(": ")[1];
      expect(text).toContain(suffix);
    }
    // The three Najee rungs are three DIFFERENT strings on the page, which is
    // the reader-level claim: ten rows reading `Malachi Fields:…` were one.
    expect(text).toContain("10+");
    expect(text).toContain("15+");
    expect(text).toContain("20+");
  });

  test("the value slot is this file's absent mark, not a blank", () => {
    const html = renderToStaticMarkup(<PropsSection items={UNGRADED_LADDER} state="graded" />);
    // Five rows, five em dashes: the slot says "we have no verdict", the same
    // way THE SCRIPT's markless rows say "we have no number" (D102 / #4530).
    expect(visibleText(html).split("—").length - 1).toBe(UNGRADED_LADDER.length);
  });

  // ── controls ──────────────────────────────────────────────────────────────

  test("CONTROL: on a MIXED list the header claims grades, so the row keeps the phrase", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED} state="graded" />);
    const text = visibleText(html);
    expect(text).toContain("The pregame script, graded.");
    expect(text).not.toContain("No grades published");
    // The ungraded row is now the only place this reader can learn it.
    expect(text).toContain(SETTLED_NO_GRADE_LABEL);
    // …and the graded row still shows its verdict.
    expect(text).toContain(propResultLabel("hit"));
  });

  test("CONTROL: a settled row inside a LIVE section keeps the phrase", () => {
    // The Open 2026 p0 path: `item.settled` renders WHAT HIT for one row while
    // the section is THE DIVERGENCE. That blurb says nothing about grading, so
    // the row owes the sentence.
    const live: PropMark[] = [
      {
        key: 1,
        label: "Najee Harris: 10+",
        pregame_mark: 0.5,
        current: 0.52,
        graded_result: null,
        settled: true,
      },
    ];
    const html = renderToStaticMarkup(<PropsSection items={live} state="divergence" />);
    expect(visibleText(html)).toContain(SETTLED_NO_GRADE_LABEL);
  });

  /**
   * The SECOND call site. `isBinaryBarMark` routes a binary mark with a live
   * number to `BinaryBarRow`, which owns its own copy of the graded slot — the
   * shape that let #5191 and #5240 each need two edits. Without this, a fix
   * threaded into `PropRow` alone passes every test above while half the
   * section's rows keep the chip.
   */
  test("the binary-bar row obeys the same rule, both directions", () => {
    const binary: PropMark[] = [
      {
        key: 1,
        label: "Najee Harris: 10+",
        kind: "binary",
        pregame_mark: 0.5,
        current: 0.52,
        graded_result: null,
      },
    ];
    const quiet = visibleText(renderToStaticMarkup(<PropsSection items={binary} state="graded" />));
    expect(quiet).toContain("No grades published");
    expect(quiet).not.toContain(SETTLED_NO_GRADE_LABEL);

    const mixedBinary: PropMark[] = [
      { ...binary[0], key: 2, graded_result: "hit", current: 1 },
      binary[0],
    ];
    const loud = visibleText(
      renderToStaticMarkup(<PropsSection items={mixedBinary} state="graded" />),
    );
    expect(loud).toContain(SETTLED_NO_GRADE_LABEL);
    expect(loud).toContain(propResultLabel("hit"));
  });

  test("CONTROL: a fully graded list is untouched", () => {
    const graded: PropMark[] = [
      { key: 1, label: "Najee Harris: 10+", pregame_mark: 0.5, current: 1, graded_result: "hit" },
      { key: 2, label: "Najee Harris: 15+", pregame_mark: 0.4, current: 0, graded_result: "miss" },
    ];
    const text = visibleText(renderToStaticMarkup(<PropsSection items={graded} state="graded" />));
    expect(text).toContain("The pregame script, graded.");
    expect(text).toContain(propResultLabel("hit"));
    expect(text).toContain(propResultLabel("miss"));
    expect(text).not.toContain(SETTLED_NO_GRADE_LABEL);
  });

  test("CONTROL: THE SCRIPT and THE DIVERGENCE are not touched by this rule", () => {
    const script = visibleText(
      renderToStaticMarkup(<PropsSection items={UNGRADED_LADDER} state="script" />),
    );
    // #8147 moved this literal from "expected" to "expects" (the blurb renders
    // only on events that have not started, so the past tense was never true).
    // This control's claim — #6129's ungraded-blurb rule does not leak out of
    // WHAT HIT — is unchanged; only the sentence it names moved.
    expect(script).toContain("What the market expects before the event.");
    expect(script).not.toContain("No grades published");

    const divergence = visibleText(
      renderToStaticMarkup(<PropsSection items={UNGRADED_LADDER} state="divergence" />),
    );
    expect(divergence).toContain("How far the live number has moved");
    expect(divergence).not.toContain("No grades published");
  });
});
