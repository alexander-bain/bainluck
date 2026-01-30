"use client";

import type { BookmakerOddsDetail } from "@/lib/types";

interface BookmakerTableProps {
  bookmakerOdds: BookmakerOddsDetail[];
  homeTeam: string;
  awayTeam: string;
}

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

  // Sort by home probability descending to show range clearly
  const sortedOdds = [...bookmakerOdds].sort((a, b) => {
    const aProb = a.home_probability ?? 0;
    const bProb = b.home_probability ?? 0;
    return bProb - aProb;
  });

  // Calculate average for comparison
  const validHomeProbs = bookmakerOdds
    .map((b) => b.home_probability)
    .filter((p): p is number => p !== null);
  const avgHomeProb =
    validHomeProbs.length > 0
      ? validHomeProbs.reduce((a, b) => a + b, 0) / validHomeProbs.length
      : null;

  // Shorten team names for table header
  const shortHomeTeam = homeTeam.split(" ").pop() || homeTeam;
  const shortAwayTeam = awayTeam.split(" ").pop() || awayTeam;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-mist">
            <th className="text-left py-3 px-4 font-semibold text-slate">
              Sportsbook
            </th>
            <th className="text-center py-3 px-4 font-semibold text-slate">
              {shortHomeTeam} (Home)
            </th>
            <th className="text-center py-3 px-4 font-semibold text-slate">
              {shortAwayTeam} (Away)
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedOdds.map((odds) => {
            const homeProb = odds.home_probability;
            const awayProb = odds.away_probability;

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
                }`}
              >
                <td className="py-3 px-4 font-medium text-graphite">
                  {odds.bookmaker}
                  {isDivergent && (
                    <span className="ml-2 text-xs text-amber-600">*</span>
                  )}
                </td>
                <td className="py-3 px-4 text-center font-mono tabular-nums">
                  {homeProb !== null ? `${(homeProb * 100).toFixed(1)}%` : "-"}
                </td>
                <td className="py-3 px-4 text-center font-mono tabular-nums">
                  {awayProb !== null ? `${(awayProb * 100).toFixed(1)}%` : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
        {avgHomeProb !== null && (
          <tfoot>
            <tr className="bg-slate/5 font-semibold">
              <td className="py-3 px-4 text-graphite">Average (Consensus)</td>
              <td className="py-3 px-4 text-center font-mono tabular-nums text-graphite">
                {(avgHomeProb * 100).toFixed(1)}%
              </td>
              <td className="py-3 px-4 text-center font-mono tabular-nums text-graphite">
                {((1 - avgHomeProb) * 100).toFixed(1)}%
              </td>
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
        <p className="text-xs text-amber-600 mt-2 px-4">
          * Differs from consensus by more than 5%
        </p>
      )}
    </div>
  );
}
