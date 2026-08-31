// lane1-Q481 — the SETTLED half of the Q478 ladder. Repair of CERT-605.
//
// CERT-605 blocked `dc92f009`: "The new own-outcome ladder runs for resolved
// quantity markets, suppresses the graded outcomes table, and can render only
// probabilities under 'Final Results' because `QuantityRung` carries no winner
// state."
//
// THE FINDING IS ACCEPTED IN FULL AND IT IS BIGGER THAN THE BLOCK SAYS.
// Measured on production 2026-08-31:
//
//   SELECT status, count(*) FROM futures_markets WHERE market_type='quantity'
//     -> resolved 278,151 | open 9,678
//
// The blocked bytes ladder BOTH, so the graded table was suppressed on 96.6% of the
// population — while `census_quantity_ladder_q478.py` measures the ship over
// `WHERE m.market_type='quantity' AND m.status='open'`. The 278k resolved markets
// were never in the measurement at all. Laddering them was unmeasured scope.
//
// 🔴 AND THE REPAIR IS NOT "ADD Won/Lost TO THE RUNG", because a settled ladder
// cannot ORDER itself either. Rung order comes from ascending price, and settlement
// collapses price: of 1,500 settled quantity markets carrying a true winner, 1,260
// (84%) hold two or fewer distinct probabilities and 60 hold exactly one. With every
// rung at 0% or 100% the order falls through to the stable-sort tiebreak — serve
// order — which for 109349 is `2027, October, April, July`: the backwards timeline
// item 10 exists to fix, wearing a ladder's clothes. `opening_probability` is no
// rescue (present on every row for only 891 of the 1,500, 59.4%).
//
// So a settled market renders the graded table, exactly as it did before Q478, and
// every open market still ladders. Teaching the ladder to grade AND to order itself
// without prices needs an ordering signal that survives settlement — a data
// question, not a rendering one — and is filed as a follow-up.
//
// 🔴 `is_winner` CANNOT BE READ THE OBVIOUS WAY, which is why every gate below is on
// STATUS. `models.py:856` declares `is_winner: Mapped[bool] = mapped_column(Boolean,
// default=False)` — a CLIENT-side default, so `false` is what an ungraded row says
// and null never appears (measured: 0 of 2,000 open quantity markets have any NULL
// `is_winner`). A first version of this measurement asked `IS NOT NULL` and got a
// perfect 3000/3000 — the vacuous answer that trap hands you.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PRODUCTION = require("../fixtures/futuresDetail109349Production.json");

const RAW = PRODUCTION as Record<string, unknown>;
type Outcome = Record<string, unknown>;
const RAW_OUTCOMES = RAW.outcomes as Outcome[];

/**
 * The real 109349 payload, settled the way its own rungs would settle.
 *
 * The iPhone 18 ships in September: "Before October" and "Before 2027" are BOTH
 * true, "Before April" and "Before July" both false. Two winners, built from the
 * real fixture's real outcome ids and names — not a hand-written ladder with tidy
 * ascending ids. (Q478 was caught out once by assuming insertion order was a fact:
 * this fixture prices April and July identically at 1% and its ids run
 * 1596640 = July, 1596641 = April.)
 *
 * The collapsed 1/0 probabilities are not a convenience — they are the measured
 * majority case (84%), and they are exactly what destroys the ladder's ordering.
 */
function settled(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const byName = (n: string) => RAW_OUTCOMES.find((o) => o.name === n)!;
  return {
    ...RAW,
    market_type: "quantity",
    status: "resolved",
    outcomes: [
      { ...byName("Before 2027"), is_winner: true, probability: 1 },
      { ...byName("Before October"), is_winner: true, probability: 1 },
      { ...byName("Before April"), is_winner: false, probability: 0 },
      { ...byName("Before July"), is_winner: false, probability: 0 },
    ],
    ...overrides,
  };
}

let payload: Record<string, unknown> = settled();

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false };
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") return { data: payload, error: null, isLoading: false };
    if (tag === "futures-group") {
      return {
        data: { group_id: RAW.group_id, markets: [], threshold_groups: {} },
        error: null,
        isLoading: false,
      };
    }
    return { data: undefined, error: null, isLoading: false };
  },
}));

jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, pinned: [] }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({}),
}));

import FuturesDetailPage from "@/app/futures/[id]/page";

function render(p: Record<string, unknown>): string {
  payload = p;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "109349" }} />);
}

/**
 * The region from the outcome-section heading to the end of the document.
 *
 * CERT-605's own assertion was SECTION-SCOPED for a reason, and it is the reason
 * this helper exists: the page prints the winner's name and the word "Settled" in
 * its hero banner too, so an unscoped `toContain("Settled")` is satisfied by chrome
 * the block was never about, and would stay green with the outcome section deleted
 * entirely.
 */
function resultsSection(html: string): string {
  const i = html.indexOf("Final Results");
  expect(i).toBeGreaterThan(-1);
  return html.slice(i);
}

/**
 * Chrome that belongs to exactly ONE arm.
 *
 * `QuantityGroup` gives every rung `aria-label="{label}: {pct}"`; no table row
 * carries one. `OutcomeRow` stamps `data-testid="outcome-row"`; the ladder never
 * does. Neither marker is printed by both.
 *
 * 🔴 BOTH ARE TEST HOOKS, NOT DISPLAY COPY, AND THAT IS THE POINT. Q478 first told
 * these two arms apart with `toContain("All Outcomes")` — which the LADDER prints
 * as its own title — and a mutant walked through it. The replacement was
 * `"24h Change"`, the sort pill's label, which held right up until master renamed
 * that pill to "Last move" (UX-P233) and broke six assertions in this file and its
 * Q478 sibling on the merged tree, while the page rendered perfectly correctly.
 * A guard keyed on words a designer may reword is a guard with an expiry date.
 */
