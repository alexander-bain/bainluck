/**
 * #5105 (thin supply) — the ordinary-live continuation stays separated after
 * client filtering, with no dropped cards, no extra rows and no mixed editions.
 *
 * Synthetic minimal fixtures only: a card is `{ id }`, identity is the
 * caller's callback. The page is not wired; these pin the unmounted adapter
 * and section component.
 */
import { renderToStaticMarkup } from "react-dom/server";
import ContinuationSections, { CONTINUATION_HEADING } from "@/components/discover/ContinuationSections";
import {
  foldContinuationPage,
  partitionBySection,
  readContinuationBoundary,
  type ContinuationPageInput,
  type ContinuationSections as Sections,
} from "@/lib/discover/continuationSections";

type Card = { id: string; data: { n: number } };
const getId = (card: Card) => card.id;

function deck(total: number): Card[] {
  return Array.from({ length: total }, (_, n) => ({ id: `c${n}`, data: { n } }));
}

function page(
  cards: Card[],
  offset: number,
  limit: number,
  extra: Partial<ContinuationPageInput<Card>> = {},
): ContinuationPageInput<Card> {
  return { items: cards.slice(offset, offset + limit), offset, total: cards.length, edition: "ed-1", ...extra };
}

function fold(prior: Sections<Card> | null, input: ContinuationPageInput<Card>): Sections<Card> {
  const result = foldContinuationPage(prior, input, getId);
  if (result.status !== "ok") throw new Error(`unexpected ${result.reason}`);
  return result.sections;
}

const ids = (cards: readonly Card[]) => cards.map(getId);

function render(opening: readonly Card[], continuation: readonly Card[]): string {
  return renderToStaticMarkup(
    <ContinuationSections
      opening={opening}
      continuation={continuation}
      renderSection={(items, section) => (
        <ul data-list={section}>
          {items.map((card) => (
            <li key={card.id}>
              <a href={`/c/${card.id}`}>{card.id}</a>
            </li>
          ))}
        </ul>
      )}
    />,
  );
}

describe("boundary metadata", () => {
  it("absent and null are legacy; 0 is a real boundary", () => {
    const cards = deck(4);
    for (const legacy of [undefined, null]) {
      const sections = fold(null, page(cards, 0, 4, { continuation_start: legacy }));
      expect(sections.boundary).toBeNull();
      expect(ids(sections.opening)).toEqual(["c0", "c1", "c2", "c3"]);
      expect(sections.continuation).toEqual([]);
    }
    const zero = fold(null, page(cards, 0, 4, { continuation_start: 0 }));
    expect(zero.boundary).toBe(0);
    expect(zero.opening).toEqual([]);
    expect(ids(zero.continuation)).toEqual(["c0", "c1", "c2", "c3"]);
  });

  it.each([
    ["boolean", true],
    ["string", "3"],
    ["fraction", 2.5],
    ["negative", -1],
    ["equal to total", 6],
    ["past total", 9],
    ["NaN", Number.NaN],
    ["Infinity", Number.POSITIVE_INFINITY],
    ["object", { start: 3 }],
  ])("a %s boundary is unsupported and fabricates no section", (_label, raw) => {
    expect(readContinuationBoundary(raw, 6)).toEqual({ kind: "invalid" });
    const result = foldContinuationPage(null, page(deck(6), 0, 6, { continuation_start: raw }), getId);
    expect(result).toEqual({ status: "unsupported", reason: "invalid_boundary" });
  });

  it("a malformed page (offset/total/items) is unsupported", () => {
    const cards = deck(6);
    for (const bad of [{ offset: "0" }, { offset: -1 }, { total: 6.5 }, { total: undefined }, { items: null }]) {
      const input = { ...page(cards, 0, 6, { continuation_start: 3 }), ...bad } as unknown as ContinuationPageInput<Card>;
      expect(foldContinuationPage(null, input, getId)).toEqual({ status: "unsupported", reason: "invalid_page" });
    }
  });
});

