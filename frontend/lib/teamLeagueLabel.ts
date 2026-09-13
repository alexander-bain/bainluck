import { getSportLabel } from "@/lib/sportCategories";

/**
 * The one league label a team page shows — the breadcrumb, `document.title` and
 * the JSON-LD `SportsTeam.sport` / `memberOf.name` all read it (#5847).
 *
 * `getSportLabel` is the canonical three-source rule (#4350 / #4358 / #4381):
 * the curated map when it names the key by hand, else the server's brand, else
 * a key parse. The page used to call the key PARSER directly, so every
 * uncurated league shouted a fragment of its own key at the reader —
 * "KOREA KLEAGUE1" for a row the server calls "K League 1", "USA MLS" for MLS.
 * `LEAGUE_DISPLAY` has no soccer key at all, so that was 1,601 team pages
 * across 52 leagues, measured on production.
 *
 * The parser was not chosen by accident and its reason survives: `sport_name`
 * carried stale season-phase copy ("MLB Preseason", L2-158 Item 3). That case is
 * the CURATED branch — `baseball_mlb` is in the map — so it still answers "MLB"
 * whatever the server says.
 *
 * It lives here rather than in the page so both call sites cannot drift apart
 * again, and so the rule is testable without rendering an async page.
 */
export function teamLeagueLabel(
  team: { sport_key?: string | null; sport_name?: string | null } | undefined,
  routeLeague: string,
): string {
  if (!team?.sport_key) {
    return team?.sport_name || routeLeague.toUpperCase();
  }
  return getSportLabel(team.sport_key, team.sport_name);
}
