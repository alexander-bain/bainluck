/**
 * #10050 — the Yankees page's "Next Team" race printed "New York Y" under all 13 players.
 *
 * Production, 390px, 2026-10-01 10:38Z, `/sport/baseball/mlb/team/new-york-yankees-mlb`:
 *
 *     Next Team                       13 IN THE MIX
 *     Rafael Devers                              7%
 *     New York Y
 *     ...
 *     Mike Trout                                 1%
 *     New York Y
 *
 * The grey line read as each player's team. It is the outcome being priced (Devers's next team
 * IS the Yankees, 7%), printed in Kalshi's cut-off form. The fixture below is the served
 * `/api/teams/new-york-yankees-mlb/prop-families` family `next team`, verbatim (10:37Z gen 3).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { TeamPropFamilies } from "@/components/TeamPropFamilies";
import type { PropFamily, PropFamilyRow } from "@/lib/api";

const YANKEES_NEXT_TEAM_ROWS = [
  {
    "entity": "Rafael Devers",
    "market_id": 52755787,
    "outcome_id": null,
    "probability": 0.07,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.07
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27RDEVERS",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Francisco Lindor",
    "market_id": 56914122,
    "outcome_id": null,
    "probability": 0.065,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.065
    },
    "group_id": "kalshi:KXMLBNEXTTEAM-27FLINDOR12",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Tarik Skubal",
    "market_id": 59164885,
    "outcome_id": null,
    "probability": 0.06,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.06
    },
    "group_id": "kalshi:KXMLBNEXTTEAM-27TSKUBAL",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Ronald Acuna Jr.",
    "market_id": 60473157,
    "outcome_id": null,
    "probability": 0.055,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.055
    },
    "group_id": "kalshi:KXMLBNEXTTEAM-27RACUNA",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Joe Ryan",
    "market_id": 27558451,
    "outcome_id": null,
    "probability": 0.05,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.05
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27JRYAN",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Fernando Tatis Jr.",
    "market_id": 27558453,
    "outcome_id": null,
    "probability": 0.04,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.04
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27FTATIS",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Luis Severino",
    "market_id": 27558450,
    "outcome_id": null,
    "probability": 0.04,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.04
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27LSEVERINO",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Aroldis Chapman",
    "market_id": 27558456,
    "outcome_id": null,
    "probability": 0.04,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.04
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27ACHAPMAN",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Sandy Alcantara",
    "market_id": 27558448,
    "outcome_id": null,
    "probability": 0.015,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.015
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27SALCANTARA",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Mike Trout",
    "market_id": 27558449,
    "outcome_id": null,
    "probability": 0.01,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.01
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27MTROUT",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Yandy Diaz",
    "market_id": 27558446,
    "outcome_id": null,
    "probability": 0.01,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.01
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27YDIAZ",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Christian Walker",
    "market_id": 27558454,
    "outcome_id": null,
    "probability": 0.01,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.01
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27CWALKER",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  },
  {
    "entity": "Jarren Duran",
    "market_id": 27558452,
    "outcome_id": null,
    "probability": 0.01,
    "source": "kalshi",
    "sources": [
      "kalshi"
    ],
    "cross_source": {
      "kalshi": 0.01
    },
    "group_id": "kalshi:KXNEXTTEAMMLB-27JDURAN",
    "status": "open",
    "settled": false,
    "result": null,
    "top_outcome": "New York Y"
  }
] as unknown as PropFamilyRow[];

function family(key: string, label: string, rows: PropFamilyRow[]): PropFamily {
  return { family_key: key, label, entity_count: rows.length, sources: ["kalshi"], rows };
}

function row(entity: string, probability: number, top_outcome: string | null): PropFamilyRow {
  return {
    ...YANKEES_NEXT_TEAM_ROWS[0],
    entity,
    probability,
    top_outcome,
    market_id: 900000 + Math.round(probability * 1000),
    group_id: `kalshi:TEST-${entity}`,
  };
}

/** Every text node the card prints, in order — what a reader reads. */
function texts(families: PropFamily[], teamName?: string | null): string[] {
  const markup = renderToStaticMarkup(
    <TeamPropFamilies families={families} teamColor="#0C2340" teamName={teamName} />,
  );
  return [...markup.replace(/<!-- -->/g, "").matchAll(/>([^<]+)</g)]
    .map((m) => m[1].trim())
    .filter(Boolean);
}

describe("#10050 — a Next Team row's outcome that names the page's team", () => {
  it("specimen fixture is the served shape: 13 live rows, every outcome 'New York Y'", () => {
    expect(YANKEES_NEXT_TEAM_ROWS).toHaveLength(13);
    expect(
      YANKEES_NEXT_TEAM_ROWS.every((r) => r.top_outcome === "New York Y" && !r.settled),
    ).toBe(true);
  });

  it("prints no 'New York Y' under the players and names the Yankees once, in the heading", () => {
    const t = texts([family("next team", "Next Team", YANKEES_NEXT_TEAM_ROWS)], "New York Yankees");
    expect(t).not.toContain("New York Y");
    expect(t.filter((x) => x.includes("New York Yankees"))).toEqual([
      "Next Team: New York Yankees",
    ]);
    expect(t).toContain("Mike Trout");
    expect(t).toContain("Rafael Devers");
    expect(t).toContain("13 in the mix");
  });

  it("control: a row whose outcome is ANOTHER club keeps its line, and the heading stays plain", () => {
    const t = texts(
      [
        family("next team", "Next Team", [
          row("Steph Curry", 0.05, "Boston Celtics"),
          row("Nikola Vucevic", 0.03, "Orlando Magic"),
        ]),
      ],
      "Boston Celtics",
    );
    expect(t).toContain("Next Team");
    expect(t).toContain("Orlando Magic");
    // The mixed card cannot hoist the team, so the own-team row names it in full.
    expect(t).toContain("Boston Celtics");
  });

  it("control: a mixed card spells the page team's cut-off name out in full", () => {
    const t = texts(
      [
        family("next team", "Next Team", [
          row("Rafael Devers", 0.07, "New York Y"),
          row("Juan Soto", 0.03, "New York M"),
        ]),
      ],
      "New York Yankees",
    );
    expect(t).toContain("Next Team");
    expect(t).toContain("New York Yankees");
    expect(t).not.toContain("New York Y");
    expect(t).toContain("New York M");
  });

  it("control: another club's city-plus-initials does not count as the page's team", () => {
    const t = texts(
      [
        family("next team", "Next Team", [
          row("Player A", 0.05, "Chicago WS"),
          row("Player B", 0.03, "Chicago WS"),
        ]),
      ],
      "Chicago Cubs",
    );
    expect(t).toContain("Next Team");
    expect(t.filter((x) => x === "Chicago WS")).toHaveLength(2);
  });

  it("control: an award race (no outcome line) keeps its label untouched", () => {
    const t = texts(
      [family("alcs mvp", "ALCS MVP", [row("Aaron Judge", 0.07, null), row("Ben Rice", 0.058, null)])],
      "New York Yankees",
    );
    expect(t).toContain("ALCS MVP");
    expect(t.some((x) => x.includes("New York Yankees"))).toBe(false);
  });

  it("without a team name (older caller) the rows render as before", () => {
    const t = texts([family("next team", "Next Team", YANKEES_NEXT_TEAM_ROWS)]);
    expect(t).toContain("Next Team");
    expect(t.filter((x) => x === "New York Y")).toHaveLength(13);
  });
});
