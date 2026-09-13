/**
 * WHAT A PASTED TEAM LINK SAYS, AND THE PICTURE IT DRAWS.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * `/sport/[sport]/[league]/team/[team]` is the last route on check 8's ratchet
 * that still unfurled with the house card, and it is the one a fan actually
 * pastes (`lib/shareCard.ts` carries the 2026-09-08 measurement). Read with a
 * crawler UA against production 2026-09-13 12:31:54Z:
 *
 *   /sport/baseball/mlb/team/boston-red-sox    og:image      …bainluck.com/opengraph-image
 *                                              twitter:image …bainluck.com/opengraph-image
 *   /sport/basketball/nba/team/boston-celtics  identical, both namespaces
 *
 * `GET <route>/opengraph-image` answered 404 on every team page — there was no
 * file — so `defaultShareCard()` was the picture, and the Red Sox, the Celtics
 * and a slug that names nothing were one image in chat.
 *
 * ═══ THE THREE THINGS A TEAM URL CAN BE ═══
 *
 * 1. A TEAM. Its name, its record, and the one number the page itself leads
 *    with — `teamHeadline`, imported rather than retyped, so the picture and
 *    the page cannot quote different odds for the Red Sox.
 *
 * 2. A TEAM AT THE WRONG ADDRESS (#5852). `GET /api/teams/{slug}` resolves BY
 *    SLUG ALONE, so `/sport/football/ncaaf/team/hawaii-rainbow-warriors` answers
 *    200 with a BASKETBALL team. The page already refuses to render football
 *    that is not there; the card has to refuse too, and this is exactly the
 *    #5846 class — a confident card asserting a fact nobody has.
 *
 *    ⚠️ It must NOT say "this team isn't on Bain Luck". The team IS on Bain
 *    Luck, at another address, and `unresolvedShareCopy`'s sentence would be
 *    false. It says what the page says instead, which is why this branch has
 *    its own copy and does not reach for the shared subject.
 *
 * 3. NOTHING. A 404 from `/api/teams/{slug}` — measured clean, 2026-09-13
 *    12:33Z, `not-a-real-team-99999` answers 404 while both real teams answer
 *    200 — or a segment that could never be a slug. Anything else (a 500, a
 *    timeout, an unparseable body) is `"unavailable"` and claims nothing about
 *    whether the team exists: gotcha #53, and the reason this module never
 *    collapses the two.
 *
 * ═══ WHY EVERY DECISION IS HERE AND THE ROUTES ARE SPREADS ═══
 *
 * `hubCardCopy` is the precedent and the reason. When `/hub/[competition]` left
 * the accent in the route rather than in the pure function, a mutant replacing
 * `accentFor(competition)` with `accentFor(null)` — all five hubs one colour,
 * the exact defect that ship removed — survived the whole suite, because no
 * test could reach a decision the route still owned. So `layout.tsx` and
 * `opengraph-image.tsx` below make no choices: they fetch, they classify, they
 * spread.
 */

import { accentFor, type UnfurlCardProps } from "@/components/og/UnfurlCard";
import type { ChampionshipPathEntry, TeamFutureItem, TeamPageTeam } from "@/lib/api";
import { withSiteSuffix } from "@/lib/eventShareMeta";
import { formatShareProbability } from "@/lib/share";
import { teamHeadline } from "@/lib/teamHeadline";
import { teamLeagueLabel } from "@/lib/teamLeagueLabel";
import { describeTeamRoute } from "@/lib/teamRouteSport";
import {
  unresolvedCardCopy,
} from "@/lib/unresolvedCardCopy";
import {
  unresolvedShareCopy,
  type ResolutionFailure,
} from "@/lib/unresolvedShareMeta";

/**
 * The slice of `TeamPageResponse` a share card reads.
 *
 * Declared rather than imported whole so a test can build one by hand: the
 * live payload is 22kB and 24 futures deep, and a fixture that size is one
 * nobody reads.
 */
export interface TeamShareSource {
  team: TeamPageTeam;
  futures?: TeamFutureItem[] | null;
  championship_path?: ChampionshipPathEntry[] | null;
}

