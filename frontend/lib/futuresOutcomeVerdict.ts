import type { SettlementDisplay } from "@/lib/types";
import { isAuthoritativeResolution } from "@/lib/resolutionAuthority";

/**
 * The verdict this row is allowed to state: `"won"`, `"lost"`, or `null` for
 * "say nothing".
 *
 * ## #4788 / #4783 / #1638 — a default is not a verdict
 *
 * `futures_outcomes.is_winner` is `boolean NULL DEFAULT false`. An INSERT that
 * merely OMITS the column stores an affirmative graded **LOSS** on a leg nobody
 * called (CAL-P1004R), and three of the four Polymarket outcome INSERTs do
 * exactly that — 27,197 legs since 2026-09-07, of which 10,337 sit on 3,308
 * RESOLVED markets and therefore print. So `is_winner === false` answers two
 * different questions with one bit: "a grader called this a loser" and "nobody
 * has been here".
 *
 * `resolution_source` is the field that separates them: **a row with no source
 * was not graded, whatever `is_winner` says.**
 *
 * But a non-empty source is NOT automatically a grade, and reading it as one is
 * its own defect (CERT-2222 on the sibling surface, CERT-2517 here). Exactly one
 * value — `ungradeable_result` — is a RETRACTION: our own statement that the leg
 * is unknowable. It is refused first and unconditionally; see
 * `RETRACTED_RESOLUTION_SOURCE` below.
 *
 * Measured on the specimen this landed against, `/futures/59700266` (NFL
 * Receptions, finished 2026-09-09): 24 of 75 legs carry
 * `is_winner=false, resolution_source=NULL` and **0 carry a source at all** —
 * nobody graded that market. Two of the 24 are Jaxon Smith-Njigba 7+ and 8+,
 * which Kalshi settled `yes` (he caught 8); under a heading reading *Final
 * Results* we printed a red `Lost · 0% · Settled` on both while our own last
 * recorded price on each was **99%**. The other 51 legs carry an explicit
 * `is_winner: null` and were already rendering honestly, so the page
 * contradicted itself about rows of identical grading status.
 *
 * ### Why this returns a verdict rather than a boolean "is it graded"
 *
 * Four separate branches below key off the settled state — the row tint, the
 * `Won`/`Lost` pill, the `100%`/`0%` + `Settled` numbers cell, and
 * `outcomeRowPrintsMove`'s suppression of the movement column. Each one of them
 * previously restated `isResolved && outcome.is_winner === X` for itself, which
 * is the defect `outcomeRowPrintsMove` was extracted to end (see its note): a
 * branch changed on one side and missed on the other. One function answers it
 * once, so a row cannot be tinted as a loss while its cell declines to say so.
 *
 * ### The `true` arm is deliberately gated too, and is a no-op today
 *
 * A fabricated grade is always `false` — `false` is the column default, so a
 * `true` had to be written by something. Probed on production: resolved
 * outcomes with `is_winner IS TRUE AND resolution_source IS NULL` return
 * **0 rows**, so gating the win branch changes nothing that renders now. It is
 * gated anyway because the asymmetric version — guard the loss, trust the win —
 * is a rule that silently stops holding the first time a producer defaults the
 * other way, and nothing would catch it.
 *
 * ### #6082 — and the market's STATUS is not the leg's question
 *
 * The paragraphs above are about WHO graded a leg. The other half is WHERE a
 * grade is allowed to stand, and it is the same rule the backend already owns:
 * `can_write_winner` (#845) admits a winner on a settled market OR on any market
 * when an AUTHORITATIVE (tier-3) venue settlement says so. An `open` market can
 * therefore hold a genuinely settled leg, which is the ordinary state of a
 * threshold ladder mid-season. Only the WON arm crosses that line — see the
 * comment on the branch itself for why the LOST arm cannot until #4597's drain
 * lands. Tier-3 membership is `lib/resolutionAuthority.ts`.
 *
 * Note this is a WEAKER guarantee than the props rail's `readPropGrade`, which
 * refuses to believe `is_winner` even WITH a source ("only `hit` types a
 * verdict", UX-P044/#1642, after 70 measured false red MISSes built from a
 * generic source plus a defaulted `false`). That rail has an independently
 * derived `hit` to stand on; the futures wire carries no such second field, so
 * `resolution_source` is the strongest discriminator available here. Grading
 * accuracy GIVEN a source is the producers' half of #4783/#4788 and is not
 * something the renderer can adjudicate (ruling 003).
 */
/**
 * The one `resolution_source` that is a RETRACTION rather than a grade.
 *
 * CAL-P056 (#1852). `ungradeable_result` is the state of a leg whose stored loss
 * the venue never declared (a Kalshi `result` of `"scalar"` or `""`). It asserts
 * NO winner — it exists to take a fabricated loss OUT of the published curve
 * instead of re-grading it — and `resolution_authority.py` files it as TERMINAL
 * (tier 1), structurally no-winner and calibration-truth ineligible.
 *
 * Mirror of `RETRACTION_SOURCE` in `app/utils/kalshi_fabricated_loss.py`, and
 * pinned to it by `test_futures_serves_resolution_source_4788.py` so the two
 * cannot drift.
 */
export const RETRACTED_RESOLUTION_SOURCE = "ungradeable_result";

/**
 * The two fields this rule actually reads.
 *
 * #6138 WIDENED THE PARAMETER RATHER THAN COPYING THE FUNCTION. The event
 * page's `Additional Markets` rows carry the same two fields under different
 * names and needed the same answer; `FuturesOutcome` satisfies this shape, so
 * every existing call site is unchanged and `tsc` proves it. The alternative
 * was a second private copy of a rule whose own comment block says twice that
 * it must not be copied — and #6082 exists because the last copy diverged.
 */
