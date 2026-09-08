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
