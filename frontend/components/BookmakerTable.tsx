"use client";

import type { BookmakerOddsDetail } from "@/lib/types";
import { isNamedSource, sourceLabel } from "@/lib/sourceLabels";
import { formatSourceAge, formatSourceStamp } from "@/lib/sourceAge";

interface BookmakerTableProps {
  bookmakerOdds: BookmakerOddsDetail[];
  homeTeam: string;
  awayTeam: string;
}

/*
 * `formatRelativeTime` and `formatAbsoluteTime` used to live here as private
 * functions. #4970 needs the same two sentences on `/events/{id}/models`, where
 * the per-SOURCE numbers carry no age at all, so they moved to
 * `@/lib/sourceAge` as `formatSourceAge` / `formatSourceStamp` — a move, not a
 * copy, for the reason that file's header gives. The thresholds and the wording
 * are unchanged; the only difference is that both now return `null` for an
 * absent or unparseable stamp instead of walking `NaN` through the comparisons
 * and printing "NaN d ago". The `"-"` this column already showed for a missing
 * `captured_at` is preserved at the call site below.
 */

/**
 * Table showing win probabilities by sportsbook.
 * Helps users see consensus and which books differ.
 */
export default function BookmakerTable({
  bookmakerOdds,
  homeTeam,
  awayTeam,
}: BookmakerTableProps) {
  if (!bookmakerOdds || bookmakerOdds.length === 0) {
    return null;
  }

  // Filter out sportsbooks without probability data (they only have spread/totals),
  // and those this app cannot name (#4284). The naming filter runs HERE, before
  // the average, the counts and the divergence flag are derived, so the table can
  // never disagree with its own footer about how many sportsbooks it is showing —
  // the trap the iOS half hit when it capped the list before labelling it.
  const oddsWithProbability = bookmakerOdds.filter(
    (odds) =>
      odds.home_probability !== null &&
      odds.away_probability !== null &&
      isNamedSource(odds.bookmaker)
  );

  // If no bookmakers have probability data, show a message
  if (oddsWithProbability.length === 0) {
    return (
      <div className="text-center py-4 text-sm text-slate">
        No win probability data available from sportsbooks for this event.
      </div>
    );
  }

  // Check if any odds are stale (>30 minutes old)
  const now = new Date();
  const isStale = (isoString: string): boolean => {
    const date = new Date(isoString);
    const diffMs = now.getTime() - date.getTime();
    return diffMs > 30 * 60 * 1000; // 30 minutes
  };

  // Sort by home probability descending to show range clearly
  const sortedOdds = [...oddsWithProbability].sort((a, b) => {
    const aProb = a.home_probability ?? 0;
    const bProb = b.home_probability ?? 0;
    return bProb - aProb;
  });

  // Calculate average ONLY from non-stale sportsbooks (those still actively updating)
  const activeOdds = oddsWithProbability.filter(
    (b) => b.captured_at && !isStale(b.captured_at)
  );
  const validHomeProbs = activeOdds
    .map((b) => b.home_probability)
    .filter((p): p is number => p !== null);
  const avgHomeProb =
    validHomeProbs.length > 0
      ? validHomeProbs.reduce((a, b) => a + b, 0) / validHomeProbs.length
      : null;

  // Calculate average projected scores from active bookmakers that have score data
  const activeWithScores = activeOdds.filter(
    (b) => b.projected_home_score != null && b.projected_away_score != null
  );
  const avgProjectedHomeScore =
    activeWithScores.length > 0
      ? activeWithScores.reduce((sum, b) => sum + (b.projected_home_score ?? 0), 0) / activeWithScores.length
      : null;
  const avgProjectedAwayScore =
    activeWithScores.length > 0
      ? activeWithScores.reduce((sum, b) => sum + (b.projected_away_score ?? 0), 0) / activeWithScores.length
      : null;

  // Count how many are stale vs active
  const staleCount = oddsWithProbability.filter(
    (b) => b.captured_at && isStale(b.captured_at)
  ).length;
  const activeCount = oddsWithProbability.length - staleCount;

  // Shorten team names for table header
  const shortHomeTeam = homeTeam.split(" ").pop() || homeTeam;
  const shortAwayTeam = awayTeam.split(" ").pop() || awayTeam;

  // Check if any SHOWN sportsbook has projected scores — reading the unfiltered
  // array here would head a column "(proj. score)" that no visible row fills.
  const hasAnyProjectedScores = oddsWithProbability.some(
    (odds) => odds.projected_home_score != null && odds.projected_away_score != null
  );

  return (
    // ── #4317: the fourth column has to survive a 390px phone ────────────────
    //
    // Every cell was `px-4`. Four columns of 32px chrome put the table's
    // intrinsic width past the card, the container scrolled, and the column that
    // went over the edge was `Status` — the one carrying the caveat about
    // whether the number beside it is still being updated. The header rendered
    // as `St` and all eleven rows read `Clo` with the time sliced to `51r`.
    //
    // Measured on production 2026-09-09, `/events/15307463` at 390px with the
    // disclosure open. The container is 334px and this table's content, with all
    // padding removed, is 253.7px — so the intrinsic width is `253.7 + 8 * pad`,
    // which reproduces all three readings exactly:
    //
    //     pad 16px (`px-4`)  381.7  →  48px over  ← what shipped
    //     pad 12px (`px-3`)  349.7  →  16px over  ← still clipped
    //     pad  8px (`px-2`)  317.7  →   0, fits with 16px to spare
    //
    // Hence `px-2`, and hence not `px-3`: the budget allows at most 10px a side.
    // Full width is restored from `sm` up, where there was never a problem.
    //
    // The horizontal scroll is deliberately LEFT IN PLACE. Column widths are
    // content-driven, so two long surnames can still exceed the budget (measured:
    // two `Khachanov`-width columns overflow by 13px even at `px-2`), and the
    // scroll is the honest fallback for that. What it must not be is the everyday
    // state of the table, which is what it had become.
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-mist">
            <th className="text-left py-3 px-2 sm:px-4 font-semibold text-slate">
              Sportsbook
            </th>
            <th className="text-center py-3 px-2 sm:px-4 font-semibold text-slate">
              <div>{shortHomeTeam}</div>
              {hasAnyProjectedScores && <div className="text-xs font-normal text-text-muted">(proj. score)</div>}
            </th>
            <th className="text-center py-3 px-2 sm:px-4 font-semibold text-slate">
              <div>{shortAwayTeam}</div>
              {hasAnyProjectedScores && <div className="text-xs font-normal text-text-muted">(proj. score)</div>}
            </th>
            <th className="text-right py-3 px-2 sm:px-4 font-semibold text-slate">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedOdds.map((odds) => {
            const homeProb = odds.home_probability;
            const awayProb = odds.away_probability;
            const stale = odds.captured_at ? isStale(odds.captured_at) : false;
            const hasProjectedScore = odds.projected_home_score != null && odds.projected_away_score != null;

            // Highlight if this book differs significantly from average (>5%)
            const isDivergent =
              avgHomeProb !== null &&
              homeProb !== null &&
              Math.abs(homeProb - avgHomeProb) > 0.05;

            return (
              <tr
                key={odds.bookmaker}
                className={`border-b border-mist/50 ${
                  isDivergent ? "bg-amber-50" : ""
                } ${stale ? "opacity-60" : ""}`}
              >
                <td className="py-3 px-2 sm:px-4 font-medium text-graphite">
                  {sourceLabel(odds.bookmaker)}
                  {isDivergent && (
                    <span className="ml-2 text-xs text-amber-600">*</span>
                  )}
                </td>
                <td className="py-3 px-2 sm:px-4 text-center">
                  <div className="font-mono tabular-nums">
                    {homeProb !== null ? `${(homeProb * 100).toFixed(1)}%` : "-"}
                  </div>
                  {hasProjectedScore && (
                    <div className="text-xs text-text-muted mt-0.5" title="Projected score">
                      {Math.round(odds.projected_home_score!)}
                    </div>
                  )}
                </td>
                <td className="py-3 px-2 sm:px-4 text-center">
                  <div className="font-mono tabular-nums">
                    {awayProb !== null ? `${(awayProb * 100).toFixed(1)}%` : "-"}
                  </div>
                  {hasProjectedScore && (
                    <div className="text-xs text-text-muted mt-0.5" title="Projected score">
                      {Math.round(odds.projected_away_score!)}
                    </div>
                  )}
                </td>
                <td
                  className="py-3 px-2 sm:px-4 text-right"
                  title={formatSourceStamp(odds.captured_at) ?? undefined}
                >
                  {stale ? (
                    <span className="inline-flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">
                      Closed
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      Open
                    </span>
                  )}
                  <div className="text-xs text-text-muted mt-1">
                    {formatSourceAge(odds.captured_at) ?? "-"}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
        {avgHomeProb !== null && (
          <tfoot>
            <tr className="bg-slate/5 font-semibold">
              <td className="py-3 px-2 sm:px-4 text-graphite">
                Average (Consensus)
                {staleCount > 0 && (
                  <span className="ml-2 text-xs font-normal text-slate">
                    ({activeCount} of {oddsWithProbability.length} open)
                  </span>
                )}
              </td>
              <td className="py-3 px-2 sm:px-4 text-center">
                <div className="font-mono tabular-nums text-graphite">
                  {(avgHomeProb * 100).toFixed(1)}%
                </div>
                {avgProjectedHomeScore !== null && (
                  <div className="text-xs text-text-muted font-normal mt-0.5" title="Projected score">
                    {Math.round(avgProjectedHomeScore)}
                  </div>
                )}
              </td>
              <td className="py-3 px-2 sm:px-4 text-center">
                <div className="font-mono tabular-nums text-graphite">
                  {((1 - avgHomeProb) * 100).toFixed(1)}%
                </div>
                {avgProjectedAwayScore !== null && (
                  <div className="text-xs text-text-muted font-normal mt-0.5" title="Projected score">
                    {Math.round(avgProjectedAwayScore)}
                  </div>
                )}
              </td>
              <td className="py-3 px-2 sm:px-4"></td>
            </tr>
          </tfoot>
        )}
      </table>
      {sortedOdds.some(
        (odds) =>
          avgHomeProb !== null &&
          odds.home_probability !== null &&
          Math.abs(odds.home_probability - avgHomeProb) > 0.05
      ) && (
        <p className="text-xs text-amber-600 mt-2 px-2 sm:px-4">
          * Differs from consensus by more than 5%
        </p>
      )}
    </div>
  );
}
