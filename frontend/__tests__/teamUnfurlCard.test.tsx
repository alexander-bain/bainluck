/**
 * A PASTED TEAM LINK UNFURLS AS THAT TEAM, PICTURE AND ALL.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS, MEASURED 2026-09-13 12:31:54Z ═══
 *
 *   /sport/baseball/mlb/team/boston-red-sox      og:image      …/opengraph-image
 *                                                twitter:image …/opengraph-image
 *   /sport/football/nfl/team/kansas-city-chiefs  identical
 *   /sport/basketball/nba/team/boston-celtics    identical
 *
 * `GET <route>/opengraph-image` answered **404** on all three — the route had no
 * card at all — so the house picture was every team's picture, in chat and on X
 * alike. This was the last entry on check 8's ratchet, and by the 2026-09-08
 * measurement in `lib/shareCard.ts` the one a fan actually pastes.
 *
 * ═══ WHAT THIS ASSERTS, AND IN WHICH DIRECTION ═══
 *
 * Both directions, per gotcha #43. The live card must carry the team's own
 * facts AND the two refusal branches must carry none — a fix that drew the
 * quiet card for every team would satisfy half of this file and is the obvious
 * way to "pass" it.
 *
 * The three branches are asserted as BEHAVIOUR through the route, not read off
 * the copy table, because the split is the whole ship:
 *
 *   200 + a team              -> its name, its record, its one number
 *   200 + a team in another
 *     sport (#5852)           -> the page's own refusal, and NO number
 *   404 / unparseable segment -> "This team isn't on Bain Luck", and NO number
 *   500 / timeout             -> claims nothing about existence (gotcha #53)
 *
 * ⚠️ THE RIG IS PROVED NOT BLIND BEFORE ANY ABSENCE IS ASSERTED. `UnfurlCard`
 * is rendered as `<UnfurlCard {...props} />`, so every string it draws is a
 * PROP and not a child: a reader that walks the element tree returns `[]` and
 * every "the dead card does not print X" passes vacuously — which is exactly
 * what happened to the first cut of `deadLinkUnfurlCard5846.test.tsx`, on the
 * assertions that file exists for. `renderToStaticMarkup` is the fix, and the
 * first test below blinds the reader deliberately and fails.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import TeamOgImage from "@/app/sport/[sport]/[league]/team/[team]/opengraph-image";
import { generateMetadata as teamMetadata } from "@/app/sport/[sport]/[league]/team/[team]/layout";
import {
  buildTeamShareCopy,
  classifyTeamShare,
  readableAccent,
  teamCardCopy,
  teamRouteSegmentsAreWellFormed,
  teamSeasonLine,
} from "@/lib/teamShareMeta";
import { teamHeadline } from "@/lib/teamHeadline";
import { unresolvedShareCopy } from "@/lib/unresolvedShareMeta";
import { DEFAULT_ACCENT, UnfurlCard } from "@/components/og/UnfurlCard";

/* ────────────────────────────── the harness ────────────────────────────── */

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&#x2F;": "/",
};

/**
 * Every string the card DRAWS, in render order.
 *
 * Split on TAG boundaries rather than whitespace: these assertions name whole
 * sentences, and a word-split list can never contain one. The sentinel is an
 * escape so no raw control byte sits in the file — `grep` calls such a file
 * binary and stops printing it. Rendering also puts `clampText`/`clampWords`
 * inside the test, so what is asserted is what reaches the canvas.
 */
