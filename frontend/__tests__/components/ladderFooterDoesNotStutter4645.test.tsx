/**
 * #4645 — the ladder footer stops saying "above" twice.
 *
 * Production, 390px, Discover card "Netflix App Downloads in September",
 * 2026-09-09 21:36 PT, under a comparator ladder:
 *
 *     Above 50% through  Above 67
 *
 * The fixed prefix was written for the DATE ladder it shipped with, where the
 * rung label is a date and the sentence closes ("Above 50% through Before
 * 2027"). On a comparator ladder the label opens with the same word the caption
 * ends near, so the reader gets two comparators and two unrelated quantities
 * (50, 67) in six words, and the line parses as nothing.
 *
 * D102 keeps small grey type where it offers the reader value, and this line
 * has a real thing to say — the furthest rung the market still calls better
 * than even — so the fix is the grammar, not the deletion.
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

type Point = { label: string; probability: number; value: number };

function ladderData(points: Point[], name: string): FeedFuturesData {
  return {
    id: 91,
    name,
    llm_sport_category: "economics",
    sport_name: "Economics",
    resolution_date: "2026-10-07T00:00:00Z",
    top_outcomes: points.map((p, i) => ({
      id: i + 1,
      name: p.label,
      probability: p.probability,
      movement: null,
    })),
    outcome_count: points.length,
    volume_24h: 500_000,
    confidence_tier: "high",
    discover_card: { suggested_format: "threshold_heatmap", threshold_points: points },
  } as unknown as FeedFuturesData;
}

function render(points: Point[], name = "Netflix App Downloads in September"): string {
  const data = ladderData(points, name);
  const item = { type: "futures", score: 90, reason: "", headline: "", data } as unknown as FeedItem;
  return renderToStaticMarkup(
    <FuturesCard item={item} data={data} liked={false} setLiked={() => {}} trending={false} />,
  );
}

/**
 * The composed footer sentence: the grey caption and the accented rung label it
 * points at, read as the reader reads them — as one line.
 */
function footerSentence(html: string): string | null {
  const m = html.match(
    /<span class="[^"]*text-text-secondary[^"]*">([^<]*)<\/span><span class="[^"]*text-accent-brand[^"]*">([^<]*)<\/span>/,
  );
  return m ? `${m[1]} ${m[2]}` : null;
}

/** The card in the photograph, minus the impossible rung #4610 removes. */
const comparatorLadder: Point[] = [
  { label: "Above 52", probability: 0.92, value: 52 },
  { label: "Above 58", probability: 0.88, value: 58 },
  { label: "Above 64", probability: 0.64, value: 64 },
  { label: "Above 70", probability: 0.41, value: 70 },
  { label: "Above 73", probability: 0.33, value: 73 },
];

const dateLadder: Point[] = [
  { label: "Before 2027", probability: 0.58, value: 1 },
  { label: "2027", probability: 0.24, value: 2 },
  { label: "2029 or later", probability: 0.08, value: 3 },
];

describe("#4645 the footer says one thing", () => {
  test("a comparator ladder no longer prints the comparator twice", () => {
    const html = render(comparatorLadder);
    expect(html).not.toContain("Above 50% through");
    expect(html).toContain("More likely than not:");
    // The rung it points at is unchanged: the furthest one still over even.
    expect(html).toContain(">Above 64<");
  });

  test("no rendering of the caption puts two comparators in one sentence", () => {
    // The class, not the case: whatever the caption becomes, the sentence it
    // forms WITH the rung label may not repeat the label's comparator. Read off
    // the rendered pair rather than a literal, so a future rewording cannot
    // reintroduce the stutter. (The ladder rows above legitimately print
    // "Above 52 … Above 58"; only this composed sentence is under the rule.)
    const sentence = footerSentence(render(comparatorLadder));
    expect(sentence).toBe("More likely than not: Above 64");
    expect(sentence?.match(/above/gi)?.length).toBe(1);
  });

  test("the date ladder it was written for still reads", () => {
    const html = render(dateLadder, "When will Apple ship it?");
    expect(html).toContain("More likely than not:");
    expect(html).toContain(">Before 2027<");
  });

  test("CONTROL: a ladder with no rung over 50% prints no caption at all", () => {
    // Already true before this change (the `lastAbove50Label` guard drops the
    // row) and it must stay true — an orphan "More likely than not:" with
    // nothing after it would be worse than the stutter.
    const html = render([
      { label: "Above 52", probability: 0.41, value: 52 },
      { label: "Above 58", probability: 0.33, value: 58 },
    ]);
    expect(html).not.toContain("More likely than not");
    expect(html).not.toContain("Above 50% through");
  });
});
