/**
 * #7906 — A SETTLED FIELD WITH MANY WINNERS CROWNS NOBODY.
 *
 * Measured on production 2026-09-22 06:45Z, `/futures/61010898` at 390px:
 *
 *     BMW PGA Championship - Make the Cut
 *     Ludvig Aberg   WON                ← the hero
 *     Settled — Ludvig Aberg won.       ← the caption under the trend chart
 *     Final Results: 72 of 163 rows badged  Won · 100% Settled
 *
 * `mutually_exclusive: false`, `market_type: 'participation'`, seventy-two golfers
 * graded `is_winner: true` because seventy-two made the cut. Ludvig Aberg is one of
 * them. He did not win the BMW PGA Championship, and the page says he did — in the
 * hero, in the caption, and in the share card's title.
 *
 * ═══ WHY THE TWO PRIOR FIXES IN THIS SERIES MISS IT ═══
 *
 * #6079 gave the word "won" one source (the grade). #6301 taught the surfaces to
 * stay silent when that source grades NOBODY. Both ask "is the featured row a
 * winner"; neither asks "is it the ONLY one". `pickHeroOutcome`'s resolved branch
 * is `outcomes.find((o) => o.is_winner === true)` — the FIRST graded row in payload
 * order — so on a 72-winner board the crown lands on whoever the serializer emitted
 * first. #7906's original specimen, a 106-golfer board reading "Jackson Suber WON",
 * is the same accident on a different payload.
 *
 * ═══ THE TEST IS THE COUNT, AND THE COUNT IS TESTED IN BOTH WORLDS ═══
 *
 * Not `mutually_exclusive`: CERT-609 records that only Kalshi's `false` is
 * affirmative, because Polymarket coerces an absent `negRisk` to `false`. The
 * number of graded rows is served by every source and means one thing everywhere.
 *
 * So the same rule covers the corrupt case, and `sixWayDraw` below pins it: #6590
 * measured a MUTEX market serving two winners (`/futures/60015154`, "Settled — SK
 * Beveren won." over a table badging both `SK Beveren` and `Draw (…)`, on a match
 * that finished 3–0). We cannot tell which row is the lie, and #4923 ruled that
 * case — no verdict beats a wrong one.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "Never crown anyone on a settled market" satisfies every negative assertion here,
 * and `oneWinner` + `bigBoardOneWinner` are what kill it: a real champion must still
 * be named, and — the assertion that stops a lazy "big boards don't crown" — a
 * 163-row board with exactly ONE graded winner must still name them. The fix keys
 * on the number of GRADES, never on the size of the field.
 *
 * ═══ WHY THE ASSERTIONS ARE SCOPED TO THE HERO ═══
 *
 * 🔴 `expect(html).not.toContain("Ludvig Aberg")` is UNSATISFIABLE and would be a
 * false guard: the Final Results table legitimately prints his name, badged `Won`,
 * because he did make the cut. The fix withholds the CROWN, not the row. Every
 * assertion therefore addresses `data-testid="hero-resolved-name"` — the one element
 * whose presence means "this page is telling you he won the championship".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;
/**
 * The settled caption ("Settled — X won.") lives INSIDE the price-trend card, which
 * the page renders only when history is present. With no history the page draws its
 * empty state and the caption never mounts — a caption assertion against a
 * history-less fixture tests nothing at all (the trap the #6301 sibling documents).
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
import { futuresUnfurlCopy, gradedWinner } from "@/lib/futuresDetailDisplay";

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
    bookmaker: "datagolf",
  });
  return {
    market_id: 61010898,
    market_name: name,
    hours: 168,
    outcomes: [
      {
        outcome_id: 3,
        name,
        // 🔴 `history`, not `points` — the wrong key throws
        // "outcome.history is not iterable" out of the SSR pass.
        history: [
          at("2026-09-17T00:00:00Z", 0.62),
          at("2026-09-18T00:00:00Z", 0.78),
          at("2026-09-19T00:00:00Z", 0.84),
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
 * 🔴 A CHARACTER SCAN, not `replace(/<[^>]*>/g, "")` — CodeQL flags the regex form
 * high-severity `js/incomplete-multi-character-sanitization`, and it is right about
 * the shape.
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
 * The BMW PGA make-the-cut board as `/api/futures/61010898` serves it: resolved,
 * non-mutually-exclusive, and graded on FOUR golfers at once. Probabilities are the
 * production values (Aberg 0.840267, Fleetwood 0.83825, McIlroy 0.837933, Rahm
 * 0.83475) — frozen make-cut prices, all within a quarter-point of each other, which
 * is why nothing about the price can be used to pick a champion either.
 *
 * 🔴 REAL GOLFER NAMES, deliberately. `display_rank_order` drops anonymized reserved
 * slots BY NAME ("Party C", "Candidate A"), so a fixture written with placeholder
 * names loses its rows before the page renders and every assertion passes vacuously.
 */