function textNodes(element: React.ReactElement): string[] {
  const TAG_BOUNDARY = "\u0000";
  return renderToStaticMarkup(element)
    .replace(/<[^>]*>/g, TAG_BOUNDARY)
    .split(TAG_BOUNDARY)
    .map((text) =>
      text.replace(/&(?:amp|lt|gt|quot|#x27|#39|#x2F);/g, (e) => ENTITIES[e]).trim(),
    )
    .filter(Boolean);
}

/** Every fill/stroke colour the card drew, so the accent is readable too. */
function colours(element: React.ReactElement): string {
  return renderToStaticMarkup(element).toLowerCase();
}

/** An upstream answer, by status. `ok` is derived the way `fetch` derives it. */
function respondWith(status: number, body: unknown = {}) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/** One futures row, shaped like the live payload's. */
let marketId = 100;
function market(tier: number, probability: number | null, name: string) {
  marketId += 1;
  return {
    outcome_id: marketId * 10,
    outcome_name: "Boston",
    market_id: marketId,
    market_name: name,
    market_tier: tier,
    category: "baseball",
    source: "kalshi",
    probability,
    probability_change_24h: null,
    rank: null,
    total_outcomes: null,
    resolution_date: null,
  };
}

/**
 * The Red Sox, trimmed from the live `/api/teams/boston-red-sox` read of
 * 2026-09-13 12:33Z. `championship_path` really is empty and the 24-future
 * list really does carry three tier-1 rows, which is why the fallback branch is
 * the one production exercises.
 */
const RED_SOX = {
  team: {
    id: 1,
    slug: "boston-red-sox",
    name: "Boston Red Sox",
    abbreviation: "BOS",
    sport_key: "baseball_mlb",
    sport_name: "MLB",
    location: "Boston",
    primary_color: "#0d2b56",
    secondary_color: "#bd3039",
    logo_small: null,
    logo_large: null,
    record: "81-68",
    standings: {
      pct: ".544",
      wins: 81,
      losses: 68,
      div_rank: 3,
      division: "East",
      conference: "American League",
    },
    season_stats: null,
    roster: null,
  },
  championship_path: [],
  futures: [
    market(2, 0.135, "American League Champion"),
    market(1, 0.0575, "Pro Baseball Champion"),
    market(1, 0.0495, "MLB World Series Champion 2026"),
    market(4, 0.006, "MLB: 2026 AL East Champion"),
    market(5, 0.9975, "MLB: Team to make postseason"),
  ],
};

/** A basketball team, which is what `hawaii-rainbow-warriors` resolves to. */
const OFF_ROUTE_TEAM = {
  team: {
    ...RED_SOX.team,
    name: "Hawai'i Rainbow Warriors",
    slug: "hawaii-rainbow-warriors",
    sport_key: "basketball_wncaab",
    sport_name: "WNCAAB",
    primary_color: "#024731",
    record: "12-9",
    standings: null,
  },
  championship_path: [],
  futures: [],
};

const MLB_ROUTE = { sport: "baseball", league: "mlb", team: "boston-red-sox" };

async function drawCard(
  params: { sport: string; league: string; team: string },
  status: number,
  body: unknown = {},
): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  respondWith(status, body);
  await (TeamOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: Promise.resolve(params),
  });
  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return mockImageResponseCalls[0];
}

/* ─────────────────────── the rig, before it is trusted ─────────────────── */

describe("the reader can see a spread card at all", () => {
  it("finds the team's own strings, so every absence below means something", async () => {
    const drawn = textNodes(await drawCard(MLB_ROUTE, 200, RED_SOX));

    // Four independent slots. A reader that returned [] — the vacuous shape
    // that let `deadLinkUnfurlCard5846`'s first cut pass on its own subject —
    // fails here before it can score an absence as a pass.
    expect(drawn).toContain("Boston Red Sox");
    expect(drawn).toContain("MLB");
    expect(drawn.join(" ")).toContain("81-68");
    expect(drawn).toContain("Championship");
    expect(drawn.length).toBeGreaterThanOrEqual(5);
  });

  it("a blinded reader fails, so the guard is the render and not the walk", () => {
    // The mutation on the RIG, kept in the suite rather than described in a
    // comment: a props-blind reader sees the element and nothing in it.
    const blind = (element: React.ReactElement): string[] =>
      React.Children.toArray(
        (element.props as { children?: React.ReactNode }).children,
      )
        .filter((c): c is string => typeof c === "string")
        .map((c) => c.trim())
        .filter(Boolean);

    const card = teamCardCopy(
      classifyTeamShare({ ok: true, payload: RED_SOX }, "baseball"),
      "baseball",
      "mlb",
    );
    const element = React.createElement(UnfurlCard, card);
    expect(blind(element)).toEqual([]);
    // ...while the reader this file actually uses sees four slots on the same
    // element. That gap IS the guard.
    expect(textNodes(element)).toContain("Boston Red Sox");
  });
});

/* ──────────────────────────── the live branch ──────────────────────────── */

