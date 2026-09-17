/**
 * #4568 — FIVE NAMED, RANKED, NUMBERLESS ROWS AT THE FOOT OF A CHAMPIONSHIP LADDER.
 *
 * Measured on production 2026-09-17 20:2xZ, `bainluck.com/futures/114175` at
 * 390px (`artifacts/ux-1317/shop-futures-114175-390.png`,
 * `crop-placeholders.png`) — "Who will be UFC Heavyweight champion at the end of
 * 2026?", ranks 15-19 of ALL OUTCOMES:
 *
 *     14  Rizvan Kuniev   LAST MOVE  -   LATEST  <1%
 *     15  Fighter E       LAST MOVE  -   LATEST  -
 *     16  Fighter D       LAST MOVE  -   LATEST  -
 *     17  Other           LAST MOVE  -   LATEST  -
 *     18  Fighter F       LAST MOVE  -   LATEST  -
 *     19  Fighter G       LAST MOVE  -   LATEST  -
 *
 * Standing notice 37 / D102 (Alex, 2026-09-09): "Untraded or vanished props go
 * behind a collapsed toggle — present, openable, taking no real estate when
 * closed." D111 (2026-09-10) then overruled the WORDING to a neutral "More
 * props (N)". The label here is that ruling's, not this issue's title.
 *
 * ═══ WHY THE PAGE NEVER FOLDED THEM, which #4568 asked and nobody answered ═══
 *
 * Its only collapse is `slice(0, 25)` — an overflow cap blind to price. Of the
 * four payloads in the issue, `11020528` serves 36 outcomes with ONE null leg
 * (the cap hides rows 26-36, that leg among them, so the page LOOKED like it
 * folded) while `108559` 22/2, `108555` 22/5 and `114175` 19/5 are all under 25
 * and rendered every numberless row. The page that appeared to have D102's
 * toggle was a coincidence of length.
 *
 * ═══ THE ASSERTION TRAP THIS SHIP HAS, AND IT IS THE WHOLE FILE ═══
 *
 * 🪤 `<details>` renders its contents into the markup. They are collapsed by the
 * BROWSER, not omitted by React. So `expect(html).toContain("Fighter E")` passes
 * before AND after, and `expect(html).not.toContain("Fighter E")` would demand a
 * deletion D102 explicitly forbids (gotcha #43: collapsed, never dropped).
 * Neither is the claim.
 *
 * The claim is POSITIONAL — which side of the disclosure a row is on — so every
 * assertion below splits the markup at the `<details>` boundary and asks about
 * the two halves. That is the only shape that can tell "folded" from "deleted"
 * and from "unchanged". Same family as ux/1316's `visibleText()` and ux/1301's
 * `26%` matching `width:26%`: assert the thing you mean, not a substring that
 * happens to co-occur with it.
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
import { partitionOutcomesByPrice } from "@/lib/futuresDetailDisplay";

/* ────────────────────────────── the harness ────────────────────────────── */

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

const FOLD_MARKER = 'data-testid="futures-more-outcomes"';
const LADDER_FOLD_MARKER = 'data-testid="futures-more-rungs"';

/**
 * The markup either side of the disclosure.
 *
 * `beforeFold` is what a reader sees without opening anything; `insideFold` is
 * what the toggle reveals. A row must be in exactly one of them, and WHICH one
 * is the entire subject of this issue.
 */
function splitAtFold(html: string): { beforeFold: string; insideFold: string } {
  const at = html.indexOf(FOLD_MARKER);
  if (at === -1) return { beforeFold: html, insideFold: "" };
  return { beforeFold: html.slice(0, at), insideFold: html.slice(at) };
}

