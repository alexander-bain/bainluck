/**
 * #8788: an at-least ladder marks the rung its caption names, not its tallest bar.
 *
 * Production, 390px, 2026-09-26 03:55Z. Discover card "Tennessee gas prices
 * tomorrow" (futures 62419329): every rung is "Above <price>", so each one
 * contains the next and the tallest bar is the loosest question. The card
 * highlighted "Above 3.9850 — 91%" and captioned "More likely than not: Above
 * 4.0100": two rows called out for one answer. #8647 fixed exactly this for
 * date ladders; this is the same axis turned round.
 *
 * NOT changed, pinned below as controls: where no rung clears even, the highest
 * rung stays marked on every ladder. That is Alex's UX-1052 design ("outcomes
 * as ordered bars … with the leader marked", 2026-09-03), and the aliens card
 * ("Before Jan 20, 2029 — 19%") that opened this issue is that shape.
 *
 * Rungs below are the served `threshold_points`, verbatim, from that feed read.
 */
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { FuturesCard } from "../../components/discover/FuturesCard";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

type Point = { label: string; probability: number; value: number; source: string; direction: string };

function render(points: Point[], name: string): string {
  const data = {
    id: 8788,
    name,
    llm_sport_category: "tech",
    sport_name: "Tech",
    resolution_date: "2027-01-01T15:00:00Z",
    top_outcomes: [...points]
      .sort((a, b) => b.probability - a.probability)
      .slice(0, 3)
      .map((p, i) => ({ id: i + 1, name: p.label, probability: p.probability, movement: null })),
    outcome_count: points.length,
    volume_24h: 500_000,
    confidence_tier: "low",
    discover_card: { suggested_format: "threshold_heatmap", threshold_points: points },
  } as unknown as FeedFuturesData;
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/** Rungs drawn on the tinted inset row, which is how QuantityGroup marks the highlighted rung. */
function highlightedRungs(html: string): string[] {
  return Array.from(
    html.matchAll(/<div class="[^"]*bg-accent-brand\/\[0\.06\][^"]*" aria-label="([^"]*): [^"]*"/g),
    (m) => m[1],
  );
}

function caption(html: string): string | null {
  const m = html.match(
    /<span class="[^"]*text-text-secondary[^"]*">More likely than not:<\/span><span class="[^"]*text-accent-brand[^"]*">([^<]*)<\/span>/,
  );
  return m ? m[1] : null;
}

const date = (label: string, value: number, probability: number): Point => ({
  label, value, probability, source: "date_bucket", direction: "before",
});
const rung = (label: string, value: number, probability: number): Point => ({
  label, value, probability, source: "outcome", direction: "exact",
});

const aliens: Point[] = [
  date("Before October", 20261000, 0.01),
  date("Before November", 20261100, 0.015),
  date("Before December", 20261200, 0.025),
  date("Before 2027", 20270100, 0.0455),
  date("Before 2028", 20280100, 0.125),
  date("Before Jan 20, 2029", 20290120, 0.185),
];

const earthquake: Point[] = [
  rung("6.8+", 6.8, 0.47),
  rung("7.0+", 7.0, 0.375),
  rung("7.1+", 7.1, 0.255),
  rung("7.2+", 7.2, 0.165),
  rung("7.4+", 7.4, 0.135),
  rung("7.5+", 7.5, 0.08),
];

const gas: Point[] = [
  rung("Above 3.9700", 3.97, 0.885),
  rung("Above 3.9750", 3.975, 0.885),
  rung("Above 3.9800", 3.98, 0.885),
  rung("Above 3.9850", 3.985, 0.905),
  rung("Above 3.9950", 3.995, 0.885),
  rung("Above 4.0000", 4.0, 0.885),
  rung("Above 4.0050", 4.005, 0.885),
  rung("Above 4.0100", 4.01, 0.885),
];

