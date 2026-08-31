// UX-P238 — the hero number answers the question the card asks.
//
// A futures card headlines ONE number. Every surface picked it as
// `top_outcomes[0]`, the probability leader, which on a market whose answer is
// "probably not" is the **No** side. Discover's variant-B hero prints that
// number as a bare 4xl percent with NO outcome label under the title, so
// `Will "Onslaught" score at least 80 on the Tomatometer?` headlined **88%**
// when the answer was **12%**.
//
// 🔴 THE FIXTURE IS THE LIVE PAYLOAD, VERBATIM. `heroAnswersQuestionP238.json`
// was cut from `GET /api/feed?limit=100` on 2026-08-31 while the defect was in
// production — all 7 of the feed's two-outcome futures cards, which is the
// entire population the rule can reach. 2 of the 7 were inverted.
//
// 🔴 WHY EVERY ASSERTION GOES THROUGH A RENDERED COMPONENT. `heroOutcome`
// returning the right object proves nothing if no surface consults it, and
// THREE do — `FuturesCard` (Discover), `FuturesCompactRow` (group and
// theme-bundle rows) and `FeedCard` (`/categories/*`, `/sports`, `/my-stuff`).
// A lib-only test would have passed with two of the three call sites untouched.
//
// 🔴 WHY THE HERO IS READ OUT OF ITS OWN ELEMENT AND NOT OUT OF THE PAGE TEXT.
// "88%" still appears on the fixed Onslaught card — the served hook sentence
// says `No: "Onslaught" ... leads at 88%`. An assertion that the string 88% is
// absent would fail on the CORRECT render, and one that 12% is present passes
// on a card that prints both. Both numbers live in the same document, so the
// only assertion that means anything is the exact content of the element the
// hero renders into.
//
// 🔴 AND WHY FIVE OF THE SEVEN ARE SURVIVOR ROWS. A negation test that fired
// too widely would "fix" these two and silently re-headline the other five —
// including `Texas State House winner?`, whose sides are `Democratic party` /
// `Republican party`, and the Fed's real `No change` row, which a bare
// `/^no\b/` matches. The survivors are the only shape of assertion that can
// catch a too-eager predicate.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { heroOutcome, negates } from "@/lib/discover/heroOutcome";
import { suppressBareZeroFuturesCard } from "@/components/discover/utils";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FIXTURE = require("../fixtures/heroAnswersQuestionP238.json") as Record<
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

// `FeedCard` reads the analytics context and THROWS outside its provider, so
// rendering it standalone needs this. Same lesson as CERT-606's `pinFor`: a leaf
// that reaches for app-level context cannot be rendered by itself without one.
jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import DiscoverCard from "@/components/DiscoverCard";
import FeedCard from "@/components/FeedCard";
import { FuturesCompactRow } from "@/components/discover/FuturesCard";

const HERO_TESTID = "futures-hero-probability";

function feedItem(id: string, override?: Partial<FeedFuturesData>): FeedItem {
  const spec = FIXTURE[id];
  if (!spec) throw new Error(`fixture ${id} missing`);
  return {
    ...spec.item,
    data: override ? { ...spec.data, ...override } : spec.data,
  } as unknown as FeedItem;
}

function renderDiscover(id: string, override?: Partial<FeedFuturesData>): string {
  return renderToStaticMarkup(
    // `DiscoverCard` is a DEFAULT export and takes a grouped item, never a bare
    // `item` — a named import or the wrong prop yields "Element type is invalid".
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    React.createElement(DiscoverCard as any, {
      groupedItem: { type: "single", item: feedItem(id, override) },
    }),
  );
}

/**
 * The exact text the hero element renders, or null when the card draws no hero
 * at all. Returning null rather than "" is what stops a card that lost its hero
 * from reading as a card that prints something unexpected.
 */
function heroText(html: string): string | null {
  const m = new RegExp(`data-testid="${HERO_TESTID}"[^>]*>([^<]*)<`).exec(html);
  return m ? m[1].trim() : null;
}

/** The compact row's percent element — it carries no testid of its own. */
function compactPercent(html: string): string | null {
  const m = /<span class="font-mono tabular-nums text-sm font-bold">([^<]*)</.exec(html);
  return m ? m[1].trim() : null;
}

/**
 * FeedCard's headline block: the percent and the outcome name printed under it.
 *
 * Scoped, because FeedCard also prints the FULL outcome list beneath the
 * headline — correctly, and including the No side at 73%. A whole-document
 * check therefore says nothing about which side won the headline, which is the
 * only thing this ship changes.
 */
