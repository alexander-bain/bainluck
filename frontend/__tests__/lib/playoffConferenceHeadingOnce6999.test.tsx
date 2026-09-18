/**
 * #6999 — THE CONFERENCE NAME IS PRINTED ONCE, AND "ONCE" HAS TWO FAILURE SIDES.
 *
 * Alex measured the four biggest US playoff grids at 390px on 2026-09-18 and
 * found each conference named TWICE, 49px apart, at the same size and weight:
 *
 *     /playoffs/nfl  y= 910 <h2> "American Football Conference"
 *                    y= 959 <h3> "American Football Conference"
 *                    y=1969 <h2> / y=2018 <h3> "National Football Conference"
 *     /playoffs/nba  Eastern / Western   · /playoffs/mlb  AL / NL
 *     /playoffs/nhl  Eastern / Western
 *
 * Eight duplicated headings, all on the DEFAULT landing view. The page handed
 * `conf` both to its section `<h2>` and to `teamsToProgression`'s
 * `tournamentName`, which becomes `ProgressionResponse.tournament_name` and is
 * drawn as the card's own `<h3>` by `TournamentProgressionTable`.
 *
 * ═══ WHY IT SURVIVED, AND WHY THAT DICTATES THE SHAPE OF THE FIX ═══
 *
 * It vanishes the moment anyone interacts. The `<h2>` was gated on
 * `sections.length > 1`; tapping a conference chip collapses the page to one
 * section, the `<h2>` drops, and the card `<h3>` alone is correct. So the
 * duplicate lived only on the view a reader never clicks out of to check.
 *
 * That means the fix CANNOT be "stop passing the name to the card" — in the
 * filtered view the card title is the only thing naming the conference, and
 * deleting it leaves a table whose conference is indicated by a chip alone.
 * Nor can it be "stop drawing the <h2>". The name has one place to be and
 * WHICH place depends on the section count, so both sides are now derived from
 * a single boolean in `conferenceSectionHeadings`.
 *
 * 🔴 THE GUARD THEREFORE HAS TWO SIDES, AND ONLY ASSERTING ONE IS THE TRAP.
 * "The name does not appear twice" is satisfied by a page that prints it ZERO
 * times, which is a worse defect than the one being fixed and is precisely what
 * the tempting one-line fix (pass `""` always) produces in the filtered view.
 * Every absence assertion below is paired with the presence assertion that
 * makes it non-vacuous, and the count assertions pin EXACTLY one, not "at most
 * one".
 *
 * ═══ THE REJECTED FIX, RECORDED SO IT IS NOT RE-DERIVED ═══
 *
 * The issue's suggested repair was to pass the grid's own name
 * (`gridData.name`) instead of `conf`, "recovering a line of real information".
 * Measured against the live page before building: `name` is
 * "NFL Playoffs 2026-27", while the page's `<h1>` reads "NFL Championship Grid"
 * with "2026-27" on the line directly below it. So that fix prints the page
 * title back to the reader on BOTH conference cards — trading one adjacent
 * duplicate for two distant ones, and still leaving the filtered view with no
 * conference name. `A_GRID_NAME` below is a live string and is asserted absent.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

import { conferenceSectionHeadings } from "@/lib/playoffConferenceSections";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import type { ProgressionResponse } from "../../lib/types";

/** Read from `/api/playoffs/nfl` on 2026-09-18, exactly as served. */
const NFL_CONFERENCES = [
  "American Football Conference",
  "National Football Conference",
];
const A_GRID_NAME = "NFL Playoffs 2026-27";

/** Every grouped grid the defect was measured on, with its served keys. */
const GROUPED_GRIDS: ReadonlyArray<readonly [string, readonly string[]]> = [
  ["nfl", NFL_CONFERENCES],
  ["nba", ["Eastern Conference", "Western Conference"]],
  ["mlb", ["American League", "National League"]],
  ["nhl", ["Eastern Conference", "Western Conference"]],
];

/**
 * Count the places one section would actually PRINT a string: the section
 * heading and the card title. This is the whole question the suite asks, so it
 * is computed from the returned record rather than restated per test.
 */
function placesNamed(
  heading: { label: string | null; tournamentName: string },
  name: string,
): number {
  return (
    (heading.label === name ? 1 : 0) + (heading.tournamentName === name ? 1 : 0)
  );
}

