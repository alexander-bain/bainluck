// UX-P265 (#2645) — THE CARD COUNTS IN THE SINGULAR.
//
// What the shopper saw, `/sports` -> Top Markets, 1280w production, 2026-09-01
// ~23:44 PT: the third card of the first row printed TWO unconditional plurals
// on one card — a `1 sources` badge top-right, and a `+1 more outcomes` footer.
// The card beside it printed `2 sources`, correctly, which is why the string had
// never been noticed: it is only wrong when the count happens to be one.
//
// ── WHY THE `sources` HALF IS A MISSING GUARD, NOT A MISSING PLURAL ──────────
//
// Every other futures card in the tree already refuses to render a single-source
// badge, and one of them writes the reason down (`FuturesCard.tsx:205`):
//
//     "A single source renders nothing — users see one clean number, not 'Kalshi'."
//
// `RelatedFutures`' `MultiSourceBadge` returns null at <= 1, `TotalPointsSpectrum`'s
// `SourceBadge` returns null at <= 1, `SourceAggregationBlock` returns null below 2,
// and `FeedCard` gates on `source_count > 1`. `CombinedFeedCard` was the ONLY one
// missing the guard. So "1 source" would have been a third behaviour, inconsistent
// with all four siblings, and it would advertise single-sourcing — which the
// blend-is-the-product ruling says we do not do. The fix is the guard the siblings
// have; the plural is kept for the 2+ string so it cannot regress if the guard is
// ever loosened.
//
// ── THE SUBSTRING TRAP THIS FILE HAS TO DODGE ────────────────────────────────
//
// `expect(html).toContain("+1 more outcome")` is VACUOUS: the broken render says
// "+1 more outcomes", which contains "+1 more outcome" as a prefix. So every
// singular claim here is made as a NEGATIVE against the plural form, or against
// the exact closing tag. Asserting the presence of the singular alone would be
// green on both arms.
//
// Everything is read off the RENDERED MARKUP rather than off `plural()`, because a
// helper-only test stays green if a call site never calls it — the state that
// shipped.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import type { GroupedMarket } from "@/lib/feedSections";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: React.ReactNode;
    [k: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import CombinedFeedCard from "../../components/CombinedFeedCard";
import CombinedMarketCard from "../../components/CombinedMarketCard";
import { plural, countOf } from "@/lib/plural";

// ── Fixtures ────────────────────────────────────────────────────────────────
// Shaped like the payload `/api/feed` serves: `data.source` is what the card
// counts, `data.top_outcomes` is what it merges.

function outcomes(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: 1000 + i,
    rank: i + 1,
    name: `Player ${String.fromCharCode(65 + i)}`,
    probability: 0.5 - i * 0.05,
    rendered_percent: 50 - i * 5,
    movement: null,
  }));
}

