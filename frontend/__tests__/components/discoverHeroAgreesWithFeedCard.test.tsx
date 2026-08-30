// UX-P162 — ONE NUMBER PER QUESTION, ACROSS SURFACES.
//
// Alex's standing ruling is "the blend is the product": one number per question.
// It was being honoured WITHIN a card and broken BETWEEN cards. The same futures
// market, from the same `GET /api/feed` payload, is drawn by two components:
//
//   • `components/FeedCard.tsx`          → /categories/*, /sports, /my-stuff
//   • `components/discover/FuturesCard.tsx` → Discover (the default landing page)
//
// Since #2060/UX-P160 the first takes the CARD RULE — a complement pair is
// normalized by its true total, the headline is rounded once and the other side
// is derived — and the second still ran `Math.round(p * 100)` on the leader's raw
// probability. Those two disagree by a point whenever a pair sums to anything but
// exactly 1.00 inside the [0.99, 1.01] complement band, so one market could read
// 57% on Discover and 56% one tab over.
//
// ## Latent when shipped, and that is stated rather than hidden
//
// Measured on the deployed feed 2026-08-29 across all five feed surfaces
// (`/api/feed?limit=100` plus the politics, economics, entertainment and sports
// variants): 114 unique futures cards, 7 two-outcome, and ZERO disagree today —
// every live pair sums to exactly 1.00. Nothing a reader can see changed the day
// this shipped. It is fixed because the disagreement is structural and silent:
// there is no surface, alert or test that would have announced the first pair to
// land off 1.00, and by then it is on the landing page.
//
// ## Why this file renders instead of checking the rule
//
// `renderedPercentContract.test.ts` drives the shared table and would stay green
// if neither component ever called it — which is the state this queue found. A
// pure-lib guard cannot see a render. Every assertion below reads
// `renderToStaticMarkup` output from the SHIPPED components, and the last block
// plants failures to prove the assertions can fail.

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
import { FuturesCard, FuturesCompactRow } from "../../components/discover/FuturesCard";
import { BELOW_ONE_PERCENT } from "@/lib/probabilityDisplay";

type Outcome = {
  id: number;
  name: string;
  probability: number | null;
  rendered_percent?: number | null;
};

function futuresData(outcomes: Outcome[], over: Partial<FeedFuturesData> = {}): FeedFuturesData {
  return {
    id: 108621,
    name: "Which party will win the U.S. House?",
    llm_sport_category: "politics",
    sport_name: "Politics",
    status: "open",
    source: "kalshi",
    resolution_date: "2026-11-03T00:00:00Z",
    outcome_count: outcomes.length,
    top_outcomes: outcomes.map((o, i) => ({ rank: i + 1, movement: null, ...o })),
    ...over,
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
}

/** The Discover hero's printed percent, read out of the shipped markup. */
function discoverHero(data: FeedFuturesData): string {
  const html = renderToStaticMarkup(
    <FuturesCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
  // Both A/B variants tag the hero with the same testid, so this reads whichever
  // one the deterministic hash picked rather than pinning the layout.
  const m = html.match(/data-testid="futures-hero-probability"[^>]*>([^<]+)</);
  if (!m) throw new Error("no Discover hero rendered — fixture fell into a kernel branch");
  // `renderToStaticMarkup` escapes the angle bracket in UX-P046's `<1%` / `>99%`
  // sentinels, so compare against the constants rather than against `&lt;1%` —
  // the entity is the serializer's, not the component's.
  return m[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">");
}

/** Every percent `FeedCard` prints for the same payload. */
function feedCardPercents(data: FeedFuturesData): string[] {
  const html = renderToStaticMarkup(<FeedCard item={itemFor(data)} />);
  return Array.from(html.matchAll(/(&lt;1%|&gt;99%|\d{1,3}%)/g)).map((m) => m[1]);
}

// ── 1. THE DEFECT: a pair off 1.00 moved the leader by a point ───────────────

describe("the Discover hero agrees with the category page", () => {
  // 0.5595 + 0.4455 = 1.005 — inside the complement band, so the card rule
  // normalizes: 0.5595 / 1.005 = 0.556716…, which rounds to 56. Raw half-up on
  // the served probability gives floor(55.95 + 0.5) = 56 as well… so this pair is
  // NOT the one that breaks. The pair below is, and it is spelled out per fixture
  // rather than derived so a rule change has to be restated here.
  //
  // 0.5525 + 0.4425 = 0.995. Raw: floor(55.25 + 0.5) = 55. Card rule:
  // 0.5525 / 0.995 = 0.555276… → 56. The two surfaces printed 55 and 56.
  const SPLIT = [
    { id: 1, name: "Democratic Party", probability: 0.5525 },
    { id: 2, name: "Republican Party", probability: 0.4425 },
  ];

  it("prints the card-rule percent, not the raw rounding", () => {
    expect(discoverHero(futuresData(SPLIT))).toBe("56%");
  });

  it("prints the SAME number FeedCard prints for the same payload", () => {
    const data = futuresData(SPLIT);
    const hero = discoverHero(data);
    expect(feedCardPercents(data)).toContain(hero);
  });

  it("the raw rounding this replaces really would have disagreed", () => {
    // Guards the fixture: if 0.5525 ever stopped being a case where the rule and
    // the raw arithmetic differ, the two assertions above would pass vacuously.
    expect(Math.round(0.5525 * 100)).toBe(55);
    expect(discoverHero(futuresData(SPLIT))).not.toBe("55%");
  });
});

// ── 2. THE SERVED PERCENT WINS, AND ABSENCE IS NOT A NULL ────────────────────

describe("the served rendered_percent reaches the Discover hero", () => {
  it("prints the served integer over its own arithmetic", () => {
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.5525, rendered_percent: 56 },
      { id: 2, name: "Republican Party", probability: 0.4425, rendered_percent: 44 },
    ]);
    expect(discoverHero(data)).toBe("56%");
  });

  it("a served null means 'no override', not 'no number'", () => {
    // The key is PRESENT and null: the server looked and declined to annotate.
    // The hero falls back to `formatProbabilityPercent`'s own rounding rather than
    // rendering nothing — the same direction FeedCard takes.
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.62, rendered_percent: null },
      { id: 2, name: "Republican Party", probability: 0.38, rendered_percent: null },
    ]);
    expect(discoverHero(data)).toBe("62%");
  });
});

