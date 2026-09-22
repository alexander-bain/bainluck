/**
 * #8033 — TWO ROWS OF ONE RACE STOP OWNING MORE THAN THE RACE.
 *
 * 🔴 THE READER. Production `/discover` at 390px, 2026-09-22, card 3, market
 * 112996 `Brazil Presidential Election`:
 *
 *     1  Flávio Bolsonaro             60%
 *     2  Luiz Inácio Lula da Silva    41%
 *     3  Renan Santos                  1%
 *     4  Jair Bolsonaro               <1%
 *     5  Field and 16 more outcomes
 *
 * Two candidates in ONE election at 60 and 41. No hidden outcome can explain a
 * top two that already exceeds 100, and adding two numbers is the whole proof.
 *
 * ** AND MOST OF THE POINT IS OURS. ** Re-measured off `GET /api/feed?limit=200`
 * at 17:00Z the same day, the raw legs are `0.5955 / 0.405` — a pair summing to
 * **1.0005**. The venue over-round contributes 0.05 of the point the reader sees;
 * our double rounding contributes 0.95, because `0.405` lands exactly on the `.5`
 * grid and rounds up while `0.5955` rounds up beside it.
 *
 * ═══ WHY THE OBVIOUS FIX IS NOT THE FIX ═══
 *
 * The issue proposed largest remainders across the rendered rows. Replayed over
 * the 41 `outcome_distribution` boards in that same pass it moves **23 boards and
 * 25 rows to fix this one card** — a board prints four rows out of a field of
 * thirty-two, and the total of those four is not a claim a reader can check. It is
 * not even always closer to the data: `Presidents Cup` (`6.11 / 4.25 / 3.19 /
 * 3.02`) is pushed from 4 to 5 to satisfy a sum nobody can see. The measurement is
 * in `renderedPercent.ts` above the helper, with the rule and its five refusals.
 *
 * What IS checkable is #7844 half two's own claim: on a field the route calls a
 * race, exactly one row can win. So only the pair is repaired, only when it is a
 * complement pair, only when it already prints over 100, and the leader never
 * moves — it is the same market's headline on surfaces that do not normalize.
 *
 * ═══ THE WIDENING CONTROLS ═══
 *
 * Measured reach is ONE board of 41, so almost all of this file is refusals:
 *
 *   · the SAME board with `field_is_a_race: false` renders 60/41 unchanged;
 *   · the SAME board with NO `field_is_a_race` key renders 60/41 unchanged — the
 *     gate fails CLOSED, unlike #7844's podium which fails to today's rendering;
 *   · rows three and four are asserted byte-identical in every arm, so the field
 *     beneath the pair is proved untouched rather than assumed;
 *   · the unit block refuses an out-of-band pair, a pair already summing to 100, a
 *     tie that would need two points, and a list that is not leader-first.
 *
 * ⚠️ EVERY ABSENCE IS PAIRED WITH A POSITIVE. A card that failed to render at all,
 * or forked to `ComparisonCard`, would satisfy "still prints 41%" for free — so
 * every rendered arm first asserts `data-card-format="leaderboard"` and the four
 * row labels. `top_outcomes` is three rows for exactly that reason: the wrapper
 * forks to the comparison card at four, and the served payload sends three, which
 * is why a reader meets the leaderboard at all.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";
import type { DiscoverGroupedItem } from "@/components/discover/types";
import { renderedRaceBoardPercents } from "@/lib/renderedPercent";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";

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
 * `GET /api/feed?limit=200`, 2026-09-22 17:00Z, market 112996. All eight served
 * rows are kept rather than the four that are drawn: `remaining_outcome_count` is
 * 12 and `outcome_count` is 32, so the rendered remainder is `12 + (8 - 4) = 16`,
 * which is where the photographed "Field and 16 more outcomes" comes from. The
 * second term is what a hand-built fixture gets wrong.
 */
const BRAZIL_DISTRIBUTION = [
  { label: "Flávio Bolsonaro", probability: 0.5955, movement: null },
  { label: "Luiz Inácio Lula da Silva", probability: 0.405, movement: null },
  { label: "Renan Santos", probability: 0.0075, movement: null },
  { label: "Jair Bolsonaro", probability: 0.0015, movement: null },
  { label: "Geraldo Alckmin", probability: 0.0015, movement: null },
  { label: "Camilo Santana", probability: 0.0005, movement: null },
  { label: "Pablo Marçal", probability: 0.0005, movement: null },
  { label: "Tarcisio de Freitas", probability: 0.0005, movement: null },
];

/** The three the route serves as `top_outcomes` — the wrapper's fork input. */
const BRAZIL_TOP_OUTCOMES = [
  { id: 1626862, name: "Flávio Bolsonaro", probability: 0.5955, movement: null },
  { id: 1626861, name: "Luiz Inácio Lula da Silva", probability: 0.405, movement: null },
  { id: 1626863, name: "Renan Santos", probability: 0.0075, movement: null },
];

