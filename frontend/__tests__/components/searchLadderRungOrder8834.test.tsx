/**
 * #8834 — searching "fed rate" shows where each meeting's rate is expected to land.
 *
 * latency's PR #8839 (C1) made `/api/events/search` serve a threshold ladder's
 * `top_outcomes` as the five rungs around its crossing, IN THRESHOLD ORDER.
 * Two web renderers then undid it (C2, C3 on the issue):
 *
 *   C2  `FuturesCard` re-sorted the five by probability, so near-tied rungs
 *       swapped — 109947 prices `Above 3.75%` 0.995 over `Above 3.50%` 0.99.
 *   C3  a `SearchFamilyCard` row printed the FIRST rung, `Above 3.50% 99%`,
 *       true and empty, when `Above 4.00% 63%` is the answer.
 *
 * THE FIXTURE IS THE SERVED WINDOW for Kalshi 109947 (`Fed funds rate after Oct
 * 2026 meeting?`) as #8839's own specimen test pins it, prices verbatim.
 * CONTROLS: an entity field keeps leader-first order and its top-row leader.
 */

import { renderToStaticMarkup } from "react-dom/server";
import FuturesCard from "@/components/FuturesCard";
import SearchFamilyCard from "@/components/SearchFamilyCard";
import { leaderOutcome } from "@/components/searchFamilyDisplay";
import { answerRung, inThresholdOrder, ladderSlice } from "@/lib/discover/leaderOrder";
import type { FuturesFamily, FuturesMarket, FuturesOutcome } from "@/lib/types";

function outcome(id: number, name: string, probability: number | null): FuturesOutcome {
  return {
    id,
    name,
    probability,
    american_odds: null,
    rank: null,
    rank_change_24h: null,
    probability_change_24h: null,
    movement: null,
    opening_probability: null,
    opening_american_odds: null,
    is_winner: null,
    last_updated: null,
  } as unknown as FuturesOutcome;
}

/** 109947's window, in the threshold order #8839 serves it. */
const SERVED_WINDOW = [
  outcome(1601949, "Above 3.50%", 0.99),
  outcome(1601950, "Above 3.75%", 0.995),
  outcome(1601951, "Above 4.00%", 0.625),
  outcome(1601955, "Above 4.25%", 0.015),
  outcome(1601956, "Above 4.50%", 0.02),
];
const THRESHOLD_ORDER = ["Above 3.50%", "Above 3.75%", "Above 4.00%", "Above 4.25%", "Above 4.50%"];

const FIELD = [
  outcome(1, "Kevin Hassett", 0.18),
  outcome(2, "Kevin Warsh", 0.62),
  outcome(3, "Christopher Waller", 0.12),
];

function market(name: string, top: FuturesOutcome[], id = 109947): FuturesMarket {
  return {
    id,
    name,
    description: null,
    source: "kalshi",
    category: null,
    sport: null,
    sport_name: null,
    llm_sport_category: "economics",
    external_id: null,
    mutually_exclusive: false,
    commence_time: null,
    resolution_date: null,
    outcome_count: top.length,
    created_at: null,
    updated_at: null,
    status: "open",
    top_outcomes: top,
  } as unknown as FuturesMarket;
}

function labels(html: string): string[] {
  const found = [...html.matchAll(/data-outcome-label[^>]*>([^<]*)</g)].map((m) => m[1]);
  if (found.length === 0) throw new Error("no data-outcome-label spans — extractor blind");
  return found;
}

/** Labels drawn with the leader emphasis (`font-medium text-text-primary`). */
function highlighted(html: string): string[] {
  const spans = [...html.matchAll(/<span([^>]*data-outcome-label[^>]*)>([^<]*)</g)];
  if (spans.length === 0) throw new Error("no data-outcome-label spans — extractor blind");
  return spans
    .filter(([, attrs]) => /class="[^"]*\bfont-medium\b/.test(attrs))
    .map(([, , label]) => label);
}

const renderCard = (m: FuturesMarket) => renderToStaticMarkup(<FuturesCard market={m} />);

describe("C2 — FuturesCard keeps a ladder's served order", () => {
  const html = renderCard(market("Fed funds rate after Oct 2026 meeting?", SERVED_WINDOW));

  test("the rungs render in threshold order, the near-tie not swapped", () => {
    expect(labels(html)).toEqual(THRESHOLD_ORDER);
  });

  test("the highlighted rung is the one nearest even, and it is the only one", () => {
    expect(highlighted(html)).toEqual(["Above 4.00%"]);
  });

  test("control: an entity field is still drawn leader-first with the top row highlighted", () => {
    const field = renderCard(market("Next Fed chair?", FIELD, 1));
    expect(labels(field)).toEqual(["Kevin Warsh", "Kevin Hassett", "Christopher Waller"]);
    expect(highlighted(field)).toEqual(["Kevin Warsh"]);
  });
});

