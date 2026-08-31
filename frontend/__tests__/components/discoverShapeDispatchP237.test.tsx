// UX-P237 — the Discover card obeys the shape field.
//
// GO-2026-08-31-B Priority 3: `frontend/lib/marketShape.ts` states the contract
// — "Every surface — Discover cards, detail pages, concept pages — keys off that
// ONE field" — and the Discover card did not. It picked its kernel from
// `discover_card.suggested_format`, which `discover_card_archetypes.py` derives
// from outcome-label regexes and a raw outcome count, never reading
// `market_type`. Two channels described the same market and they disagreed.
//
// Measured against the LIVE feed on 2026-08-31 (95 items / 61 futures cards):
// 12 cards drew a kernel that contradicts the stored shape. The four specimens
// below are that payload verbatim — `__tests__/fixtures/discoverShapeDispatchP237.json`
// was cut from `GET /api/feed?limit=100` while the defect was in production.
//
// 🔴 WHY THIS RENDERS THE CARD AND NOT THE LIB. `shapeForbidsKernel` returning
// the right boolean proves nothing if no branch consults it. The dispatch it
// has to change lives in TWO components — `DiscoverCard` routes an
// `outcome_distribution` item to ComparisonCard BEFORE FuturesCard ever sees
// it (the CERT-606 lesson: a futures item has two possible cards) — so every
// assertion here goes through `DiscoverCard`, the real entry point, and counts
// what a reader sees.
//
// 🔴 AND WHY THERE ARE SURVIVOR CASES. A veto that fires too widely would
// "fix" both defects and quietly downgrade the 43 cards that were already
// right. The last two describes are expected-SURVIVOR rows: real quantity
// markets that must keep the exact ladder they render today. They are the only
// shape of assertion that can catch a too-strong guard.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FIXTURE = require("../fixtures/discoverShapeDispatchP237.json") as Record<
  string,
  { item: Record<string, unknown>; data: FeedFuturesData }
>;

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock("@/lib/discoverInteractions", () => ({
  getDiscoverItemAnalytics: () => ({}),
  recordDiscoverInteraction: () => {},
  sendDiscoverInteraction: () => {},
}));

import DiscoverCard from "@/components/DiscoverCard";

function renderCard(id: string, override?: Partial<FeedFuturesData>): string {
  const spec = FIXTURE[id];
  const item = {
    ...spec.item,
    data: override ? { ...spec.data, ...override } : spec.data,
  } as unknown as FeedItem;
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} />);
}

/** The ladder kernel tags itself; the leaderboard does not. */
function drewLadder(html: string): boolean {
  return html.includes('data-card-format="heatmap"');
}

/**
 * The leaderboard numbers its rows. Counting the aria-label rather than a
 * visible glyph keeps this from being satisfied by an unrelated "1" on the card
 * — a digit is a string both arms can print.
 */
function rankBadgeCount(html: string): number {
  return (html.match(/aria-label="Rank \d+"/g) ?? []).length;
}

describe("quantity: a continuous question stops being ranked and cropped", () => {
  // 59164972 — "When will the S&P 500 Index be above $8,000?"
  // market_type=quantity, threshold_points=[] (no date parses as a numeric
  // threshold), distribution_outcomes=7. The empty parse dropped it to the
  // count>=4 rule, so it drew the ranked leaderboard.
  const ID = "59164972";

  test("the specimen still holds this queue's premise", () => {
    const d = FIXTURE[ID].data as FeedFuturesData & { discover_card: Record<string, unknown> };
    expect(d.market_type).toBe("quantity");
    expect(d.discover_card.suggested_format).toBe("outcome_distribution");
    expect(d.discover_card.threshold_points).toEqual([]);
    expect((d.discover_card.distribution_outcomes as unknown[]).length).toBe(7);
  });

  test("it draws the ladder, not the leaderboard", () => {
    const html = renderCard(ID);
    expect(drewLadder(html)).toBe(true);
    expect(rankBadgeCount(html)).toBe(0);
  });

  test("all seven rungs survive — the three nearest dates were being cropped", () => {
    const html = renderCard(ID);
    for (const label of [
      "Before Mar 1, 2027",
      "Before Feb 1, 2027",
      "Before Jan 1, 2027",
      "Before Dec 1, 2026",
      "Before Nov 1, 2026",
      "Before Oct 1, 2026",
      "Before Sep 1, 2026",
    ]) {
      expect(html).toContain(label);
    }
  });

  test("🔴 the nearest bucket is the one the 4-row crop used to drop", () => {
    // The regression this pins: `leaderFirstSlice(rows, 4)` kept the four
    // HIGHEST probabilities, which on a cumulative date ladder are the four
    // FURTHEST-OUT dates. Sep/Oct/Nov 2026 — the decision-relevant end — were
    // the rows removed. Asserting presence alone would pass on a 4-row render
    // that happened to include this label, so pin the count too.
    const html = renderCard(ID);
    expect(html).toContain("Before Sep 1, 2026");
    expect(html).toContain("Before Oct 1, 2026");
    expect(html).toContain("Before Nov 1, 2026");
  });

  test("rung order is preserved, not re-sorted into a claim we cannot support", () => {
    const html = renderCard(ID);
    expect(html.indexOf("Before Mar 1, 2027")).toBeLessThan(html.indexOf("Before Dec 1, 2026"));
    expect(html.indexOf("Before Dec 1, 2026")).toBeLessThan(html.indexOf("Before Sep 1, 2026"));
  });

  test("no cumulative footer claim on rungs that carry no threshold value", () => {
    // "Above 50% through X" names the last rung of an ascending NUMERIC ladder.
    // These rungs have no `value` to be ascending in, so the phrase must not
    // appear — it would be pointing at wherever the probability sort landed.
    expect(renderCard(ID)).not.toContain("Above 50% through");
  });

  test("🔴 the veto also covers the ComparisonCard route, not just FuturesCard", () => {
    // No live specimen reaches that route (this market carries 3 top_outcomes
    // and the route needs 4), so construct the reachable state faithfully: the
    // same quantity market with its distribution rows promoted to top_outcomes,
    // which is exactly what a 4-outcome quantity market serves. Without the
    // veto in DiscoverCard this renders ComparisonCard and never reaches the
    // ladder at all — the fix would sit on a path this reader does not take.
    const rows = (FIXTURE[ID].data as unknown as {
      discover_card: { distribution_outcomes: { label: string; probability: number }[] };
    }).discover_card.distribution_outcomes;
    const html = renderCard(ID, {
      top_outcomes: rows.map((r, i) => ({
        id: i + 1,
        name: r.label,
        probability: r.probability,
      })) as FeedFuturesData["top_outcomes"],
    });
    expect(html.length).toBeGreaterThan(0);
    expect(drewLadder(html)).toBe(true);
    expect(rankBadgeCount(html)).toBe(0);
  });
});

