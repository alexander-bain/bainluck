/**
 * #6301 — A SETTLED FIELD WITH NO WINNER CROWNS NOBODY.
 *
 * Measured on production 2026-09-15 05:2xZ, `/futures/58675941` at 390px
 * (`artifacts/ux-1269/bf-6301-vuelta-nowinner-390.png`):
 *
 *     Vuelta a Espana 2026: Winner
 *     Tadej Pogacar   RESOLVED          ← the hero
 *     Final Results
 *      1  Tadej Pogacar   Lost   0%   Settled   ← three inches below
 *
 * Tadej Pogacar did not win the 2026 Vuelta a España; Enric Mas Nicolau did, and
 * we crown him correctly on our Kalshi copy of the same question (`59700067`,
 * photographed beside it as the control). The payload serves 30 outcomes with
 * `is_winner:false` and `probability:0.0` on every one — the only thing that
 * singled Pogacar out is `rank: 1`, a stale PRE-RACE rank frozen from when he was
 * the favourite.
 *
 * ═══ THE RULE, AND WHY THIS IS AN ADOPTION RATHER THAN A NEW ONE ═══
 *
 * `pickHeroOutcome` answers "which row does this surface feature", and its
 * documented fallback when nothing is graded is the PRICE LEADER. That is the
 * right answer to its question. `gradedWinner` (#6079) answers the other one —
 * "did anybody actually win" — and returns null on a field that never graded.
 *
 * Three surfaces ask. `layout.tsx` adopted `gradedWinner` under #6079 and has been
 * right ever since; the PAGE HERO and `futuresUnfurlCopy`'s `featuredName` never
 * did. So the unfurl TITLE of this market was already correct while the page it
 * links to crowned a loser — the defect is not a missing rule, it is two call
 * sites that never asked for it. Both are converted here.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Never name anyone on a settled market" satisfies every negative assertion in
 * this file. The graded controls are what kill it: `59700067` must still print
 * **Enric Mas Nicolau** beside a green WON chip, and the unfurl must still name
 * him. A blanket suppression is a worse defect than the one being fixed, because
 * it deletes every correct crowning on the site.
 *
 * ═══ WHY THE ASSERTIONS ARE SCOPED TO THE HERO ═══
 *
 * 🔴 `expect(html).not.toContain("Tadej Pogacar")` is UNSATISFIABLE and would be a
 * false guard: the results table legitimately prints his name on its first row,
 * marked `Lost`. The fix withholds the CROWN, not the row. So every assertion
 * addresses `data-testid="hero-resolved-name"` — the one element whose presence
 * means "this page is telling you he won". A whole-page scan cannot tell the two
 * states apart, which is exactly how this shipped in the first place.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;
/**
 * The settled caption ("Settled — X won.") lives INSIDE the price-trend card,
 * which the page only renders when `historyData && historyOutcomes.length > 0`
 * (page.tsx:820). With no history the page draws "Not enough price history yet"
 * instead and the caption never mounts — so a caption assertion against a
 * history-less fixture tests nothing at all.
 *
 * 🔴 That is not hypothetical: the first draft of this file asserted
 * `html).toContain("Settled")` and PASSED, matching the word on the outcome rows'
 * own price chips rather than the caption it named. A healthy sibling string
 * absorbing an assertion is the same trap ux/1268 hit on `/privacy`. Supplying
 * history is what makes these two tests real.
 */
let ACTIVE_HISTORY: unknown = undefined;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
    }
    if (tag === "futures-history") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_HISTORY as any, error: null, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: null, isLoading: false, mutate: () => {} };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import { futuresUnfurlCopy } from "@/lib/futuresDetailDisplay";

/* ────────────────────────────── the harness ────────────────────────────── */

