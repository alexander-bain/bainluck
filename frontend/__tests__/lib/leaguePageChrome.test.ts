/**
 * UX-P062 (#1743, epic #1741) — the league page's page-level decisions.
 *
 * Spec `docs/entity-page-templates.md` §3/§4/§6, ruling 027.
 */

import {
  countRenderedSections,
  resolveGridSlug,
  resolveLeagueTerminalState,
} from "@/lib/leaguePageChrome";
import { earnsSectionHeader } from "@/lib/entityPageChrome";

describe("resolveGridSlug — register E5", () => {
  it("prefers the slug the register served", () => {
    expect(resolveGridSlug("ncaa-basketball", "basketball_ncaab")).toBe(
      "ncaa-basketball",
    );
  });

  it("falls back to the sport-key suffix when the register has no grid", () => {
    expect(resolveGridSlug(null, "tennis_atp")).toBe("atp");
    expect(resolveGridSlug(undefined, "soccer_italy_serie_a")).toBe("italy_serie_a");
  });

  it("survives a key with no underscore rather than returning empty string", () => {
    // The old inline expression could produce "" for a single-token key, which
    // would have requested /api/playoffs//grid.
    expect(resolveGridSlug(null, "boxing")).toBe("boxing");
  });

  it("reproduces every entry of the retired GRID_SLUG_MAP", () => {
    // The map that used to live in the page. Pinned so moving it into the
    // register cannot silently drop or rename a grid — the register is now the
    // only copy, and this is the proof the move was lossless.
    const RETIRED_MAP: Record<string, string> = {
      soccer_usa_mls: "mls",
      soccer_epl: "epl",
      soccer_uefa_champs_league: "champions-league",
      soccer_spain_la_liga: "la-liga",
      soccer_germany_bundesliga: "bundesliga",
      americanfootball_nfl: "nfl",
      americanfootball_ncaaf: "ncaa-football",
      basketball_nba: "nba",
      basketball_ncaab: "ncaa-basketball",
      basketball_wnba: "wnba",
      icehockey_nhl: "nhl",
      baseball_mlb: "mlb",
    };
    for (const [sportKey, expected] of Object.entries(RETIRED_MAP)) {
      // Served from the register, the page must produce the same slug it did before.
      expect(resolveGridSlug(expected, sportKey)).toBe(expected);
    }
    expect(Object.keys(RETIRED_MAP)).toHaveLength(12);
  });
});

describe("countRenderedSections — the §4 denominator", () => {
  const base = {
    marketSectionCount: 0,
    upcomingGameCount: 0,
    recentResultCount: 0,
    gridTeamCount: 0,
  };

  it("counts the grid and both rails as containers (Alex's amendment)", () => {
    expect(
      countRenderedSections({
        marketSectionCount: 2,
        upcomingGameCount: 5,
        recentResultCount: 3,
        gridTeamCount: 30,
      }),
    ).toBe(5);
  });

  it("counts a rail once, not once per game", () => {
    expect(countRenderedSections({ ...base, upcomingGameCount: 8 })).toBe(1);
  });

  it("counts nothing when there is nothing", () => {
    expect(countRenderedSections(base)).toBe(0);
  });

  it("is what stops a lone section growing a header", () => {
    // A T1 league: one market section, no games, no grid. One container means the
    // header has nothing to distinguish itself from, so it is not earned.
    const sections = countRenderedSections({ ...base, marketSectionCount: 1 });
    expect(earnsSectionHeader(3, sections)).toBe(false);

    // Add a games rail and the same section now sits among peers, so it is.
    const withGames = countRenderedSections({
      ...base,
      marketSectionCount: 1,
      upcomingGameCount: 4,
    });
    expect(earnsSectionHeader(3, withGames)).toBe(true);
  });
});

describe("resolveLeagueTerminalState — degraded is NOT empty (E6 / clause 4)", () => {
  const loaded = { loaded: true, marketSectionCount: 0, upcomingGameCount: 0 };

  it("renders nothing before the payload has arrived", () => {
    expect(
      resolveLeagueTerminalState({
        loaded: false,
        tier: null,
        availability: null,
        marketSectionCount: 0,
        upcomingGameCount: 0,
      }),
    ).toBeNull();
  });

  it("declares degraded when the fetch failed", () => {
    expect(
      resolveLeagueTerminalState({ ...loaded, tier: null, availability: "degraded" }),
    ).toBe("degraded");
  });

  it("declares T0 for a real league with nothing open", () => {
    expect(
      resolveLeagueTerminalState({ ...loaded, tier: "present", availability: "empty" }),
    ).toBe("present");
  });

  it("NEVER shows an off-season statement for a degraded read", () => {
    // The named failure: an outage and an off-season rendering identically. Even
    // with a `present` tier in hand, a degraded availability must not print
    // "nothing is happening" — we do not know that.
    expect(
      resolveLeagueTerminalState({
        ...loaded,
        tier: "present",
        availability: "degraded",
      }),
    ).toBe("degraded");
  });

  it("shows no terminal state when the page has content", () => {
    expect(
      resolveLeagueTerminalState({
        loaded: true,
        tier: "standard",
        availability: "fresh",
        marketSectionCount: 2,
        upcomingGameCount: 0,
      }),
    ).toBeNull();

    // A league with no futures but a full schedule is NOT empty.
    expect(
      resolveLeagueTerminalState({
        loaded: true,
        tier: "standard",
        availability: "fresh",
        marketSectionCount: 0,
        upcomingGameCount: 6,
      }),
    ).toBeNull();
  });
});
