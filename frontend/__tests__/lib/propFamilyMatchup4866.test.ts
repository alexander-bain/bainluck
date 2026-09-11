// #4866 — the matchup prefix on every graded-window group header.
//
// `sharedFamilyPrefix` takes ONE longest-common prefix across the whole
// section, so it only fires when the section is homogeneous. Since #1735
// un-suppressed the graded windows, a live MLB page carries two cohorts whose
// common prefix is the empty string, and neither gets stripped.
//
// MEASURED through the real grouper on the real payload of
// `/api/events/15308050/game-markets` (Tampa Bay @ Atlanta, 2026-09-10):
// 91 group headers, 33 of them reading "Tampa Bay vs Atlanta: …". After the
// fix: 0 of 33 keep the prefix, 58 player families are untouched, 0 display
// names collide. On `/api/events/14632820/game-markets` (SF @ LAR, homogeneous)
// nothing changes at all — 14 headers in, 14 identical headers out.
//
// THE TEST THAT EARNS ITS PLACE IS "a repeated PLAYER head is never stripped".
// The obvious reading of the bug report — compute a prefix per `": "` cohort
// instead of once per section — passes every other test in this file and
// destroys the player cohort: `Drake Baldwin` heads seven families on that same
// payload, so it clears any "shared ⇒ boilerplate" threshold, and the player's
// name, which IS the meaning of the row, is what gets stripped.

import {
  groupByPropFamily,
  stripEventMatchupPrefix,
} from "@/lib/propFamily";

const RAYS_AT_BRAVES = { home: "Atlanta Braves", away: "Tampa Bay Rays" };

describe("stripEventMatchupPrefix", () => {
  test("drops the matchup head the hero already states", () => {
    expect(
      stripEventMatchupPrefix(
        ["Tampa Bay vs Atlanta: 8th Inning Total"],
        RAYS_AT_BRAVES,
      ),
    ).toEqual(["8th Inning Total"]);
  });

  test("A REPEATED PLAYER HEAD IS NEVER STRIPPED — the player names the row", () => {
    const players = [
      "Drake Baldwin: Hits O/U 2.5",
      "Drake Baldwin: Home Runs O/U 0.5",
      "Drake Baldwin: Home Runs O/U 1.5",
      "Drake Baldwin: Hits + Runs + RBIs O/U 3.5",
    ];
    expect(stripEventMatchupPrefix(players, RAYS_AT_BRAVES)).toEqual(players);
  });

  test("the two cohorts are treated differently IN ONE LIST", () => {
    expect(
      stripEventMatchupPrefix(
        [
          "Drake Baldwin: Hits O/U 2.5",
          "Tampa Bay vs Atlanta: Strikeouts",
          "Ozzie Albies: Home Runs O/U 0.5",
          "Tampa Bay vs Atlanta: Total Bases",
        ],
        RAYS_AT_BRAVES,
      ),
    ).toEqual([
      "Drake Baldwin: Hits O/U 2.5",
      "Strikeouts",
      "Ozzie Albies: Home Runs O/U 0.5",
      "Total Bases",
    ]);
  });

  test("either side order matches, and so does the '@' separator", () => {
    expect(
      stripEventMatchupPrefix(
        [
          "Atlanta vs Tampa Bay: Hits",
          "Tampa Bay @ Atlanta: RBIs",
          "Atlanta vs. Tampa Bay: Walks",
        ],
        RAYS_AT_BRAVES,
      ),
    ).toEqual(["Hits", "RBIs", "Walks"]);
  });

  test("a MANGLED truncated side still matches (#5181's 'Los Angeles R')", () => {
    expect(
      stripEventMatchupPrefix(
        ["San Francisco vs Los Angeles R: First Touchdown"],
        { home: "Los Angeles Rams", away: "San Francisco 49ers" },
      ),
    ).toEqual(["First Touchdown"]);
  });

  test("a nickname-only side matches", () => {
    expect(
      stripEventMatchupPrefix(["Rays vs Braves: Hits"], RAYS_AT_BRAVES),
    ).toEqual(["Hits"]);
  });

  test("accents in our team name do not defeat the match", () => {
    expect(
      stripEventMatchupPrefix(["Montreal vs Atlanta: Hits"], {
        home: "Atlanta Braves",
        away: "Montréal Expos",
      }),
    ).toEqual(["Hits"]);
  });

  // The fail-safe. A market belonging to some other fixture that has been
  // mis-attached to this event is a truth defect (notice 40); stripping its
  // prefix would disguise it as one of ours. It must stay legible.
  test("a MIS-ATTACHED fixture keeps its prefix and stays visible", () => {
    expect(
      stripEventMatchupPrefix(
        ["New York vs Boston: Hits"],
        RAYS_AT_BRAVES,
      ),
    ).toEqual(["New York vs Boston: Hits"]);
  });

  test("HALF a match is not a match — both sides must name a team", () => {
    expect(
      stripEventMatchupPrefix(["Tampa Bay vs Boston: Hits"], RAYS_AT_BRAVES),
    ).toEqual(["Tampa Bay vs Boston: Hits"]);
  });

  test("one team named on BOTH sides is not a matchup", () => {
    expect(
      stripEventMatchupPrefix(["Tampa Bay vs Tampa Bay: Hits"], RAYS_AT_BRAVES),
    ).toEqual(["Tampa Bay vs Tampa Bay: Hits"]);
  });

  test("never strips a name down to nothing", () => {
    expect(
      stripEventMatchupPrefix(["Tampa Bay vs Atlanta: "], RAYS_AT_BRAVES),
    ).toEqual(["Tampa Bay vs Atlanta: "]);
  });

  test("no teams (the golf/combat concept page) leaves every name alone", () => {
    const names = ["Tampa Bay vs Atlanta: Hits", "Drake Baldwin: Hits O/U 2.5"];
    expect(stripEventMatchupPrefix(names, null)).toEqual(names);
    expect(stripEventMatchupPrefix(names, {})).toEqual(names);
    expect(stripEventMatchupPrefix(names, { home: "Atlanta Braves" })).toEqual(
      names,
    );
  });

  // Both sides here ARE character prefixes of the two teams ("at" → "atlanta
  // braves", "ta" → "tampa bay rays"), so only the minimum-length rule stops
  // this being read as the matchup. Written this way deliberately: the obvious
  // version of this test ("TB vs Atlanta") is vacuous, because "tb" prefixes
  // neither team and the test passes with the length rule deleted.
  test("a two-character side cannot match a team even when it prefixes one", () => {
    expect(
      stripEventMatchupPrefix(["At vs Ta: Hits"], RAYS_AT_BRAVES),
    ).toEqual(["At vs Ta: Hits"]);
  });
});

