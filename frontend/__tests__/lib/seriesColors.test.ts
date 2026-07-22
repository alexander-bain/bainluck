import {
  SERIES_COLORS,
  SERIES_COLORS_GOLD,
  SERIES_COLORS_GREEN,
  ELIMINATED_SERIES_COLOR,
  COMBINED_SERIES_COLOR,
} from "../../lib/seriesColors";

describe("seriesColors registry (L2-157 class E — index/outcome palette half)", () => {
  const HEX = /^#[0-9a-fA-F]{6}$/;

  // The flagship FuturesChart field kernel is the canonicalization anchor: its
  // first 8 index colors MUST survive verbatim so the event-page hero charts
  // (RaceToTitle / WinnerEvolution / SettledPath) do not shift.
  test("indices 0-7 match the flagship FuturesChart palette", () => {
    expect(SERIES_COLORS.slice(0, 8)).toEqual([
      "#2563eb", "#dc2626", "#16a34a", "#9333ea",
      "#ea580c", "#0891b2", "#be185d", "#4f46e5",
    ]);
  });

  test("the palette carries 10-competitor headroom with distinct hexes", () => {
    expect(SERIES_COLORS.length).toBeGreaterThanOrEqual(10);
    expect(new Set(SERIES_COLORS).size).toBe(SERIES_COLORS.length);
  });

  test("every palette entry is a valid 6-digit hex", () => {
    for (const palette of [SERIES_COLORS, SERIES_COLORS_GOLD, SERIES_COLORS_GREEN]) {
      for (const hex of palette) expect(hex).toMatch(HEX);
    }
    expect(ELIMINATED_SERIES_COLOR).toMatch(HEX);
    expect(COMBINED_SERIES_COLOR).toMatch(HEX);
  });

  // The two headroom hues (8, 9) are reused from the old EVOLUTION palette, not
  // newly invented — canonicalization discipline (no new colors).
  test("headroom hues are pre-existing palette values, not new colors", () => {
    expect(SERIES_COLORS[8]).toBe("#92400e");
    expect(SERIES_COLORS[9]).toBe("#065f46");
  });

  test("gold and green leader themes lead with their signature color", () => {
    expect(SERIES_COLORS_GOLD[0]).toBe("#D4AF37"); // leader gold
    expect(SERIES_COLORS_GREEN[0]).toBe("#006747"); // Augusta green
  });

  // The eliminated grey and the combined-line neutral must not collide with any
  // live contender color, or a knocked-out / summed line masquerades as a field.
  test("eliminated + combined neutrals are outside the live palette", () => {
    expect(SERIES_COLORS).not.toContain(ELIMINATED_SERIES_COLOR);
    expect(SERIES_COLORS).not.toContain(COMBINED_SERIES_COLOR);
  });
});