/** The payload, or WHY there is none — a 404 and a bad minute are not the same. */
export type TeamLookup =
  | { ok: true; payload: TeamShareSource }
  | { ok: false; failure: ResolutionFailure };

/** Which of the three things the URL turned out to be. */
export type TeamShareVerdict =
  | { kind: "team"; payload: TeamShareSource }
  | { kind: "off-route"; teamName: string; routeSport: string }
  | { kind: "unresolved"; failure: ResolutionFailure };

/**
 * Segments this route will spend a request on.
 *
 * `generateMetadata` and `opengraph-image` both run on every crawl and all
 * three segments are attacker-supplied, so a path that could never name a team
 * page is refused here rather than upstream — the screen `/hub/[competition]`,
 * `/tournaments/[slug]` and `/event/[domain]/[slug]` all apply for the same
 * reason.
 *
 * The shapes are `lib/teamUrls.ts`'s, because that is the function that BUILDS
 * every team link in the app: `slugify` emits `[a-z0-9-]` only, and the league
 * segment is either a curated key (`mlb`, `ncaaf`) or `sport_key` minus its
 * first part, which can carry an underscore (`soccer_usa_mls` -> `usa_mls`).
 */
const TEAM_SEGMENT = /^[a-z0-9][a-z0-9-]{0,63}$/;
const SPORT_SEGMENT = /^[a-z0-9]{1,24}$/;
const LEAGUE_SEGMENT = /^[a-z0-9][a-z0-9_-]{0,31}$/;

