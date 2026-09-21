/**
 * #7844 HALF TWO — A COALITION BOARD STOPS BEING DRAWN AS A LEADERBOARD.
 *
 * 🔴 THE READER. Production page one, card 3, 390px, 2026-09-21 17:30Z, slug
 * `0c58f558` (`artifacts/d386-shop/nz-card-390-1730Z.png`):
 *
 *     POLITICS · Resolves Jan 31, 2028
 *     Which parties will be part of the next government of New Zealand?
 *     New favorite: Green Party (68%)
 *      1  Green Party                     68%
 *      2  Labour Party                    54%
 *      3  National Party                  53%
 *      4  New Zealand First Party         50%
 *      5  Field and 2 more outcomes
 *
 * Half one took the CAPTION off. The board beneath it says the same false thing
 * in chrome, and it says it twice:
 *
 *   1. `1 2 3 4` is the grammar this component uses for `2026-27 Stanley Cup®
 *      Finals Winner`, one card below it in the same edition, where exactly one
 *      row can win. Here they are four separate yes/no questions printed as a
 *      podium — the four legs sum to 225%, and Green at 68% is not "beating"
 *      Labour at 54%, because both can be in the next government.
 *   2. "Field and 2 more outcomes" is an exhaustiveness-and-exclusivity claim:
 *      it tells a reader the remaining probability lives in a residual field. On
 *      a board summing to 225% there is no residual field. The two hidden rows
 *      are two more independent questions.
 *
 * ** THE REMEDY IS A REFUSAL, NOT A RENORMALIZATION. ** 225% is the honest
 * answer. Scaling a coalition board to 100 would be the defect (#4895 is the
 * inverse case — a genuinely exclusive ladder that DOES need normalizing).
 *
 * ═══ WHY THIS FILE RENDERS THE WRAPPER ═══
 *
 * `DiscoverCard`, not `FuturesCard`, for #4355's reason: the wrapper carries its
 * own fork on `top_outcomes.length >= 4` into `ComparisonCard`, which is a
 * different component with no remainder row. The NZ payload sends three top
 * outcomes, so a reader meets the leaderboard — and asserting that is the only
 * way this file can say it tested the card a reader sees. `data-card-format=
 * "leaderboard"` is checked in both arms for the same reason.
 *
 * ═══ THE WIDENING CONTROL ═══
 *
 * The exclusive twin is the SAME board with `field_is_a_race: true`, and it is
 * both halves of the proof: it shows the change did not widen, and it shows the
 * refusal arm is not green by absence — if the fixture stopped producing a
 * leaderboard at all, the twin reds instead of silently passing.
 *
 * A third arm renders the board with NO `field_is_a_race` key at all. That is
 * the fail-to-today default, and it is what makes every other leaderboard test
 * in this directory still a valid control: none of their fixtures carry the
 * field, so none of their markup moves.
 *
 * ⚠️ EVERY ASSERTION OF ABSENCE IS PAIRED WITH A POSITIVE — an empty render
 * satisfies `not.toContain` for free. So the refusal arm also asserts the four
 * party names, the four percentages and the remainder count are all still on the
 * card: a reader loses the podium and keeps every number.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import type { DiscoverGroupedItem } from "@/components/discover/types";

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

// ── the fixture, copied verbatim from the served edition ────────────────────

/**
 * `GET /api/feed?limit=200`, 2026-09-21 17:40Z, market 16624064
 * (`artifacts/d387-7844/feed-200-1740Z.json`). Six distribution rows,
 * `remaining_outcome_count` 0, `outcome_count` 8 — so the rendered remainder is
 * `0 + (6 - 4) = 2`, which is where the photographed "Field and 2 more
 * outcomes" comes from. Copied rather than invented: the second term is the one
 * a hand-built fixture gets wrong.
 *
 * The first four rows sum to 2.245. That is the whole defect, and it is why the
 * fixture keeps all six rather than the four that are drawn.
 */
const NZ_DISTRIBUTION = [
  { label: "Green Party", probability: 0.675, movement: null },
  { label: "Labour Party", probability: 0.54, movement: null },
  { label: "National Party", probability: 0.53, movement: null },
  { label: "New Zealand First Party", probability: 0.5, movement: null },
  { label: "ACT New Zealand", probability: 0.46, movement: -0.22000000000000003 },
  { label: "Te Pāti Māori", probability: 0.18, movement: null },
];

/** The three the route serves as `top_outcomes` — the wrapper's fork input. */
const NZ_TOP_OUTCOMES = [
  { id: 95083484, name: "Green Party", probability: 0.675, movement: null },
  { id: 95083480, name: "Labour Party", probability: 0.54, movement: null },
  { id: 95083483, name: "National Party", probability: 0.53, movement: null },
];

const NZ_QUESTION =
  "Which parties will be part of the next government of New Zealand?";

/**
 * `fieldIsARace: undefined` omits the key entirely rather than sending `null`,
 * because "an older payload" is the case the default exists for and an absent
 * key is what an older payload actually sends.
 */
function nzCard(fieldIsARace?: boolean): FeedItem {
  const discoverCard: Record<string, unknown> = {
    suggested_format: "outcome_distribution",
    distribution_outcomes: NZ_DISTRIBUTION,
    remaining_outcome_count: 0,
  };
  if (fieldIsARace !== undefined) discoverCard.field_is_a_race = fieldIsARace;
  return {
    type: "futures",
    score: 88,
    reason: "",
    headline: "",
    data: {
      id: 16624064,
      name: NZ_QUESTION,
      llm_sport_category: "politics",
      sport_name: null,
      resolution_date: "2028-02-01T04:59:00+00:00",
      top_outcomes: NZ_TOP_OUTCOMES,
      outcome_count: 8,
      market_tier: 2,
      confidence_tier: "low",
      discover_card: discoverCard,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "item", item } as unknown as DiscoverGroupedItem} />
  );
}

