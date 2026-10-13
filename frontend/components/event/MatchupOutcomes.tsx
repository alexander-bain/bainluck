import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import type { GameMarketsResponse } from "@/lib/api";
import { renderedPercent } from "@/lib/renderedPercent";

type Matchup = NonNullable<GameMarketsResponse["matchups"]>[number];

/**
 * One Matchups entry (H2H / 3-ball) on the event page.
 *
 * #10980. A finished game printed every head-to-head as `Last quotes` with a
 * 100% / 0% bar while the payload already carried the venue's grade on each
 * leg — #6138's defect in the section #6138 did not reach. A graded row now
 * states its result through `outcomeRowVerdict` (the one settled-state rule;
 * retraction, served-null and absent-key handling are all its own), in the
 * words Special markets use for the same state: `Won` in the accent, `Lost`
 * muted, standing in the price slot with no bar. `· Last quotes` stays only
 * while a row on this matchup is still a price.
 */
export default function MatchupOutcomes({
  matchup,
  finished,
}: {
  matchup: Matchup;
  finished: boolean;
}) {
  const verdicts = matchup.outcomes.map((o) => outcomeRowVerdict(o, finished));
  const anyPriced = verdicts.some((v) => v === null);
  return (
    <div className="px-4 sm:px-5 py-3">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-xs font-medium text-text-secondary">
          {matchup.market_name}
          {finished && anyPriced ? " · Last quotes" : ""}
        </span>
        {/* L2-52: source-name badge removed (blend-only). */}
      </div>
      <div className="space-y-2">
        {matchup.outcomes.map((outcome, oidx) => {
          const verdict = verdicts[oidx];
          if (verdict !== null) {
            return (
              <div
                key={oidx}
                className="flex items-center gap-3"
                data-testid="matchup-verdict"
                data-verdict={verdict}
              >
                <span
                  className={`flex-1 text-xs truncate ${
                    verdict === "won" ? "font-semibold text-text-primary" : "font-medium text-text-secondary"
                  }`}
                >
                  {outcome.name}
                </span>
                <span
                  className={
                    verdict === "won"
                      ? "text-xs font-mono tabular-nums font-bold text-emerald-600"
                      : "text-xs font-mono tabular-nums text-text-muted"
                  }
                >
                  {verdict === "won" ? "Won" : "Lost"}
                </span>
              </div>
            );
          }
          // #3867 (CERT-2224 repair): the label routes through the
          // contract; `Math.max(pct, 2)` below is still the bar's geometry.
          const pct = renderedPercent(outcome.probability) ?? 0;
          const isLeader = outcome.probability === Math.max(...matchup.outcomes.map((o) => o.probability));
          return (
            <div key={oidx} className="flex items-center gap-3">
              <span className={`text-xs font-medium w-[140px] sm:w-[180px] truncate ${isLeader ? "text-text-primary" : "text-text-secondary"}`}>
                {outcome.name}
              </span>
              <div className="flex-1 h-5 bg-surface-elevated rounded-full overflow-hidden relative">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.max(pct, 2)}%`,
                    backgroundColor: isLeader ? "#10B981" : "#94A3B8",
                    opacity: isLeader ? 1 : 0.5,
                  }}
                />
              </div>
              <span className={`text-xs font-bold tabular-nums w-10 text-right ${isLeader ? "text-text-primary" : "text-text-muted"}`}>
                {pct}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
