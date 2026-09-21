/**
 * #7670 — WHAT A PROBABILITY CELL PRINTS, GUARDED AT BOTH ENDS.
 *
 * ── WHAT THE READER SAW ────────────────────────────────────────────────────
 *
 * The MLB playoff grid printed **`100%`** for Boston, whose served probability
 * is **`0.9972`** — two rows under clubs rendering **✓** for having actually
 * clinched. `100%` on a club that can still miss says the season is decided
 * when it is not, and it says it in the same glyph we use for the clubs where
 * it IS decided. Filed by authority/928, measured 2026-09-21 03:29Z against
 * `GET /api/playoffs/mlb` read in the same minute.
 *
 * ── THE SHAPE OF THE BUG: ONE GUARDED END OUT OF TWO ───────────────────────
 *
 * `TournamentProgressionTable.formatProb` already refused to print `0%` for a
 * small-but-possible outcome, degrading to `<0.1%` — because `0%` claims
 * impossibility. It then rounded the top of the range with `Math.round`, which
 * claims certainty for the mirror-image reason. One end was defended and the
 * other was not, in the same six-line function.
 *
 * `lib/playoffGrid.formatGridCell` had NEITHER guard — a bare
 * `Math.round(p * 100)` — so it printed `100%` at 0.9972 AND `0%` at the
 * `0.0005` that seventeen clubs' championship cells were serving the same
 * minute.
 *
 * ── WHY ONE HELPER ─────────────────────────────────────────────────────────
 *
 * Both renderers print the same vocabulary (`NN%`) for the same quantity on
 * pages a reader moves between, and they had drifted to two different answers
 * about what the edges mean. They now ask one function.
 *
 * ── ABOUT `ChampionshipGrid`, TWICE CORRECTED ──────────────────────────────
 *
 * The first draft of this comment said `ChampionshipGrid` was deliberately not
 * routed here because it "already guards both ends". Two things were wrong
 * with that, and the second one undoes the first:
 *
 *   1. It guards both ends in ONE of its two cells. The 10px summary cell
 *      guards its top at the CALL SITE (`prob >= 0.995 ? "99+" : fmt(prob)`)
 *      and prints a bare number with no `%`. The per-source breakdown table
 *      eleven lines away printed `${fmt(p)}%` with no such guard — a bare
 *      `Math.round` above its `<1` floor, i.e. `100%` at 0.9972. So the file
 *      contained the very defect the comment used it as a clean example of.
 *
 *   2. NO READER HAS EVER SEEN EITHER CELL. `components/ChampionshipGrid.tsx`
 *      has a single `export default` and ZERO importers — the whole frontend
 *      mentions only the similarly-named `ChampionshipGridResponse` TYPES,
 *      which are a different thing and are consumed by the pages that render
 *      `TournamentProgressionTable` instead. The playoffs payload confirms it
 *      from the other side: production serves `teams[].cells`, while this
 *      component wants `teams[].stages[].sources[]`, a shape the API does not
 *      return. The component is dead code.
 *
 * Its breakdown cell is routed here anyway — consistency inside a file that
 * may one day be revived costs nothing, and the guard test now pins BOTH cells
 * so a revival cannot quietly restore the bad one. But it is not a reader-
 * visible fix and must not be counted as one.
 *
 * The lesson survives the retraction, and is the reason the rule lives inside
 * this function rather than at each call site: one small file managed to guard
 * this correctly once and incorrectly once, and a comment asserting the file
 * was fine outlived the truth of it.
 *
 * ── THE RULE ───────────────────────────────────────────────────────────────
 *
 * An absolute is printed only when the payload states an absolute. Anything
 * that is merely CLOSE to an absolute is printed as a bound, never rounded
 * into one:
 *
 *     1      -> "100%"     certain, because the payload says certain
 *     0.9972 -> "99.7%"    close, so it keeps the decimal that says so
 *     0.99995-> ">99.9%"   too close to render, so it says "too close"
 *     0.0005 -> "<0.1%"    the floor's long-standing mirror of that
 *     0      -> "0%"       impossible, because the payload says impossible
 *
 * The `> 99` band mirrors the `< 1` band that has always existed below it:
 * where a tenth of a point is the whole of the information, a tenth of a point
 * is what gets printed.
 *
 * ── WHAT THIS DELIBERATELY DOES NOT DECIDE ─────────────────────────────────
 *
 * Whether a served `0` ever means "we have no number" rather than "this cannot
 * happen". If it does, `0%` is the wrong print and so was `formatGridCell`'s
 * before this — but the grid carries separate named states for a hole
 * (`no_market` and its siblings, see `formatGridCell`'s own docstring), so a
 * numeric `0` reaching here should be a real zero. Changing that reading is a
 * payload question, not a formatting one, and it is not answered here.
 */

