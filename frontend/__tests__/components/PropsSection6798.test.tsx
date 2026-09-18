/**
 * #6798 — ON A MIXED LIST THE CHIP CANNOT GO, SO THE QUESTION MUST NOT.
 *
 * #6129 fixed the all-ungraded page by dropping `SETTLED_NO_GRADE_LABEL` from every row,
 * because the section blurb already said it. It narrowed that deliberately: on a MIXED list
 * the header claims grades, so the chip is the only place a reader learns a given row was not
 * graded. That narrowing is correct and is untouched here. What it left open is that on a
 * mixed list the chip is still 198px of `shrink-0`, and the label beside it is the only thing
 * in the row that can yield.
 *
 * ── MEASURED, IN A REAL BROWSER, NOT EYEBALLED AND NOT IN jsdom ──────────────────────────
 *
 * `tools/props-row-fit-6798.mjs` against `https://www.bainluck.com/events/14638444`
 * (Buffalo Bills 41 — Detroit Lions 31, completed 03:30Z) at 390px, live bundle
 * `06d4ceb59efaba6906328216c88ae8cafafb2770`, 2026-09-18 05:4xZ:
 *
 *   rows 379 · graded 324 · withheld 55
 *   chip width          198px   (`shrink-0`)
 *   label width, chip   108px
 *   label width, no chip 268px
 *   clipped rows          8     — ALL of them withheld rows
 *   distinct full labels, withheld  13
 *   distinct VISIBLE labels, withheld 9
 *
 * and the clip lands on the digits that tell the rows apart:
 *
 *   'Jameson Williams: 3+'   108 / 141  ->  'Jameson Willia'
 *   'Jameson Williams: 4+'   108 / 141  ->  'Jameson Willia'
 *   'Jameson Williams: 9+'   108 / 141  ->  'Jameson Willia'
 *   'Amon-Ra St. Brown: 11+' 108 / 156  ->  'Amon-Ra St. Bro'
 *   'Amon-Ra St. Brown: 14+' 108 / 158  ->  'Amon-Ra St. Bro'
 *   'Amon-Ra St. Brown: 15+' 108 / 158  ->  'Amon-Ra St. Bro'
 *   'Jahmyr Gibbs: 10+'      108 / 120  ->  'Jahmyr Gibbs: 1'
 *   'Joshua Palmer: 5+'      108 / 120  ->  'Joshua Palmer:'
 *
 * 🔴 NOTE WHAT THE NUMBERS DO **NOT** SAY, because the issue's headline overstates it and a
 * later reader will otherwise re-derive the wrong claim. 55 rows reaching the reader as 9
 * strings is mostly LEGITIMATE: #5191 strips a family's name from labels whose header already
 * says it, so a family's two rows are honestly called `Over` and `Under` and collapse with the
 * chip gone too. The full labels were already only 13. Truncation destroys 4 of those 13
 * distinctions, across 3 ladders. That is the defect — smaller than filed, real, and landing
 * exactly on the part a reader came for.
 *
 * ── THE A/B, ON THE LIVE PAGE, SAME LOAD, ONE VARIABLE ───────────────────────────────────
 *
 * `APPLY_FIX=1` injects what `line-clamp-2` compiles to over the same rows and re-measures.
 * Bundle `0b81ce11f874dc1884e10c5cdd47fd78fd6240c7` (master had rolled between the two runs
 * above and this one; both arms below are the same load of the same bundle):
 *
 *                              BEFORE   AFTER
 *   clipped rows                  8       0
 *   distinct visible, withheld    9      13
 *   distinct FULL,   withheld    13      13
 *   labels past the 2-line clamp  0       0      (max lines used: 1 -> 2)
 *
 * `distinct visible == distinct full` is the claim in one line: after the change no label is
 * lost to truncation at all, and the 13-not-55 residue is #5191's family rule, not this bug.
 * `0` labels reach the clamp's bound, which is what licenses the comment in the component
 * saying nothing measured reaches it.
 *
 * ── THE FIX IS THE HOUSE IDIOM, AND THE PRECEDENT NAMES THE TRAP ─────────────────────────
 *
 * `GamePlayCard.tsx` (#6496, citing #4342 on the golf list) already ruled this exact shape —
 * "a `min-w-0` text column squeezed by `shrink-0` siblings" — and states the answer and its
 * trap: *`line-clamp-2`, NEVER `truncate`: the two cannot be combined, because `truncate` sets
 * `white-space: nowrap` and silently defeats the clamp.* So the label clamps to two lines and
 * keeps its tail; the chip is untouched; #1650's one-phrase-per-backend-state rule is not
 * re-opened by inventing a shorter second phrase.
 *
 * ── WHY EVERY ASSERTION IS PAIRED (gotcha #43) ───────────────────────────────────────────
 *
 * Deleting the chip would also stop the clipping, and would be a regression of #6129's
 * narrowing. Removing the clamp's bound would also stop it, and would let one pathological
 * label grow the list. So each test below is matched by a control that fails if the fix went
 * too far in that direction.
 *
 * jsdom has no layout, so the 108px cannot be re-derived here and is not: the pixel numbers
 * above are the production measurement, quoted. What this file proves is the MARKUP mechanism
 * — which span yields, and that the class that would defeat the fix is absent.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import PropsSection from "../../components/event/PropsSection";
import type { PropMark } from "../../components/event/PropsSection";
import { propResultLabel, SETTLED_NO_GRADE_LABEL } from "../../lib/propGrade";

/**
 * The production ladder, verbatim from `/api/events/14638444/game-markets` — the three rows
 * that clipped to one string, plus the graded sibling that makes the list MIXED and therefore
 * keeps the chip alive. A fix that only works on short labels cannot pass this.
 */
