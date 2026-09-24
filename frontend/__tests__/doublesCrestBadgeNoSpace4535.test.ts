/**
 * #4535 — a doubles-pair crest badge never paints a space.
 *
 * `teamCrestBadge` took three CHARACTERS of the whole pair, so a first surname
 * of one or two letters cut into the space: production's "An Lin / Yi Yang"
 * painted `AN `, two glyphs and a hole, on 25 distinct names (measured
 * 2026-09-09). It now counts letters and digits across the space, the rule the
 * iPhone's `glyphs(ofLabel:)` already applies, and #3110's pinned value — three
 * letters of the first surname — is untouched wherever the surname has them.
 */
import { teamCrestBadge, shippableCrestBadge, discoverCrestBadge } from "@/lib/teamShortName";

// The six names #4535 lists, with what they painted before this change.
const SPECIMENS: Array<[string, string, string]> = [
  ["An Lin / Yi Yang", "AN ", "ANL"],
  ["Da Rosa Castro / Dinis Silva", "DA ", "DAR"],
  ["De Koning / Stevic", "DE ", "DEK"],
  ["Du Pree / Van Emst", "DU ", "DUP"],
  ["El Sayed / Fouad", "EL ", "ELS"],
  ["Ho / Jebens", "HO ", "HOJ"],
];

describe("#4535 a doubles pair's crest badge", () => {
  it.each(SPECIMENS)("%s is three real glyphs, not %j", (name, before, after) => {
    const badge = teamCrestBadge(name);
    expect(badge).toBe(after);
    expect(badge).not.toBe(before);
    expect(badge).not.toMatch(/\s/);
    expect(badge).toHaveLength(3);
  });

  it("keeps #3110's badge for every pair whose first surname has three letters", () => {
    // Control: the pinned values move for nobody the defect did not touch.
    expect(teamCrestBadge("Siniakova / Townsend")).toBe("SIN");
    expect(teamCrestBadge("Hunter / Krawczyk")).toBe("HUN");
    expect(teamCrestBadge("Milutinovic / Van de Peer")).toBe("MIL");
    expect(teamCrestBadge("Cervantes / Molchanov", "tennis_atp")).toBe("CER");
  });

  it("keeps a non-ASCII first letter rather than dropping it", () => {
    // Swift's `isLetter` counts "Č"; an ASCII-only filter would print `ILI`.
    expect(teamCrestBadge("Čilić / Dodig")).toBe("ČIL");
  });

  it("drops punctuation the same way it drops the space", () => {
    expect(teamCrestBadge("O'Connell / Purcell")).toBe("OCO");
  });

  it("reaches the Discover tile and the event hero unchanged", () => {
    for (const [name, , after] of SPECIMENS) {
      expect(discoverCrestBadge(name)).toBe(after);
      expect(shippableCrestBadge(name)).toBe(after);
    }
  });

  it("does not touch a name with an unspaced slash, which is one entity", () => {
    // "W-B/Scranton Penguins" is a club, not a pair (`isDoublesPair` is false),
    // so it keeps its last-word badge; read as a pair it would print `WBS`.
    expect(teamCrestBadge("W-B/Scranton Penguins")).toBe("PEN");
  });
});
