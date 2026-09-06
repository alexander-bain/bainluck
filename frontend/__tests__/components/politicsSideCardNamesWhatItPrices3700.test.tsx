import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SideMarketCard } from "../../components/politics/SideMarketCard";
import type { PoliticsMarketRow } from "../../lib/api";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

// #3700 — a side card must name the outcome the number beside it belongs to.
//
// The card used to derive its label from a threshold —
// `isBinary ? (market.prob >= 50 ? "Yes" : "No") : leader.name` — and then
// print `market.prob` unchanged, never taking the complement. So the label
// always claimed the majority side while the number could be the minority one,
// and every sub-50% binary on `/politics` was inverted:
//
//     Trump goes to space in 2026?
//     No                                    2%
//
// which tells a reader there is a 98% chance he does. The market said 2% Yes.
//
// The rows below are the real production payload from `GET /api/politics`
// on 2026-09-06, copied verbatim, including the two that were rendering wrong.

function row(overrides: Partial<PoliticsMarketRow> = {}): PoliticsMarketRow {
  return {
    q: "Trump goes to space in 2026?",
    prob: 2.1,
    src: "polymarket",
    market_id: 16625133,
    top_outcomes: [{ name: "Yes", prob: 2.1 }],
    outcome_count: 1,
    ...overrides,
  };
}

const label = (m: PoliticsMarketRow) => renderToStaticMarkup(<SideMarketCard market={m} />);

describe("#3700 — a /politics side card names the outcome it prices", () => {
  it("does not print 'No' next to a Yes probability", () => {
    const html = label(row());

    expect(html).toContain("Yes");
    expect(html).toContain("2%");
    // The whole bug in one assertion.
    expect(html).not.toContain(">No<");
  });

  it("keeps a single-outcome ladder rung's own name instead of calling it 'No'", () => {
    // `outcome_count: 1` used to satisfy `outcome_count <= 2` and be treated as
    // a Yes/No binary, throwing away the only informative label on the card.
    const html = label(
      row({
        q: "Trump eliminates capital gains tax on crypto by ___?",
        top_outcomes: [{ name: "December 31, 2026", prob: 2.1 }],
        market_id: 16625140,
      }),
    );

    expect(html).toContain("December 31, 2026");
    expect(html).not.toContain(">No<");
  });

  it("is unchanged for a market already above 50%", () => {
    const html = label(
      row({
        q: "How many Senate Democrats will lose their primary in 2026?",
        prob: 98.0,
        src: "kalshi",
        top_outcomes: [
          { name: "Will exactly 0 Senate Democratic members lose their primary in 2026?", prob: 98.0 },
          { name: "Will exactly 1 Senate Democratic members lose their primary in 2026?", prob: 0.9 },
        ],
        outcome_count: 5,
      }),
    );

    expect(html).toContain("Will exactly 0 Senate Democratic members");
    expect(html).toContain("98%");
  });

  it("still prints a real 'No' when No is genuinely the leading outcome", () => {
    // The fix must not make "No" unprintable — only unearned. Here the payload
    // itself says the leader is No, so the card should say No, at No's price.
    const html = label(
      row({
        q: "Will the government shut down in 2026?",
        prob: 71,
        top_outcomes: [
          { name: "No", prob: 71 },
          { name: "Yes", prob: 29 },
        ],
        outcome_count: 2,
      }),
    );

    expect(html).toContain("No");
    expect(html).toContain("71%");
  });

  it("falls back to a dash rather than inventing a side when there are no outcomes", () => {
    const html = label(row({ top_outcomes: [], outcome_count: 0 }));

    expect(html).toContain("—");
    expect(html).not.toContain(">No<");
    expect(html).not.toContain(">Yes<");
  });
});