const BRAZIL_QUESTION = "Brazil Presidential Election";

/** The four labels a reader is shown, in rendered order. */
const DRAWN_LABELS = [
  "Flávio Bolsonaro",
  "Luiz Inácio Lula da Silva",
  "Renan Santos",
  "Jair Bolsonaro",
];

/**
 * `fieldIsARace: undefined` omits the key entirely rather than sending `null`,
 * because "an older payload" is the case the closed gate exists for and an absent
 * key is what an older payload actually sends.
 */
function brazilCard(fieldIsARace?: boolean): FeedItem {
  const discoverCard: Record<string, unknown> = {
    suggested_format: "outcome_distribution",
    distribution_outcomes: BRAZIL_DISTRIBUTION,
    remaining_outcome_count: 12,
  };
  if (fieldIsARace !== undefined) discoverCard.field_is_a_race = fieldIsARace;
  return {
    type: "futures",
    score: 91,
    reason: "",
    headline: "",
    data: {
      id: 112996,
      name: BRAZIL_QUESTION,
      llm_sport_category: "politics",
      sport_name: null,
      resolution_date: "2026-10-04T00:00:00+00:00",
      top_outcomes: BRAZIL_TOP_OUTCOMES,
      outcome_count: 32,
      market_tier: 2,
      confidence_tier: "moderate",
      discover_card: discoverCard,
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "item", item } as unknown as DiscoverGroupedItem} />
  );
}

/** Row labels in rendered order, off the `title` each named row carries. */
function renderedLabels(markup: string): string[] {
  return BRAZIL_DISTRIBUTION.map((r) => ({
    label: r.label,
    at: markup.indexOf(`title="${r.label}"`),
  }))
    .filter((x) => x.at !== -1)
    .sort((a, b) => a.at - b.at)
    .map((x) => x.label);
}

/**
 * The percentage column, in render order.
 *
 * `renderToStaticMarkup` escapes the `<` of UX-P046's `<1%`, so the entity is
 * decoded here — asserting `&lt;1%` would pin the ESCAPING rather than the
 * reading, and a change of renderer would red a test that is about neither.
 */
function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)]
    .map((m) => m[1].replace(/&lt;/g, "<").replace(/&gt;/g, ">"))
    .filter((c) => c.endsWith("%"));
}

