"use client";

import type { FuturesOutcome } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import EntityImage from "@/components/EntityImage";
import {
  isNonSportsCategory,
  isInternationalSport,
  isNumericLadder,
  flagUrl,
} from "@/lib/images";
import { boardOutcomeLabel, readableOpeningProbability } from "@/lib/futuresDetailDisplay";
import { SHAPE_QUANTITY, type MarketShape } from "@/lib/marketShape";
import { outcomeRowVerdict } from "@/lib/futuresOutcomeVerdict";
export { outcomeRowVerdict, RETRACTED_RESOLUTION_SOURCE } from "@/lib/futuresOutcomeVerdict";
export type { GradedRow } from "@/lib/futuresOutcomeVerdict";
import { isResultUnknown } from "@/lib/settledResultDisplay";

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
 * ## #6632 — a `field` can be a ladder too, and the card already knew it
 *
 * The paragraph that used to stand here said the other shapes are safe because
 * "`duel`, `field`, `participation` and `container_member` all have genuine entity
 * outcomes (candidates, teams, nominees) and their pictures are the point". That is
 * a statement about what a shape USUALLY holds, and `/futures/112854` ("NATO/EU
 * troops fighting in Ukraine?") refutes it: `market_type = 'field'`, three outcomes,
 * and they are **dates** — `December 31, 2026`, `June 30, 2026`, `December 31, 2025`
 * drew `D3` · `J3` · `D3`, two of them the identical chip, on production at 390px.
 * A shape says how a board is ORDERED, not whether its rungs have faces.
 *
 * So the gate asks the outcome SET whether it is a ladder, and it does not have to
 * invent a way to ask: `isNumericLadder` (#4416) is exactly that question, and
 * `FuturesCard` has gated its own avatar on `isNonSports && !numericLadder` since
 * that queue. The detail page simply never adopted it — the same predicate, one
 * call site short. Its test is a shared SKELETON, not a numeric look: `50 Cent` and
 * `Drake` reduce to two different things, so a field of rappers keeps its faces,
 * while `Democrats, 2+ pts` and `Democrats, 5+ pts` reduce to one.
 *
 * Measured over the FULL live population (2026-09-16, 9,476 open non-sports markets,
 * every non-`quantity` one scanned): **907 flip** — 860 `field`, 47 `duel`, 0
 * `container_member`, 0 `unshaped`. Every flip read by hand in two passes (all 47
 * duels; the 33 whose outcome text matches no threshold/date vocabulary at all) and
 * **no false positive found**: they are margins-of-victory, ballot-measure numbers,
 * rate-cut counts, quarters and dates. The 47 `duel` rows are the reason this is not
 * scoped to `field` — the shape a census once measured at 0% now flips 47, which is
 * the same lesson twice.
 *
 * `quantity` keeps its own unconditional arm above: the shape is *known* to be
 * thresholds even where the names are too irregular to share a skeleton.
 * `claim` and `unshaped` are unchanged — unknown is not "known to be a threshold".
 *
 * Nothing renumbers. Unlike the card, where the avatar and the rank badge share one
 * slot, this row draws its badge separately, so a withheld picture leaves the rung's
 * position, name, prices and verdict exactly where they were.
 *
 * Shape and names are supplied by the CALLER, once, over the whole outcome set — the
 * same division as `showLastMove` below, and for the same reason: `resolveShape()`
 * owns the `market_type`-then-fallback preference order (`lib/types.ts`: "callers
 * must not re-derive shape themselves") and both tests need every outcome name,
 * which a single row does not have. `outcomeNames` is REQUIRED for the reason
 * `showEntityImage` is: an optional one would let the next surface inherit the bug.
 */
export function outcomeRowShowsEntityImage(
  marketCategory: string | null | undefined,
  shape: MarketShape | null,
  outcomeNames: readonly string[],
): boolean {
  if (!isNonSportsCategory(marketCategory ?? null)) return false;
  if (shape === SHAPE_QUANTITY) return false;
  return !isNumericLadder(outcomeNames);
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
  const openingShown = readableOpeningProbability(outcome);
  // #4788: the ONE settled-state decision for this row. Every branch below reads
  // it — never `isResolved && outcome.is_winner === X`, which counts a defaulted
  // `false` as a grader's verdict.
  const verdict = outcomeRowVerdict(outcome, isResolved);
  // #698 — a settled row with NO result to state. Not the ungraded/live
  // fallback below: it says "Result unknown", labels a finite price as the LAST
  // RECORDED one, never prints a final 0%/100%, a win/loss tint or a move, and
  // stops wearing the leader's amber — on `/futures/62134744` the "leader" was
  // one side of a 50/50 tie on a finished match.
  const resultUnknown = isResultUnknown(outcome, isResolved);
  const leads = isLeader && !resultUnknown;

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

  // #6765 — THE ROW STOPS REPEATING THE QUESTION THE <h1> ALREADY ASKED, and
  // this is the half of that defect a reader actually loses information to.
  //
  // `marketName` has been threaded in from both call sites since #4483 and had
  // NO consumer — the prop existed, the page filled it, and nothing read it.
  // What that cost is visible on `/futures/61645756` at 390px: the name span is
  // `truncate`, so three different sub-markets whose names all begin with the
  // 45-character board name render as three IDENTICAL rows —
  // `Korea Open: Alevtina Ibragimova vs Yeon…` three times, ranked 1, 3 and 4,
  // with no way to tell which is Set 1 and which is the match total. The hero
  // above merely wastes a line; here the truncation destroys the distinction.
  //
  // Only the PAINTED text changes. `title` and `data-outcome-name` keep the full
  // served name deliberately: the tooltip is the reader's way back to it, and the
  // attribute is an IDENTITY key that `futuresDetailOutcomeOrder` and
  // `settledBoardRankBadge6325` read to assert row ORDER — a probe asking "which
  // rows, in what order" must not have to know this page's shortening rule. The
  // guard for this ship asserts both halves so the pair cannot drift apart.
  const outcomeLabel = boardOutcomeLabel(outcome.name, marketName);

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
          : leads
          ? "bg-amber-50 border border-amber-200"
          : "bg-charcoal/5 hover:bg-charcoal/10"
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
              : "border-charcoal/30 hover:border-text-secondary"
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
              leads ? "font-semibold text-text-primary" : "text-text-primary"
            }`}
          >
            {outcomeLabel}
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
          {/* #698 — its own testid, NOT `outcome-verdict`: probes count that id
              as "rows stating a result", and this row states that it has none. */}
          {resultUnknown && (
            <span
              data-testid="outcome-result-unknown"
              className="text-xs text-text-secondary font-medium"
            >
              Result unknown
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
        {/* #8313: an opening whose own odds name the other side's price is not
            printed, the same as a missing one (`readableOpeningProbability`). */}
        {openingShown !== null && (
          <div className="text-xs text-text-secondary text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              Open
            </div>
            <div data-testid="outcome-open">
              {formatProbability(openingShown, { rendered: renderedOpening })}
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
          {verdict === null && !(resultUnknown && outcome.probability == null) && (
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              {resultUnknown ? "Last recorded" : "Latest"}
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
          ) : resultUnknown && outcome.probability == null ? null : (
            <>
              <div
                data-testid="outcome-price"
                className={`font-mono text-base tabular-nums ${
                  leads ? "font-bold text-text-primary" : "font-semibold text-text-primary"
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
