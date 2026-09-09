/**
 * #4355 — THE LEADERBOARD CARD'S RENDERED CONTRACT: 4 BARS + A REMAINDER ROW.
 *
 * `FuturesCard.tsx`'s `outcome_distribution` branch renders `leaderFirstSlice(
 * distributionRows, 4)` plus one "Field and remaining outcomes +N" row —
 * FOUR named rows, whatever the payload's `distribution_outcomes` length. The
 * backend caps `distribution_outcomes` at 8 (`_distribution_outcomes` takes
 * `outcomes[:8]`) and the card takes 4 of those; the two numbers are related by
 * nothing but coincidence, and until this file NOTHING asserted either.
 *
 * ═══ WHY A TEST AND NOT A SHRUG ═══
 *
 * It let a ship claim be wrong in a way that read as fine. #4226's PR body and
 * its cert body both said the six-model AI card becomes "a six-bar field". It
 * does not — it becomes four bars and a `+2`. The ship held (a two-rung ladder
 * at one meaningless value became the ranked field, and the 71.5% favourite is
 * on the card at rank 1 instead of missing from it), but the sentence
 * describing what a READER sees was written from the payload rather than from
 * the component, and the reviewer had to catch it by reading the component.
 * A number stated from the payload is not a statement about the screen.
 *
 * ═══ WHAT THIS FILE RENDERS, AND WHY THAT AND NOT THE LEAF ═══
 *
 * It renders `DiscoverCard` — the wrapper — not `FuturesCard`. That is
 * deliberate and it is the half a leaf test cannot reach. `DiscoverCard.tsx`
 * carries its OWN fork for this format:
 *
 *     item.type === "futures"
 *       && discover_card?.suggested_format === "outcome_distribution"
 *       && top_outcomes?.length >= 4            <-- a DIFFERENT array
 *         ? <ComparisonCard/>                   <-- 4 rows, NO remainder row
 *         : <FuturesCard/>                      <-- the leaderboard below
 *
 * The wrapper gates on `top_outcomes.length`; the leaf gates on
 * `distribution_outcomes.length`. So which component a reader meets is decided
 * by an array that is not the one the leaderboard draws. Measured on the live
 * payload (`GET /api/feed?limit=250`, edition 7fc4a0ded4c1ff60, 2026-09-09):
 * all 50 `outcome_distribution` cards arrive with `top_outcomes` length 3, so
 * every one of them takes the leaderboard branch and the ComparisonCard fork is
 * live code that never fires. It COULD fire — `routes/feed.py` slices
 * `top_outcomes` at `[:5]`, not at 3 — which is exactly why the fork is pinned
 * below rather than left to be discovered by a reader. A test that rendered
 * `FuturesCard` directly would assert the leaderboard contract while saying
 * nothing about whether a reader ever arrives there.
 *
 * ⚠️ EVERY ASSERTION OF ABSENCE HERE IS PAIRED WITH A POSITIVE. A card that
 * rendered nothing at all passes `not.toContain(...)`, and an empty render
 * reads exactly like a clean pass. So the row count is asserted as an EXACT
 * number, the path is asserted by its `data-card-format` marker (the CERT-678
 * repair, which exists so a render-path test can prove which of the four
 * `<article>` roots it reached), and the ComparisonCard arm asserts the
 * comparison marker is PRESENT as well as the remainder row being absent.
 *
 * Fixtures are production payloads, copied rather than invented — see each one.
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

// ── fixtures ────────────────────────────────────────────────────────────────

type Row = { label: string; probability: number; movement: number | null };

/**
 * THE #4226 SPECIMEN, verbatim from production.
 *
 * `futures_markets` id 60481294, "Top AI model in September?", six outcomes,
 * classified `outcome_distribution` by the post-#4226 parser (before the fix it
 * was a `threshold_heatmap` with two rungs both at 4.0, scored off the version
 * separators in `Claude Opus 4-6 Thinking` and `Claude Opus 4-7`, and the 71.5%
 * favourite had no rung at all).
 *
 * 🔴 NOTE THE ORDER — IT IS NOT SORTED, AND THAT IS THE PRODUCTION ORDER.
 * Position 2 carries 0.025 and position 3 carries 0.035. A plain
 * `slice(0, 4)` would print those two in payload order and label them
 * "Rank 3" and "Rank 4" the wrong way round. `leaderFirstSlice` (#1526) sorts
 * before truncating, so the assertions below pin the SORTED result. This is
 * why the fixture was copied and not tidied: a tidied fixture would have
 * removed the only thing in it that tests the sort.
 */
