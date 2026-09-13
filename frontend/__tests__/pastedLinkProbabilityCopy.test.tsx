/**
 * CHECK 8's REMAINING HALF — A PASTED GAME OR MARKET LINK SAYS THE PROBABILITY.
 *
 * The route work (#5813 tournament, #5833 concept, #5840 dead link, #5846/#5888
 * pictures, #5912 team, and the category/bracket/sport/league cards) settled
 * WHICH card each link draws. This file is about the WORDS printed beside it,
 * which is the literal wording of check 8 and the half YOUR-TURN still carried
 * as open: "a pasted game/market link unfurls with plain probability copy".
 *
 * ═══ DEFECT A — THE MARKET HALF PRINTED AN ESSAY, NOT A PRICE ═══
 *
 * `app/futures/[id]/layout.tsx` read `hook_description ||` in front of its
 * probability sentence, so the hook won on every market that has one. Per
 * `/api/admin/hook-coverage` at 2026-09-13 15:28Z that is 10,997 of 15,560
 * tier-1-3 markets — 70.7%, and tier 1-3 is what anyone would paste.
 *
 * Measured on production 2026-09-13 15:31Z, `/futures/60276241`:
 *
 *   og:description  "As Texas braces for another scorching summer, the question
 *                    of rainfall in Dallas for September 2026 has become
 *                    increasingly pertinent, with shifts in climate patterns
 *                    raising conc..."
 *
 * No probability in it, and cut mid-word. The same minute, `/events/15297788`
 * served "Live now. Bain Luck gives Le Mans FC a 25% win probability and RC Lens
 * a 75% win probability." One half of the check passed and the other did not.
 *
 * ═══ DEFECT B — THE GAME HALF FLIPPED THE TEAMS MID-TITLE ═══
 *
 * Same specimen, same minute. `matchup` is AWAY vs HOME and the card draws away
 * on the left, but the percentage lists ran home-first:
 *
 *   og:title  "RC Lens vs Le Mans FC: Le Mans FC 25%, RC Lens 75%"
 *   og:image  RC Lens 75% on the LEFT, Le Mans FC 25% on the right
 *
 * Both numbers were correct and each sat with its own team. What failed is that
 * a reader cannot read the card straight through: 75% under the left crest, and
 * a sentence opening with the other team on 25%.
 *
 * ═══ WHY THE ASSERTIONS ARE SHAPED THE WAY THEY ARE ═══
 *
 * Ordering is asserted POSITIONALLY, never as a hardcoded sentence. A frozen
 * expected string is killed by any mutant, including mutants that are correct,
 * and says nothing about what the rule is. The pairing assertions exist because
 * there are two different wrong answers here and a string compare cannot tell
 * them apart: swapping the NAMES alone ("76ers 65%, Celtics 35%") reports the
 * wrong number for each team, which is worse than the defect being fixed.
 *
 * Both directions, per gotcha #43. Leading with the price must not delete the
 * hook: it still has to reach the CARD, where it is the grey line under the big
 * number and D102 says grey type belongs beside a figure it supports. A change
 * that dropped the hook everywhere would satisfy half this file.
 */

import React from "react";

const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import { renderToStaticMarkup } from "react-dom/server";
import { generateMetadata as futuresMetadata } from "@/app/futures/[id]/layout";
import FuturesOgImage from "@/app/futures/[id]/opengraph-image";
import { buildEventShareCopy } from "@/lib/eventShareMeta";
import { truncateShareText } from "@/lib/share";

/* ────────────────────────────── the harness ────────────────────────────── */

function respondWith(status: number, body: unknown = {}) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }) as unknown as typeof fetch;
}

const HOOK =
  "As Texas braces for another scorching summer, the question of rainfall in " +
  "Dallas for September 2026 has become increasingly pertinent, with shifts in " +
  "climate patterns raising concerns among residents and forecasters alike.";

/** The Dallas rain market, shaped as `/api/futures/{id}` serves it. */
function rainMarket(overrides: Record<string, unknown> = {}) {
  return {
    id: 60276241,
    name: "Rain in Dallas in Sep 2026?",
    status: "open",
    hook_description: HOOK,
    outcome_count: 7,
    outcomes: [
      { name: "Above 2 inches", probability: 0.21 },
      { name: "Above 1 inch", probability: 0.52 },
      { name: "Above 3 inches", probability: 0.09 },
      { name: "Above 4 inches", probability: 0.03 },
    ],
    ...overrides,
  };
}

