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
 * So printing "grading unavailable" over these rows would state something false
 * to the reader: the result is known, this view just does not act on it. A
 * refusal that is itself a false claim is worse than the bug it replaces.
 *
 * ── TWO CLAIMS THAT WERE TRUE WHEN WRITTEN AND ARE NOT NOW (live/072) ────────
 *
 * This note used to say the endpoint "emits `{market_name, outcome_name,
 * probability, source}` for `other` rows and drops the rest", and to point at
 * **#1494** for the serialization work. Both are stale, and a stale claim in a
 * file this deliberate is worse than no claim:
 *
 *   - The endpoint has NOT dropped the rest for some time. `_settled_grade_fields`
 *     is spread onto every `other` row, so `is_winner` and `resolution_source`
 *     are on the wire today — verified against `/api/events/15301243/game-markets`
 *     on 2026-09-05, where four of 27 `other` rows carry `is_winner`.
 *   - #1494 is the SEARCH-LATENCY issue. The live issue for this surface is
 *     **#3135**.
 *
 * ── AND WHY THE FIELD BEING PRESENT STILL DID NOT MAKE THIS RENDERABLE ───────
 *
 * live/071 threaded `is_winner` through to the renderer and measured it against
 * five real settled events before pushing: **0 rendered rows graded** on all
 * five. live/072 then measured the join the obvious way round — pair a rendered
 * row with the resolved twin of the same question — and gated it out too. The
 * reason is upstream of both and is recorded on #3135: the rows a reader sees
 * under a Polymarket container are the CONTAINER's children, which carry the
 * question as their label and a price for a side nobody named, because
 * `poll_polymarket_markets` overwrites the venue's own outcome labels
 * (`["Wu", "Alcaraz"]`) with a hardcoded `"Yes"` / `"No"`. A verdict word on
 * such a row would read `Set 2 Winner — HIT`, which names no winner.
 *
 * So the bar for the next attempt is not "get the grade to the renderer" — it
 * is already reachable. It is "be able to say WHO".
 *
 * So this surface states NO VERDICT. `SETTLED_VOCABULARY` governs "the verdict
 * slot"; nothing is put in that slot here, and neither of the phrases below
 * belongs in it. They label a NUMBER, which is the one thing this payload can
 * honestly support. Letting the row say "Burruchaga — won" is the real fix, it
 * is backend, and it is filed rather than guessed at (#3135).
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
 * The section-level sentence for a settled section that still shows a number,
 * said ONCE per section.
 *
 * `PropDivergenceDetail` sets the precedent for a uniformly ungraded set: name
 * the state once for the group. `PropTravelBar` labels every row instead, and
 * correctly so — its rows differ, so the label discriminates. Repeating this on
 * every row would discriminate nothing.
 *
 * ── #3752: IT USED TO SAY "showing each market's last quote" ─────────────────
 *
 * That wording made a promise about EVERY row, and by the time it was written
 * the rows had stopped agreeing with each other. `buildMarketSection` now
 * renders a decided row as its RESULT — `Shelton won Set 1`, deliberately with
 * no bar and no number — and an impossible one struck through, so a settled
 * tennis page holds three row shapes at once and only one of them is a quote.
 *
 * Measured on production 2026-09-07, `/events/15305016` (Shelton d. Tsitsipas,
 * `completed`): the header read "6 markets grouped by category · settled —
 * showing each market's last quote" over **six rows carrying zero quotes**.
 * "each" was false for 6 of 6.
 *
 * The replacement is quantified the other way round, so it stays true whether
 * one row is quoted or all of them are, and never promises a number a reader
 * cannot find. When NO row quotes, the clause is dropped for
 * `SETTLED_SECTION_NOTE_NO_QUOTES` — see `settledSectionNote`.
 */
export const SETTLED_QUOTE_SECTION_NOTE = "settled — any percentage is a last quote";

/**
 * The section-level sentence when the section is settled and NOTHING under it
 * shows a percentage — every row states a result or is struck as impossible.
 *
 * It names the state and stops. The alternative considered and rejected was
 * saying nothing at all: the rows do carry the settlement in their own words,
 * but the header is where the other two states announce themselves, and a
 * heading that goes quiet in one state only is how a reader learns to stop
 * reading it.
 */
export const SETTLED_SECTION_NOTE_NO_QUOTES = "settled";

/**
 * Pick the section sentence from what the section will actually render.
 *
 * `quotedOutcomes` is counted by `buildMarketSection` off the very array the
 * renderer maps over, which is the point: the note is chosen from the rows, not
 * from an intention about them. A predicate derived some other way would drift
 * the first time a new row shape learns to suppress its number, which is
 * exactly how #3752 happened.
 */
export function settledSectionNote(quotedOutcomes: number): string {
  return quotedOutcomes > 0 ? SETTLED_QUOTE_SECTION_NOTE : SETTLED_SECTION_NOTE_NO_QUOTES;
}

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
