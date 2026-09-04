/**
 * CERT-867 — the ladder share sentence names the ladder's OWN axis.
 *
 * UX-1052 item 4 gave the `threshold_heatmap` card a share sentence that reads
 * forwards and says how many rungs the ladder has. It spelled that count "N
 * windows", because the card it shipped against was a date ladder ("Before
 * October · Before 2027"). `threshold_heatmap` is not only the date card: the
 * same branch draws magnitude ladders, and those got told they had windows too.
 *
 * The block's own words: *"`FuturesCard.tsx` unconditionally sends the
 * date-specific `buildLadderShareText`, so CPI/temperature/quantity cards tell
 * users they have 'N windows.'"*
 *
 * WHY IT SHIPPED GREEN, which is the part worth not repeating. UX-1052's guard
 * asserts `buildLadderShareText` directly and then says, of the wiring:
 * *"Reaching into the component would be a lie; instead prove the card renders
 * the ladder branch … and that the branch's inputs are the ones the builder is
 * asserted on above."* Asserting the builder proves the SENTENCE is well-formed
 * and is silent on which arguments the card hands it — so a correct builder and
 * a wrong call site are indistinguishable to it. Capturing the prop at the
 * `ActionBar` boundary is not reaching into the component; it is observing the
 * one place the value actually leaves it, and it is the only arm that can go
 * red on this defect.
 *
 * BOTH FIXTURES ARE REAL PAYLOADS, not hand-built shapes:
 *   - the magnitude ladder is market 60124859 off `GET /api/feed` on
 *     2026-09-04, verbatim rungs;
 *   - the date ladder is market 109349, the payload UX-1052 committed.
 *
 * And the live population is why this is a defect rather than an edge case: on
 * that same feed read, SIX of six `threshold_heatmap` cards were magnitude
 * ladders and NONE was a date ladder. Of those six, two carried enough distinct
 * rungs to render the ladder branch at all — a share price and a box-office
 * gross — so every ladder share sentence the site could produce that day was
 * wrong.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

/** Prop captures from the mocked `ActionBar`. `mock`-prefixed for jest hoisting. */
const mockShareCalls: { shareTitle: string; shareText: string }[] = [];

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// Everything real except `ActionBar`, which records the props the card hands it.
// `requireActual` matters: this module also exports the animated probability,
// the badges and the chip the heatmap branch renders, and stubbing those would
// change what is under test.
jest.mock("@/components/discover/shared", () => {
  const actual = jest.requireActual("@/components/discover/shared");
  const ReactLib = require("react");
  return {
    ...actual,
    ActionBar: (props: { shareTitle: string; shareText: string }) => {
      mockShareCalls.push({ shareTitle: props.shareTitle, shareText: props.shareText });
      return ReactLib.createElement("div", { "data-testid": "action-bar" });
    },
  };
});

import { FuturesCard } from "@/components/discover/FuturesCard";
import { buildLadderShareText } from "@/lib/share";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

// ── FIXTURES ──────────────────────────────────────────────────────────────

/** Market 60124859, `GET /api/feed` 2026-09-04. A ladder in DOLLARS. */
const MSFT_DATA = {
  id: 60124859,
  name: "Microsoft (MSFT) closes above ___ on September 4?",
  sport: null,
  sport_name: null,
  llm_sport_category: "economics",
  source: "polymarket",
  source_count: 1,
  market_tier: 2,
  market_type: "quantity",
  status: "open",
  resolution_date: "2026-09-04T20:00:00+00:00",
  top_outcomes: [
    { id: 224215523, name: "$490", probability: 0.9455, rank: 1, movement: 0.046 },
    { id: 224212353, name: "$480", probability: 0.9235, rank: 2, movement: -0.0565 },
    { id: 224215524, name: "$500", probability: 0.905, rank: 3, movement: null },
  ],
  outcome_count: 7,
  confidence_tier: "moderate",
  discover_card: {
    suggested_format: "threshold_heatmap",
    bundle_candidate: false,
    comparison_theme: null,
    threshold_points: [
      { source: "outcome", label: "$480", value: 480.0, unit: "$", direction: "exact", probability: 0.9235 },
      { source: "outcome", label: "$490", value: 490.0, unit: "$", direction: "exact", probability: 0.9455 },
      { source: "outcome", label: "$500", value: 500.0, unit: "$", direction: "exact", probability: 0.905 },
      { source: "outcome", label: "$510", value: 510.0, unit: "$", direction: "exact", probability: 0.605 },
      { source: "outcome", label: "$520", value: 520.0, unit: "$", direction: "exact", probability: 0.225 },
    ],
    distribution_outcomes: [],
    remaining_outcome_count: 0,
    qa_signals: [],
    public_source_disagreement: false,
    reasons: ["threshold_values"],
  },
} as unknown as FeedFuturesData;