/** The production ladder, with the five served stamps and ranks it really has. */
function ufcHeavyweight() {
  const priced = [
    ["Ciryl Gane", 0.655, 1],
    ["Josh Hokit", 0.2, 2],
    ["Alexander Volkov", 0.0415, 3],
    ["Tom Aspinall", 0.0145, 4],
    ["Sergei Pavlovich", 0.0095, 5],
    ["Curtis Blaydes", 0.0005, 6],
    ["Jailton Almeida", 0.0005, 7],
    ["Tyrell Fortune", 0.0005, 8],
    ["Waldo Cortes Acosta", 0.0005, 9],
    ["Serghei Spivac", 0.0005, 10],
    ["Derrick Lewis", 0.0005, 11],
    ["Ante Delija", 0.0005, 12],
    ["Marcin Tybura", 0.0005, 13],
    ["Rizvan Kuniev", 0.0005, 14],
  ] as const;
  // 🔴 `probability: null`, NOT 0. A zero prints "0%" and is a claim; these rows
  // have never carried a price, which is why they print "-" (lib/api.ts:799).
  const numberless = [
    ["Fighter E", 15],
    ["Fighter D", 16],
    ["Other", 17],
    ["Fighter F", 18],
    ["Fighter G", 19],
  ] as const;
  return {
    id: 114175,
    name: "Who will be UFC Heavyweight champion at the end of 2026?",
    status: "open",
    source: "polymarket",
    category: "championship",
    llm_sport_category: "mma",
    market_type: "field",
    mutually_exclusive: true,
    outcome_count: 19,
    bookmakers: ["polymarket"],
    resolution_date: "2026-12-31T00:00:00+00:00",
    updated_at: "2026-07-21T17:15:45.265591+00:00",
    outcomes: [
      ...priced.map(([name, probability, rank], i) => ({
        id: 900 + i,
        name: name as string,
        probability: probability as number | null,
        rank: rank as number,
        opening_probability: null,
        probability_change_24h: null,
        american_odds: null,
        opening_american_odds: null,
        is_winner: null,
        resolution_source: null,
        last_updated: "2026-09-17T19:50:18.481336+00:00",
      })),
      ...numberless.map(([name, rank], i) => ({
        id: 950 + i,
        name: name as string,
        probability: null as number | null,
        rank: rank as number,
        opening_probability: null,
        probability_change_24h: null,
        american_odds: null,
        opening_american_odds: null,
        is_winner: null,
        resolution_source: null,
        last_updated: "2026-05-12T16:16:06.970740+00:00",
      })),
    ],
  };
}

/* ───────────────────────────────── the rule ───────────────────────────────── */

describe("partitionOutcomesByPrice", () => {
  it("folds the rows with no probability and lists the rest", () => {
    const { listed, folded } = partitionOutcomesByPrice(
      ufcHeavyweight().outcomes,
    );
    expect(listed).toHaveLength(14);
    expect(folded.map((o) => o.name)).toEqual([
      "Fighter E",
      "Fighter D",
      "Other",
      "Fighter F",
      "Fighter G",
    ]);
  });

  it("keeps a genuine 0 in the listed half — 0% is a claim, absence is not", () => {
    const { listed, folded } = partitionOutcomesByPrice([
      { probability: 0 },
      { probability: null },
    ]);
    expect(listed).toEqual([{ probability: 0 }]);
    expect(folded).toEqual([{ probability: null }]);
  });

  it("preserves the incoming order within each half", () => {
    const { listed } = partitionOutcomesByPrice([
      { probability: 0.1, name: "a" },
      { probability: null, name: "b" },
      { probability: 0.2, name: "c" },
    ] as Array<{ probability: number | null; name: string }>);
    expect(listed.map((o) => o.name)).toEqual(["a", "c"]);
  });

  it("returns empty halves for an empty ladder rather than throwing", () => {
    expect(partitionOutcomesByPrice([])).toEqual({ listed: [], folded: [] });
  });
});

/* ─────────────────────────────── the wiring ─────────────────────────────── */

