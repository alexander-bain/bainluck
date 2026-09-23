import { describeTeamRoute } from "@/lib/teamRouteSport";
import { sportKeyForRoute } from "@/lib/teamUrls";

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
 * The OTHER shape a qualified slug takes: the LAST TOKEN of the sport key. #5852
 *
 * `leagueQualifiedSlug` above reads the suffix off the URL's `league` segment,
 * which is right whenever that segment IS the sport key's last token
 * (`soccer_epl` -> `epl`, `americanfootball_ncaaf` -> `ncaaf`). Measured on the
 * whole `teams` table 2026-09-20, it is not right in general — the suffix is
 * minted from the key, so `soccer_fa_cup` gives `arsenal-cup` and
 * `soccer_uefa_champs_league` gives `arsenal-league`, while the route segments
 * for those two are `fa_cup` and the ALIAS `ucl`. Over the 4,098 rows whose
 * name-derived URL lands on another row, this form reaches 1,418 real
 * league-qualified rows against the league-segment form's 759, and there is no
 * row it misses that the other finds — so it is tried FIRST, not instead of.
 *
 * Returns null when there is nothing to try: no key for the route, an empty
 * slug, or a slug already carrying the suffix.
 */
export function sportKeyQualifiedSlug(
  teamSlug: string,
  sport: string,
  league: string,
): string | null {
  const key = sportKeyForRoute(sport, league);
  if (!key) return null;
  const suffix = key.split("_").pop()?.toLowerCase() ?? "";
  return leagueQualifiedSlug(teamSlug, suffix);
}

/**
 * The candidate slugs for a route. Exported so a guard can assert the COUNT —
 * the cost of this repair is exactly the length of this list, and it is at
 * most two. #7651
 *
 * WHY BOTH SHAPES, AND WHY THIS ORDER. #5852 shipped only the key-derived
 * shape, on a measurement taken when 40% of `teams` had NO slug at all: 1,418
 * vs 759 with an empty difference, and zero rows ending in `-ucl` or `-arts`.
 * #7501 then backfilled 4,031 of those rows, and the shape it settled on is
 * the URL-segment form (`new-jersey-devils-nhl_preseason`,
 * `benfica-uefa_champs_league_women`, `-ucl` for the aliased keys) — 2,482 of
 * the 4,031 carry a multi-token suffix the key-derived shape never composes.
 * The old measurement's "branch no data can enter" is now the growing half of
 * the table, and the filler that mints it is the column's single owner, so the
 * segment shape is tried FIRST and the frozen legacy shape (`real-madrid-
 * league`, the `-open` tennis rows, never re-slugged) SECOND. NCAAF, EPL and
 * every other single-token league are unaffected: the two forms are the same
 * string there and dedupe to one candidate, which is why the shipped Clemson
 * repair is untouched.
 *
 * WHY AN UNDERSCORE IS ASKABLE NOW. The old "always slug-shaped" rule rested
 * on all 5,748 slugs matching `^[a-z0-9-]+$` — true before the backfill, false
 * after it by design: the settled rung-2 shape carries the segment's
 * underscores and the API serves those rows. Candidates mirror the column, not
 * `slugify`.
 */
export function teamRouteCandidates(
  teamSlug: string,
  sport: string,
  league: string,
): string[] {
  const segment = leagueQualifiedSlug(teamSlug, league);
  const keyed = sportKeyQualifiedSlug(teamSlug, sport, league);
  const candidates = [segment, keyed].filter((c): c is string => c !== null);
  return [...new Set(candidates)];
}

/** The fields that make a team page look like that team rather than a stub. */
interface TeamIdentity {
  logo_small?: string | null;
  logo_large?: string | null;
  primary_color?: string | null;
  record?: string | null;
}

/**
 * How much of a club's identity a row can put on the page: its crest, its
 * colour, its record. #5852
 *
 * This exists because "the row the URL names" is not unconditionally the better
 * page, and production says so. Of the 47 reachable clubs where the qualified
 * row is on-route, it is richer on 27 and equal on 18 — but on TWO it is
 * poorer: `/sport/soccer/turkey_super_league/team/galatasaray` is served a UCL
 * row with crest, colour and record, and the Süper Lig row has none of the
 * three; Newcastle's UCL row has no record where the EPL row it is served
 * today does. Moving those readers would fix a breadcrumb by emptying a page.
 * So a right-competition row is preferred only when it costs the reader
 * nothing, and the comparison is per-field rather than a total: a row is never
 * accepted for gaining a crest while losing the record.
 */
