import {
  SOURCE_COLORS,
  DEFAULT_SOURCE_COLOR,
  getSourceColor,
  sourceHex,
  canonicalSourceKey,
} from "../../lib/sourceColors";

describe("sourceColors registry (L2-155 class E)", () => {
  // The flagship OddsChart hexes are the canonicalization anchor — the registry
  // MUST carry exactly these so every surface inherits one map, not eight.
  test("canonical hexes match the flagship OddsChart values", () => {
    expect(SOURCE_COLORS.kalshi.hex).toBe("#22c55e");
    expect(SOURCE_COLORS.polymarket.hex).toBe("#3b82f6");
    expect(SOURCE_COLORS.odds_api.hex).toBe("#0f172a"); // the deliberate L2-131 slate
    expect(SOURCE_COLORS.espn.hex).toBe("#f97316");
    expect(SOURCE_COLORS.stat_model.hex).toBe("#8b5cf6");
    expect(SOURCE_COLORS.mlb.hex).toBe("#06b6d4");
    expect(SOURCE_COLORS.datagolf.hex).toBe("#f59e0b");
    expect(SOURCE_COLORS.blend.hex).toBe("#059669");
  });

  test("every entry carries hex/faint/fg/label", () => {
    for (const [key, entry] of Object.entries(SOURCE_COLORS)) {
      expect(entry.hex).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(entry.faint).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(entry.fg).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(entry.label.length).toBeGreaterThan(0);
      // sanity: the key resolves back to itself
      expect(canonicalSourceKey(key)).toBe(key);
    }
  });

  test("the eight primary sources have distinct identity hexes", () => {
    const primary = ["kalshi", "polymarket", "odds_api", "espn", "stat_model", "mlb", "datagolf", "blend"];
    const hexes = primary.map((k) => SOURCE_COLORS[k].hex);
    expect(new Set(hexes).size).toBe(primary.length);
  });

  test("aliases resolve to the canonical key", () => {
    expect(canonicalSourceKey("betting")).toBe("odds_api");
    expect(canonicalSourceKey("fangraphs")).toBe("mlb");
    expect(canonicalSourceKey("datagolf_model")).toBe("datagolf");
    expect(canonicalSourceKey("bainluck")).toBe("blend");
  });

  test("aliases share the canonical source color", () => {
    expect(sourceHex("betting")).toBe(SOURCE_COLORS.odds_api.hex);
    expect(sourceHex("fangraphs")).toBe(SOURCE_COLORS.mlb.hex);
    expect(sourceHex("datagolf_model")).toBe(SOURCE_COLORS.datagolf.hex);
    expect(sourceHex("bainluck")).toBe(SOURCE_COLORS.blend.hex);
  });

  test("lookups are case-insensitive and handle display-name spellings", () => {
    expect(sourceHex("Kalshi")).toBe(SOURCE_COLORS.kalshi.hex);
    expect(sourceHex("Polymarket")).toBe(SOURCE_COLORS.polymarket.hex);
    expect(sourceHex("Odds API")).toBe(SOURCE_COLORS.odds_api.hex);
    expect(sourceHex("Sportsbooks")).toBe(SOURCE_COLORS.odds_api.hex);
  });

  test("unknown sources fall back to the neutral default", () => {
    expect(getSourceColor("nonsense_source")).toEqual(DEFAULT_SOURCE_COLOR);
    expect(sourceHex("")).toBe(DEFAULT_SOURCE_COLOR.hex);
  });

  test("getSourceColor never returns undefined", () => {
    for (const key of ["kalshi", "betting", "MLB", "unknown", ""]) {
      expect(getSourceColor(key)).toBeDefined();
      expect(getSourceColor(key).hex).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });
});
