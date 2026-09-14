// A SETTLED MARKET'S PICTURE MUST NOT SAY "leads" — #6032, discover/067.
//
// Found while verifying the two links YOUR-TURN asks Alex to paste into a phone
// preview (check 8's last lane-payable item). On `/futures/60544511`, settled
// Sep 3, the text and the picture made opposite claims in the SAME preview
// (production 2026-09-13 23:59Z, confirmed again 00:05Z — ISR serves the stale
// body first, so an unfurl is always read twice):
//
//   og:description  "77° or above won (Temperature in New York City ...)"   ✅
//   og:image        96px "100%" over "77° or above leads at 100%
//                    — 10 outcomes tracked."                                 ❌
//
// Two of the three surfaces describing that state already had the rule —
// `futuresTitleText` (#883 L2-55) and `FuturesHero` (#883 L2-53, Alex ruling:
// "NO big percentage on a settled market"). The OG route had no settled branch
// at all, which is exactly why the logic now lives in a pure helper: that route
// is an edge-runtime `ImageResponse` and could not be unit-tested in place.
//
// 🔴 THE WORDING IS THE SMALLER HALF, and the `winner` describe-block below is
// the one that matters. The card featured the PRICE leader while the title
// features the GRADED winner. UX-P232 measured why those differ: settlement
// freezes every outcome at its last traded price, "routinely NOT the highest on
// the board". Its production case is "Arsenal vs Coventry: First Goalscorer",
// grading Kai Havertz at 21% while two players who did not score sit frozen at
// 99% — so the card drew a man who did not score, at 99%, over the word "leads".

import { futuresUnfurlCopy } from "@/lib/futuresDetailDisplay";

interface Outcome {
  name: string;
  probability: number | null;
  is_winner?: boolean | null;
}

/** Highest price first — what the OG route's own `topOutcome` computes. */
function priceLeader(outcomes: Outcome[]): Outcome | null {
  if (outcomes.length === 0) return null;
  return [...outcomes].sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))[0];
}

function copyFor(
  outcomes: Outcome[],
  status: string | null,
  extra: { hookDescription?: string | null; outcomeCount?: number | null } = {},
) {
  const leader = priceLeader(outcomes);
  return futuresUnfurlCopy({
    outcomes,
    leader,
    status,
    hookDescription: extra.hookDescription ?? null,
    outcomeCount: extra.outcomeCount ?? outcomes.length,
    probabilityLabel: leader?.probability != null ? `${Math.round(leader.probability * 100)}%` : "--",
  });
}

// The specimen, as production served it at 23:59Z: a cumulative temperature
// ladder where five thresholds are graded true and all five are frozen at 1.0.
const SPECIMEN: Outcome[] = [
  { name: "77° or above", probability: 1.0, is_winner: true },
  { name: "78° or above", probability: 1.0, is_winner: true },
  { name: "82° or above", probability: 1.0, is_winner: true },
  { name: "83° or above", probability: null, is_winner: false },
  { name: "86° or above", probability: null, is_winner: false },
];

// UX-P232's production case: the graded winner is NOT the price leader.
const FIRST_GOALSCORER: Outcome[] = [
  { name: "Player Who Did Not Score", probability: 0.99, is_winner: false },
  { name: "Second Player Who Did Not Score", probability: 0.99, is_winner: false },
  { name: "Kai Havertz", probability: 0.21, is_winner: true },
];

describe("the settled card never speaks in the present tense", () => {
  it("says the winner WON instead of leading — the reported defect", () => {
    const copy = copyFor(SPECIMEN, "resolved", { outcomeCount: 10 });

    expect(copy.subtitle).toBe("77° or above won — 10 outcomes tracked.");
    expect(copy.subtitle).not.toContain("leads");
  });

  it("prints no percentage anywhere in the settled copy (#883 L2-53)", () => {
    // The rule is about the PRICE, so assert no digit-percent survives at all
    // rather than spot-checking "100%": the frozen value differs per market and
    // an assertion naming one number would pass on every other settled card.
    const copy = copyFor(SPECIMEN, "resolved", { outcomeCount: 10 });
    expect(copy.subtitle).not.toMatch(/\d+%/);
    expect(copy.isResolved).toBe(true);
  });

  it("flags the card to drop its numeral and its bar", () => {
    // `isResolved` is what gates the 96px numeral and the probability bar in the
    // route. Without this the copy could be fixed while the picture still drew
    // "100%" in 96px type above it — which is the half a reader sees first.
    expect(copyFor(SPECIMEN, "resolved").isResolved).toBe(true);
    expect(copyFor(SPECIMEN, "open").isResolved).toBe(false);
  });
});

