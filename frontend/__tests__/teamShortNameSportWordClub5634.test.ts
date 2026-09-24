/**
 * #5634 — a club is not the name of its sport.
 *
 * WHAT THE READER SAW: `/events/15292394`, Dubai Basketball v Real Madrid, live
 * EuroLeague, 390px, 2026-09-24 (shopper pass 0040) — the hero named the home
 * side **"Basketball"**, its badge read **"BAS"**, the since-open line read
 * "Basketball 57% → 58%" and the chart axis "↑ BASKETBALL". PR #8391's
 * whole-club rule is soccer-only, so a `basketball_euroleague` row still took
 * the last-word rule.
 *
 * `PRODUCTION_NAMES` is DATA: every `teams.name` on production ending in a
 * sport word, read 2026-09-24 (5 rows), with the sport key each row carries.
 */

import {
  isNonDistinctiveTrailingWord,
  teamCrestBadge,
  teamShortName,
  teamShortNames,
} from "@/lib/teamShortName";

const PRODUCTION_NAMES: ReadonlyArray<[string, string, string]> = [
  ["Dubai Basketball", "basketball_euroleague", "Basketball"],
  ["Paris Basketball", "basketball_euroleague", "Basketball"],
  ["Valencia Basket", "basketball_euroleague", "Basket"],
  ["Modo Hockey", "icehockey_sweden_allsvenskan", "Hockey"],
  ["TUTO Hockey", "icehockey_mestis", "Hockey"],
];

describe("#5634 — a trailing sport word never stands for the club", () => {
  it.each(PRODUCTION_NAMES)(
    "%s keeps its whole name, with or without its sport key",
    (name, sportKey, word) => {
      expect(teamShortName(name, null, sportKey)).toBe(name);
      expect(teamShortName(name)).toBe(name);
      expect(teamShortName(name, null, sportKey)).not.toBe(word);
    },
  );

  it("the two EuroLeague clubs that both printed 'Basketball' are told apart", () => {
    const labels = ["Dubai Basketball", "Paris Basketball"].map((n) =>
      teamShortName(n, null, "basketball_euroleague"),
    );
    expect(new Set(labels).size).toBe(2);
  });

  it("the crest badge is the club's letters, not the sport's", () => {
    expect(teamCrestBadge("Dubai Basketball", "basketball_euroleague")).toBe("DUB");
    expect(teamCrestBadge("Paris Basketball", "basketball_euroleague")).toBe("PAR");
    expect(teamCrestBadge("Valencia Basket", "basketball_euroleague")).toBe("VAL");
    expect(teamCrestBadge("Modo Hockey", "icehockey_sweden_allsvenskan")).toBe("MOD");
    expect(teamCrestBadge("TUTO Hockey", "icehockey_mestis")).toBe("TUT");
  });

  it("the specimen's hero pair names Dubai, and Real Madrid is untouched", () => {
    const pair = teamShortNames(
      { name: "Dubai Basketball" },
      { name: "Real Madrid" },
      "basketball_euroleague",
    );
    expect(pair.home).toBe("Dubai Basketball");
    expect(pair.away).toBe("Madrid");
  });

  it("matches the word, case-insensitively, and nothing that merely contains it", () => {
    for (const w of ["Basketball", "BASKET", "hockey"]) {
      expect(isNonDistinctiveTrailingWord(w)).toBe(true);
    }
    // A nickname that contains a sport word is still a nickname.
    expect(teamShortName("Kitchener Hockeyists")).toBe("Hockeyists");
    // North American nicknames are unaffected.
    expect(teamShortName("Boston Celtics", null, "basketball_nba")).toBe("Celtics");
    expect(teamShortName("Toronto Maple Leafs", null, "icehockey_nhl")).toBe("Maple Leafs");
  });
});
