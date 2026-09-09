/**
 * #4428 — WHAT A BUNDLE'S SHARE ACTUALLY SAYS, AND WHERE IT POINTS.
 *
 * `bundleHasAnActionBar4428.test.tsx` proves the affordance exists. This file
 * proves it carries something worth sending, and it captures the props at the
 * `ActionBar` boundary rather than asserting the builder on its own.
 *
 * That distinction is CERT-867's, and it is the reason this is a second file:
 * `buildLadderShareText` shipped correct and was called with the wrong argument,
 * so its guard was green while every ladder share on the site said "N windows"
 * about a share price. A correct builder and a wrong call site are
 * indistinguishable to a builder-only test. `ActionBar` never renders `shareText`
 * or `shareUrl`, so the mock is the only place the value leaves the component.
 *
 * ═══ THE TWO THINGS THAT CAN GO WRONG QUIETLY ═══
 *
 * 1. THE URL. A bundle has no detail page. Option A of the issue (recommended,
 *    and the one built) shares `/discover` and puts the content in the text —
 *    `GuessCard` already does exactly this. A share pointing at `/futures/{id}`
 *    would send a stranger to ONE member and look entirely correct in a diff.
 *
 * 2. THE PERCENTS. The sentence quotes numbers the reader can see on the rows
 *    above it. `FuturesCompactRow` prints
 *    `formatProbabilityPercent(p, { rendered: renderedLeaderPercent(...) })`, so
 *    a share that re-rounded the raw probability could disagree by a point —
 *    #3867's defect, one surface further out. The arm below does not hardcode
 *    the number: it reads the percent out of the RENDERED ROW and requires the
 *    captured sentence to contain that same string.
 *
 * FIXTURES ARE VERBATIM PRODUCTION PAYLOADS — `GET /api/feed?limit=25`,
 * 2026-09-09 ~13:05 PT.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem } from "@/lib/types";

/** Prop captures from the mocked `ActionBar`. `mock`-prefixed for jest hoisting. */
const mockBars: { shareUrl: string; shareTitle: string; shareText?: string; hasPin: boolean }[] = [];

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

// Everything real except `ActionBar`. `requireActual` matters: this module also
// exports the badges, the chip and the signal bars the peek rows render, and
// stubbing those would change what is under test.
jest.mock("@/components/discover/shared", () => {
  const actual = jest.requireActual("@/components/discover/shared");
  const ReactLib = require("react");
  return {
    ...actual,
    ActionBar: (props: { shareUrl: string; shareTitle: string; shareText?: string; pin?: unknown }) => {
      mockBars.push({
        shareUrl: props.shareUrl,
        shareTitle: props.shareTitle,
        shareText: props.shareText,
        hasPin: props.pin != null,
      });
      return ReactLib.createElement("div", { "data-testid": "action-bar-stub" });
    },
  };
});

import { ThemeBundleCard } from "@/components/discover/ThemeBundleCard";
import { buildBundleShareText } from "@/lib/share";
import BUNDLES from "../fixtures/discoverBundles.20260909.json";

type BundleFixture = {
  data: { title: string; shared_question: string; story_key: string; items: FeedItem[] };
};
const FIXTURES = BUNDLES as unknown as { election2028: BundleFixture; fed: BundleFixture };

function renderBundle(f: BundleFixture): { markup: string; bar: (typeof mockBars)[number] } {
  mockBars.length = 0;
  const markup = renderToStaticMarkup(
    <ThemeBundleCard
      items={f.data.items}
      title={f.data.title}
      sharedQuestion={f.data.shared_question}
      storyKey={f.data.story_key}
      positionIndex={5}
    />
  );
  return { markup, bar: mockBars[0] };
}

/**
 * Every percent the collapsed peek rows actually print, in row order.
 *
 * Entities are decoded because the boundary forms are exactly the ones React
 * escapes: `>99%` arrives as `&gt;99%` and `<1%` as `&lt;1%`. Comparing the raw
 * markup against a share sentence would have made the two disagree on precisely
 * the values this file exists to keep in agreement.
 */
function renderedRowPercents(markup: string): string[] {
  return [...markup.matchAll(/font-mono tabular-nums[^>]*>([^<]+)</g)].map((m) =>
    m[1].replace(/&gt;/g, ">").replace(/&lt;/g, "<").replace(/&amp;/g, "&")
  );
}

