"use client";

import type { FuturesOutcome } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import EntityImage from "@/components/EntityImage";
import { isNonSportsCategory, isInternationalSport, flagUrl } from "@/lib/images";
import { SHAPE_QUANTITY, type MarketShape } from "@/lib/marketShape";
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

/**
 * Does this row's "Last move" cell print a MOVE, or the muted dash?
 *
 * #3358: the row and the table have to agree on this, and the only way to be sure
 * they do is for both to call the same function. The row uses it to pick its cell;
 * the page uses it over the whole outcome set to decide whether the column is worth
 * any width at all. A second copy of the predicate is the defect that
 * `_futures_feed_load_options` in `routes/feed.py` was written to end — a column
 * added or a branch changed on one side and missed on the other.
 */
export function outcomeRowPrintsMove(
  outcome: FuturesOutcome,
  isResolved: boolean,
): boolean {
  // A settled row prints its result, never a movement. #4788: "settled" is a
  // row that STATES a verdict, not merely one on a resolved market — an ungraded
  // row has no result to print instead, so it keeps its movement like any other.
  if (outcomeRowVerdict(outcome, isResolved) !== null) return false;
  // #6488 — AND A SETTLED MARKET NEVER ADVERTISES A LIVE MOVE, GRADED OR NOT.
  //
  // The line above is #4788's and is about the VERDICT cell: an ungraded leg must
  // not print a confident `Lost`, and must not be blanked either. It left the
  // ungraded arm printing a movement badge, so `/futures/61120482` rendered
  // `Draw … LAST MOVE +0.5 pts` underneath a banner reading "This market has been
  // settled" and a heading reading "Final Results" — the page telling a reader
  // it is over and that the price is still moving, in one glance. Alex flagged
  // exactly that juxtaposition from his phone (2026-09-15 intake).
  //
  // THIS IS THE PAGE'S OWN RULE, NOT A NEW ONE. The detail page already answers
  // "may a resolved market show movement?" three times and answers no every time:
  // it declines to pass `movement` to the hero at all (`page.tsx:675`,
  // `!isResolved && …`), `FuturesHero` suppresses the pill a second time on its
  // own `resolved` prop — whose doc states the rule outright, "so a settled market
  // never reads like an ongoing 58%" — and the movement explanation is gated the
  // same way (`page.tsx:898`). The table was the one widget that missed it.
  //
  // #4788's stated cost does not arise here. Its objection was that a row with no
  // result "has nothing to trade [the cell] for", i.e. a hole; but `showLastMove`
  // (#3358, `page.tsx:511`) asks this same predicate across the WHOLE table, so a
  // settled market now drops the column outright and hands its fixed 80px back to
  // the name — which at 390px is the difference between a name and `Pe…`.
  //
  // Narrow by construction, in both directions: a GRADED row already returned
  // false one line up, and #6082's genuinely-settled leg on an OPEN market has
  // `isResolved === false` and keeps its movement exactly as before.
  if (isResolved) return false;
  const change = outcome.probability_change_24h;
  // UX-P275: the gate asks whether a move PRINTS, not whether the wire fraction is
  // nonzero — anything that rounds to zero is no move.
  return change !== null && change !== undefined && isRenderedMove(change);
}

/**
 * Does this table's rows draw an entity picture beside the outcome name?
 *
 * #4483. `EntityImage type="wikipedia"` falls back to the name's INITIALS when it
 * has no picture, which is right for a person or a party and nonsense for a
 * threshold: `Above 50`, `Above 51`, `Above 52` and `Above 53` all initialise to
 * an identical grey **`A5`**, so four different answers wore one label on
 * `/futures/31835562` ("How many Senators will vote to confirm Todd Blanche").
 * `futuresLadder.ts` already names the same defect on the ladder path — "avatar
 * circles reading 'BA', 'BJ', 'BO', 'B2'" for a date market.
 *
 * A `quantity` market's outcomes are thresholds, dates or bins. They are not
 * entities, they have no picture, and there is nothing for initials to abbreviate.
 * `market_type` is the field that already knows this (#194), so the answer is read
 * from the shape rather than re-derived from the outcome text — re-deriving shape
 * from names is the very defect `futuresLadder`'s queue closed.
 *
 * Deliberately NOT extended to the other shapes. `duel`, `field`, `participation`
 * and `container_member` all have genuine entity outcomes (candidates, teams,
 * nominees) and their pictures are the point. `claim` would qualify on principle —
 * "Yes"/"No" are not entities either — but a census of the eight non-sports
 * categories returns **no `claim` rows at all**, so that arm would be unreachable
 * and unprovable; `unshaped` keeps today's behaviour because unknown is not the
 * same as "known to be a threshold".
 *
 * Shape is resolved by the CALLER, once, over the whole outcome set — the same
 * division as `showLastMove` below, and for the same reason: `resolveShape()` owns
 * the `market_type`-then-fallback preference order (`lib/types.ts`: "callers must
 * not re-derive shape themselves") and its fallback needs every outcome name, which
 * a single row does not have.
 */
