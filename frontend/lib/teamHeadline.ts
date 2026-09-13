/**
 * THE ONE NUMBER A TEAM PAGE LEADS WITH.
 *
 * Lifted verbatim out of the team page's own render so the PICTURE a pasted
 * team link unfurls with cannot quote a different number than the page it
 * points at. That is the discipline the rest of the unfurl family already
 * keeps — `hubCardCopy` takes `buildHubShareCopy`'s two fields rather than
 * retyping them, `unresolvedCardCopy` takes `unresolvedShareCopy`'s title — and
 * this is the same move for the one route where the headline was computed
 * inline in an async page component, i.e. in the one place a test cannot reach
 * and an `opengraph-image.tsx` route cannot import.
 *
 * ⚠️ NOT A BEHAVIOUR CHANGE. Every branch below is the page's, in its order,
 * with its comments. If this file and the page ever disagree about the Red Sox,
 * the bug is that somebody edited one of them.
 *
 * ═══ WHY THE CHAMPIONSHIP AND NOT THE NEXT GAME ═══
 *
 * A team page's signature number is its season price — one number per question
 * (the blend-is-the-product ruling), and the question a team page is about is
 * "does this team win it". The next game is a different question with its own
 * card on `/events/[id]`; putting both on one image with two bars under them
 * would invite a reader to compare a 6% and a 62% that are not comparable.
 */

import type { ChampionshipPathEntry, TeamFutureItem } from "@/lib/api";
import { pickJourneyFuture } from "@/lib/teamSeasonJourney";

export interface TeamHeadline {
  /** "Championship", "Conference", "Division", or the path entry's own label. */
  label: string;
  /** 0..1. Never null — a headline with no number is no headline. */
  probability: number;
  /** Points of 24h movement, when the source carries one. */
  movement: number | null;
}

/**
 * The word for a season market's tier, on the fallback branch.
 *
 * Only the three tiers `pickJourneyFuture` prefers are named. Anything else
 * reaches this map only when the team has NOTHING in tiers 1/2/4, and then
 * "Championship" is the honest generic — the same default the page shipped.
 */
const TIER_LABEL: Record<number, string> = {
  1: "Championship",
  2: "Conference",
  4: "Division",
};

/**
 * The team's "price", or null when it cannot be stated.
 *
 * Prefer the dedicated championship path (tier-1 Championship, else strongest
 * step). When the backend ships an empty champ-path but the futures payload
 * still carries the season markets (the live Red Sox case — measured on
 * production 2026-09-13, `championship_path: []` and 24 futures), fall back to
 * the best season future so the signature number never silently disappears.
 */
export function teamHeadline(
  championshipPath: ChampionshipPathEntry[] | null | undefined,
  futures: TeamFutureItem[] | null | undefined,
): TeamHeadline | null {
  const path = championshipPath ?? [];
  const pathEntry = path.find((e) => e.tier === 1) ?? path[0] ?? null;
  if (pathEntry && pathEntry.probability !== null) {
    return {
      label: pathEntry.label,
      probability: pathEntry.probability,
      movement: pathEntry.movement,
    };
  }

  const pick = pickJourneyFuture(futures);
  if (!pick || pick.probability === null) return null;
  const item = (futures ?? []).find(
    (f) => f.market_id === pick.marketId && f.outcome_id === pick.outcomeId,
  );
  return {
    label: TIER_LABEL[item?.market_tier ?? 1] ?? "Championship",
    probability: pick.probability,
    movement: item?.probability_change_24h ?? null,
  };
}