/** Market 109349 — the date ladder UX-1052 shipped against. A ladder in TIME. */
const IPHONE_DATA = {
  id: 109349,
  name: "When will Apple release the iPhone 18?",
  sport: null,
  sport_name: null,
  llm_sport_category: "tech",
  source: "kalshi",
  source_count: 1,
  market_tier: 2,
  market_type: "quantity",
  status: "open",
  resolution_date: "2027-04-01T03:59:00+00:00",
  top_outcomes: [
    { id: 1596638, name: "Before 2027", probability: 0.15, rank: 1, movement: null },
    { id: 1596639, name: "Before October", probability: 0.065, rank: 2, movement: null },
  ],
  outcome_count: 4,
  confidence_tier: "low",
  discover_card: {
    suggested_format: "threshold_heatmap",
    bundle_candidate: false,
    comparison_theme: null,
    threshold_points: [
      { source: "date_bucket", label: "Before April", value: 202604, unit: "date", direction: "before", probability: 0.01, movement: null },
      { source: "date_bucket", label: "Before July", value: 202607, unit: "date", direction: "before", probability: 0.01, movement: null },
      { source: "date_bucket", label: "Before October", value: 202610, unit: "date", direction: "before", probability: 0.065, movement: -0.305 },
      { source: "date_bucket", label: "Before 2027", value: 202701, unit: "date", direction: "before", probability: 0.15, movement: -0.02 },
    ],
    distribution_outcomes: [],
    remaining_outcome_count: 0,
    qa_signals: [],
    public_source_disagreement: false,
    reasons: ["threshold_values"],
  },
} as unknown as FeedFuturesData;

/**
 * A market with no ladder at all — it falls through to the one-number card.
 * The CONTROL for "this repair did not touch the other branches' share text".
 */
const PLAIN_DATA = {
  id: 60000001,
  name: "Who wins the 2026 Formula 1 Drivers' Championship?",
  sport: null,
  sport_name: null,
  llm_sport_category: "motorsports",
  source: "kalshi",
  source_count: 1,
  market_tier: 2,
  market_type: "championship",
  status: "open",
  resolution_date: "2026-12-06T18:00:00+00:00",
  top_outcomes: [
    { id: 1, name: "Lando Norris", probability: 0.82, rank: 1, movement: null },
    { id: 2, name: "Max Verstappen", probability: 0.12, rank: 2, movement: null },
  ],
  outcome_count: 2,
  confidence_tier: "high",
} as unknown as FeedFuturesData;

function itemFor(data: FeedFuturesData, reason: string): FeedItem {
  return {
    type: "futures",
    score: 60,
    reason,
    headline: reason,
    context_summary: reason,
    data,
  } as unknown as FeedItem;
}

/**
 * Render one card and return the share props it handed `ActionBar`.
 *
 * Asserts its own yield: exactly one action bar per card. A silent zero would
 * make every expectation below pass against nothing, which is the failure mode
 * a capture-based guard is most prone to.
 */