describe("field: a competition between entrants stops being drawn as a ladder", () => {
  // 59934347 — "What will be said on the next All-In Podcast? (September 4)"
  // market_type=field, but four labels ("SpaceX 3+ times", "AI 50+ times")
  // parse as numeric thresholds, so it drew a 4-rung ladder of eight unrelated
  // claims and captioned it "Above 50% through <one of them>".
  const ID = "59934347";

  test("the specimen still holds this queue's premise", () => {
    const d = FIXTURE[ID].data as FeedFuturesData & { discover_card: Record<string, unknown> };
    expect(d.market_type).toBe("field");
    expect(d.discover_card.suggested_format).toBe("threshold_heatmap");
    expect((d.discover_card.threshold_points as unknown[]).length).toBe(4);
  });

  test("it draws the leaderboard, not the ladder", () => {
    const html = renderCard(ID);
    expect(drewLadder(html)).toBe(false);
    expect(rankBadgeCount(html)).toBeGreaterThan(0);
  });

  test("the nonsense cumulative caption is gone", () => {
    // Eight independent podcast predictions have no "through" — there is no
    // ordering along which 50% can be sustained.
    expect(renderCard(ID)).not.toContain("Above 50% through");
  });

  test("the leader is present and first", () => {
    const html = renderCard(ID);
    expect(html).toContain("Hundred / Thousand / Million 10+ times");
    expect(html.indexOf("Hundred / Thousand / Million 10+ times")).toBeLessThan(
      html.indexOf("Anthropic 5+ times")
    );
  });
});

describe("SURVIVORS — a real quantity ladder is untouched", () => {
  // 57774286 — "McDonald's comparable sales growth in fiscal 2026".
  // market_type=quantity AND the parser found 8 thresholds. This is the path 11
  // of the 13 live quantity cards take. The veto must not reach it.
  test("the parsed-threshold ladder still renders as a ladder", () => {
    const html = renderCard("57774286");
    expect(drewLadder(html)).toBe(true);
    expect(rankBadgeCount(html)).toBe(0);
  });

  test("it keeps its value ordering — ascending threshold, not probability", () => {
    // 'Above 1.5%' is p=0.90 and 'Above 4%' is p=0.75, so probability order and
    // value order disagree here. Pinning value order proves the existing
    // `sortValue` path is still feeding QuantityGroup.
    const html = renderCard("57774286");
    expect(html.indexOf("Above 1.5%")).toBeLessThan(html.indexOf("Above 4%"));
    expect(html.indexOf("Above 4%")).toBeLessThan(html.indexOf("Above 5%"));
  });

  test("it keeps its cumulative footer", () => {
    // The caption is correct on a real numeric ladder and must not have been
    // suppressed globally.
    expect(renderCard("57774286")).toContain("Above 50% through");
  });

  test("🔴 a market with NO stored shape renders exactly as it did before", () => {
    // The veto reads the stored field ONLY. `resolveShape` would fall back to an
    // outcome-name heuristic, and on this market that heuristic returns `field`
    // (measured — its three outcome names are non-numeric and n>=3), which would
    // veto the ladder. So letting the heuristic vote does not merely "add
    // nothing": it changes the render of a market we have no authoritative answer
    // for, on the strength of the same kind of regex guess that produced the
    // wrong `suggested_format` in the first place.
    //
    // This is the only assertion that can observe that rule, because all four
    // real specimens DO carry a stored shape.
    const html = renderCard("59934347", { market_type: null });
    expect(drewLadder(html)).toBe(true);
  });

  // 59917975 — "Precipitation in NYC in September?" — DISJOINT bins
  // ('2-3"', '<2"', '3-4"'…), the case where ordering by probability would be
  // flat-out wrong. It parses as thresholds, so it never reaches the
  // distribution-fed path. This row is why that path is scoped to an empty parse.
  test("disjoint bins keep their parsed ordering", () => {
    const html = renderCard("59917975");
    expect(drewLadder(html)).toBe(true);
    expect(html.indexOf('2-3&quot;')).toBeLessThan(html.indexOf('3-4&quot;'));
    expect(html.indexOf('3-4&quot;')).toBeLessThan(html.indexOf('5-6&quot;'));
  });
});
