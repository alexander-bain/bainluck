"use client";

import type { FuturesOutcome } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import EntityImage from "@/components/EntityImage";
import { isNonSportsCategory, isInternationalSport, flagUrl } from "@/lib/images";
import { SHAPE_QUANTITY, type MarketShape } from "@/lib/marketShape";

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

export function outcomeRowVerdict(
  outcome: FuturesOutcome,
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
  if (!isResolved) return null;
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

      {/* Rank */}
      <span
        className={`w-8 h-8 flex items-center justify-center text-sm rounded-full shrink-0 ${
          isLeader
            ? "bg-amber-100 text-amber-700 font-bold"
            : "bg-surface-card text-text-secondary border border-surface-border"
        }`}
      >
        {rank}
      </span>

      {/* Rank change indicator */}
      {rankChange !== null && rankChange !== 0 && (
        <span
          className={`text-xs shrink-0 ${
            rankChange < 0 ? "text-emerald-600" : "text-red-500"
          }`}
        >
          {rankChange < 0 ? `↑${Math.abs(rankChange)}` : `↓${rankChange}`}
        </span>
      )}

      {/* Name */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
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
          on the name's line and this row renders exactly as it did before. */}
      <div
        data-testid="outcome-numbers"
        className={`flex items-center justify-end gap-3 shrink-0 ${
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
                {(change as number) > 0 ? "+" : "-"}
                {formatMovementPoints(change as number)}%
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
              `/futures/59700266` printing a bare unlabelled number. Open markets
              are unaffected: `verdict` is always null when not resolved. */}
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
