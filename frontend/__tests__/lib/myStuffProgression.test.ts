/**
 * ux/1070 item 3 — the pennant is a rung on the ladder.
 *
 * Alex's 7:00am shop: the Red Sox block showed Division and World Series and
 * nothing in between. The AL pennant market was attached the whole time
 * (Kalshi 274 "American League Champion", outcome "Boston" → team 10709,
 * 14.5%); the classifier below is what could not see it, so it fell out of the
 * ladder and into a flat list that is capped at ten rows.
 *
 * These are the market names PRODUCTION actually carries for the Red Sox
 * (measured 2026-09-04 via /api/admin/db-query), not invented strings.
 */
import {
  PROGRESSION_STAGES,
  detectMarketTypeFromName,
  extractMarketType,
} from "@/lib/myStuffProgression";

describe("detectMarketTypeFromName — the pennant rung", () => {
  it.each([
    ["American League Champion", "conference_winner"],
    ["MLB: 2026 American League Champion", "conference_winner"],
    ["National League Champion", "conference_winner"],
    ["AL Pennant Winner", "conference_winner"],
    ["NL Champion", "conference_winner"],
  ])("classifies %s as %s", (name, expected) => {
    expect(detectMarketTypeFromName(name)).toBe(expected);
  });

  it("puts the pennant between the division and the trophy", () => {
    const division = PROGRESSION_STAGES["division_winner"]!.order;
    const pennant = PROGRESSION_STAGES["conference_winner"]!.order;
    const trophy = PROGRESSION_STAGES["championship"]!.order;
    expect(division).toBeLessThan(pennant);
    expect(pennant).toBeLessThan(trophy);
  });
});

describe("detectMarketTypeFromName — the rungs it must NOT take", () => {
  it.each([
    // Division names both an `al` and a `champion`; it is still a division.
    ["AL East Division Winner", "division_winner"],
    ["MLB: 2026 AL East Champion", "division_winner"],
    // Player awards are not stages of a team's season.
    ["AL MVP Winner?", null],
    ["AL Cy Young Winner?", null],
    ["AL Rookie of the Year Winner?", null],
    ["AL Hank Aaron Award Winner?", null],
    // Season-shape markets are not rungs either.
    ["MLB: 2026 Regular Season Win Totals", null],
    ["Pro Baseball Best Record", null],
    ["Pro Baseball Worst Record", null],
    ["Pro Baseball Hits Leader", null],
  ])("classifies %s as %s", (name, expected) => {
    expect(detectMarketTypeFromName(name)).toBe(expected);
  });
});

describe("detectMarketTypeFromName — the trophy, in both vocabularies", () => {
  it.each([
    ["MLB World Series Champion 2026", "championship"],
    ["MLB World Series Winner", "championship"],
    // Kalshi's own name for the same trophy — without it the top rung could
    // only ever be the Polymarket copy, and the Kalshi price was invisible.
    ["Pro Baseball Champion", "championship"],
    ["Pro Football Champion", "championship"],
  ])("classifies %s as %s", (name, expected) => {
    expect(detectMarketTypeFromName(name)).toBe(expected);
  });

  it("keeps make-playoffs ahead of everything", () => {
    expect(detectMarketTypeFromName("Pro Baseball Playoff Qualifiers")).toBe(null);
    expect(detectMarketTypeFromName("MLB: Team to make playoffs")).toBe("make_playoffs");
  });
});

describe("extractMarketType", () => {
  it("reads the type segment of a canonical key", () => {
    expect(extractMarketType("baseball:MLB:championship:2028")).toBe("championship");
    expect(extractMarketType("baseball::division_winner:2026")).toBe("division_winner");
  });

  it("is null for an absent or short key", () => {
    expect(extractMarketType(null)).toBe(null);
    expect(extractMarketType("baseball:MLB")).toBe(null);
  });
});
