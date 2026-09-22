import {
  getCategoryForLeague,
  getLeagueDisplay,
  hasCuratedLeagueName,
} from "@/lib/sportCategories";

/**
 * ═══ #8093: THE RAIL AT THE FOOT OF A GAME PAGE ASKED FOR A SPORT ═══
 *
 * A WNBA game page's `MORE BASKETBALL · 4` rail dealt `NBA: 2027 Champion`,
 * `NBA: 2026 NBA Cup Winner` and `NBA Championship Winner` above the one WNBA
 * market in it — three of four cards the men's league, on a women's fixture,
 * under a heading that says it is more of what the reader is looking at.
 * Photographed on production 2026-09-22 by lane1/602 on `/events/15316933`
 * and `/events/15310072`.
 *
 * The page asked `RelatedByTag` for `sport:${getCategoryForLeague(sport).key}`,
 * and that helper collapses every basketball league to one category key. So the
 * request said `sport:basketball` and the feed answered with whatever ranks
 * highest under it, which is the NBA. Nothing in the chain ever mentioned the
 * league. The identical collapse sits under soccer, tennis and football.
 *
 * ## Three things measured before this was written
 *
 * **1. `league:` is a real, SQL-pushable tag namespace.** `feed.py`'s
 * `_STATIC_TAG_NAMESPACES` lists it beside `sport`, and the two AND rather than
 * OR: `?tags=["sport:basketball"]` served 9 items, `?tags=["sport:basketball",
 * "league:wnba"]` served 4 and every one of them WNBA. The narrowing is not
 * inert.
 *
 * **2. The league tag ALONE is not the fix.** Concepts and tournaments are
 * filtered on the `sport:` arm only (`concept_filter_for_tags`), so
 * `?tags=["league:wnba"]` re-admitted `UFC 332: Silva vs Cong` and
 * `FedEx Open de France`. Both tags travel together or neither does.
 *
 * **3. There is no new league map here, deliberately.** `/api/events/{id}`
 * already serves `event_tags` carrying `league:wnba`, minted by
 * `event_taxonomy.compute_event_tags` from the same `_SPORT_KEY_TO_LEAGUE` the
 * feed filters on. Re-deriving that map in the client would be a second copy
 * free to drift from the one the server matches against; taking the producer's
 * own tag cannot. When the payload carries no `league:` tag the rail is exactly
 * what it is today.
 *
 * ## Why it falls back instead of simply narrowing
 *
 * Measured at the rail's own fetch size (`limit + 5` = 9) over 14 leagues, wide
 * count → league-narrowed count:
 *
 *   nfl 9→9 · ncaaf 9→9 · nba 9→9 · mlb 9→9 · nhl 9→9 · mls 9→9 · ufc 9→9 ·
 *   pga 9→8 · epl 9→7 · **wnba 9→4** · ncaab 9→1 · la_liga 9→2 ·
 *   **champions_league 9→0** · **tennis us_open 9→0**
 *
 * A blanket narrow would take the whole rail off a Champions League tie and off
 * every Grand Slam match page — marquee surfaces, for a defect neither of them
 * has. So the rail asks league-first and falls back to *exactly today's query*
 * when the league query matches nothing at all: strictly no worse than today
 * anywhere, strictly better on every league that has content of its own.
 *
 * The heading travels with the scope that was actually served — `More WNBA`
 * when the league query answered, `More Basketball` when the fallback did — so
 * a rail can never name a narrower thing than the cards under it.
 */
export interface RelatedRailQuery {
  /** The tags the rail asks for first. */
  tags: string[];
  /** Today's sport-only query, used only when `tags` matches nothing. */
  fallbackTags?: string[];
  /** The heading over `tags`' results. */
  title: string;
  /** The heading over `fallbackTags`' results. */
  fallbackTitle?: string;
}

/**
 * The tag query and heading for the related rail at the foot of a game page.
 *
 * Returns `null` when the sport key maps to no category at all, which is the
 * same "draw nothing" the call site has always taken.
 */
export function relatedRailQuery(
  sportKey: string | null | undefined,
  eventTags: string[] | null | undefined,
): RelatedRailQuery | null {
  if (!sportKey) return null;
  const category = getCategoryForLeague(sportKey);
  if (!category) return null;

  const sportTag = `sport:${category.key}`;
  const categoryTitle = `More ${category.name}`;

  /* The producer's own tag, not a re-derivation. `find` rather than a filter:
     `compute_event_tags` adds at most one `league:` tag per event, and a second
     one would be a taxonomy defect rather than something for this rail to
     reconcile. */
  const leagueTag = (eventTags ?? []).find((tag) => tag.startsWith("league:"));
  if (!leagueTag) {
    return { tags: [sportTag], title: categoryTitle };
  }

  /* `getLeagueDisplay` answers for every key it is given — a curated word when
     it has one, a `split("_")` parse when it does not (`hasCuratedLeagueName`
     exists precisely because the two are indistinguishable downstream). A
     heading is reader-facing copy, so it takes the curated word or the category
     name, never `GERMANY LIGA3`. The CARDS are narrowed either way: what a
     reader can be called is independent of what they should be shown. */
  const title = hasCuratedLeagueName(sportKey)
    ? `More ${getLeagueDisplay(sportKey)}`
    : categoryTitle;

  return {
    tags: [sportTag, leagueTag],
    fallbackTags: [sportTag],
    title,
    fallbackTitle: categoryTitle,
  };
}