export function outcomeRowShowsEntityImage(
  marketCategory: string | null | undefined,
  shape: MarketShape | null,
): boolean {
  if (!isNonSportsCategory(marketCategory ?? null)) return false;
  return shape !== SHAPE_QUANTITY;
}

/**
 * Single outcome row of the "All Outcomes" table on `/futures/[id]`.
 *
 * ## #3358 — the one column that says WHO was the one column with no width
 *
 * Extracted from `app/futures/[id]/page.tsx` so the layout contract below can be
 * rendered and asserted; the markup is otherwise the page's, unchanged.
 *
 * At 390px this row had ~294px of content box and spent ~268px of it on things that
 * are not the name: the checkbox (20), the rank badge (32), `Open` (~34), a **fixed
 * `w-20`** `Last move` (80), `Latest` (~42) and five 12px gaps (60). The name is
 * `flex-1 min-w-0`, so it took what was left — ~26px, which prints `Pe…`, and ~10px
 * on the rows that also carry a rank-change arrow, which prints a single letter.
 * The avatar was 100% visible and the name 0% visible on a page whose entire job is
 * to say who is leading.
 *
 * Two independent changes, because the row has two different shapes to get right:
 *
 * 1. **An empty column buys no width.** `Last move` is a per-write delta (CAL-P159)
 *    and on whole markets it is `–` on every row — on `/futures/202` and on #3358's
 *    own `/futures/112996`, all of them. The caller passes `showLastMove`, computed
 *    over the whole outcome set with `outcomeRowPrintsMove`, and a column that would
 *    print nothing is not rendered. That returns ~92px to the name at every width.
 * 2. **When it is NOT empty, the row wraps instead of starving the name.** The three
 *    numeric columns move into one group that takes a full line of its own below
 *    `sm`, so the name is measured against the row rather than against what four
 *    columns left it. Nothing is dropped and no label is abbreviated — UX-P233 put a
 *    label on all three of those numbers deliberately, and this keeps all three.
 *
 * So the common case stays on one line with a readable name, the moving case grows a
 * second line, and neither case can starve the name again.
 *
 * ## #4592 — the common case could still starve the name, because `flex-1` is basis-0
 *
 * #3358's change 1 returns ~92px by dropping an empty column, and its arithmetic above
 * says that is enough. Measured at 390px on 2026-09-16, with `Last move` already
 * dropped, it is not — the name node is **92px** on `/futures/112854` and `/112860`
 * (date rungs) and on `/futures/25924714` (senators), so `December 31, 2026` (needs
 * 132px) prints `December 31, ...` on a board whose whole question is *which year*,
 * and `June 30, 2026` (94px) clips by 2px. Budget of one 318px row, measured:
 * checkbox 20 + rank 32 + name cell 124.3 + numbers 79.7 + three 12px gaps = the
 * 294px content box, exactly. Nothing is wasted; the name is simply last in line.
 *
 * The reason change 2 did not cover this is a flexbox detail rather than a width:
 * **`flex-1` is `flex: 1 1 0%`**, so the name cell's *hypothetical main size* — the
 * number multi-line flex uses to decide where a line breaks — is **0**, whatever the
 * name is. A cell that measures 0 can never push a sibling onto the next line, so the
 * numbers group stays on line 1 and the name absorbs the whole shortfall. That is why
 * the starvation survived a change explicitly written to stop it.
 *
 * `flex-auto` is `flex: 1 1 auto`: same grow, same shrink, but the hypothetical size
 * is the cell's CONTENT — avatar + gap + the full name, which is nowrap under
 * `truncate`. So the wrap decision is now made against the width the name actually
 * needs, and the three cases fall out of one class rather than out of a threshold:
 *
 *   - short name (`Mike Lee`, 57px): everything still fits, the row stays on ONE line
 *     and is not made taller — #3358's common case, preserved by construction;
 *   - long name (`December 31, 2026`, 132px): the sum exceeds the line, the numbers
 *     group wraps exactly as it does under `Last move`, and the name is re-measured
 *     against the row — 186px, so it fits;
 *   - name longer than a whole line (>186px): `min-w-0` and `flex-shrink: 1` are
 *     untouched, so the cell still shrinks and still ellipsises. This is the case a
 *     `min-w-[Npx]` floor gets wrong — a floor clamps the hypothetical size for EVERY
 *     row (wrapping the short ones too, taking the density change #3358 declined) and
 *     then refuses to shrink, overflowing the row instead of truncating.
 *
 * A row that does not wrap is therefore a row whose name fits: the test is the name's
 * own width, so there is no tuned constant here to drift.
 */