function item(source: string, outcomeCount: number, id = 114160): FeedItem {
  return {
    type: "futures",
    score: 71,
    reason: null,
    headline: null,
    data: {
      id,
      name: "2026 Women's US Open Winner (Tennis)",
      llm_sport_category: "tennis",
      source,
      source_count: 1,
      status: "open",
      resolution_date: "2026-09-13T00:00:00+00:00",
      outcome_count: outcomeCount,
      card_sum_reason: null,
      canonical_market_key: "tennis::championship:2026",
      top_outcomes: outcomes(outcomeCount),
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

function group(items: FeedItem[]): GroupedMarket {
  return { canonicalKey: "tennis::championship:2026", items, bestScore: 71 };
}

const render = (g: GroupedMarket) =>
  renderToStaticMarkup(<CombinedFeedCard group={g} />);

// ── The defect, exactly as shot ─────────────────────────────────────────────

describe("#2645 — the card the shopper photographed", () => {
  // One source, six outcomes: five displayed, one over. Both broken strings on
  // one render, which is how the shopper met them.
  const html = render(group([item("polymarket", 6)]));

  it("does not print the shopper's `1 sources`", () => {
    expect(html).not.toContain("1 sources");
  });

  it("prints no source badge at all for a single source, like every sibling card", () => {
    // Negative on BOTH forms: the guard means neither string is reachable, so a
    // fix that merely pluralised to "1 source" would fail here on purpose.
    expect(html).not.toContain("1 sources");
    expect(html).not.toContain("1 source<");
    expect(html).not.toContain(">1 source");
  });

  it("does not print the shopper's `+1 more outcomes`", () => {
    // The discriminating assertion. Its positive twin would be vacuous.
    expect(html).not.toContain("+1 more outcomes");
  });

  it("prints the singular `+1 more outcome` in the footer", () => {
    // Safe only because the plural is excluded above; anchored on the closing
    // tag so the plural cannot satisfy it either.
    expect(html).toContain("+1 more outcome<");
  });

  it("omits the count from the aria-label rather than saying `1 sources`", () => {
    expect(html).toContain('aria-label="2026 Women&#x27;s US Open Winner (Tennis)"');
    expect(html).not.toContain("- 1 sources");
  });
});

// ── Controls: green on BOTH arms, and they must stay green ──────────────────

describe("#2645 controls — correct today, must not move", () => {
  it("CONTROL (green on main too): two sources still print `2 sources`", () => {
    const html = render(group([item("polymarket", 6), item("kalshi", 6, 114161)]));
    expect(html).toContain("2 sources");
    expect(html).not.toContain("2 source<");
  });

  it("CONTROL (green on main too): two sources keep the count in the aria-label", () => {
    const html = render(group([item("polymarket", 6), item("kalshi", 6, 114161)]));
    expect(html).toContain("- 2 sources");
  });

  it("CONTROL (green on main too): an overflow of three still reads `+3 more outcomes`", () => {
    const html = render(group([item("polymarket", 8)]));
    expect(html).toContain("+3 more outcomes");
  });

  it("CONTROL (green on main too): exactly five outcomes renders no footer at all", () => {
    const html = render(group([item("polymarket", 5)]));
    expect(html).not.toContain("more outcome");
  });
});

// ── The sibling card carrying the same footer string ────────────────────────

describe("#2645 — CombinedMarketCard's footer, the same string in a second place", () => {
  // maxOutcomes defaults to 8, so nine outcomes leaves exactly one over. Fixing
  // only CombinedFeedCard would leave this one printing the shopper's string on
  // a different surface — the one-seam-fixed trap.
  const markets = [
    {
      id: 1,
      name: "2026 Women's US Open Winner (Tennis)",
      source: "polymarket",
      outcomes: outcomes(9).map((o) => ({
        id: o.id,
        name: o.name,
        probability: o.probability,
      })),
    },
  ];

  const html = renderToStaticMarkup(
    <CombinedMarketCard
      title="2026 Women's US Open Winner (Tennis)"
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      markets={markets as any}
    />,
  );

  it("does not print `+1 more outcomes`", () => {
    expect(html).not.toContain("+1 more outcomes");
  });

  it("prints the singular `+1 more outcome`", () => {
    expect(html).toContain("+1 more outcome<");
  });
});

// ── The helper itself, including the counter-case ───────────────────────────

describe("#2645 — plural()/countOf()", () => {
  it("picks the singular at exactly one and the plural everywhere else", () => {
    expect(plural(1, "source", "sources")).toBe("source");
    expect(plural(2, "source", "sources")).toBe("sources");
    expect(plural(0, "source", "sources")).toBe("sources");
    expect(plural(-1, "source", "sources")).toBe("sources");
  });

  it("countOf attaches the number", () => {
    expect(countOf(1, "more outcome", "more outcomes")).toBe("1 more outcome");
    expect(countOf(4, "more outcome", "more outcomes")).toBe("4 more outcomes");
  });

  it("COUNTER-CASE: countOf is not a no-op that returns its plural form", () => {
    // Deleting the branch and always returning `many` would satisfy every
    // plural-side assertion above. This is the arm that would catch it.
    expect(countOf(1, "more outcome", "more outcomes")).not.toBe("1 more outcomes");
  });
});
