/**
 * #6166 — THE FOUR UNFURL PICTURES #6049 DID NOT REACH STOP FREEZING.
 *
 * FOUR, not the three #6166 was filed with. `/hub/[competition]` was called
 * immune because it quotes no probability; the population scan at the bottom of
 * this file refused that, and the route's own header explains why it was right
 * to — see the comment at its `ImageResponse` call. The test that enumerates
 * from the filesystem caught a route the issue had reasoned its way past, which
 * is the entire argument for deriving the population instead of listing it.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 14:08-14:11Z ═══
 *
 * `bainluck.com/sport/baseball/mlb/team/boston-red-sox`, read with a crawler UA
 * at one instant and stable across three reads a minute apart:
 *
 *   og:image        a "6%" championship number, record "81-68"  (md5 5607fc5e…)
 *   og:description  "5%"
 *   GET /api/teams/boston-red-sox   0.0485 -> 5%, record 82-68
 *
 * The picture was a day behind the words beside it. It was NOT a split
 * implementation — `buildTeamShareCopy` and `teamCardCopy` already share
 * `teamHeadline` and `formatShareProbability`, and forcing a CDN MISS with a
 * cache-busting query rendered 5% and 82-68 (md5 ee94b2f0…, reproduced twice).
 * The code was right; the response header was not:
 *
 *   cache-control: public, immutable, no-transform, max-age=31536000
 *
 * That is next/og's own default, under a URL whose only varying part is a
 * DEPLOYMENT hash — the exact defect #6049 diagnosed and fixed. #6049 applied
 * its fix to 2 of the 5 fetching routes.
 *
 * ═══ WHAT THIS FILE ASSERTS THAT #6049's DOES NOT ═══
 *
 * #6049's file already owns the framework contract (that `ImageResponse` still
 * spreads `...options.headers` over its own default) and the window VALUES.
 * Neither is re-asserted here; duplicating them would mean two files to update
 * when next/og changes and two chances to update only one.
 *
 * This file owns the two things that were actually missing.
 *
 * 1. THE WIRING OF THE THREE REMAINING ROUTES, both directions (gotcha #43).
 *    Asserting only "the live card revalidates" would be satisfied by deleting
 *    the long window everywhere, so the one card that EARNS the long window —
 *    an event concept with an authoritative winner — is asserted to keep it.
 *
 * 2. THE POPULATION. This is the guard that would have caught #6166 itself, and
 *    it is the reason this file exists rather than three more rows in #6049's
 *    table. #6049 was correct, merged, and left three routes drawing live
 *    numbers behind a one-year immutable header; every test passed, because a
 *    route nobody listed is a route nobody tested. So the population is
 *    DERIVED from the filesystem rather than listed, and a route that fetches
 *    is required to have the header — including one added next month by someone
 *    who has never read this file.
 */

import fs from "fs";
import path from "path";

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

import ConceptOgImage from "@/app/event/[domain]/[slug]/opengraph-image";
import HubOgImage from "@/app/hub/[competition]/opengraph-image";
import TeamOgImage from "@/app/sport/[sport]/[league]/team/[team]/opengraph-image";
import TournamentOgImage from "@/app/tournaments/[slug]/opengraph-image";
import { UNFURL_CACHE_MOVING, UNFURL_CACHE_SETTLED } from "@/lib/unfurlImageCache";

/** The exact string next@14.2.35 hardcodes when no header is passed. */
const NEXT_DEFAULT_IMMUTABLE = "public, immutable, no-transform, max-age=31536000";

/* ─────────────────────────────── 1. the wiring ───────────────────────────── */