describe("the winner, not the frozen price leader (UX-P232)", () => {
  it("features the graded winner even at 21% against two losers at 99%", () => {
    const copy = copyFor(FIRST_GOALSCORER, "resolved");

    expect(copy.featuredName).toBe("Kai Havertz");
    expect(copy.settledWon).toBe(true);
    expect(copy.subtitle).toBe("Kai Havertz won — 3 outcomes tracked.");
  });

  it("never names a loser in the settled copy", () => {
    // The literal shape of the production defect: a man who did not score,
    // captioned as the story of the market.
    const copy = copyFor(FIRST_GOALSCORER, "resolved");
    expect(copy.subtitle).not.toContain("Did Not Score");
    expect(copy.featuredName).not.toContain("Did Not Score");
  });
});

describe("a fallback never crowns an ungraded row", () => {
  // `pickHeroOutcome` falls back to the price leader when nothing carries
  // `is_winner`, so "resolved" alone must not produce the word "won" — that is
  // the #6025/#6029 class (a result claimed from a settlement artifact).
  const UNGRADED: Outcome[] = [
    { name: "Alpha", probability: 0.99, is_winner: null },
    { name: "Beta", probability: 0.01, is_winner: null },
  ];

  it("says settled, not won, when no outcome is graded", () => {
    const copy = copyFor(UNGRADED, "resolved");

    expect(copy.settledWon).toBe(false);
    expect(copy.subtitle).toBe("This market has settled — 2 outcomes tracked.");
    expect(copy.subtitle).not.toContain("won");
    expect(copy.subtitle).not.toContain("leads");
  });

  it("does not let is_winner: false be read as a grade either", () => {
    const allLosers = UNGRADED.map((o) => ({ ...o, is_winner: false }));
    expect(copyFor(allLosers, "resolved").settledWon).toBe(false);
  });

  it("a stray is_winner on a LIVE market claims no result", () => {
    // The page's own rule: "`market.status`, never `is_winner` alone: a stray
    // flag must not make a live market claim a result." #6029 is the inverse
    // defect (status never flips) and is a DATA fix — not something this
    // renderer may paper over by inferring settlement from the flag.
    const copy = copyFor(
      [{ name: "Alpha", probability: 0.62, is_winner: true }],
      "open",
    );

    expect(copy.isResolved).toBe(false);
    expect(copy.settledWon).toBe(false);
    expect(copy.subtitle).toBe("Alpha leads at 62% — 1 outcomes tracked.");
  });
});

describe("THE CONTROL — the live card is untouched (gotcha #43)", () => {
  // Without these, a fix that simply hard-coded the settled sentence would pass
  // every assertion above and silence the probability copy on every OPEN market
  // — the 70.7% of tier-1-3 markets anyone actually pastes.
  const LIVE: Outcome[] = [
    { name: "Alpha", probability: 0.62, is_winner: null },
    { name: "Beta", probability: 0.38, is_winner: null },
  ];

  it("still leads with the price on an open market", () => {
    expect(copyFor(LIVE, "open").subtitle).toBe("Alpha leads at 62% — 2 outcomes tracked.");
  });

  it("still lets the hook lead on an open market", () => {
    const copy = copyFor(LIVE, "open", { hookDescription: "A hook worth reading." });
    expect(copy.subtitle).toBe("A hook worth reading.");
  });

  it("but the hook never pre-empts a settled RESULT", () => {
    // `hook_description` is pre-settlement editorial; under the word "Won" it
    // reads as though the market were still running. Same call `layout.tsx`
    // made for the description in #6002.
    const copy = copyFor(SPECIMEN, "resolved", {
      hookDescription: "Texas braces for another scorching summer...",
      outcomeCount: 10,
    });
    expect(copy.subtitle).toBe("77° or above won — 10 outcomes tracked.");
  });

  it("keeps the standing fallback when there is nothing priced at all", () => {
    expect(copyFor([], "open").subtitle).toBe(
      "Prediction markets translated into intuitive probabilities.",
    );
  });
});
