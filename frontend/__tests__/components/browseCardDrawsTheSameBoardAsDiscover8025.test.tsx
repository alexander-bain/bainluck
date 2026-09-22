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

// ── 2b. #8033'S PAIR REPAIR IS PART OF THE BOARD RULE, SO BOTH CARDS HAVE IT ─
//
// This block exists because of how this ship nearly shipped. #8033 landed on
// `discover/FuturesCard.tsx` WHILE that card still privately owned the board, so
// the rule "the top two may not own more than the race" was written into the
// same lines this ship extracts. Rebasing the extraction onto it produced a
// conflict whose obvious resolution — take the extracted version — silently
// deleted the repair.
//
// #8033's own guard (`raceBoardTopTwoOverHundred8033.test.tsx`) renders
// `DiscoverCard` and would have caught that on the Discover side. NOTHING would
// have caught it here: the browse card had no board at all when #8033 was
// written, so no guard anywhere asserted that THIS card can add up. It now draws
// the identical top two, which is precisely what makes it able to print 101%.
//
// The specimen is #8033's own: `Brazil Presidential Election` market 112996,
// raw legs 0.5955 / 0.405 measured off `GET /api/feed?limit=200`. Independently
// rounded they print 60% and 41% — 101% of a mutually exclusive race, refutable
// by a reader adding two numbers.

const BRAZIL_BOARD = [
  { label: "Flávio Bolsonaro", probability: 0.5955, movement: null },
  { label: "Luiz Inácio Lula da Silva", probability: 0.405, movement: null },
  { label: "Renan Santos", probability: 0.0075, movement: null },
  { label: "Jair Bolsonaro", probability: 0.0015, movement: null },
];

function brazilData(fieldIsARace?: boolean): FeedFuturesData {
  const discoverCard: Record<string, unknown> = {
    suggested_format: "outcome_distribution",
    distribution_outcomes: BRAZIL_BOARD,
    remaining_outcome_count: 12,
  };
  // Omit the key entirely rather than sending `null` when undefined — "an older
  // payload" is the case the closed gate exists for, and that is what one sends.
  if (fieldIsARace !== undefined) discoverCard.field_is_a_race = fieldIsARace;
  return iplData({
    id: 112996,
    name: "Brazil Presidential Election",
    llm_sport_category: "politics",
    outcome_count: 32,
    top_outcomes: BRAZIL_BOARD.slice(0, 3).map((row, i) => ({
      id: i + 1,
      rank: i + 1,
      name: row.label,
      probability: row.probability,
      movement: null,
    })),
    discover_card: discoverCard,
  });
}

/**
 * The percent each BOARD ROW printed, in rendered order.
 *
 * Anchored on each row's own `title="<label>"` and then the first numeric cell
 * after it, rather than on every percent in the markup: both cards print the
 * leader a second time in a hero rail above the board, so a document-wide sweep
 * reads that one first and every index is off by one. `renderToStaticMarkup`
 * escapes the `<` of UX-P046's `<1%`, so the entity is decoded here — asserting
 * `&lt;1%` would pin the escaping rather than the reading.
 */
function boardPercents(html: string): string[] {
  return BRAZIL_BOARD.map((row) => ({
    at: html.indexOf(`title="${row.label}"`),
  }))
    .filter((x) => x.at !== -1)
    .sort((a, b) => a.at - b.at)
    .map((x) => {
      const m = /tabular-nums[^>]*>([^<]*)</.exec(html.slice(x.at));
      return m ? m[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">") : "";
    })
    .filter((c) => c.endsWith("%"));
}

describe("the top two may not own more than the race, on either card", () => {
  it("the browse card prints a top two a reader can add up", () => {
    const cells = boardPercents(browseHtml(brazilData(true)));
    expect(cells.slice(0, 2)).toEqual(["60%", "40%"]);
    const topTwo = cells
      .slice(0, 2)
      .map((c) => Number.parseInt(c.replace("%", ""), 10))
      .reduce((a, b) => a + b, 0);
    expect(topTwo).toBe(100);
  });

  it("both cards print the identical top two", () => {
    const data = brazilData(true);
    expect(boardPercents(browseHtml(data)).slice(0, 2)).toEqual(
      boardPercents(discoverHtml(data)).slice(0, 2),
    );
  });

  it("does not move the leader on either card", () => {
    // Clause 4 — only the second row is derived, as `100 - leader`. A repair that
    // normalized index 0 would print 60 on THIS specimen too, so the guard that
    // discriminates is the runner-up, asserted above.
    const data = brazilData(true);
    expect(boardPercents(browseHtml(data))[0]).toBe("60%");
    expect(boardPercents(discoverHtml(data))[0]).toBe("60%");
  });

  it("THE DEFECT IS REAL: without the repair the browse card prints 101%", () => {
    // `field_is_a_race: false` is the widening control AND the strawman. It is
    // the one input for which the repair is correctly refused, so it renders the
    // unrepaired arithmetic — which is exactly what a resolution that dropped
    // `rowPercents` would have printed for every board.
    const cells = boardPercents(browseHtml(brazilData(false)));
    expect(cells.slice(0, 2)).toEqual(["60%", "41%"]);
    expect(
      cells
        .slice(0, 2)
        .map((c) => Number.parseInt(c.replace("%", ""), 10))
        .reduce((a, b) => a + b, 0),
    ).toBe(101);
  });

  it("fails CLOSED on a payload that never said the field is exclusive", () => {
    // The two `field_is_a_race` derivations differ on purpose: the podium
    // question fails to today's rendering on an absent key (`!== false`), the
    // pair repair fails closed (`=== true`). Deriving a row down a point on a
    // board that turns out to be independent is a wrong number, not a missing
    // repair — and both cards must agree about that too.
    const data = brazilData(undefined);
    expect(boardPercents(browseHtml(data)).slice(0, 2)).toEqual(["60%", "41%"]);
    expect(boardPercents(discoverHtml(data)).slice(0, 2)).toEqual(["60%", "41%"]);
  });

  it("leaves every row beneath the pair alone on both cards", () => {
    const data = brazilData(true);
    expect(boardPercents(browseHtml(data)).slice(2, 4)).toEqual(
      boardPercents(discoverHtml(data)).slice(2, 4),
    );
    expect(boardPercents(browseHtml(data)).slice(2, 4)).toEqual(["1%", "<1%"]);
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
