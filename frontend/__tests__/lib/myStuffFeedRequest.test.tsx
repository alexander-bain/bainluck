/**
 * ux/1070 item 5, CERT-942's required repair — the request in the middle.
 *
 * ═══ THE DEFECT THIS EXISTS FOR ═══
 *
 * Item 5 shipped as no visible change at all, and both halves of it passed their
 * own tests while it did.
 *
 *   * the backend admitted this week's golf and tennis to My Stuff, and
 *     `test_my_stuff_followed_sport_futures_1070.py` proved it, 53/53;
 *   * the page knew how to find those markets in the payload and render them,
 *     and `myStuffSections.test.ts` proved that, 12/12;
 *   * and the request between them said `include_futures: false`, so
 *     `_score_futures` never ran on this surface and the payload contained no
 *     futures for either side to be right about.
 *
 * CERT-942 blocked it: *"the page still calls `fetchFeed(... include_futures:
 * false)`, the API serializes that flag, and the backend skips `_score_futures`;
 * `followedSportItems` therefore receives none of the 23 claimed markets."*
 * Correct, and the reason it got that far is that producer and consumer were
 * tested separately — the classic shape where every part is green and the whole
 * does nothing.
 *
 * ═══ WHAT THIS TEST DOES DIFFERENTLY ═══
 *
 * It runs the CHAIN, not the parts, and every link is the real one:
 *
 *   1. the page's own params object (`MY_STUFF_FEED_PARAMS`, imported by the
 *      page — not a copy retyped here, which would pass while the page sent
 *      something else),
 *   2. through the real `fetchFeed`, so the URL is the one the browser sends,
 *   3. against a stubbed transport returning a real-shaped golf market,
 *   4. into the real `followedSportFutures`, the page's own partition,
 *   5. into a real `FeedCard` render.
 *
 * Break any link — reinstate the flag, drop the section, mislabel the category —
 * and this goes red.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { feedItemHasRenderableContent } from "@/components/discover/utils";
import { fetchFeed } from "@/lib/api";
import {
  MY_STUFF_FEED_PARAMS,
  followedSportFutures,
} from "@/lib/myStuffSections";
import type { FeedItem } from "@/lib/types";

// Same two mocks every FeedCard render test uses: `next/link` needs a router and
// the card reads the analytics context on click. Neither is what is under test.
jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

/**
 * The Omega European Masters Winner as production holds it (2026-09-04): the
 * exact market Alex could not see, 193 golfers, resolving Sunday.
 */
const GOLF_FUTURE = {
  type: "futures",
  score: 62,
  reason: "followed sport",
  headline: null,
  data: {
    id: 90210,
    name: "Omega European Masters - Winner",
    llm_sport_category: "golf",
    resolution_date: "2026-09-07T03:59:00Z",
    market_tier: 1,
    // `top_outcomes`, and the name is load-bearing: `FeedCard`'s fail-closed
    // guard reads exactly this field, so a market carrying `outcomes` instead
    // renders as nothing at all. Six of the eighteen in-window golf markets on
    // production carry no outcomes, which is why the page filters on the same
    // guard rather than trusting the partition.
    top_outcomes: [
      { name: "Thriston Lawrence", probability: 0.14, movement: 0.01 },
      { name: "Matt Wallace", probability: 0.09, movement: -0.01 },
    ],
  },
};

/** A team-sport future, which `my-team-futures` renders and this page must not. */
const BASEBALL_FUTURE = {
  type: "futures",
  score: 70,
  reason: "your team",
  headline: null,
  data: {
    id: 90211,
    name: "AL Pennant Winner",
    llm_sport_category: "baseball",
    resolution_date: "2026-10-20T00:00:00Z",
    market_tier: 1,
    top_outcomes: [{ name: "Boston Red Sox", probability: 0.18, movement: 0.02 }],
  },
};

let lastUrl = "";