describe("a real team link draws that team", () => {
  it("carries the name, the record, the standing and the season number", async () => {
    const drawn = textNodes(await drawCard(MLB_ROUTE, 200, RED_SOX));

    expect(drawn).toContain("Boston Red Sox");
    expect(drawn).toContain("MLB");
    expect(drawn).toContain("81-68 · #3 in East");
    expect(drawn).toContain("Championship");
    // `formatShareProbability(0.0575)` and the page's own
    // `Math.round(p * 100)` agree by construction: both round to 6%.
    expect(drawn).toContain("6%");
  });

  it("quotes the number the PAGE's hero quotes, from the same function", () => {
    // Not "the card says 6%" — that a string appears proves nothing about
    // whose number it is. The page renders `Math.round(headline.probability *
    // 100)%` off `teamHeadline`, so this asserts the card's row is that same
    // call's output and would fail the day the card grew its own rule.
    const headline = teamHeadline(RED_SOX.championship_path, RED_SOX.futures);
    expect(headline).not.toBeNull();
    const card = teamCardCopy(
      classifyTeamShare({ ok: true, payload: RED_SOX }, "baseball"),
      "baseball",
      "mlb",
    );
    expect(card.rows).toHaveLength(1);
    expect(card.rows[0].fraction).toBe(headline!.probability);
    expect(card.rows[0].probability).toBe(`${Math.round(headline!.probability * 100)}%`);
    expect(card.rows[0].name).toBe(headline!.label);
  });

  it("draws the team's own colour when it is readable, not the sport's", async () => {
    const markup = colours(await drawCard(MLB_ROUTE, 200, RED_SOX));
    // Red Sox navy, the same `primary_color` the page's hero border uses.
    expect(markup).toContain("#0d2b56");
    // ...and NOT the baseball default it would fall back to.
    expect(markup).not.toContain("#ba1c1c");
  });

  it("a team with no season price draws no number rather than a zero", () => {
    const card = teamCardCopy(
      classifyTeamShare(
        { ok: true, payload: { ...RED_SOX, futures: [], championship_path: [] } },
        "baseball",
      ),
      "baseball",
      "mlb",
    );
    expect(card.rows).toEqual([]);
    expect(card.title).toBe("Boston Red Sox");
    expect(textNodes(React.createElement(UnfurlCard, card)).join(" ")).not.toMatch(/\d+%/);
  });
});

/* ─────────────────────── the wrong-address branch (#5852) ──────────────── */

describe("a team at the wrong address refuses, and invents nothing", () => {
  const FOOTBALL_ROUTE = {
    sport: "football",
    league: "ncaaf",
    team: "hawaii-rainbow-warriors",
  };

  it("says what the PAGE says, word for word", async () => {
    const drawn = textNodes(await drawCard(FOOTBALL_ROUTE, 200, OFF_ROUTE_TEAM));
    expect(drawn).toContain("We don't have a football page for Hawai'i Rainbow Warriors");
  });

  it("prints no probability and no record for a sport it cannot speak for", async () => {
    const drawn = textNodes(await drawCard(FOOTBALL_ROUTE, 200, OFF_ROUTE_TEAM)).join(" ");
    expect(drawn).not.toMatch(/\d+%/);
    expect(drawn).not.toContain("12-9");
    expect(drawn).not.toContain("Championship");
    // And it must NOT borrow the shared sentence: the team IS on Bain Luck.
    expect(drawn).not.toContain(unresolvedShareCopy("team", "not-found").title);
  });

  it("is noindex, because 282 measured slugs land on one sentence", async () => {
    respondWith(200, OFF_ROUTE_TEAM);
    const meta = await teamMetadata({ params: Promise.resolve(FOOTBALL_ROUTE) });
    expect(meta.robots).toEqual({ index: false, follow: true });
  });

  it("a team whose sport CANNOT be measured is not off-route", () => {
    // "Absent is not wrong" — `teamRouteSport.ts`. A guard that refuses when it
    // cannot measure is one somebody switches off wholesale.
    const verdict = classifyTeamShare(
      {
        ok: true,
        payload: { ...RED_SOX, team: { ...RED_SOX.team, sport_key: null } },
      },
      "football",
    );
    expect(verdict.kind).toBe("team");
  });
});

/* ────────────────────────── the unresolved branch ──────────────────────── */