function bmwPga(overrides: Record<string, unknown> = {}) {
  return {
    id: 61010898,
    name: "BMW PGA Championship - Make the Cut",
    status: "resolved",
    mutually_exclusive: false,
    market_type: "participation",
    resolution_date: "2026-09-20T00:00:00Z",
    outcome_count: 4,
    outcomes: [
      { id: 1, name: "Ludvig Aberg", probability: 0.840267, rank: 1, is_winner: true },
      { id: 2, name: "Tommy Fleetwood", probability: 0.83825, rank: 2, is_winner: false },
      { id: 3, name: "Rory McIlroy", probability: 0.837933, rank: 3, is_winner: true },
      { id: 4, name: "Jon Rahm", probability: 0.83475, rank: 4, is_winner: false },
    ],
    ...overrides,
  };
}

/** The same shape of board, graded on exactly one golfer — a real championship. */
function oneWinner() {
  return bmwPga({
    name: "BMW PGA Championship Winner",
    outcomes: [
      { id: 1, name: "Ludvig Aberg", probability: 0.0, rank: 1, is_winner: false },
      { id: 2, name: "Tommy Fleetwood", probability: 0.96, rank: 2, is_winner: true },
      { id: 3, name: "Rory McIlroy", probability: 0.0, rank: 3, is_winner: false },
      { id: 4, name: "Jon Rahm", probability: 0.0, rank: 4, is_winner: false },
    ],
  });
}

/* ═════════════════ the harness proves itself before it judges ═════════════════ */

describe("the harness renders the real settled page", () => {
  test("positive control: the results table is built and holds the golfers", () => {
    // Every SHIP assertion below is an ABSENCE. A loading shell, an error state or a
    // fixture filtered to nothing satisfies all of them vacuously.
    const html = render(bmwPga(), "61010898");
    expect(html).toContain("Ludvig Aberg");
    expect(html).toContain("Rory McIlroy");
  });

  test("positive control: the settled chip is rendered, so the hero itself exists", () => {
    // Distinguishes "the hero declined to crown" from "the hero never rendered".
    const html = render(bmwPga(), "61010898");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Resolved");
  });
});

/* ═══════════════════════ SHIP — the crown is withheld ═══════════════════════ */