function render(market: unknown, id: string, history: unknown = undefined): string {
  ACTIVE_MARKET = market;
  ACTIVE_HISTORY = history;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

/** Enough of a series to mount the trend card, and with it the settled caption. */
function historyFor(name: string) {
  const at = (timestamp: string, probability: number) => ({
    timestamp,
    probability,
    american_odds: null,
    bookmaker: "kalshi",
  });
  return {
    market_id: 59700067,
    market_name: name,
    hours: 168,
    outcomes: [
      {
        outcome_id: 3,
        name,
        // 🔴 `history`, not `points` — `FuturesOutcomeHistory` (lib/types.ts:906).
        // The wrong key does not render an empty chart, it throws
        // "outcome.history is not iterable" out of the SSR pass.
        history: [
          at("2026-09-10T00:00:00Z", 0.4),
          at("2026-09-12T00:00:00Z", 0.7),
          at("2026-09-13T00:00:00Z", 0.96),
        ],
      },
    ],
  };
}

/**
 * Text of the element carrying a `data-testid`, or null when the element is not
 * rendered at all. Null IS the ship state for the hero name: `FuturesHero` guards
 * the span on `outcomeName &&`, so a declined crown emits no element.
 *
 * 🔴 A CHARACTER SCAN, not `replace(/<[^>]*>/g, "")`. CodeQL flags the regex form
 * high-severity `js/incomplete-multi-character-sanitization` and it is right about
 * the shape — one pass over `<<a>script>` leaves a tag behind. The sibling file
 * `futuresBaselineRender.test.tsx` carries the same scan for the same reason.
 */
function testIdText(html: string, id: string): string | null {
  const m = new RegExp(`data-testid="${id}"[^>]*>([\\s\\S]*?)</`).exec(html);
  if (!m) return null;
  let out = "";
  let inTag = false;
  for (const ch of m[1]) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

/**
 * The 2026 Vuelta overall field as `/api/futures/58675941` serves it: settled,
 * thirty riders, not one graded, every price frozen at zero, and `rank` still
 * holding the pre-race order that makes Pogacar look like the answer.
 *
 * 🔴 REAL RIDER NAMES, deliberately. `display_rank_order` (UX-P126/F5) drops
 * anonymized reserved slots BY NAME — "Party C", "Candidate A", "Coach N" — as the
 * last thing it does before the slice, so a fixture written with placeholder names
 * has its rows removed before the page renders and every assertion below passes
 * vacuously against a table that was never built. ux/1268 lost three fixtures to
 * exactly this. A placeholder name is not neutral in this pipeline.
 */
function vuelta(overrides: Record<string, unknown> = {}) {
  return {
    id: 58675941,
    name: "Vuelta a Espana 2026: Winner",
    status: "resolved",
    resolution_date: "2026-09-20T00:00:00Z",
    outcome_count: 4,
    outcomes: [
      { id: 1, name: "Tadej Pogacar", probability: 0.0, rank: 1, is_winner: false },
      { id: 2, name: "Jonas Vingegaard", probability: 0.0, rank: 2, is_winner: false },
      { id: 3, name: "Enric Mas Nicolau", probability: 0.0, rank: 9, is_winner: false },
      { id: 4, name: "Mathieu van der Poel", probability: 0.0, rank: 12, is_winner: false },
    ],
    ...overrides,
  };
}

/** The same field with the grade the venue actually published. */
function vueltaGraded() {
  return vuelta({
    name: "Vuelta a Espana Winner",
    outcomes: [
      { id: 1, name: "Tadej Pogacar", probability: 0.0, rank: 1, is_winner: false },
      { id: 2, name: "Jonas Vingegaard", probability: 0.0, rank: 2, is_winner: false },
      { id: 3, name: "Enric Mas Nicolau", probability: 0.96, rank: 9, is_winner: true },
      { id: 4, name: "Mathieu van der Poel", probability: 0.0, rank: 12, is_winner: false },
    ],
  });
}

/* ═════════════════ the harness proves itself before it judges ═════════════════ */

describe("the harness renders the real settled page", () => {
  test("positive control: the results table is built and holds the riders", () => {
    // Every SHIP assertion below is an ABSENCE. A loading shell, an error state or
    // a fixture filtered to nothing satisfies all of them vacuously. So prove the
    // page rendered its table first — this is the row that must exist for the
    // hero's silence to mean anything.
    const html = render(vuelta(), "58675941");
    expect(html).toContain("Tadej Pogacar");
    expect(html).toContain("Enric Mas Nicolau");
  });

  test("positive control: the settled chip is rendered, so the hero itself exists", () => {
    // Distinguishes "the hero declined to crown" from "the hero never rendered".
    const html = render(vuelta(), "58675941");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Resolved");
  });
});

/* ═══════════════════════ SHIP — the crown is withheld ═══════════════════════ */

describe("a settled field with no graded winner crowns nobody", () => {
  test("🔴 the hero names no one, while the rider's row stays on the page", () => {
    const html = render(vuelta(), "58675941");
    // The crown is gone …
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
    // … and the row is NOT, which is the half a whole-page assertion gets wrong.
    expect(html).toContain("Tadej Pogacar");
  });

  test("the chip stays grey 'Resolved' and never becomes 'Won'", () => {
    const html = render(vuelta(), "58675941");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Resolved");
    expect(testIdText(html, "hero-resolved-chip")).not.toBe("Won");
  });

  test("the settled caption states the fact and claims no victor", () => {
    // Needs history or the caption does not mount at all — see ACTIVE_HISTORY.
    const html = render(vuelta(), "58675941", historyFor("Tadej Pogacar"));
    // Prove the caption is ON the page before asserting what it does not say,
    // rather than matching the word "Settled" on the outcome rows' price chips.
    expect(html).toContain("Settled.");
    expect(html).not.toContain("Tadej Pogacar won");
    expect(html).not.toMatch(/\bwon\./);
  });

  test("a missing is_winner field is not read as a grade by omission", () => {
    // Kalshi rows arrive ungraded rather than graded-false; absence of the flag
    // must reach the same verdict as an explicit false.
    const html = render(
      vuelta({
        outcomes: [
          { id: 1, name: "Tadej Pogacar", probability: 0.0, rank: 1 },
          { id: 2, name: "Jonas Vingegaard", probability: 0.0, rank: 2 },
        ],
      }),
      "58675941",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
  });

  test("a void field whose loser still carries a PRICE is declined too", () => {
    // `/futures/60010606` — Vuelta Stage 3, finalized by Kalshi as `result=scalar`
    // across all 184 legs, so "no winner" is the CORRECT answer there. Its rank-1
    // row serves `probability: 0.35`, not the 0.0 the all-losers fields serve, so
    // this specimen is the one that proves the fix keys on the GRADE and not on
    // the price being zero.
    const html = render(
      vuelta({
        id: 60010606,
        name: "Vuelta a Espana: Stage 3 Winner",
        outcomes: [
          { id: 1, name: "Tadej Pogacar", probability: 0.35, rank: 1, is_winner: false },
          { id: 2, name: "Jonas Vingegaard", probability: 0.2, rank: 2, is_winner: false },
        ],
      }),
      "60010606",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
  });
});

/* ══════════ THE OTHER DIRECTION — a real champion is still crowned ══════════ */

describe("a settled field WITH a graded winner still crowns them", () => {
  test("🔴 the hero names the graded rider, not the rank-1 favourite", () => {
    // The assertion that kills "just never name anyone on a settled market", and
    // the one that kills "name whatever sorts first": Pogacar is still rank 1 in
    // this payload and Enric Mas Nicolau is rank 9.
    const html = render(vueltaGraded(), "59700067");
    expect(testIdText(html, "hero-resolved-name")).toBe("Enric Mas Nicolau");
  });

  test("the chip turns green 'Won'", () => {
    const html = render(vueltaGraded(), "59700067");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Won");
  });

  test("the settled caption credits the graded rider by name", () => {
    const html = render(vueltaGraded(), "59700067", historyFor("Enric Mas Nicolau"));
    expect(html).toContain("Enric Mas Nicolau won.");
    // Never the rank-1 loser the old code would have reached for.
    expect(html).not.toContain("Tadej Pogacar won.");
  });
});

/* ═══════════════ the live control — an open market is untouched ═══════════════ */

describe("an open market is unaffected", () => {
  test("the live hero still prints its leader and a percentage", () => {
    const html = render(
      vuelta({
        status: "open",
        resolution_date: null,
        outcomes: [
          { id: 1, name: "Tadej Pogacar", probability: 0.62, rank: 1, is_winner: false },
          { id: 2, name: "Jonas Vingegaard", probability: 0.31, rank: 2, is_winner: false },
        ],
      }),
      "58675941",
    );
    // The settled hero draws no numeral at all, so a percentage on the page is
    // proof the LIVE branch rendered and this fix did not leak into it.
    expect(html).toContain("62");
    expect(html).toContain("Tadej Pogacar");
    expect(testIdText(html, "hero-resolved-chip")).toBeNull();
  });
});

/* ═══════════ the sibling surface — the share card had the same gap ═══════════ */

describe("the unfurl card's featured name asks for the grade too", () => {
  // `futuresUnfurlCopy` gated `settledWon` on the grade (#6079) and left
  // `featuredName` on the price-leader fallback, so the share card drew a LOSER's
  // name at 64px beside a grey RESOLVED pill — the two halves of one sentence
  // disagreeing because only one of them asked.

  test("🔴 an ungraded settled field contributes no featured name", () => {
    const copy = futuresUnfurlCopy({
      outcomes: vuelta().outcomes,
      leader: vuelta().outcomes[0],
      status: "resolved",
      hookDescription: null,
    });
    expect(copy.featuredName).toBeNull();
    expect(copy.settledWon).toBe(false);
    // The card falls back to `featuredName || title` at the call site, so the
    // reader gets the market's own name and no invented champion.
  });

  test("a graded field still names its winner on the card", () => {
    const g = vueltaGraded();
    const copy = futuresUnfurlCopy({
      outcomes: g.outcomes,
      leader: g.outcomes[0], // the rank-1 LOSER is handed in as the leader …
      status: "resolved",
      hookDescription: null,
    });
    expect(copy.featuredName).toBe("Enric Mas Nicolau"); // … and the GRADE wins.
    expect(copy.settledWon).toBe(true);
  });

  test("an open market's featured name is still null, as before", () => {
    const copy = futuresUnfurlCopy({
      outcomes: vuelta().outcomes,
      leader: vuelta().outcomes[0],
      status: "open",
      hookDescription: null,
    });
    expect(copy.featuredName).toBeNull();
    expect(copy.settledWon).toBe(false);
  });
});
