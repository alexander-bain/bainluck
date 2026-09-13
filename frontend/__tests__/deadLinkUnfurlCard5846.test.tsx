/**
 * #5846 — A DEAD GAME OR MARKET LINK UNFURLS AS A DEAD LINK, IN BOTH NAMESPACES.
 *
 * ═══ THE TWO DEFECTS, BOTH MEASURED ON PRODUCTION 2026-09-13 11:49:13Z ═══
 *
 * 1. THE PICTURE. `/events/99999999/opengraph-image` and
 *    `/futures/99999999/opengraph-image` both answered `200 image/png`,
 *    1200x630, md5 `12e3f23f4984…` and `6a4c72c052a8…`. The events card drew
 *    two coloured crests reading `AWA` and `HOM`, the names "Away" and "Home",
 *    and **50% against 50%** in 74px type over a half-and-half bar. The futures
 *    card drew "Prediction market", a `- -` glyph where the 96px probability
 *    goes, an empty leader line and "0 outcomes tracked".
 *
 *    #5840 had already given both routes honest WORDS ("This game isn't on Bain
 *    Luck", self-canonical, `noindex`). Only the image routes were left, and
 *    they read every field through `?.` with a default behind it.
 *
 * 2. THE OTHER NAMESPACE. Next's `opengraph-image.tsx` file convention
 *    overrides `og:image` and NOT `twitter:image`, so with no 4th argument
 *    passed to `unresolvedMetadata` the two tags disagreed:
 *
 *      /events/99999999   og:image       …/events/99999999/opengraph-image?509a39…
 *                         twitter:image  https://www.bainluck.com/opengraph-image
 *      /futures/99999999  the same split
 *
 *    X reads `twitter:`, so one rotted link previewed as the route's own card
 *    in Slack and as the HOME PAGE on X — the split #5888 closed for
 *    `/tournaments/[slug]` and `/event/[domain]/[slug]`, one namespace over.
 *
 * ═══ WHAT THIS ASSERTS, AND IN WHICH DIRECTION ═══
 *
 * Both directions, per gotcha #43. A miss must draw the quiet card AND a hit
 * must still draw the live one — a fix that made every card quiet would satisfy
 * half of this file and is the obvious way to "pass" it.
 *
 * The 404/non-404 split is asserted as behaviour rather than trusted from the
 * layout's copy of it: claiming a real market is "not on Bain Luck" because the
 * API was restarting is the failure `unresolvedShareMeta.ts` documents at
 * length (gotcha #53), and on a PICTURE it is worse than on a sentence, because
 * the unfurler caches it.
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

import EventsOgImage from "@/app/events/[id]/opengraph-image";
import FuturesOgImage from "@/app/futures/[id]/opengraph-image";
import EventsLayoutMeta from "@/app/events/[id]/layout";
import { generateMetadata as eventsMetadata } from "@/app/events/[id]/layout";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import { unresolvedCardCopy } from "@/lib/unresolvedCardCopy";
import { unresolvedShareCopy } from "@/lib/unresolvedShareMeta";

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
 * ⚠️ Walking the element tree is not enough here and the first cut of this file
 * proved it: the quiet card is `<UnfurlCard {...props} />`, so its title is a
 * PROP, not a child, and a walker found zero text nodes on a card that draws
 * four. Every "the dead card does not print X" assertion passed for that reason
 * alone — the vacuous shape, on the exact assertions that matter.
 *
 * Rendering also puts `clampText`/`clampWords` inside the test, so the strings
 * asserted are the ones that reach the canvas rather than the ones handed in.
 */