describe("inThresholdOrder — the gate that lets a card trust served order", () => {
  test("109947's served window passes, up or down", () => {
    expect(inThresholdOrder(THRESHOLD_ORDER)).toBe(true);
    expect(inThresholdOrder([...THRESHOLD_ORDER].reverse())).toBe(true);
    expect(inThresholdOrder(["24,400 or above", "24,200 or above", "24,000 or above"])).toBe(true);
  });

  test("the #2789 specimen (two name shapes) fails — it is not a ladder", () => {
    expect(inThresholdOrder(["Set 2 Winner", "Set 1 O/U 8.5", "Set 1 Winner"])).toBe(false);
    // Numbers that DO run in order must not rescue a mixed list: only the shape
    // clause can refuse this one.
    expect(inThresholdOrder(["Set 1 Winner", "Set 2 O/U 8.5", "Set 3 Winner"])).toBe(false);
  });

  test("a ladder served out of order fails, including a probability sort's near-tie swap", () => {
    expect(inThresholdOrder(["Above 3.75%", "Above 3.50%", "Above 4.00%"])).toBe(false);
    expect(inThresholdOrder(["Above 4.00%", "Above 5.25%", "Above 4.75%"])).toBe(false);
  });

  test("repeated values, entity names and a single row all fail", () => {
    expect(inThresholdOrder(["Above 4.00%", "Above 4.00%"])).toBe(false);
    expect(inThresholdOrder(["Kevin Warsh", "Kevin Hassett"])).toBe(false);
    expect(inThresholdOrder(["Above 4.00%"])).toBe(false);
  });

  test("the card sorts a ladder served out of order leader-first, as before", () => {
    const scrambled = [SERVED_WINDOW[1], SERVED_WINDOW[0], SERVED_WINDOW[2]];
    const html = renderCard(market("Fed funds rate after Oct 2026 meeting?", scrambled));
    expect(labels(html)).toEqual(["Above 3.75%", "Above 3.50%", "Above 4.00%"]);
    expect(highlighted(html)).toEqual(["Above 3.75%"]);
  });
});

describe("ladderSlice — order from the input, membership from leaderFirstSlice", () => {
  test("a probability-sorted payload comes back unchanged", () => {
    const sorted = [...SERVED_WINDOW].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0));
    expect(ladderSlice(sorted, 5)).toEqual(sorted);
  });

  test("with more rows than slots the maximum-probability row survives (#1526)", () => {
    const rows = [
      outcome(1, "Above 5.00%", 0.01),
      outcome(2, "Above 4.75%", 0.01),
      outcome(3, "Above 4.50%", 0.02),
      outcome(4, "Above 4.25%", 0.015),
      outcome(5, "Above 4.00%", 0.625),
      outcome(6, "Above 3.75%", 0.995),
    ];
    const out = ladderSlice(rows, 3).map((o) => o.name);
    expect(out).toContain("Above 3.75%");
    expect(out).toEqual(["Above 4.50%", "Above 4.00%", "Above 3.75%"]);
  });
});

describe("answerRung", () => {
  test("a ladder answers with its rung nearest even", () => {
    expect(answerRung(SERVED_WINDOW)?.name).toBe("Above 4.00%");
  });

  test("an exclusive field answers with its leader, above and below even", () => {
    expect(answerRung(FIELD)?.name).toBe("Kevin Warsh");
    expect(
      answerRung([outcome(1, "A", 0.2), outcome(2, "B", 0.45), outcome(3, "C", 0.35)])?.name,
    ).toBe("B");
  });

  test("a tie in distance goes to the higher probability", () => {
    expect(answerRung([outcome(1, "Under", 0.25), outcome(2, "Over", 0.75)])?.name).toBe("Over");
  });

  test("unpriced rows are never the answer", () => {
    expect(answerRung([outcome(1, "A", null), outcome(2, "B", 0.9)])?.name).toBe("B");
    expect(answerRung([outcome(1, "A", null)])).toBeNull();
  });
});

describe("C3 — a family row prints the ladder's answer rung", () => {
  const ladder = market("Fed funds rate after Oct 2026 meeting?", SERVED_WINDOW);

  test("leaderOutcome on a ladder is the rung nearest even, not the first", () => {
    expect(leaderOutcome(ladder)?.name).toBe("Above 4.00%");
  });

  test("control: a non-ladder row still prints the first served outcome", () => {
    // Deliberately NOT leader-first here: the family row displays server order
    // as given, and this pins that the ladder rule did not turn into a sort.
    const m = market("Next Fed chair?", [FIELD[0], FIELD[1]], 1);
    expect(leaderOutcome(m)?.name).toBe("Kevin Hassett");
  });

  test("the rendered Fed & Rates card reads `Above 4.00% 63%` on the ladder row", () => {
    const family = {
      family_key: "topic:fed",
      label: "Fed & Rates",
      headline: market("Next Fed chair?", FIELD.slice(1, 2), 1),
      members: [ladder],
      more_count: 0,
      member_count: 2,
    } as unknown as FuturesFamily;
    const text = renderToStaticMarkup(<SearchFamilyCard family={family} />)
      .replace(/<[^>]*>/g, " ")
      .replace(/&gt;/g, ">")
      .replace(/\s+/g, " ");
    expect(text).toContain("Above 4.00% 63%");
    expect(text).not.toContain("Above 3.50%");
  });
});
