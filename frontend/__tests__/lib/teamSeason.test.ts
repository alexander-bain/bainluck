// L2-169: team-page season chips — bind #242's payload season fields (contract,
// not live data: the team endpoint 500s under #1197) to display strings.
import {
  seasonChipText,
  pathSeason,
  journeyRangeLabel,
} from "../../lib/teamSeason";
import type { ChampionshipPathEntry, SeasonDescriptor } from "../../lib/api";

function descriptor(overrides: Partial<SeasonDescriptor>): SeasonDescriptor {
  return {
    league: "nba",
    season: "2026-27",
    phase: "regular_season",
    label: "2026-27 · Regular season",
    ...overrides,
  };
}

function entry(overrides: Partial<ChampionshipPathEntry>): ChampionshipPathEntry {
  return {
    tier: 1,
    label: "Championship",
    market_name: "NBA Champion",
    market_id: 10,
    probability: 0.2,
    rank: null,
    movement: null,
    season: "2026-27",
    ...overrides,
  };
}

describe("seasonChipText", () => {
  test("returns the season string from the descriptor", () => {
    expect(seasonChipText(descriptor({ season: "2026-27" }))).toBe("2026-27");
  });

  test("null/blank season → null (chip hidden, never a blank pill)", () => {
    expect(seasonChipText(descriptor({ season: null }))).toBeNull();
    expect(seasonChipText(descriptor({ season: "   " }))).toBeNull();
    expect(seasonChipText(null)).toBeNull();
    expect(seasonChipText(undefined)).toBeNull();
  });

  test("trims surrounding whitespace", () => {
    expect(seasonChipText(descriptor({ season: " 2026 " }))).toBe("2026");
  });
});

describe("pathSeason", () => {
  test("returns the common season when every entry agrees", () => {
    expect(
      pathSeason([
        entry({ tier: 4, season: "2026-27" }),
        entry({ tier: 2, season: "2026-27" }),
        entry({ tier: 1, season: "2026-27" }),
      ]),
    ).toBe("2026-27");
  });

  test("ignores entries missing a season, using the agreed rest", () => {
    expect(
      pathSeason([
        entry({ tier: 4, season: null }),
        entry({ tier: 1, season: "2026" }),
      ]),
    ).toBe("2026");
  });

  test("null when seasons disagree (data artifact — assert nothing)", () => {
    expect(
      pathSeason([
        entry({ tier: 2, season: "2025-26" }),
        entry({ tier: 1, season: "2026-27" }),
      ]),
    ).toBeNull();
  });

  test("null for empty / all-seasonless input", () => {
    expect(pathSeason([])).toBeNull();
    expect(pathSeason(null)).toBeNull();
    expect(pathSeason(undefined)).toBeNull();
    expect(pathSeason([entry({ season: null }), entry({ season: undefined })])).toBeNull();
  });
});

describe("journeyRangeLabel", () => {
  test("prefixes the season when present", () => {
    expect(journeyRangeLabel("2026-27")).toBe(
      "2026-27 · Opening day → today · fixed 0–100% scale (tap Zoom for detail)",
    );
  });

  test("degrades to the plain range without a season", () => {
    const plain = "Opening day → today · fixed 0–100% scale (tap Zoom for detail)";
    expect(journeyRangeLabel(null)).toBe(plain);
    expect(journeyRangeLabel(undefined)).toBe(plain);
    expect(journeyRangeLabel("  ")).toBe(plain);
  });
});
