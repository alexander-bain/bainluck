import { describeTeamRoute } from "@/lib/teamRouteSport";

/**
 * The league-qualified form of a team slug, or null when there isn't one. #5852
 *
 * Team rows are slugged per competition, and where a bare name-slug is already
 * taken the row carries the league as a suffix — measured uniform across every
 * sport that does it: `clemson-tigers-ncaaf`, `boston-red-sox-mlb`,
 * `arsenal-epl`. That suffix token is EXACTLY the `league` segment the URL
 * already carries, because `buildTeamPageUrl` writes both from the same sport
 * key, so this composes the candidate rather than guessing at it.
 *
 * Returns null when there is nothing to try: an empty league, or a slug that
 * already ends in the suffix (otherwise a reader who lands on the canonical
 * `clemson-tigers-ncaaf` and somehow misses would have us ask for
 * `clemson-tigers-ncaaf-ncaaf`).
 */
export function leagueQualifiedSlug(
  teamSlug: string,
  league: string,
): string | null {
  const slug = teamSlug.trim();
  const suffix = league.trim().toLowerCase();
  if (!slug || !suffix) return null;
  if (slug.toLowerCase().endsWith(`-${suffix}`)) return null;
  return `${slug}-${suffix}`;
}

/**
 * Resolve the team a `/sport/<sport>/<league>/team/<slug>` URL is ASKING for,
 * rather than the one its slug happens to own. The link half of #5852.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, 390px, 2026-09-13 ~13:3xZ. `/sport/football/ncaaf/team/clemson-tigers`,
 * reached by tapping "Clemson Tigers" in an NCAAF event hero:
 *
 *     We don't have a football page for Clemson Tigers.
 *     Clemson Tigers — Basketball        Back to NCAAF
 *
 * That sentence is FALSE. The football page exists and renders in full at
 * `/sport/football/ncaaf/team/clemson-tigers-ncaaf` — record 1-1, championship
 * 1%, an upcoming game vs North Carolina at 63%. We had it the whole time and
 * told the reader we did not.
 *
 * ═══ MECHANISM ═══
 *
 * `GET /api/teams/{slug}` resolves BY SLUG ALONE — it is never told which sport
 * the reader is in, even though the path says `football/ncaaf`. `clemson-tigers`
 * is owned by the WNCAAB row (team 72), so that is who answers; the NCAAF row
 * (team 10) is slugged `clemson-tigers-ncaaf` and is never asked for. The
 * shipped guard (`describeTeamRoute`) correctly NOTICES the wrong sport came
 * back. This is the half that then goes and gets the right one.
 *
 * ═══ WHY THIS CANNOT REGRESS A WORKING PAGE ═══
 *
 * The retry fires only on the branch that is already rendering a failure
 * notice, and only replaces the first answer when the second is measurably
 * on-route. Every other path — on-route first answer, no league-qualified row,
 * a second answer that is also off-route — returns the first answer unchanged,
 * so the reader sees exactly what they see today. The tennis case that the
 * family test exists to protect (same player, wrong tournament: `offRoute`
 * false) never reaches the retry at all.
 *
 * ═══ WHY A THROWN FIRST FETCH IS NOT RETRIED ═══
 *
 * Measured on production over the ±48h reader window (950 distinct teams on
 * real events): 191 teams resolve to another sport's page, 17 of those have a
 * league-qualified row this reaches — and **0** teams whose bare slug resolves
 * to nothing have one. There is no population behind a retry-on-error, so it
 * would be an extra request on every genuinely-missing team page bought for
 * nothing. A 404 keeps today's "Team not found".
 */
export async function resolveTeamForRoute<
  T extends { team: { name: string; sport_key?: string | null } },
>(
  teamSlug: string,
  sport: string,
  league: string,
  fetchTeam: (slug: string) => Promise<T>,
): Promise<{ slug: string; data: T }> {
  const first = await fetchTeam(teamSlug);
  if (!describeTeamRoute(first.team, sport).offRoute) {
    return { slug: teamSlug, data: first };
  }

  const candidate = leagueQualifiedSlug(teamSlug, league);
  if (!candidate) return { slug: teamSlug, data: first };

  try {
    const second = await fetchTeam(candidate);
    if (!describeTeamRoute(second.team, sport).offRoute) {
      return { slug: candidate, data: second };
    }
  } catch {
    // No league-qualified row for this team — the off-route notice is then the
    // honest answer (Hawai'i has no NCAAF page at all) and the caller renders it.
  }

  return { slug: teamSlug, data: first };
}