const AI_MODEL_ROWS: Row[] = [
  { label: "Claude Fable 5.1 Max", probability: 0.715, movement: null },
  { label: "Claude Opus 5 Max", probability: 0.075, movement: null },
  { label: "Claude Opus 5 High", probability: 0.025, movement: null },
  { label: "Claude Opus 4-6 Thinking", probability: 0.035, movement: null },
  { label: "Claude Opus 4-7", probability: 0.01, movement: null },
  { label: "Claude Fable 5", probability: 0.01, movement: null },
];

/**
 * The card the issue photographed: "MLB World Series Winner" at 390px, four
 * named teams over `Field and remaining outcomes +26`. `futures_markets` id 1,
 * 30 outcomes, `distribution_outcomes` capped at 8 by the backend and
 * `remaining_outcome_count` 22 — so the rendered remainder is
 * `22 + (8 - 4) = 26`, and the four rows the payload sends but the card does
 * NOT draw are folded into it. That second term is the one a payload-only
 * reading misses.
 */
const MLB_ROWS: Row[] = [
  { label: "Los Angeles Dodgers", probability: 0.306359, movement: 0.003203 },
  { label: "Milwaukee Brewers", probability: 0.105644, movement: 0.000666 },
  { label: "New York Yankees", probability: 0.096184, movement: 0.001643 },
  { label: "Tampa Bay Rays", probability: 0.076, movement: 0.000512 },
  { label: "Atlanta Braves", probability: 0.061367, movement: -0.001594 },
  { label: "Philadelphia Phillies", probability: 0.058741, movement: -0.002067 },
  { label: "Boston Red Sox", probability: 0.054833, movement: 0.000373 },
  { label: "Chicago Cubs", probability: 0.048753, movement: null },
];

/**
 * `topOutcomeCount` is the wrapper's fork input and is set INDEPENDENTLY of the
 * distribution rows, because production sets them independently: every live
 * `outcome_distribution` card sends 3 top outcomes and up to 8 distribution
 * rows.
 */
function futuresItem(opts: {
  id: number;
  name: string;
  rows: Row[];
  remaining: number;
  topOutcomeCount: number;
}): FeedItem {
  const top = opts.rows.slice(0, opts.topOutcomeCount).map((r, i) => ({
    id: i + 1,
    name: r.label,
    probability: r.probability,
    movement: r.movement,
  }));
  return {
    type: "futures",
    score: 90,
    reason: "",
    headline: "",
    data: {
      id: opts.id,
      name: opts.name,
      llm_sport_category: "tech",
      sport_name: "Tech & Science",
      resolution_date: "2026-09-30T00:00:00Z",
      top_outcomes: top,
      outcome_count: opts.rows.length,
      confidence_tier: "moderate",
      discover_card: {
        suggested_format: "outcome_distribution",
        distribution_outcomes: opts.rows,
        remaining_outcome_count: opts.remaining,
      },
    } as unknown as FeedFuturesData,
  } as unknown as FeedItem;
}

function render(item: FeedItem): string {
  return renderToStaticMarkup(
    <DiscoverCard groupedItem={{ type: "item", item } as unknown as DiscoverGroupedItem} />
  );
}

/**
 * The named outcome rows, counted by the per-row rank marker.
 *
 * `aria-label="Rank N"` is on the rank cell of every NAMED row and on no other
 * element — the remainder row prints `shownRows.length + 1` in a bare `<span>`
 * with no aria-label. So this counts exactly the bars and never the remainder,
 * which is the distinction the whole file is about.
 */
function namedRowRanks(markup: string): number[] {
  return [...markup.matchAll(/aria-label="Rank (\d+)"/g)].map((m) => Number(m[1]));
}

/** Row labels in rendered order, read off the `title` attribute each row carries. */
function renderedLabels(markup: string, candidates: string[]): string[] {
  return candidates
    .map((label) => ({ label, at: markup.indexOf(`title="${label}"`) }))
    .filter((x) => x.at !== -1)
    .sort((a, b) => a.at - b.at)
    .map((x) => x.label);
}

