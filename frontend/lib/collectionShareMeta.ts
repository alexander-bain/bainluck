/**
 * THE COPY THE FOUR *COLLECTION* ROUTES UNFURL WITH — THE LAST OF CHECK 8.
 *
 * `/categories/[slug]`, `/playoffs/[sport]`, `/sport/[sport]` and
 * `/sport/[sport]/[league]` were the four entries left on
 * `SHARES_THE_SITE_CARD` in `__tests__/shareUnfurl.test.ts`: routes that say
 * something about themselves and then sit that sentence next to the house card.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * Read with a crawler UA on 2026-09-13 at 13:4xZ:
 *
 *   /categories/politics  <title>        Bain Luck — Prediction Market Discovery
 *                         og:title       Bain Luck — Prediction Market Discovery
 *                         og:description See what the world thinks will happen. …
 *                         og:image       https://www.bainluck.com/opengraph-image
 *   /playoffs/nfl         byte-identical in all four.
 *
 * Both layouts called `selfCanonical()` and nothing else, so `canonical` and
 * `og:url` were their own and every WORD was the root's. A pasted
 * `/categories/politics` link previewed as the front door — #5877's defect, two
 * routes over.
 *
 *   /sport/football       og:title       Football - BainLuck
 *                         twitter:title  Bain Luck — Prediction Market Discovery
 *   /sport/football/nfl   og:title       NFL - BainLuck
 *                         twitter:title  Bain Luck — Prediction Market Discovery
 *
 * These two got their `openGraph` right and declared no `twitter` block at all,
 * so X — where a league link is most likely to be pasted — inherited the root's
 * title and the root's card. That is the split `unresolvedShareMeta.ts`
 * documents for `/events/[id]`, here in the LIVE branch rather than the dead one.
 *
 * All five reads named one picture, `https://www.bainluck.com/opengraph-image`.
 *
 * ═══ WHY ONE MODULE FOR FOUR ROUTES ═══
 *
 * They are one shape: each names a COLLECTION — a category's markets, a sport's
 * leagues, a league's season, a bracket — so none of them has a single question
 * to headline and none of them draws rows. That is `hubCardCopy`'s argument
 * (`lib/hubShareMeta.ts`, "THIS CARD HAS NO ROWS, AND THAT IS THE DESIGN") and
 * it transfers verbatim: picking one of a category's markets to quote would be
 * arbitrary, and quoting the COUNT would put a fact about our inventory on the
 * most public screen we have (notice 34).
 *
 * Four copies of that reasoning is how four voices happen. One module, four
 * functions, one card builder.
 *
 * ═══ WHY NONE OF THEM FETCHES ═══
 *
 * ⚠️ Unlike every sibling in this family, these four resolve their name from a
 * LOCAL table — `getCategoryByKey`, `PLAYOFF_LEAGUE_MAP`, `LEAGUE_DISPLAY_NAMES`
 * — because that is what the PAGES themselves do. `/categories/[slug]` renders
 * `getCategoryByKey(slug)?.name ?? toTitleCaseAcronymSafe(slug)` as its `<h1>`
 * and `/playoffs/[sport]` renders `playoffDisplayName`. Deriving the card from
 * the same call is what makes the picture and the page agree by construction
 * rather than by review — and it means no network on a path every crawl hits.
 *
 * The two `/sport` routes' `<h1>`s come from the API (`hierarchy.name`,
 * `league.name`) while their titles already came from these maps; that is the
 * state this ship inherited and does not change. Named residue.
 *
 * ═══ THE ONE NOT-FOUND CLAIM, AND WHY ONLY ONE ═══
 *
 * `playoffShare` returns `null` for a slug with no bracket, and the route says
 * so — because that absence is DECIDABLE here: the page itself renders "League
 * Not Found" and a picker for exactly those slugs. The other three fall back to
 * a title-cased segment and claim nothing, because on those routes the page
 * still renders real content for a segment these tables do not list, and
 * "this isn't on Bain Luck" would be false (gotcha #53, in the shape it takes
 * when the oracle is a local table rather than a 404).
 */

import {
  accentFor,
  type UnfurlCardProps,
} from "@/components/og/UnfurlCard";
import { playoffDisplayName, playoffLeagueFor } from "@/lib/playoffLeagues";
import { getCategoryByKey } from "@/lib/sportCategories";
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";

export interface CollectionShare {
  /**
   * The subject's own name — the card's headline, and the stem of the social
   * title. "Politics", "Football", "NFL", "NFL Championship Grid".
   */
  name: string;
  /**
   * The `<title>`, WITHOUT a site suffix.
   *
   * ⚠️ Whether a suffix is appended is NOT uniform across these four routes and
   * cannot be made so from here. `app/sport/layout.tsx` sets a plain-string
   * `title`, which REPLACES the root's `%s | Bain Luck` template for everything
   * beneath it, so `/sport/[sport]` and `/sport/[sport]/[league]` must carry the
   * brand themselves; `/categories/**` and `/playoffs/**` have no such ancestor
   * and get the template. Each layout applies `withSiteSuffix` or does not, and
   * `__tests__/collectionUnfurlCard.test.tsx` reads the ancestor layouts and
   * asserts the split rather than trusting anyone to remember it.
   */
  pageTitle: string;
  /** One sentence. Serves as `description` AND as the card's second line. */
  description: string;
  /** The card's pill: the reader's word for the kind of thing this is. */
  eyebrow: string;
  /** The stripe and the pill's colour — what makes 40 categories 40 pictures. */
  accent: string;
}