function sharePropsFor(data: FeedFuturesData, reason: string): { shareTitle: string; shareText: string } {
  mockShareCalls.length = 0;
  const html = renderToStaticMarkup(
    <FuturesCard item={itemFor(data, reason)} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
  if (mockShareCalls.length !== 1) {
    throw new Error(
      `expected exactly 1 ActionBar render, captured ${mockShareCalls.length}; ` +
        `card markup was ${html.length} chars`,
    );
  }
  return mockShareCalls[0];
}

// ── THE SHIP ──────────────────────────────────────────────────────────────

describe("CERT-867 — a magnitude ladder is not made of windows", () => {
  it("the fixtures really do render the ladder branch (else everything below is vacuous)", () => {
    for (const data of [MSFT_DATA, IPHONE_DATA]) {
      const html = renderToStaticMarkup(
        <FuturesCard item={itemFor(data, "x")} data={data} liked={false} setLiked={() => {}} trending={false} />,
      );
      expect(html).toContain('data-card-format="heatmap"');
    }
  });

  it("a dollar ladder counts OUTCOMES, and says nothing about windows", () => {
    const { shareText } = sharePropsFor(MSFT_DATA, "Big odds movement in Microsoft (MSFT)");
    expect(shareText).toBe(
      "Microsoft (MSFT) closes above ___ on September 4? — $490 leads at 95% across 5 outcomes on Bain Luck.",
    );
    expect(shareText).not.toContain("window");
  });

  it("the noun is bound to the CARD, not to the render order", () => {
    // Both kinds, in one test, compared as (title, noun) PAIRS. A fix that got
    // the nouns right but attached them to the wrong cards is a different bug
    // and this is the arm that can see it.
    const msft = sharePropsFor(MSFT_DATA, "Big odds movement in Microsoft (MSFT)");
    const iphone = sharePropsFor(IPHONE_DATA, "Before October down 30.5 points from opening");

    expect(msft.shareTitle).toBe("Microsoft (MSFT) closes above ___ on September 4?");
    expect(msft.shareText).toContain("across 5 outcomes on");

    expect(iphone.shareTitle).toBe("When will Apple release the iPhone 18?");
    expect(iphone.shareText).toContain("across 4 windows on");
  });
});

// ── CONTROLS (green on the parent too) ────────────────────────────────────

describe("CERT-867 CONTROLS — what this repair must not move", () => {
  it("CONTROL: the date ladder still says windows, unchanged", () => {
    // The one population the original wording was true of. If this moves, the
    // repair replaced a wrong noun with a differently wrong one.
    const { shareText } = sharePropsFor(IPHONE_DATA, "Before October down 30.5 points from opening");
    expect(shareText).toBe(
      "When will Apple release the iPhone 18? — Before 2027 leads at 15% across 4 windows on Bain Luck.",
    );
  });

  it("CONTROL: a card with no ladder keeps the plain share sentence", () => {
    const { shareText } = sharePropsFor(PLAIN_DATA, "Lando Norris leads at 82%");
    expect(shareText).toBe(
      "Lando Norris is at 82% in Who wins the 2026 Formula 1 Drivers' Championship? on Bain Luck.",
    );
    expect(shareText).not.toContain("across");
  });

  it("CONTROL: the sentence still names the LEADER, not the first rung", () => {
    // CERT-859's repair. On the dollar ladder the first rung is $480 and the
    // leader is $490; on the date ladder the first rung is April and the leader
    // is Before 2027. Both would be satisfied by a top-row reading if that
    // regressed, so both are pinned.
    expect(sharePropsFor(MSFT_DATA, "x").shareText).toContain("— $490 leads at");
    expect(sharePropsFor(IPHONE_DATA, "x").shareText).toContain("— Before 2027 leads at");
  });
});

// ── THE BUILDER'S OWN CONTRACT ────────────────────────────────────────────

describe("CERT-867 — buildLadderShareText pluralises whichever noun it was given", () => {
  // Not reachable from the card: the heatmap branch is gated on two or more
  // rungs, so a one-rung ladder never renders. Asserted anyway because the
  // export is the contract, and stated as unreachable so nobody reads a green
  // here as evidence about a screen.
  it("singular, both kinds", () => {
    expect(buildLadderShareText("Q", "Before 2027", 0.5, 1, "date")).toContain("across 1 window on");
    expect(buildLadderShareText("Q", "$490", 0.5, 1, "threshold")).toContain("across 1 outcome on");
  });

  it("plural, both kinds", () => {
    expect(buildLadderShareText("Q", "Before 2027", 0.5, 4, "date")).toContain("across 4 windows on");
    expect(buildLadderShareText("Q", "$490", 0.5, 5, "threshold")).toContain("across 5 outcomes on");
  });
});