describe("groupByPropFamily with a matchup", () => {
  const mark = (family: string, outcome: string) => ({
    key: `${family}|${outcome}`,
  });

  test("the mixed MLB section: windows lose the matchup, players keep their names", () => {
    const groups = groupByPropFamily(
      [
        mark("Tampa Bay vs Atlanta: 8th Inning Total", "Over 0.5"),
        mark("Drake Baldwin: Hits O/U 2.5", "Over"),
        mark("Tampa Bay vs Atlanta: 6th Inning Total", "Over 0.5"),
        mark("Drake Baldwin: Home Runs O/U 0.5", "Over"),
      ],
      (m) => m.key,
      RAYS_AT_BRAVES,
    );
    expect(groups.map((g) => g.name)).toEqual([
      "8th Inning Total",
      "Drake Baldwin: Hits O/U 2.5",
      "6th Inning Total",
      "Drake Baldwin: Home Runs O/U 0.5",
    ]);
  });

  // The homogeneous path (an NFL page, measured: 14 headers, 0 changed) must
  // keep reaching the section-wide shared-prefix logic, which already handled
  // it. This is the regression guard for the composition order.
  test("a HOMOGENEOUS matchup section is stripped exactly as it was before", () => {
    const items = [
      mark("San Francisco vs Los Angeles R: Receiving Yards", "Over"),
      mark("San Francisco vs Los Angeles R: Team Sacks", "Over"),
    ];
    const withTeams = groupByPropFamily(items, (m) => m.key, {
      home: "Los Angeles Rams",
      away: "San Francisco 49ers",
    });
    const withoutTeams = groupByPropFamily(items, (m) => m.key);
    expect(withTeams.map((g) => g.name)).toEqual([
      "Receiving Yards",
      "Team Sacks",
    ]);
    expect(withoutTeams.map((g) => g.name)).toEqual(
      withTeams.map((g) => g.name),
    );
  });

  test("non-matchup boilerplate is still stripped by the shared-prefix path", () => {
    const groups = groupByPropFamily(
      [
        mark("US Open WTA: Set 1 Winner", "Andreeva"),
        mark("US Open WTA: Set 2 Winner", "Andreeva"),
      ],
      (m) => m.key,
      RAYS_AT_BRAVES,
    );
    expect(groups.map((g) => g.name)).toEqual(["Set 1 Winner", "Set 2 Winner"]);
  });

  test("a SINGLE non-matchup family keeps its meaning ('Best Picture: Winner')", () => {
    const groups = groupByPropFamily(
      [mark("Best Picture: Winner", "Oppenheimer")],
      (m) => m.key,
      RAYS_AT_BRAVES,
    );
    expect(groups.map((g) => g.name)).toEqual(["Best Picture: Winner"]);
  });

  test("items and their order survive the strip", () => {
    const items = [
      mark("Tampa Bay vs Atlanta: Hits", "a"),
      mark("Tampa Bay vs Atlanta: Hits", "b"),
      mark("Drake Baldwin: Hits O/U 2.5", "c"),
    ];
    const groups = groupByPropFamily(items, (m) => m.key, RAYS_AT_BRAVES);
    expect(groups).toHaveLength(2);
    expect(groups[0].items).toEqual([items[0], items[1]]);
    expect(groups[1].items).toEqual([items[2]]);
  });

  test("a numeric-key section still collapses to one unnamed group", () => {
    const groups = groupByPropFamily(
      [{ key: 90210 }, { key: 90211 }],
      (m) => m.key,
      RAYS_AT_BRAVES,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].name).toBeNull();
  });
});