describe("#4568 — the ALL OUTCOMES ladder on /futures/114175", () => {
  it("draws the disclosure, naming its own count", () => {
    const html = render(ufcHeavyweight(), "114175");
    expect(html).toContain(FOLD_MARKER);
    expect(html).toContain("More outcomes (5)");
  });

  it("puts every numberless row BEHIND the disclosure, not in the open list", () => {
    const { beforeFold, insideFold } = splitAtFold(
      render(ufcHeavyweight(), "114175"),
    );
    for (const name of ["Fighter E", "Fighter D", "Fighter F", "Fighter G"]) {
      expect(insideFold).toContain(name);
      expect(beforeFold).not.toContain(name);
    }
  });

  it("keeps every PRICED row in the open list — the fold is not a truncation", () => {
    const { beforeFold, insideFold } = splitAtFold(
      render(ufcHeavyweight(), "114175"),
    );
    // Both ends of the priced ladder, including the 14th row that sat directly
    // above the placeholders and is the one a truncating "fix" would eat.
    for (const name of ["Ciryl Gane", "Josh Hokit", "Rizvan Kuniev"]) {
      expect(beforeFold).toContain(name);
      expect(insideFold).not.toContain(name);
    }
  });

  it("folds rather than deletes — the rows are still in the document (gotcha #43)", () => {
    const html = render(ufcHeavyweight(), "114175");
    for (const name of ["Fighter E", "Other", "Fighter G"]) {
      expect(html).toContain(name);
    }
  });

  it("keeps the served rank, so the numbering never restarts at 1", () => {
    const { insideFold } = splitAtFold(render(ufcHeavyweight(), "114175"));
    // 15-19 as served. A fold that renumbered its own contents would print 1-5
    // and tell the reader these are the top five of something.
    for (const rank of ["15", "16", "17", "18", "19"]) {
      expect(insideFold).toContain(rank);
    }
  });

  it("draws NO disclosure when every row carries a price", () => {
    const market = ufcHeavyweight();
    market.outcomes = market.outcomes.filter((o) => o.probability != null);
    const html = render(market, "114175");
    expect(html).not.toContain(FOLD_MARKER);
    expect(html).not.toContain("More outcomes");
  });

  /**
   * The counters are claims about the list the reader is looking at. Folding
   * five rows out of a 19-row ladder while "Show all 19" still stands would make
   * the button reveal fourteen rows — the fold's own second defect, and the one
   * a reviewer is least likely to look for.
   */
  it("counts the OPEN list, not the whole ladder, in the show-all control", () => {
    const market = ufcHeavyweight();
    const base = market.outcomes.filter((o) => o.probability != null);
    // 30 priced + the 5 numberless: over the 25-cap, so the control appears.
    market.outcomes = [
      ...Array.from({ length: 30 }, (_, i) => ({
        ...base[0],
        id: 2000 + i,
        name: `Contender ${i}`,
        probability: 0.01,
        rank: i + 1,
      })),
      ...market.outcomes.filter((o) => o.probability == null),
    ];
    const html = render(market, "114175");
    expect(html).toContain("Show all 30");
    expect(html).not.toContain("Show all 35");
    expect(html).toContain("Show 5 more outcomes");
    expect(html).toContain("More outcomes (5)");
  });
});

/* ───────────────────── the OTHER renderer, and why it is here ───────────────────── */

/**
 * 🔴 THE PAGE DRAWS ITS OUTCOME SET THROUGH TWO DIFFERENT COMPONENTS, CHOSEN BY
 * MARKET SHAPE, AND #4568's OWN SPECIMENS ARE ON THE ONE THE RANKED TABLE IS NOT.
 *
 * `114175` is a `field` market and renders the ranked table asserted above.
 * `108555` ("When will Starlink officially announce an IPO?") is a `quantity`
 * market, so `hasOwnLadder` is true and the table is suppressed entirely — its
 * five numberless rungs are drawn by `QuantityGroup`. Photographed still bare on
 * production at 2026-09-17 20:4xZ, AFTER the table half was written:
 * `artifacts/ux-1317/crop-108555-outcomes.png`.
 *
 * So a fix to either renderer alone leaves the issue live on half its evidence,
 * and the half it leaves live is the half the issue was actually filed about.
 * Both call `partitionOutcomesByPrice` — one rule, two wirings (notice 35;
 * ux/1316's mutants A and B are the same lesson one surface over).
 */
