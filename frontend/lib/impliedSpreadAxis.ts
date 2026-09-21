/**
 * #3948 repair `3948-KALSHI-IMPLIED-LINE-MATCHES-HOME-MARGIN-AXIS`.
 *
 * There are TWO opposite sign conventions in `pm_spread_data`, one negation
 * apart, which is exactly why they were confused:
 *
 * - `spread` is **betting-line sign** — negative means the HOME team is
 *   favoured. This is what the backend's `projected_final_score` consumes, and
 *   it is correct there.
 * - The score-differential chart's Y axis is **`home - away`** — positive means
 *   the HOME team is LEADING. Every other series on that chart is built as
 *   `projected_home_score - awayScore`.
 *
 * Plotting `spread` on that axis mirrors the line about zero. On the real
 * Giants-home ladder with Dallas favoured by 3, `spread` is `+3.0`, which the
 * chart drew as the GIANTS leading by 3 — against a hero on the same page
 * favouring Dallas.
 *
 * The backend now states the axis explicitly as `home_margin`. This reads it,
 * and falls back to negating `spread` so a payload cached before the repair
 * deployed still draws on the right half.
 */

export interface ImpliedSpreadLadderRung {
  threshold: number;
  probability: number;
}

export interface ImpliedSpreadArm {
  spread: number;
  home_margin?: number;
  confidence?: number;
  contracts?: ImpliedSpreadLadderRung[];
}

/**
 * The value the implied-spread line is drawn at, on the chart's `home - away`
 * axis. Positive = home leading.
 */
export function impliedSpreadHomeMargin(arm: ImpliedSpreadArm): number {
  return arm.home_margin ?? -arm.spread;
}

/**
 * #7660. A SNAPSHOT THE PRODUCER DOES NOT BELIEVE IS NOT A FORECAST A READER
 * CAN WEIGH — AND `confidence` HAS BEEN SERVED FOR THIS AND NEVER CONSULTED.
 *
 * ── WHAT THE READER SAW ────────────────────────────────────────────────────
 *
 * `/events/14780544`, Chiefs 24 - Colts 20, **live, 5:12 left in the 3rd**
 * (390px, 2026-09-20 7:27 PM PDT, `artifacts/ux-1402/final/…-1927PT-y700.png`).
 * The Score Differential chart drew `Kalshi Implied` flat at **a tie**, while
 * `Polymarket Implied` sat at Chiefs +7, the orange actual line at Chiefs +4,
 * and the hero one card up read **Chiefs 78%**. Kalshi was the only thing on
 * the page calling the game even.
 *
 * It was not what Kalshi said. That arm's half-point rungs are clean and
 * monotone and cross 0.50 at **7.5** — agreeing with Polymarket (+6.7), the
 * sportsbooks (+7.1) and the hero. Served `home_margin` was **+0.3**, because
 * three INTEGER thresholds are interleaved into the ladder, each appearing
 * twice with contradictory probabilities (`1.0 -> 0.37` and `1.0 -> 0.11`,
 * `7.0 -> 0.02` and `7.0 -> 0.48`, …), and one of them lands beside the
 * crossing. Fixing THAT is the derivation half of #7660 and is not ux's; the
 * wire is committed verbatim as `impliedSpread.14780544.live.json`.
 *
 * ── WHY THE GATE IS `confidence` AND NOT THE CONTRADICTION ITSELF ──────────
 *
 * Refusing "a ladder with duplicated rungs" was built first and MEASURED
 * WRONG: those integer duplicates are in every NFL kalshi ladder on the wire,
 * including #6142's scheduled control, so that rule deleted the line on every
 * page rather than the broken ones. Refusing "duplicates that straddle 0.50"
 * failed too — the live ladder moved across that boundary between two reads
 * six minutes apart, so the rule caught a moment, not a defect. A renderer
 * cannot re-derive its way to trust in a number the producer derived.
 *
 * What the producer DOES state is `confidence`, and #6142 recorded that the
 * chart ignores it: `0.2` draws exactly like `1.0`. It declined a floor on one
 * measurement — every kalshi arm served `0.2`, so a floor "would delete the
 * feature on every game". **That measurement has inverted.** On the same wire,
 * 2026-09-21 02:29Z:
 *
 *     14780544 live       polymarket 0.97 (+6.7)   kalshi 0.2 (+0.3)
 *     14780545 scheduled  polymarket 0.95 (+6.9)   kalshi 0.2 (-0.4)
 *
 * So a floor no longer deletes the feature: on BOTH non-final NFL pages it
 * keeps a line, and the line it keeps is the one that agrees with the score,
 * the hero and the sportsbooks. It withdraws the one the producer marked as a
 * guess and that is measurably 7.5 points from its own ladder.
 *
 * `MIN_CONFIDENCE` is 0.5 — "more likely than not to be a real estimate". The
 * served values are bimodal with nothing in between (0.2 / 0.3 against
 * 0.95 / 0.97 / 1.0), so every value in (0.3, 0.95] picks the same two groups;
 * the constant is reading a gap, not tuning a knob.
 *
 * ── WHAT THIS COSTS, SAID PLAINLY ──────────────────────────────────────────
 *
 * #6142 installed "an unplayed game still draws it, from both venues" as a
 * load-bearing control against exactly this ship deleting the feature, and
 * that control's fixture (polymarket 0.3, kalshi 0.2) now draws neither arm.
 * That is a real reduction in coverage on games where only distrusted arms
 * exist, taken deliberately: a low-confidence implied spread drawn in the same
 * idiom as two real series is a contradiction on the reader's screen, not
 * information. The control is replaced rather than dropped — the live wire
 * proves the gate DISCRIMINATES (polymarket drawn, kalshi withheld, one
 * payload) instead of merely deleting, which is what that control protected.
 *
 * An arm with no `confidence` at all is drawn: absence is not a low score, and
 * refusing an unmarked arm would silently widen this the day the field moves.
 */