// ─────────────────────────────────────────────────────────────────────────────
describe("#4355 — the leaderboard card renders 4 bars and one remainder row", () => {
  const aiCard = futuresItem({
    id: 60481294,
    name: "Top AI model in September?",
    rows: AI_MODEL_ROWS,
    remaining: 0,
    topOutcomeCount: 3, // what production sends
  });

  it("reaches the leaderboard render path, and says so with its marker", () => {
    const markup = render(aiCard);
    // The path, not the output. Without this a fixture that fell through to
    // Variant A would satisfy every other assertion in this file by accident.
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(markup).not.toContain('data-card-format="comparison"');
  });

  it("draws exactly FOUR named rows from a six-outcome field — not six", () => {
    const markup = render(aiCard);
    // The literal claim #4226 got wrong. Asserted as an exact count, and as the
    // exact rank sequence, so neither a dropped row nor a fifth one passes.
    expect(namedRowRanks(markup)).toEqual([1, 2, 3, 4]);
  });

  it("folds the two undrawn outcomes into a remainder row reading +2", () => {
    const markup = render(aiCard);
    expect(markup).toContain("Field and remaining outcomes");
    expect(markup).toContain("+2");
    // remaining_outcome_count is 0 here, so the +2 can ONLY have come from the
    // `distributionRows.length - shownRows.length` term — the term a
    // payload-only reading of this card misses.
    expect(markup).toContain(">5</span>"); // the remainder row's rank cell, 4 + 1
  });

  it("puts the leader in row 1 (#1526) and SORTS before slicing", () => {
    const markup = render(aiCard);
    const order = renderedLabels(
      markup,
      AI_MODEL_ROWS.map((r) => r.label)
    );
    // 0.715, 0.075, 0.035, 0.025 — note the last two are the pair the payload
    // sends in the wrong order. Both 0.01 rows fall into the remainder.
    expect(order).toEqual([
      "Claude Fable 5.1 Max",
      "Claude Opus 5 Max",
      "Claude Opus 4-6 Thinking",
      "Claude Opus 5 High",
    ]);
    expect(markup).not.toContain('title="Claude Opus 4-7"');
    expect(markup).not.toContain('title="Claude Fable 5"');
  });

  it("adds the undrawn payload rows to remaining_outcome_count (MLB: 22 -> +26)", () => {
    const markup = render(
      futuresItem({
        id: 1,
        name: "MLB World Series Winner",
        rows: MLB_ROWS,
        remaining: 22,
        topOutcomeCount: 3,
      })
    );
    expect(markup).toContain('data-card-format="leaderboard"');
    expect(namedRowRanks(markup)).toEqual([1, 2, 3, 4]);
    // The photographed number. 22 from the backend + 4 sent-but-undrawn rows.
    expect(markup).toContain("+26");
    expect(markup).not.toContain("+22");
    expect(markup).toContain('title="Los Angeles Dodgers"');
    expect(markup).not.toContain('title="Atlanta Braves"'); // row 5 of 8
  });

  /**
   * THE WRAPPER'S FORK, pinned so it cannot move silently.
   *
   * Dormant on every live card today (all 50 arrive with 3 top outcomes) but
   * reachable: `routes/feed.py` slices `top_outcomes` at `[:5]`. If a payload
   * ever carries 4, the SAME market stops being a leaderboard and becomes a
   * ComparisonCard — four rows and NO remainder row, so the reader silently
   * loses the "+N" that tells them the field is bigger than the card.
   *
   * This is not an assertion that the fork is right. It is an assertion that it
   * exists and that changing it is a decision somebody makes on purpose.
   */
  it("routes the same market to ComparisonCard when top_outcomes reaches 4", () => {
    const markup = render(
      futuresItem({
        id: 60481294,
        name: "Top AI model in September?",
        rows: AI_MODEL_ROWS,
        remaining: 0,
        topOutcomeCount: 4, // the only change from the first test
      })
    );
    // Positive first: prove something rendered and prove WHICH path.
    expect(markup).toContain('data-card-format="comparison"');
    expect(markup).not.toContain('data-card-format="leaderboard"');
    // ...and only then the absence that is the point.
    expect(markup).not.toContain("Field and remaining outcomes");
  });

  /**
   * CONTROL — passes both before and after any plausible change to the slice
   * width, and fails if the leaderboard branch stops gating on 4.
   *
   * Three distribution rows is below `distributionRows.length >= 4`, so this
   * card must NOT be a leaderboard. Without this arm, a widening that let the
   * leaderboard render 3-row fields would leave every assertion above green.
   */
  it("does not render a leaderboard for a field of three", () => {
    const markup = render(
      futuresItem({
        id: 999,
        name: "A three-horse field",
        rows: AI_MODEL_ROWS.slice(0, 3),
        remaining: 0,
        topOutcomeCount: 3,
      })
    );
    expect(markup).not.toContain('data-card-format="leaderboard"');
    expect(markup).not.toContain("Field and remaining outcomes");
    // Paired positive: the card still rendered, it just took another path.
    expect(markup).toContain("A three-horse field");
  });
});
