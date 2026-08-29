/**
 * UX-P177 — "MORE MMA" STOPS SENDING READERS TO DEAD LINKS FOR THE WRONG SPORT.
 *
 * ═══ WHAT A PERSON SAW ═══
 *
 * `bainluck.com/futures/195` is "Welterweight Title Holder on Dec 31, 2026?".
 * At the bottom of it, a section headed **More Mma**. Measured live on
 * 2026-08-29 through the exact request the shipped component builds
 * (`/api/feed?limit=9&tags=["sport:mma"]`, i.e. `limit + 5`), its four rows
 * were:
 *
 *     Vuelta a España 2026                              -> /futures/undefined
 *     Fight Night: Nurmagomedov vs Song                 -> /futures/undefined
 *     Freedom 250 Grand Prix of Washington: Race Winner -> /futures/undefined
 *     Dutch Grand Prix: Driver Winner                   -> /futures/undefined
 *
 * Three of the four are not MMA. Four of the four are dead links. None of them
 * carries a probability, because the row reads `top_outcomes` and a concept has
 * none.
 *
 * ═══ WHY — TWO INDEPENDENT LAYERS, EACH WRONG ═══
 *
 * **The backend** gated the concept tier on the `sport:` tag and then built it
 * with no filter at all, so an MMA surface was served the F1 and cycling
 * concepts too. That half is proven in
 * `backend/tests/test_feed_concept_tag_filter.py`; this file does not re-prove
 * it, because it is not this component's bug.
 *
 * **This component** had an INVERTED type list: `event` rendered, `tournament`
 * returned null, and everything else fell through to the futures branch.
 * `concept` and `bundle` are both in `FeedItem["type"]` and neither carries a
 * numeric `id`, so `` `/futures/${d.id}` `` interpolated `undefined`.
 *
 * The two are genuinely separable, and that is the point of fixing both: even
 * with a perfectly filtered backend, an MMA concept on an MMA page still had to
 * render as a working link. Fixing only the filter would have left four correct
 * UFC cards pointing at `/futures/undefined`.
 *
 * ═══ THE READER COUNT ═══
 *
 * Measured on production 2026-08-29. `RelatedByTag` mounts on every futures
 * detail page that has an `llm_sport_category` and every event detail page
 * whose sport maps to a category:
 *
 *     251  open futures markets with llm_sport_category = 'mma'
 *     163  open futures markets with llm_sport_category = 'motorsports'
 *      12  open futures markets with llm_sport_category = 'cycling'
 *   1,924  events under an mma_* sport key
 *
 * The defect is DETERMINISTIC, not intermittent — every one of those pages, on
 * every load — so a sweep is the honest instrument, not Sentry.
 *
 * ═══ WHAT THE FIXTURE IS ═══
 *
 * `uxp177_related_mma_before.json` is a verbatim production `/api/feed` body,
 * banked 2026-08-29 before the fix was written, from the exact URL this
 * component builds. It is the BEFORE payload and nothing has been assembled or
 * touched. The component rendered against it is the SHIPPED one, so what these
 * tests read is the repair, not a drawing of it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SERVED from "../fixtures/uxp177_related_mma_before.json";

/* ── SWR is all that stands between the component and the payload ── */

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;

type Item = { type: string; data: Record<string, unknown> };
const ITEMS = (SERVED as { items: Item[] }).items;

function render(payload: unknown, props: Record<string, unknown> = {}): string {
  swrPayload = payload;
  return renderToStaticMarkup(
    React.createElement(RelatedByTag, {
      tags: ["sport:mma"],
      limit: 4,
      title: "More Mma",
      ...props,
    })
  );
}

