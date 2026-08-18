/**
 * CAL-P067 item 4 (Fable ruling) — the selection-bias rule, presentation half.
 *
 * **Any published cell whose graded share is under 50% renders NOT-PROVABLE,
 * with the graded share shown.**
 *
 * The reasoning, kept here because the rule looks like a sample-size caveat and
 * has the opposite remedy. A calibration cell answers "when we said 30%, how
 * often did it happen?", which requires a graded result — so the rows in the
 * curve are exactly the graded rows, and the selection criterion IS the property
 * being measured. More data does not fix that; wider error bars do not fix that.
 * The ungraded remainder is not random either: CAL-P066's census found it
 * concentrated in whole market shapes no grader had claimed.
 *
 * So the presentation strikes the confident formatting and shows the share,
 * rather than widening an interval around a number that does not describe the
 * category. The number itself is never altered or hidden — a biased estimate is
 * still the estimate, and quietly swapping it would be its own dishonesty.
 *
 * The third state matters as much as the first two: `unknown` means the graded
 * share was never measured, and it is NOT a pass. It renders as its own thing,
 * never as `provable` — the same discipline as this queue's ruling-075 fix,
 * where a check that could not run must never share a rendering with a check
 * that passed.
 */

export type Provability =
  | "provable"
  | "not_provable_selection_biased"
  | "unknown";

/** The ruling's threshold. A half, and not a tunable. */
export const MIN_GRADED_SHARE = 0.5;

export interface ProvabilityCell {
  provability?: Provability;
  graded_share?: number | null;
  provability_reason?: string;
}

export interface ProvabilityPresentation {
  /** Strike the pp figures and drop the confident colour ramp. */
  strike: boolean;
  /** Show the orange "Not provable" chip. */
  showNotProvableBadge: boolean;
  /** Show the neutral "Graded share unmeasured" chip. */
  showUnknownBadge: boolean;
  /** e.g. `"25.0%"`, or null when there is no measured share. */
  sharePct: string | null;
  /** Chip text, share included when there is one — the ruling requires it SHOWN. */
  badgeLabel: string | null;
  /** Long-form explanation for the chip's tooltip. */
  title: string | undefined;
}

/**
 * What the category row should look like, from the cell's annotation alone.
 *
 * A cell with no `provability` field at all is the pre-rule payload: rendered
 * exactly as before, because the backend states an absent census ONCE in
 * `provability_census` rather than badging every row. An unannotated cell is
 * therefore "the rule has nothing to say here", which is different from
 * "unknown" (the rule ran, the denominator was missing) and different again
 * from "provable".
 */
export function provabilityPresentation(
  cell: ProvabilityCell | null | undefined,
): ProvabilityPresentation {
  const verdict = cell?.provability;
  const share =
    typeof cell?.graded_share === "number" && Number.isFinite(cell.graded_share)
      ? cell.graded_share
      : null;
  const sharePct = share === null ? null : `${(share * 100).toFixed(1)}%`;

  if (verdict === "not_provable_selection_biased") {
    return {
      strike: true,
      showNotProvableBadge: true,
      showUnknownBadge: false,
      sharePct,
      badgeLabel: sharePct ? `Not provable · ${sharePct} graded` : "Not provable",
      title: cell?.provability_reason,
    };
  }
  if (verdict === "unknown") {
    return {
      strike: false,
      showNotProvableBadge: false,
      showUnknownBadge: true,
      sharePct,
      badgeLabel: "Graded share unmeasured",
      title: cell?.provability_reason,
    };
  }
  return {
    strike: false,
    showNotProvableBadge: false,
    showUnknownBadge: false,
    sharePct,
    badgeLabel: null,
    title: cell?.provability_reason,
  };
}

/** True when at least one published cell is not provable — gates the page note. */
export function anyNotProvable(cells: readonly ProvabilityCell[]): boolean {
  return cells.some((c) => c.provability === "not_provable_selection_biased");
}