function feedHeadline(html: string): { percent: string | null; label: string | null } {
  const pct = /<div class="font-mono text-sm font-bold text-text-primary">([^<]*)</.exec(html);
  const anchor = 'max-w-[100px]">';
  const at = html.indexOf(anchor);
  const label =
    at < 0
      ? null
      : html
          .slice(at + anchor.length, at + anchor.length + 400)
          .split("</div>")
          .slice(0, 2)
          .join(" ")
          .replace(new RegExp("<[^>]*>", "g"), " ")
          .replace(/\s+/g, " ")
          .trim();
  return { percent: pct ? pct[1].trim() : null, label };
}

// ── The defect: the hero was the negation of its own question ───────────────

describe("the Discover hero prints the probability of the question as asked", () => {
  it('answers `Will "Onslaught" score at least 80?` with 12%, not the No side 88%', () => {
    const hero = heroText(renderDiscover("59934328"));
    // Not `toContain`: 88 is legitimately elsewhere in this document (the served
    // hook sentence quotes it), so only the hero's own content decides.
    expect(hero).toBe("12%");
  });

  it("answers `Will Neuralink's valuation hit $47.5B?` with 27%, not the No side 73%", () => {
    const hero = heroText(renderDiscover("57792416"));
    expect(hero).toBe("27%");
  });

  it("draws the hero's progress bar at the affirmative width, not the negation's", () => {
    // The bar is `width: ${Math.round(prob * 100)}%`, taken off the same `prob`.
    // If only the printed percent were re-pointed and the bar left on the served
    // leader, the card would print 12% above a bar filled almost to the end.
    const html = renderDiscover("59934328");
    expect(html).toContain("width:12%");
    expect(html).not.toContain("width:88%");
  });
});

// ── The same decision on the surfaces that are not Discover ─────────────────

