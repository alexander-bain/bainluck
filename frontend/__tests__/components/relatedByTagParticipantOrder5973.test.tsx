/**
 * #5973 — WHAT THE RAIL DRAWS, ON THE PAYLOAD PRODUCTION SERVED.
 *
 * The companion to `__tests__/lib/railParticipantOrder5973.test.ts`. That file
 * pins the ordering rule; this one pins the thing a reader sees, and it does it
 * on a captured payload rather than a hand-built one — the whole question is
 * what the feed actually returns for a league tag, and that is not mine to
 * invent. (A malformed hand-built fake is also how you get a helper's
 * "unknown" branch and read it as a principled refusal.)
 *
 * `5973RelatedMlbRail.20260922.json` is `?tags=["sport:baseball","league:mlb"]`
 * at the rail's own fetch size (`limit + 5` = 9), captured 2026-09-22. Its rank
 * order is:
 *
 *   0 MLB World Series Winner            Dodgers · Brewers · Rays
 *   1 MLB World Series Champion 2026     Dodgers · Brewers · Rays
 *   2 MLB: AL Platinum Glove Winner      Witt Jr. · Rafaela · Dingler
 *   3 MLB: AL Comeback Player of the Year
 *   4 AL Reliever of the Year Winner?
 *   5 MLB: 2026 AL Central Champion      Guardians · White Sox · DETROIT TIGERS
 *   6 MLB: 2026 AL West Champion
 *   7 National League Champion           Dodgers · Milwaukee · Atlanta
 *   8 American League Champion
 *
 * On `Washington Nationals v Detroit Tigers` the one card of the nine that
 * names a side of the match sits at rank 5 — outside a four-card rail. That is
 * the defect in one line, and the BEFORE is rendered below rather than
 * described.
 *
 * ## The two cases that keep this honest
 *
 * The same fixture is also the negative control. On `Milwaukee Brewers v
 * Philadelphia Phillies` the two cards that name the Brewers are ALREADY ranks
 * 0 and 1, so the rail must not move — and `National League Champion` prints
 * the outcome `Milwaukee`, not `Milwaukee Brewers`, so it must not be promoted
 * on a partial name.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MLB from "../fixtures/5973RelatedMlbRail.20260922.json";

const MLB_KEY = "related-by-tag|sport:baseball|league:mlb";

let responses: Record<string, unknown> = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key === null || key === undefined) {
      return { data: undefined, error: undefined, isLoading: false };
    }
    const flat = Array.isArray(key) ? key.join("|") : String(key);
    return { data: responses[flat], error: undefined, isLoading: false };
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

function render(props: Record<string, unknown>): string {
  responses = { [MLB_KEY]: MLB };
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["sport:baseball", "league:mlb"],
      excludeId: 15316847,
      excludeType: "event",
      limit: 4,
      title: "More MLB",
      ...props,
    } as never)
  );
}

/** The card titles the rail drew, in the order it drew them. */
function drawnTitles(markup: string): string[] {
  return Array.from(markup.matchAll(/data-testid="related-card"[\s\S]*?<span class="min-w-0 text-\[14px\][^"]*">([^<]*)</g)).map(
    (m) => m[1].replace(/&#x27;|&apos;/g, "'").replace(/&amp;/g, "&").trim()
  );
}

describe("#5973 — the rail beside a Nationals v Tigers game", () => {
  it("STRAWMAN: with no participants it deals four cards, none about this game", () => {
    /* Exactly today's behaviour, and the reason the issue was filed: the feed's
       generic rank is the same on every MLB page. */
    const titles = drawnTitles(render({}));

    expect(titles).toEqual([
      "MLB World Series Winner",
      "MLB World Series Champion 2026",
      "MLB: AL Platinum Glove Winner",
      "MLB: AL Comeback Player of the Year",
    ]);
    expect(titles).not.toContain("MLB: 2026 AL Central Champion");
  });

  it("lifts the one card naming the Tigers into the rail", () => {
    const titles = drawnTitles(render({ preferNames: ["washington nationals", "detroit tigers"] }));

    expect(titles[0]).toBe("MLB: 2026 AL Central Champion");
    // The rest keep the feed's own rank behind it, and the rail is still four.
    expect(titles).toEqual([
      "MLB: 2026 AL Central Champion",
      "MLB World Series Winner",
      "MLB World Series Champion 2026",
      "MLB: AL Platinum Glove Winner",
    ]);
  });

  it("still draws four cards and still says four", () => {
    /* The count in the heading is rendered from `items.length`. A sort that
       changed it would mean the sort had stopped being a sort. */
    const html = render({ preferNames: ["washington nationals", "detroit tigers"] });
    expect(html).toContain('data-count="4"');
    expect(html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ")).toContain("More MLB · 4");
  });
});

describe("#5973 — the cases the rail must leave alone", () => {
  it("does not reorder when the naming cards are already on top", () => {
    /* Brewers v Phillies: ranks 0 and 1 both print `Milwaukee Brewers`. */
    const before = drawnTitles(render({}));
    const after = drawnTitles(
      render({ preferNames: ["milwaukee brewers", "philadelphia phillies"] })
    );
    expect(after).toEqual(before);
  });

  it("does not promote `National League Champion` on the outcome `Milwaukee`", () => {
    /* Rank 7 prints `Milwaukee`, a partial name. Promoting on it would be the
       start of the substring matching that `Connecticut Sun` makes unsafe. */
    const titles = drawnTitles(
      render({ preferNames: ["milwaukee brewers", "philadelphia phillies"] })
    );
    expect(titles).not.toContain("National League Champion");
  });

  it("is untouched by a page that passes no participants at all", () => {
    /* Every other caller of this component — the futures page — has no match to
       prefer, and must keep the order it has today. */
    expect(drawnTitles(render({ preferNames: [] }))).toEqual(drawnTitles(render({})));
  });
});