describe("a link that names no team says so, and draws nothing", () => {
  it("a 404 draws the quiet card with the shared sentence", async () => {
    const drawn = textNodes(
      await drawCard({ ...MLB_ROUTE, team: "not-a-real-team-99999" }, 404),
    );
    expect(drawn).toContain(unresolvedShareCopy("team", "not-found").title);
    expect(drawn.join(" ")).not.toMatch(/\d+%/);
  });

  it("a 500 claims nothing about whether the team exists (gotcha #53)", async () => {
    const drawn = textNodes(await drawCard(MLB_ROUTE, 500)).join(" ");
    expect(drawn).not.toContain("isn't on Bain Luck");
    expect(drawn).toContain(unresolvedShareCopy("team", "unavailable").title);
  });

  it("a 500 is not noindex-ed, and a 404 is", async () => {
    respondWith(500);
    const unavailable = await teamMetadata({ params: Promise.resolve(MLB_ROUTE) });
    expect(unavailable.robots).toBeUndefined();

    respondWith(404);
    const missing = await teamMetadata({ params: Promise.resolve(MLB_ROUTE) });
    expect(missing.robots).toEqual({ index: false, follow: true });
  });

  it("a 200 with no name is not a team", () => {
    const verdict = classifyTeamShare(
      { ok: true, payload: { team: { ...RED_SOX.team, name: "  " } } as never },
      "baseball",
    );
    expect(verdict).toEqual({ kind: "unresolved", failure: "not-found" });
  });
});

/* ─────────────────── both namespaces name THIS route's card ────────────── */

describe("one picture, in both namespaces, on every branch", () => {
  const OWN_CARD =
    "/sport/baseball/mlb/team/boston-red-sox/opengraph-image";

  it.each([
    ["a real team", 200, RED_SOX],
    ["a dead link", 404, {}],
    ["a bad minute", 500, {}],
  ])("%s names its own card in og AND twitter", async (_label, status, body) => {
    respondWith(status as number, body);
    const meta = await teamMetadata({ params: Promise.resolve(MLB_ROUTE) });

    const og = (meta.openGraph as { images?: Array<{ url: string }> })?.images ?? [];
    const tw = (meta.twitter as { images?: string[] })?.images ?? [];

    // The file convention overrides `og:image` and NOT `twitter:image`, so the
    // twitter side is the one that silently kept the house card on `/events`
    // and `/futures` until #5846.
    expect(og[0].url).toContain(OWN_CARD);
    expect(tw[0]).toContain(OWN_CARD);
    expect(tw[0]).not.toBe("https://www.bainluck.com/opengraph-image");
  });

  it("the canonical is this page, never the apex", async () => {
    respondWith(200, RED_SOX);
    const meta = await teamMetadata({ params: Promise.resolve(MLB_ROUTE) });
    expect(meta.alternates?.canonical).toBe("/sport/baseball/mlb/team/boston-red-sox");
  });
});

/* ────────────────────────── the words, per branch ──────────────────────── */

describe("the title and description are the payload's, not the segments'", () => {
  it("names the team and the league from the payload", () => {
    const copy = buildTeamShareCopy(
      classifyTeamShare({ ok: true, payload: RED_SOX }, "baseball"),
      "mlb",
    );
    expect(copy.title).toBe("Boston Red Sox MLB Odds & Probabilities — Bain Luck");
    expect(copy.description).toContain("Boston Red Sox: 6% to win the championship");
  });

  it("stops shouting a fragment of the sport key (#5847, one surface over)", () => {
    // `league.toUpperCase()` on the ROUTE segment is what the layout used to
    // do, and it rendered "KOREA_KLEAGUE1" in the tab of every K League team.
    const kLeague = {
      ...RED_SOX,
      team: {
        ...RED_SOX.team,
        name: "Suwon Bluewings",
        sport_key: "soccer_korea_kleague1",
        sport_name: "K League 1",
      },
      futures: [],
      championship_path: [],
    };
    const copy = buildTeamShareCopy(
      classifyTeamShare({ ok: true, payload: kLeague }, "soccer"),
      "korea_kleague1",
    );
    expect(copy.title).not.toContain("KOREA_KLEAGUE1");
    expect(copy.title).toContain("K League 1");
  });

  it("a team with no season price makes no claim about one", () => {
    const copy = buildTeamShareCopy(
      classifyTeamShare(
        { ok: true, payload: { ...RED_SOX, futures: [], championship_path: [] } },
        "baseball",
      ),
      "mlb",
    );
    expect(copy.description).not.toMatch(/\d+%/);
    expect(copy.description).not.toContain("championship odds");
  });
});

/* ───────────────────────────── the pure rules ──────────────────────────── */

