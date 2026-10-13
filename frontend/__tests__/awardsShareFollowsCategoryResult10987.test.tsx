/**
 * #10987 — A SHARED OSCARS LINK SAYS WHAT THE PAGE SAYS.
 *
 * On the #5349 synthetic awards payload the page body shows Best Picture →
 * "Winner: Actual unpriced winner", while the tab title, `og:description` and
 * the share card printed "Forecast nominee 0" at 90%: they read the parent
 * status (`unknown`, correctly, mid-ceremony) and the price-ranked leader, and
 * never the category's own `outcomes[].won`.
 *
 * The fixture is the reader's own (`7988d54a`), byte for byte. Each case below
 * points `primary.evolution_market_id` at one of its categories; nothing else in
 * the payload is edited unless the case says so.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  buildEventConceptShareCopy,
  eventConceptShareFacts,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";
import FIXTURE from "./fixtures/awardsCategoryTruth5349.SYNTHETIC.json";

const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/event/[domain]/[slug]/opengraph-image";

const SERVED = FIXTURE as unknown as EventConceptShareSource;

/** The fixture with its primary pointed at another category (and that category's label). */
function primaryIs(marketId: number, label: string): EventConceptShareSource {
  return { ...SERVED, primary: { ...SERVED.primary, evolution_market_id: marketId, label } };
}

/** The same payload as the copy read it before #10987: no category rows. */
function withoutChildren(source: EventConceptShareSource): EventConceptShareSource {
  return { ...source, children: undefined };
}

async function drawCard(payload: EventConceptShareSource): Promise<string> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  }) as unknown as typeof fetch;
  await OgImage({ params: Promise.resolve({ domain: "awards", slug: "oscars-2026" }) });
  return renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

async function everythingSaid(payload: EventConceptShareSource) {
  const { title, description } = buildEventConceptShareCopy(payload);
  return { title, description, card: await drawCard(payload) };
}

describe("#10987 an announced primary category names its own winner", () => {
  it("the served fixture: title, description and card name the winner, no price", async () => {
    const said = await everythingSaid(SERVED);
    expect(said.title).toBe("The Oscars 2026: Actual unpriced winner won Best Picture");
    expect(said.description).toBe("Best Picture. Winner: Actual unpriced winner.");
    expect(said.card).toContain("Actual unpriced winner won");
    for (const text of Object.values(said)) {
      expect(text).not.toContain("Forecast nominee");
      expect(text).not.toMatch(/\d%/);
    }
  });

  it("the parent stays unknown — nothing is promoted to settled or Final", async () => {
    expect(SERVED.event?.status).toBe("unknown");
    const facts = eventConceptShareFacts(SERVED);
    expect(facts.settled).toBe(false);
    expect(facts.winner).toBeNull();
    expect(facts.priced).toEqual([]);
    const said = await everythingSaid(SERVED);
    expect(Object.values(said).join(" ")).not.toMatch(/Final/);
  });

  it("a tie lists every winner", async () => {
    const said = await everythingSaid(primaryIs(4, "Best Score"));
    expect(said.title).toBe("The Oscars 2026: Composer A and Composer B won Best Score");
    expect(said.description).toBe("Best Score. Joint winners: Composer A and Composer B.");
    expect(said.card).toContain("Composer A and Composer B won");
    expect(said.card).toContain("Joint winners");
    expect(Object.values(said).join(" ")).not.toMatch(/\d%|Score favorite/);
  });

  it('a category won by "Other" reads "Another nominee"', async () => {
    const said = await everythingSaid(primaryIs(5, "Best Costume"));
    expect(said.title).toBe("The Oscars 2026: Another nominee won Best Costume");
    expect(said.card).toContain("Another nominee won");
    expect(Object.values(said).join(" ")).not.toMatch(/\bOther\b|\d%|Costume favorite/);
  });
});

describe("#10987 no grade, no winner", () => {
  it("closed but ungraded prints no price and names nobody", async () => {
    const said = await everythingSaid(primaryIs(3, "Best Actor"));
    expect(said.title).toBe("The Oscars 2026");
    expect(said.description).toBe("Best Actor. Trading closed, result not announced yet.");
    expect(said.card).toContain("Trading closed");
    expect(Object.values(said).join(" ")).not.toMatch(/\d%|won|Closed favorite|Forecast nominee/);
  });

  it("graded_winner alone is not a grade: the category is closed, not announced", async () => {
    const source = structuredClone(SERVED) as EventConceptShareSource;
    for (const outcome of source.children![0].outcomes!) outcome!.won = false;
    expect(eventConceptShareFacts(source).category).toEqual({ state: "closed", winners: [], names: "" });
    expect(buildEventConceptShareCopy(source).title).not.toContain("Actual unpriced winner");
  });

  it("an open, ungraded category is unchanged", async () => {
    const open = primaryIs(2, "Best Director");
    expect(eventConceptShareFacts(open).category).toBeNull();
    expect(await everythingSaid(open)).toEqual(await everythingSaid(withoutChildren(open)));
  });

  it("the nominations prop sharing the label is not the category", async () => {
    const prop = primaryIs(7, "Best Picture");
    expect(eventConceptShareFacts(prop).category).toBeNull();
    expect(buildEventConceptShareCopy(prop)).toEqual(buildEventConceptShareCopy(withoutChildren(prop)));
  });
});

describe("#10987 ordinary share behaviour is unchanged", () => {
  it("a non-awards envelope with graded children ignores them", async () => {
    const ufc = { ...SERVED, event: { ...SERVED.event, domain: "ufc" } };
    expect(eventConceptShareFacts(ufc).category).toBeNull();
    expect(await everythingSaid(ufc)).toEqual(await everythingSaid(withoutChildren(ufc)));
  });

  it("an authoritative parent winner is not hidden behind a closed category", () => {
    const source = structuredClone(primaryIs(3, "Best Actor")) as EventConceptShareSource;
    source.event = { ...source.event, status: "settled" };
    source.primary!.competitors = [
      { name: "Closed favorite", probability: 0.99, won: true },
      { name: "Another actor", probability: 0.01, won: false },
    ];
    expect(buildEventConceptShareCopy(source).title).toBe("The Oscars 2026: Closed favorite won");
  });
});
