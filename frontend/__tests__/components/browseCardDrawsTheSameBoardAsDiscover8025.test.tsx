// #8025 — THE SAME FIELD, WHICHEVER PAGE YOU CAME IN THROUGH.
//
// `2027 IPL Champion` (market 31834252) is a ten-team field with eight priced
// outcomes. On `/discover` it drew a ranked board of four over "Field and 6 more
// outcomes". On `/categories/cricket`, `/sports` and `/my-stuff` — which render
// through `components/FeedCard.tsx` — it drew three rows totalling 43%, with
// nothing saying the other seven teams existed. The browse card read
// `top_outcomes` and contained no reference to `discover_card` at all.
//
// Measured on `GET /api/feed?limit=200`, 2026-09-22 15:4xZ: 83 futures cards, 44
// of which clear the board's bar. The majority of the futures cards on those
// three surfaces were drawing a smaller field than the market has.
//
// ## What this file guards, and why it renders rather than checks the rule
//
// `futuresBoardRule8025.test.ts` beside it drives the shared module directly. A
// pure-lib guard cannot see whether either component CALLS it — which is exactly
// the state this ship found, with the rule sitting inline in one card and absent
// from the other. So every assertion below reads `renderToStaticMarkup` output
// from the SHIPPED components, and the agreement block compares the two cards'
// markup against each other rather than against a hand-written expectation: a
// future change that moves both surfaces together is allowed, and one that moves
// only one of them is what reddens.
//
// The last block plants failures, so the assertions cannot pass vacuously.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "../../components/FeedCard";
import { FuturesCard } from "../../components/discover/FuturesCard";

/**
 * The IPL specimen from #8025, shaped as the payload serves it: ten outcomes,
 * eight of them on the distribution board, three on `top_outcomes`.
 */
const IPL_BOARD = [
  { label: "Royal Challengers Bengaluru", probability: 0.22, movement: null },
  { label: "Mumbai Indians", probability: 0.11, movement: null },
  { label: "Chennai Super Kings", probability: 0.1, movement: null },
  { label: "Kolkata Knight Riders", probability: 0.09, movement: null },
  { label: "Gujarat Titans", probability: 0.08, movement: null },
  { label: "Rajasthan Royals", probability: 0.07, movement: null },
  { label: "Delhi Capitals", probability: 0.06, movement: null },
  { label: "Punjab Kings", probability: 0.04, movement: null },
];

function iplData(over: Record<string, unknown> = {}): FeedFuturesData {
  return {
    id: 31834252,
    name: "2027 IPL Champion",
    llm_sport_category: "cricket",
    sport_name: "Cricket",
    status: "open",
    source: "kalshi",
    source_count: 1,
    resolution_date: "2027-06-06T00:00:00Z",
    outcome_count: 10,
    top_outcomes: IPL_BOARD.slice(0, 3).map((row, i) => ({
      id: i + 1,
      rank: i + 1,
      name: row.label,
      probability: row.probability,
      movement: null,
    })),
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: IPL_BOARD,
      remaining_outcome_count: 2,
      field_is_a_race: true,
    },
    ...over,
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data,
  } as unknown as FeedItem;
}

const browseHtml = (data: FeedFuturesData) =>
  renderToStaticMarkup(<FeedCard item={itemFor(data)} />);

const discoverHtml = (data: FeedFuturesData) =>
  renderToStaticMarkup(
    <FuturesCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );

/** Which of the eight board labels a rendering actually printed. */
function labelsDrawn(html: string): string[] {
  return IPL_BOARD.map((r) => r.label).filter((label) => html.includes(label));
}

/** The remainder row's sentence, or null when the row was not drawn. */
function remainderSentence(html: string): string | null {
  const m = html.match(/data-row="field-remainder"[\s\S]{0,400}?>([^<]*more outcomes?)</);
  return m ? m[1] : null;
}

// ── 1. THE DEFECT: the browse card drew three of ten and said nothing ────────

