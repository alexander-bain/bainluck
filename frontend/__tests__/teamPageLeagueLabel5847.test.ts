/**
 * #5847 — the team page shouted a fragment of its own sport key at the reader.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sport/soccer/korea_kleague1/team/sangju-sangmu-fc`, production, 390px,
 * 2026-09-13 08:0xZ (`artifacts/ux-1231/live-team-sangju-390.png`):
 *
 *     Home / KOREA KLEAGUE1 / Sangju Sangmu FC
 *
 * The server's own `team.sport_name` for that key is "K League 1". The page
 * never asked for it.
 *
 * ═══ MECHANISM ═══
 *
 * The page computed its league label TWICE — once for `document.title`, once
 * for the breadcrumb and the JSON-LD — and both called
 * `getLeagueDisplay(team.sport_key)`, which is the KEY PARSER: for a key the
 * curated `LEAGUE_DISPLAY` map has no entry for, it splits on `_`, drops the
 * category and uppercases the rest. `getSportLabel(key, servedName)` is the
 * canonical three-source rule for exactly this (#4350 / #4358 / #4381) and is
 * already what `FeedCard`, `EventCard`, `/sports/[key]`, the search sport chips
 * and the event OG image use. The team page was the one call site holding a
 * served name that did not.
 *
 * Reach, measured on production rather than modelled — `teams JOIN sports`
 * where `teams.slug IS NOT NULL`, 108 sport rows / 5,913 slugged teams: 52 rows
 * and **1,601 team pages** print a key parse while the server carries a brand.
 * `LEAGUE_DISPLAY` holds no soccer key at all, so every soccer league is in it;
 * MLS alone is 690 teams reading "USA MLS".
 *
 * ═══ THE CASE THE OLD CODE WAS PROTECTING, AND WHY IT SURVIVES ═══
 *
 * The parser was not chosen by accident: the deleted comment says `sport_name`
 * carried stale season-phase copy ("MLB Preseason", L2-158 Item 3). That case
 * lands on `getSportLabel`'s CURATED branch — `baseball_mlb` is in the map — so
 * it still answers "MLB" whatever the server says. Part 1's third block is that
 * regression, pinned, because a fix that reintroduced "MLB Preseason" would be
 * a worse bug than the one being fixed.
 *
 * ═══ WHY THE DEFECT IS PINNED ON A SYNTHETIC KEY ═══
 *
 * The obvious red check is `getLeagueDisplay("soccer_korea_kleague1") ===
 * "KOREA KLEAGUE1"`. That assertion goes false the day somebody curates that
 * key by hand — a correct improvement that would red this suite for no reason.
 * So the parser's shouting is pinned on a key nobody will ever curate, and the
 * real specimens are asserted only on what they must NOT say.
 */

import { teamLeagueLabel } from "../lib/teamLeagueLabel";
import { getLeagueDisplay, hasCuratedLeagueName } from "../lib/sportCategories";

import fs from "node:fs";
import path from "node:path";

const ROOT = path.join(__dirname, "..");
const TEAM_PAGE = "app/sport/[sport]/[league]/team/[team]/page.tsx";

// ---------------------------------------------------------------------------
// Part 1 — the rule, on the real helper
// ---------------------------------------------------------------------------

