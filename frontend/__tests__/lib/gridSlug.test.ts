// L2-162: sport_key → championship-grid slug resolution.
import { sportKeyToGridSlug } from "../../lib/gridSlug";

describe("sportKeyToGridSlug", () => {
  test("maps the four major US leagues", () => {
    expect(sportKeyToGridSlug("baseball_mlb")).toBe("mlb");
    expect(sportKeyToGridSlug("basketball_nba")).toBe("nba");
    expect(sportKeyToGridSlug("americanfootball_nfl")).toBe("nfl");
    expect(sportKeyToGridSlug("icehockey_nhl")).toBe("nhl");
  });

  test("maps soccer/UCL whose slug differs from the key suffix", () => {
    expect(sportKeyToGridSlug("soccer_uefa_champs_league")).toBe("champions-league");
    expect(sportKeyToGridSlug("soccer_spain_la_liga")).toBe("la-liga");
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