const LADDER_ONLY = 'aria-label="Before April:';
const TABLE_ONLY = 'data-testid="outcome-row"';

describe("🔴 CERT-605: a settled quantity market shows its RESULT, not four prices", () => {
  test("the results section says Won", () => {
    const section = resultsSection(render(settled()));
    expect(section).toContain(">Won<");
  });

  test("BOTH winners are marked — a cumulative ladder settles as a THRESHOLD", () => {
    // 151 of 3,000 resolved quantity markets carry more than one true winner
    // ("Before October" and "Before 2027" are both true when the phone ships in
    // September). A render that can only crown one is wrong for every one of them.
    const section = resultsSection(render(settled()));
    expect(section.split(">Won<").length - 1).toBe(2);
  });

  test("the losers say Lost, and only the losers", () => {
    const section = resultsSection(render(settled()));
    expect(section.split(">Lost<").length - 1).toBe(2);
  });

  test("no rung prints a live-looking probability under Final Results", () => {
    // `settled means settled`. The blocked bytes printed the last traded price
    // beneath a "Final Results" heading, which reads as a live quote on a finished
    // question. The graded table prints 100%/0% + "Settled" instead.
    const section = resultsSection(render(settled()));
    expect(section).toContain("Settled");
  });

  test("🔴 THE GATE IS LOAD-BEARING: a settled market draws NO ladder", () => {
    // Deleting `if (market?.status === "resolved") return []` must fail HERE, not
    // somewhere subtle. Both directions asserted: the ladder's own chrome is gone
    // and the table's own chrome is present. Asserting only one of the two is how
    // a mutant survives.
    const html = render(settled());
    expect(html).not.toContain(LADDER_ONLY);
    expect(html).toContain(TABLE_ONLY);
  });
});

describe("🔴 the ship Q478 actually measured is preserved intact", () => {
  test("an OPEN quantity market still ladders — the 9,678 that were ever measured", () => {
    // The positive control for the gate above. A stand-down keyed on anything
    // coarser than status (say, "has no true winner") would silently un-ship item
    // 10 for every open market, since having no winner is what being open means.
    const html = render({ ...RAW, market_type: "quantity" });
    expect(html).toContain(LADDER_ONLY);
    expect(html).not.toContain(TABLE_ONLY);
  });

  test("its rungs keep ladder order, April first — item 10's whole point", () => {
    const html = render({ ...RAW, market_type: "quantity" });
    const at = (s: string) => html.indexOf(s);
    expect(at("Before April")).toBeLessThan(at("Before July"));
    expect(at("Before July")).toBeLessThan(at("Before October"));
    expect(at("Before October")).toBeLessThan(at("Before 2027"));
  });

  test("and no leaderboard chrome comes back with it", () => {
    // Alex's actual complaint: rank badges and avatar circles reading "BA", "BJ",
    // "BO", "B2" over one continuous question.
    const html = render({ ...RAW, market_type: "quantity" });
    for (const initials of [">BA<", ">BJ<", ">BO<", ">B2<"]) {
      expect(html).not.toContain(initials);
    }
    expect(html.split(">Before October<").length - 1).toBe(1);
  });

  test("🔴 is_winner is IGNORED on an open market, because false is the DEFAULT", () => {
    // The captured production payload is an OPEN market and all four of its
    // outcomes already read `is_winner: false`. Any gate that read that as "Lost"
    // would print four losers on a live question. 69 of 2,000 open quantity markets
    // even carry a TRUE winner (gotcha #33 — settled Kalshi markets keep
    // status='open'), so status is the only safe gate, exactly as `OutcomeRow`
    // already does it.
    expect(RAW_OUTCOMES.every((o) => o.is_winner === false)).toBe(true);
    const html = render({ ...RAW, market_type: "quantity" });
    expect(html).not.toContain(">Lost<");
    expect(html).not.toContain(">Won<");
  });
});

describe("the arms this repair must not disturb", () => {
  test("a settled FIELD market keeps its graded ranked table, untouched", () => {
    // The shape gate still decides; this repair must not reach a field market.
    const field = settled({
      market_type: "field",
      mutually_exclusive: true,
      outcomes: [
        { ...RAW_OUTCOMES[0], id: 1, name: "Amazon", probability: 0, is_winner: false },
        { ...RAW_OUTCOMES[0], id: 2, name: "Peacock", probability: 1, is_winner: true },
      ],
    });
    const html = render(field);
    expect(html).toContain(TABLE_ONLY);
    expect(html).toContain(">Peacock<");
    expect(html).toContain(">Won<");
  });

  test("a shape-less row still degrades to the old render, never to a blank", () => {
    // The pre-backfill rows serve no `market_type`.
    const html = render(RAW);
    expect(html).toContain("Before 2027");
    expect(html).toContain(TABLE_ONLY);
  });

  test("a settled market with no true winner renders the table, claiming nothing extra", () => {
    // 61.8% of resolved quantity markets have zero true winners, and because
    // `is_winner` defaults to FALSE that is indistinguishable from "never graded"
    // (gotcha #53 — one value answering two different questions). This repair does
    // not make that better, and it must not make it worse: the market takes the
    // same table it took before Q478 existed.
    const html = render(settled({ outcomes: RAW_OUTCOMES.map((o) => ({ ...o, is_winner: false })) }));
    expect(html).toContain(TABLE_ONLY);
    expect(html).not.toContain(LADDER_ONLY);
  });
});