/** #4355's helper: `aria-label="Rank N"` marks the rank cell of a named row. */
function namedRowRanks(markup: string): number[] {
  return [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
}

/** Row labels in rendered order, off the `title` each named row carries. */
function renderedLabels(markup: string): string[] {
  return NZ_DISTRIBUTION.map((r) => ({
    label: r.label,
    at: markup.indexOf(`title="${r.label}"`),
  }))
    .filter((x) => x.at !== -1)
    .sort((a, b) => a.at - b.at)
    .map((x) => x.label);
}

/** #6586's helper: the remainder row's own markup, or "" if it was not drawn. */
function remainderRow(markup: string): string {
  const start = markup.indexOf('data-row="field-remainder"');
  if (start === -1) return "";
  const end = markup.indexOf("</div>", start);
  return markup.slice(start, end === -1 ? undefined : end);
}

/** The percentage column, in render order. */
function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)]
    .map((m) => m[1])
    .filter((c) => c.endsWith("%"));
}

// ─────────────────────────────────────────────────────────────────────────────
describe("#7844 half two — the coalition board drops the podium", () => {
  describe("the refusal arm: field_is_a_race === false", () => {
    const markup = render(nzCard(false));

    it("still reaches the leaderboard, so the assertions below are about a card", () => {
      // Without this every `not.toContain` in this block passes on an empty
      // render, on the ComparisonCard fork, or on a hero fallback.
      expect(markup).toContain('data-card-format="leaderboard"');
      expect(markup).not.toContain('data-card-format="comparison"');
      expect(renderedLabels(markup)).toEqual([
        "Green Party",
        "Labour Party",
        "National Party",
        "New Zealand First Party",
      ]);
    });

    it("prints no rank digits — the four legs are not racing for one slot", () => {
      expect(namedRowRanks(markup)).toEqual([]);
      // The screen-reader half of the same claim. `aria-label` is checked above;
      // `title="Rank N by probability"` is the sighted hover, and leaving either
      // behind keeps the false sentence for one of the two readers.
      expect(markup).not.toContain("Rank 1 by probability");
      expect(markup).not.toContain("by probability");
    });

    it("makes no exhaustiveness claim about the two rows it does not draw", () => {
      const row = remainderRow(markup);
      // Paired positive first: the row IS drawn and IS readable, so the
      // negative below is a statement about its content and not about a
      // slicer that found nothing (#6586's red-first lesson).
      expect(row).not.toBe("");
      expect(row).toContain("2 more outcomes");
      // "Field and" is the residual claim, and it is the only part removed.
      expect(row).not.toContain("Field and");
      // The remainder row's own rank cell — the podium's fifth rung.
      expect(row).not.toContain(">5<");
    });

    it("keeps every number a reader came for", () => {
      // The refusal must not empty the card: that would be the same defect,
      // silent. 225% across the drawn rows is the honest answer and stays.
      expect(valueCells(markup)).toEqual(["68%", "54%", "53%", "50%"]);
      expect(markup).toContain(NZ_QUESTION);
    });

    it("gives the label column the track the rank digits used to hold", () => {
      // The cell is a grid column, not a decoration: emptying it without
      // dropping the track would leave a dead 1.25rem gutter, and dropping the
      // content without the track would slide every label one column left.
      expect(markup).toContain("grid-cols-[minmax(0,1fr)_2.75rem]");
      expect(markup).not.toContain("grid-cols-[1.25rem_minmax(0,1fr)_2.75rem]");
    });
  });

  describe("the exclusive twin: the widening control AND the non-vacuity proof", () => {
    // Byte-identical board, `field_is_a_race: true`. Every assertion here is
    // the negation of one above. If this block goes green while the block above
    // does too, the change is confined to the population it names; if this
    // block reds, the block above has stopped testing anything.
    const markup = render(nzCard(true));

    it("keeps its rank digits", () => {
      expect(markup).toContain('data-card-format="leaderboard"');
      expect(namedRowRanks(markup)).toEqual([1, 2, 3, 4]);
      expect(markup).toContain("Rank 1 by probability");
    });

    it("keeps the residual-field row exactly as #6586 left it", () => {
      const row = remainderRow(markup);
      expect(row).toContain("Field and 2 more outcomes");
      expect(row).toContain(">5<");
      expect([...row.matchAll(/<span\b/g)]).toHaveLength(2); // rank + label
    });

    it("keeps the four-column grid", () => {
      expect(markup).toContain("grid-cols-[1.25rem_minmax(0,1fr)_2.75rem]");
    });
  });

  describe("an absent flag draws today's board", () => {
    // The fail-to-today default, asserted directly. This is the arm that makes
    // every other leaderboard fixture in this directory — none of which carries
    // `field_is_a_race` — still a valid control for this change.
    const markup = render(nzCard(undefined));
    const twin = render(nzCard(true));

    it("is byte-for-byte the exclusive twin", () => {
      expect(markup).toEqual(twin);
    });

    it("and that board is the podium, not the refusal", () => {
      // Paired positive: `toEqual` above would also pass if BOTH renders had
      // silently become the refusal.
      expect(namedRowRanks(markup)).toEqual([1, 2, 3, 4]);
      expect(markup).toContain("Field and 2 more outcomes");
    });
  });
});