describe("teamHeadline is the page's rule and nothing else", () => {
  it("prefers the championship path over the futures fallback", () => {
    const headline = teamHeadline(
      [
        { tier: 2, label: "Conference", market_name: "AL", market_id: 1, probability: 0.4, rank: 1, movement: 2 },
        { tier: 1, label: "World Series", market_name: "WS", market_id: 2, probability: 0.11, rank: 3, movement: -1 },
      ] as never,
      RED_SOX.futures as never,
    );
    expect(headline).toEqual({ label: "World Series", probability: 0.11, movement: -1 });
  });

  it("falls back to the best tier-1 future when the path is empty — the live case", () => {
    const headline = teamHeadline([], RED_SOX.futures as never);
    // 0.0575 "Pro Baseball Champion", not the 0.9975 tier-5 postseason market
    // and not the 0.135 tier-2 one: tier order first, probability only to break
    // a tie inside a tier.
    expect(headline).toEqual({ label: "Championship", probability: 0.0575, movement: null });
  });

  it("is null when nothing carries a probability", () => {
    expect(teamHeadline([], [])).toBeNull();
    expect(teamHeadline(null, null)).toBeNull();
    expect(teamHeadline([{ tier: 1, label: "X", probability: null } as never], [])).toBeNull();
  });
});

describe("readableAccent refuses a colour the pill would vanish in", () => {
  it.each([
    ["#0d2b56", "#0d2b56"], // Red Sox navy, L=0.026
    ["#008348", "#008348"], // Celtics green, L=0.167
    ["#0D2B56", "#0d2b56"], // case is not a different colour
    ["#036", "#003366"], // three-digit hex expands
  ])("keeps %s", (input, expected) => {
    expect(readableAccent(input, DEFAULT_ACCENT)).toBe(expected);
  });

  it.each([
    ["#ffffff"], // the Celtics' own secondary_color, L=1
    ["#ffd700"], // gold, L=0.70
    ["#cccccc"],
    ["rebeccapurple"], // not a hex
    ["#12345"], // not a hex either
    [null],
    [undefined],
    [""],
  ])("falls back on %s", (input) => {
    expect(readableAccent(input as string | null, "#ba1c1c")).toBe("#ba1c1c");
  });
});

describe("teamSeasonLine names the pool it counted (#4732)", () => {
  const withStandings = (standings: Record<string, unknown> | null, record: string | null) =>
    teamSeasonLine({ ...RED_SOX.team, standings, record } as never);

  it("prints the record and the division place, naming the division", () => {
    expect(withStandings({ div_rank: 3, division: "East" }, "81-68")).toBe(
      "81-68 · #3 in East",
    );
  });

  it("prefers conf_rank, the only field that genuinely scopes to a conference", () => {
    expect(withStandings({ conf_rank: 2, div_rank: 3, division: "East" }, "81-68")).toBe(
      "81-68 · #2 in conference",
    );
  });

  it("says 'in division' rather than inventing a division name", () => {
    expect(withStandings({ div_rank: 1 }, null)).toBe("#1 in division");
  });

  it("is null when the team has neither", () => {
    expect(withStandings(null, null)).toBeNull();
    expect(withStandings({}, "   ")).toBeNull();
  });
});

describe("the segment screen refuses what could never be a team page", () => {
  it.each([
    ["baseball", "mlb", "boston-red-sox"],
    ["soccer", "usa_mls", "inter-miami-cf"], // the league segment carries an underscore
    ["basketball", "wncaab", "hawaii-rainbow-warriors"],
  ])("admits /%s/%s/%s", (sport, league, team) => {
    expect(teamRouteSegmentsAreWellFormed(sport, league, team)).toBe(true);
  });

  it.each([
    ["baseball", "mlb", ".."],
    ["baseball", "mlb", "Boston-Red-Sox"],
    ["baseball", "mlb", "boston red sox"],
    ["baseball", "mlb", "-leading-hyphen"],
    ["baseball", "mlb", `x${"y".repeat(80)}`],
    ["../../etc", "mlb", "boston-red-sox"],
    ["baseball", "", "boston-red-sox"],
    ["", "mlb", "boston-red-sox"],
  ])("refuses /%s/%s/%s", (sport, league, team) => {
    expect(teamRouteSegmentsAreWellFormed(sport, league, team)).toBe(false);
  });

  it("a refused segment is a 404 card, and costs no upstream request", async () => {
    // The screen is the reason `generateMetadata` and this image route are safe
    // to run on every crawl of an attacker-supplied path: a segment that could
    // never name a team page never reaches the API.
    mockImageResponseCalls.length = 0;
    const fetchSpy = jest.fn();
    global.fetch = fetchSpy as unknown as typeof fetch;

    await (TeamOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
      params: Promise.resolve({ sport: "baseball", league: "mlb", team: ".." }),
    });

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(textNodes(mockImageResponseCalls[0])).toContain(
      unresolvedShareCopy("team", "not-found").title,
    );
  });
});