describe("#8788 an at-least ladder over even marks the caption's rung", () => {
  test("Tennessee gas (served): the mark leaves the tallest bar for the rung the caption names", () => {
    const html = render(gas, "Tennessee gas prices tomorrow");
    expect(caption(html)).toBe("Above 4.0100");
    expect(highlightedRungs(html)).toEqual(["Above 4.0100"]);
  });

  test("a '+' ladder that clears even marks its most specific rung over even", () => {
    const html = render(
      [rung("6.5+", 6.5, 0.9), rung("6.8+", 6.8, 0.62), rung("7.0+", 7.0, 0.375), rung("7.2+", 7.2, 0.165)],
      "How strong of an earthquake will occur worldwide before Oct 1, 2026?",
    );
    expect(caption(html)).toBe("6.8+");
    expect(highlightedRungs(html)).toEqual(["6.8+"]);
  });

  test("'Over' / 'At least' / 'or more' wording reads the same", () => {
    const html = render(
      [rung("At least 10", 10, 0.8), rung("At least 20", 20, 0.55), rung("30 or more", 30, 0.2)],
      "How many?",
    );
    expect(caption(html)).toBe("At least 20");
    expect(highlightedRungs(html)).toEqual(["At least 20"]);
  });
});

describe("#8788 CONTROLS: what this fix must not move", () => {
  test("UX-1052: a deadline ladder with no rung over even keeps its highest rung marked (aliens, served)", () => {
    const html = render(aliens, "Will the U.S. confirm that aliens exist?");
    expect(caption(html)).toBeNull();
    expect(highlightedRungs(html)).toEqual(["Before Jan 20, 2029"]);
  });

  test("UX-1052: an at-least ladder with no rung over even keeps its highest rung marked (earthquake, served)", () => {
    const html = render(earthquake, "How strong of an earthquake will occur worldwide before Oct 1, 2026?");
    expect(caption(html)).toBeNull();
    expect(highlightedRungs(html)).toEqual(["6.8+"]);
  });

  test("exclusive price buckets mark their highest rung (Meta close, served)", () => {
    const html = render(
      [rung("$750", 750, 0.38), rung("$760", 760, 0.205), rung("$770", 770, 0.11), rung("$780", 780, 0.06)],
      "How high will Meta (META) close on September 28?",
    );
    expect(highlightedRungs(html)).toEqual(["$750"]);
  });

  test("range buckets with an open-ended '+' rung are not an at-least ladder (box office, served)", () => {
    const html = render(
      [
        rung("<14m", 14_000_000, 0.01),
        rung("14-17m", 14_000_000, 0.09),
        rung("17-20m", 17_000_000, 0.345),
        rung("20-23m", 20_000_000, 0.385),
        rung("23-26m", 23_000_000, 0.062),
        rung("26m+", 26_000_000, 0.019),
      ],
      '"Heart of the Beast" Opening Weekend Box Office',
    );
    expect(highlightedRungs(html)).toEqual(["20-23m"]);
  });

  test("a two-sided pair (Below 15% / At least 15%) is not an at-least ladder", () => {
    const html = render(
      [rung("Below 15%", 15, 0.62), rung("At least 15%", 15.01, 0.38)],
      "MacAskill–Moll AI growth challenge · Who will win?",
    );
    expect(highlightedRungs(html)).toEqual(["Below 15%"]);
  });

  test("an 'or below' ladder keeps today's mark (its caption is a separate question)", () => {
    // Deliberately incoherent (#4751 serves such boards): the tallest bar and the
    // last rung over even are different rows, so this control is the one that
    // fails if the at-least test is widened to every non-date ladder.
    const html = render(
      [rung("5.05% or below", 5.05, 0.55), rung("5.09% or below", 5.09, 0.9), rung("5.16% or below", 5.16, 0.7)],
      "How low will the 30Y US Treasury yield get by Sep 30, 2026?",
    );
    expect(caption(html)).toBe("5.16% or below");
    expect(highlightedRungs(html)).toEqual(["5.09% or below"]);
  });
});