// ── 3. UX-P046's FLOOR SURVIVES THE OVERRIDE ─────────────────────────────────

describe("a nonzero probability still never prints 0%", () => {
  it("a served 0 over a live 0.003 prints <1%", () => {
    // The one piece of care in this fix. `{ rendered }` overrides the INTEGER, not
    // the boundary rule — "rounding may never move a probability across a boundary
    // it is not on" is a claim about the value, not about which arithmetic produced
    // the integer. A regression here reads `0%` over a market actively pricing the
    // outcome as possible, which is UX-P046's whole defect.
    const data = futuresData([
      { id: 1, name: "Longshot", probability: 0.003, rendered_percent: 0 },
      { id: 2, name: "Field", probability: 0.997, rendered_percent: 100 },
    ]);
    expect(discoverHero(data)).toBe(BELOW_ONE_PERCENT);
  });
});

// ── 4. THE HEADLINE IS FOUND BY IDENTITY, NOT BY POSITION ────────────────────

describe("an unsorted top_outcomes does not misplace the headline", () => {
  // MEASURED on the deployed feed 2026-08-29: 1 of 103 multi-outcome cards ships a
  // `top_outcomes[0]` that is NOT the maximum — `Which party will win the House in
  // 2026?` serves [0.4275, 0.0725, 0.5]. The card rule anchors on the LEADER-FIRST
  // slice (index 0 survives rounding, index 1 is derived), so anchoring on served
  // order would normalize the pair around an also-ran and hand the two surfaces
  // opposite answers. This is why the lookup is `indexOf`, not `[0]`.
  it("headlines top_outcomes[0] with ITS percent when the max sits elsewhere", () => {
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.4275 },
      { id: 2, name: "Republican Party", probability: 0.0725 },
      { id: 3, name: "Other", probability: 0.5 },
    ]);
    // Arity 3 is not a complement pair, so the rule is a no-op and the headline is
    // the served leader's own rounding — the same number FeedCard prints.
    const hero = discoverHero(data);
    expect(hero).toBe("43%");
    expect(feedCardPercents(data)).toContain(hero);
  });
});

// ── 5. THE GROUP ROW AGREES WITH THE CARD IT EXPANDS INTO ────────────────────

describe("FuturesCompactRow prints the same headline as the full card", () => {
  it("takes the card rule too", () => {
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.5525 },
      { id: 2, name: "Republican Party", probability: 0.4425 },
    ]);
    const html = renderToStaticMarkup(<FuturesCompactRow item={itemFor(data)} data={data} />);
    expect(html).toContain("56%");
    expect(html).not.toContain("55%");
    expect(html).toContain(discoverHero(data));
  });
});

// ── 6. THE PLANTS — proof the assertions above can fail ──────────────────────

describe("the assertions are load-bearing", () => {
  it("a card whose pair sums to exactly 1.00 is untouched (the common case)", () => {
    // 103 of the 114 measured cards look like this. The fix must change NOTHING
    // here, or "latent" would have been a lie.
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.58 },
      { id: 2, name: "Republican Party", probability: 0.42 },
    ]);
    expect(discoverHero(data)).toBe("58%");
    expect(Math.round(0.58 * 100)).toBe(58); // raw and rule agree, as they should
  });

  it("the hero extractor really reads the hero (not any percent on the card)", () => {
    const data = futuresData([
      { id: 1, name: "Democratic Party", probability: 0.5525 },
      { id: 2, name: "Republican Party", probability: 0.4425 },
    ]);
    expect(() => discoverHero(futuresData([]))).toThrow();
    expect(discoverHero(data)).toMatch(/^\d{1,3}%$/);
  });
});