describe("classification survives client filtering", () => {
  const cards = deck(6);
  const sections = fold(null, page(cards, 0, 6, { continuation_start: 3 }));

  it("E=3 with an opening card removed keeps the boundary at the server position", () => {
    const filtered = cards.filter((card) => card.id !== "c1");
    // Strawman: the filtered array's 3rd index is c3's neighbour c4 — a
    // length-based boundary would seat c3 in the opening.
    expect(ids(filtered.slice(3))).toEqual(["c4", "c5"]);
    const split = partitionBySection(filtered, sections, getId);
    expect(ids(split.opening)).toEqual(["c0", "c2"]);
    expect(ids(split.continuation)).toEqual(["c3", "c4", "c5"]);
    expect(split.unclassified).toEqual([]);
  });

  it("removing the first continuation card does not move the boundary", () => {
    const filtered = cards.filter((card) => card.id !== "c3");
    const split = partitionBySection(filtered, sections, getId);
    expect(ids(split.opening)).toEqual(["c0", "c1", "c2"]);
    expect(ids(split.continuation)).toEqual(["c4", "c5"]);
  });

  it("keeps original references, data and the caller's within-section order", () => {
    const reordered = [cards[5], cards[0], cards[4], cards[2]];
    const split = partitionBySection(reordered, sections, getId);
    expect(split.opening[0]).toBe(cards[0]);
    expect(split.opening[1]).toBe(cards[2]);
    expect(split.continuation[0]).toBe(cards[5]);
    expect(split.continuation[1]).toBe(cards[4]);
    expect(sections.opening[1]).toBe(cards[1]);
    expect(cards[4].data).toEqual({ n: 4 });
  });

  it("a card the deck never received is unclassified, not seated", () => {
    const synthetic: Card = { id: "challenge", data: { n: -1 } };
    const split = partitionBySection([synthetic, cards[0]], sections, getId);
    expect(split.unclassified).toEqual([synthetic]);
    expect(ids(split.opening)).toEqual(["c0"]);
  });
});

describe("pages before, at and after the boundary", () => {
  it("classifies each page from offset + raw index", () => {
    const cards = deck(60);
    let sections = fold(null, page(cards, 0, 20, { continuation_start: 25 }));
    expect(sections.continuation).toEqual([]);
    sections = fold(sections, page(cards, 20, 20, { continuation_start: 25 }));
    expect(ids(sections.opening).slice(-5)).toEqual(["c20", "c21", "c22", "c23", "c24"]);
    expect(ids(sections.continuation)[0]).toBe("c25");
    expect(sections.continuation).toHaveLength(15);
    sections = fold(sections, page(cards, 40, 20, { continuation_start: 25 }));
    expect(sections.opening).toHaveLength(25);
    expect(sections.continuation).toHaveLength(35);
  });

  it("a page that starts exactly at the boundary is all continuation", () => {
    const cards = deck(40);
    let sections = fold(null, page(cards, 0, 20, { continuation_start: 20 }));
    sections = fold(sections, page(cards, 20, 20, { continuation_start: 20 }));
    expect(ids(sections.opening)).toEqual(ids(cards.slice(0, 20)));
    expect(ids(sections.continuation)).toEqual(ids(cards.slice(20)));
  });

  it("a duplicate page adds no card and no second heading", () => {
    const cards = deck(10);
    const first = fold(null, page(cards, 0, 10, { continuation_start: 6 }));
    const again = fold(first, page(cards, 0, 10, { continuation_start: 6 }));
    expect(ids(again.opening)).toEqual(ids(first.opening));
    expect(ids(again.continuation)).toEqual(ids(first.continuation));
    const html = render(again.opening, again.continuation);
    expect(html.split(CONTINUATION_HEADING)).toHaveLength(2);
    expect(html.split("<li>")).toHaveLength(11);
  });
});