function starlinkIpo() {
  const priced = [
    ["Before May 1, 2026", 0.01],
    ["Before Apr 1, 2026", 0.01],
    ["Before Nov 1, 2026", 0.01],
    ["Before Jun 30, 2027", 0.06],
  ] as const;
  const numberless = [
    "Before Nov 1, 2025",
    "Before Sep 1, 2025",
    "Before Dec 1, 2025",
    "Before Oct 1, 2025",
    "Before Jan 1, 2026",
  ] as const;
  return {
    id: 108555,
    name: "When will Starlink officially announce an IPO?",
    status: "open",
    source: "kalshi",
    category: "championship",
    market_type: "quantity",
    // 🔴 FALSE is what makes this a cumulative ladder (`ladderOrderFor`), which
    // is what makes `hasOwnLadder` true and suppresses the ranked table.
    mutually_exclusive: false,
    outcome_count: 9,
    bookmakers: ["kalshi"],
    resolution_date: "2027-06-30T00:00:00+00:00",
    outcomes: [
      ...priced.map(([name, probability], i) => ({
        id: 1593052 + i,
        name: name as string,
        probability: probability as number | null,
        rank: i + 1,
        opening_probability: null,
        probability_change_24h: null,
        american_odds: null,
        opening_american_odds: null,
        is_winner: null,
        resolution_source: null,
        last_updated: "2026-09-17T19:50:18.481336+00:00",
      })),
      ...numberless.map((name, i) => ({
        id: 1593032 + i,
        name: name as string,
        probability: null as number | null,
        rank: 18 + i,
        opening_probability: null,
        probability_change_24h: null,
        american_odds: null,
        opening_american_odds: null,
        is_winner: null,
        resolution_source: null,
        last_updated: "2026-05-12T16:16:06.970740+00:00",
      })),
    ],
  };
}

function splitAtLadderFold(html: string): { beforeFold: string; insideFold: string } {
  const at = html.indexOf(LADDER_FOLD_MARKER);
  if (at === -1) return { beforeFold: html, insideFold: "" };
  return { beforeFold: html.slice(0, at), insideFold: html.slice(at) };
}

describe("#4568 — the QUANTITY LADDER on /futures/108555", () => {
  it("renders the ladder, not the ranked table — the fixture proves the branch", () => {
    const html = render(starlinkIpo(), "108555");
    // The table's own fold must be absent, or this suite would be asserting the
    // same renderer twice and calling it two.
    expect(html).not.toContain(FOLD_MARKER);
    expect(html).toContain(LADDER_FOLD_MARKER);
  });

  it("puts every numberless rung BEHIND the disclosure", () => {
    const { beforeFold, insideFold } = splitAtLadderFold(
      render(starlinkIpo(), "108555"),
    );
    for (const label of [
      "Before Nov 1, 2025",
      "Before Sep 1, 2025",
      "Before Dec 1, 2025",
      "Before Oct 1, 2025",
    ]) {
      expect(insideFold).toContain(label);
      expect(beforeFold).not.toContain(label);
    }
    expect(insideFold).toContain("More outcomes (5)");
  });

  it("keeps every priced rung in the open ladder", () => {
    const { beforeFold, insideFold } = splitAtLadderFold(
      render(starlinkIpo(), "108555"),
    );
    for (const label of ["Before May 1, 2026", "Before Jun 30, 2027"]) {
      expect(beforeFold).toContain(label);
      expect(insideFold).not.toContain(label);
    }
  });

  it("draws NO ladder disclosure when every rung carries a price", () => {
    const market = starlinkIpo();
    market.outcomes = market.outcomes.filter((o) => o.probability != null);
    const html = render(market, "108555");
    expect(html).not.toContain(LADDER_FOLD_MARKER);
    expect(html).not.toContain("More outcomes");
  });
});