function identityFields(team: TeamIdentity): boolean[] {
  return [
    Boolean(team.logo_small || team.logo_large),
    Boolean(team.primary_color),
    Boolean(team.record),
  ];
}

function isNotPoorer(candidate: TeamIdentity, current: TeamIdentity): boolean {
  const next = identityFields(candidate);
  return identityFields(current).every((had, i) => !had || next[i]);
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
 * ═══ WHAT A READER SEES ON THE SECOND HALF (2026-09-20) ═══
 *
 * The original trigger was `offRoute` — the wrong SPORT. That left the wrong
 * COMPETITION untouched, because two rows of one club in two competitions are
 * always same-family. Production, 390px, measured against the served payload:
 * `/sport/soccer/epl/team/arsenal` — again, the URL the app writes for itself —
 * resolved to the EFL Cup row: breadcrumb "Home / EFL Cup / Arsenal", a grey
 * "A" placeholder where the crest goes, and no record. `…/bundesliga/team/
 * union-berlin` resolved to Union Berlin WOMEN. Of 136 clubs with a game in the
 * next 30 days, 98 were served another competition's row; 78 of those were
 * same-family, i.e. invisible to the shipped guard. So the trigger is now
 * `offRoute || offLeague` and the acceptance test moved with it.
 *
 * ═══ WHY THIS CANNOT REGRESS A WORKING PAGE ═══
 *
 * The retry fires only where the first answer is already the wrong row, and it
 * only REPLACES that answer when the second is measurably on-route by sport AND
 * competition and is not a poorer page (`isNotPoorer` — the Galatasaray and
 * Newcastle cases, where the right competition's row has no crest or no
 * record; it applies only when the first answer is on-sport, because an
 * off-sport one renders the refusal, not a page — #7651). Every other path — an on-route first answer, no qualified row, a
 * second answer that is also off-route, a second answer that would empty the
 * page — returns the first answer unchanged. The tennis population the family
 * test protects can now only move BETWEEN THE SAME PERSON'S TOURNAMENT ROWS,
 * never to another person: the second answer has to satisfy the same route test
 * the page's own link-builder wrote the URL from.
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
  T extends { team: { name: string; sport_key?: string | null } & TeamIdentity },
>(
  teamSlug: string,
  sport: string,
  league: string,
  fetchTeam: (slug: string) => Promise<T>,
): Promise<{ slug: string; data: T }> {
  const first = await fetchTeam(teamSlug);
  const verdict = describeTeamRoute(first.team, sport, league);
  if (!verdict.offRoute && !verdict.offLeague) {
    return { slug: teamSlug, data: first };
  }

  // The richness test compares two PAGES, so it binds only when the first
  // answer is one. An off-SPORT first answer is never rendered — the page
  // prints "We don't have a … page" instead — so the reader's alternative to
  // the candidate is that refusal, and any on-route row beats it. #7651:
  // `new-jersey-devils-nhl_preseason` has no crest, colour or record on
  // production (2026-09-23) while the NHL row it would be compared against has
  // crest and colour; without this the segment candidate was fetched, judged
  // "poorer" than a row the page refuses to draw, and the refusal stood.
  const firstIsAPage = !verdict.offRoute;

  for (const candidate of teamRouteCandidates(teamSlug, sport, league)) {
    try {
      const second = await fetchTeam(candidate);
      const onRoute = describeTeamRoute(second.team, sport, league);
      if (
        !onRoute.offRoute &&
        !onRoute.offLeague &&
        (!firstIsAPage || isNotPoorer(second.team, first.team))
      ) {
        return { slug: candidate, data: second };
      }
    } catch {
      // No row under this candidate — try the next shape, and if there is none
      // the first answer stands: the off-route notice is then the honest answer
      // (Hawai'i has no NCAAF page at all) and the caller renders it.
    }
  }

  return { slug: teamSlug, data: first };
}
