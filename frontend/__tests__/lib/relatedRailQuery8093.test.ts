/**
 * #8093 — THE RAIL AT THE FOOT OF A GAME PAGE ASKS FOR ITS LEAGUE.
 *
 * Production, 2026-09-22, `/events/15316933` (Connecticut Sun @ Washington
 * Mystics) at phone width: the rail read `MORE BASKETBALL · 4` and dealt
 * `NBA: 2027 Champion`, `NBA: 2026 NBA Cup Winner`, `WNBA: 2026 Champion`,
 * `NBA Championship Winner`. Three of four cards the men's league, on a
 * women's fixture, under a heading that says it is more of what the reader is
 * looking at.
 *
 * The page asked for `sport:${getCategoryForLeague(event.sport).key}`, and that
 * helper collapses `basketball_wnba` to `basketball`. The league was never in
 * the question, so it could not be in the answer.
 *
 * ## What each assertion is holding down
 *
 * The acceptance on the issue asks for "a guard that pins the league→tag
 * mapping so a future category collapse cannot silently reopen it". The
 * mapping this pins is deliberately NOT a new client-side league table — the
 * defect being guarded is a re-derivation drifting from the server's, so the
 * fix takes the `league:` tag out of the event's own `event_tags` (minted by
 * `event_taxonomy.compute_event_tags`) and the guard pins *that* it does so.
 *
 * - **The narrowed query is both tags, never the league alone.** Measured on
 *   production: `?tags=["league:wnba"]` re-admits `UFC 332: Silva vs Cong` and
 *   `FedEx Open de France`, because concepts and tournaments are filtered on
 *   the `sport:` arm only. A future simplification to "just ask for the league"
 *   reads as tidier and is the old bug wearing different clothes.
 * - **The STRAWMAN.** The pre-fix query is stated here explicitly, and it is
 *   the same array the fix now uses as its *fallback*. Without this, a change
 *   that quietly promoted the fallback to the primary query would pass every
 *   other assertion in this file.
 * - **The inertness control.** An event whose payload carries no `league:` tag
 *   gets byte-for-byte today's query and today's heading, and no fallback — the
 *   one shape in which this fix must do nothing at all.
 * - **The two halves are independent.** A league with no curated display word
 *   keeps the category heading (a reader must never be shown `GERMANY LIGA3`)
 *   while its CARDS are still narrowed. Conflating "what we can call this" with
 *   "what we should show" is how a copy rule silently becomes a content rule.
 */

import { relatedRailQuery } from "@/lib/relatedRailQuery";

/** The WNBA fixture the issue was filed on, as `/api/events/15316933` serves
 *  it — the `event_tags` array is verbatim from that payload. */
const WNBA_EVENT_TAGS = [
  "audience:national_interest",
  "class:pro_major",
  "competitive_structure:head_to_head",
  "gender:women",
  "importance:regular_season",
  "league:wnba",
  "level:professional",
  "narrative:david_vs_goliath",
  "sport:basketball",
  "stakes:playoff_race",
  "status:scheduled",
  "tier:2",
  "timing:national_tv",
];

describe("#8093 — the related rail asks for the event's league", () => {
  it("narrows a WNBA game page to its own league, and says so", () => {
    const rail = relatedRailQuery("basketball_wnba", WNBA_EVENT_TAGS);

    expect(rail).not.toBeNull();
    // BOTH tags. The sport arm is what filters concepts and tournaments; the
    // league arm is what filters the futures. Dropping either reopens a defect.
    expect(rail!.tags).toEqual(["sport:basketball", "league:wnba"]);
    expect(rail!.title).toBe("More WNBA");
  });

  it("does the mirror: an NBA page asks for the NBA", () => {
    const rail = relatedRailQuery("basketball_nba", [
      "league:nba",
      "sport:basketball",
      "tier:1",
    ]);

    expect(rail!.tags).toEqual(["sport:basketball", "league:nba"]);
    expect(rail!.title).toBe("More NBA");
  });

  /* THE STRAWMAN. This is the query that shipped the defect. It is asserted as
     a string so that the relationship between it and `fallbackTags` is visible:
     the fix did not delete the old behaviour, it demoted it. */
  it("keeps the pre-fix query as the FALLBACK, not as the question", () => {
    const rail = relatedRailQuery("basketball_wnba", WNBA_EVENT_TAGS);

    const PRE_FIX_QUERY = ["sport:basketball"];
    expect(rail!.fallbackTags).toEqual(PRE_FIX_QUERY);
    expect(rail!.tags).not.toEqual(PRE_FIX_QUERY);

    // And the fallback's heading is the fallback's scope. A rail that drew from
    // all of basketball may not be headed `More WNBA`.
    expect(rail!.fallbackTitle).toBe("More Basketball");
    expect(rail!.title).not.toBe(rail!.fallbackTitle);
  });

  /* THE INERTNESS CONTROL — the shape in which this change must do nothing. */
  it("leaves an event with no league tag exactly as it was, with no fallback", () => {
    const rail = relatedRailQuery("basketball_wnba", [
      "sport:basketball",
      "status:scheduled",
    ]);

    expect(rail!.tags).toEqual(["sport:basketball"]);
    expect(rail!.title).toBe("More Basketball");
    // No second query to fall back TO, because the first one is already the
    // wide one. A fallback here would be the same request twice.
    expect(rail!.fallbackTags).toBeUndefined();
    expect(rail!.fallbackTitle).toBeUndefined();
  });

  it("treats a missing event_tags array as no league tag", () => {
    expect(relatedRailQuery("basketball_wnba", undefined)!.tags).toEqual([
      "sport:basketball",
    ]);
    expect(relatedRailQuery("basketball_wnba", null)!.tags).toEqual([
      "sport:basketball",
    ]);
    expect(relatedRailQuery("basketball_wnba", [])!.tags).toEqual([
      "sport:basketball",
    ]);
  });

  it("draws nothing at all when the sport key maps to no category", () => {
    expect(relatedRailQuery("", WNBA_EVENT_TAGS)).toBeNull();
    expect(relatedRailQuery(null, WNBA_EVENT_TAGS)).toBeNull();
    expect(relatedRailQuery(undefined, undefined)).toBeNull();
  });

  /* The heading rule and the content rule are separate rules. A key with no
     curated word still narrows its cards — it just does not get named. */
  it("narrows the cards even where it cannot name the league", () => {
    const rail = relatedRailQuery("soccer_germany_liga3", [
      "sport:soccer",
      "league:liga3",
    ]);

    expect(rail!.tags).toEqual(["sport:soccer", "league:liga3"]);
    expect(rail!.title).toBe("More Soccer");
    expect(rail!.title).not.toContain("LIGA3");
  });

  /* The soccer and tennis leagues the production measurement showed returning
     ZERO under a narrowed query. They must still be narrowed — the empty case
     is handled by the fallback in the component, not by refusing to narrow
     here, because "this league has content today" is not a thing a pure
     function can know. */
  it("narrows the leagues measured empty, and hands them a fallback", () => {
    const ucl = relatedRailQuery("soccer_uefa_champs_league", [
      "sport:soccer",
      "league:champions_league",
    ]);
    expect(ucl!.tags).toEqual(["sport:soccer", "league:champions_league"]);
    expect(ucl!.fallbackTags).toEqual(["sport:soccer"]);

    const slam = relatedRailQuery("tennis_us_open", [
      "sport:tennis",
      "league:us_open",
    ]);
    expect(slam!.tags).toEqual(["sport:tennis", "league:us_open"]);
    expect(slam!.fallbackTags).toEqual(["sport:tennis"]);
  });
});