export function teamRouteSegmentsAreWellFormed(
  sport: string,
  league: string,
  team: string,
): boolean {
  return (
    SPORT_SEGMENT.test(sport) &&
    LEAGUE_SEGMENT.test(league) &&
    TEAM_SEGMENT.test(team)
  );
}

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * The team payload, or why not. THE ONE IMPURE EXPORT IN THIS FILE.
 *
 * `/hub/[competition]` keeps a byte-identical copy of its fetcher in its layout
 * AND in its image route, with a paragraph either side explaining that the two
 * cannot share a render. They cannot share a RENDER; they can share a function,
 * and one of the two copies is the one that gets edited. So this lives here,
 * beside the classifier it feeds, and the two routes below call it.
 *
 * `revalidate: 300` is the hub's, for its reason: the picture and the words
 * then come from the same five-minute window rather than drifting apart.
 *
 * A metadata request must never take a page down over a card, so every failure
 * path returns a `failure` rather than throwing — and only a 404 is allowed to
 * mean "there is no such team" (gotcha #53).
 */
export async function fetchTeamShare(
  sport: string,
  league: string,
  team: string,
): Promise<TeamLookup> {
  if (!teamRouteSegmentsAreWellFormed(sport, league, team)) {
    return { ok: false, failure: "not-found" };
  }

  try {
    const response = await fetch(
      `${API_URL}/api/teams/${encodeURIComponent(team)}`,
      { next: { revalidate: 300 } },
    );
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, payload: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

/**
 * A lookup plus the route it arrived on, reduced to one of three cases.
 *
 * The off-route test is `describeTeamRoute`'s, unchanged — the same function
 * the page renders its refusal from, so the card and the page cannot disagree
 * about whether this URL is a football page. An ABSENT measurement (a team with
 * no `sport_key`) is not off-route: a guard that refuses when it cannot measure
 * is one somebody switches off wholesale.
 */
export function classifyTeamShare(
  lookup: TeamLookup,
  routeSport: string,
): TeamShareVerdict {
  if (!lookup.ok) return { kind: "unresolved", failure: lookup.failure };

  const { team } = lookup.payload;
  // A 200 with no name is not a team. The page needs a name for every sentence
  // it writes, and inventing one from the slug is how "Ny Yankees" gets onto
  // the most public screen we have.
  if (!team?.name?.trim()) return { kind: "unresolved", failure: "not-found" };

  if (describeTeamRoute(team, routeSport).offRoute) {
    return { kind: "off-route", teamName: team.name.trim(), routeSport };
  }

  return { kind: "team", payload: lookup.payload };
}

export interface TeamShareCopy {
  /** The `<title>`. Carries its own suffix — see the note in the builder. */
  title: string;
  /** The `<meta name="description">` and the unfurl's second line. */
  description: string;
  /** The og:/twitter: headline. */
  socialTitle: string;
}

/**
 * The sentence about a URL that resolved to a team in another sport.
 *
 * Word-for-word the page's own refusal (`page.tsx`, #5852: "We don't have a
 * {sport} page for {team.name}."), because a reader who taps the preview lands
 * on that page and should not be told two different things in two seconds.
 */
export function offRouteSentence(teamName: string, routeSport: string): string {
  return `We don't have a ${routeSport} page for ${teamName}`;
}

/**
 * What the tab, the description and the preview headline say.
 *
 * ⚠️ The resolved title carries "— Bain Luck" ITSELF and is not passed through
 * `withSiteSuffix`. Measured on production 2026-09-13 12:34Z: `/hub/tennis`
 * renders `Tennis | Bain Luck` — the root template fires — while this route
 * renders `Boston Red Sox MLB Odds & Probabilities — Bain Luck`, with no `|`
 * suffix appended, because every ancestor under `app/sport/` sets a plain
 * string title. So the template does NOT reach here and a title written to
 * rely on it would ship bare. This is the shape the route already had; the
 * change is that the NAME and the LEAGUE are the payload's rather than a
 * title-cased slug and an upper-cased route segment.
 *
 * That second half is #5847 one surface over: the page stopped shouting a
 * fragment of its own sport key in January, but the `<title>` and the og:title
 * still did — a K League 1 team's tab read "KOREA_KLEAGUE1", because
 * `league.toUpperCase()` is the route segment and nothing else.
 */
export function buildTeamShareCopy(
  verdict: TeamShareVerdict,
  routeLeague: string,
): TeamShareCopy {
  if (verdict.kind === "unresolved") {
    const { title, description } = unresolvedShareCopy("team", verdict.failure);
    return { title, description, socialTitle: withSiteSuffix(title) };
  }

  if (verdict.kind === "off-route") {
    const sentence = offRouteSentence(verdict.teamName, verdict.routeSport);
    return {
      title: sentence,
      description: `${sentence}. See the sports and leagues we do cover, as probabilities.`,
      socialTitle: withSiteSuffix(sentence),
    };
  }

  const { team } = verdict.payload;
  const league = teamLeagueLabel(team, routeLeague);
  const headline = teamHeadline(
    verdict.payload.championship_path,
    verdict.payload.futures,
  );
  const probability = headline
    ? formatShareProbability(headline.probability)
    : null;

  return {
    title: `${team.name} ${league} Odds & Probabilities — Bain Luck`,
    description:
      headline && probability
        ? `${team.name}: ${probability} to win the ${headline.label.toLowerCase()}. Live win probabilities, upcoming ${league} schedule, and season futures.`
        : `${team.name} win probabilities, upcoming ${league} schedule, and season futures.`,
    socialTitle: `${team.name} — ${league} — Bain Luck`,
  };
}

/**
 * The second line of the card: what a fan would say about the team's season.
 *
 * Record first, then the standing. The standing's rule is the page's, and it is
 * #4732's: `conf_rank` is the only field that genuinely scopes to a conference,
 * and `div_rank` must NAME the division it counted — printing a division place
 * as "in conference" put four NBA teams at "#1 in conference" at once.
 *
 * Everything here is a fact about the world (a record, a place in a table), not
 * a fact about our inventory, which is the line notice 34 draws.
 */
export function teamSeasonLine(team: TeamPageTeam): string | null {
  const standings = (team.standings ?? {}) as Record<string, unknown>;
  const text = (key: string): string | null => {
    const value = standings[key];
    if (value === null || value === undefined) return "";
    const s = String(value).trim();
    return s.length > 0 ? s : "";
  };

  const parts: string[] = [];
  const record = team.record?.trim();
  if (record) parts.push(record);

  const conf = text("conf_rank");
  const div = text("div_rank");
  if (conf) {
    parts.push(`#${conf} in conference`);
  } else if (div) {
    const division = text("division");
    parts.push(division ? `#${div} in ${division}` : `#${div} in division`);
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * Is this colour readable as ink and as a rule on a white card?
 *
 * The accent is not decoration here: `UnfurlCard` draws the eyebrow pill's
 * TEXT and border in it, on white. A team's `primary_color` is whatever the
 * provider stored, and the payload really does carry white
 * (`secondary_color: "#ffffff"` on the Celtics), so an unchecked hand-off puts
 * an invisible pill on a share card.
 *
 * WCAG 2.1 relative luminance, and the 3:1 bar for large text and graphical
 * objects — `1.05 / (L + 0.05) >= 3` reduces to `L <= 0.3`. Measured against
 * the two teams in this module's header: `#0d2b56` (Red Sox navy) L=0.026 and
 * `#008348` (Celtics green) L=0.167 both pass; `#ffffff` L=1 and `#ffd700`
 * L=0.70 do not and fall back to the sport's colour.
 */
export function readableAccent(
  hex: string | null | undefined,
  fallback: string,
): string {
  const luminance = relativeLuminance(hex);
  if (luminance === null || luminance > 0.3) return fallback;
  return normalizeHex(hex as string) as string;
}

/** `#abc` and `#aabbcc`, lower-cased. Anything else is not a colour we will draw. */
function normalizeHex(hex: string): string | null {
  const value = hex.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(value)) return value;
  if (/^#[0-9a-f]{3}$/.test(value)) {
    return `#${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`;
  }
  return null;
}

function relativeLuminance(hex: string | null | undefined): number | null {
  if (!hex) return null;
  const value = normalizeHex(hex);
  if (!value) return null;

  const channel = (pair: string): number => {
    const srgb = parseInt(pair, 16) / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };

  return (
    0.2126 * channel(value.slice(1, 3)) +
    0.7152 * channel(value.slice(3, 5)) +
    0.0722 * channel(value.slice(5, 7))
  );
}

/**
 * Everything `UnfurlCard` needs to draw a team link.
 *
 * ═══ ONE ROW, AND IT IS THE PAGE'S OWN HERO ═══
 *
 * A hub card carries no rows because a hub names a COLLECTION. A team names one
 * question — does this team win it — so it gets the hero row `/futures/[id]`
 * uses, carrying the number `teamHeadline` gives the page's own hero. The row's
 * NAME is the question ("Championship", "Conference", "Division") because the
 * contender is the title.
 *
 * A team with no season price gets no row, and the quiet shape says its name,
 * its record and nothing it cannot prove. That is a real state and not an edge
 * case: `championship_path` was empty for BOTH teams measured on 2026-09-13,
 * and the number came from the futures fallback each time.
 *
 * ═══ WHAT MAKES TWO TEAM CARDS DIFFERENT PICTURES ═══
 *
 * The name, the record, the number — and the team's own colour, the same
 * `primary_color` the page draws its hero's left border in, when it is dark
 * enough to read on white. The sport's colour is the floor, taken from the
 * ROUTE segment rather than the payload, because that is the one signal
 * available before the fetch and the only one still available when it fails.
 */
export function teamCardCopy(
  verdict: TeamShareVerdict,
  routeSport: string,
  routeLeague: string,
): UnfurlCardProps {
  if (verdict.kind === "unresolved") {
    return unresolvedCardCopy("team", verdict.failure);
  }

  const sportAccent = accentFor(routeSport);

  if (verdict.kind === "off-route") {
    return {
      eyebrow: "Team",
      title: offRouteSentence(verdict.teamName, verdict.routeSport),
      subtitle: "This team is on Bain Luck under a different sport.",
      rows: [],
      accent: sportAccent,
    };
  }

  const { team } = verdict.payload;
  const headline = teamHeadline(
    verdict.payload.championship_path,
    verdict.payload.futures,
  );
  const probability = headline
    ? formatShareProbability(headline.probability)
    : null;

  return {
    eyebrow: teamLeagueLabel(team, routeLeague),
    title: team.name,
    subtitle: teamSeasonLine(team),
    rows:
      headline && probability
        ? [
            {
              name: headline.label,
              probability,
              fraction: headline.probability,
            },
          ]
        : [],
    accent: readableAccent(team.primary_color, sportAccent),
  };
}
