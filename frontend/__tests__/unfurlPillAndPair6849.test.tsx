/**
 * #6849 — A PASTED POWER SLAP LINK UNFURLED WITH A `UFC` PILL AND A 68/33 PAIR.
 *
 * ═══ THE DEFECT, BOTH HALVES, ONE PICTURE ═══
 *
 * Read from production 2026-09-18, `/event/ufc/power-slap-23-26sep18powerslap23`:
 *
 *     the card (03:00Z)  ( UFC )  Power Slap 23 / Main event
 *                        Brandon Wilson 68%  ·  Brian Ellis 33%
 *     og:title (04:42Z)  Power Slap 23: Brandon Wilson 68%, Brian Ellis 33%
 *
 * `GET /api/event/event:ufc:power-slap-23-26sep18powerslap23` at 04:40Z served
 * `sport_label: "Combat"` and `0.675 / 0.325`. So neither half was a data
 * problem: the sport was on the wire and the prices are exact complements. The
 * pill read the URL segment instead of the payload, and the two prices were
 * rounded separately.
 *
 * This is the unfurl — iMessage, Slack, X, Workplace. It reaches a wider
 * audience than the page, and it is the one place a reader cannot correct the
 * impression by scrolling.
 *
 * ═══ WHY THIS ASSERTS THE RENDER, NOT THE RULES ═══
 *
 * `conceptDomainLabel` and `renderedDuelPercents` both existed, both had their
 * own suites, and both were green all the way through this bug — the same shape
 * #4963 found on `/events/[id]`'s card. What was untested is whether THIS route
 * calls them. No test of a helper can answer that, so the route is invoked for
 * real with `next/og` stubbed, and the assertions read the strings a reader
 * sees. The caption is asserted beside the card in every case, because the two
 * are halves of one unfurl and a fix to one of them is how they drift apart.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { conceptDomainLabel } from "@/components/discover/utils";
import {
  buildEventConceptShareCopy,
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/event/[domain]/[slug]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The filed card, field for field from the 04:40Z production read — NOT trimmed
 * to the fix's shape. Both defects are reproducible from it alone.
 */
const POWER_SLAP: EventConceptShareSource = {
  event: {
    name: "Power Slap 23",
    slug: "power-slap-23-26sep18powerslap23",
    status: "live",
    venue: null,
    location: null,
    sport_label: "Combat",
    domain: "ufc",
  },
  primary: {
    label: "Main event",
    competitors: [
      { name: "Brandon Wilson", probability: 0.675, won: false },
      { name: "Brian Ellis", probability: 0.325, won: false },
    ],
  },
};

/**
 * THE CONTROL THAT MAKES THE PILL FIX MEAN SOMETHING — `event:ufc:26sep20`, read
 * the same minute. A real UFC card in the same namespace, and the fix must give
 * it its own name back rather than flattening the whole namespace to `COMBAT`.
 */
const REAL_UFC: EventConceptShareSource = {
  event: {
    name: "331: Van vs Pantoja",
    slug: "331-van-vs-pantoja-26sep19",
    status: "upcoming",
    venue: null,
    location: null,
    sport_label: "UFC",
    domain: "ufc",
  },
  primary: {
    label: "Main event",
    competitors: [
      { name: "Joshua Van", probability: 0.565, won: false },
      { name: "Alexandre Pantoja", probability: 0.435, won: false },
    ],
  },
};

/**
 * A FIELD, not a duel: the tennis shape whose 0% tail leaves exactly two
 * survivors. `0.565 + 0.425 = 0.99` lands inside the complement band by
 * coincidence, so a pairing predicate that counted survivors would normalize two
 * of 138 entrants as if they were the two sides of one question.
 */
const TENNIS_FIELD: EventConceptShareSource = {
  event: {
    name: "US Open Men's Singles Winner",
    slug: null,
    status: "live",
    venue: null,
    location: null,
    sport_label: "Tennis",
    domain: "tennis",
  },
  primary: {
    label: "Winner",
    competitors: [
      { name: "Alexander Zverev", probability: 0.565, won: false },
      { name: "Ben Shelton", probability: 0.425, won: false },
      { name: "Cameron Norrie", probability: 0.0, won: false },
      { name: "Karen Khachanov", probability: 0.0, won: false },
    ],
  },
};

/* ────────────────────────────── the harness ─────────────────────────────── */

/** Every string the CARD puts in front of a reader, as one blob. */
async function drawCard(
  payload: EventConceptShareSource | null,
  domain: string,
  slug = "a-slug",
): Promise<string> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue(
    payload === null
      ? { ok: false, status: 503, json: async () => ({}) }
      : { ok: true, status: 200, json: async () => payload },
  ) as unknown as typeof fetch;

  await OgImage({ params: Promise.resolve({ domain, slug }) });

  return (
    renderToStaticMarkup(mockImageResponseCalls[0])
      .replace(/<[^>]+>/g, " ")
      // `&#x27;` and not only `&amp;`: the unresolved card's copy carries an
      // apostrophe, and a blob that still holds the entity silently fails a
      // `toContain` for the sentence a reader actually reads.
      .replace(/&#x27;/g, "'")
      .replace(/&amp;/g, "&")
      .replace(/\s+/g, " ")
      .trim()
  );
}

/** Every whole percent a blob prints, in order. */
function percents(text: string): string[] {
  return text.match(/\d+%/g) ?? [];
}

/** Card and caption as one blob — an unfurl is both at once. */
async function everythingSaid(
  payload: EventConceptShareSource,
  domain: string,
): Promise<string> {
  const { title, description } = buildEventConceptShareCopy(payload);
  return `${title} ${description} ${await drawCard(payload, domain)}`;
}

/* ─────────────────────────────── the pill ───────────────────────────────── */

