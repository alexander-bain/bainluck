/**
 * ── THE SETTLED-QUOTE WORDS, AND WHY THEY ARE NOT VERDICT WORDS ──────────────
 *
 * UX-P115 (#2086). A game-market row on an event that has finished carries a
 * number that is no longer a probability: it is the last price the market was
 * quoted at before it stopped updating. This module owns the two phrases that
 * say so, for every runtime that has to say it.
 *
 * ── WHY NOT `SETTLED_NO_GRADE_LABEL` ─────────────────────────────────────────
 *
 * This is the load-bearing decision, and it is the one a reader will want to
 * re-litigate, so the measurement is here rather than in a report.
 *
 * `propGrade.SETTLED_NO_GRADE_LABEL` ("Resolved · grading unavailable") is the
 * site's owned phrase for a settled row with no statable verdict, and reusing
 * an owned phrase is nearly always right (#1650: one backend state must not
 * wear three vocabularies). It is wrong HERE, and #2086's own scope note is
 * what misled: the issue reasons that the event's `home_score`/`away_score` are
 * null, so no winner can be derived, so a refusal is the honest render.
 *
 * The event's score is not the only source of a grade, and for these rows it is
 * not the relevant one. Measured against production 2026-08-21, on the issue's
 * own specimen (event 15177664, a tennis match that finished a month earlier),
 * every underlying market is independently settled:
 *
 *     resolved  …: Exact Match Score   Burruchaga wins 2-1  is_winner=True   api_settlement
 *     resolved  …: Set 1 Winner        Burruchaga           is_winner=True   api_settlement
 *     resolved  …: Set 2 Winner        Wawrinka             is_winner=True   api_settlement
 *     resolved  Wawrinka vs Burruchaga Burruchaga           is_winner=True   api_settlement
 *
 * The grading is AUTHORITATIVE and it is merely UNSERIALIZED — the game-markets
 * endpoint emits `{market_name, outcome_name, probability, source}` for `other`
 * rows and drops the rest. So printing "grading unavailable" over these rows
 * would state something false to the reader: the result is known, this view
 * just does not carry it. A refusal that is itself a false claim is worse than
 * the bug it replaces.
 *
 * So this surface states NO VERDICT. `SETTLED_VOCABULARY` governs "the verdict
 * slot"; nothing is put in that slot here, and neither of the phrases below
 * belongs in it. They label a NUMBER, which is the one thing this payload can
 * honestly support. Serializing the grade so the row can say "Burruchaga —
 * won" is the real fix and lives in `routes/events.py`, which this lane does
 * not own (#1494); it is filed rather than guessed at.
 *
 * ── THE TRAP THE NEXT CONSUMER WILL HIT ──────────────────────────────────────
 *
 * When that grade IS serialized, key on the MARKET's status, never on
 * `is_winner` alone. Measured over settled events on the same day: markets with
 * `status='resolved'` carry 5,869 outcomes with a real assignment (1,383 true /
 * 4,486 false / 0 null), while markets still marked `status='open'` carry 1,761
 * outcomes that are ALL `is_winner = false` — gotcha #33, Kalshi settled
 * markets stay `open` in the DB because polling stops seeing them. That blanket
 * false is the ungraded default, not a grade, and a naive read renders 1,761
 * outcomes as having lost.
 */

/**
 * Prefix for a frozen price on a finished game: "last quote 99%".
 *
 * Lower case and set alongside the number rather than in a badge, because it is
 * a description of the figure, not a verdict about the outcome. The wording is
 * #2086's own — "a 99% on a settled market is not a probability, it is a frozen
 * last quote".
 */
export const SETTLED_QUOTE_PREFIX = "last quote";

/**
 * The section-level sentence, said ONCE per section.
 *
 * `PropDivergenceDetail` sets the precedent for a uniformly ungraded set: name
 * the state once for the group. `PropTravelBar` labels every row instead, and
 * correctly so — its rows differ, so the label discriminates. Every row here is
 * in the same state, so per-row repetition discriminates nothing.
 */
export const SETTLED_QUOTE_SECTION_NOTE = "settled — showing each market's last quote";

/**
 * ── THE LIFECYCLE PREDICATE, AND WHY IT LIVES HERE RATHER THAN IN THE RAIL ───
 *
 * This list sat in `lib/propDivergence.ts` from the day THE DIVERGENCE rail was
 * written, which was reasonable — the rail was the only thing asking. UX-P115
 * moved it, and the move was forced by a guard rather than chosen:
 * `propDivergence` imports `propGrade`, so `SpecialEventMarkets` reaching for
 * nothing more than "is this game over?" was pulled into the settled-vocabulary
 * CLOSURE, and `settledVocabulary.test.tsx` enrolled it in a verdict census it
 * can never satisfy. Both of that suite's enrolment guards fired at once — one
 * demanding enrolment, the other demanding an enrolled surface actually state a
 * verdict.
 *
 * The guards were right, and the lesson generalises past this cycle:
 * **knowing a game is over is not knowing who won.** Keeping the lifecycle
 * predicate behind the verdict authority conflates the two and quietly destroys
 * the property the census depends on — that everything in the closure is a
 * surface which CAN state a verdict. `propDivergence` re-exports the name, so
 * no existing caller changed.
 */
const SETTLED_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "closed",
  "settled",
  "final",
  "resolved",
]);

export function isSettledStatus(status?: string | null): boolean {
  return SETTLED_STATUSES.has((status || "").toLowerCase());
}
