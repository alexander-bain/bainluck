/**
 * #5852 — tapping a college football team's name opened a basketball team page.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * Production, 390px, 2026-09-13 08:1xZ. Event 15304882, NCAAF, New Mexico State
 * at Hawai'i. Tap the home team in the hero, land on
 * `/sport/football/ncaaf/team/hawaii-rainbow-warriors`, and the page renders
 * (`artifacts/ux-1231/hawaii-team-390.png`):
 *
 *     Home / WNCAAB / Hawai'i Rainbow Warriors
 *     SEASON JOURNEY — NCAAB Championship Winner
 *
 * A women's basketball team page, reached from a men's college football game.
 * HTTP 200, no error, no football anywhere on it.
 *
 * ═══ MECHANISM ═══
 *
 * The route reads only `params.team` and calls `GET /api/teams/{slug}`, which
 * resolves BY SLUG ALONE — the `sport` and `league` segments are decoration.
 * `buildTeamPageUrl` derives the slug by slugifying the team's NAME, so a team
 * with no slug of its own sends the reader to whichever team owns that string.
 * The NCAAF Hawai'i row has `slug = null`; the WNCAAB row of the same name has
 * `slug = "hawaii-rainbow-warriors"`.
 *
 * Slug collisions are NOT the cause — measured, 0 slugs are owned by more than
 * one sport. A slugless team's derived URL is simply indistinguishable from a
 * different team's real slug.
 *
 * ═══ WHY FAMILY AND NOT THE FULL KEY ═══
 *
 * Census, production: 2,478 slugless team rows whose derived URL resolves to
 * another team. It splits 282 / 2,196. The big half is tennis, where the slug
 * lands on the same PLAYER filed under a different tournament — a page about
 * the right person, which it would be a regression to refuse. Only the FAMILY
 * test separates "wrong tournament row" from "wrong sport", so the tennis case
 * is a named control below and a full-key test is a mutant this suite kills.
 *
 * ═══ WHY IT CANNOT BREAK A WORKING LINK ═══
 *
 * Measured rather than argued: of 11,199 (event, team) pairs in the last 30
 * days, 11,199 are same-family and 0 are not. Every team link in the app is
 * built by `buildTeamPageUrl` from an event's own sport key, so the segment and
 * the team row agree whenever the slug resolved to the team the reader tapped.
 *
 * ═══ ABSENT IS NOT WRONG ═══
 *
 * A team with no `sport_key` yields no verdict and the page renders as before.
 * A guard that refuses when it cannot measure is one somebody switches off
 * wholesale, so the no-measurement cases are pinned as their own arms.
 */

import fs from "node:fs";
import path from "node:path";

import { describeTeamRoute } from "../lib/teamRouteSport";

const ROOT = path.join(__dirname, "..");
const TEAM_PAGE = "app/sport/[sport]/[league]/team/[team]/page.tsx";

// ---------------------------------------------------------------------------
// Part 1 — the verdict, on the real helper
// ---------------------------------------------------------------------------

describe("#5852 the route/sport verdict", () => {
  it("catches the production specimen: NCAAF route, WNCAAB team", () => {
    const v = describeTeamRoute(
      { name: "Hawai'i Rainbow Warriors", sport_key: "basketball_wncaab" },
      "football",
    );
    expect(v.offRoute).toBe(true);
    expect(v.canonicalPath).toBe(
      "/sport/basketball/wncaab/team/hawaii-rainbow-warriors",
    );
    expect(v.familyLabel).toBe("Basketball");
  });

  it("leaves the tennis class alone — same player, different tournament row", () => {
    // The 2,196. `tennis_wta_miami_open` is not in SPORT_KEY_TO_PATH, so this
    // also exercises the key-parse arm of `buildTeamPageUrl`.
    const v = describeTeamRoute(
      { name: "Iga Swiatek", sport_key: "tennis_wta_miami_open" },
      "tennis",
    );
    expect(v.offRoute).toBe(false);
  });

  it("leaves every working page alone", () => {
    expect(
      describeTeamRoute(
        { name: "Jacksonville Jaguars", sport_key: "americanfootball_nfl" },
        "football",
      ).offRoute,
    ).toBe(false);
    expect(
      describeTeamRoute(
        { name: "Boston Red Sox", sport_key: "baseball_mlb" },
        "baseball",
      ).offRoute,
    ).toBe(false);
    // The same university's FOOTBALL row, reached from a football route. This
    // is the page the specimen should have had, and the guard must not eat it.
    expect(
      describeTeamRoute(
        { name: "Hawai'i Rainbow Warriors", sport_key: "americanfootball_ncaaf" },
        "football",
      ).offRoute,
    ).toBe(false);
  });

  it("does not refuse on an ABSENT measurement", () => {
    const noKey = describeTeamRoute(
      { name: "Hawai'i Rainbow Warriors", sport_key: null },
      "football",
    );
    expect(noKey.offRoute).toBe(false);
    expect(noKey.canonicalPath).toBeNull();

    expect(describeTeamRoute(undefined, "football").offRoute).toBe(false);
    expect(
      describeTeamRoute(
        { name: "Hawai'i Rainbow Warriors", sport_key: "basketball_wncaab" },
        "",
      ).offRoute,
    ).toBe(false);
  });

  it("compares the segments, not their spelling", () => {
    expect(
      describeTeamRoute(
        { name: "Jacksonville Jaguars", sport_key: "americanfootball_nfl" },
        "Football",
      ).offRoute,
    ).toBe(false);
    expect(
      describeTeamRoute(
        { name: "Jacksonville Jaguars", sport_key: "americanfootball_nfl" },
        " football ",
      ).offRoute,
    ).toBe(false);
  });

  it("catches an uncurated key too, and only across families", () => {
    const team = { name: "Sangju Sangmu FC", sport_key: "soccer_korea_kleague1" };
    expect(describeTeamRoute(team, "soccer").offRoute).toBe(false);
    expect(describeTeamRoute(team, "football").offRoute).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the page half, by source scan
//
// The page is a client component whose three fetches run on mount; its sibling
// guards (#5652, #5669) reach it the same way. Both directions, so a guard that
// only proved the refusal exists would also pass on a page that refuses
// everything (gotcha #43).
// ---------------------------------------------------------------------------

describe("#5852 the page refuses an off-route team", () => {
  const src = fs.readFileSync(path.join(ROOT, TEAM_PAGE), "utf8");

  it("asks the verdict about the RESOLVED team and the ROUTE's sport", () => {
    expect(src).toContain('import { describeTeamRoute } from "@/lib/teamRouteSport"');
    expect(src).toContain("const route = describeTeamRoute(team, sport);");
    expect(src.match(/describeTeamRoute\(/g) ?? []).toHaveLength(1);
  });

  it("returns early on the verdict, and says what a reader can do instead", () => {
    expect(src).toContain("if (route.offRoute) {");
    expect(src.match(/route\.offRoute/g) ?? []).toHaveLength(1);
    expect(src).toContain("We don&apos;t have a {sport} page for {team.name}.");
    expect(src).toContain("href={route.canonicalPath}");
  });

  it("still renders the real page for every team that is on route", () => {
    // Non-vacuity: the body below the guard is untouched and still present.
    expect(src).toContain("{leagueLabel}");
    expect(src).toContain('"Live & Upcoming"');
    expect(src).toContain('"@type": "SportsTeam"');
  });
});