export const MIN_CONFIDENCE = 0.5;

/** Whether the producer marked this arm as an estimate it stands behind. */
export function impliedSpreadArmIsTrusted(arm: ImpliedSpreadArm): boolean {
  return arm.confidence === undefined || arm.confidence >= MIN_CONFIDENCE;
}

/**
 * #6142 render half — WHETHER a source's implied-spread snapshot is drawn at
 * all. The function above answers *where* the line sits; this one answers
 * whether there is a line.
 *
 * ── WHAT THE READER SAW ────────────────────────────────────────────────────
 *
 * `/events/14780142`, Carolina 37 – Chicago **59**, Final, four hours after
 * the whistle (390px, 2026-09-14 11:20Z, `artifacts/ux-1257/slice-00.png`).
 * The Score Differential chart drew a flat purple dashed line labelled
 * `Kalshi Implied` edge to edge at **Carolina +15**, while the orange Actual
 * Score Diff line under it finished at **Chicago +22** and the scoreboard at
 * the top of the same page said 59–37. Nothing on the page reconciles them.
 *
 * ── THIS IS THE SECOND HALF OF A RULE THE SERVER ALREADY APPLIED ───────────
 *
 * `routes/events.py` (#5078) withholds `projected_final` on a finished game
 * under "settled means settled", and says in the same comment that it is
 * deliberately leaving the chart's own rungs alone:
 *
 *     `implied_spreads`/`implied_totals` are deliberately left alone — they
 *     are the chart's own rungs, and this is the narrow claim: no PROJECTION
 *     of a game that has already been played.
 *
 * So the rungs were left FOR the renderer, and this is the renderer paying
 * it. The predicate is deliberately the same one the producer uses —
 * `status in ("completed", "closed")` — so the two halves cannot come to
 * disagree about what "final" means.
 *
 * ── WHY A FINAL GAME IS THE WHOLE OF THE GATE ──────────────────────────────
 *
 * The series is a snapshot of what the venue's ladder implies *right now*,
 * painted across every timestamp ("This is a snapshot, not a time series" —
 * `ScoreDifferentialChart`'s own comment). Before the whistle that is a
 * forecast a reader can weigh. After it, the result is a fact served on the
 * same payload and drawn on the same axis two pixels below, so the snapshot
 * can only ever agree redundantly or contradict a fact — and a 2px dashed
 * line reads as a series, not as a single current value.
 *
 * It is NOT gated on `confidence`, though the chart never consults that
 * either: every kalshi arm measured on 2026-09-14 served `confidence: 0.2`
 * (five settled NFL pages, three arms), so a confidence floor would not
 * narrow this case, it would delete the feature on every game. Whether a
 * 0.2 ladder should be served at all is the producer's half of #6142 and is
 * not answered here.
 *
 * 🔴 SUPERSEDED 2026-09-20 BY #7660, which now gates on exactly that. The
 * measurement above was true when taken and is no longer: polymarket arms on
 * the same wire serve 0.95-0.97, so a floor keeps a line on every non-final
 * NFL page instead of deleting the feature. The paragraph is kept because the
 * reasoning was sound on its evidence — see `impliedSpreadArmIsTrusted` above
 * for what changed and what it cost.
 *
 * ── WHAT THIS DOES NOT DO ──────────────────────────────────────────────────
 *
 * It does not delete the alarm. The +15 is the visible symptom of a
 * derivation defect on a settled ladder, and that defect stays filed and
 * measured in #6142 with the payload quoted; the guard fixtures carry the
 * production wire verbatim. Withholding it from the chart withdraws a
 * contradiction from a reader's screen, not the evidence from the record.
 *
 * `sportsbook` is excluded on its own long-standing grounds and for every
 * game state: that arm is already drawn as the projected-margin line, so
 * drawing it here would double it. Folding both exclusions into one rule is
 * the point — the chart asks this function once instead of restating "not
 * sportsbook" at each of its three draw sites.
 */
export function impliedSpreadSnapshotDrawn(opts: {
  source: string;
  isFinal: boolean;
  arm: ImpliedSpreadArm;
}): boolean {
  // Already drawn as the projected-margin series; a second line would double it.
  if (opts.source === "sportsbook") return false;
  if (opts.isFinal) return false;
  // #7660: drawing a snapshot the producer scored 0.2 in the same idiom as two
  // real series states a confidence the payload does not.
  return impliedSpreadArmIsTrusted(opts.arm);
}

/**
 * The sources whose implied-spread snapshot this chart draws, in payload
 * order. One list, read by the data build, the legend and the lines, so the
 * three cannot disagree about what is on the screen.
 */
export function drawnImpliedSpreadSources(
  impliedSpreads: Record<string, ImpliedSpreadArm> | null | undefined,
  isFinal: boolean
): string[] {
  return Object.entries(impliedSpreads ?? {})
    .filter(([source, arm]) =>
      // #7660: the arm is a REQUIRED input of the rule, not an optional extra.
      // A gate whose input can be forgotten at the call site fires never while
      // every test stays green — #2086's failure mode, and the reason the
      // signature makes the compiler ask for it.
      impliedSpreadSnapshotDrawn({ source, isFinal, arm })
    )
    .map(([source]) => source);
}
