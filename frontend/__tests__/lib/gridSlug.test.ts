// L2-162 & #11492: sport_key ↔ championship-grid slug resolution.
import { gridSlugToSportKey, sportKeyToGridSlug } from "../../lib/gridSlug";

describe("sportKeyToGridSlug", () => {
  test("maps the four major US leagues", () => {
    expect(sportKeyToGridSlug("baseball_mlb")).toBe("mlb");
    expect(sportKeyToGridSlug("basketball_nba")).toBe("nba");
    expect(sportKeyToGridSlug("americanfootball_nfl")).toBe("nfl");
    expect(sportKeyToGridSlug("icehockey_nhl")).toBe("nhl");
  });

  test("maps soccer/UCL and college women's basketball whose slugs differ from the key suffix", () => {
    expect(sportKeyToGridSlug("soccer_uefa_champs_league")).toBe("champions-league");
    expect(sportKeyToGridSlug("soccer_spain_la_liga")).toBe("la-liga");
    expect(sportKeyToGridSlug("basketball_wncaab")).toBe("ncaa-women-basketball");
  });

  test("strips season-phase suffixes before mapping (the Red Sox live case)", () => {
    expect(sportKeyToGridSlug("baseball_mlb_preseason")).toBe("mlb");
    expect(sportKeyToGridSlug("basketball_nba_postseason")).toBe("nba");
    expect(sportKeyToGridSlug("americanfootball_nfl_regular_season")).toBe("nfl");
    expect(sportKeyToGridSlug("icehockey_nhl_playoffs")).toBe("nhl");
  });

  test("falls back to stripping the provider prefix for unknown keys", () => {
    expect(sportKeyToGridSlug("cricket_ipl")).toBe("ipl");
  });

  test("returns null for empty/nullish input", () => {
    expect(sportKeyToGridSlug(null)).toBeNull();
    expect(sportKeyToGridSlug(undefined)).toBeNull();
    expect(sportKeyToGridSlug("")).toBeNull();
  });
});

describe("gridSlugToSportKey (#11492)", () => {
  test("maps all 13 team-sport championship-grid slugs and route aliases to their canonical sport_key", () => {
    expect(gridSlugToSportKey("mlb")).toBe("baseball_mlb");
    expect(gridSlugToSportKey("nba")).toBe("basketball_nba");
    expect(gridSlugToSportKey("nfl")).toBe("americanfootball_nfl");
    expect(gridSlugToSportKey("nhl")).toBe("icehockey_nhl");
    expect(gridSlugToSportKey("wnba")).toBe("basketball_wnba");
    expect(gridSlugToSportKey("ncaa-basketball")).toBe("basketball_ncaab");
    expect(gridSlugToSportKey("ncaab")).toBe("basketball_ncaab");
    expect(gridSlugToSportKey("ncaa-women-basketball")).toBe("basketball_wncaab");
    expect(gridSlugToSportKey("wncaab")).toBe("basketball_wncaab");
    expect(gridSlugToSportKey("ncaa-football")).toBe("americanfootball_ncaaf");
    expect(gridSlugToSportKey("ncaaf")).toBe("americanfootball_ncaaf");
    expect(gridSlugToSportKey("epl")).toBe("soccer_epl");
    expect(gridSlugToSportKey("la-liga")).toBe("soccer_spain_la_liga");
    expect(gridSlugToSportKey("champions-league")).toBe("soccer_uefa_champs_league");
    expect(gridSlugToSportKey("ucl")).toBe("soccer_uefa_champs_league");
    expect(gridSlugToSportKey("bundesliga")).toBe("soccer_germany_bundesliga");
    expect(gridSlugToSportKey("mls")).toBe("soccer_usa_mls");
  });

  test("returns null for non-team slugs (golf) and empty inputs", () => {
    expect(gridSlugToSportKey("golf")).toBeNull();
    expect(gridSlugToSportKey(null)).toBeNull();
    expect(gridSlugToSportKey(undefined)).toBeNull();
    expect(gridSlugToSportKey("")).toBeNull();
  });
});
