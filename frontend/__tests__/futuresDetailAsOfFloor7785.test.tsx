/**
 * #7785 — THE FUTURES BOARD'S ONE FRESHNESS LINE READS THE FLOOR OVER THE ROWS IT
 * DRAWS, AND IT REACHES THE LADDER.
 *
 * `app/futures/[id]/page.tsx` computed its as-of as
 * `asOfLabel(leader?.last_updated)`, and `leader` is the HIGHEST-PROBABILITY
 * outcome. #6018 rejected that rule for the search card in as many words —
 * *"taking the newest would let one refreshed favourite vouch for four stale
 * rungs"* — and shipped `renderedPricesAsOf`, the floor over the drawn rows,
 * which the card, My Stuff and the iOS twin have read ever since. The one surface
 * that puts the most rows under a single label kept the ceiling.
 *
 * ═══ WHAT THE READER SAW, and why it is SILENCE rather than a wrong date ═══
 *
 * The leader is also the most-polled row, so `asOfLabel` returned `null` and the
 * header printed nothing at all. Production at 390px, 2026-09-21
 * (`artifacts/ux-asof/BEFORE-12046267-390-s1400.png` and `…-s2600.png`),
 * `/futures/12046267` — the WNBA title board, mid-playoffs:
 *
 *     📊 All Outcomes                     <- nothing here
 *        1  Minnesota     OPEN 16%   LATEST 46%     written 2026-09-21T10:50Z
 *        …
 *       13  Phoenix       OPEN 11%   LATEST  0%     written 2026-09-19T10:50Z
 *       14  Toronto       OPEN  1%   LATEST  0%     written 2026-09-19T10:50Z
 *       15  Los Angeles   OPEN 22%   LATEST  0%     written 2026-09-19T10:50Z
 *
 * `/futures/275` (Pro Baseball Champion) is the same shape on the same morning.
 * `WNBA_TITLE` below is that served payload, stamps and all.
 *
 * ═══ THE CONTROL THAT SEPARATES THE FIX FROM "PRINT A DATE MORE OFTEN" ═══
 *
 * 🔴 `freshBoard()` — every row written this morning — must print NO as-of. A
 * label on a current price is noise, not honesty (UX-P233), and a change that
 * made the element unconditional would satisfy every "the date is there"
 * assertion in this file. Measured on the served payloads of the 199 busiest open
 * tier-1/2 boards, the leader rule labels 37 boards and the floor labels 41: this
 * is a four-board change, not a new caption on every page.
 *
 * ═══ THE 25-CAP IS PART OF THE RULE, NOT AN IMPLEMENTATION DETAIL ═══
 *
 * 🪤 The plausible wrong scope is "every priced row". The ranked table draws
 * `pricedOutcomes.slice(0, 25)` until the reader expands it, and on the 391 open
 * tier-1–3 boards with more than 25 priced rows the two scopes print a different
 * date on 17 — on 7 of them the wider scope dates the header from rows BELOW the
 * cap that nobody can see, which is #6018's own named mirror-image lie ("honest
 * about rows the reader cannot see and misleading about the ones they can").
 * `cappedBoard()` is the case that can tell those two rules apart; a suite
 * without it passes under either.
 *
 * ═══ AND #6803 ═══
 *
 * 🔴 A row showing no number has no age this sentence is about, and `0` IS a
 * price and keeps its vote. `numberlessOldestBoard()` pins both halves: the
 * oldest row on the board is numberless and must NOT set the floor, while a 0%
 * row two days old must.
 *
 * Assertions read the RENDERED MARKUP through the page's SSR, not a helper call,
 * because the defect was never in a helper — `renderedPricesAsOf` was correct and
 * shipped the whole time. What was wrong was which rows this page handed it, and
 * the only instrument that can see that is the page's own output. Reverting
 * `marketAsOf` to `asOfLabel(leader?.last_updated)` reddens the first, third,
 * fourth and sixth tests below.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return { data: ACTIVE_MARKET as any, error: null, isLoading: false, mutate: () => {} };
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

/* ────────────────────────────── the harness ────────────────────────────── */

/**
 * The morning the specimens were read. `jest.config.js` pins `TZ=UTC`, so
 * `instantDayLabel` — which the page deliberately calls with no zone — renders
 * UTC days here and "Sep 19" is deterministic.
 */