describe("#6849 the pill names the sport, not the routing namespace", () => {
  it("the filed card stops wearing a UFC pill", async () => {
    const card = await drawCard(POWER_SLAP, "ufc");
    expect(card).toContain("COMBAT");
    expect(card).not.toContain("UFC");
  });

  it("a real UFC card in the same namespace keeps its own name", async () => {
    // Without this, `ufc → COMBAT` would be indistinguishable from a fix that
    // simply deleted the label — and the namespace's biggest tenant is the one
    // card the old map was right about.
    const card = await drawCard(REAL_UFC, "ufc");
    expect(card).toContain("UFC");
    expect(card).not.toContain("COMBAT");
  });

  it("an unresolved link falls to COMBAT, which knows less rather than more", async () => {
    // The old comment's real case: no payload, so the segment is all there is.
    // It may colour and family the card; it may not name a promotion.
    const card = await drawCard(null, "ufc");
    expect(card).toContain("This event isn't on Bain Luck");
    expect(card).toContain("COMBAT");
    expect(card).not.toContain("UFC");
  });

  it("the pill is `conceptDomainLabel`'s answer, on every arm", async () => {
    // Behaviour, not a source grep: this is what forbids a second label rule
    // growing back beside the shared one. The failed fetch is in the table
    // because it is the arm a local map would most plausibly be kept for.
    const cases: Array<[EventConceptShareSource | null, string, string | null]> = [
      [POWER_SLAP, "ufc", "Combat"],
      [REAL_UFC, "ufc", "UFC"],
      [TENNIS_FIELD, "tennis", "Tennis"],
      [null, "ufc", null],
      [null, "election", null],
      [null, "f1", null],
    ];
    for (const [payload, domain, label] of cases) {
      const card = await drawCard(payload, domain);
      expect([domain, label, card]).toEqual([
        domain,
        label,
        expect.stringContaining(conceptDomainLabel(label, domain)),
      ]);
    }
  });

  it("retiring the map is what changes `election` and `f1`, and it is recorded", async () => {
    // Both carry `sport_label: null` on production (measured 04:41Z), and both
    // PAGES already print these spellings in their own chips. Pinned so the
    // widening is a decision with a test, not a side effect nobody wrote down.
    expect(await drawCard(null, "election")).toContain("ELECTION");
    expect(await drawCard(null, "f1")).toContain("F1");
  });
});

/* ─────────────────────────────── the pair ───────────────────────────────── */

describe("#6849 the two sides of one bout are rounded once, together", () => {
  it("the filed 68/33 is gone from the card AND the caption", async () => {
    const said = await everythingSaid(POWER_SLAP, "ufc");
    expect(said).not.toContain("33%");
    expect(said).toContain("68%");
    expect(said).toContain("32%");
  });

  it("the card and the caption print the SAME pair", async () => {
    // The reason this fix lives in `pricedCompetitors` and not in the route:
    // a picture reading 68/32 under a title reading 68/33 is a worse card than
    // the one filed, and no sum guard on either half alone can see it.
    const { title } = buildEventConceptShareCopy(POWER_SLAP);
    const card = await drawCard(POWER_SLAP, "ufc");
    expect(percents(title)).toEqual(["68%", "32%"]);
    expect(percents(card)).toEqual(["68%", "32%"]);
  });

  it("the printed pair totals 100", async () => {
    const total = percents(await drawCard(POWER_SLAP, "ufc"))
      .map((p) => parseInt(p, 10))
      .reduce((a, b) => a + b, 0);
    expect(total).toBe(100);
  });

  it("a FIELD with two priced survivors is NOT normalized as a pair", async () => {
    // The trap the first version of this fix fell into, caught by this module's
    // own suite: two survivors out of four, totalling 0.99 by coincidence.
    // Naming both leaders is a display choice; normalizing them claims a shape
    // the contest does not have. 56 + 43 = 99 is the correct output here.
    const said = await everythingSaid(TENNIS_FIELD, "tennis");
    expect(said).toContain("56%");
    expect(said).toContain("43%");
    expect(said).not.toContain("57%");
  });

  it("a pairing that would print a certainty withholds the board instead", async () => {
    // Normalizing divides by the true total, so a pair totalling under 1.0
    // pushes its leader UP — `0.9895` prints "100%" once normalized, from a raw
    // price `isForecast` correctly calls a forecast. #6029's rule is about the
    // number a READER sees, so it is re-checked after the pairing that can trip
    // it. Derived from the band; no live specimen, which is why it is pinned.
    const nearCertain: EventConceptShareSource = {
      ...POWER_SLAP,
      primary: {
        label: "Main event",
        competitors: [
          { name: "Brandon Wilson", probability: 0.9895, won: false },
          { name: "Brian Ellis", probability: 0.0005, won: false },
        ],
      },
    };
    expect(eventConceptShareFacts(nearCertain).priced).toEqual([]);

    const said = await everythingSaid(nearCertain, "ufc");
    expect(said).not.toContain("100%");
    expect(said).toContain("Power Slap 23");
    // And it still does not claim a result — the board says less, not more.
    expect(said).not.toContain("won");
  });

  it("a settled card is untouched: a verdict, and no forecast either way", async () => {
    // The pairing must not reach the branch that prints no numbers at all.
    const settled: EventConceptShareSource = {
      ...POWER_SLAP,
      event: { ...POWER_SLAP.event, status: "settled" },
      primary: {
        label: "Main event",
        competitors: [
          { name: "Brandon Wilson", probability: 0.675, won: true },
          { name: "Brian Ellis", probability: 0.325, won: false },
        ],
      },
    };
    const said = await everythingSaid(settled, "ufc");
    expect(said).toContain("Brandon Wilson won");
    expect(percents(said)).toEqual([]);
  });
});
