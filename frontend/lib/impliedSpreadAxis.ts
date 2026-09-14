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

export interface ImpliedSpreadArm {
  spread: number;
  home_margin?: number;
}

/**
 * The value the implied-spread line is drawn at, on the chart's `home - away`
 * axis. Positive = home leading.
 */
export function impliedSpreadHomeMargin(arm: ImpliedSpreadArm): number {
  return arm.home_margin ?? -arm.spread;
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
}): boolean {
  // Already drawn as the projected-margin series; a second line would double it.
  if (opts.source === "sportsbook") return false;
  return !opts.isFinal;
}

/**
 * The sources whose implied-spread snapshot this chart draws, in payload
 * order. One list, read by the data build, the legend and the lines, so the
 * three cannot disagree about what is on the screen.
 */
export function drawnImpliedSpreadSources(
  impliedSpreads: Record<string, unknown> | null | undefined,
  isFinal: boolean
): string[] {
  return Object.keys(impliedSpreads ?? {}).filter((source) =>
    impliedSpreadSnapshotDrawn({ source, isFinal })
  );
}