/**
 * League display names, moved here from `app/sport/[sport]/[league]/layout.tsx`.
 *
 * Moved rather than copied: the layout's `<title>` and the card's headline are
 * the same string, and the day they come from two tables is the day one of them
 * says "NFL" while the other says "Nfl".
 */
export const LEAGUE_DISPLAY_NAMES: Record<string, string> = {
  pga: "PGA Tour",
  dpworld: "DP World Tour",
  lpga: "LPGA",
  liv: "LIV Golf",
  kft: "Korn Ferry Tour",
  nba: "NBA",
  wnba: "WNBA",
  ncaab: "NCAA Men's Basketball",
  wncaab: "NCAA Women's Basketball",
  nfl: "NFL",
  ncaaf: "NCAA Football",
  cfl: "CFL",
  ufl: "UFL",
  nhl: "NHL",
  mlb: "MLB",
  ncaa: "College Baseball",
  epl: "Premier League",
  mls: "MLS",
  laliga: "La Liga",
  bundesliga: "Bundesliga",
  seriea: "Serie A",
  ligue1: "Ligue 1",
  ucl: "Champions League",
  atp: "ATP Tour",
  wta: "WTA Tour",
  ufc: "UFC",
};

/**
 * The league's name, or the segment upper-cased.
 *
 * The fallback is the layout's own, kept: an unlisted segment is a league we
 * route to and have not named here, not a league that does not exist, so the
 * honest floor is what the reader typed.
 */
export function leagueDisplayName(league: string): string {
  return LEAGUE_DISPLAY_NAMES[league.toLowerCase()] ?? league.toUpperCase();
}

/**
 * `/categories/<slug>` — every market the classifier put in one category.
 *
 * The name is `getCategoryByKey`'s, which is the call the PAGE makes for its
 * `<h1>`, down to the same `toTitleCaseAcronymSafe` fallback. 26 of the 48
 * counted categories are not in `SPORT_CATEGORIES` at all — `table_tennis`, the
 * largest on the site, among them — so that fallback is the common path here,
 * not an edge case.
 */
export function categoryShare(slug: string): CollectionShare {
  const name = getCategoryByKey(slug)?.name ?? toTitleCaseAcronymSafe(slug) ?? slug;

  return {
    name,
    pageTitle: `${name} Odds & Probabilities`,
    description: `Every ${name} market we track, translated into plain probabilities.`,
    eyebrow: "Category",
    accent: accentFor(slug),
  };
}

/** `/sport/<sport>` — one sport's leagues and their championship grids. */
export function sportShare(sport: string): CollectionShare {
  const name = getCategoryByKey(sport)?.name ?? toTitleCaseAcronymSafe(sport) ?? sport;

  return {
    name,
    pageTitle: `${name} Odds & Probabilities`,
    description: `Every ${name} league we cover, with win probabilities and championship odds as one clean number.`,
    eyebrow: "Sport",
    // The sport segment, which is what `CATEGORY_ACCENT` is keyed on.
    accent: accentFor(sport),
  };
}

/** `/sport/<sport>/<league>` — one league's schedule, odds and grid. */
export function leagueShare(sport: string, league: string): CollectionShare {
  const name = leagueDisplayName(league);

  return {
    name,
    pageTitle: `${name} Odds & Schedule`,
    description: `${name} schedule, win probabilities and championship odds, as one clean number.`,
    eyebrow: "League",
    // The SPORT segment, not the league: `CATEGORY_ACCENT` has no `nfl` key, so
    // keying on the league would draw every league in the default green.
    accent: accentFor(sport),
  };
}

/**
 * `/playoffs/<slug>` — a bracket, or `null` where there is none.
 *
 * `null` is a real answer and not a failure to look: the page renders "League
 * Not Found" and a picker for exactly the slugs this returns `null` for, so the
 * route may honestly say the bracket is not here. See the header.
 */
export function playoffShare(slug: string): CollectionShare | null {
  const league = playoffLeagueFor(slug);
  if (!league) return null;

  const name = playoffDisplayName(league);

  return {
    name,
    pageTitle: name,
    description:
      league.slug === "golf"
        ? "Every tournament on the schedule, with each golfer's chance to win."
        : `Every team's road to the ${league.label} title, as one clean probability.`,
    eyebrow: "Playoffs",
    accent: accentFor(league.sport),
  };
}

/**
 * The card, from the words.
 *
 * Everything the route would otherwise decide for itself lives here, for the
 * reason `lib/hubShareMeta.ts` records: when `/hub/[competition]` left the
 * accent in its `opengraph-image.tsx`, a mutant replacing `accentFor(segment)`
 * with `accentFor(null)` — all five hubs one colour, the very defect that ship
 * removed — survived the whole suite, because no test could reach a decision
 * the route still owned. Each of these four routes is now a spread.
 *
 * `rows` is empty and `note` absent by construction. `UnfurlCard`'s
 * empty-`rows` shape (`SUBTITLE_MAX_QUIET`, no bar, no footer note) is drawn
 * for exactly this.
 */
export function collectionCardCopy(share: CollectionShare): UnfurlCardProps {
  return {
    eyebrow: share.eyebrow,
    title: share.name,
    subtitle: share.description,
    rows: [],
    accent: share.accent,
  };
}