describe("the browse card draws the whole board", () => {
  it("draws four board rows, not the three top_outcomes carried", () => {
    const drawn = labelsDrawn(browseHtml(iplData()));
    expect(drawn).toEqual([
      "Royal Challengers Bengaluru",
      "Mumbai Indians",
      "Chennai Super Kings",
      "Kolkata Knight Riders",
    ]);
  });

  it("tells the reader how much field it did not draw", () => {
    // 2 served remainder + (8 priced − 4 drawn) = 6, the same arithmetic
    // `/discover` has always done.
    expect(remainderSentence(browseHtml(iplData()))).toBe("Field and 6 more outcomes");
  });

  it("the defect really was a three-row card — the fixture can show it", () => {
    // Strips the board and leaves `top_outcomes` alone: this is precisely what
    // the browse card rendered for this market before the ship, so if the
    // assertions above ever pass for the wrong reason, this one says so.
    const withoutBoard = iplData({ discover_card: undefined });
    expect(labelsDrawn(browseHtml(withoutBoard))).toEqual([
      "Royal Challengers Bengaluru",
      "Mumbai Indians",
      "Chennai Super Kings",
    ]);
    expect(remainderSentence(browseHtml(withoutBoard))).toBeNull();
  });
});

// ── 2. ONE RULE: the two cards agree on rows, percents and remainder ─────────

describe("the browse card and the Discover card read one board", () => {
  it("draws the same rows in the same order", () => {
    const data = iplData();
    expect(labelsDrawn(browseHtml(data))).toEqual(labelsDrawn(discoverHtml(data)));
  });

  it("prints the same percent for every row it draws", () => {
    const data = iplData();
    // Read off the shipped markup rather than recomputed: a shared rounding
    // helper that neither card called would leave this green.
    const percents = (html: string) =>
      Array.from(html.matchAll(/(&lt;1%|&gt;99%|\d{1,3}%)/g)).map((m) => m[1]);
    const browse = percents(browseHtml(data));
    for (const p of percents(discoverHtml(data))) {
      expect(browse).toContain(p);
    }
  });

  it("says the same sentence about the field it did not draw", () => {
    const data = iplData();
    expect(remainderSentence(browseHtml(data))).toBe(remainderSentence(discoverHtml(data)));
  });

  it("drops 'Field and' on both cards when the field is not a race", () => {
    // #7844 half two — an independent set has no residual field. The claim comes
    // off BOTH surfaces or the browse card re-states something Discover retracted.
    const data = iplData({
      discover_card: {
        suggested_format: "outcome_distribution",
        distribution_outcomes: IPL_BOARD,
        remaining_outcome_count: 2,
        field_is_a_race: false,
      },
    });
    expect(remainderSentence(browseHtml(data))).toBe("6 more outcomes");
    expect(remainderSentence(discoverHtml(data))).toBe("6 more outcomes");
  });
});

// ── 3. THE ARM THAT DOES NOT CHANGE ──────────────────────────────────────────

describe("a card with no board renders exactly as it did", () => {
  it("keeps the top_outcomes rows when the format is not a distribution", () => {
    const data = iplData({
      discover_card: {
        suggested_format: "hero",
        distribution_outcomes: IPL_BOARD,
        remaining_outcome_count: 2,
      },
    });
    expect(labelsDrawn(browseHtml(data)).length).toBe(3);
    expect(remainderSentence(browseHtml(data))).toBeNull();
  });

  it("keeps the top_outcomes rows when too few rows carry a number", () => {
    // #6505 — three priced rows out of three is below the bar of four and the
    // board is not drawn. Not a bend case: `distribution_outcomes` never had
    // four, so `droppedBelowTheBar` is false.
    const data = iplData({
      discover_card: {
        suggested_format: "outcome_distribution",
        distribution_outcomes: IPL_BOARD.slice(0, 3),
        remaining_outcome_count: 7,
      },
    });
    expect(remainderSentence(browseHtml(data))).toBeNull();
    expect(labelsDrawn(browseHtml(data)).length).toBe(3);
  });
});

// ── 4. THE ASSERTIONS CAN FAIL ───────────────────────────────────────────────

describe("planted failures", () => {
  it("a board label the payload does not carry is not reported as drawn", () => {
    expect(labelsDrawn(browseHtml(iplData()))).not.toContain("Punjab Kings");
  });

  it("the remainder reader returns null on markup with no remainder row", () => {
    expect(remainderSentence("<div>Field and 6 more outcomes</div>")).toBeNull();
  });

  it("the remainder reader reads the count, not a constant", () => {
    const data = iplData({
      discover_card: {
        suggested_format: "outcome_distribution",
        distribution_outcomes: IPL_BOARD,
        remaining_outcome_count: 0,
      },
    });
    // 0 served + (8 − 4) = 4.
    expect(remainderSentence(browseHtml(data))).toBe("Field and 4 more outcomes");
  });
});
