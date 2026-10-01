import type { ChampionshipPathEntry, TeamFutureItem } from "@/lib/api";

/**
 * The team page's Season Futures list: everything the championship path does
 * not already show (lifted out of the page so a test can reach it — #10078).
 *
 * The path holds the tier 1/2/4 questions (title, conference, division), so
 * when it exists those rows are dropped here. The tier read is the one the
 * row is SHOWN at (`display_tier`, served by the team route): a playoff-
 * qualifier board stored at tier 4 (#7189) is never a path step — the path
 * refuses it — so Miami's "College Football Playoff Qualifiers" 83.5% stays
 * listed instead of vanishing behind a step that is not about it.
 */
export function seasonFuturesRows(
  futures: TeamFutureItem[],
  championshipPath: ChampionshipPathEntry[]
): TeamFutureItem[] {
  if (championshipPath.length === 0) return futures;
  return futures.filter(
    (f) => ![1, 2, 4].includes(f.display_tier ?? f.market_tier ?? -1)
  );
}
