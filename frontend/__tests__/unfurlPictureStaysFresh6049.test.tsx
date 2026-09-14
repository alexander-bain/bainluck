/**
 * #6049 — A PASTED LINK'S PICTURE STOPS BEING FROZEN UNTIL THE NEXT DEPLOY.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 02:57-03:05Z ═══
 *
 * `/futures/60276241`, one instant, crawler UA: the TEXT said "Above 1 inch
 * 19%" and the PICTURE drew a 96px "26%" over a 26% bar. `/api/futures/60276241`
 * said 0.19, `status open` — the picture was the liar.
 *
 * It was not a 60-second skew. Both image routes answered
 *
 *   cache-control: public, immutable, no-transform, max-age=31536000
 *
 * measured on `/events/1/opengraph-image` at `x-vercel-cache: MISS`, `age: 0`,
 * which is what proves the header is the ORIGIN's rather than a CDN rule. One
 * year, immutable, under a URL whose only varying part is a DEPLOYMENT hash
 * (`?abc750316894a8f6` was served by two unrelated markets at 02:58Z and changed
 * for both at the v4509 deploy). So the first crawler to fetch a market after a
 * deploy fixed that market's number for every reader until the next deploy.
 *
 * ═══ WHAT THIS FILE ASSERTS, AND IN WHICH DIRECTION ═══
 *
 * Three things, because the fix has three independent ways to stop working.
 *
 * 1. THE FRAMEWORK CONTRACT. The whole fix rests on one line of next@14.2.35 —
 *    `ImageResponse` spreads `...options.headers` AFTER its own hardcoded
 *    default. If a Next upgrade reorders that spread, every route below keeps
 *    compiling, keeps passing its wiring test, and production silently refreezes
 *    for a year. So the contract is asserted against the REAL `next/og`, both
 *    halves of it: that the immutable default is still what you get with no
 *    header, and that ours still wins. (Constructing an `ImageResponse` does not
 *    render: the satori call lives in the body stream, which nothing here reads.
 *    That is why this can be a unit test at all.)
 *
 * 2. THE WIRING, BOTH DIRECTIONS (gotcha #43). Every one of the four call sites
 *    across the two routes gets the window its content earns. Asserting only
 *    "the live card revalidates" would be satisfied by deleting the long window
 *    everywhere, so the settled cards are asserted to KEEP theirs; asserting
 *    only "settled is long" would be satisfied by the unfixed tree.
 *
 * 3. THE VALUES. A "moving" window that someone widens to a day would pass both
 *    of the above while restoring the defect in all but name, so the property
 *    that actually matters — this picture is revalidated on a scale of a minute,
 *    and is never `immutable` — is asserted on the constant itself.
 */

import React from "react";

/** Every `new ImageResponse(...)` the route under test made, args intact. */
const imageResponseCalls: { element: React.ReactElement; options: unknown }[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement, options: unknown) {
    imageResponseCalls.push({ element, options });
    return { __stub: "ImageResponse" };
  },
}));

import EventsOgImage from "@/app/events/[id]/opengraph-image";
import FuturesOgImage from "@/app/futures/[id]/opengraph-image";
import {
  UNFURL_CACHE_MOVING,
  UNFURL_CACHE_SETTLED,
  unfurlImageCacheControl,
} from "@/lib/unfurlImageCache";

/* ────────────────────────── 1. the framework contract ────────────────────── */

/**
 * The exact string next@14.2.35 hardcodes. Written out rather than imported
 * because the point of this block is to notice if the framework's own answer
 * changes — a constant we share with it could not.
 */
const NEXT_DEFAULT_IMMUTABLE = "public, immutable, no-transform, max-age=31536000";

