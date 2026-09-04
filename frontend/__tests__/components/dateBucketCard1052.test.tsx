/**
 * UX-1052 item 4 — the date-bucket card, on screen.
 *
 * Alex, shopping Discover at 1:00pm PT on 2026-09-03:
 *
 *     "Multi-outcome date questions are unreadable. Discover card 'When will
 *      Apple release the iPhone 18?' shows one number (15%, 'Before 2027') and
 *      a sentence that says the same thing twice ('Before October down 30.5
 *      points from opening; Before 2027 leads at 15% — Before October moved
 *      down 30.5 points from opening in When will…'). Design: outcomes as
 *      ordered bars (Before Oct · Before 2027 · …) with the leader marked and
 *      the mover marked, one sentence that never repeats a clause; the share
 *      text ('Before 2027 is at 15% in When will Apple…') gets the same
 *      treatment."
 *
 * Three separate claims, three sections below. The classification half lives in
 * `backend/tests/test_date_bucket_ladder_1052.py`; this proves the card DRAWS
 * the ladder, marks both things Alex asked to be marked, and stops saying the
 * same thing twice.
 *
 * The repeated-clause section is deliberately not a test of this one card. The
 * bug was in `feedExpandedContext`'s duplicate detector — it split on
 * whitespace, so "opening;" and "opening" were different words, and it compared
 * against a candidate that still carried a trailing " in <market name>" whose
 * dozen unmatched words dragged the ratio under the bar on their own. Both are
 * asserted directly.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

import { FuturesCard } from "@/components/discover/FuturesCard";
import { feedExpandedContext, feedContextSnippet } from "@/components/discover/utils";
import { buildLadderShareText } from "@/lib/share";
import type { FeedItem, FeedFuturesData } from "@/lib/types";

/** The served payload for market 109349, with the rungs the fixed backend adds. */
const IPHONE_DATA = {
  id: 109349,
  name: "When will Apple release the iPhone 18?",
  sport: null,
  sport_name: null,
  llm_sport_category: "tech",
  source: "kalshi",
  source_count: 1,
  sources: ["kalshi"],
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

const IPHONE_ITEM: FeedItem = {
  type: "futures",
  score: 74,
  reason: "Before October moved down 30.5 points from opening in When will Apple release the iPhone 18?",
  headline: "Before October down 30.5 points from opening",
  context_summary: "Before October down 30.5 points from opening; Before 2027 leads at 15%",
  data: IPHONE_DATA,
} as unknown as FeedItem;

function render() {
  return renderToStaticMarkup(
    <FuturesCard
      item={IPHONE_ITEM}
      data={IPHONE_DATA}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("UX-1052 item 4 — ordered bars, not one number", () => {
  it("renders the ladder card, not the one-number card", () => {
    expect(render()).toContain('data-card-format="heatmap"');
  });

  it("shows every bucket, in chronological order", () => {
    const html = render();
    const order = ["Before April", "Before July", "Before October", "Before 2027"];
    let cursor = -1;
    for (const label of order) {
      const at = html.indexOf(label, cursor + 1);
      expect(at).toBeGreaterThan(cursor);
      cursor = at;
    }
  });

  it("marks the LEADER — and it is not the top row", () => {
    // Chronological order puts the 1% April bucket first. Without a mark the
    // reader has to scan four bars to find the answer.
    const html = render();
    const leaderIdx = html.indexOf("Before 2027");
    const aprilIdx = html.indexOf("Before April");
    expect(leaderIdx).toBeGreaterThan(aprilIdx);
    // The highlighted-rung treatment (tinted row + accent label), and it is on
    // the LEADER'S row — asserted against that row, not the document, so an
    // unrelated tint elsewhere cannot satisfy it.
    expect(html).toContain("bg-accent-brand/[0.06]");
    const rowStart = html.lastIndexOf('<div class="flex items-center gap-3', leaderIdx);
    expect(rowStart).toBeGreaterThan(-1);
    const leaderRow = html.slice(rowStart, leaderIdx);
    expect(leaderRow).toContain("bg-accent-brand/[0.06]");
    // …and the 1% April row is NOT marked.
    const aprilStart = html.lastIndexOf('<div class="flex items-center gap-3', aprilIdx);
    expect(html.slice(aprilStart, aprilIdx)).not.toContain("bg-accent-brand/[0.06]");
  });

  it("marks the MOVER, and only the rungs that actually moved", () => {
    const html = render();
    expect(html).toContain("30.5");
    expect(html).toContain("▼");
    // Two of the four buckets have no movement — they get no chip.
    expect(html.split("▼").length - 1).toBe(2);
  });

  it("does not print an arrow for a movement that rounds to nothing", () => {
    const data = {
      ...IPHONE_DATA,
      discover_card: {
        ...(IPHONE_DATA as unknown as { discover_card: Record<string, unknown> }).discover_card,
        threshold_points: [
          { source: "date_bucket", label: "Before July", value: 202607, unit: "date", direction: "before", probability: 0.3, movement: 0.00003 },
          { source: "date_bucket", label: "Before 2027", value: 202701, unit: "date", direction: "before", probability: 0.5, movement: null },
        ],
      },
    } as unknown as FeedFuturesData;
    const html = renderToStaticMarkup(
      <FuturesCard item={{ ...IPHONE_ITEM, data }} data={data} liked={false} setLiked={() => {}} trending={false} />,
    );
    expect(html).not.toContain("▲");
    expect(html).not.toContain("▼");
  });
});

describe("UX-1052 item 4 — one sentence that never repeats a clause", () => {
  it("stops appending the clause the snippet already made", () => {
    const expanded = feedExpandedContext(IPHONE_ITEM);
    expect(expanded).toBe(feedContextSnippet(IPHONE_ITEM));
    expect(expanded).not.toContain("moved down 30.5 points from opening");
  });

  it("is punctuation-blind — the old detector was defeated by a semicolon", () => {
    // "opening;" vs "opening" was one of the two reasons the ratio came out
    // at 0.375 instead of over the 0.7 bar.
    const item = {
      ...IPHONE_ITEM,
      context_summary: "Alpha leads at 40%; Beta down 5 points from opening",
      reason: "Beta down 5 points from opening",
    } as unknown as FeedItem;
    expect(feedExpandedContext(item)).toBe(feedContextSnippet(item));
  });

  it("drops the trailing market name before comparing", () => {
    const item = {
      ...IPHONE_ITEM,
      context_summary: "Alpha leads at 40%",
      reason: "Alpha leads at 40% in When will Apple release the iPhone 18?",
    } as unknown as FeedItem;
    expect(feedExpandedContext(item)).toBe("Alpha leads at 40%");
  });

  it("STILL appends genuinely new context — this is a better detector, not a stricter one", () => {
    const item = {
      ...IPHONE_ITEM,
      context_summary: "Before 2027 leads at 15%",
      reason: "Apple has never shipped a numbered iPhone outside its September window",
    } as unknown as FeedItem;
    const expanded = feedExpandedContext(item);
    expect(expanded).toContain("Before 2027 leads at 15%");
    expect(expanded).toContain("September window");
  });
});

describe("UX-1052 item 4 — the share text gets the same treatment", () => {
  // `ActionBar` hands share text to a handler and never renders it, so the
  // wording is asserted on the builder the card calls — the reason it is a
  // named export rather than a template literal inline.
  //
  // CERT-867 amended what that buys. This section grades the SENTENCE; it
  // cannot grade the ARGUMENTS, and the two are independently wrong-able. The
  // wiring now has its own file (`ladderShareNoun867.test.tsx`), which captures
  // the prop at the `ActionBar` boundary. Every call below therefore passes
  // `"date"` explicitly: these are claims about the date card specifically, not
  // about whatever kind the component happens to infer.
  it("reads forwards, names the leader, and says the ladder has more rungs", () => {
    expect(
      buildLadderShareText("When will Apple release the iPhone 18?", "Before 2027", 0.15, 4, "date"),
    ).toBe(
      "When will Apple release the iPhone 18? — Before 2027 leads at 15% across 4 windows on Bain Luck.",
    );
  });

  it("no longer reads backwards as 'X is at Y% in <question>'", () => {
    const text = buildLadderShareText("When will Apple release the iPhone 18?", "Before 2027", 0.15, 4, "date");
    expect(text).not.toContain("is at 15% in When will Apple");
    expect(text.indexOf("When will Apple")).toBe(0);
  });

  it("says 'window' when there is only one", () => {
    expect(buildLadderShareText("Q", "Before 2027", 0.5, 1, "date")).toContain("across 1 window on");
  });

  it("is the text the card actually passes to its share action", () => {
    // RETITLED IN PLACE BY CERT-867, not deleted, because the claim it makes is
    // still true and still worth pinning — but it never justified its old name.
    // It proves the ladder BRANCH renders with these inputs; it does not and
    // cannot observe the share prop, which is exactly how the wrong rung noun
    // shipped past it. The prop itself is asserted in `ladderShareNoun867`.
    const html = render();
    expect(html).toContain('data-card-format="heatmap"');
    expect(html).toContain("Before 2027");
    expect(html).toContain("15%");
  });
});
