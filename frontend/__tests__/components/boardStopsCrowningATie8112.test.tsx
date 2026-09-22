/**
 * #8112 — A RACE BOARD STOPS CROWNING A DEAD HEAT.
 *
 * 🔴 THE READER. Production `https://bainluck.com/`, 390px, 2026-09-22 23:2xZ
 * (`artifacts-discover/d422/disc-1600.png`), market 52755659 off
 * `GET /api/feed?limit=40`, `price_observed_at 2026-09-22T22:51:25Z`:
 *
 *     HOCKEY · Resolves Jul 1, 2027
 *     2026-27 Stanley Cup® Finals Winner
 *     Colorado Avalanche at 10%
 *      1  Colorado Avalanche    ─────  10%   ← bold, brand-green bar
 *      2  Florida Panthers      ─────  10%   ← semibold, muted grey bar
 *      3  Carolina Hurricanes   ────    8%
 *      4  Edmonton Oilers       ────    7%
 *      5  Field and 28 more outcomes
 *
 * Colorado and Florida are priced at `0.1031` each — identical, not merely
 * close — and both print 10%. One of them was given every mark this card has
 * for "favourite": the rank digit 1, `font-bold`, and the `bg-accent-brand`
 * bar. Which one was decided by nothing: `leaderFirstSlice` is a STABLE sort,
 * so the podium went to whichever club the payload happened to list first.
 *
 * ═══ THE RULE EXISTED AND WAS WIRED TO THE COPY, NOT THE PAINT ═══
 *
 * #6187 is the same card, the same market and the same tie — its title is "A
 * futures card says 'Florida Panthers leads at 10%' above a board where the
 * runner-up also reads 10%". It shipped `lead_is_printable`
 * (`app/utils/feed_reasons.py:1997`), which asks whether "a reader checking the
 * board can see the lead the sentence asserts", and the backend obeys it: this
 * card's served headline is `Colorado Avalanche at 10%`, with no comparative,
 * while its four siblings in the same edition all clear the gate and all say
 * "leads". The SENTENCE already refuses the claim the BOARD then makes in bold
 * and brand green. This ship asks #6187's question of the chrome.
 *
 * ═══ THE CONTROL EXERCISES THE OPPOSITE BRANCH ═══
 *
 * Every arm below is run twice against ONE fixture that differs in ONE number:
 * Florida at `0.1031` (prints 10%, tied) and Florida at `0.0931` (prints 9%,
 * beaten). Not two specimens on the same side of the gate — the second is the
 * branch the change must leave alone, and it is what fails if the tie test ever
 * over-fires and stops crowning boards that DO have a leader.
 *
 * Both directions are therefore covered by construction: delete the tie test
 * and the tied arm reds (two crowns collapse to one); widen it and the beaten
 * arm reds (one crown becomes two).
 *
 * ⚠️ EVERY ABSENCE IS PAIRED WITH A POSITIVE. An empty render satisfies a
 * "nothing is crowned" assertion for free, so each arm also asserts the four
 * club names, the four percentages and the remainder sentence are all still on
 * the card. A reader loses an arbitrary podium and keeps every number.
 *
 * ═══ BOTH CARDS, BECAUSE THERE IS ONE BOARD (#8025, notice 35) ═══
 *
 * `FuturesCard` (/discover) draws the podium with rank digits; `FeedCard`
 * (/sports, /categories/*, /my-stuff) draws its own compact row with no digit,
 * so there the weight and the bar colour are the only two marks. Both read the
 * same `futuresDistributionBoard`, and before this ship both crowned off a bare
 * index.
 *
 * NOT COVERED, stated so this file cannot be read as proving more than it does:
 * `FeedCard`'s OTHER outcome list — the `top_outcomes` fallback reached by cards
 * that earn no distribution board — still crowns `i === 0`. It is a different
 * list with a different printed value and is named as the remainder in #8112.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

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
import { FuturesCard } from "../../components/discover/FuturesCard";

// ── the fixture, copied verbatim from the served edition ────────────────────

const COLORADO = "Colorado Avalanche";
const FLORIDA = "Florida Panthers";
const CAROLINA = "Carolina Hurricanes";
const EDMONTON = "Edmonton Oilers";

/**
 * All eight rows `discover_card.distribution_outcomes` served, kept rather than
 * trimmed to the four that draw: `remaining_outcome_count` is 24 and the
 * rendered remainder is `24 + (8 - 4) = 28`, which is where the photographed
 * "Field and 28 more outcomes" comes from. The second term is the one a
 * hand-built fixture gets wrong (#6586).
 *
 * `floridaProbability` is the ONE number that moves between the two arms.
 */
