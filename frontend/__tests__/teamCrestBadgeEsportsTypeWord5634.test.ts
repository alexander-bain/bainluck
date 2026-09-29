/**
 * #5634 — an esports crest is not the organisation's TYPE.
 *
 * WHAT THE READER SAW: `/events/15319232`, G2 Esports v Paper Rex, 390px,
 * 2026-09-29, after the label fix went live — the hero read "G2 Esports" in
 * full under a crest reading **`ESP`**, while the Bigger Picture tile for the
 * same team read `G2`.
 *
 * Every name below was read verbatim from production `events` (esports, all
 * 925 names of 60 days, 2026-09-29). Over that population 158 badges were a
 * type word and 8 still are, every one a name that really starts "Gam"/"Tea"
 * ("GamerLegion", "GAM Esports"). No other badge moves.
 */

import { discoverCrestBadge, shippableCrestBadge, teamCrestBadge } from "@/lib/teamShortName";

const ESPORTS = "esports";

describe("#5634 — an esports crest drops the type word", () => {
  it.each([
    ["G2 Esports", "ESP", "G2"],
    ["Top Esports", "ESP", "TOP"],
    ["FURIA Esports", "ESP", "FUR"],
    ["SK Gaming", "GAM", "SK"],
    ["JD Gaming", "GAM", "JD"],
    ["Bilibili Gaming", "GAM", "BIL"],
    ["Team WE", "TEA", "WE"],
    ["BOMBA Team", "TEA", "BOM"],
    ["Insiders Esport", "ESP", "INS"],
    ["INTZ e-Sports", "E-S", "INT"],
  ])("%s: %s → %s", (name, before, after) => {
    expect(teamCrestBadge(name)).toBe(before);
    expect(teamCrestBadge(name, ESPORTS)).toBe(after);
    expect(teamCrestBadge(name, "esports_valorant")).toBe(after);
    // The two surfaces that read it: the event hero and the Discover tile.
    expect(shippableCrestBadge(name, ESPORTS)).toBe(after);
    expect(discoverCrestBadge(name, ESPORTS)).toBe(after);
  });

  // An initials badge that counts the type word as one letter is often the
  // org's own tag. Dropping every type word regressed exactly these.
  it.each([
    ["Hanwha Life Esports", "HLE"],
    ["Berlin International Gaming", "BIG"],
    ["Team Secret Whales", "TSW"],
    ["Black Dragons e-Sports", "BDS"],
    ["E WIE EINFACH E-SPORTS", "WES"],
  ])("%s keeps %s", (name, badge) => {
    expect(teamCrestBadge(name)).toBe(badge);
    expect(teamCrestBadge(name, ESPORTS)).toBe(badge);
  });

  it.each([
    // No type word: untouched to the character.
    ["Paper Rex", "REX"],
    ["Team Liquid", "LIQ"],
    ["Natus Vincere", "VIN"],
    // A name that really starts with the letters keeps them.
    ["GamerLegion", "GAM"],
    ["GAM Esports", "GAM"],
  ])("%s stays %s", (name, badge) => {
    expect(teamCrestBadge(name, ESPORTS)).toBe(badge);
  });

  it("other sports and a missing sport keep the shipped badge (control)", () => {
    for (const sport of [undefined, null, "soccer_epl", "basketball_nba", "soccer_esports_cup"]) {
      expect(teamCrestBadge("G2 Esports", sport)).toBe("ESP");
      expect(teamCrestBadge("SK Gaming", sport)).toBe("GAM");
    }
    expect(teamCrestBadge("Boston Celtics", "basketball_nba")).toBe("CEL");
  });
});
