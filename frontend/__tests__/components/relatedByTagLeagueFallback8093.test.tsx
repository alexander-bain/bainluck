/**
 * #8093 — THE RAIL FALLS BACK, AND ONLY WHEN IT IS EMPTY.
 *
 * The companion to `__tests__/lib/relatedRailQuery8093.test.ts`. That file pins
 * the QUESTION a WNBA game page asks; this one pins what `RelatedByTag` does
 * with the two answers.
 *
 * ## The payloads are the ones production served
 *
 * Both fixtures were captured from `api.bainluck.com/api/feed` on 2026-09-22 at
 * the rail's own fetch size (`limit + 5` = 9):
 *
 *   - `8093RelatedWideBasketball` — `?tags=["sport:basketball"]`, the query the
 *     page shipped. Nine markets, of which `NBA: 2027 Champion`,
 *     `NBA: 2026 NBA Cup Winner` and `NBA Championship Winner` are the three
 *     cards a reader met on a WNBA fixture. **This is the BEFORE, and it is
 *     rendered below rather than described**, so the improvement is a measured
 *     difference and not a claim.
 *   - `8093RelatedNarrowWnba` — `?tags=["sport:basketball","league:wnba"]`,
 *     exactly four markets, every one of them WNBA.
 *
 * A hand-built payload would have proved nothing here: the whole question is
 * what the feed returns for two real tag filters, and the answer to that is not
 * mine to invent.
 *
 * ## Why the fallback needs guarding as hard as the fix
 *
 * A blanket league narrow would take the rail off a Champions League tie and
 * off every Grand Slam match page — both measured at ZERO narrowed items. The
 * fallback is what makes the fix safe to ship site-wide, and it is also the one
 * path that can put an NBA card back on a WNBA page. So it is pinned in both
 * directions: it fires when the narrow query is empty, and it is **never
 * requested at all** when the narrow query has anything in it.
 *
 * The SWR mock is key-aware for that reason. A mock that ignores its key can
 * only answer "what did the component draw"; the assertion that matters most
 * here is "what did the component ASK FOR", and only the key records that.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import WIDE from "../fixtures/8093RelatedWideBasketball.20260922.json";
import NARROW from "../fixtures/8093RelatedNarrowWnba.20260922.json";

const NARROW_KEY = "related-by-tag|sport:basketball|league:wnba";
const WIDE_KEY = "related-by-tag|sport:basketball";

/** Key → payload for this render. A key that is absent from the map answers
 *  `undefined`, which is SWR's "still in flight" — not an empty result. */
let responses: Record<string, unknown> = {};
/** Every non-null key the component subscribed to, in order. */
let requested: string[] = [];

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key === null || key === undefined) {
      return { data: undefined, error: undefined, isLoading: false };
    }
    const flat = Array.isArray(key) ? key.join("|") : String(key);
    requested.push(flat);
    return { data: responses[flat], error: undefined, isLoading: false };
  },
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

function render(props: Record<string, unknown>, payloads: Record<string, unknown>): string {
  responses = payloads;
  requested = [];
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      excludeId: 15316933,
      excludeType: "event",
      limit: 4,
      ...props,
    } as never)
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

const WNBA_PAGE = {
  tags: ["sport:basketball", "league:wnba"],
  fallbackTags: ["sport:basketball"],
  title: "More WNBA",
  fallbackTitle: "More Basketball",
};