function stanleyCupBoard(floridaProbability: number) {
  return [
    { label: COLORADO, probability: 0.1031, movement: null },
    { label: FLORIDA, probability: floridaProbability, movement: null },
    { label: CAROLINA, probability: 0.0762, movement: null },
    { label: EDMONTON, probability: 0.0673, movement: null },
    { label: "Vegas Golden Knights", probability: 0.0583, movement: null },
    { label: "Minnesota Wild", probability: 0.0538, movement: null },
    { label: "Washington Capitals", probability: 0.0493, movement: null },
    { label: "Tampa Bay Lightning", probability: 0.0493, movement: null },
  ];
}

/** The three the route serves as `top_outcomes`, with their real ids. */
function stanleyCupTopOutcomes(floridaProbability: number) {
  return [
    { id: 198632537, rank: 1, name: COLORADO, probability: 0.1031, movement: null },
    { id: 198632536, rank: 2, name: FLORIDA, probability: floridaProbability, movement: null },
    { id: 198632538, rank: 3, name: CAROLINA, probability: 0.0762, movement: null },
  ];
}

function stanleyCupData(floridaProbability: number): FeedFuturesData {
  return {
    id: 52755659,
    name: "2026-27 Stanley Cup® Finals Winner",
    llm_sport_category: "hockey",
    sport_name: null,
    status: "open",
    source: "kalshi",
    source_count: 2,
    market_tier: 1,
    confidence_tier: "moderate",
    resolution_date: "2027-07-01T14:00:00+00:00",
    outcome_count: 32,
    top_outcomes: stanleyCupTopOutcomes(floridaProbability),
    discover_card: {
      suggested_format: "outcome_distribution",
      distribution_outcomes: stanleyCupBoard(floridaProbability),
      remaining_outcome_count: 24,
      field_is_a_race: true,
    },
  } as unknown as FeedFuturesData;
}

function itemFor(data: FeedFuturesData): FeedItem {
  return {
    type: "futures",
    score: 93,
    // The served copy, which already refuses the comparative — quoted so this
    // file records that the caption and the chrome now agree.
    reason: `${COLORADO} (10%) in 2026-27 Stanley Cup® Finals Winner`,
    headline: `${COLORADO} at 10%`,
    data,
  } as unknown as FeedItem;
}