describe("#6999 the section heading and the card title never say the same thing", () => {
  test.each(GROUPED_GRIDS)(
    "/playoffs/%s default view: each conference is named exactly ONCE",
    (_slug, confs) => {
      const sections = conferenceSectionHeadings(confs, null);

      expect(sections).toHaveLength(confs.length);
      for (const conf of confs) {
        const section = sections.find((s) => s.conf === conf)!;
        // Exactly one, not "at most one" — zero is the other failure.
        expect(placesNamed(section, conf)).toBe(1);
      }
    },
  );

  test("default view: the heading carries it and the card title is empty", () => {
    const [afc, nfc] = conferenceSectionHeadings(NFL_CONFERENCES, null);

    expect(afc.label).toBe("American Football Conference");
    expect(afc.tournamentName).toBe("");
    expect(nfc.label).toBe("National Football Conference");
    expect(nfc.tournamentName).toBe("");
  });

  test("filtered to one conference: the card title carries it and no heading is drawn", () => {
    const sections = conferenceSectionHeadings(
      NFL_CONFERENCES,
      "American Football Conference",
    );

    expect(sections).toHaveLength(1);
    // The presence half. Without this, "no duplicate" passes on a page that
    // names the conference nowhere at all.
    expect(sections[0].tournamentName).toBe("American Football Conference");
    expect(sections[0].label).toBeNull();
    expect(placesNamed(sections[0], "American Football Conference")).toBe(1);
  });

  test.each(GROUPED_GRIDS)(
    "/playoffs/%s: every conference chip yields exactly one naming",
    (_slug, confs) => {
      for (const chip of confs) {
        const sections = conferenceSectionHeadings(confs, chip);
        expect(sections).toHaveLength(1);
        expect(placesNamed(sections[0], chip)).toBe(1);
      }
    },
  );

  test("the grid's own name is never substituted in (the rejected fix)", () => {
    // Absence asserted against the REJECTED VALUE, paired with the presence
    // assertion above — a title that is `""` and a title that is the page's
    // `<h1>` restated are different outcomes and the suite must tell them apart.
    for (const section of conferenceSectionHeadings(NFL_CONFERENCES, null)) {
      expect(section.tournamentName).not.toBe(A_GRID_NAME);
      expect(section.label).not.toBe(A_GRID_NAME);
    }
  });

  test("a single-conference grid still names its one conference", () => {
    // Not a chip filter — a grid that only ever serves one group. Same branch,
    // and the one place left to print is the card title.
    const sections = conferenceSectionHeadings(["Eastern Conference"], null);
    expect(sections).toHaveLength(1);
    expect(sections[0].label).toBeNull();
    expect(sections[0].tournamentName).toBe("Eastern Conference");
  });

  test("a chip matching nothing yields no sections rather than an empty heading", () => {
    expect(conferenceSectionHeadings(NFL_CONFERENCES, "Pacific Coast League")).toEqual(
      [],
    );
  });
});

/**
 * The render half. The rule above is only true of the page if the component
 * actually suppresses its `<h3>` on the empty string — a pure-function suite
 * cannot see that, and `tournament_name: ""` reaching a component that renders
 * `""` as a heading would put an empty bold line where the duplicate was.
 */
describe("#6999 TournamentProgressionTable honours the empty title", () => {
  function grid(tournamentName: string): ProgressionResponse {
    return {
      sport: "americanfootball_nfl",
      tournament_name: tournamentName,
      stages: [
        {
          key: "make_playoffs",
          label: "Make Playoffs",
          order: 0,
          market_id: null,
          market_name: null,
          resolved: false,
        },
      ],
      participants: [
        {
          name: "Buffalo Bills",
          team_id: null,
          logo_url: null,
          primary_color: null,
          conference: "American Football Conference",
          region: null,
          seed: null,
          record: null,
          probabilities: { make_playoffs: 0.81 },
          changes_24h: {},
          status: {},
          sources_data: {},
        },
      ],
    };
  }

  test("an empty title draws no heading element at all", () => {
    const html = renderToStaticMarkup(
      React.createElement(TournamentProgressionTable, { data: grid("") }),
    );

    expect(html).not.toContain("<h3");
    // Non-vacuity: the component rendered its actual content. An absence
    // assertion against a component that returned nothing is decoration.
    expect(html).toContain("Buffalo Bills");
  });

  test("a non-empty title still draws it — the filtered view depends on this", () => {
    const html = renderToStaticMarkup(
      React.createElement(TournamentProgressionTable, {
        data: grid("American Football Conference"),
      }),
    );

    expect(html).toContain("<h3");
    expect(html).toContain("American Football Conference");
    expect(html).toContain("Buffalo Bills");
  });
});
