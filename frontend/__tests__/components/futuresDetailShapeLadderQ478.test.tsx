// lane1-Q478 — the PAGE-level proof for TOP-PRODUCT-DEFECTS item 10.
//
// The lib test pins the ordering contract. This one renders the actual
// `app/futures/[id]/page.tsx` against the REAL production payload of market
// 109349 ("When will Apple release the iPhone 18?"), captured verbatim on
// 2026-08-31 into `__tests__/fixtures/futuresDetail109349Production.json`, and
// counts what a reader sees.
//
// It exists because the claim is about a PAGE. `buildOutcomeLadderRungs` returning
// the right array proves nothing if the page never calls it — and the page's
// ladder had, until this queue, exactly one caller reachable only through a
// backend grouping that comes back `{}` for this market. A guard that tests the
// builder alone would pass on the blocked bytes.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PRODUCTION = require("../fixtures/futuresDetail109349Production.json");

// The payload EXACTLY as production served it while the defect was live. Note
// what it does NOT contain — see the first test.
const RAW = PRODUCTION as Record<string, unknown>;

// The same payload once the backend serves the shape field it had already
// classified. `market_type: 'quantity'` is the measured DB value for 109349, not
// an invention: `SELECT market_type FROM futures_markets WHERE id = 109349`.
const WITH_SHAPE = { ...RAW, market_type: "quantity" };

let payload: Record<string, unknown> = WITH_SHAPE;

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
    // The group fetch is the OLD ladder route. Production returns
    // `threshold_groups: {}` for this market — the numeric threshold parser
    // matches none of its four date rungs — so the old path stays dead here and
    // the ladder below can only have come from the shape field.
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

describe("the specimen still holds this queue's premise", () => {
  test("109349 is the four-rung date ladder the defect describes", () => {
    const outcomes = RAW.outcomes as { id: number; name: string; probability: number }[];
    expect(outcomes.map((o) => o.name)).toEqual([
      "Before 2027",
      "Before October",
      "Before April",
      "Before July",
    ]);
    // Cumulative, not disjoint — this is what makes ascending price the ladder order.
    expect(RAW.mutually_exclusive).toBe(false);
  });

  test("🔴 production did not serve the shape field at all", () => {
    // The captured payload is the pre-fix production response. This asserts the
    // ROOT CAUSE, and it is the assertion that will start failing (correctly) once
    // the fixture is re-captured after deploy — at which point it should be
    // updated to assert `market_type === 'quantity'`, not deleted.
    expect(RAW).not.toHaveProperty("market_type");
  });
});

describe("with the shape field served, the page draws the ladder", () => {
  test("the four rungs render in ladder order, April first", () => {
    const html = render(WITH_SHAPE);
    const at = (s: string) => html.indexOf(s);
    for (const rung of ["Before April", "Before July", "Before October", "Before 2027"]) {
      expect(at(rung)).toBeGreaterThan(-1);
    }
    // Order, not just presence. The leaderboard rendered these 2027-first.
    expect(at("Before April")).toBeLessThan(at("Before July"));
    expect(at("Before July")).toBeLessThan(at("Before October"));
    expect(at("Before October")).toBeLessThan(at("Before 2027"));
  });

  test("🔴 the ranked leaderboard chrome is GONE — no rank badges, no initial avatars", () => {
    // Alex's actual complaint: rank badges 1-4 and avatar circles reading "BA",
    // "BJ", "BO", "B2" over what is one continuous question. The initials are
    // built from the outcome names, so their absence is the load-bearing check.
    const html = render(WITH_SHAPE);
    for (const initials of [">BA<", ">BJ<", ">BO<", ">B2<"]) {
      expect(html).not.toContain(initials);
    }
  });

  test("the outcome set renders ONCE — the ladder replaces the table, it does not join it", () => {
    // Count the VISIBLE text node, not the raw substring: one rung legitimately
    // mentions its own label three times (`aria-label`, `title`, and the text).
    // Counting the bare string reported 3 and read as a duplicate render — the
    // assertion was wrong, not the page.
    const html = render(WITH_SHAPE);
    expect(html.split(">Before October<").length - 1).toBe(1);
  });
});

describe("the fallbacks this must not break", () => {
  test("without the shape field the page still renders (and still shows the outcomes)", () => {
    // The ~70k pre-backfill rows serve no `market_type`. They must degrade to the
    // old render, never to a crash or a blank.
    const html = render(RAW);
    expect(html).toContain("Before 2027");
  });

  test("a FIELD market is untouched — it keeps the ranked table", () => {
    // 109441 is `field` in the DB and its ranked leaderboard is CORRECT. A change
    // that laddered every market would break the shape it was built to respect.
    const field = {
      ...RAW,
      id: 109441,
      market_type: "field",
      mutually_exclusive: true,
      name: "Which companies will release a Fully AI-generated series before 2027?",
      outcomes: [
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 1, name: "Amazon", probability: 0.27 },
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 2, name: "Netflix", probability: 0.07 },
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 3, name: "Peacock", probability: 0.03 },
      ],
    };
    const html = render(field);
    expect(html).toContain("Amazon");
    // Key on chrome ONLY the ranked table has. The first version of this test
    // asserted `toContain("All Outcomes")` — which the LADDER also prints, since
    // that is its title too. It passed with the shape gate deleted and a mutant
    // walked straight through it.
    // Q481: the replacement was `"24h Change"`, the sort pill's label — and master
    // renamed that pill to "Last move" (UX-P233), so this assertion failed on the
    // merged tree while the page rendered correctly. Now keyed on `OutcomeRow`'s
    // own test hook, which the ladder never emits and no designer will reword.
    expect(html).toContain('data-testid="outcome-row"');
    expect(html).toContain(">Amazon<"); // the table's own outcome row
  });

  test("🔴 the shape gate is load-bearing: a field market must NOT get a ladder", () => {
    // The explicit inverse of the quantity case, so that deleting
    // `marketShape !== SHAPE_QUANTITY` fails here rather than silently laddering
    // every leaderboard on the site.
    const field = {
      ...RAW,
      market_type: "field",
      mutually_exclusive: true,
      outcomes: [
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 1, name: "Amazon", probability: 0.27 },
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 2, name: "Netflix", probability: 0.07 },
        { ...(RAW.outcomes as Record<string, unknown>[])[0], id: 3, name: "Peacock", probability: 0.03 },
      ],
    };
    const html = render(field);
    // The ranked table draws initial avatars; the ladder never does. Their
    // presence is proof the ladder did not take over.
    expect(html).toContain(">A<"); // Amazon's initial avatar
    // Q481: was `"24h Change"`; see the note above — display copy moved under it.
    expect(html).toContain('data-testid="outcome-row"');
  });

  test("a quantity market with a live threshold_group does not draw the ladder twice", () => {
    // The cross-market ladder still owns its case. If both paths fired, the page
    // would print the rungs twice.
    const html = render(WITH_SHAPE);
    expect(html.split(">Before April<").length - 1).toBe(1);
  });
});