/** Closer to an absolute than one decimal can render. */
const UNRENDERABLY_CLOSE = 0.1;
/** Under this, `formatProb` has always kept a decimal. Unchanged. */
const DECIMALS_BELOW = 10;
/**
 * Over this, it now keeps one for the mirror reason. Deliberately NOT the
 * mirror of `DECIMALS_BELOW`: at 95% the tenths carry nothing, but at 99.7%
 * they are the entire difference between "nearly there" and the `100%` that
 * started #7670. The band is the width of the rounding hazard, not a symmetry.
 */
const DECIMALS_ABOVE = 99;

/**
 * The text a probability cell shows, for a probability that is known to be a
 * finite number in [0, 1]. Callers handle null/absent themselves, because what
 * a MISSING number prints is a per-surface decision (a dash, a word, nothing)
 * and is not this function's business.
 */
export function probabilityCellText(p: number): string {
  const pct = p * 100;

  // The absolutes, printed only when the payload states them.
  if (pct <= 0) return "0%";
  if (pct >= 100) return "100%";

  // Nearer an absolute than a decimal can express: say that, do not round to it.
  if (pct < UNRENDERABLY_CLOSE) return "<0.1%";
  if (pct > 100 - UNRENDERABLY_CLOSE) return ">99.9%";

  // The two bands where the decimal carries the meaning.
  if (pct < DECIMALS_BELOW) return `${pct.toFixed(1)}%`;
  if (pct > DECIMALS_ABOVE) return `${pct.toFixed(1)}%`;

  return `${Math.round(pct)}%`;
}

/**
 * #7692 — THE SAME RULE FOR THE 9px PER-SOURCE CHIPS UNDER A GRID CELL.
 *
 * ── WHY A SECOND FUNCTION AND NOT A SECOND CALL SITE ───────────────────────
 *
 * The playoff grid's `SourceBreakdown` chips print the same quantity in a
 * different vocabulary: 9px mono, no `%` (the table's legend supplies the
 * unit), and a floor written `<.1` with the leading zero elided because the
 * cell is two characters wide. So they cannot call `probabilityCellText` —
 * its output carries a `%` — and stripping the suffix would drag `<0.1` into
 * a spelling that was chosen for a wider cell.
 *
 * What they CAN share is the rule: WHERE the bands are, and that an absolute
 * is never rounded into. That is the part that drifted. `SourceBreakdown`
 * guarded its low end (`<.1`) and rounded its high one, so at 99.5 it printed
 * `K100` — directly under a cell that #7670 had just taught to print `99.5%`.
 * One guarded end out of two, eleven lines from the function #7670 fixed.
 * Measured on production 2026-09-21 05:26Z: `/api/playoffs/mlb`, Chicago Cubs
 * `make_playoffs`, merged `0.9948`, sources `polymarket 0.9945 / kalshi 0.995`
 * — the page read `99.5%` over `P99 K100`.
 *
 * Both functions live in this file so the bands are one edit, not two.
 *
 * ── WHERE THE TWO SPELLINGS DIFFER, AND WHY ────────────────────────────────
 *
 *     value     cell       chip     why the chip differs
 *     1         "100%"     "100"    same rule: the payload states the absolute
 *     0.9995    ">99.9%"   ">99.9"  same rule, no unit
 *     0.9948    "99.5%"    "99.5"   same rule, no unit
 *     0.65      "65%"      "65"     same rule, no unit
 *     0.007     "0.7%"     "0.7"    same rule, no unit
 *     0.0005    "<0.1%"    "<.1"    the chip's own elided floor, pre-existing
 *     0         "0%"       "<.1"    the chip has never printed a bare `0`
 *
 * The last row is deliberately left alone. A chip printing `0` would make the
 * impossibility claim that #7670 removed from the cell, and `<.1` is the
 * conservative side of that; changing it is not this fix's business.
 */
export function probabilityChipText(p: number): string {
  const pct = p * 100;

  // The one absolute the chip prints, and only when the payload states it.
  if (pct >= 100) return "100";

  // Too close to render, at either end. The floor keeps its elided spelling.
  if (pct < UNRENDERABLY_CLOSE) return "<.1";
  if (pct > 100 - UNRENDERABLY_CLOSE) return ">99.9";

  // The two bands where the decimal carries the meaning — the same bands.
  if (pct < DECIMALS_BELOW) return pct.toFixed(1);
  if (pct > DECIMALS_ABOVE) return pct.toFixed(1);

  return `${Math.round(pct)}`;
}