const MIXED_LADDER: PropMark[] = [
  { key: 1, label: "Jameson Williams: 3+", pregame_mark: 0.5, current: 0.52, graded_result: null },
  { key: 2, label: "Jameson Williams: 4+", pregame_mark: 0.4, current: 0.44, graded_result: null },
  { key: 3, label: "Jameson Williams: 9+", pregame_mark: 0.3, current: 0.31, graded_result: null },
  { key: 4, label: "Amon-Ra St. Brown: 11+", pregame_mark: 0.2, current: 1, graded_result: "hit" },
];

/** #6129's page: nothing graded at all, so the blurb speaks and the chip must stay gone. */
const ALL_UNGRADED: PropMark[] = MIXED_LADDER.map((m) => ({ ...m, graded_result: null }));

/** The same mixed list as binary-bar rows (`kind: "binary"` with a live `current`). */
const MIXED_BINARY: PropMark[] = MIXED_LADDER.map((m) => ({ ...m, kind: "binary" }));

/** Every label span the section emits for a row, with its class list. */
function labelSpans(html: string): string[] {
  return [...html.matchAll(/<span class="([^"]*\bflex-1\b[^"]*)"/g)].map((m) => m[1]);
}

describe("#6798 · a withheld row on a mixed list keeps the digits that name it", () => {
  test("the label clamps instead of truncating, so its tail survives the 198px chip", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED_LADDER} state="graded" />);
    const spans = labelSpans(html);

    expect(spans.length).toBeGreaterThan(0);
    for (const cls of spans) {
      expect(cls).toContain("line-clamp-2");
      // THE PRECEDENT'S TRAP, asserted rather than trusted: `truncate` is
      // `white-space: nowrap`, which silently defeats the clamp and ships the bug back
      // while the `line-clamp-2` above still reads as present.
      expect(cls).not.toContain("truncate");
      // The clamp only reaches the text if the column can actually shrink.
      expect(cls).toContain("min-w-0");
    }
  });

  test("the binary-bar row is the same defect by construction and gets the same answer", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED_BINARY} state="graded" />);
    const spans = labelSpans(html);

    expect(spans.length).toBeGreaterThan(0);
    for (const cls of spans) {
      expect(cls).toContain("line-clamp-2");
      expect(cls).not.toContain("truncate");
    }
  });

  test("CONTROL — the chip survives on a mixed list: #6129's narrowing is not widened", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED_LADDER} state="graded" />);
    // The header claims grades, so the three ungraded rows must each still say so. If a fix
    // "solved" the clipping by dropping the chip, this is the assertion that catches it.
    expect(html).toContain(SETTLED_NO_GRADE_LABEL);
    expect(html.split(SETTLED_NO_GRADE_LABEL).length - 1).toBe(3);
  });

  test("CONTROL — #6129 still holds: an all-ungraded list says it once, in the blurb", () => {
    const html = renderToStaticMarkup(<PropsSection items={ALL_UNGRADED} state="graded" />);
    expect(html).toContain("No grades published for these props.");
    expect(html).not.toContain(SETTLED_NO_GRADE_LABEL);
  });

  test("CONTROL — the growth is bounded: the clamp is two lines, not unbounded wrapping", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED_LADDER} state="graded" />);
    for (const cls of labelSpans(html)) {
      // `line-clamp-2`, not `line-clamp-none` and not a bare `whitespace-normal` — a
      // pathological label must not be able to grow the list without bound.
      expect(cls).toMatch(/\bline-clamp-2\b/);
      expect(cls).not.toMatch(/\bline-clamp-(none|[3-9])\b/);
    }
  });

  test("CONTROL — each rung is still a distinct question on the page", () => {
    const html = renderToStaticMarkup(<PropsSection items={MIXED_LADDER} state="graded" />);
    // The suffixes are what the 108px clip was eating. All three reach the markup.
    for (const suffix of ["3+", "4+", "9+"]) expect(html).toContain(suffix);
    // And the graded sibling keeps its verdict, so the fix did not quiet the other half.
    // Imported, never retyped: UX-P106 exists because three settled words were typed as
    // literals in the wrong case, which is exactly the slip this line first made.
    expect(html).toContain(propResultLabel("hit"));
  });
});
