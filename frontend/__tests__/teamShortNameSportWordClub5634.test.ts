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
import { marginSideLabels } from "@/components/MarketMapSection";

// The fourth column is the label under the row's own key. It is the name
// itself, except where the EuroLeague whole-club rule (#5634, 2026-09-30)
// drops a leading designator exactly as it does for football: "FC".
const PRODUCTION_NAMES: ReadonlyArray<[string, string, string, string]> = [
  ["Dubai Basketball", "basketball_euroleague", "Basketball", "Dubai Basketball"],
  ["Paris Basketball", "basketball_euroleague", "Basketball", "Paris Basketball"],
  ["Valencia Basket", "basketball_euroleague", "Basket", "Valencia Basket"],
  ["Modo Hockey", "icehockey_sweden_allsvenskan", "Hockey", "Modo Hockey"],
  ["TUTO Hockey", "icehockey_mestis", "Hockey", "TUTO Hockey"],
  // Re-read 2026-09-29 with the non-English sport words too (shopper pass 0126,
  // `/events/15318706`, a EuroLeague final that printed "Bàsquet" / "BÀS").
  ["FC Barcelona Bàsquet", "basketball_euroleague", "Bàsquet", "Barcelona Bàsquet"],
];

describe("#5634 — a trailing sport word never stands for the club", () => {
  it.each(PRODUCTION_NAMES)(
    "%s keeps its club name, with or without its sport key",
    (name, sportKey, word, label) => {
      expect(teamShortName(name, null, sportKey)).toBe(label);
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
    expect(teamCrestBadge("FC Barcelona Bàsquet", "basketball_euroleague")).toBe("BAR");
  });

  it("the specimen's hero pair names Dubai, and Real Madrid takes the EuroLeague whole-club rule", () => {
    const pair = teamShortNames(
      { name: "Dubai Basketball" },
      { name: "Real Madrid" },
      "basketball_euroleague",
    );
    expect(pair.home).toBe("Dubai Basketball");
    expect(pair.away).toBe("Real Madrid");
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

  it("an accented sport word is folded before the lookup (#5634, pass 0126)", () => {
    // `alphanumeric` alone turns "Bàsquet" into "Bsquet", which matches nothing.
    for (const w of ["Bàsquet", "BÀSQUET", "Basquet", "bàsquet"]) {
      expect(isNonDistinctiveTrailingWord(w)).toBe(true);
    }
    const pair = teamShortNames(
      { name: "Dubai Basketball" },
      { name: "FC Barcelona Bàsquet" },
      "basketball_euroleague",
    );
    expect(pair.away).toBe("Barcelona Bàsquet");
    expect(pair.away).not.toBe("Bàsquet");
    // The margin card's axis ends read "BÀS by 18+" on the specimen.
    const margin = marginSideLabels("Dubai Basketball", "FC Barcelona Bàsquet", undefined, undefined, "basketball_euroleague");
    expect(margin.away).toBe("Barcelona Bàsquet");
    // The fold feeds only this lookup: an accented NICKNAME still shortens.
    expect(teamShortName("Club Atlético Tigres")).toBe("Tigres");
    expect(teamShortName("Montréal Canadiens", null, "icehockey_nhl")).toBe("Canadiens");
  });
});

