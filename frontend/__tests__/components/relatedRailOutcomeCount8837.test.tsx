/**
 * #8837 — ONE MARKET, ONE OUTCOME COUNT, ON THE DISCOVER CARD AND THE RAIL.
 *
 * Seen on production at 390px, 2026-09-26 ~15:00Z (discover/d549): Discover →
 * Brazil Presidential Election → the "More politics" rail.
 *
 *     Next French Presidential Election   Discover: 4 rows + "Field and 39 more outcomes"
 *                                         rail:     3 rows + "+125 more"
 *
 * The rail counted off `outcome_count` (every stored leg, 128); the Discover
 * card counts off `discover_card` through `lib/discover/futuresBoard.ts`
 * (#8025). The fix routes the rail through the same total.
 *
 * ## The specimen is production bytes
 *
 * `ux1413_related_futures_zero_row_7796.20260921.json` is a verbatim
 * `GET /api/feed?limit=100` body, and it carries 113364 — the French election —
 * at `outcome_count: 128` beside a `discover_card` whose board plus remainder is
 * 42. Same shape as the issue's minute, one day earlier.
 *
 * ## The comparison is two SHIPPED renders against each other
 *
 * Each arm reads the Discover card's remainder out of `FuturesCard`'s markup and
 * the rail's out of `RelatedByTag`'s, and requires rows-drawn + remainder to agree.
 * A change that moves both surfaces together is allowed; one that moves only one
 * is what reddens. The last block plants the old rule so the agreement assertion
 * is shown to discriminate.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import {
  futuresDistributionBoard,
  futuresOutcomeTotal,
} from "@/lib/discover/futuresBoard";
import FIXTURE from "../fixtures/ux1413_related_futures_zero_row_7796.20260921.json";
import TENNIS from "../fixtures/uxp1034_related_tennis.20260902.json";

let swrPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: swrPayload, error: undefined, isLoading: false }),
}));
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// eslint-disable-next-line @typescript-eslint/no-var-requires
const RelatedByTag = require("@/components/RelatedByTag").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { FuturesCard } = require("@/components/discover/FuturesCard");

type Item = { type: string; data: FeedFuturesData };

const FUTURES: Item[] = (FIXTURE as { items: Item[] }).items.filter(
  (item) => item.type === "futures",
);

function futuresById(id: number): Item {
  const found = FUTURES.find((item) => item.data.id === id);
  if (!found) throw new Error(`fixture has no futures ${id}`);
  return found;
}

/** The rail with exactly this one card on it. */
function railHtml(items: Item[]): string {
  swrPayload = { items };
  return renderToStaticMarkup(
    React.createElement(RelatedByTag as React.FC, {
      tags: ["category:politics"],
      limit: 200,
      title: "More politics",
    } as never),
  );
}

type RailCard = { rows: number; more: number | null };

/** Per card, how many field rows the rail drew and the `+N more` it printed. */
function railCards(markup: string): RailCard[] {
  return markup
    .split('data-testid="related-card"')
    .slice(1)
    .map((block) => {
      const card = block.split("</a>")[0];
      const more = card.match(/data-testid="related-card-more">\+(\d+) more</);
      return {
        rows: (card.match(/<li /g) ?? []).length,
        more: more ? Number(more[1]) : null,
      };
    });
}

function discoverHtml(data: FeedFuturesData): string {
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/** The number in Discover's remainder row ("Field and 38 more outcomes"). */
function discoverRemainder(markup: string): number | null {
  const m = markup
    .replace(/<[^>]*>/g, " ")
    .match(/(?:Field and )?(\d+) more outcomes?/);
  return m ? Number(m[1]) : null;
}

describe("#8837 — the French election specimen", () => {
  const france = futuresById(113364);

  test("the specimen is still the defect's shape (raw legs ≫ the card's own set)", () => {
    expect(france.data.outcome_count).toBe(128);
    expect(futuresOutcomeTotal(france.data)).toBe(42);
  });

  test("Discover and the rail state the same total", () => {
    const board = futuresDistributionBoard(france.data);
    expect(board).not.toBeNull();
    const discoverSaid = discoverRemainder(discoverHtml(france.data));
    expect(discoverSaid).toBe(board!.remainingCount);

    const [rail] = railCards(railHtml([france]));
    expect(rail.rows).toBe(3);
    expect(rail.more).not.toBeNull();

    expect(rail.rows + rail.more!).toBe(board!.rows.length + discoverSaid!);
    expect(rail.more).toBe(39);
    expect(railHtml([france])).not.toContain("+125 more");
  });
});

describe("#8837 — every board-drawing card on the banked page agrees", () => {
  const boards = FUTURES.filter((item) => futuresDistributionBoard(item.data));

  test("the population is not trivially small", () => {
    expect(boards.length).toBeGreaterThanOrEqual(30);
  });

  test.each(boards.map((item) => [item.data.id, item] as const))(
    "market %s: rail rows + remainder === Discover rows + remainder",
    (_id, item) => {
      const board = futuresDistributionBoard(item.data)!;
      const discoverSaid = discoverRemainder(discoverHtml(item.data)) ?? 0;
      const [rail] = railCards(railHtml([item]));
      expect(rail.rows + (rail.more ?? 0)).toBe(board.rows.length + discoverSaid);
    },
  );
});

describe("#8837 — unchanged directions (gotcha #43)", () => {
  test("where the card's set IS every leg, the rail prints what it always did", () => {
    // uxp1034's tennis draws: 8 + 25 = 33 = outcome_count, 8 + 15 = 23.
    swrPayload = TENNIS;
    const text = renderToStaticMarkup(
      React.createElement(RelatedByTag as React.FC, {
        tags: ["sport:tennis"],
        excludeId: 15293830,
        excludeType: "event",
        limit: 4,
        title: "More Tennis",
      } as never),
    );
    expect(text).toContain("+30 more");
    expect(text).toContain("+20 more");
  });

  test("every card on the page: rows + remainder is the card's set, never more", () => {
    // Includes the non-board formats (binary, threshold ladders): the count is a
    // property of the market, not of which treatment Discover chose for it.
    for (const item of FUTURES) {
      const total = futuresOutcomeTotal(item.data);
      const [rail] = railCards(railHtml([item]));
      if (total === null || rail.rows >= total) {
        expect(rail.more).toBeNull();
      } else {
        expect(rail.rows + (rail.more ?? 0)).toBe(total);
      }
    }
  });

  test("no served card total ⇒ no remainder, never the raw leg count", () => {
    const bare = france_without_card();
    const [rail] = railCards(railHtml([{ type: "futures", data: bare }]));
    expect(rail.rows).toBe(3);
    expect(rail.more).toBeNull();
  });
});

describe("#8837 — the agreement assertion discriminates (planted old rule)", () => {
  test("the retired rule on the same specimen disagrees with Discover", () => {
    const france = futuresById(113364);
    const board = futuresDistributionBoard(france.data)!;
    const oldMore = france.data.outcome_count - 3;
    expect(oldMore).toBe(125);
    expect(3 + oldMore).not.toBe(board.rows.length + board.remainingCount);
  });
});

function france_without_card(): FeedFuturesData {
  const { discover_card: _dropped, ...rest } = futuresById(113364).data as FeedFuturesData & {
    discover_card?: unknown;
  };
  return rest as FeedFuturesData;
}
