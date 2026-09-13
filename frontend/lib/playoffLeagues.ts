/**
 * THE LEAGUES THAT HAVE A CHAMPIONSHIP GRID.
 *
 * Lifted verbatim out of `app/playoffs/[sport]/page.tsx`, which is a
 * `"use client"` file — so the registry was unreachable from anything that runs
 * on the server. `opengraph-image.tsx` runs on the edge and `layout.tsx` runs
 * during `generateMetadata`; importing a client page from either drags the
 * whole component graph and does not build.
 *
 * It is lifted rather than copied for the reason `lib/sportCategories.ts`
 * exists: the alternative is the same fourteen rows in three files, and the
 * fifteenth league is the one that gets two of them. The page imports these
 * back and its rendering is unchanged.
 *
 * ═══ THE ONE FIELD THAT IS NEW ═══
 *
 * `sport`. The slug is a LEAGUE (`nfl`, `mls`, `ncaa-women-basketball`) and
 * `CATEGORY_ACCENT` in `components/og/UnfurlCard` is keyed on SPORTS, so
 * `accentFor("nfl")` is the default green — which would draw all fourteen
 * brackets in one colour, the exact defect `hubCardCopy` was written to stop
 * one route over. The mapping is stated here, beside the league it belongs to,
 * rather than as a second table somewhere else.
 */

export interface LeagueInfo {
  slug: string;
  label: string;
  emoji: string;
  group: "us" | "college" | "soccer" | "other";
  conferences?: string[];
  /** The accent key — a SPORT, not this league. See the header. */
  sport: string;
}

export const PLAYOFF_LEAGUES: LeagueInfo[] = [
  { slug: "nba", label: "NBA", emoji: "\u{1F3C0}", group: "us", conferences: ["Eastern", "Western"], sport: "basketball" },
  { slug: "nfl", label: "NFL", emoji: "\u{1F3C8}", group: "us", conferences: ["AFC", "NFC"], sport: "football" },
  { slug: "mlb", label: "MLB", emoji: "\u26BE", group: "us", conferences: ["American League", "National League"], sport: "baseball" },
  { slug: "nhl", label: "NHL", emoji: "\u{1F3D2}", group: "us", conferences: ["Eastern", "Western"], sport: "hockey" },
  { slug: "wnba", label: "WNBA", emoji: "\u{1F3C0}", group: "us", sport: "basketball" },
  { slug: "ncaa-basketball", label: "NCAAB", emoji: "\u{1F3C0}", group: "college", sport: "basketball" },
  { slug: "ncaa-women-basketball", label: "WNCAAB", emoji: "\u{1F3C0}", group: "college", sport: "basketball" },
  { slug: "ncaa-football", label: "NCAAF", emoji: "\u{1F3C8}", group: "college", sport: "football" },
  { slug: "epl", label: "EPL", emoji: "\u26BD", group: "soccer", sport: "soccer" },
  { slug: "la-liga", label: "La Liga", emoji: "\u26BD", group: "soccer", sport: "soccer" },
  { slug: "champions-league", label: "UCL", emoji: "\u26BD", group: "soccer", sport: "soccer" },
  { slug: "bundesliga", label: "Bundesliga", emoji: "\u26BD", group: "soccer", sport: "soccer" },
  { slug: "mls", label: "MLS", emoji: "\u26BD", group: "soccer", sport: "soccer" },
  { slug: "golf", label: "Golf", emoji: "\u26F3", group: "other", sport: "golf" },
];

/**
 * Every slug the route answers to, aliases included.
 *
 * The five aliases below are addresses readers and links already use, and they
 * resolve to the same bracket — so they must resolve to the same CARD too. A
 * card that says "this bracket isn't on Bain Luck" for `/playoffs/ncaab` while
 * the page renders the NCAAB grid is worse than the generic card it replaces.
 */
export const PLAYOFF_LEAGUE_MAP: Record<string, LeagueInfo> = Object.fromEntries(
  PLAYOFF_LEAGUES.map((l) => [l.slug, l])
);
PLAYOFF_LEAGUE_MAP["ucl"] = PLAYOFF_LEAGUE_MAP["champions-league"];
PLAYOFF_LEAGUE_MAP["ncaab"] = PLAYOFF_LEAGUE_MAP["ncaa-basketball"];
PLAYOFF_LEAGUE_MAP["ncaaf"] = PLAYOFF_LEAGUE_MAP["ncaa-football"];
PLAYOFF_LEAGUE_MAP["wncaab"] = PLAYOFF_LEAGUE_MAP["ncaa-women-basketball"];
PLAYOFF_LEAGUE_MAP["ncaa"] = PLAYOFF_LEAGUE_MAP["ncaa-basketball"];

/** The bracket at this slug, or nothing. Lower-cased, as the page does. */
export function playoffLeagueFor(slug: string): LeagueInfo | undefined {
  return PLAYOFF_LEAGUE_MAP[slug.toLowerCase()];
}

/**
 * The page's own `<h1>`, as a function, so the share card can be the same string.
 *
 * Golf is the special case the page already carries: `/playoffs/golf` renders a
 * tournament schedule rather than a bracket, so "Golf Championship Grid" would
 * name something the reader does not find there.
 */
export function playoffDisplayName(league: LeagueInfo): string {
  return league.slug === "golf" ? "Golf Tournament Odds" : `${league.label} Championship Grid`;
}
