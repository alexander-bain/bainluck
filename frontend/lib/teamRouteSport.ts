import { buildTeamPageUrl } from "@/lib/teamUrls";
import { getCategoryForLeague } from "@/lib/sportCategories";

export interface TeamRouteVerdict {
  /**
   * True only when the team the slug RESOLVED TO measurably belongs to a
   * different sport than the URL asked for. Never true on an absent
   * measurement — see the header.
   */
  offRoute: boolean;
  /** Where this team's page actually lives, when we can say. */
  canonicalPath: string | null;
  /** The word for that sport ("Basketball"), for a reader-facing sentence. */
  familyLabel: string | null;
}

/**
 * Does the team a slug resolved to belong to the sport the URL asked for? #5852
 *
 * `/sport/<sport>/<league>/team/<team>` reads only `params.team` and calls
 * `GET /api/teams/{slug}`, which resolves BY SLUG ALONE — the `sport` and
 * `league` segments are decoration. Meanwhile `buildTeamPageUrl` derives the
 * slug by slugifying the team's NAME, so a team with no slug of its own sends
 * the reader to whichever team does own that string. Measured on production:
 * 2,478 slugless team rows whose derived URL resolves to another team, 282 of
 * them in a different sport family. Tapping "Hawai'i Rainbow Warriors" on an
 * NCAAF event opened the WNCAAB team page — HTTP 200, no football anywhere on
 * it. Alabama, Arkansas, Boise State, Boston College and Air Force are all in
 * that list.
 *
 * WHY FAMILY AND NOT THE FULL KEY. The same census splits 2,196 / 282: the big
 * half is tennis, where the derived slug lands on the same PLAYER filed under a
 * different tournament (`tennis_wta_us_open` -> `tennis_wta_miami_open`). That
 * page is about the right person and refusing it would be a regression. Only
 * the family test separates "wrong tournament row" from "wrong sport".
 *
 * WHY IT CANNOT BREAK A WORKING LINK. Every team link in the app is built by
 * `buildTeamPageUrl` from an event's own sport key, so the route segment agrees
 * with the team row whenever the slug resolved to the team the reader tapped.
 * Measured, not assumed: of 11,199 (event, team) pairs in the last 30 days —
 * both slugged and slugless — 11,199 are same-family and 0 are not.
 *
 * ABSENT IS NOT WRONG. A team with no `sport_key` yields no canonical path and
 * no verdict, and the page renders as before. A guard that refuses when it
 * cannot measure is one somebody switches off wholesale.
 */
export function describeTeamRoute(
  team: { name: string; sport_key?: string | null } | undefined,
  routeSport: string,
): TeamRouteVerdict {
  const canonicalPath = team?.sport_key
    ? buildTeamPageUrl(team.name, team.sport_key)
    : null;
  // "/sport/basketball/wncaab/team/hawaii-rainbow-warriors" -> "basketball".
  // Same function that built the link, so the two can never disagree about
  // what the segment for a sport key is.
  const segment = canonicalPath ? canonicalPath.split("/")[2] || null : null;
  const familyLabel = team?.sport_key
    ? getCategoryForLeague(team.sport_key)?.name ?? null
    : null;

  return {
    offRoute:
      segment !== null &&
      routeSport.trim() !== "" &&
      segment.toLowerCase() !== routeSport.trim().toLowerCase(),
    canonicalPath,
    familyLabel,
  };
}