function mockApi(status: number, body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/**
 * The cache-control the route handed `ImageResponse` on its only call.
 *
 * The size assertion is not decoration: a card that lost its dimensions would
 * satisfy every cache assertion in this file, and `unfurlImageOptions` is
 * precisely the seam where width and height could go missing.
 */
function servedCacheControl(): string | undefined {
  expect(imageResponseCalls).toHaveLength(1);
  const options = imageResponseCalls[0].options as
    | { headers?: Record<string, string>; width?: number; height?: number }
    | undefined;
  expect(options?.width).toBe(1200);
  expect(options?.height).toBe(630);
  return options?.headers?.["cache-control"];
}

/* The specimen from the issue, and its neighbours. */
const RED_SOX = {
  team: { name: "Boston Red Sox", sport_key: "baseball_mlb", wins: 82, losses: 68 },
  futures: [],
  championship_path: [{ label: "Pro Baseball Champion", probability: 0.0485 }],
};

const LIVE_CONCEPT = {
  event: { name: "US Open", status: "live", venue: "Flushing Meadows" },
  primary: {
    label: "Men's Singles",
    competitors: [
      { name: "Carlos Alcaraz", probability: 0.62 },
      { name: "Jannik Sinner", probability: 0.38 },
    ],
  },
};

/** `event.status === "settled"` AND an authoritative `won` flag. Terminal. */
const WON_CONCEPT = {
  event: { name: "US Open", status: "settled", venue: "Flushing Meadows" },
  primary: {
    label: "Men's Singles",
    competitors: [
      { name: "Carlos Alcaraz", probability: 1, won: true },
      { name: "Jannik Sinner", probability: 0, won: false },
    ],
  },
};

/**
 * Settled with NO flagged winner — the card that draws "Result not yet
 * confirmed". Our record is incomplete, not the world.
 */
const UNCONFIRMED_CONCEPT = {
  ...WON_CONCEPT,
  primary: {
    label: "Men's Singles",
    competitors: [
      { name: "Carlos Alcaraz", probability: 1, won: false },
      { name: "Jannik Sinner", probability: 0, won: false },
    ],
  },
};

/** No `generated_at`: `payloadIsStale` fails open, so this board is priced. */
const LIVE_TOURNAMENT = {
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  boards: [
    {
      label: "Men's Singles",
      rows: [
        { display_name: "Carlos Alcaraz", probability: 0.62 },
        { display_name: "Jannik Sinner", probability: 0.38 },
      ],
    },
  ],
};

type Case = {
  name: string;
  run: () => Promise<unknown>;
  api: { status: number; body: unknown };
  expected: string;
};

const CONCEPT_PARAMS = { domain: "tennis", slug: "us-open-men-s-singles" };
const TEAM_PARAMS = { sport: "baseball", league: "mlb", team: "boston-red-sox" };

const CASES: readonly Case[] = [
  {
    name: "team — THE SPECIMEN: a record and a championship number that both move",
    run: () => (TeamOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: TEAM_PARAMS }),
    api: { status: 200, body: RED_SOX },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "team — a dead link, a claim we may have to retract",
    run: () => (TeamOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: TEAM_PARAMS }),
    api: { status: 404, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "team — an off-route team, the third verdict and still not terminal",
    run: () =>
      (TeamOgImage as (a: { params: unknown }) => Promise<unknown>)({
        params: { ...TEAM_PARAMS, sport: "basketball" },
      }),
    api: { status: 200, body: RED_SOX },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "tournament — a priced board, the live prices that cannot freeze",
    run: () =>
      (TournamentOgImage as (a: { params: unknown }) => Promise<unknown>)({
        params: { slug: "us-open" },
      }),
    api: { status: 200, body: LIVE_TOURNAMENT },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "tournament — a dead slug, a claim we may have to retract",
    run: () =>
      (TournamentOgImage as (a: { params: unknown }) => Promise<unknown>)({
        params: { slug: "us-open" },
      }),
    api: { status: 404, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "concept — a live field, the forecast that must revalidate",
    run: () =>
      (ConceptOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: CONCEPT_PARAMS }),
    api: { status: 200, body: LIVE_CONCEPT },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "concept — an authoritative winner, the ONE card that earns the long window",
    run: () =>
      (ConceptOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: CONCEPT_PARAMS }),
    api: { status: 200, body: WON_CONCEPT },
    expected: UNFURL_CACHE_SETTLED,
  },
  {
    name: "concept — settled with NO winner: our RECORD is pending, so still moving",
    run: () =>
      (ConceptOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: CONCEPT_PARAMS }),
    api: { status: 200, body: UNCONFIRMED_CONCEPT },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "concept — a dead link, a claim we may have to retract",
    run: () =>
      (ConceptOgImage as (a: { params: unknown }) => Promise<unknown>)({ params: CONCEPT_PARAMS }),
    api: { status: 404, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    name: "hub — a live competition; no number, but a blurb the API still serves",
    run: () =>
      (HubOgImage as (a: { params: unknown }) => Promise<unknown>)({
        params: { competition: "tennis" },
      }),
    api: { status: 200, body: { name: "Tennis", blurb: "Every match, one number." } },
    expected: UNFURL_CACHE_MOVING,
  },
  {
    // The case the "it draws no number, so it is immune" reading would have
    // left frozen for a year: a 5xx during a restart makes this card say a live
    // competition is not on Bain Luck (gotcha #53).
    name: "hub — a 5xx during a restart, the claim this ship most needs to retract",
    run: () =>
      (HubOgImage as (a: { params: unknown }) => Promise<unknown>)({
        params: { competition: "tennis" },
      }),
    api: { status: 503, body: {} },
    expected: UNFURL_CACHE_MOVING,
  },
];