describe("every surface that headlines this market takes the same side", () => {
  it("FeedCard (/categories, /sports, /my-stuff) headlines the affirmative", () => {
    const html = renderToStaticMarkup(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      React.createElement(FeedCard as any, { item: feedItem("57792416") }),
    );
    // FeedCard prints the outcome NAME directly beneath its headline percent,
    // so the label is the unambiguous witness for which side won the headline.
    const headline = feedHeadline(html);
    expect(headline.percent).toBe("27%");
    // The label block also carries the entity-image placeholder's initials, so
    // it is anchored at the END rather than compared whole — and the negation is
    // excluded WITHIN this block, which is what the outcome list below may not
    // be held to.
    expect(headline.label).toMatch(/(?:^|\s)Neuralink&#x27;s valuation$/);
    expect(headline.label).not.toContain("Not Neuralink");
  });

  it("FuturesCompactRow (group + theme-bundle rows) headlines the affirmative", () => {
    // This row prints a percent beside the market name with no outcome label at
    // all, so an inverted number here is less recoverable than on the full card.
    const html = renderToStaticMarkup(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      React.createElement(FuturesCompactRow as any, {
        item: feedItem("59934328"),
        data: FIXTURE["59934328"].data,
      }),
    );
    // Scoped to the percent element for the same reason the Discover hero is:
    // the served hook snippet on this row quotes `leads at 88%`, and the
    // movement badge beside it prints `47%`, so a whole-document containment
    // check answers about neither the right string nor the right element.
    expect(compactPercent(html)).toBe("12%");
  });
});

// ── The guard that had to move with the hero ────────────────────────────────

describe("the bare-sub-1% suppression follows the number the hero prints", () => {
  // Constructed, not live: no negation pair in the 2026-08-31 feed has a sub-1%
  // affirmative. It is reachable by construction — a `binary_probability` claim
  // whose answer is "almost certainly not" — and it is exactly the print that
  // `suppressBareZeroFuturesCard` exists to stop.
  const nearZeroAffirmative = {
    ...FIXTURE["108621"].data,
    discover_card: { suggested_format: "binary_probability" },
    top_outcomes: [
      { name: "No: the claim", probability: 0.996, movement: null },
      { name: "the claim", probability: 0.004, movement: null },
    ],
  } as unknown as FeedFuturesData;

  it("suppresses a card whose affirmative hero would print under 1%", () => {
    const item = { ...FIXTURE["108621"].item, data: nearZeroAffirmative } as unknown as FeedItem;
    // Reading `top_outcomes[0]` here would see 99.6% and wave the card through
    // to render the "<1%" hero this guard was written to prevent.
    expect(suppressBareZeroFuturesCard(item, Date.parse("2026-08-31T20:00:00Z"))).toBe(true);
  });

  it("still leaves a healthy affirmative alone", () => {
    const healthy = {
      ...nearZeroAffirmative,
      top_outcomes: [
        { name: "No: the claim", probability: 0.6, movement: null },
        { name: "the claim", probability: 0.4, movement: null },
      ],
    } as unknown as FeedFuturesData;
    const item = { ...FIXTURE["108621"].item, data: healthy } as unknown as FeedItem;
    expect(suppressBareZeroFuturesCard(item, Date.parse("2026-08-31T20:00:00Z"))).toBe(false);
  });
});

// ── Survivors: the five live cards that must not move ───────────────────────

describe("the other five two-outcome cards in the live feed keep their hero", () => {
  it.each([
    ["108621", "85%", "Which party will win the U.S. House? — two parties, no negation"],
    ["52756062", "25%", "Texas State House winner? — Democratic party / Republican party"],
    ["59698974", "50%", "MotoGP World Champion (2026) — two named riders"],
    ["59925149", "67%", "Will Tesla close above $360? — one priced outcome, already affirmative"],
    ["59530991", "92%", "Will Russia target Kyiv by...? — one priced outcome"],
  ])("%s still headlines %s (%s)", (id, expected) => {
    expect(heroText(renderDiscover(id))).toBe(expected);
  });

  it("changes exactly two of the seven — the whole live two-outcome population", () => {
    const moved = Object.keys(FIXTURE).filter((id) => {
      const outs = FIXTURE[id].data.top_outcomes ?? [];
      return heroOutcome(outs) !== outs[0];
    });
    expect(moved.sort()).toEqual(["57792416", "59934328"]);
  });
});

// ── The predicate's false-positive set ──────────────────────────────────────

describe("a negation is a restatement of its sibling, not a name starting with No", () => {
  it.each([
    // The Fed's real outcome row, named in leaderOrder.ts as the 56% row a slice
    // once dropped. `/^no\b/` matches it; the pair test is what does not.
    [{ name: "No change" }, { name: "25 bps cut" }, "No change / 25 bps cut"],
    [{ name: "Norway" }, { name: "Sweden" }, "Norway / Sweden"],
    [{ name: "Nottingham Forest" }, { name: "Forest" }, "Nottingham Forest / Forest"],
    [{ name: "North Carolina" }, { name: "Carolina" }, "North Carolina / Carolina"],
    [{ name: "No. 1 seed" }, { name: "1 seed" }, "No. 1 seed / 1 seed"],
    // Too short to be evidence of anything.
    [{ name: "No A" }, { name: "A B C" }, "one-letter restatement"],
  ])("does not read %j as negating %j (%s)", (neg, aff) => {
    expect(negates(neg, aff)).toBe(false);
  });

  it.each([
    [{ name: "No" }, { name: "Yes" }, "the canonical binary"],
    [
      { name: "Not Neuralink's valuation" },
      { name: "Neuralink's valuation" },
      "Polymarket's `Not <restatement>`",
    ],
    [
      { name: 'No: "Onslaught" score at least 80 on ...' },
      { name: '"Onslaught" score at least 80 on the ...' },
      "`No: <restatement>`, each side truncated at a different length",
    ],
  ])("reads %j as negating %j (%s)", (neg, aff) => {
    expect(negates(neg, aff)).toBe(true);
  });

  it("keeps the served headline when the affirmative has no price to print", () => {
    // A swap that leaves the card with no hero is not a fix. An unpriced
    // affirmative keeps the card exactly as it renders today.
    const outs = [
      { name: "No: the claim", probability: 0.9 },
      { name: "the claim", probability: null },
    ];
    expect(heroOutcome(outs)).toBe(outs[0]);
  });

  it("leaves a market with more than two outcomes entirely alone", () => {
    // The negation rule is about a binary pair. A three-way market containing a
    // "No ..." row must never have its headline re-pointed.
    const outs = [
      { name: "No change", probability: 0.56 },
      { name: "25 bps cut", probability: 0.3 },
      { name: "50 bps cut", probability: 0.14 },
    ];
    expect(heroOutcome(outs)).toBe(outs[0]);
  });
});