const NOW = new Date("2026-09-21T11:05:00.000Z");

const TODAY = "2026-09-21T10:50:47.000000+00:00";
const TWO_DAYS_AGO = "2026-09-19T10:50:23.000000+00:00";
const APRIL = "2026-04-30T04:46:55.862136+00:00";

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["nextTick"] }).setSystemTime(NOW);
});
afterAll(() => {
  jest.useRealTimers();
});

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

const AS_OF = 'data-testid="market-as-of"';

/** The as-of the ranked table prints, or null when it prints none. */
function tableAsOf(html: string): string | null {
  const at = html.indexOf(AS_OF);
  if (at === -1) return null;
  const open = html.indexOf(">", at);
  const close = html.indexOf("<", open);
  return html.slice(open + 1, close);
}

/**
 * The ladder's header hint. `QuantityGroup` renders it as the right-hand span of
 * its title row; this reads the window around the title rather than assuming a
 * class, so a restyle of the component does not silently blind the assertion.
 */
function ladderHint(html: string): string | null {
  const at = html.indexOf("All Outcomes");
  if (at === -1) return null;
  const window = html.slice(at, at + 400);
  const m = window.match(/as of [A-Z][a-z]{2} \d{1,2}/);
  return m ? m[0] : null;
}

function outcome(
  id: number,
  name: string,
  probability: number | null,
  rank: number,
  lastUpdated: string,
) {
  return {
    id,
    name,
    probability,
    rank,
    opening_probability: null,
    probability_change_24h: null,
    american_odds: null,
    opening_american_odds: null,
    is_winner: false,
    resolution_source: null,
    last_updated: lastUpdated,
  };
}

function board(over: Record<string, unknown>) {
  return {
    id: 12046267,
    name: "Women's Pro Basketball Champion",
    status: "open",
    source: "odds_api",
    category: "championship",
    llm_sport_category: "basketball",
    market_type: "field",
    mutually_exclusive: true,
    bookmakers: ["odds_api"],
    resolution_date: "2026-10-20T00:00:00+00:00",
    updated_at: TODAY,
    ...over,
  };
}

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * `/api/futures/12046267`, read 2026-09-21 ~10:5xZ. Fifteen rows: the top eleven
 * repriced that morning, the last four frozen at 0% two days earlier. Fewer than
 * 25 priced rows, so the whole board is drawn and the cap is not in play.
 */
const WNBA_ROWS: Array<[string, number, string]> = [
  ["Minnesota", 0.455, TODAY],
  ["Golden State", 0.125, TODAY],
  ["Las Vegas", 0.125, TODAY],
  ["Atlanta", 0.105, TODAY],
  ["Indiana", 0.095, TODAY],
  ["New York", 0.055, TODAY],
  ["Phoenix (WC)", 0.02, TODAY],
  ["Dallas", 0.01, TODAY],
  ["Washington", 0.005, TODAY],
  ["Chicago", 0.005, TODAY],
  ["Connecticut", 0.005, TODAY],
  ["Seattle", 0.0, TWO_DAYS_AGO],
  ["Phoenix", 0.0, TWO_DAYS_AGO],
  ["Toronto", 0.0, TWO_DAYS_AGO],
  ["Los Angeles", 0.0, TWO_DAYS_AGO],
];

function wnbaTitle() {
  return board({
    outcome_count: WNBA_ROWS.length,
    outcomes: WNBA_ROWS.map(([name, p, stamp], i) => outcome(800 + i, name, p, i + 1, stamp)),
  });
}

/** The same board with every row repriced this morning. */
function freshBoard() {
  return board({
    outcome_count: WNBA_ROWS.length,
    outcomes: WNBA_ROWS.map(([name, p], i) => outcome(800 + i, name, p, i + 1, TODAY)),
  });
}

/**
 * Thirty priced rows: the drawn twenty-five are all fresh, and only the five
 * below the cap are stale. The scope control.
 */
function cappedBoard() {
  const rows = Array.from({ length: 30 }, (_, i) =>
    outcome(
      600 + i,
      `Club ${i + 1}`,
      // Strictly descending, so the sort cannot reorder the cap boundary.
      (30 - i) / 100,
      i + 1,
      i < 25 ? TODAY : APRIL,
    ),
  );
  return board({ id: 275, name: "Pro Baseball Champion", outcome_count: 30, outcomes: rows });
}