beforeEach(() => {
  lastUrl = "";
  // Stub the transport, not `fetchFeed` — the URL construction under test is
  // inside `fetchFeed`, so mocking it would delete the thing being measured.
  global.fetch = jest.fn(async (input: RequestInfo | URL) => {
    lastUrl = String(input);
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ items: [GOLF_FUTURE, BASEBALL_FUTURE], total: 2 }),
    } as unknown as Response;
  }) as unknown as typeof fetch;
});

describe("the request My Stuff actually sends", () => {
  it("does not switch futures off", async () => {
    // THE BLOCKED DEFECT, in one assertion. `fetchFeed` serializes only the
    // `false` case (`if (params?.include_futures === false)`), so the bug has
    // exactly one spelling in the URL and this is it.
    await fetchFeed(MY_STUFF_FEED_PARAMS);

    expect(lastUrl).not.toContain("include_futures=false");
    expect(lastUrl).not.toContain("include_futures");
  });

  it("still asks for the viewer's own page and nothing global", () => {
    // The other half of the same URL. Turning futures back on must not have
    // turned My Stuff into Discover — `my_teams_only` is what scopes both the
    // events half and the follow-gated futures half to this viewer.
    expect(MY_STUFF_FEED_PARAMS.my_teams_only).toBe(true);
  });

  it("sends my_teams_only on the wire, not just in the object", async () => {
    await fetchFeed(MY_STUFF_FEED_PARAMS);

    expect(lastUrl).toContain("my_teams_only=true");
    expect(lastUrl).toContain("limit=100");
  });
});

describe("end to end: the request, the partition, the card", () => {
  it("a golf market survives the whole chain and renders", async () => {
    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);

    // The payload the page receives really does carry it...
    expect(payload.items).toHaveLength(2);

    // ...the page's own partition really does select it...
    const section = followedSportFutures(payload.items as unknown as FeedItem[]);
    expect(section.map((i) => (i.data as { id: number }).id)).toEqual([90210]);

    // ...and a card really does draw it.
    const html = renderToStaticMarkup(
      <FeedCard item={section[0] as FeedItem} category="golf" />,
    );
    expect(html).toContain("Omega European Masters");
  });

  it("the team-sport future is dropped, exactly once, by the page", async () => {
    // Not a duplicate of the unit test: there it is a hand-built item, here it
    // arrives through the real request beside the golf one. The AL pennant is
    // rendered by "Your Teams' Odds" from its own endpoint, merged and laddered
    // across sources; drawing it here as well would print it twice, and only
    // one of the two knows how to merge.
    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);
    const section = followedSportFutures(payload.items as unknown as FeedItem[]);

    expect(section.some((i) => (i.data as { id: number }).id === 90211)).toBe(false);
  });

  it("an empty futures half is not an error, just an empty section", async () => {
    // The common case for someone who follows only team sports. It must render
    // as absence, and it must not throw on the way there.
    (global.fetch as jest.Mock).mockImplementationOnce(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ items: [BASEBALL_FUTURE], total: 1 }),
    }));

    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);
    expect(followedSportFutures(payload.items as unknown as FeedItem[])).toEqual([]);
  });
});