describe("#6049 the assumption the fix rests on: next/og's own header handling", () => {
  const realNextOg = () => jest.requireActual("next/og") as {
    ImageResponse: new (element: React.ReactElement, options?: unknown) => Response;
  };
  const element = React.createElement("div", null, "unfurl");

  it("still defaults a picture to a one-year immutable cache when nothing is passed", () => {
    const { ImageResponse } = realNextOg();
    const response = new ImageResponse(element, { width: 10, height: 10 });
    expect(response.headers.get("cache-control")).toBe(NEXT_DEFAULT_IMMUTABLE);
  });

  it("still lets an explicit cache-control override that default", () => {
    const { ImageResponse } = realNextOg();
    const response = new ImageResponse(element, {
      width: 10,
      height: 10,
      headers: { "cache-control": UNFURL_CACHE_MOVING },
    });
    expect(response.headers.get("cache-control")).toBe(UNFURL_CACHE_MOVING);
  });

  it("still sends the picture as a PNG when we pass headers of our own", () => {
    // `...options.headers` spreads over `content-type` too, so an override that
    // was ever written as a whole-header replacement would break the image.
    const { ImageResponse } = realNextOg();
    const response = new ImageResponse(element, {
      width: 10,
      height: 10,
      headers: { "cache-control": UNFURL_CACHE_SETTLED },
    });
    expect(response.headers.get("content-type")).toBe("image/png");
  });
});

/* ─────────────────────────────── 2. the wiring ───────────────────────────── */