describe("a settled field with many graded winners crowns nobody", () => {
  test("🔴 the hero names no one, while every golfer's row stays on the page", () => {
    const html = render(bmwPga(), "61010898");
    // The crown is gone …
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
    // … and the rows are NOT. Aberg and McIlroy both made the cut and the table is
    // the honest place to say so — this is the half a whole-page scan gets wrong.
    expect(html).toContain("Ludvig Aberg");
    expect(html).toContain("Rory McIlroy");
  });

  test("the chip stays grey 'Resolved' and never becomes 'Won'", () => {
    const html = render(bmwPga(), "61010898");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Resolved");
    expect(testIdText(html, "hero-resolved-chip")).not.toBe("Won");
  });

  test("the settled caption states the fact and claims no victor", () => {
    // Needs history or the caption does not mount at all — see ACTIVE_HISTORY.
    const html = render(bmwPga(), "61010898", historyFor("Ludvig Aberg"));
    // Prove the caption is ON the page before asserting what it does not say.
    expect(html).toContain("Settled.");
    expect(html).not.toContain("Ludvig Aberg won");
    expect(html).not.toMatch(/\bwon\./);
  });

  test("the crown does not simply move to the SECOND graded row", () => {
    // Payload order is the whole defect, so reorder it: if the fix were "skip the
    // first winner" or "prefer the highest price", McIlroy or Aberg would surface
    // here. Nobody may.
    const html = render(
      bmwPga({
        outcomes: [
          { id: 3, name: "Rory McIlroy", probability: 0.837933, rank: 1, is_winner: true },
          { id: 1, name: "Ludvig Aberg", probability: 0.840267, rank: 2, is_winner: true },
          { id: 2, name: "Tommy Fleetwood", probability: 0.83825, rank: 3, is_winner: false },
        ],
      }),
      "61010898",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
  });

  test("two graded winners are already too many — the rule is not a 'lots of them' rule", () => {
    const html = render(
      bmwPga({
        outcomes: [
          { id: 1, name: "Ludvig Aberg", probability: 0.84, rank: 1, is_winner: true },
          { id: 2, name: "Tommy Fleetwood", probability: 0.83, rank: 2, is_winner: true },
        ],
      }),
      "61010898",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
  });

  test("#6590's corrupt MUTEX board is declined by the same rule", () => {
    // `/futures/60015154` — a match that finished 3–0 served TWO winners on a
    // mutually-exclusive market and captioned one of them. Plurality is corruption
    // here rather than design, we cannot tell which row is the lie, and #4923 says
    // no verdict beats a wrong one. Note `mutually_exclusive: true`: the fix must
    // reach this board without consulting that flag.
    const html = render(
      bmwPga({
        id: 60015154,
        name: "Belgium Pro League: SK Beveren vs Oud-Heverlee Leuven",
        mutually_exclusive: true,
        market_type: "duel",
        outcomes: [
          { id: 1, name: "SK Beveren", probability: 0.0, rank: 1, is_winner: true },
          {
            id: 2,
            name: "Draw (SK Beveren vs. Oud-Heverlee Leuven)",
            probability: 0.0,
            rank: 2,
            is_winner: true,
          },
          { id: 3, name: "Oud-Heverlee Leuven", probability: 1.0, rank: 3, is_winner: false },
        ],
      }),
      "60015154",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
    expect(testIdText(html, "hero-resolved-chip")).toBe("Resolved");
  });
});

/* ══════════ THE OTHER DIRECTION — a real champion is still crowned ══════════ */

describe("a settled field with exactly one graded winner still crowns them", () => {
  test("🔴 the hero names the graded golfer, not the rank-1 favourite", () => {
    // Kills "never crown anyone on a settled market" AND "name whatever sorts
    // first": Aberg is still rank 1 and first in the payload; Fleetwood is graded.
    const html = render(oneWinner(), "61010899");
    expect(testIdText(html, "hero-resolved-name")).toBe("Tommy Fleetwood");
  });

  test("the chip turns green 'Won'", () => {
    const html = render(oneWinner(), "61010899");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Won");
  });

  test("the settled caption credits the graded golfer by name", () => {
    const html = render(oneWinner(), "61010899", historyFor("Tommy Fleetwood"));
    expect(html).toContain("Tommy Fleetwood won.");
    expect(html).not.toContain("Ludvig Aberg won.");
  });

  test("🔴 a 163-row board with ONE graded winner still crowns them", () => {
    // The assertion that stops the fix degenerating into "big fields don't crown".
    // 163 rows is the real BMW PGA board's size; exactly one of them is graded.
    const many = Array.from({ length: 163 }, (_, i) => ({
      id: i + 1,
      name: `Golfer ${i + 1}`,
      probability: 0.0,
      rank: i + 1,
      is_winner: false,
    }));
    // A real name, for the `display_rank_order` reason documented on the fixture.
    many[99] = { id: 100, name: "Viktor Hovland", probability: 0.99, rank: 100, is_winner: true };
    const html = render(bmwPga({ outcome_count: 163, outcomes: many }), "61010898");
    expect(testIdText(html, "hero-resolved-name")).toBe("Viktor Hovland");
    expect(testIdText(html, "hero-resolved-chip")).toBe("Won");
  });
});

/* ═════════ #6301 is preserved — a field grading NOBODY still names nobody ═════════ */

describe("the zero-winner rule #6301 shipped is unchanged", () => {
  test("a settled field with no grade at all crowns nobody", () => {
    const html = render(
      bmwPga({
        outcomes: [
          { id: 1, name: "Ludvig Aberg", probability: 0.0, rank: 1, is_winner: false },
          { id: 2, name: "Tommy Fleetwood", probability: 0.0, rank: 2, is_winner: false },
        ],
      }),
      "61010898",
    );
    expect(testIdText(html, "hero-resolved-name")).toBeNull();
  });
});

/* ═══════════════ the live control — an open market is untouched ═══════════════ */

describe("an open market is unaffected", () => {
  test("the live hero still prints a leader and a percentage", () => {
    const html = render(
      bmwPga({
        status: "open",
        resolution_date: null,
        outcomes: [
          { id: 1, name: "Ludvig Aberg", probability: 0.62, rank: 1, is_winner: false },
          { id: 2, name: "Tommy Fleetwood", probability: 0.31, rank: 2, is_winner: false },
        ],
      }),
      "61010898",
    );
    // The settled hero draws no numeral, so a percentage proves the LIVE branch ran.
    expect(html).toContain("62");
    expect(html).toContain("Ludvig Aberg");
    expect(testIdText(html, "hero-resolved-chip")).toBeNull();
  });
});

/* ═══════════ the sibling surfaces — share card and unfurl title agree ═══════════ */

describe("the unfurl card refuses the same crown", () => {
  // `futuresUnfurlCopy` and `layout.tsx`'s `winnerName` both ask `gradedWinner`, so
  // the share card and the og:title decline with the page rather than drifting into
  // naming a champion the page itself withholds (#6079's whole point).

  test("🔴 a many-winner settled board contributes no featured name", () => {
    const copy = futuresUnfurlCopy({
      outcomes: bmwPga().outcomes,
      leader: bmwPga().outcomes[0],
      status: "resolved",
      hookDescription: null,
      marketType: "participation",
    });
    expect(copy.featuredName).toBeNull();
    expect(copy.settledWon).toBe(false);
    // The card falls back to `featuredName || title`, so the reader gets the board's
    // own question and no invented champion.
  });

  test("a single-winner board still names its champion on the card", () => {
    const g = oneWinner();
    const copy = futuresUnfurlCopy({
      outcomes: g.outcomes,
      leader: g.outcomes[0], // the rank-1 non-winner is handed in as the leader …
      status: "resolved",
      hookDescription: null,
      marketType: "participation",
    });
    expect(copy.featuredName).toBe("Tommy Fleetwood"); // … and the GRADE wins.
    expect(copy.settledWon).toBe(true);
  });
});

/* ═══════ THE EXEMPTION — a cumulative ladder's plural grades are the design ═══════ */

describe("a threshold ladder still names its rung", () => {
  // #6032's production specimen, `/futures/60544511`: a New York temperature
  // ladder where three rungs are graded true because the day cleared all three.
  // "77° or above won" is TRUE — the rungs are one question at ascending
  // thresholds and they are ORDERED, so the first true one is a canonical answer.
  // Peers on a field have no order, which is the whole difference.
  const LADDER = [
    { id: 1, name: "77° or above", probability: 1.0, rank: 1, is_winner: true },
    { id: 2, name: "78° or above", probability: 1.0, rank: 2, is_winner: true },
    { id: 3, name: "82° or above", probability: 1.0, rank: 3, is_winner: true },
    { id: 4, name: "83° or above", probability: null, rank: 4, is_winner: false },
    { id: 5, name: "86° or above", probability: null, rank: 5, is_winner: false },
  ];

  test("🔴 three true rungs still produce a named champion (stored shape)", () => {
    expect(gradedWinner(LADDER, LADDER[0], "resolved", "quantity")).toBe(LADDER[0]);
  });

  test("🔴 and with NO stored shape it is still named — the guard refuses to guess", () => {
    // This is the assertion that fixes the DESIGN, not just the behaviour. The
    // tempting form of this fix is "decline unless the shape is `quantity`", and
    // it reads identically until the shape is missing: `resolveShapeFallback`'s
    // `NUMERIC_OUTCOME_RE` anchors its keywords at the START of a name, so
    // "77° or above" matches nothing and this ladder classifies as a FIELD. A
    // negative test would strip the crown from exactly the boards the exemption
    // exists for, on every payload the #194 backfill has not reached.
    expect(gradedWinner(LADDER, LADDER[0], "resolved")).toBe(LADDER[0]);
  });

  test("an unrecognised or unshaped market_type is left alone for the same reason", () => {
    expect(gradedWinner(LADDER, LADDER[0], "resolved", "unshaped")).toBe(LADDER[0]);
    expect(gradedWinner(LADDER, LADDER[0], "resolved", "not-a-shape")).toBe(LADDER[0]);
  });

  test("the exemption is the SHAPE, not the plurality — a participation board is still declined", () => {
    // The assertion that stops the exemption swallowing the ship: same plural
    // grades, a shape whose winners are peers.
    const field = bmwPga().outcomes;
    expect(gradedWinner(field, field[0], "resolved", "participation")).toBeNull();
  });
});

/* ═════════════════ the helper, asserted directly ═════════════════ */

describe("gradedWinner counts grades on a peer-shaped board", () => {
  const rows = (...flags: Array<boolean | null | undefined>) =>
    flags.map((is_winner, i) => ({ id: i + 1, name: `Row ${i + 1}`, is_winner }));

  test("two grades ⇒ null", () => {
    const o = rows(true, true, false);
    expect(gradedWinner(o, o[0], "resolved", "field")).toBeNull();
  });

  test("one grade ⇒ that row", () => {
    const o = rows(false, true, false);
    expect(gradedWinner(o, o[0], "resolved", "field")).toBe(o[1]);
  });

  test("no grades ⇒ null (#6301)", () => {
    const o = rows(false, false);
    expect(gradedWinner(o, o[0], "resolved", "field")).toBeNull();
  });

  test("an unresolved board is null whatever the grades say", () => {
    const o = rows(true, true);
    expect(gradedWinner(o, o[0], "open", "field")).toBeNull();
  });

  test("absent flags are not read as grades by omission", () => {
    // Kalshi rows arrive ungraded rather than graded-false.
    const o = rows(undefined, null, true);
    expect(gradedWinner(o, o[0], "resolved", "field")).toBe(o[2]);
  });

  test("🔴 every peer shape declines, and only the peer shapes", () => {
    // The whole rule in one assertion, both directions. A shape added to the
    // classifier without a decision here shows up as a failure in this test.
    const o = rows(true, true);
    for (const shape of ["claim", "duel", "field", "participation", "container_member"]) {
      expect(gradedWinner(o, o[0], "resolved", shape)).toBeNull();
    }
    // `quantity` is the design exemption; `unshaped` and absent are the refusal
    // to guess — both keep the pre-#7906 answer.
    expect(gradedWinner(o, o[0], "resolved", "quantity")).toBe(o[0]);
    expect(gradedWinner(o, o[0], "resolved", "unshaped")).toBe(o[0]);
    expect(gradedWinner(o, o[0], "resolved")).toBe(o[0]);
  });
});
