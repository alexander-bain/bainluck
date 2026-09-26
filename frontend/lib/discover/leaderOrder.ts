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

/** One number as a venue prints it on a rung: `3.50`, `24,200`, `2027`. */
const RUNG_NUMBER = /\d[\d,]*(?:\.\d+)?/g;

/**
 * #8834 — is this list a threshold ladder ALREADY IN threshold order?
 *
 * `/search` serves a ladder's `top_outcomes` as the rungs around its crossing in
 * threshold order (latency, PR #8839). The card may keep that order only when it
 * can see it is one, because every other rule on this page says "never trust
 * upstream order" — #2789's grouped feed shipped an unordered five and the card
 * stamped ranks on it.
 *
 * So the test is strict, stricter than `isNumericLadder` (which only decides
 * avatar vs rank and needs just two rungs to agree): EVERY name reads the same
 * once its numbers are masked (`Above #%`), and the first number runs strictly
 * up or strictly down the list as served. `Set 1 O/U 8.5 · Set 1 Winner · Set 2
 * Winner` — the #2789 specimen — has two shapes and fails; a ladder served out
 * of order fails; a probability-sorted ladder with a near-tie swap fails. A
 * date ladder (`Before July 2027`, `Before 2027`) has two shapes and keeps the
 * probability sort it had — a known remainder, not a regression.
 */
export function inThresholdOrder(names: readonly string[]): boolean {
  if (names.length < 2) return false;
  const shape = (name: string) => name.replace(RUNG_NUMBER, "#").trim().toLowerCase();
  const first = shape(names[0]);
  const values: number[] = [];
  for (const name of names) {
    const match = name.match(RUNG_NUMBER);
    if (!match || shape(name) !== first) return false;
    values.push(Number(match[0].replace(/,/g, "")));
  }
  const up = values.every((v, i) => i === 0 || v > values[i - 1]);
  const down = values.every((v, i) => i === 0 || v < values[i - 1]);
  return up || down;
}

/**
 * #8834 — a threshold ladder's rows, in the order the payload gave them. Call
 * only where `inThresholdOrder` has said that order means something.
 *
 * `/search?q=fed rate` serves a ladder's `top_outcomes` as the five rungs around
 * its crossing IN THRESHOLD ORDER (latency, PR #8839). Re-sorting that by
 * probability swaps near-tied rungs: production priced 109947's `Above 3.75%`
 * at 0.995 over `Above 3.50%` at 0.99, so the card read `3.75% · 3.50% · 4.00%`.
 * On a ladder the position IS the meaning.
 *
 * WHICH rows survive is still decided by `leaderFirstSlice`, so the #1526
 * invariant holds unchanged — the maximum-probability row is always kept. Only
 * their ORDER is taken from the input. Every other payload that reaches a card
 * (`_format_market_summary`, the grouped feed) already serves probability order,
 * so on those this returns exactly what `leaderFirstSlice` returns.
 */
export function ladderSlice<T extends Probable>(rows: readonly T[], count: number): T[] {
  const kept = new Set(leaderFirstSlice(rows, count));
  return rows.filter((row) => kept.has(row));
}

/**
 * #8834 — the rung that answers a ladder's question: the priced row nearest even.
 *
 * On `Fed funds rate after Oct 2026 meeting?` the rungs read `Above 3.50% 99% ·
 * Above 3.75% >99% · Above 4.00% 63% · Above 4.25% 2% · Above 4.50% 2%`. The
 * first rung (what a one-line row used to print) is always-true and says
 * nothing; `Above 4.00% 63%` is where the rate is expected to land.
 *
 * SAFE ON AN EXCLUSIVE FIELD TOO, by arithmetic rather than by gate: when the
 * rows sum to at most 1 and the top row is `m > 0.5`, every other row is at most
 * `1 - m`, so its distance from even is at least `m - 0.5` — never nearer than
 * the top row. When `m <= 0.5` every row sits at or below it, so the top row is
 * nearest. Ties go to the higher probability, then to the earlier row, so the
 * leader wins every tie that arithmetic allows.
 */
export function answerRung<T extends Probable>(rows: readonly T[]): T | null {
  let best: T | null = null;
  for (const row of rows) {
    const p = row.probability;
    if (typeof p !== "number" || !Number.isFinite(p)) continue;
    if (best === null) {
      best = row;
      continue;
    }
    const bp = best.probability as number;
    const d = Math.abs(p - 0.5);
    const bd = Math.abs(bp - 0.5);
    if (d < bd || (d === bd && p > bp)) best = row;
  }
  return best;
}
