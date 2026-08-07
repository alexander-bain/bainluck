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