describe("#6166 the four routes #6049 did not reach state how long they may be kept", () => {
  it.each(CASES)("$name", async ({ run, api, expected }) => {
    imageResponseCalls.length = 0;
    mockApi(api.status, api.body);

    await run();

    // Named rather than bare so a failure says WHICH window was served.
    const label = (value: string | undefined) =>
      value === UNFURL_CACHE_SETTLED
        ? "settled"
        : value === UNFURL_CACHE_MOVING
          ? "moving"
          : value;
    expect(label(servedCacheControl())).toBe(label(expected));
  });

  it("never serves next/og's immutable default from any of them", async () => {
    for (const { run, api } of CASES) {
      imageResponseCalls.length = 0;
      mockApi(api.status, api.body);
      await run();
      expect(servedCacheControl()).not.toBe(NEXT_DEFAULT_IMMUTABLE);
    }
  });

  /**
   * The settled arm has to be reachable for the row above to mean anything, and
   * it has to be UNREACHABLE for the wrong reason to be absent. If someone
   * wires every call site to "moving" the table still passes row by row; this
   * is the assertion that notices the long window left the tree entirely.
   */
  it("still has a settled arm at all — not every card wired to one window", () => {
    expect(CASES.filter((c) => c.expected === UNFURL_CACHE_SETTLED)).not.toHaveLength(0);
    expect(CASES.filter((c) => c.expected === UNFURL_CACHE_MOVING)).not.toHaveLength(0);
  });
});

/* ───────────────────────────── 2. the population ─────────────────────────── */

const APP_DIR = path.join(__dirname, "..", "app");
const LIB_DIR = path.join(__dirname, "..", "lib");

function everyOgRoute(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return everyOgRoute(full);
    return entry.name === "opengraph-image.tsx" ? [full] : [];
  });
}

/**
 * Whether a route draws something that can change under its own URL.
 *
 * ONE LEVEL OF IMPORT IS FOLLOWED, AND THAT IS THE WHOLE POINT. Scanning the
 * route file alone for `await fetch(` reports the #6166 SPECIMEN as static: the
 * team card fetches through `fetchTeamShare`, so a route-only scan returns 0 and
 * the guard passes over the one file that shipped the defect. Measured while
 * building this: 5 routes fetch, and only 3 of them say `fetch(` in their own
 * source.
 */
function drawsMovingContent(routeFile: string): boolean {
  const source = fs.readFileSync(routeFile, "utf8");
  if (/\bfetch\(/.test(source)) return true;

  const imported = [...source.matchAll(/from "@\/lib\/([A-Za-z0-9_/-]+)"/g)].map((m) => m[1]);
  return imported.some((mod) => {
    const file = path.join(LIB_DIR, `${mod}.ts`);
    return fs.existsSync(file) && /\bfetch\(/.test(fs.readFileSync(file, "utf8"));
  });
}

describe("#6166 no unfurl picture that draws a moving number keeps next/og's default", () => {
  const routes = everyOgRoute(APP_DIR);
  const fetching = routes.filter(drawsMovingContent);
  const staticCards = routes.filter((r) => !drawsMovingContent(r));

  /**
   * A scan that silently finds nothing passes every assertion below it. These
   * two numbers are the scan's own smoke test: they are asserted as floors
   * rather than equalities so that ADDING a route is not a test failure — the
   * assertions that follow are what a new route has to satisfy.
   */
  it("actually found the routes it is scanning", () => {
    expect(routes.length).toBeGreaterThanOrEqual(12);
    expect(fetching.length).toBeGreaterThanOrEqual(5);
    expect(staticCards.length).toBeGreaterThanOrEqual(6);
  });

  it("classifies the #6166 specimen as fetching, which a route-only scan does not", () => {
    const specimen = routes.find((r) => r.includes(path.join("team", "[team]")));
    expect(specimen).toBeDefined();
    expect(drawsMovingContent(specimen as string)).toBe(true);
    // The trap, pinned: its own source contains no fetch call.
    expect(/\bfetch\(/.test(fs.readFileSync(specimen as string, "utf8"))).toBe(false);
  });

  it.each(
    // `fetching` is derived, so a route added tomorrow is a row here tomorrow.
    (() => fetching.map((file) => [path.relative(APP_DIR, file), file] as const))(),
  )("%s asks for a window at every ImageResponse", (_label, file) => {
    const source = fs.readFileSync(file, "utf8");
    const calls = source.match(/new ImageResponse\(/g) ?? [];
    expect(calls.length).toBeGreaterThan(0);

    // Every call must be given options built by the helper. Counting the helper
    // rather than merely importing it is what catches the half-adoption: a
    // route with three call sites and two helper calls is exactly the shape
    // #6049 left behind.
    const helperCalls = source.match(/unfurlImageOptions\(/g) ?? [];
    expect(helperCalls).toHaveLength(calls.length);

    // And the bare `size,` argument — the unfixed spelling — is gone.
    expect(source).not.toMatch(/new ImageResponse\([\s\S]*?\n\s*size,\n\s*\);/);
  });

  /**
   * The other direction (gotcha #43). A static card SHOULD keep next/og's
   * one-year immutable default: it is drawn from the source tree, so its
   * deployment-hashed URL really does change whenever its bytes do. Adopting the
   * helper there would be a regression, and this is the assertion that stops a
   * future sweep "finishing the job".
   */
  it("leaves the static cards alone, because immutable is correct for them", () => {
    for (const file of staticCards) {
      const source = fs.readFileSync(file, "utf8");
      expect({
        route: path.relative(APP_DIR, file),
        usesHelper: source.includes("unfurlImageOptions"),
      }).toEqual({ route: path.relative(APP_DIR, file), usesHelper: false });
    }
  });
});