describe("#8093 — a WNBA game page's rail", () => {
  /* THE BEFORE, RENDERED. The pre-fix page asked one question and got this. */
  it("STRAWMAN: the query it used to ask deals three NBA cards", () => {
    const html = render(
      { tags: ["sport:basketball"], title: "More Basketball" },
      { [WIDE_KEY]: WIDE }
    );
    const text = visibleText(html);

    expect(text).toContain("More Basketball · 4");
    expect(text).toContain("NBA: 2027 Champion");
    expect(text).toContain("NBA: 2026 NBA Cup Winner");
    expect(text).toContain("NBA Championship Winner");
    // One of the four is the league the reader is actually on.
    expect(text).toContain("WNBA: 2026 Champion");
  });

  it("AFTER: draws four WNBA markets and no NBA-only card", () => {
    const html = render(WNBA_PAGE, { [NARROW_KEY]: NARROW });
    const text = visibleText(html);

    expect(text).toContain("More WNBA · 4");
    expect(text).toContain("WNBA: 2026 Champion");
    expect(text).toContain("WNBA: Assists Per Game Leader");

    /* The acceptance, stated as the issue states it. `NBA: ` with the colon
       rather than the bare token, because `WNBA: 2026 Champion` contains the
       substring `NBA` and an assertion that cannot tell those apart is an
       assertion that cannot fail the right way. */
    expect(text).not.toContain("NBA: 2027 Champion");
    expect(text).not.toContain("NBA Championship Winner");
    for (const card of text.split("WNBA").join("").split("·")) {
      expect(card).not.toMatch(/\bNBA\b/);
    }
  });

  /* FAIL-CLOSED, AND THE DIRECTION THAT MATTERS MOST: a narrow result that has
     anything in it must never cause the wide query to be requested. If this
     ever goes green-but-wrong, every WNBA page pays a second request AND can
     draw the cards this ship exists to remove. */
  it("never asks the wide query when the narrow one answered", () => {
    render(WNBA_PAGE, { [NARROW_KEY]: NARROW });

    expect(requested).toContain(NARROW_KEY);
    expect(requested).not.toContain(WIDE_KEY);
  });

  it("falls back to the sport rail when the league has nothing at all", () => {
    const html = render(WNBA_PAGE, {
      [NARROW_KEY]: { items: [] },
      [WIDE_KEY]: WIDE,
    });
    const text = visibleText(html);

    // It asked the narrow question FIRST and the wide one only after.
    expect(requested.indexOf(NARROW_KEY)).toBeLessThan(requested.indexOf(WIDE_KEY));

    // Four cards rather than an empty space where a rail used to be — the
    // Champions League and Grand Slam case, which measured 0 narrowed items.
    expect(text).toContain("NBA: 2027 Champion");

    // And the heading came with the scope that actually answered. A rail drawn
    // from all of basketball may not be headed `More WNBA`.
    expect(text).toContain("More Basketball · 4");
    expect(text).not.toContain("More WNBA");
  });

  /* "Still loading" is not "empty". Firing the fallback while the first request
     is in flight would make every page pay two requests for a fallback almost
     none of them use, and would race a wide answer onto the page ahead of the
     narrow one. */
  it("does not fire the fallback while the narrow query is in flight", () => {
    const html = render(WNBA_PAGE, { [WIDE_KEY]: WIDE });

    expect(requested).toContain(NARROW_KEY);
    expect(requested).not.toContain(WIDE_KEY);
    expect(html).toBe("");
  });

  /* The futures page passes no fallback (a market has no league to ask about),
     and must behave exactly as it did before this change. */
  it("renders nothing on an empty result when no fallback was offered", () => {
    const html = render(
      { tags: ["sport:basketball"], title: "More Basketball" },
      { [WIDE_KEY]: { items: [] } }
    );

    expect(html).toBe("");
    expect(requested).toEqual([WIDE_KEY]);
  });

  /* An "empty" narrow result is empty as a READER would count it, not as the
     payload length does: a response carrying only the current event, or only
     item types this component cannot draw, leaves the rail blank and must
     therefore reach the fallback. */
  it("counts a result of nothing-renderable as empty and falls back", () => {
    const html = render(WNBA_PAGE, {
      [NARROW_KEY]: {
        items: [
          { type: "event", data: { id: 15316933, away_team: "A", home_team: "B" } },
          { type: "bundle", data: { id: 1 } },
        ],
      },
      [WIDE_KEY]: WIDE,
    });

    expect(requested).toContain(WIDE_KEY);
    expect(visibleText(html)).toContain("More Basketball · 4");
  });
});