/** Every `href` the markup emits, in order. */
function hrefs(markup: string): string[] {
  return [...markup.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
}

/** Strip tags so assertions read what a PERSON reads. */
function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

describe("the fixture is the honest BEFORE, not a strawman", () => {
  it("is a real served body from the request the component actually makes", () => {
    // limit + 5 = 9. The component asks for 9 and shows 4.
    expect(ITEMS).toHaveLength(9);
    expect((SERVED as { total: number }).total).toBe(16);
  });

  it("every served item is a concept, and NOT ONE carries a numeric id", () => {
    // This is what made the old futures branch produce `/futures/undefined`.
    // If a future payload gives concepts an `id`, this fails and the premise
    // below has to be re-derived rather than assumed.
    expect(ITEMS.every((i) => i.type === "concept")).toBe(true);
    expect(ITEMS.every((i) => i.data.id === undefined)).toBe(true);
    expect(ITEMS.every((i) => i.data.top_outcomes === undefined)).toBe(true);
  });

  it("three of the nine are the wrong sport for an MMA surface", () => {
    const foreign = ITEMS.filter((i) => i.data.domain !== "ufc");
    expect(foreign.map((i) => i.data.domain).sort()).toEqual([
      "cycling",
      "f1",
      "f1",
    ]);
  });
});

describe("the repair: no dead links", () => {
  it("renders NOTHING pointing at /futures/undefined", () => {
    const markup = render(SERVED);
    expect(markup).not.toContain("/futures/undefined");
  });

  it("no emitted href ends in `undefined` — the general form of the bug", () => {
    const bad = hrefs(render(SERVED)).filter((h) => h.includes("undefined"));
    expect(bad).toEqual([]);
  });

  it("every row links to its concept's /event/<domain>/<slug> page", () => {
    // The canonical concept path (L2-113, `lib/eventKey.ts`), which is where
    // `ConceptFeedCard` sends the same items on Discover.
    const links = hrefs(render(SERVED));
    expect(links).toHaveLength(4);
    expect(links.every((h) => h.startsWith("/event/"))).toBe(true);
    expect(links[0]).toBe("/event/cycling/vuelta-2026");
    expect(links[1]).toBe("/event/ufc/26aug29");
  });
});

describe("the repair: the rows say something", () => {
  it("each row carries its leader and a probability, not a bare name", () => {
    const text = visibleText(render(SERVED));
    expect(text).toContain("Tadej Pogacar");
    expect(text).toContain("Yadong Song");
    // `formatProbability` renders the served 0.751 / 0.99.
    expect(text).toMatch(/Tadej Pogacar\s+75%/);
    expect(text).toMatch(/Yadong Song\s+99%/);
  });

  it("a leader with a non-numeric probability is dropped, never printed", () => {
    // Guarded exactly as `ConceptFeedCard` guards it, never laxer.
    const payload = {
      items: [
        {
          type: "concept",
          data: {
            key: "event:ufc:26aug29",
            name: "Fight Night",
            domain: "ufc",
            leader: { name: "Somebody", probability: null },
          },
        },
      ],
    };
    const text = visibleText(render(payload));
    expect(text).toContain("Fight Night");
    expect(text).not.toContain("Somebody");
    expect(text).not.toContain("NaN");
  });
});

describe("the repair: an allowlist, so an unknown type is invisible not broken", () => {
  const mixed = {
    items: [
      { type: "tournament", data: { id: 1, name: "Tour Championship" } },
      { type: "bundle", data: { id: "bundle:x", title: "A Bundle" } },
      {
        type: "concept",
        data: {
          key: "event:ufc:26aug29",
          name: "Fight Night",
          domain: "ufc",
          leader: { name: "Yadong Song", probability: 0.99 },
        },
      },
      {
        type: "futures",
        data: {
          id: 195,
          name: "Welterweight Title Holder",
          top_outcomes: [{ name: "Someone", probability: 0.4 }],
        },
      },
    ],
  };

  it("drops `tournament` and `bundle` rather than mis-rendering them", () => {
    const text = visibleText(render(mixed));
    expect(text).not.toContain("Tour Championship");
    expect(text).not.toContain("A Bundle");
  });

  it("a bundle never becomes a /futures/<string-id> link", () => {
    expect(hrefs(render(mixed))).not.toContain("/futures/bundle:x");
  });

  it("still renders the two types it knows, both correctly", () => {
    const links = hrefs(render(mixed));
    expect(links).toEqual(["/event/ufc/26aug29", "/futures/195"]);
  });

  it("unrenderable items are dropped BEFORE the limit, so the section fills", () => {
    // The filter runs ahead of `.slice(0, limit)`. If it ran after, two of the
    // four slots on this payload would have been spent on nulls and the reader
    // would see a half-empty section.
    const payload = {
      items: [
        { type: "tournament", data: { id: 1, name: "T" } },
        { type: "bundle", data: { id: "b", title: "B" } },
        ...ITEMS,
      ],
    };
    expect(hrefs(render(payload))).toHaveLength(4);
  });
});

describe("the exclusion contract still holds", () => {
  it("the current futures market is still excluded from its own section", () => {
    const payload = {
      items: [
        {
          type: "futures",
          data: { id: 195, name: "This very market", top_outcomes: [] },
        },
        {
          type: "futures",
          data: { id: 196, name: "A sibling", top_outcomes: [] },
        },
      ],
    };
    const text = visibleText(
      render(payload, { excludeId: 195, excludeType: "futures" })
    );
    expect(text).not.toContain("This very market");
    expect(text).toContain("A sibling");
  });

  it("a concept is never excluded by a numeric id it does not have", () => {
    // The old exclusion read `(item.data as FeedFuturesData).id` for every
    // non-event, non-tournament item. A concept's `undefined` id could never
    // equal `excludeId`, so this was latent rather than live — but the id is
    // now read only for the type that has one.
    const links = hrefs(render(SERVED, { excludeId: 195, excludeType: "futures" }));
    expect(links).toHaveLength(4);
  });
});
