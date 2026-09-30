/**
 * #9750 — a golf card's chaser strip never prints two golfers as the same word.
 *
 * WHAT THE READER SAW: `/sports` at 390px, 2026-09-30 ~06:58Z — the LPGA LOTTE
 * Championship card's strip read **"Kim 9.0%"** beside **"Kim 7.7%"**. The
 * served golfers (`/api/golf`, same read) are the fixture below: Jeeno Thitikul
 * leads, and the strip holds Miyu Yamashita, A Lim Kim, Hyo Joo Kim, Nasa Hataoka.
 *
 * Every block pairs the shared-surname frame with the frame the fix must NOT
 * touch: a strip of distinct surnames prints exactly the surnames it always did.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "@/components/TournamentCard";
import { golfChaserLabels } from "@/lib/golfChaserLabels";
import type { GolfTournament } from "@/lib/types";

const golfer = (name: string, probability: number) => ({
  name,
  probability,
  rank: 0,
  movement_24h: null,
  american_odds: null,
  opening_probability: null,
  sources: {},
});

function lotte(names: Array<[string, number]>): GolfTournament {
  return {
    key: "lotte_championship",
    name: "LOTTE Championship presented by Hoakalei",
    is_major: false,
    tour: "lpga",
    tour_label: "LPGA Tour",
    commence_time: "2026-10-01T00:00:00+00:00",
    resolution_date: "2026-10-04T00:00:00+00:00",
    start_date: "2026-10-01T00:00:00+00:00",
    end_date: "2026-10-04T00:00:00+00:00",
    schedule_status: "upcoming",
    market_ids: [1],
    champion: null,
    golfers: names.map(([n, p]) => golfer(n, p)),
  };
}

/** The strip's name cells, in order. */
function stripLabels(html: string): string[] {
  const cell = /<div class="text-\[11px\] font-medium text-text-secondary truncate px-1">([^<]*)<\/div>/g;
  return Array.from(html.matchAll(cell), (m) => m[1]);
}

function render(t: GolfTournament): string {
  jest.useFakeTimers({ now: new Date("2026-09-30T07:00:00Z") });
  try {
    return renderToStaticMarkup(<TournamentCard tournament={t} />);
  } finally {
    jest.useRealTimers();
  }
}

const SERVED: Array<[string, number]> = [
  ["Jeeno Thitikul", 0.125],
  ["Miyu Yamashita", 0.11],
  ["A Lim Kim", 0.09],
  ["Hyo Joo Kim", 0.077],
  ["Nasa Hataoka", 0.037],
];

describe("#9750 the rendered card", () => {
  it("names the two Kims apart on the served LOTTE field", () => {
    const labels = stripLabels(render(lotte(SERVED)));
    expect(labels).toEqual(["Yamashita", "A. Kim", "H. Kim", "Hataoka"]);
  });

  it("control: a strip of distinct surnames prints exactly the surnames", () => {
    const labels = stripLabels(
      render(
        lotte([
          ["Jeeno Thitikul", 0.125],
          ["Miyu Yamashita", 0.11],
          ["Hyo Joo Kim", 0.077],
          ["Nasa Hataoka", 0.037],
          ["Akie Iwai", 0.028],
        ]),
      ),
    );
    expect(labels).toEqual(["Yamashita", "Kim", "Hataoka", "Iwai"]);
  });
});

/**
 * The hero counts too. `/sports` at 390px, 2026-09-30 ~07:40Z: the Alfred
 * Dunhill Links card led with "Matt Fitzpatrick 10.4%" and its strip printed
 * "Fitzpatrick 3.5%" — Alex Fitzpatrick, as served (fixture below).
 */
const DUNHILL: Array<[string, number]> = [
  ["Matt Fitzpatrick", 0.104],
  ["Tommy Fleetwood", 0.083],
  ["Robert MacIntyre", 0.067],
  ["Tyrrell Hatton", 0.048],
  ["Alex Fitzpatrick", 0.035],
];

describe("#9750 a chaser who shares the hero's surname", () => {
  it("names Alex Fitzpatrick apart from the Matt Fitzpatrick hero on the served field", () => {
    const html = render(lotte(DUNHILL));
    expect(html).toContain("Matt Fitzpatrick");
    expect(stripLabels(html)).toEqual(["Fleetwood", "MacIntyre", "Hatton", "A. Fitzpatrick"]);
  });

  it("control: the same strip under a hero with a different surname is unchanged", () => {
    const labels = stripLabels(
      render(lotte([["Rory McIlroy", 0.2], ...DUNHILL.slice(1)])),
    );
    expect(labels).toEqual(["Fleetwood", "MacIntyre", "Hatton", "Fitzpatrick"]);
  });

  it("a chaser whose initial also matches the hero's gets the full name", () => {
    expect(golfChaserLabels(["Adam Fitzpatrick", "Tommy Fleetwood"], "Alex Fitzpatrick")).toEqual([
      "Adam Fitzpatrick",
      "Fleetwood",
    ]);
  });

  it("no hero, a blank hero and a one-word hero change nothing", () => {
    const strip = ["Tommy Fleetwood", "Alex Fitzpatrick"];
    expect(golfChaserLabels(strip)).toEqual(["Fleetwood", "Fitzpatrick"]);
    expect(golfChaserLabels(strip, null)).toEqual(["Fleetwood", "Fitzpatrick"]);
    expect(golfChaserLabels(strip, "  ")).toEqual(["Fleetwood", "Fitzpatrick"]);
    expect(golfChaserLabels(strip, "Tiger")).toEqual(["Fleetwood", "Fitzpatrick"]);
  });
});

describe("#9750 golfChaserLabels", () => {
  it("initials only the golfers whose surname is shared", () => {
    expect(golfChaserLabels(["Miyu Yamashita", "A Lim Kim", "Hyo Joo Kim"])).toEqual([
      "Yamashita",
      "A. Kim",
      "H. Kim",
    ]);
  });

  it("a hyphenated given name gives its first initial", () => {
    expect(golfChaserLabels(["Hyo-Joo Kim", "A-Lim Kim"])).toEqual(["H. Kim", "A. Kim"]);
  });

  it("surnames compare case-blind", () => {
    expect(golfChaserLabels(["Sei Young KIM", "Hyo Joo Kim"])).toEqual(["S. KIM", "H. Kim"]);
  });

  it("colliding initials fall back to the full name, and only for that pair", () => {
    expect(golfChaserLabels(["A Lim Kim", "Auston Kim", "Hyo Joo Kim", "Nasa Hataoka"])).toEqual([
      "A Lim Kim",
      "Auston Kim",
      "H. Kim",
      "Hataoka",
    ]);
  });

  it("never returns two equal labels for two different golfers", () => {
    const fields = [
      ["A Lim Kim", "Hyo Joo Kim", "Auston Kim", "Sei Young Kim"],
      ["Minjee Lee", "Jeongeun Lee", "Andrea Lee", "Alison Lee"],
      ["Inbee Park", "Sung Hyun Park", "Hee Young Park"],
    ];
    for (const names of fields) {
      const labels = golfChaserLabels(names).map((l) => l.toLowerCase());
      expect(new Set(labels).size).toBe(names.length);
    }
  });

  it("a one-word name and an empty strip pass through", () => {
    expect(golfChaserLabels(["Tiger"])).toEqual(["Tiger"]);
    expect(golfChaserLabels([])).toEqual([]);
  });
});