describe("turning futures back on does not delete the pinned ones", () => {
  /**
   * The second bug, which the first repair would have caused.
   *
   * `missingPinnedFuturesIds` is `pinnedFuturesIds` minus the futures the feed
   * already carries — a dedupe that was written when the feed carried NO
   * futures on this page, so the subtracted set was always empty and every
   * pinned market was fetched and drawn.
   *
   * Switch futures on and read that set as "every futures item in the feed",
   * and a pinned AL Pennant is suddenly subtracted — while the section loop
   * drops all futures and `followedSportFutures` keeps only the non-team
   * sports. Nothing draws it. A user's pinned market silently disappears, and
   * no test in the suite was watching, because the whole mechanism was inert.
   *
   * So the set is what the page RENDERS from the feed, which is the
   * followed-sport list. These two tests are that distinction.
   */
  const renderedFromFeed = (items: FeedItem[]) =>
    new Set(followedSportFutures(items).map((i) => (i.data as { id: number }).id));

  it("a pinned TEAM future is still fetched, because nothing else draws it", async () => {
    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);
    const drawn = renderedFromFeed(payload.items as unknown as FeedItem[]);

    // 90211 is the AL Pennant. It is in the feed, and it must NOT be treated as
    // already-drawn — "Your Teams' Odds" comes from a different endpoint, and
    // the Pinned block is the only place a pinned copy can appear.
    expect(drawn.has(90211)).toBe(false);
  });

  it("a pinned GOLF future is not fetched twice, because the section draws it", async () => {
    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);
    const drawn = renderedFromFeed(payload.items as unknown as FeedItem[]);

    expect(drawn.has(90210)).toBe(true);
  });

  it("the page subtracts the rendered list, not every futures item", () => {
    const src = require("fs").readFileSync(
      require("path").join(process.cwd(), "app/my-stuff/page.tsx"),
      "utf8",
    );

    // The regression has one spelling — rebuilding the set by filtering the raw
    // items on `type === "futures"` — and this is it.
    expect(src).toContain(
      "new Set(followedSportItems.map(i => (i.data as FeedFuturesData).id))",
    );
  });
});

describe("the section counts only what will draw", () => {
  it("an outcome-less market is not counted above an empty grid", async () => {
    // Six of the eighteen in-window golf markets on production carry zero
    // outcomes (the "DP World Tour: European Masters" rows duplicating the
    // Omega ones). `FeedCard` returns null for them, so counting them would
    // print a heading and a number over blank space.
    (global.fetch as jest.Mock).mockImplementationOnce(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        items: [
          GOLF_FUTURE,
          {
            ...GOLF_FUTURE,
            data: {
              ...GOLF_FUTURE.data,
              id: 90212,
              name: "DP World Tour: European Masters Winner",
              top_outcomes: [],
            },
          },
        ],
        total: 2,
      }),
    }));

    const payload = await fetchFeed(MY_STUFF_FEED_PARAMS);
    const partitioned = followedSportFutures(payload.items as unknown as FeedItem[]);
    // The partition itself is about sport shape and keeps both...
    expect(partitioned).toHaveLength(2);

    // ...and the page's fail-closed filter is what drops the empty one.
    const drawable = partitioned.filter(feedItemHasRenderableContent);
    expect(drawable.map((i) => (i.data as { id: number }).id)).toEqual([90210]);
  });

  it("the page applies that filter", () => {
    const src = require("fs").readFileSync(
      require("path").join(process.cwd(), "app/my-stuff/page.tsx"),
      "utf8",
    );

    expect(src).toContain(
      "followedSportFutures(feedData.items).filter(feedItemHasRenderableContent)",
    );
  });
});

describe("the params have one owner", () => {
  it("the page imports them rather than writing its own", () => {
    // The failure this catches is the one that produced CERT-942: a test that
    // asserts a correct URL built from a literal it wrote itself, while the
    // page sends a different one. Reading the page's source is the only way to
    // assert the coupling from here, since the page cannot be mounted in jsdom.
    const src = require("fs").readFileSync(
      require("path").join(process.cwd(), "app/my-stuff/page.tsx"),
      "utf8",
    );

    expect(src).toContain("fetchFeed(MY_STUFF_FEED_PARAMS)");

    // Matched as a CALL ARGUMENT, not as a bare substring. The page carries a
    // comment explaining why the flag was removed, and that comment names the
    // flag — a `not.toContain("include_futures: false")` is red on the correct
    // file, which is a test that fails on the fix and passes on nothing useful.
    expect(src).not.toMatch(/fetchFeed\([^)]*include_futures/);
  });
});