async function futuresDescription(market: unknown): Promise<string> {
  respondWith(200, market);
  const meta = await futuresMetadata({ params: Promise.resolve({ id: "60276241" }) });
  return String(meta.description ?? "");
}

/**
 * What the card DRAWS, rendered.
 *
 * Rendered rather than walked: the futures card clamps its own strings, so the
 * text that reaches the canvas is not the text handed in, and a prop-based card
 * has no child text nodes for a walker to find at all (#5846's first cut).
 * Tags collapse to a space so adjacent spans do not weld into one word.
 */
function cardText(element: React.ReactElement): string {
  return renderToStaticMarkup(element).replace(/<[^>]*>/g, " ");
}

/** Assert `first` is printed before `second`, and that both are printed. */
function expectOrder(text: string, first: string, second: string) {
  const a = text.indexOf(first);
  const b = text.indexOf(second);
  expect(a).toBeGreaterThanOrEqual(0);
  expect(b).toBeGreaterThanOrEqual(0);
  expect(a).toBeLessThan(b);
}

beforeEach(() => {
  mockImageResponseCalls.length = 0;
});

/* ══════════════ DEFECT A — the market half states the board ══════════════ */

describe("a pasted market link states the price, not the essay", () => {
  it("leads with the leader and the leader's own percentage", async () => {
    const description = await futuresDescription(rainMarket());
    expect(description.startsWith("Above 1 inch 52%")).toBe(true);
  });

  it("names the chasers with their own percentages, in price order", async () => {
    const description = await futuresDescription(rainMarket());
    // Paired, not merely present: the defect this replaces reported no number at
    // all, and the plausible mutant reports the wrong one for each name.
    expect(description).toContain("Above 1 inch 52%");
    expect(description).toContain("Above 2 inches 21%");
    expect(description).toContain("Above 3 inches 9%");
    expectOrder(description, "Above 1 inch 52%", "Above 2 inches 21%");
    expectOrder(description, "Above 2 inches 21%", "Above 3 inches 9%");
  });

  it("stops at three names rather than reciting the whole board", async () => {
    const description = await futuresDescription(rainMarket());
    // 4th by price. A description that grows with the board is how a 40-outcome
    // market gets truncated back to saying nothing.
    expect(description).not.toContain("Above 4 inches");
  });

  it("does not print the hook, which is what used to win", async () => {
    const description = await futuresDescription(rainMarket());
    expect(description).not.toContain("As Texas braces");
    expect(description).not.toContain("scorching");
  });

  it("is not cut mid-word", async () => {
    const description = await futuresDescription(rainMarket());
    // "raising conc..." was the shipped defect. A truncated description must end
    // on a whole word; an untruncated one must not claim to be truncated.
    if (description.endsWith("...")) {
      expect(description.slice(0, -3)).toMatch(/\w$|[.?!]$/);
    }
    expect(description).not.toMatch(/\bconc\.\.\./);
  });

  it("still says who WON once the market resolves, with no percentage", async () => {
    const description = await futuresDescription(
      rainMarket({
        status: "resolved",
        outcomes: [
          { name: "Above 1 inch", probability: 1, is_winner: true },
          { name: "Above 2 inches", probability: 0 },
        ],
      }),
    );
    // Settled means settled: the board sentence must not reach this branch and
    // re-publish a price on a decided question.
    expect(description).toContain("Above 1 inch won");
    expect(description).not.toMatch(/\d+%/);
  });

  it("falls back to the plain sentence when the board is empty", async () => {
    const description = await futuresDescription(rainMarket({ outcomes: [] }));
    expect(description).toContain("Rain in Dallas in Sep 2026?");
    expect(description).not.toContain("As Texas braces");
  });

  it("drops an unpriced chaser rather than printing it as 0%", async () => {
    const description = await futuresDescription(
      rainMarket({
        outcomes: [
          { name: "Above 1 inch", probability: 0.52 },
          { name: "Unpriced Name", probability: null },
          { name: "Above 2 inches", probability: 0.21 },
        ],
      }),
    );
    expect(description).toContain("Above 2 inches 21%");
    expect(description).not.toContain("Unpriced Name");
  });

  // ── the other direction (gotcha #43) ──
  it("keeps the hook on the CARD, where it is the line under the number", async () => {
    respondWith(200, rainMarket());
    // Plain object, NOT a promise: the card route's `params` is unwrapped
    // (`{ params: { id: string } }`) while the layout's `generateMetadata` takes
    // `Promise<{ id }>`. Handing a promise here makes `params.id` undefined, which
    // parses to NaN and draws the DEAD-LINK card — a green-looking harness that
    // tests the wrong branch. `shareCardDuelPair4963` already calls it this way.
    await FuturesOgImage({ params: { id: "60276241" } });
    expect(mockImageResponseCalls).toHaveLength(1);
    const drawn = cardText(mockImageResponseCalls[0]);
    expect(drawn).toContain("As Texas braces");
    // And the card still carries the figure the hook is supporting.
    expect(drawn).toContain("52%");
  });
});

