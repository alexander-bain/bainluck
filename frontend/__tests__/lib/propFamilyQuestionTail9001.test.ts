// #9001 — THE SCRIPT printed "WILL THE GAME GO TO EXTRA INNINGS?: LOS ANGELES
// ANGELS VS. SEATTLE MARINERS" on every MLB page (7 of 7 on 2026-09-26).
//
// #4866 strips a matchup at the HEAD of a family name. Polymarket puts it at the
// TAIL, after a question, so the head was the question and nothing matched.
// Strings below are verbatim from `/api/events/{id}/game-markets` player_props,
// production 2026-09-27 01:15Z.

import {
  groupByPropFamily,
  stripEventMatchupPrefix,
} from "@/lib/propFamily";

const ANGELS_AT_MARINERS = { home: "Seattle Mariners", away: "Los Angeles Angels" };
const ASTROS_AT_ATHLETICS = { home: "Athletics", away: "Houston Astros" };

describe("stripEventMatchupPrefix — a question with the matchup at its tail", () => {
  test("the question heads the family; '?:' and the matchup go", () => {
    expect(
      stripEventMatchupPrefix(
        [
          "Will the game go to extra innings?: Los Angeles Angels vs. Seattle Mariners",
          "Will there be a run scored in the first inning?: Los Angeles Angels vs. Seattle Mariners",
        ],
        ANGELS_AT_MARINERS,
      ),
    ).toEqual([
      "Will the game go to extra innings?",
      "Will there be a run scored in the first inning?",
    ]);
  });

  test("a one-word club name on the tail still matches", () => {
    expect(
      stripEventMatchupPrefix(
        ["Will the game go to extra innings?: Houston Astros vs. Athletics"],
        ASTROS_AT_ATHLETICS,
      ),
    ).toEqual(["Will the game go to extra innings?"]);
  });

  test("a MIS-ATTACHED fixture's tail keeps its full name and stays visible", () => {
    const other = [
      "Will the game go to extra innings?: Houston Astros vs. Athletics",
    ];
    expect(stripEventMatchupPrefix(other, ANGELS_AT_MARINERS)).toEqual(other);
  });

  test("a head that is not a question keeps its tail", () => {
    const names = ["Extra Innings: Los Angeles Angels vs. Seattle Mariners"];
    expect(stripEventMatchupPrefix(names, ANGELS_AT_MARINERS)).toEqual(names);
  });

  test("player families on the same page are untouched", () => {
    const players = [
      "Cole Young: Home Runs O/U 0.5",
      "Ryan Johnson: Strikeouts O/U 6.5",
      "Julio Rodríguez: Home Runs O/U 0.5",
    ];
    expect(stripEventMatchupPrefix(players, ANGELS_AT_MARINERS)).toEqual(players);
  });

  test("no teams (concept page) leaves the question's tail alone", () => {
    const names = [
      "Will the game go to extra innings?: Los Angeles Angels vs. Seattle Mariners",
    ];
    expect(stripEventMatchupPrefix(names, null)).toEqual(names);
  });
});

describe("groupByPropFamily — the served keys for Angels @ Mariners", () => {
  test("the extra-innings family is headed by its question, the players by their names", () => {
    const keys = [
      "Will the game go to extra innings?: Los Angeles Angels vs. Seattle Mariners|No",
      "Will the game go to extra innings?: Los Angeles Angels vs. Seattle Mariners|Yes",
      "Cole Young: Home Runs O/U 0.5|Under",
      "Cole Young: Home Runs O/U 0.5|Over",
    ];
    const groups = groupByPropFamily(keys, (k) => k, ANGELS_AT_MARINERS);
    expect(groups.map((g) => [g.name, g.items.length])).toEqual([
      ["Will the game go to extra innings?", 2],
      ["Cole Young: Home Runs O/U 0.5", 2],
    ]);
  });
});