/**
 * #6803 both ways: the oldest row on the board shows no number (it must not vote),
 * and a 0% row two days old does (it must).
 */
function numberlessOldestBoard() {
  return board({
    outcome_count: 4,
    outcomes: [
      outcome(1, "Minnesota", 0.6, 1, TODAY),
      outcome(2, "Las Vegas", 0.4, 2, TODAY),
      outcome(3, "Toronto", 0.0, 3, TWO_DAYS_AGO),
      outcome(4, "Other", null, 4, APRIL),
    ],
  });
}

/**
 * A quantity ladder — the branch that rendered no as-of at all. Shaped like
 * `/futures/109403`: dated rungs, every one frozen in April. `market_type` is
 * "quantity" and the rung names are numeric-dated so `resolveShape` keeps it
 * there.
 */
function staleLadder() {
  return {
    id: 109403,
    name: "When will DHS be funded again?",
    status: "open",
    source: "kalshi",
    category: "politics",
    llm_sport_category: "politics",
    market_type: "quantity",
    mutually_exclusive: false,
    bookmakers: ["kalshi"],
    resolution_date: "2027-01-01T15:00:00+00:00",
    updated_at: APRIL,
    outcome_count: 5,
    outcomes: [
      outcome(10, "Before May 15, 2026", 0.66, 5, APRIL),
      outcome(11, "Before May 22, 2026", 0.78, 4, APRIL),
      outcome(12, "Before Jun 1, 2026", 0.855, 3, APRIL),
      outcome(13, "Before Jul 1, 2026", 0.9635, 2, APRIL),
      outcome(14, "Before Jan 1, 2027", 0.985, 1, APRIL),
    ],
  };
}

/** The same ladder repriced this morning. */
function freshLadder() {
  const m = staleLadder();
  return { ...m, updated_at: TODAY, outcomes: m.outcomes.map((o) => ({ ...o, last_updated: TODAY })) };
}

/* ─────────────────────────────── the guards ─────────────────────────────── */

describe("the ranked table's as-of", () => {
  it("dates the WNBA title board from its oldest DRAWN row, not from the leader", () => {
    const html = render(wnbaTitle(), "12046267");
    // The leader (Minnesota, 46%) was written this morning, which is why the
    // leader rule printed nothing here.
    expect(tableAsOf(html)).toBe("as of Sep 19");
  });

  it("says nothing when every drawn row is current", () => {
    const html = render(freshBoard(), "12046267");
    expect(html).not.toContain(AS_OF);
  });

  it("reads the rows above the 25-cap, not the stale tail the reader cannot see", () => {
    const html = render(cappedBoard(), "275");
    // Five April rows sit at ranks 26–30, behind "Show all 30". Dating the
    // header from them would be honest about rows nobody is looking at.
    expect(html).not.toContain(AS_OF);
    // …and the tail is really there, so the test is not passing on an empty board.
    expect(html).toContain("Show all 30");
  });

  it("lets a 0% row set the floor and refuses to let a numberless one (#6803)", () => {
    const html = render(numberlessOldestBoard(), "12046267");
    // "Other" is the oldest row on the board (April) and shows no number, so it
    // is not an age this sentence is about. Toronto's 0% two days ago is.
    expect(tableAsOf(html)).toBe("as of Sep 19");
  });
});

describe("the ladder's as-of", () => {
  it("prints the same line on a quantity board, which had none at all", () => {
    const html = render(staleLadder(), "109403");
    expect(ladderHint(html)).toBe("as of Apr 30");
  });

  it("says nothing on a ladder repriced this morning", () => {
    const html = render(freshLadder(), "109403");
    expect(ladderHint(html)).toBeNull();
  });

  it("renders the ladder, so the assertions above are reading the right branch", () => {
    const html = render(staleLadder(), "109403");
    // The ladder branch, not the ranked table: the ranked table is suppressed
    // under `hasOwnLadder`, so its testid must be absent while the rungs are drawn.
    expect(html).toContain("Before May 15, 2026");
    expect(html).not.toContain(AS_OF);
  });
});