/* ═════════ DEFECT B — one order across matchup, copy and picture ═════════ */

describe("a pasted game link reads in one order", () => {
  const unsettled = {
    home_team: "Celtics",
    away_team: "76ers",
    status: "scheduled",
    commence_time: "2026-09-02T23:00:00Z",
    hero_probability_source: "blend",
    current_odds: { home_probability: 0.65, away_probability: 0.35 },
  };

  it("lists the away side first in the title, matching 'AWAY vs HOME'", () => {
    const { title } = buildEventShareCopy(unsettled);
    expectOrder(title, "76ers vs Celtics", "76ers 35%");
    expectOrder(title, "76ers 35%", "Celtics 65%");
  });

  it("lists the away side first in the description too", () => {
    const { description } = buildEventShareCopy(unsettled);
    expectOrder(description, "76ers a 35%", "Celtics a 65%");
  });

  it("keeps each percentage with its OWN team", () => {
    // The mutant this kills: swapping the two names and leaving the numbers,
    // which orders the sentence correctly and reports both teams wrong.
    const { title, description } = buildEventShareCopy(unsettled);
    expect(title).toContain("76ers 35%");
    expect(title).toContain("Celtics 65%");
    expect(title).not.toContain("76ers 65%");
    expect(title).not.toContain("Celtics 35%");
    expect(description).toContain("76ers a 35% win probability");
    expect(description).toContain("Celtics a 65% win probability");
  });

  it("holds for a live game, which is the one most likely to be pasted", () => {
    const { title, description } = buildEventShareCopy({ ...unsettled, status: "live" });
    expectOrder(title, "76ers 35%", "Celtics 65%");
    expect(description.startsWith("Live now.")).toBe(true);
    expectOrder(description, "76ers a 35%", "Celtics a 65%");
  });

  it("leaves the settled wording alone — it names a winner, not a side", () => {
    const { title, description } = buildEventShareCopy({
      ...unsettled,
      status: "completed",
      hero_probability_source: "settled",
      hero_settled_result: "home",
      home_score: 110,
      away_score: 104,
    });
    expect(title).toBe("76ers vs Celtics: Celtics won 110-104");
    expect(description).toBe("Final: Celtics beat 76ers 110-104.");
  });
});

/* ═════════════════ the shared cut, which both halves use ════════════════ */

describe("truncateShareText cuts at a word boundary", () => {
  it("does not leave half a word before the ellipsis", () => {
    const out = truncateShareText(HOOK);
    expect(out.endsWith("...")).toBe(true);
    expect(out).not.toContain("conc...");
    expect(out.slice(0, -3)).toMatch(/\w$/);
    // The whole word before the cut survives intact.
    expect(HOOK).toContain(out.slice(0, -3));
  });

  it("keeps the ceiling callers have been pinned to since #4149", () => {
    expect(truncateShareText(HOOK).length).toBeLessThanOrEqual(182);
  });

  it("returns short text untouched, with no ellipsis", () => {
    expect(truncateShareText("Above 1 inch 52%.")).toBe("Above 1 inch 52%.");
  });

  it("still cuts a single monstrous token rather than collapsing to nothing", () => {
    // `tournamentShareMeta`'s own guard feeds a 400-character display name. A
    // boundary search with no floor rewinds past every real word before it.
    const monstrous = `US Open 2026: ${"X".repeat(400)} leads at 40%.`;
    const out = truncateShareText(monstrous);
    expect(out.length).toBeGreaterThan(90);
    expect(out.length).toBeLessThanOrEqual(182);
  });
});