export interface GradedRow {
  is_winner?: boolean | null;
  resolution_source?: string | null;
  /** #698 — the settled-result contract (`lib/settledResultDisplay`). Optional:
   * detail and search rows carry it; legacy callers keep their fallback. */
  settlement_display?: SettlementDisplay | null;
}

export function outcomeRowVerdict(
  outcome: GradedRow,
  isResolved: boolean,
): "won" | "lost" | null {
  // THE RETRACTION IS REFUSED FIRST, AND UNCONDITIONALLY — before `isResolved`,
  // before the null test, before `is_winner`.
  //
  // CERT-2222 blocked this exact reading on the sibling surface, and CERT-2517
  // blocked it here: "a non-empty `resolution_source` is not a grade". A row we
  // have explicitly declared unknowable is the LAST row entitled to a verdict,
  // and treating the retraction as a grade turns it into the confident red `Lost`
  // this whole ship exists to remove — the worse lie, because it looks like a
  // result. `_outcome_is_settled` in `routes/league_futures.py` states the rule
  // at length; this is the same rule, not a second private copy of it.
  //
  // Unconditional in BOTH directions: a row that is both retracted and crowned is
  // a contradiction, and the honest render for a contradiction is the live one.
  if (outcome.resolution_source === RETRACTED_RESOLUTION_SOURCE) return null;
  // #698 — THE SETTLED-RESULT CONTRACT, WHEN THE ROW CARRIES ONE, IS THE ANSWER.
  //
  // `/futures/62134744` served both legs `0.5 / false / clob_authoritative` and
  // the last line of this function made each a `lost` — printed `Lost · 0%` —
  // because nothing below reads the price. The server now states, from the
  // STORED row, whether a result exists; `unknown` returns no verdict and never
  // falls through to `is_winner`, or a `false` would restore the two losses.
  // The contract is only ever attached on a RESOLVED market, so an open board
  // (#6082's settled leg) never reaches this branch and keeps its rule below.
  const contract = outcome.settlement_display;
  if (contract && isResolved) {
    return contract.verdict === "unknown" ? null : contract.verdict;
  }
  // A SERVED null means the payload looked and found no grader ⇒ say nothing.
  //
  // `=== null`, never `== null`, and this is the load-bearing line of the whole
  // change. ABSENT is not the same answer as NULL: Vercel deploys ahead of
  // Heroku, so this component runs against the OLD payload — which has no
  // `resolution_source` key at all — for the length of every deploy. Folding
  // `undefined` in with `null` would withhold on EVERY resolved market during
  // that window, blanking genuine `Won` marks across the site to fix a defect
  // that only ever prints a false `Lost`. Absent means "this payload cannot
  // say", and the honest response to that is today's behaviour, not a blackout.
  if (outcome.resolution_source === null) return null;
  if (outcome.is_winner == null) return null;
  // #6082 — THE MARKET'S STATUS IS NOT THE LEG'S QUESTION.
  //
  // `isResolved` is `market.status === "resolved"`, a MARKET-level fact, and it
  // used to sit above this line refusing every verdict on a market that had not
  // settled. A threshold ladder is exactly where that comes apart: Kalshi settled
  // `80+ wins` and `75+ wins` YES on `/futures/261` while the market stayed
  // legitimately `open` (the parent question runs to Nov 8 and `90+ wins` traded
  // at 19%), so two called rungs printed `LATEST 99%` and `LATEST 98%` — and
  // because both numbers were pre-settlement relics rather than prices, the page
  // put `≥ 75 98%` directly above `≥ 80 99%`. 2,428 legs on 797 open markets
  // carry this stamp (measured 2026-09-14), 1,738 priced under 99.5%.
  //
  // `can_write_winner` (#845) is the codebase's rule and it admits exactly this:
  // a winner stands on a settled market, OR on any market when an AUTHORITATIVE
  // (tier-3) venue settlement says so. `_outcome_is_settled` renders on that rule
  // on the sibling surface and names this case. The comment above this function
  // already claimed to be "the same rule, not a second private copy of it"; it
  // was a second copy, and this is where it had diverged.
  //
  // ONLY THE WON ARM CROSSES THE STATUS LINE, and the asymmetry is deliberate
  // rather than timid. A tier-3 `is_winner = true` cannot be CAL-P1004 residue by
  // construction: that rail's population is `win_count = 0` markets, its
  // retraction writes `ungradeable_result` (never `api_settlement`), and its only
  // TRUE write is `restore_winner`, licensed by the venue's own answer for that
  // exact ticker. A tier-3 `is_winner = false` on an OPEN market has no such
  // proof — `is_winner` is `boolean NULL DEFAULT false`, so on a market nobody
  // has finished grading a defaulted FALSE is indistinguishable from a called
  // loss, and crowning it `Lost` is #4788's lie on a market that is still
  // trading. That arm is #4597's, it waits on the CAL-P1004 drain, and until then
  // an ungraded-looking leg keeps its price — which is also why `85+ wins` on
  // this very market must keep reading 96%.
  //
  // A settled market is untouched: below this branch both arms answer as before.
  if (!isResolved) {
    return outcome.is_winner === true &&
      isAuthoritativeResolution(outcome.resolution_source)
      ? "won"
      : null;
  }
  return outcome.is_winner ? "won" : "lost";
}

