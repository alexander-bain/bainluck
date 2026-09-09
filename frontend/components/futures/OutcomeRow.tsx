"use client";

import type { FuturesOutcome } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";
import EntityImage from "@/components/EntityImage";
import { isNonSportsCategory, isInternationalSport, flagUrl } from "@/lib/images";

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
  // A settled row prints its result, never a movement.
  if (isResolved && outcome.is_winner !== null) return false;
  const change = outcome.probability_change_24h;
  // UX-P275: the gate asks whether a move PRINTS, not whether the wire fraction is
  // nonzero — anything that rounds to zero is no move.
  return change !== null && change !== undefined && isRenderedMove(change);
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
}) {
  const change = outcome.probability_change_24h;
  const rankChange = outcome.rank_change_24h;
  const printsMove = outcomeRowPrintsMove(outcome, isResolved);

  // Entity image detection
  const isNonSports = isNonSportsCategory(marketCategory ?? null);
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
          : isResolved && outcome.is_winner === true
          ? "bg-emerald-50 border border-emerald-200"
          : isResolved && outcome.is_winner === false
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
        ) : isNonSports ? (
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
          {isResolved && outcome.is_winner === true && (
            <span className="text-xs text-emerald-600 font-medium">Won</span>
          )}
          {isResolved && outcome.is_winner === false && (
            <span className="text-xs text-red-400 font-medium">Lost</span>
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
          {!isResolved && (
            <div className="text-[10px] uppercase tracking-wide text-text-muted">
              Latest
            </div>
          )}
          {isResolved && outcome.is_winner === true ? (
            <>
              <div className="font-mono text-base tabular-nums font-bold text-emerald-600">
                100%
              </div>
              <div className="text-xs text-emerald-500 font-medium">
                Settled
              </div>
            </>
          ) : isResolved && outcome.is_winner === false ? (
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
