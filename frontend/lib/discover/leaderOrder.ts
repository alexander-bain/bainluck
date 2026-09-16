/**
 * UX-P007 / #1526 — a Discover card must never drop its leader.
 *
 * The renderer truncates outcome lists to fit a card (`slice(0, 4)`, `slice(0,
 * 3)`). Truncation is fine; truncating an array that is not leader-first is
 * not. The Fed September card rendered four also-rans summing to 47% because
 * the 56% "No change" row sat at an index the slice never reached — the
 * backend, the API response and the payload were all correct, and the card
 * destroyed the answer on the way to the screen.
 *
 * Sorting is done HERE, at the truncation site, rather than trusted from the
 * payload. The backend does sort (UX-P005 made the display rank the
 * probability rank), but a renderer that silently depends on upstream order
 * has no way to fail loudly when that order changes — it just quietly shows
 * the wrong answer, which is exactly how this shipped.
 *
 * Ordering is stable: equal probabilities keep their incoming relative order,
 * so a backend tie-break (alphabetical, rank column, ladder position) survives.
 * Null/undefined probabilities sort last — an unpriced row is never the leader.
 */

/** Anything the card renders as an outcome row. */
type Probable = { probability?: number | null };

/**
 * Can a card print a percentage for this row? (#6505)
 *
 * The other half of the sentence this module's header already ends on — "an
 * unpriced row is never the leader". It is never a ROW either, and the two
 * clauses live in one file so they cannot drift apart.
 *
 * This is verbatim the test the leaderboard's value cell has always made
 * (`probability > 0 ? pct : "—"`), lifted out of the leaf. Measured on
 * production `/api/feed?limit=200`, 2026-09-16 07:2xZ: five cards drew a board
 * whose rows print `—` where the percentage goes, because the row LIST was
 * built from everything the payload carried while only the value CELL asked
 * whether there was a number — so every unanswerable row was still laid out,
 * ranked, given a bar and counted against the card's minimum-row bar. "Velo
 * Point of Sale Growth in September" drew eight rungs and one number.
 *
 * ZERO IS UNPRINTABLE ON PURPOSE, not an oversight inherited from the truthiness
 * test it replaces. The backend already serves `probability: null` for a
 * `0.000000` outcome on the `top_outcomes` carrier (`_outcome_prints_a_price`
 * reads a Kalshi row at `0.00 bid / 1.00 ask` as an empty book, not a settled
 * zero) while `distribution_outcomes` passes the same row through as `0.0`. One
 * predicate over both carriers is what stops them disagreeing on screen. A
 * genuine settled zero is a RESULT and belongs to the settled rendering, which a
 * Discover board card is not.
 */
export function printsAPercent(
  probability: number | null | undefined
): probability is number {
  return typeof probability === "number" && Number.isFinite(probability) && probability > 0;
}

/**
 * Leader-first copy of `rows`, highest probability first. Stable; never mutates
 * the input. Always call this before slicing an outcome list for display.
 */
export function leaderFirst<T extends Probable>(rows: readonly T[]): T[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const pa = a.row.probability ?? -1;
      const pb = b.row.probability ?? -1;
      if (pb !== pa) return pb - pa;
      return a.index - b.index; // stable: preserve the backend's tie-break
    })
    .map(({ row }) => row);
}

/**
 * Leader-first, then truncated to `count`. The return value is guaranteed to
 * contain the maximum-probability row whenever `rows` is non-empty and
 * `count >= 1` — the invariant #1526 exists to enforce.
 */
export function leaderFirstSlice<T extends Probable>(rows: readonly T[], count: number): T[] {
  return leaderFirst(rows).slice(0, count);
}
