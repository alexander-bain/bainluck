import { sportVocab } from "@/lib/marketMapUtils";

/**
 * WHAT A MATCH SURFACE MAY PRINT WHEN THE WINNER MARKET HAS THREE OUTCOMES.
 *
 * #6238 — the WEB twin of native's #5271 (`ios/.../Utilities/DrawPricedWinner.swift`,
 * shipped 2026-09-11). The guard existed in one client and the other client was
 * unguarded: before this file, the only path outside `ios/` that named the flag
 * was `__tests__/ios/aDrawIsNotTheAwayTeam5271.test.ts`, a jest test that scans
 * the *Swift source*. So nothing went red while the web printed the complement.
 *
 * ═══ THE DEFECT ═══
 *
 * Every probability this site draws for a match comes from one pair, and the
 * pair is `home` and `1 − home`. `routes/feed.py` derives
 * `current_odds.away_probability` as `round(1.0 - current_home_prob, 6)`, and
 * `renderedDuelPercents` is built on the two summing to one. On a two-outcome
 * sport that is exactly right.
 *
 * `1 − P(home)` is **"the home team does not win"**. In soccer that is *away win
 * **or** draw*, so the figure printed under the away crest silently absorbs the
 * entire draw probability.
 *
 * Photographed on production 2026-09-14 by authority/322 under D48 —
 * `/events/15301234`, León v Atlético San Luis, Liga MX, 2h pre-match, 390px:
 *
 * | where | León | draw | San Luis |
 * |---|---|---|---|
 * | hero, top of page | **68%** | — | **32%** |
 * | the same page's correct-score card | — | 0-0 at 22%, 1-1 at 10% | — |
 *
 * The page refutes itself one card down. The books behind it were nowhere near a
 * two-way split: draftkings −115/+285 implies 53.5%/26.0%, **summing to 79.5%**;
 * fanduel 80.9%; lowvig 77.3%. We divide by that sum to strip vig — correct for a
 * two-way market, wrong here, because the missing ~20 points are mostly the draw
 * and not vig. León was overstated by ~14pp, San Luis by ~6pp.
 *
 * Worse once settled: `/events/15305024` (Daejeon Citizen v Pohang Steelers)
 * finished **2–2**, and its chart readout said `Citizen 63% — Steelers 37%` off
 * terminal odds of **+600 / +950** — both long shots, because in the dying
 * minutes of a level game the draw was the overwhelming favourite and then the
 * actual result.
 *
 * ═══ WHY THIS WITHHOLDS RATHER THAN CORRECTS ═══
 *
 * The obvious fix — print the away team's real price — has nowhere to read one
 * from. Measured for #5271 on 2026-09-11 and re-confirmed on this site's own
 * payloads on 2026-09-14:
 *
 *  * the event payload carries no draw and no independent away price: the away
 *    field IS the complement (`0.317 === 1 − 0.683` on the specimen, exactly);
 *  * `win_prob_snapshots.draw_probability` exists and is **NULL on all 3,084,750
 *    rows** — no writer has ever set it;
 *  * the three-way groups on `game-markets` are not fit to print (#5328).
 *
 * So this takes the move the codebase already makes wherever it cannot state a
 * number — `UNSCORED_IN_POINTS`'s empty unit, `NO_READING`, `formatProbabilityOrDash`:
 * **a number in the wrong unit is worse than an absent one, because it looks
 * sourced.** The away slot is withheld and prints the em-dash the hero already
 * draws for a side with no reading.
 *
 * ═══ WHAT THIS DOES NOT FIX, AND MUST NOT BE READ AS FIXING ═══
 *
 * The home price it KEEPS is the blend, and on soccer the blend is itself
 * draw-dropped whenever the books are in it (**#1011**) — that is why the
 * specimen's retained number is 68% and not the ~53% the raw moneylines imply.
 * This file fixes the RENDER defect only: a client inventing an away price out
 * of a complement. The two are independent, and #6238's acceptance test — the
 * hero and the three-way card agreeing on one screen — is only reachable once
 * #1011 lands too. Nobody should read this landing as that being delivered.
 */

/**
 * Whether this sport's match-winner market prices a draw as a third outcome.
 *
 * Declared per sport in `sportVocab`, **never inferred from a key here**. A
 * `sportKey.startsWith("soccer")` at a call site is the same defect one layer
 * down: it is a spelling test standing in for a semantic one, and it puts the
 * declaration wherever the last person happened to need it. `sportVocab` already
 * matches `soccer_mexico_ligamx` and `soccer_korea_kleague1` through its
 * `["soccer", "mls", "epl", "uefa", "fifa"]` row, which is why both production
 * specimens are covered without anyone listing a league.
 *
 * An undeclared sport answers `false` and keeps its two-sided reading, so
 * widening the rule is one `true` in the vocab and a test.
 */
export function sportPricesADraw(sportKey: string | null | undefined): boolean {
  return sportVocab(sportKey || undefined).winnerMarketPricesADraw;
}

/**
 * The away figure a two-slot surface may print — the served one, or `null` where
 * it may print none.
 *
 * ═══ WHY THIS TAKES THE AWAY VALUE AND RETURNS ONE, RATHER THAN MIRRORING
 *     NATIVE'S `printablePair` ═══
 *
 * Native's `printablePair` returns the whole pair and answers `nil` for the
 * *whole thing* when either side is missing on a two-way sport. Porting that
 * shape literally would change this site's two-way behaviour: the web hero today
 * prints `68% – —%` when the away price alone is absent, and `printablePair`'s
 * contract would withhold both numbers instead. That is a regression on every
 * sport this issue is not about.
 *
 * So the web takes the narrower question, which is the only one #6238 asks: *may
 * this surface print the away number?* Native does exactly this at the two call
 * sites where the difference bites — `DiscoverEventCard.swift:157` reads
 * `sportPricesADraw` directly for this reason, and `EventCardView.swift:597`
 * documents it as "the one place in the family where the difference bites". This
 * is that same choice, made once for the web rather than at each call site.
 *
 * The `away` parameter is passed through rather than re-derived so that callers
 * keep handing over the SERVED value; a surface that re-derives `1 − home`
 * locally is the trap `renderedDuelPercents` documents.
 */
export function printableAway<T>(away: T | null, sportKey: string | null | undefined): T | null {
  return sportPricesADraw(sportKey) ? null : away;
}