// ─────────────────────────────────────────────────────────────────────────────
describe("#8033 — the race board's top two", () => {
  describe("the reader: field_is_a_race === true", () => {
    const markup = render(brazilCard(true));

    it("reaches the leaderboard, so every assertion below is about a card", () => {
      expect(markup).toContain('data-card-format="leaderboard"');
      expect(markup).not.toContain('data-card-format="comparison"');
      expect(renderedLabels(markup)).toEqual(DRAWN_LABELS);
    });

    it("prints a top two a reader can add up", () => {
      const cells = valueCells(markup);
      expect(cells).toEqual(["60%", "40%", "1%", "<1%"]);

      // The reader's own arithmetic, done the way the reader does it.
      const topTwo = cells
        .slice(0, 2)
        .map((c) => Number.parseInt(c.replace("%", ""), 10))
        .reduce((a, b) => a + b, 0);
      expect(topTwo).toBe(100);
      expect(topTwo).toBeLessThanOrEqual(100);
    });

    it("does not move the leader, so the board cannot outrank its own headline", () => {
      // 0.5955 rounds to 60 on its own. A normalizing repair would print 60 here
      // too on THIS specimen but 61 on `0.6 / 0.39`, and no other surface
      // normalizes a board's leader — see clause 4 beside the helper.
      expect(valueCells(markup)[0]).toBe(formatProbabilityPercent(0.5955));
    });

    it("does not move any row beneath the pair", () => {
      expect(valueCells(markup).slice(2)).toEqual([
        formatProbabilityPercent(0.0075),
        formatProbabilityPercent(0.0015),
      ]);
    });

    it("still tells the reader how big the rest of the field is", () => {
      // 12 served + (8 - 4) undrawn. Proves the repair did not reach the
      // remainder row, which is the other thing on this card made of numbers.
      expect(markup).toContain("Field and 16 more outcomes");
    });
  });

  describe("the widening control: field_is_a_race === false", () => {
    const markup = render(brazilCard(false));

    it("reaches the leaderboard, so the assertions below are not green by absence", () => {
      expect(markup).toContain('data-card-format="leaderboard"');
      expect(renderedLabels(markup)).toEqual(DRAWN_LABELS);
    });

    it("renders exactly what it renders today — 269% is the honest answer on a non-race board", () => {
      expect(valueCells(markup)).toEqual(["60%", "41%", "1%", "<1%"]);
    });
  });

  describe("the closed gate: no field_is_a_race key at all", () => {
    const markup = render(brazilCard(undefined));

    it("reaches the leaderboard, so the assertion below is not green by absence", () => {
      expect(markup).toContain('data-card-format="leaderboard"');
      expect(renderedLabels(markup)).toEqual(DRAWN_LABELS);
    });

    it("renders exactly what it renders today", () => {
      // Deliberately NOT #7844's `!== false` default. A payload that has not said
      // the field is exclusive has not earned a derived row.
      expect(valueCells(markup)).toEqual(["60%", "41%", "1%", "<1%"]);
    });
  });

  // ───────────────────────────────────────────────────────────────────────────
  describe("renderedRaceBoardPercents — the refusals, one clause at a time", () => {
    const BRAZIL = [0.5955, 0.405, 0.0075, 0.0015];

    it("repairs the pair and answers null for every row beneath it", () => {
      expect(renderedRaceBoardPercents(BRAZIL, true)).toEqual([60, 40, null, null]);
    });

    it("clause 1 — refuses a board that is not a race", () => {
      expect(renderedRaceBoardPercents(BRAZIL, false)).toEqual([null, null, null, null]);
    });

    it("clause 2 — refuses a top two that is not a complement pair", () => {
      // A coalition board: `0.675 + 0.54` is 1.215, so a slice cannot manufacture
      // a duel out of it (#2831).
      expect(renderedRaceBoardPercents([0.675, 0.54, 0.53], true)).toEqual([
        null,
        null,
        null,
      ]);
      // And the near miss: 1.02 is one point outside the band.
      expect(renderedRaceBoardPercents([0.52, 0.5], true)).toEqual([null, null]);
    });

    it("clause 2 — refuses a pair that PRINTS 101 off legs that really do sum to 101.8", () => {
      // 🔴 THE ONLY SPECIMEN THAT ISOLATES CLAUSE 2, and it is here because
      // dropping `isComplementPair` entirely SURVIVED the first mutation pass:
      // both cases above are refused by clause 5 before the band is ever
      // consulted, so they proved nothing about it.
      //
      // `0.604 / 0.414` rounds to 60 and 41 — printed sum 101, so clause 3 lets
      // it through, and the derived 40 is one point off 41, so clause 5 lets it
      // through too. Only the band refuses it, and refusing is right: those legs
      // sum to 1.018, so deriving 40 would absorb nearly two points of venue
      // over-round into one row. That is renormalization, not rounding (#7844).
      expect(renderedRaceBoardPercents([0.604, 0.414], true)).toEqual([null, null]);
    });

    it("clause 3 — refuses a pair that already prints 100 or less", () => {
      // 0.52/0.48 prints 52/48; 0.6/0.39 prints 60/39. Neither is a defect, and
      // normalizing the second would move the LEADER to 61.
      expect(renderedRaceBoardPercents([0.52, 0.48], true)).toEqual([null, null]);
      expect(renderedRaceBoardPercents([0.6, 0.39], true)).toEqual([null, null]);
    });

    it("clause 5 — refuses a repair that would move the row more than one point", () => {
      // `0.505 / 0.505` prints 51/51. Deriving 49 beneath a 51 would print two
      // different numbers for two identical legs.
      expect(renderedRaceBoardPercents([0.505, 0.505], true)).toEqual([null, null]);
    });

    it("clause 6 — refuses a list that is not leader-first", () => {
      // The caller slices leader-first; a caller that did not would have its
      // SECOND row anchored and its first derived.
      expect(renderedRaceBoardPercents([0.405, 0.5955], true)).toEqual([null, null]);
    });

    it("refuses anything shorter than a pair, and an unpriced leg", () => {
      expect(renderedRaceBoardPercents([0.9], true)).toEqual([null]);
      expect(renderedRaceBoardPercents([], true)).toEqual([]);
      expect(renderedRaceBoardPercents(null, true)).toEqual([]);
      expect(renderedRaceBoardPercents([0.5955, null, 0.4], true)).toEqual([
        null,
        null,
        null,
      ]);
    });

    it("the classic 93/8 pair is repaired to 93/7", () => {
      // `renderedCardPercents`' own worked example (`0.925 / 0.075`), which this
      // board could reach and previously could not repair.
      expect(renderedRaceBoardPercents([0.925, 0.075], true)).toEqual([93, 7]);
    });

    it("overrides the INTEGER and not UX-P046's rule", () => {
      // A derived `0` over a leg the market is actively pricing still prints
      // `<1%`, because `probabilityParts` runs its boundary rule on the
      // PROBABILITY. This is the composition the card depends on and the one a
      // string-valued override would have broken.
      const pair = renderedRaceBoardPercents([0.9995, 0.0055], true);
      expect(pair).toEqual([100, 0]);
      expect(formatProbabilityPercent(0.0055, { rendered: pair[1] })).toBe("<1%");
      expect(formatProbabilityPercent(0.9995, { rendered: pair[0] })).toBe(">99%");
    });
  });
});
