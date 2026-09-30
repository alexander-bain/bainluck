/**
 * #9799 — WHAT THE RAIL DRAWS BESIDE CUBS @ PADRES, ON THE PAYLOAD PRODUCTION SERVED.
 *
 * `9799RelatedMlbRail.20260930.json` is `?tags=["sport:baseball","league:mlb"]`
 * at the rail's own fetch size (9), captured 2026-09-30 10:50Z. Rank order:
 *
 *   0 MLB World Series Winner
 *   1 MLB World Series Champion 2026
 *   2 AL Reliever of the Year Winner?
 *   3 MLB: AL Platinum Glove Winner
 *   4 National League Champion
 *   5 American League Champion
 *   6 MLB Postseason: World Series MVP
 *   7 MLB Postseason: RBI Leader
 *   8 MLB: AL Comeback Player of the Year
 *
 * On an all-NL game ranks 2 and 3 are half of a four-card rail. The controls: an
 * interleague game and a page with no conferences keep today's four exactly.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MLB from "../fixtures/9799RelatedMlbRail.20260930.json";

const MLB_KEY = "related-by-tag|sport:baseball|league:mlb";

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key === null || key === undefined) {
      return { data: undefined, error: undefined, isLoading: false };
    }
    const flat = Array.isArray(key) ? key.join("|") : String(key);
    return { data: flat === MLB_KEY ? MLB : undefined, error: undefined, isLoading: false };
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

function render(props: Record<string, unknown>): string {
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:baseball", "league:mlb"],
      excludeId: 15321946,
      excludeType: "event",
      limit: 4,
      title: "More MLB",
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
  "MLB World Series Winner",
  "MLB World Series Champion 2026",
  "AL Reliever of the Year Winner?",
  "MLB: AL Platinum Glove Winner",
];

describe("#9799 — the rail beside Cubs @ Padres", () => {
  it("STRAWMAN: with no conferences it deals two AL awards", () => {
    expect(drawnTitles(render({}))).toEqual(TODAY);
  });

  it("drops the AL awards and deals the NL pennant in their seat", () => {
    const titles = drawnTitles(render({ conferences: ["National League", "National League"] }));
    expect(titles).toEqual([
      "MLB World Series Winner",
      "MLB World Series Champion 2026",
      "National League Champion",
      "MLB Postseason: World Series MVP",
    ]);
    expect(titles.join(" ")).not.toMatch(/\bAL\b|American League/);
  });

  it("still draws four and says four", () => {
    const html = render({ conferences: ["National League", "National League"] });
    expect(html).toContain('data-count="4"');
  });
});

describe("#9799 — the pages the filter must leave alone", () => {
  it("an interleague game keeps today's four", () => {
    expect(drawnTitles(render({ conferences: ["National League", "American League"] }))).toEqual(TODAY);
  });

  it("a side with no conference keeps today's four", () => {
    expect(drawnTitles(render({ conferences: ["National League", null] }))).toEqual(TODAY);
  });

  it("an AL game keeps its AL awards and drops the NL pennant", () => {
    const titles = drawnTitles(
      render({ conferences: ["American League", "American League"], limit: 6 })
    );
    expect(titles).toContain("AL Reliever of the Year Winner?");
    expect(titles).not.toContain("National League Champion");
  });
});