describe("#5847 the label rule", () => {
  it("prefers the server's brand over a key parse (the production specimen)", () => {
    const label = teamLeagueLabel(
      { sport_key: "soccer_korea_kleague1", sport_name: "K League 1" },
      "korea_kleague1",
    );
    expect(label).toBe("K League 1");
    // The string that was on the page. Asserted as a NEGATIVE so this arm
    // cannot be satisfied by a helper that merely returns something.
    expect(label).not.toBe("KOREA KLEAGUE1");
  });

  it("does the same for the largest affected league, MLS (690 team pages)", () => {
    expect(
      teamLeagueLabel({ sport_key: "soccer_usa_mls", sport_name: "MLS" }, "mls"),
    ).toBe("MLS");
  });

  it("keeps the curated word when the server's copy is stale (L2-158, 'MLB Preseason')", () => {
    expect(
      teamLeagueLabel(
        { sport_key: "baseball_mlb", sport_name: "MLB Preseason" },
        "mlb",
      ),
    ).toBe("MLB");
  });

  it("falls back to the key parse when the server stores the key as the name", () => {
    // The 15 rows that have no brand at all. `mma_other` must not reach a
    // reader raw, and must not read "OTHER" either (#4247).
    expect(
      teamLeagueLabel({ sport_key: "mma_other", sport_name: "mma_other" }, "other"),
    ).toBe("Other MMA");
  });

  it("falls back to the served name, then the route segment, with no sport_key", () => {
    expect(
      teamLeagueLabel({ sport_key: null, sport_name: "K League 1" }, "korea_kleague1"),
    ).toBe("K League 1");
    expect(teamLeagueLabel({ sport_key: null, sport_name: null }, "ncaaf")).toBe(
      "NCAAF",
    );
    expect(teamLeagueLabel(undefined, "ncaaf")).toBe("NCAAF");
  });

  it("changes nothing for a curated league — Hawaii's NCAAF page is untouched", () => {
    // The control. `americanfootball_ncaaf` is curated, so old and new agree;
    // a fix that moved this string would have moved pages it had no business on.
    expect(hasCuratedLeagueName("americanfootball_ncaaf")).toBe(true);
    expect(
      teamLeagueLabel(
        { sport_key: "americanfootball_ncaaf", sport_name: "NCAAF" },
        "ncaaf",
      ),
    ).toBe(getLeagueDisplay("americanfootball_ncaaf"));
  });

  it("the parser this routes around really does shout (non-vacuity)", () => {
    // A key nobody will ever curate, so this arm cannot go stale.
    const synthetic = "soccer_neverland_top_flight";
    expect(hasCuratedLeagueName(synthetic)).toBe(false);
    expect(getLeagueDisplay(synthetic)).toBe("NEVERLAND TOP FLIGHT");
    // ...and the helper routes around it when a brand is in hand.
    expect(
      teamLeagueLabel({ sport_key: synthetic, sport_name: "Neverland Top Flight" }, "x"),
    ).toBe("Neverland Top Flight");
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the page half, by source scan
//
// The page is a client component whose three fetches run on mount; its sibling
// guards (#5652, #5669) reach it the same way and say so. The scan asserts BOTH
// directions — a guard that only proved `getLeagueDisplay` was gone would also
// pass on a page that stopped printing the label at all (gotcha #43).
// ---------------------------------------------------------------------------

describe("#5847 the page reads the rule", () => {
  const src = fs.readFileSync(path.join(ROOT, TEAM_PAGE), "utf8");

  it("imports the helper and no longer reaches for the key parser", () => {
    expect(src).toContain('import { teamLeagueLabel } from "@/lib/teamLeagueLabel"');
    expect(src).not.toContain("getLeagueDisplay");
  });

  it("uses it for BOTH the document title and the rendered label", () => {
    expect(src).toContain("teamLeagueLabel(data.team, league)");
    expect(src).toContain("const leagueLabel = teamLeagueLabel(team, league);");
    // Exactly two call sites: the two that existed. A third would be a new
    // surface nobody reasoned about.
    expect(src.match(/teamLeagueLabel\(/g) ?? []).toHaveLength(2);
  });

  it("still prints the label in all three places it reaches a reader or a crawler", () => {
    // Breadcrumb.
    expect(src).toContain("{leagueLabel}");
    // JSON-LD `SportsTeam.sport` and `memberOf.name`.
    expect(src).toContain("sport: leagueLabel");
    expect(src).toContain("name: leagueLabel");
    // Document title.
    expect(src).toContain("document.title = `${data.team.name} —");
  });
});