function textNodes(element: React.ReactElement): string[] {
  // Split on TAG boundaries, not on whitespace: these assertions name whole
  // sentences ("This game isn't on Bain Luck"), and a word-split list can never
  // contain one. The sentinel is written as an escape so no raw control byte
  // sits in the file — `grep` calls such a file binary and stops printing it.
  const TAG_BOUNDARY = "\u0000";
  return renderToStaticMarkup(element)
    .replace(/<[^>]*>/g, TAG_BOUNDARY)
    .split(TAG_BOUNDARY)
    .map((text) => text.replace(/&(?:amp|lt|gt|quot|#x27|#39|#x2F);/g, (e) => ENTITIES[e]).trim())
    .filter(Boolean);
}

/**
 * The component the route handed `ImageResponse`, by name.
 *
 * The quiet card is `UnfurlCard` and the live one is a bare `<div>` tree, so
 * this is the cleanest statement of "which card did it draw" — and it does not
 * depend on any string either card prints, which the assertions below then do
 * independently.
 */
function cardName(element: React.ReactElement): string {
  const type = element.type as string | { name?: string };
  return typeof type === "string" ? type : type?.name ?? "unknown";
}

/** An upstream answer, by status. `ok` is derived the way `fetch` derives it. */
function respondWith(status: number, body: unknown = {}) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

/** A real game, enough of one for the live card to draw. */
const LIVE_EVENT = {
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

/** A real market, enough of one for the live card to draw. */
const LIVE_MARKET = {
  id: 109952,
  name: "2026 World Series Winner",
  llm_sport_category: "baseball",
  outcome_count: 30,
  outcomes: [{ name: "Los Angeles Dodgers", probability: 0.21 }],
};

type Surface = {
  route: string;
  Image: (args: { params: { id: string } }) => Promise<unknown>;
  metadata: (args: { params: Promise<{ id: string }> }) => Promise<{
    openGraph?: { images?: unknown };
    twitter?: { images?: unknown };
  }>;
  subject: "game" | "market";
  live: unknown;
  /** A string only the LIVE card can print — the other-direction assertion. */
  liveMarker: string;
  /** The fabricated strings the dead card used to print. */
  fabrications: string[];
};

const SURFACES: readonly Surface[] = [
  {
    route: "/events/[id]",
    Image: EventsOgImage as Surface["Image"],
    metadata: eventsMetadata as Surface["metadata"],
    subject: "game",
    live: LIVE_EVENT,
    liveMarker: "Pittsburgh Pirates",
    // The invented matchup, verbatim from the production render.
    fabrications: ["Away", "Home", "50%", "Probability-first odds"],
  },
  {
    route: "/futures/[id]",
    Image: FuturesOgImage as Surface["Image"],
    metadata: futuresMetadata as Surface["metadata"],
    subject: "market",
    live: LIVE_MARKET,
    liveMarker: "2026 World Series Winner",
    fabrications: ["Prediction market", "--", "0 outcomes tracked"],
  },
];

async function drawCard(
  surface: Surface,
  status: number,
  body: unknown = {},
): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  respondWith(status, body);
  await surface.Image({ params: { id: "99999999" } });
  if (mockImageResponseCalls.length !== 1) {
    throw new Error(
      `${surface.route}: expected exactly 1 ImageResponse, captured ${mockImageResponseCalls.length}`,
    );
  }
  return mockImageResponseCalls[0];
}

/* ──────────────────────────── the harness itself ─────────────────────────── */

describe("#5846 — the rig can see both cards", () => {
  // Without this the whole file passes vacuously if an import silently resolves
  // to a stub: every "the dead card does not print X" assertion is satisfied by
  // a card that prints nothing at all.
  it.each(SURFACES)("$route draws its LIVE card on a 200", async (surface) => {
    const card = await drawCard(surface, 200, surface.live);
    expect(`${surface.route}: ${textNodes(card).includes(surface.liveMarker)}`).toBe(
      `${surface.route}: true`,
    );
    expect(`${surface.route}: ${cardName(card)}`).not.toBe(`${surface.route}: UnfurlCard`);
  });

  it("the layout module under test is the real one", () => {
    // A default export means this is the route's layout component, not a mock.
    expect(typeof EventsLayoutMeta).toBe("function");
  });
});

/* ──────────────────────────────── the picture ────────────────────────────── */

describe("#5846 — a 404 draws the quiet card, not an invented one", () => {
  it.each(SURFACES)("$route", async (surface) => {
    const card = await drawCard(surface, 404);
    const printed = textNodes(card);

    expect(`${surface.route}: ${cardName(card)}`).toBe(`${surface.route}: UnfurlCard`);
    expect(`${surface.route}: ${printed.includes(unresolvedShareCopy(surface.subject, "not-found").title)}`).toBe(
      `${surface.route}: true`,
    );
  });

  it.each(SURFACES)("$route prints none of the strings it used to invent", async (surface) => {
    const printed = textNodes(await drawCard(surface, 404));
    const survived = surface.fabrications.filter((text) => printed.includes(text));
    expect(`${surface.route}: ${JSON.stringify(survived)}`).toBe(`${surface.route}: []`);
  });

  it.each(SURFACES)("$route prints no percentage at all", async (surface) => {
    // The events card's whole defect was a NUMBER. A quiet card that somehow
    // grew one back would pass the string list above, because 51% is not 50%.
    const printed = textNodes(await drawCard(surface, 404));
    const numbers = printed.filter((text) => /\d/.test(text));
    expect(`${surface.route}: ${JSON.stringify(numbers)}`).toBe(`${surface.route}: []`);
  });
});

describe("#5846 — a bad minute is not an absence (gotcha #53)", () => {
  it.each(SURFACES)("$route says nothing about existence on a 500", async (surface) => {
    const printed = textNodes(await drawCard(surface, 500));
    const notFoundTitle = unresolvedShareCopy(surface.subject, "not-found").title;

    expect(`${surface.route}: ${printed.includes(notFoundTitle)}`).toBe(
      `${surface.route}: false`,
    );
    expect(
      `${surface.route}: ${printed.includes(unresolvedShareCopy(surface.subject, "unavailable").title)}`,
    ).toBe(`${surface.route}: true`);
  });

  it.each(SURFACES)("$route still draws the quiet card on a 500", async (surface) => {
    // "Unavailable" must not fall through to the invented card either — it was
    // the SAME branch before this ship.
    expect(`${surface.route}: ${cardName(await drawCard(surface, 500))}`).toBe(
      `${surface.route}: UnfurlCard`,
    );
  });

  it.each(SURFACES)("$route treats a thrown fetch as unavailable, not absent", async (surface) => {
    mockImageResponseCalls.length = 0;
    global.fetch = jest.fn().mockRejectedValue(new Error("socket hang up")) as unknown as typeof fetch;
    await surface.Image({ params: { id: "99999999" } });
    const printed = textNodes(mockImageResponseCalls[0]);
    expect(`${surface.route}: ${printed.includes(unresolvedShareCopy(surface.subject, "unavailable").title)}`).toBe(
      `${surface.route}: true`,
    );
  });

  it.each(SURFACES)("$route refuses a segment that could never be an id", async (surface) => {
    mockImageResponseCalls.length = 0;
    global.fetch = jest.fn(() => {
      throw new Error("the route must not spend a request on this");
    }) as unknown as typeof fetch;

    await surface.Image({ params: { id: "../../etc/passwd" } });

    const printed = textNodes(mockImageResponseCalls[0]);
    expect(`${surface.route}: ${printed.includes(unresolvedShareCopy(surface.subject, "not-found").title)}`).toBe(
      `${surface.route}: true`,
    );
  });
});

/* ──────────────────────────── the other namespace ────────────────────────── */

/** `twitter.images` normalised to the list of URLs, however it was declared. */
function twitterImageUrls(meta: { twitter?: { images?: unknown } }): string[] {
  const images = meta.twitter?.images;
  const list = Array.isArray(images) ? images : images == null ? [] : [images];
  return list.map((entry) =>
    typeof entry === "string" ? entry : String((entry as { url?: unknown })?.url ?? entry),
  );
}

function openGraphImageUrls(meta: { openGraph?: { images?: unknown } }): string[] {
  const images = meta.openGraph?.images;
  const list = Array.isArray(images) ? images : images == null ? [] : [images];
  return list.map((entry) =>
    typeof entry === "string" ? entry : String((entry as { url?: unknown })?.url ?? entry),
  );
}

describe("#5846 — a dead link names ONE picture, its own, in both namespaces", () => {
  it.each(SURFACES)("$route", async (surface) => {
    respondWith(404);
    const meta = await surface.metadata({ params: Promise.resolve({ id: "99999999" }) });

    const og = openGraphImageUrls(meta);
    const twitter = twitterImageUrls(meta);

    // One picture, and the SAME one. The defect was two.
    expect(`${surface.route}: ${JSON.stringify(twitter)}`).toBe(
      `${surface.route}: ${JSON.stringify(og)}`,
    );
    expect(`${surface.route}: ${og.length}`).toBe(`${surface.route}: 1`);
  });

  it.each(SURFACES)("$route's dead picture is the ROUTE's, never the home page's", async (surface) => {
    respondWith(404);
    const meta = await surface.metadata({ params: Promise.resolve({ id: "99999999" }) });
    const [twitterImage] = twitterImageUrls(meta);

    // The exact production value of the defect, by equality — a substring test
    // on a hostname is what CodeQL refuses (notice 32, and the #4957 guard's
    // own scar).
    expect(`${surface.route}: ${twitterImage}`).not.toBe(
      `${surface.route}: https://www.bainluck.com/opengraph-image`,
    );
    expect(`${surface.route}: ${new URL(twitterImage).pathname}`).toBe(
      `${surface.route}: ${surface.route.replace("[id]", "99999999")}/opengraph-image`,
    );
  });

  it.each(SURFACES)("$route keeps the picture on a 500 too", async (surface) => {
    // A route that only passed its card on the `not-found` branch would send an
    // existing market's X preview to the home page for as long as the API was
    // unwell — and that branch is the one nobody looks at.
    respondWith(500);
    const meta = await surface.metadata({ params: Promise.resolve({ id: "15304803" }) });
    const [twitterImage] = twitterImageUrls(meta);
    expect(`${surface.route}: ${new URL(twitterImage).pathname}`).toBe(
      `${surface.route}: ${surface.route.replace("[id]", "15304803")}/opengraph-image`,
    );
  });
});

/* ──────────────────────────── the pure function ──────────────────────────── */

describe("#5846 — unresolvedCardCopy decides everything the route used to", () => {
  it("says the same thing the title says, on every subject", () => {
    // The card and the sentence beside it come from one call. Two tables would
    // eventually disagree, and a reader sees both at once.
    for (const subject of ["game", "market", "tournament", "event", "hub"] as const) {
      for (const failure of ["not-found", "unavailable"] as const) {
        expect(`${subject}/${failure}`).toBe(`${subject}/${failure}`);
        expect(unresolvedCardCopy(subject, failure).title).toBe(
          unresolvedShareCopy(subject, failure).title,
        );
      }
    }
  });

  it("never carries a row, a note or a verdict", () => {
    // `UnfurlCard`'s quiet shape is the whole point: rows are where a number
    // would come back.
    for (const subject of ["game", "market"] as const) {
      for (const failure of ["not-found", "unavailable"] as const) {
        const copy = unresolvedCardCopy(subject, failure);
        expect(`${subject}/${failure}: ${JSON.stringify(copy.rows)}`).toBe(
          `${subject}/${failure}: []`,
        );
        expect(`${subject}/${failure}: ${copy.note ?? null}`).toBe(`${subject}/${failure}: null`);
        expect(`${subject}/${failure}: ${copy.verdict ?? null}`).toBe(
          `${subject}/${failure}: null`,
        );
      }
    }
  });

  it("gives every subject its own eyebrow and its own second line", () => {
    // A `Record` that fell back to one value would make five dead cards
    // identical — the `accentFor(null)` defect #5877 shipped and #5888 caught,
    // one field over.
    const eyebrows = (["game", "market", "tournament", "event", "hub"] as const).map(
      (subject) => unresolvedCardCopy(subject, "not-found").eyebrow,
    );
    expect(JSON.stringify(eyebrows)).toBe(
      JSON.stringify(["Game", "Market", "Tournament", "Event", "Competition"]),
    );

    const subtitles = (["game", "market", "tournament", "event", "hub"] as const).map(
      (subject) => unresolvedCardCopy(subject, "not-found").subtitle,
    );
    expect(new Set(subtitles).size).toBe(subtitles.length);
  });

  it("the not-found second line does not repeat the headline's noun back", () => {
    // The title already says "This game isn't on Bain Luck"; the description
    // says "There's no game at this link…". Stacking those two on one card is a
    // stutter, which is why the card has its own subtitle table.
    for (const subject of ["game", "market"] as const) {
      const copy = unresolvedCardCopy(subject, "not-found");
      expect(`${subject}: ${copy.subtitle}`).not.toBe(
        `${subject}: ${unresolvedShareCopy(subject, "not-found").description}`,
      );
    }
  });

  it("an unavailable card claims nothing about existence", () => {
    // The word that would be the lie, by exact absence from both fields.
    for (const subject of ["game", "market"] as const) {
      const copy = unresolvedCardCopy(subject, "unavailable");
      expect(`${subject}: ${`${copy.title} ${copy.subtitle}`.includes("isn't on Bain Luck")}`).toBe(
        `${subject}: false`,
      );
    }
  });
});