const discoverHtml = (data: FeedFuturesData) =>
  renderToStaticMarkup(
    <FuturesCard
      item={itemFor(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );

const browseHtml = (data: FeedFuturesData) =>
  renderToStaticMarkup(<FeedCard item={itemFor(data)} />);

// ── readers ─────────────────────────────────────────────────────────────────

/**
 * Is this row wearing the brand bar?
 *
 * Scoped to the row rather than counted across the card on purpose: both cards
 * use `bg-accent-brand` elsewhere (chips, links, the browse card's second
 * outcome list), so a document-wide count would be measuring the page. Each row
 * opens on `title="<label>"` and its bar follows inside the same container, so
 * the slice from one row's title to the next is exactly that row's markup.
 */
function rowIsCrowned(markup: string, label: string): boolean {
  const start = markup.indexOf(`title="${label}"`);
  if (start === -1) return false;
  const next = markup.indexOf('title="', start + 1);
  return markup.slice(start, next === -1 ? undefined : next).includes("bg-accent-brand");
}

/** Is this row's NAME in the heavier of the two weights the row template uses? */
function rowIsEmphasised(markup: string, label: string, heavy: string): boolean {
  const start = markup.indexOf(`title="${label}"`);
  if (start === -1) return false;
  const tagEnd = markup.indexOf(">", start);
  return markup.slice(start - 200, tagEnd).includes(heavy);
}

/** `aria-label="Rank N"` in render order — the Discover podium's digits. */
function renderedRanks(markup: string): number[] {
  return [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
}

/** The percentage column, in render order. */
function valueCells(markup: string): string[] {
  return [...markup.matchAll(/tabular-nums[^>]*>([^<]*)</g)]
    .map((m) => m[1])
    .filter((c) => c.endsWith("%"));
}

const DRAWN = [COLORADO, FLORIDA, CAROLINA, EDMONTON];

/** The live specimen: identical prices. */
const TIED = stanleyCupData(0.1031);
/**
 * The ROUNDED tie — a DIFFERENT probability that prints the same percent
 * (`0.0972` → 10%). This is the arm that makes the printed-string test
 * load-bearing rather than decorative: a tie test written on the raw
 * probability passes every assertion in the identical-price arm above and then
 * crowns this board, where a reader is looking at two cells both reading 10%.
 *
 * It is also #6187's own case. `lead_is_printable` compares the RENDERED
 * percents, so it refuses the caption here too — `10 > 10` is false whether the
 * ten came from `0.1031` or `0.0972`. The chrome now answers the question on
 * exactly the same terms as the copy.
 *
 * Added because a mutation run said so: severing the printed-string call to
 * `String(row.probability)` SURVIVED against the identical-price arm alone.
 */
const ROUNDED_TIE = stanleyCupData(0.0972);
/** The opposite branch: 0.0931 prints 9% and is visibly behind. */
const BEATEN = stanleyCupData(0.0931);

// ─────────────────────────────────────────────────────────────────────────────
describe("#8112 — the Discover podium", () => {
  describe("the tie arm: Colorado and Florida both print 10%", () => {
    const markup = discoverHtml(TIED);

    it("gives the rank digit 1 to BOTH level rows, and the next row the place it holds", () => {
      // Competition ranking. 1,1,3,4 — never 1,1,2,3, which would renumber the
      // tail and break the remainder row's `rows.length + 1`.
      expect(renderedRanks(markup)).toEqual([1, 1, 3, 4]);
    });

    it("crowns neither club over the other: both wear the brand bar", () => {
      expect(rowIsCrowned(markup, COLORADO)).toBe(true);
      expect(rowIsCrowned(markup, FLORIDA)).toBe(true);
      // ...and the rows that ARE behind still are not. Without this the arm
      // passes on a card that painted every bar green.
      expect(rowIsCrowned(markup, CAROLINA)).toBe(false);
      expect(rowIsCrowned(markup, EDMONTON)).toBe(false);
    });

    it("gives both level rows the same weight", () => {
      expect(rowIsEmphasised(markup, COLORADO, "font-bold")).toBe(true);
      expect(rowIsEmphasised(markup, FLORIDA, "font-bold")).toBe(true);
      expect(rowIsEmphasised(markup, CAROLINA, "font-bold")).toBe(false);
    });

    it("still prints every club, every number and the remainder", () => {
      DRAWN.forEach((label) => expect(markup).toContain(`title="${label}"`));
      expect(valueCells(markup)).toEqual(["10%", "10%", "8%", "7%"]);
      expect(markup).toContain("Field and 28 more outcomes");
    });
  });

  describe("the rounded-tie arm: Florida at 0.0972 also prints 10%", () => {
    const markup = discoverHtml(ROUNDED_TIE);

    it("reads the tie off what is PRINTED, not off the probability behind it", () => {
      // 0.1031 !== 0.0972, and it makes no difference: the reader is looking at
      // two cells that both say 10%.
      expect(valueCells(markup)).toEqual(["10%", "10%", "8%", "7%"]);
      expect(renderedRanks(markup)).toEqual([1, 1, 3, 4]);
      expect(rowIsCrowned(markup, COLORADO)).toBe(true);
      expect(rowIsCrowned(markup, FLORIDA)).toBe(true);
      expect(rowIsCrowned(markup, CAROLINA)).toBe(false);
    });

    it("carries to the browse card too", () => {
      const browse = browseHtml(ROUNDED_TIE);
      expect(rowIsCrowned(browse, COLORADO)).toBe(true);
      expect(rowIsCrowned(browse, FLORIDA)).toBe(true);
      expect(rowIsCrowned(browse, CAROLINA)).toBe(false);
    });
  });

  describe("the control arm: Florida at 0.0931 prints 9% and IS behind", () => {
    const markup = discoverHtml(BEATEN);

    it("still ranks 1,2,3,4 — the change does not reach a board with a leader", () => {
      expect(renderedRanks(markup)).toEqual([1, 2, 3, 4]);
    });

    it("crowns exactly the one row that is ahead", () => {
      expect(rowIsCrowned(markup, COLORADO)).toBe(true);
      expect(rowIsCrowned(markup, FLORIDA)).toBe(false);
      expect(rowIsEmphasised(markup, COLORADO, "font-bold")).toBe(true);
      expect(rowIsEmphasised(markup, FLORIDA, "font-bold")).toBe(false);
    });

    it("prints the moved number, so the arms are known to differ by it", () => {
      expect(valueCells(markup)).toEqual(["10%", "9%", "8%", "7%"]);
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("#8112 — the browse card draws the same verdict (#8025, notice 35)", () => {
  it("crowns both level rows on the tie", () => {
    const markup = browseHtml(TIED);
    expect(rowIsCrowned(markup, COLORADO)).toBe(true);
    expect(rowIsCrowned(markup, FLORIDA)).toBe(true);
    expect(rowIsCrowned(markup, CAROLINA)).toBe(false);
    // Paired positive: the board is really on the card.
    DRAWN.forEach((label) => expect(markup).toContain(`title="${label}"`));
    expect(markup).toContain("Field and 28 more outcomes");
  });

  it("crowns only the leader when there is one", () => {
    const markup = browseHtml(BEATEN);
    expect(rowIsCrowned(markup, COLORADO)).toBe(true);
    expect(rowIsCrowned(markup, FLORIDA)).toBe(false);
  });

  it("agrees with the Discover podium row for row, on both arms", () => {
    // The disagreement #8025 exists to end, asserted over the new mark.
    [TIED, BEATEN].forEach((data) => {
      const discover = discoverHtml(data);
      const browse = browseHtml(data);
      DRAWN.forEach((label) =>
        expect(rowIsCrowned(browse, label)).toBe(rowIsCrowned(discover, label)),
      );
    });
  });
});
