/**
 * #9809 + #9808 — THE `MORE NFL` RAIL BESIDE STEELERS @ BROWNS, ON THE PAYLOAD
 * PRODUCTION SERVED.
 *
 * `9809RelatedNflRail.20260930.json` is `?tags=["sport:football","league:nfl"]`
 * at the rail's own fetch size (9), captured 2026-09-30 ~11:30Z. Rank order:
 *
 *   0 NFL Super Bowl Winner
 *   1 NFL Conference Championship Qualifiers
 *   2 NFC Championship Winner
 *   3 NFC South: Total Wins
 *   4 AFC South: Total Wins
 *   5 AFC East: Exact Order
 *   6 Pro Football: Team to advance to AFC Championship Game
 *   7 AFC Championship Winner
 *   8 AFC East: Total Wins
 *
 * #9809: on an all-AFC game (both sides `standings.conference` = 'American
 * Football Conference', read off production) ranks 2 and 3 are half the rail
 * and about a conference neither team plays in. Controls: Cowboys @ Texans
 * (NFC v AFC) and a page with no conferences keep today's four.
 *
 * #9808: the grid carries an explicit one-column template below `sm`. Without
 * it the implicit `auto` track grew to the widest row (NFC West: Exact Order's
 * four team names) and every card ran 33px past a 390px screen.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import NFL from "../fixtures/9809RelatedNflRail.20260930.json";
import { participantNames } from "@/lib/railParticipantOrder";

const NFL_KEY = "related-by-tag|sport:football|league:nfl";

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key === null || key === undefined) {
      return { data: undefined, error: undefined, isLoading: false };
    }
    const flat = Array.isArray(key) ? key.join("|") : String(key);
    return { data: flat === NFL_KEY ? NFL : undefined, error: undefined, isLoading: false };
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

const AFC = "American Football Conference";
const NFC = "National Football Conference";

function render(props: Record<string, unknown>): string {
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:football", "league:nfl"],
      excludeId: 14780550,
      excludeType: "event",
      limit: 4,
      title: "More NFL",
      preferNames: participantNames("Pittsburgh Steelers", "Cleveland Browns"),
      ...props,
    } as never)
  );
}

function drawnTitles(markup: string): string[] {
  return Array.from(
    markup.matchAll(/data-testid="related-card"[\s\S]*?<span class="min-w-0 text-\[14px\][^"]*">([^<]*)</g)
  ).map((m) => m[1].replace(/&#x27;|&apos;/g, "'").replace(/&amp;/g, "&").trim());
}

const TODAY = [
  "NFL Super Bowl Winner",
  "NFL Conference Championship Qualifiers",
  "NFC Championship Winner",
  "NFC South: Total Wins",
];

describe("#9809 — the rail beside Steelers @ Browns", () => {
  it("STRAWMAN: with no conferences it deals two NFC-only boards", () => {
    expect(drawnTitles(render({}))).toEqual(TODAY);
  });

  it("drops the NFC boards and deals AFC ones in their seats", () => {
    const titles = drawnTitles(render({ conferences: [AFC, AFC] }));
    expect(titles).toEqual([
      "NFL Super Bowl Winner",
      "NFL Conference Championship Qualifiers",
      "AFC South: Total Wins",
      "AFC East: Exact Order",
    ]);
    expect(titles.join(" ")).not.toMatch(/\bNFC\b/);
  });

  it("still draws four and says four", () => {
    expect(render({ conferences: [AFC, AFC] })).toContain('data-count="4"');
  });
});

describe("#9809 — the pages the filter must leave alone", () => {
  it("Cowboys @ Texans (NFC v AFC) keeps today's four", () => {
    expect(drawnTitles(render({ conferences: [NFC, AFC] }))).toEqual(TODAY);
  });

  it("a side with no conference keeps today's four", () => {
    expect(drawnTitles(render({ conferences: [AFC, null] }))).toEqual(TODAY);
  });

  it("an NFC game keeps its NFC boards and drops the AFC ones", () => {
    const titles = drawnTitles(render({ conferences: [NFC, NFC], limit: 6 }));
    expect(titles).toContain("NFC Championship Winner");
    expect(titles).toContain("NFC South: Total Wins");
    expect(titles.join(" ")).not.toMatch(/\bAFC\b/);
  });
});

describe("#9808 — the grid cannot outgrow a phone", () => {
  it("has a one-column minmax template below sm and two columns from sm", () => {
    const grid = render({ conferences: [AFC, AFC] }).match(
      /<div class="([^"]*)" data-testid="related-by-tag-grid"/
    );
    expect(grid).not.toBeNull();
    const classes = grid![1].split(/\s+/);
    expect(classes).toContain("grid");
    expect(classes).toContain("grid-cols-1");
    expect(classes).toContain("sm:grid-cols-2");
  });
});
