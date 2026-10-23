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
const mockImageResponseOptions: Array<{ headers?: Record<string, string> }> = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(
    element: React.ReactElement,
    options: { headers?: Record<string, string> },
  ) {
    mockImageResponseCalls.push(element);
    mockImageResponseOptions.push(options);
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
  mockImageResponseOptions.length = 0;
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
    expect(said.description).toBe("Best Actor. Trading closed, result not yet confirmed.");
    expect(said.card).toContain("Trading closed");
    expect(Object.values(said).join(" ")).not.toMatch(/\d%|won|Closed favorite|Forecast nominee/);
  });

  it("graded_winner alone is not a grade: the category is closed, not announced", async () => {
    const source = structuredClone(SERVED) as EventConceptShareSource;
    for (const outcome of source.children![0].outcomes!) outcome!.won = false;
    expect(eventConceptShareFacts(source).category).toEqual({ state: "closed", winners: [], names: "" });
    expect(buildEventConceptShareCopy(source).title).not.toContain("Actual unpriced winner");
  });

  it("rows served without any `won` key (today's master shape) announce nobody", async () => {
    const source = structuredClone(SERVED) as EventConceptShareSource;
    for (const outcome of source.children![0].outcomes!) delete outcome!.won;
    expect(eventConceptShareFacts(source).category).toEqual({ state: "closed", winners: [], names: "" });
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
});

/**
 * #10987 (2026-10-20) — THE PARENT'S `won` FLAG NEVER OUTRANKS THE PRIMARY'S OWN
 * CATEGORY.
 *
 * Production 2026-10-20 12:20Z, `/event/awards/emmys-2026` (discover's 390px
 * reader pass for #11328): event `settled`, primary 59172874 "Emmy winner:
 * Outstanding Guest Actor in a Drama Series", all 55 categories `settled: true`
 * with no `won` outcome. The page drew "Trading closed" on that category; the
 * tab title read "The Emmys 2026: Ernest Harden, Jr. won". The capture trimmed
 * `primary.competitors`, so the flag below is CONSTRUCTED — it is the only
 * input the copy reads that can print that title, and `event_awards.py` sets it
 * from a price (the grading-lag crown) as well as from `is_winner`.
 */
function emmysShaped(): EventConceptShareSource {
  const source = structuredClone(primaryIs(3, "Emmy winner: Outstanding Guest Actor in a Drama Series")) as EventConceptShareSource;
  source.event = { ...source.event, name: "The Emmys 2026", status: "settled" };
  // Today's master shape: category rows carry no `won` key at all.
  for (const child of source.children ?? []) {
    for (const outcome of child?.outcomes ?? []) delete outcome!.won;
  }
  source.primary!.competitors = [
    { name: "Ernest Harden, Jr.", probability: 0.97, won: true },
    { name: "Another guest actor", probability: 0.03, won: false },
  ];
  return source;
}

describe("#10987 the primary category's own result is the whole answer", () => {
  it("Emmys shape: a crowned parent leader is not named over a closed category", async () => {
    const source = emmysShaped();
    const facts = eventConceptShareFacts(source);
    expect(facts.category).toEqual({ state: "closed", winners: [], names: "" });
    expect(facts.winner).toBeNull();
    expect(facts.priced).toEqual([]);

    const said = await everythingSaid(source);
    expect(said.title).toBe("The Emmys 2026");
    expect(said.description).toBe(
      "Emmy winner: Outstanding Guest Actor in a Drama Series. Trading closed, result not yet confirmed.",
    );
    expect(said.card).toContain("Trading closed");
    expect(said.card).toContain("Result not yet confirmed");
    const all = Object.values(said).join(" ");
    expect(all).not.toMatch(/Ernest Harden|\bwon\b|Final|\d%/);
    expect(all).not.toMatch(/not announced/i);
  });

  it("the closed card is not cached as a terminal picture", async () => {
    await drawCard(emmysShaped());
    const closedCache = mockImageResponseOptions[0]?.headers?.["cache-control"];
    await drawCard(withoutChildren(emmysShaped()));
    // Control: the same payload with no category row is the parent-winner card,
    // which IS terminal — so the two cache lines must differ.
    expect(mockImageResponseOptions[0]?.headers?.["cache-control"]).not.toBe(closedCache);
  });

  it("an announced category names only its own winners, never a different crowned leader", async () => {
    const source = structuredClone(primaryIs(4, "Best Score")) as EventConceptShareSource;
    source.event = { ...source.event, status: "settled" };
    source.primary!.competitors = [{ name: "Crowned by price", probability: 0.98, won: true }];
    const facts = eventConceptShareFacts(source);
    expect(facts.winner).toBeNull();
    const said = await everythingSaid(source);
    expect(said.title).toBe("The Oscars 2026: Composer A and Composer B won Best Score");
    expect(said.card).toContain("Composer A and Composer B won");
    expect(Object.values(said).join(" ")).not.toMatch(/Crowned by price|\d%/);
  });

  it("an open category still falls through to the pre-#10987 copy, parent winner included", async () => {
    const source = structuredClone(primaryIs(2, "Best Director")) as EventConceptShareSource;
    source.event = { ...source.event, status: "settled" };
    source.primary!.competitors = [{ name: "Parent winner", probability: 0.99, won: true }];
    expect(eventConceptShareFacts(source).category).toBeNull();
    expect(eventConceptShareFacts(source).winner).toBe("Parent winner");
    expect(await everythingSaid(source)).toEqual(await everythingSaid(withoutChildren(source)));
  });

  it("a non-awards settled event keeps its authoritative winner", async () => {
    const source = structuredClone(emmysShaped()) as EventConceptShareSource;
    source.event = { ...source.event, domain: "ufc" };
    expect(eventConceptShareFacts(source).category).toBeNull();
    expect(buildEventConceptShareCopy(source).title).toBe("The Emmys 2026: Ernest Harden, Jr. won");
    expect(await everythingSaid(source)).toEqual(await everythingSaid(withoutChildren(source)));
  });
});