export default function OutcomeRow({
  outcome,
  rank,
  isLeader,
  isSelected,
  onToggleSelect,
  hasHistory,
  marketCategory,
  marketName,
  isResolved = false,
  rendered,
  renderedOpening,
  showLastMove,
  showEntityImage,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
  hasHistory: boolean;
  marketCategory?: string | null;
  marketName?: string;
  isResolved?: boolean;
  /** The card-level integers for this row's two price columns, or null for "no
   *  override" (#2831). Both REQUIRED, with no default: the pair decision needs the
   *  whole outcome set, so only the caller can make it, and a default would compile
   *  at the next call site while quietly printing 101 again. */
  rendered: number | null;
  renderedOpening: number | null;
  /** #3358: does ANY row in this table print a move? REQUIRED, no default, for the
   *  same reason as the pair above — it is a whole-table decision that only the
   *  caller can make, and a default would silently restore the 80px column on the
   *  next surface that renders this row. */
  showLastMove: boolean;
  /** #4483: does this table draw entity pictures at all? REQUIRED, no default, for
   *  the same reason as `showLastMove` — it is resolved from the market's SHAPE
   *  over the whole outcome set, so only the caller can decide it, and a default
   *  would silently restore the `A5` chip on the next surface that renders a
   *  threshold ladder through this row. Compute it with
   *  `outcomeRowShowsEntityImage`. */
  showEntityImage: boolean;
}) {
  const change = outcome.probability_change_24h;
  const rankChange = outcome.rank_change_24h;
  const printsMove = outcomeRowPrintsMove(outcome, isResolved);
  // #4788: the ONE settled-state decision for this row. Every branch below reads
  // it — never `isResolved && outcome.is_winner === X`, which counts a defaulted
  // `false` as a grader's verdict.
  const verdict = outcomeRowVerdict(outcome, isResolved);

  // #6325 — A SETTLED BOARD DOES NOT NUMBER ITSELF.
  //
  // `rank` is a PRICE rank: where an outcome sat in the field while the market was
  // being made. The page hands this row `outcome.rank ?? index + 1`, so a leg with
  // no price history takes its display position instead — and on
  // `/futures/58675941` ("Vuelta a Espana 2026: Winner") that printed TWO rows
  // badged `1`: the graded champion, minted by #6110 with `rank` NULL and hoisted
  // to the top by the settled sort, and Tadej Pogacar, who lost with a stored rank
  // of 1. Measured on production: **677 markets resolved in the last 45 days have a
  // NULL-ranked graded winner beside a sibling holding stored rank 1**, and 1,960
  // mix ranked and unranked legs at all.
  //
  // The collision is the symptom; the column is the defect. On a settled market the
  // rows are ordered winner-first and then by frozen price, so the badges beside
  // them read `1 1 27 28 17 10 …` — #4416's sentence exactly: a column that carries
  // no ordering while looking exactly like one.
  //
  // NOT THE FIX: renumbering the settled rows by display position. It makes the
  // column coherent by asserting something we do not know — that the second row
  // FINISHED second. Only the winner is graded here; everyone else merely lost, and
  // their order on the page is the order their prices froze in. A badge is not a
  // place to invent a result order, and there is nothing true left for it to say,
  // so it says nothing. The verdict chip already crowns the winner (#4788).
  //
  // The arrow goes with it, and not for tidiness: `rank_change_24h` survives
  // settlement on **180,626 rows across 20,904 settled markets** (45 days), so a
  // finished board prints "moved 3 places in the last 24 hours" about a market that
  // ended weeks ago. Leaving it would also orphan an arrow beside a badge this
  // change removes.
  //
  // Scoped to `isResolved`, the MARKET-level fact — so a settled leg on an open
  // market (#6082) keeps its badges, because that board is still being priced. The
  // card's own row (`FuturesCard.tsx:291`) is a different component whose badge is
  // positional for every row, so it cannot collide and is not this defect.
  const printsRank = !isResolved;

  // Entity image detection. #4483: the non-sports test alone was the bug — it
  // asks "could this name have a Wikipedia picture?" and a threshold answers yes.
  // The caller's shape-aware `showEntityImage` is the gate now.
  const isIntl = isInternationalSport(marketCategory ?? null);
  const outcomeFlag = isIntl ? flagUrl(outcome.name) : null;

  return (
    <div
      // UX-P230: the rendered order is the thing under guard — name it on the row
      // so a test reads what the page actually painted, not what a helper returned.
      data-testid="outcome-row"
      data-outcome-name={outcome.name}
      // #3358: `flex-wrap` below `sm` is what guarantees the name a floor. It only
      // has an effect when the numeric group asks for a full line (see below), so
      // the no-move table — the common one — still renders on a single line.
      className={`flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-2 sm:gap-y-0 p-3 rounded-lg transition-colors ${
        isSelected
          ? "bg-blue-50 border border-blue-200"
          : verdict === "won"
          ? "bg-emerald-50 border border-emerald-200"
          : verdict === "lost"
          ? "bg-slate-50/50"
          : isLeader
          ? "bg-amber-50 border border-amber-200"
          : "bg-slate/5 hover:bg-slate/10"
      }`}
    >
      {/* Selection checkbox (for chart) */}
      {hasHistory && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onToggleSelect();
          }}
          className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
            isSelected
              ? "bg-blue-500 border-blue-500 text-white"
              : "border-slate/30 hover:border-text-secondary"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </button>
      )}

      {/* Rank + rank change — the whole cell, silent on a settled board (#6325) */}
      {printsRank && (
        <>
          <span
            data-testid="outcome-rank-badge"
            className={`w-8 h-8 flex items-center justify-center text-sm rounded-full shrink-0 ${
              isLeader
                ? "bg-amber-100 text-amber-700 font-bold"
                : "bg-surface-card text-text-secondary border border-surface-border"
            }`}
          >
            {rank}
          </span>

          {rankChange !== null && rankChange !== 0 && (
            <span
              data-testid="outcome-rank-change"
              className={`text-xs shrink-0 ${
                rankChange < 0 ? "text-emerald-600" : "text-red-500"
              }`}
            >
              {rankChange < 0 ? `↑${Math.abs(rankChange)}` : `↓${rankChange}`}
            </span>
          )}
        </>
      )}

      {/* Name. #4592: `flex-auto`, NOT `flex-1` — see the layout contract above. */}
      <div className="flex items-center gap-2 flex-auto min-w-0">
        {outcomeFlag ? (
          <img
            src={outcomeFlag}
            alt={outcome.name}
            width={24}
            height={18}
            loading="lazy"
            className="rounded-sm flex-shrink-0"
          />
        ) : showEntityImage ? (
          <EntityImage type="wikipedia" name={outcome.name} size={24} />
        ) : null}
        <div className="min-w-0">
          <span
            data-testid="outcome-name"
            title={outcome.name}
            className={`text-sm truncate block ${
              isLeader ? "font-semibold text-text-primary" : "text-text-primary"
            }`}
          >
            {outcome.name}
          </span>
          {/* #4788: the verdict carries its own testid. Read off the ROW's
              `textContent`, this word has no boundary after it — the pill and the
              price column are adjacent elements, so the row reads
              "…7+LostOPEN51%" and `/\bLost\b/` does not match. A verifier written
              that way reports zero verdicts on the arm that is printing them, and
              so reads identically before and after this fix. */}
          {verdict === "won" && (
            <span
              data-testid="outcome-verdict"
              className="text-xs text-emerald-600 font-medium"
            >
              Won
            </span>
          )}
          {verdict === "lost" && (
            <span
              data-testid="outcome-verdict"
              className="text-xs text-red-400 font-medium"
            >
              Lost
            </span>
          )}
        </div>
      </div>

      {/* The three numbers, as one group. #3358: below `sm` the group takes a full
          line of its own WHEN the `Last move` column is in it, so the name is sized
          against the row instead of against the 80px column's leftovers. At `sm` and
          up, and whenever `Last move` is dropped, `basis-auto` puts it straight back
          on the name's line and this row renders exactly as it did before.

          #4592: `ml-auto` so the two ways this group can reach a second line look the
          same. #3358's `basis-full` line right-aligns its contents with `justify-end`,
          but a group that wraps on its own is `basis-auto shrink-0` and sits at the
          START of line 2 — measured at 390px, `OPEN 43% LATEST 13%` landed under the
          checkbox while the identical two-line row on a `Last move` board put it under
          the price. It costs nothing on line 1: auto margins are only fed the free
          space LEFT AFTER flex-grow, and the name cell's `flex-auto` has already taken
          all of it, so a single-line row is byte-identical to before. */}
      <div
        data-testid="outcome-numbers"
        className={`flex items-center justify-end gap-3 shrink-0 ml-auto ${
          showLastMove ? "basis-full sm:basis-auto" : "basis-auto"
        }`}
      >
        {/* Opening price. UX-P233 (board item 11): this column was the ONLY one of
            the row's three numbers that named its own baseline, which is exactly why
            the other two read as if they shared it. All three are labelled now. */}
        {outcome.opening_probability !== null && (
          <div className="text-xs text-text-secondary text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              Open
            </div>
            <div data-testid="outcome-open">
              {formatProbability(outcome.opening_probability, { rendered: renderedOpening })}
            </div>
          </div>
        )}

        {/* The last recorded move. UX-P233: was headed "24h Change" and printed a
            bare badge. It is a PER-WRITE delta (CAL-P159), so on 109441 Disney reads
            +1.5 while Disney fell from an opening 22% to 7% — both true, of different
            windows, and with neither stated the badge simply looked wrong.
            #3358: rendered only when some row in this table has a move to print. */}
        {showLastMove && (
          <div className="w-20 text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              Last move
            </div>
            {printsMove ? (
              <span
                data-testid="outcome-change"
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  (change as number) > 0
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "bg-red-500/15 text-red-400"
                }`}
              >
                {/* #5686 — POINTS, and the literal says so. `formatMovementPoints`
                    returns the magnitude in POINTS (37.8% -> 47.8% is ten
                    points, not ten percent), and the `%` that used to sit here
                    read as a tenth more than the market had. Ninth surface of
                    the family discover/044's class scan counted; routed here by
                    notice 41 because this file is ux's. */}
                {(change as number) > 0 ? "+" : "-"}
                {formatMovementPoints(change as number)} pts
              </span>
            ) : (
              <span className="text-xs text-text-muted">-</span>
            )}
          </div>
        )}

        {/* The latest recorded probability. UX-P233: "Latest", never "Now" — on
            109441 every row's last write is 2026-08-28, so a column headed "Now"
            would be the same unprovable freshness claim the movement badge was
            making. WHEN that latest reading was taken is stated once for the whole
            market, above the table, rather than repeated on all eight rows. */}
        <div className="text-right shrink-0">
          {/* #4788: the label goes with the PRICE branch, not with "the market is
              open". An ungraded row on a resolved market prints its last recorded
              price — the same cell an open row prints — so it needs the same
              header. Gated on the verdict rather than on `isResolved` because
              those are the same condition that picks the branch below; keying it
              off `isResolved` left the 51 already-ungraded rows on
              `/futures/59700266` printing a bare unlabelled number.

              #6082: gating on the verdict is now load-bearing rather than merely
              tidy. An OPEN market can carry a settled leg (a tier-3 venue
              settlement is self-justifying), so `verdict` is no longer always
              null when `!isResolved` — keyed off `isResolved` this label would
              now print "Latest" directly above a `100% / Settled` cell. */}
          {verdict === null && (
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              Latest
            </div>
          )}
          {verdict === "won" ? (
            <>
              <div className="font-mono text-base tabular-nums font-bold text-emerald-600">
                100%
              </div>
              <div className="text-xs text-emerald-500 font-medium">
                Settled
              </div>
            </>
          ) : verdict === "lost" ? (
            <>
              <div className="font-mono text-base tabular-nums font-semibold text-text-muted">
                0%
              </div>
              <div className="text-xs text-text-muted font-medium">
                Settled
              </div>
            </>
          ) : (
            <>
              <div
                className={`font-mono text-base tabular-nums ${
                  isLeader ? "font-bold text-text-primary" : "font-semibold text-text-primary"
                }`}
              >
                {formatProbability(outcome.probability, { rendered })}
              </div>
              {/* #883/L2-48: American moneyline (+9900) removed — probability only.
                  The standing no-odds thesis: "60% vs 40%", never "-150/+130". */}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