function mockApi(status: number, body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/** The cache-control the route handed `ImageResponse` on its only call. */
function servedCacheControl(): string | undefined {
  expect(imageResponseCalls).toHaveLength(1);
  const options = imageResponseCalls[0].options as
    | { headers?: Record<string, string>; width?: number; height?: number }
    | undefined;
  // The size must survive the change — a card that lost its dimensions would
  // still satisfy every cache assertion in this file.
  expect(options?.width).toBe(1200);
  expect(options?.height).toBe(630);
  return options?.headers?.["cache-control"];
}

const OPEN_MARKET = {
  id: 60276241,
  name: "Rainfall in Dallas for September 2026",
  status: "open",
  llm_sport_category: "weather",
  outcome_count: 7,
  outcomes: [{ name: "Above 1 inch", probability: 0.19 }],
};

const RESOLVED_MARKET = {
  ...OPEN_MARKET,
  status: "resolved",
  outcomes: [{ name: "Above 1 inch", probability: 1, is_winner: true }],
};

const SCHEDULED_GAME = {
  id: 15304803,
  home_team: "Chicago Cubs",
  away_team: "Pittsburgh Pirates",
  status: "scheduled",
  sport_key: "baseball_mlb",
  current_odds: {
    home_probability: 0.53,
    away_probability: 0.47,
    home_rendered_percent: 53,
    away_rendered_percent: 47,
  },
};

const FINAL_GAME = { ...SCHEDULED_GAME, status: "completed" };
const CLOSED_GAME = { ...SCHEDULED_GAME, status: "closed" };

type Case = {
  name: string;
  Image: (args: { params: { id: string } }) => Promise<unknown>;
  api: { status: number; body: unknown };
  expected: string;
};

const CASES: readonly Case[] = [
  {
    name: "/futures/[id] an OPEN market — the price that moved under a frozen picture",
    Image: FuturesOgImage as Case["Image"],
    api: { status: 200, body: OPEN_MARKET },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "/futures/[id] a RESOLVED market — a winner keeps the long window",
    Image: FuturesOgImage as Case["Image"],
    api: { status: 200, body: RESOLVED_MARKET },
    expected: UNFURL_CACHE_SETTLED,
  },
  {
    name: "/futures/[id] a dead link — a claim we may have to retract",
    Image: FuturesOgImage as Case["Image"],
    api: { status: 404, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "/events/[id] a SCHEDULED game — its win probability still moves",
    Image: EventsOgImage as Case["Image"],
    api: { status: 200, body: SCHEDULED_GAME },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "/events/[id] a COMPLETED game — a final score keeps the long window",
    Image: EventsOgImage as Case["Image"],
    api: { status: 200, body: FINAL_GAME },
    expected: UNFURL_CACHE_SETTLED,
  },
  {
    name: "/events/[id] a CLOSED game — the other half of the Final predicate",
    Image: EventsOgImage as Case["Image"],
    api: { status: 200, body: CLOSED_GAME },
    expected: UNFURL_CACHE_SETTLED,
  },
  {
    name: "/events/[id] a dead link — a claim we may have to retract",
    Image: EventsOgImage as Case["Image"],
    api: { status: 404, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
];

describe("#6049 every unfurl picture states how long it may be kept", () => {
  it.each(CASES)("$name", async ({ Image, api, expected }) => {
    imageResponseCalls.length = 0;
    mockApi(api.status, api.body);

    await Image({ params: { id: "60276241" } });

    // Named rather than bare so a failure says WHICH window was served.
    const label = expected === UNFURL_CACHE_SETTLED ? "settled" : "moving";
    const served = servedCacheControl();
    const servedLabel =
      served === UNFURL_CACHE_SETTLED ? "settled" : served === UNFURL_CACHE_MOVING ? "moving" : served;
    expect(servedLabel).toBe(label);
  });

  it("never serves next/og's immutable default from any of them", async () => {
    for (const { Image, api } of CASES) {
      imageResponseCalls.length = 0;
      mockApi(api.status, api.body);
      await Image({ params: { id: "60276241" } });
      expect(servedCacheControl()).not.toBe(NEXT_DEFAULT_IMMUTABLE);
    }
  });
});

/* ─────────────────────────────── 3. the values ───────────────────────────── */

function directive(cacheControl: string, name: string): string | undefined {
  return cacheControl
    .split(",")
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name}=`));
}

function seconds(cacheControl: string, name: string): number | undefined {
  const found = directive(cacheControl, name);
  return found ? Number(found.split("=")[1]) : undefined;
}

describe("#6049 the windows themselves", () => {
  it("revalidates a moving picture on the same scale as the text beside it", () => {
    // The text half reads the API through `next: { revalidate: 60 }`. A shared
    // cache holding the picture materially longer is the defect in slower form,
    // so this asserts the BOUND, not the literal 60 — a future tightening is
    // fine, a widening to an hour is not.
    expect(seconds(UNFURL_CACHE_MOVING, "s-maxage")).toBeLessThanOrEqual(60);
    expect(seconds(UNFURL_CACHE_MOVING, "stale-while-revalidate")).toBeLessThanOrEqual(60);
  });

  it("lets a settled picture be kept for a long time, but not forever", () => {
    // The other direction: the point of the settled window is that it is cheap,
    // so a well-meaning tightening to 60s everywhere should be noticed.
    expect(seconds(UNFURL_CACHE_SETTLED, "s-maxage")).toBeGreaterThanOrEqual(600);
    // Finite is the whole reason it is not `immutable`: a settlement correction
    // has to reach the picture without a deploy.
    expect(seconds(UNFURL_CACHE_SETTLED, "s-maxage")).toBeLessThanOrEqual(86400);
  });

  it("marks neither window immutable, on either route", () => {
    for (const window of [UNFURL_CACHE_MOVING, UNFURL_CACHE_SETTLED]) {
      expect(directive(window, "immutable")).toBeUndefined();
      // A year is the value that caused #6049; no window may reach it again.
      expect(seconds(window, "max-age")).toBe(0);
    }
  });

  it("keeps both windows shared-cacheable, so a paste is not a cold render", () => {
    for (const window of [UNFURL_CACHE_MOVING, UNFURL_CACHE_SETTLED]) {
      expect(directive(window, "public")).toBe("public");
      expect(seconds(window, "stale-while-revalidate")).toBeGreaterThan(0);
    }
  });

  it("routes each kind to its own window", () => {
    expect(unfurlImageCacheControl("moving")).toBe(UNFURL_CACHE_MOVING);
    expect(unfurlImageCacheControl("settled")).toBe(UNFURL_CACHE_SETTLED);
    expect(UNFURL_CACHE_MOVING).not.toBe(UNFURL_CACHE_SETTLED);
  });
});
