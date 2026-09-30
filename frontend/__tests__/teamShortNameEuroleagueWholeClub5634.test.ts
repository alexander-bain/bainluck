/**
 * #5634 — a EuroLeague club is not its city either.
 *
 * WHAT THE READER SAW: `/events/15318709`, Fenerbahce SK 100-76 FC Bayern
 * München, EuroLeague final, 390px, 2026-09-29 — the hero named the away side
 * **"München"**. The football arm keeps a club whole under a `soccer_*` key;
 * EuroLeague clubs are named the same way (club first, city last) and took the
 * last-word rule.
 *
 * Every name below was read verbatim from production `events`
 * (`basketball_euroleague`, 60 days, all 30 distinct names, 2026-09-30), and
 * the "before" column is what the rule printed for it with this key.
 */

import { keepsWholeClubName, teamShortName, teamShortNames } from "@/lib/teamShortName";

const EUROLEAGUE = "basketball_euroleague";

describe("#5634 — a EuroLeague club keeps its whole name", () => {
  it.each([
    ["FC Bayern München", "München", "Bayern München"],
    ["FC Bayern Munchen", "Munchen", "Bayern Munchen"],
    ["Real Madrid", "Madrid", "Real Madrid"],
    ["Zalgiris Kaunas", "Kaunas", "Zalgiris Kaunas"],
    ["KK Crvena zvezda", "zvezda", "Crvena zvezda"],
    ["KK Partizan NIS", "NIS", "Partizan NIS"],
    ["Olimpia Milano", "Milano", "Olimpia Milano"],
    ["Pallacanestro Olimpia Milano", "Milano", "Pallacanestro Olimpia Milano"],
    ["Virtus Bologna", "Bologna", "Virtus Bologna"],
    ["ASVEL Lyon Villeurbanne", "Villeurbanne", "ASVEL Lyon Villeurbanne"],
    ["Anadolu Efes", "Efes", "Anadolu Efes"],
  ])("%s: %s → %s", (name, before, after) => {
    expect(teamShortName(name)).toBe(before);
    expect(teamShortName(name, null, EUROLEAGUE)).toBe(after);
  });

  it("both Tel Aviv clubs stop reading 'Aviv' on their own", () => {
    // `teamShortNames` already fell back to the full names for the derby pair;
    // a surface that labels ONE side (a card, a futures row) printed "Aviv".
    const home = { name: "Maccabi Tel Aviv" };
    const away = { name: "Hapoel Tel Aviv" };
    expect(teamShortName(home.name)).toBe("Aviv");
    expect(teamShortName(away.name)).toBe("Aviv");
    expect(teamShortName(home.name, null, EUROLEAGUE)).toBe("Maccabi Tel Aviv");
    expect(teamShortName(away.name, null, EUROLEAGUE)).toBe("Hapoel Tel Aviv");
    const after = teamShortNames(home, away, EUROLEAGUE);
    expect(after).toEqual({ home: "Maccabi Tel Aviv", away: "Hapoel Tel Aviv" });
  });

  it.each([
    "Fenerbahce SK",
    "Paris Basketball",
    "Dubai Basketball",
    "Valencia Basket",
    "Olympiacos B.C.",
    "Panathinaikos",
    "Barcelona",
  ])("%s keeps the label it already had", (name) => {
    expect(teamShortName(name, null, EUROLEAGUE)).toBe(teamShortName(name));
  });

  it("the key is matched whole, so city-first basketball keeps the last-word rule", () => {
    expect(keepsWholeClubName(EUROLEAGUE)).toBe(true);
    expect(keepsWholeClubName(" Basketball_EuroLeague ")).toBe(true);
    for (const key of ["basketball_nba", "basketball_wnba", "basketball_nbl", "basketball_other", "basketball"]) {
      expect(keepsWholeClubName(key)).toBe(false);
    }
    expect(teamShortName("Sydney Kings", null, "basketball_nbl")).toBe("Kings");
    expect(teamShortName("Las Vegas Aces", null, "basketball_other")).toBe("Aces");
    expect(teamShortName("Los Angeles Lakers", null, "basketball_nba")).toBe("Lakers");
  });
});
