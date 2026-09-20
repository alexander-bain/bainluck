/**
 * #7492 — A COMPARISON BUNDLE SEATS ITS MEMBERS, THE WAY ITS THEME SIBLING DOES.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Discover at 390px, `GET /api/feed?limit=200` read at 12:41Z 2026-09-20. Two
 * bundle cards in one scroll, both `type:"bundle"`, both two members:
 *
 *     AI theme bundle            "Where does AI land next?"      2 rows, green `Expand`
 *     IPO comparison bundle      "Which of these companies is    1 row,  blue  `Show 1 more`
 *                                 priced highest to list?"
 *
 * The comparison card asked a comparison question and drew ONE answer, under a
 * control that cost a row to reveal a row. `DiscoverCard.tsx:179` forks a
 * bundle on `kind`: `"theme"` went to `ThemeBundleCard`, which seated
 * `items.slice(0, PEEK_COUNT)` with `PEEK_COUNT = 5`; everything else went to
 * `GroupCard`, which seated `items[0]`.
 *
 * Four things differed at once between two cards of one family (notice 35):
 * seat count, control label, control colour (`text-blue-600`, a raw Tailwind
 * palette class the design system forbids) and control border. The fix moves
 * the seat count into `BUNDLE_PEEK_COUNT` in `components/discover/constants.ts`,
 * which both cards now read, and gives the comparison footer the sibling's
 * label, accent token and top border.
 *
 * ── WHY THIS ENTERS AT `DiscoverCard` ───────────────────────────────────────
 *
 * Same reason `comparisonBundleSharedQuestion4066` does: the claim is about
 * what the SERVED payload draws, and the fork that decides which card draws it
 * is in `DiscoverCard`. Handing members straight to `GroupCard` would prove a
 * component and not a reader's page.
 *
 * ── WHY THE ROW COUNT IS COUNTED BY MEMBER NAME ─────────────────────────────
 *
 * `FuturesCompactRow` prints `data.name` (`FuturesCard.tsx:960`), so a member's
 * name in the markup IS its row. Counting wrapper `div`s would count the
 * header and the action bar too; counting a class would count whatever else
 * happens to wear it. The trap paid on #7457 was anchoring a guard on a
 * design-system class (`text-accent-brand` also matches a ladder's highlighted
 * rung) — so the footer arms below anchor on the control's literal text and on
 * the raw class that must be gone, never on the token that replaced it.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. 🔴 the two-member production specimen seats BOTH members and grows no
 *     control at all — there is nothing behind it;
 *  2. 🔴 a bundle with more members than the peek seats exactly the peek, and
 *     says so in the sibling's words;
 *  3. 🔴 the footer carries no raw `text-blue-*` class on either kind;
 *  4. the chevron is drawn only where it does something — the same lie as
 *     `Show 1 more`, in the header;
 *  5. CONTROL: the theme sibling seats the same count from the same constant,
 *     so one kind cannot be fixed by breaking the other;
 *  6. CONTROL: the render reached a real bundle card (its shared question is on
 *     screen), so arms 1–4 cannot pass by rendering nothing.
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

/** `_bundle_subtitle("ipo_valuation", 2)` — the specimen's own header line. */
const SHARED_QUESTION = "Which of these companies is priced highest to list?";

/** The chevron's path data, from both bundle headers. */
const CHEVRON = "M19 9l-7 7-7-7";

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
      top_outcomes: [{ id, name: "Above $100B", probability, movement: null }],
      outcome_count: 3,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

/** The production specimen: `comparison:ipo_valuation:24647105-30691373`, 2 members. */
const PAIR = [
  member(24647105, "What will OpenAI's IPO valuation be?", 0.41),
  member(30691373, "What will SpaceX's IPO valuation be?", 0.27),
];

/** The same shape, past the peek, so the cap has something to cut. */
const OVERFLOW = Array.from({ length: BUNDLE_PEEK_COUNT + 2 }, (_, i) =>
  member(90000000 + i, `IPO valuation member number ${i + 1}`, 0.5 - i * 0.03),
);