describe("#4428 — the 2028 bundle's share", () => {
  const { markup, bar } = renderBundle(FIXTURES.election2028);

  it("CONTROL: one bundle-level ActionBar was mounted, with its props", () => {
    // Every arm below reads `bar`. Without this the whole describe would pass
    // vacuously on a render that mounted no action bar at all — which is the
    // pre-fix state this issue is about.
    expect(mockBars.length).toBe(1);
    expect(bar).toBeDefined();
    expect(markup).toContain("2028 U.S. Presidential Election winner?");
  });

  it("🔴 the share points at Discover, NOT at one member's market page", () => {
    const url = new URL(bar.shareUrl);
    expect(url.pathname).toBe("/discover");
    expect(url.pathname).not.toMatch(/^\/futures\//);
    // Keyed on the FOLD, so a bundle share is attributable to the bundle.
    expect(url.searchParams.get("item_id")).toBe("story:us_2028_election");
    expect(url.searchParams.get("utm_medium")).toBe("discover");
  });

  it("the share is titled with the group's question, not the theme chip", () => {
    expect(bar.shareTitle).toBe("Who wins in 2028?");
    expect(bar.shareTitle).not.toBe("2028 Election");
  });

  it("🔴 the sentence names the members' leaders and the group's question", () => {
    expect(bar.shareText).toBe(
      "Who wins in 2028? — J.D. Vance 23% (2028 U.S. Presidential Election winner?) · " +
        "Jon Ossoff 17% (2028 Democratic presidential nominee) · 2 markets on Bain Luck."
    );
  });

  it("every percent it quotes is one the reader can see on the row above", () => {
    // Read out of the RENDERED rows, not hardcoded.
    //
    // ⚠️ THIS ARM DOES NOT DISCRIMINATE ON TODAY'S PAYLOADS, and saying so is
    // the point. Mutating the component to `Math.round(prob * 100)` leaves it
    // GREEN, because every served `rendered_percent` on this feed read equals
    // the raw rounding (23/23, 17/17, 56/56, 92/92, 93/93). It is a real
    // cross-check and a worthless mutation detector, so the arm that actually
    // holds the rule is the boundary describe at the bottom of this file.
    const printed = renderedRowPercents(markup);
    expect(printed.length).toBe(2);
    for (const percent of printed) {
      expect(bar.shareText).toContain(percent);
    }
  });

  it("no Pin is passed — a bundle has no futures id to pin", () => {
    expect(bar.hasPin).toBe(false);
  });
});

describe("#4428 — a bundle wider than the share cap", () => {
  const { bar } = renderBundle(FIXTURES.fed);

  it("CONTROL: the Fed fixture really has three members", () => {
    expect(FIXTURES.fed.data.items.length).toBe(3);
  });

  it("🔴 it drops a whole member rather than cutting one in half", () => {
    // All three named is 196 characters. A `slice(0,3)`-then-truncate build
    // ends "...(How many Fed rate cuts in 20..." — a broken share, not a short
    // one. Two are named; none is clipped.
    expect(bar.shareText!.length).toBeLessThanOrEqual(180);
    expect(bar.shareText).not.toContain("...");
    expect(bar.shareText).toContain("Hike 25bps 56% (Fed decision in Sep 2026?)");
    expect(bar.shareText).toContain("Exactly 0 cuts 92% (Number of rate cuts in 2026?)");
    expect(bar.shareText).not.toContain("How many Fed rate cuts");
  });

  it("🔴 and still says how many markets there are", () => {
    // The count is what keeps naming two of three honest.
    expect(bar.shareText).toContain("3 markets on Bain Luck.");
  });
});

describe("#4428 — a percent the two roundings disagree about", () => {
  /**
   * CONSTRUCTED, and it has to be: no bundle on page one on 2026-09-09 carried
   * a leader near a boundary, so every arm above is blind to the defect it
   * claims to guard. This takes the 2028 fixture's first member VERBATIM and
   * changes one number — the leader's probability to 0.996, with the served
   * `rendered_percent` removed so the derivation runs.
   *
   * `formatProbabilityPercent` then prints `>99%`, because "rounding may never
   * move a probability across a boundary it is not on" is a rule about the
   * VALUE. `Math.round(0.996 * 100)` prints `100%` — a share telling a stranger
   * a market is settled when the card beside it says it is not.
   */
  const base = FIXTURES.election2028.data.items[0] as unknown as {
    data: { top_outcomes: { name: string; probability: number; rendered_percent?: number }[] };
  };
  const nearCertain = JSON.parse(JSON.stringify(base));
  nearCertain.data.top_outcomes[0].probability = 0.996;
  delete nearCertain.data.top_outcomes[0].rendered_percent;

  const { markup, bar } = renderBundle({
    data: {
      title: FIXTURES.election2028.data.title,
      shared_question: FIXTURES.election2028.data.shared_question,
      story_key: FIXTURES.election2028.data.story_key,
      items: [nearCertain as unknown as FeedItem],
    },
  });

  it("CONTROL: the row itself prints the boundary form", () => {
    // If the row printed "100%" this whole describe would be asserting nothing
    // about a disagreement, because there would not be one.
    expect(renderedRowPercents(markup)).toEqual([">99%"]);
  });

  it("🔴 the share quotes the row's number, not its own rounding", () => {
    expect(bar.shareText).toContain("J.D. Vance >99%");
    expect(bar.shareText).not.toContain("100%");
  });
});

describe("#4428 — the builder's own edges", () => {
  it("an unpriced member is dropped, never printed bare", () => {
    const text = buildBundleShareText(
      "Who wins in 2028?",
      [
        { name: "2028 Democratic presidential nominee", leaderLabel: "Jon Ossoff", percent: "17%" },
        { name: "2028 Republican presidential nominee", leaderLabel: null, percent: null },
      ],
      2
    );
    expect(text).toContain("Jon Ossoff 17% (2028 Democratic presidential nominee)");
    expect(text).not.toContain("2028 Republican presidential nominee");
    // Dropped from the sentence, NOT from the count — it is still a market.
    expect(text).toContain("2 markets on Bain Luck.");
  });

  it("a bundle with nothing priced still shares its question", () => {
    const text = buildBundleShareText(
      "Where is the Middle East conflict heading?",
      [{ name: "Ceasefire by December?", leaderLabel: null, percent: null }],
      4
    );
    expect(text).toBe("Where is the Middle East conflict heading? — 4 markets on Bain Luck.");
  });

  it("one market is not 'markets'", () => {
    expect(buildBundleShareText("Who wins?", [], 1)).toContain("1 market on Bain Luck.");
  });
});
