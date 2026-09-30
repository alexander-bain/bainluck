/**
 * #9642 — Discover's related-question groups take Alex's selected design A (9/29).
 *
 * A is a compact group treatment: a small category eyebrow, the shared question
 * as the card's heading on the card's own white, three questions at equal weight
 * with their probabilities in one right-aligned column, and "All N questions"
 * for the rest. It is a treatment for the groups the feed already builds — not an
 * all-group feed — so standalone cards are asserted untouched here too.
 *
 * Both bundle kinds are rendered through `DiscoverCard`, the path the page uses:
 * `kind:"theme"` → ThemeBundleCard, anything else → GroupCard. They share one
 * header component so the two cannot drift (the #6929 chip defect had to be
 * fixed in both files by hand).
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedBundleData, FeedFuturesData, FeedItem } from "@/lib/types";

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

import DiscoverCard from "../../components/DiscoverCard";
import { BUNDLE_PEEK_COUNT } from "../../components/discover/constants";

const QUESTION = "What does the Fed do next?";

function member(id: number, name: string, probability: number): FeedItem {
  return {
    type: "futures",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id,
      name,
      llm_sport_category: "economics",
      top_outcomes: [{ id, name: "Keep rates unchanged", probability, movement: null }],
      outcome_count: 3,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

/** Five members: the peek must cut two. Names are fixtures, not live markets. */
const MEMBERS = [
  member(1, "Fed decision in October", 0.67),
  member(2, "Fed decision in December", 0.76),
  member(3, "September inflation year over year", 0.66),
  member(4, "September core inflation", 0.37),
  member(5, "Fed decision in January", 0.52),
];

function render(kind: string, sharedQuestion: string | null = QUESTION): string {
  const item = {
    type: "bundle",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id: `${kind}:fed:1-5`,
      title: "Fed & rates",
      kind,
      story_key: kind === "theme" ? "fed" : undefined,
      shared_question: sharedQuestion,
      item_count: MEMBERS.length,
      member_ids: MEMBERS.map((m) => (m.data as FeedFuturesData).id),
      items: MEMBERS,
    } as unknown as FeedBundleData,
  } as unknown as FeedItem;
  return renderToStaticMarkup(<DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />);
}

function seated(html: string): number {
  return MEMBERS.filter((m) => html.includes((m.data as FeedFuturesData).name)).length;
}

const KINDS: Array<[string, string]> = [
  ["ThemeBundleCard (kind:theme)", "theme"],
  ["GroupCard (kind:comparison)", "comparison"],
];

describe("#9642 — bundle cards take selected design A", () => {
  it.each(KINDS)("CONTROL: %s reached a real bundle with its question", (_label, kind) => {
    const html = render(kind);
    expect(html).toContain(QUESTION);
    expect(html).toContain('data-testid="bundle-action-bar"');
  });

  it("seats three questions at equal weight", () => {
    expect(BUNDLE_PEEK_COUNT).toBe(3);
  });

  it.each(KINDS)("%s seats exactly three rows and names the rest as questions", (_label, kind) => {
    const html = render(kind);
    expect(seated(html)).toBe(3);
    expect(html).toContain(`All ${MEMBERS.length} questions`);
    expect(html).not.toContain("Show all");
  });

  it.each(KINDS)("%s prints the category as an eyebrow, not a filled chip", (_label, kind) => {
    const html = render(kind);
    const eyebrow = html.match(/data-testid="bundle-eyebrow" class="([^"]*)"/);
    expect(eyebrow).not.toBeNull();
    expect(eyebrow![1]).toContain("text-text-secondary");
    expect(eyebrow![1]).not.toMatch(/\brounded-full\b|\bbg-/);
    // The emoji keeps the category identity the chip carried.
    expect(html).toMatch(/data-testid="bundle-eyebrow"[^>]*>\S+ Fed &amp; rates</);
  });

  it.each(KINDS)("%s makes the shared question the heading, on the card's white", (_label, kind) => {
    const html = render(kind);
    expect(html).toContain(`text-[17px] font-bold text-text-primary leading-tight tracking-tight">${QUESTION}<`);
    // The tinted header band is gone from both kinds.
    expect(html).not.toContain("bg-surface-elevated/50");
  });

  it.each(KINDS)("%s draws each probability in the larger right-hand column", (_label, kind) => {
    const html = render(kind);
    const percents = html.match(/data-testid="compact-row-percent"/g) ?? [];
    expect(percents).toHaveLength(3);
    expect(html).toContain('class="font-mono tabular-nums text-base font-bold" data-testid="compact-row-percent"');
    expect(html).toContain(">67%<");
  });

  it.each(KINDS)("%s keeps the count fallback when no shared question was served", (_label, kind) => {
    const html = render(kind, null);
    expect(html).toContain(kind === "theme" ? `· ${MEMBERS.length} related` : `${MEMBERS.length} markets`);
    expect(html).not.toContain("text-[17px]");
  });

  it("CONTROL: a standalone futures card does not take the group treatment", () => {
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item: MEMBERS[0] }} positionIndex={0} />,
    );
    expect(html).toContain("Fed decision in October");
    expect(html).not.toContain('data-testid="bundle-eyebrow"');
    expect(html).not.toContain("All 5 questions");
  });
});