function bundleItem(members: FeedItem[], overrides: Partial<FeedBundleData>): FeedItem {
  return {
    type: "bundle",
    score: 70,
    reason: "",
    headline: null,
    data: {
      id: "comparison:ipo_valuation:24647105-30691373",
      title: "IPO valuation ranges",
      kind: "comparison",
      comparison_theme: "ipo_valuation",
      shared_question: SHARED_QUESTION,
      item_count: members.length,
      member_ids: members.map((m) => (m.data as FeedFuturesData).id),
      items: members,
      ...overrides,
    } as unknown as FeedBundleData,
  } as unknown as FeedItem;
}

function render(members: FeedItem[], overrides: Partial<FeedBundleData> = {}): string {
  return renderToStaticMarkup(
    <DiscoverCard
      groupedItem={{ type: "single", item: bundleItem(members, overrides) }}
      positionIndex={0}
    />,
  );
}

/**
 * React escapes text nodes, so the specimen's real name — `What will OpenAI's
 * IPO valuation be?` — reaches the markup as `OpenAI&#x27;s` and a raw
 * `includes` on it reads as "this member drew no row" for a member sitting in
 * plain sight. Escaping here rather than renaming the fixture keeps the
 * specimen the specimen.
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
}

/** How many of `members` drew a row — a member's name IS its row. */
function seated(html: string, members: FeedItem[]): number {
  return members.filter((m) => html.includes(escapeHtml((m.data as FeedFuturesData).name))).length;
}

describe("#7492 — the comparison bundle seats the comparison", () => {
  it("CONTROL: the render reached a real bundle card", () => {
    // Without this, every `not.toContain` below would pass on an empty string.
    expect(render(PAIR)).toContain(SHARED_QUESTION);
  });

  it("🔴 seats BOTH members of the two-member specimen, and asks for no tap", () => {
    const html = render(PAIR);

    expect(seated(html, PAIR)).toBe(2);
    // The exact control the shipped card grew. There is nothing behind it now,
    // so there is no control: a footer that reveals a row by costing a row is
    // the defect, not a smaller version of it.
    expect(html).not.toContain("Show 1 more");
    expect(html).not.toContain("Show all");
  });

  it("🔴 seats exactly the peek when there are more members, in the sibling's words", () => {
    const html = render(OVERFLOW);

    expect(seated(html, OVERFLOW)).toBe(BUNDLE_PEEK_COUNT);
    expect(seated(html, OVERFLOW.slice(0, BUNDLE_PEEK_COUNT))).toBe(BUNDLE_PEEK_COUNT);
    expect(html).toContain(`Show all ${OVERFLOW.length}`);
    // `Show N more` was this card's private grammar; the family has one.
    expect(html).not.toContain("more</button>");
  });

  it("🔴 grows no raw Tailwind palette class on either bundle kind", () => {
    // CLAUDE.md, Frontend Design System (MANDATORY): tokens, never raw palette
    // classes. `text-blue-600 hover:text-blue-700` is why the two footers were
    // different colours in one scroll.
    expect(render(OVERFLOW)).not.toContain("text-blue-");
    expect(render(OVERFLOW, { kind: "theme", story_key: "ipo" })).not.toContain("text-blue-");
  });

  it("draws the header chevron only where it opens something", () => {
    expect(render(PAIR)).not.toContain(CHEVRON);
    expect(render(OVERFLOW)).toContain(CHEVRON);
  });

  it("CONTROL: the theme sibling seats the same count from the same constant", () => {
    const html = render(OVERFLOW, { kind: "theme", story_key: "ipo" });

    expect(seated(html, OVERFLOW)).toBe(BUNDLE_PEEK_COUNT);
    expect(html).toContain(`Show all ${OVERFLOW.length}`);
  });
});