describe("incompatible pages are refused without touching caller state", () => {
  const cards = deck(40);
  const prior = fold(null, page(cards, 0, 20, { continuation_start: 25 }));
  const snapshot = {
    opening: [...prior.opening],
    continuation: [...prior.continuation],
    membership: [...prior.membership],
  };

  it.each([
    ["another edition", { edition: "ed-2" }, "edition_mismatch"],
    ["no edition", { edition: undefined }, "edition_missing"],
    ["another boundary", { continuation_start: 30 }, "boundary_mismatch"],
    ["a legacy page", { continuation_start: null }, "boundary_mismatch"],
    ["another total", { total: 41 }, "total_mismatch"],
  ])("%s → unsupported", (_label, extra, reason) => {
    const result = foldContinuationPage(prior, page(cards, 20, 20, { continuation_start: 25, ...extra }), getId);
    expect(result).toEqual({ status: "unsupported", reason });
    expect(prior.opening).toEqual(snapshot.opening);
    expect(prior.continuation).toEqual(snapshot.continuation);
    expect([...prior.membership]).toEqual(snapshot.membership);
  });

  it("a section page after a legacy page is unsupported", () => {
    const legacy = fold(null, page(cards, 0, 20));
    expect(foldContinuationPage(legacy, page(cards, 20, 20, { continuation_start: 25 }), getId)).toEqual({
      status: "unsupported",
      reason: "boundary_mismatch",
    });
  });

  it("a held card placed in the other section is a conflict, state untouched", () => {
    const shifted = { items: [cards[30]], offset: 0, total: 40, edition: "ed-1", continuation_start: 25 };
    const withCard = fold(null, { ...shifted, offset: 30 });
    expect(foldContinuationPage(withCard, shifted, getId)).toEqual({ status: "unsupported", reason: "membership_conflict" });
    expect(ids(withCard.continuation)).toEqual(["c30"]);
    expect(withCard.membership.get("c30")).toBe("continuation");
  });
});

describe("section component", () => {
  const cards = deck(6);
  const sections = fold(null, page(cards, 0, 6, { continuation_start: 3 }));

  it("renders opening cards, then one labelled section with the continuation in order", () => {
    const html = render(sections.opening, sections.continuation);
    const headingAt = html.indexOf(CONTINUATION_HEADING);
    expect(html.indexOf("c2")).toBeLessThan(html.indexOf("<section"));
    expect(html.indexOf("<section")).toBeLessThan(headingAt);
    expect(headingAt).toBeLessThan(html.indexOf("c3"));
    expect(html.indexOf("c3")).toBeLessThan(html.indexOf("c4"));
    expect(html.indexOf("c4")).toBeLessThan(html.indexOf("c5"));
    const labelledBy = /<section aria-labelledby="([^"]+)"/.exec(html)?.[1];
    expect(labelledBy).toBeTruthy();
    expect(html).toContain(`<h2 id="${labelledBy}"`);
    expect(html).toContain('href="/c/c3"');
    expect(html).toContain("text-text-primary");
  });

  it("all opening filtered: the heading leads, no blank opening", () => {
    const split = partitionBySection(cards.slice(3), sections, getId);
    const html = render(split.opening, split.continuation);
    expect(html).not.toContain('data-list="opening"');
    expect(html.startsWith("<section")).toBe(true);
  });

  it("all continuation filtered: no orphan heading", () => {
    const split = partitionBySection(cards.slice(0, 3), sections, getId);
    const html = render(split.opening, split.continuation);
    expect(html).not.toContain(CONTINUATION_HEADING);
    expect(html).not.toContain("<section");
  });

  it("legacy decks render exactly what the opening list alone renders", () => {
    const legacy = fold(null, page(cards, 0, 6));
    const split = partitionBySection(cards, legacy, getId);
    split.opening.forEach((card, n) => expect(card).toBe(cards[n]));
    expect(split.continuation).toEqual([]);
    const alone = renderToStaticMarkup(
      <ul data-list="opening">
        {cards.map((card) => (
          <li key={card.id}>
            <a href={`/c/${card.id}`}>{card.id}</a>
          </li>
        ))}
      </ul>,
    );
    expect(render(split.opening, split.continuation)).toBe(alone);
  });
});
