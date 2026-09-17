// #4568, second half — the PAGE-level proof.
//
// The lib test pins the tie-break contract. This one renders the actual
// `app/futures/[id]/page.tsx` against the REAL production payload of market
// 108559 ("When will OpenAI officially announce an IPO?") — the market the issue
// was filed about — captured verbatim on 2026-09-17 into
// `__tests__/fixtures/futuresDetail108559Production.json`, and reads the order a
// reader gets.
//
// It exists because a builder's green lib test proves nothing about a page that
// does not call the builder, and this page has TWO outcome renderers chosen by
// market shape (ux/1317 shipped the numberless fold into both for exactly this
// reason). 108559 is the `quantity` branch: `hasOwnLadder` is true, the ranked
// table is suppressed entirely, and `QuantityGroup` draws the rungs off
// `buildOutcomeLadderRungs`. If that call is ever removed or its `value` dropped,
// the component re-sorts and these assertions are what says so.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PRODUCTION = require("../fixtures/futuresDetail108559Production.json");

const PAYLOAD = PRODUCTION as Record<string, unknown>;

let payload: Record<string, unknown> = PAYLOAD;

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
        data: { group_id: PAYLOAD.group_id, markets: [], threshold_groups: {} },
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
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "108559" }} />);
}

/** The eleven rungs production prices at exactly 1%, in the order it serves them. */
const TIED_IN_SERVE_ORDER = [
  "Before Jan 1, 2026",
  "Before Oct 1, 2025",
  "Before Apr 1, 2026",
  "Before Feb 1, 2026",
  "Before Mar 1, 2026",
  "Before May 1, 2026",
  "Before Jul 1, 2026",
  "Before Aug 1, 2026",
  "Before Sep 1, 2026",
  "Before Oct 1, 2026",
  "Before Jun 1, 2026",
];

const CHRONOLOGICAL = [
  "Before Oct 1, 2025",
  "Before Jan 1, 2026",
  "Before Feb 1, 2026",
  "Before Mar 1, 2026",
  "Before Apr 1, 2026",
  "Before May 1, 2026",
  "Before Jun 1, 2026",
  "Before Jul 1, 2026",
  "Before Aug 1, 2026",
  "Before Sep 1, 2026",
  "Before Oct 1, 2026",
];

describe("the specimen still holds the premise", () => {
  test("108559 is a cumulative quantity ladder with eleven rungs tied at 1%", () => {
    const outcomes = PAYLOAD.outcomes as { name: string; probability: number | null }[];
    expect(PAYLOAD.market_type).toBe("quantity");
    expect(PAYLOAD.mutually_exclusive).toBe(false);
    expect(outcomes.filter((o) => o.probability === 0.01).map((o) => o.name)).toEqual(
      TIED_IN_SERVE_ORDER,
    );
    // Half the ladder. This is why the tie-break is the whole defect.
    expect(outcomes.length).toBe(22);
  });
});

describe("the page renders the tied block as a timeline", () => {
  test("🔴 the eleven tied rungs appear in calendar order", () => {
    const html = render(PAYLOAD);
    const at = (s: string) => {
      const i = html.indexOf(s);
      expect(i).toBeGreaterThan(-1); // every rung is on the page — nothing dropped
      return i;
    };
    const positions = CHRONOLOGICAL.map(at);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  test("🔴 and that order is NOT the serve order the payload arrived in", () => {
    // The non-vacuity control. Without it, a page that simply echoed the payload
    // would pass the test above on any ladder that happened to be sorted.
    const html = render(PAYLOAD);
    const served = TIED_IN_SERVE_ORDER.map((s) => html.indexOf(s));
    expect(served).not.toEqual([...served].sort((a, b) => a - b));
  });

  test("the price still decides where two rungs are priced differently", () => {
    // 108559 quotes "Before Dec 1, 2025" at 2% over "Before Oct 1, 2026" at 1% —
    // incoherent (the earlier window nests inside the later one), and NOT this
    // ship's to sort away. The reader keeps seeing what the book says.
    const html = render(PAYLOAD);
    expect(html.indexOf("Before Oct 1, 2026")).toBeLessThan(
      html.indexOf("Before Dec 1, 2025"),
    );
    // And the top of the ladder is still the likeliest rung, by price.
    expect(html.indexOf("Before May 1, 2027")).toBeLessThan(
      html.indexOf("Before Jun 1, 2027"),
    );
  });

  test("the ladder renders, not the ranked table", () => {
    // If the shape gate ever flips this market to the leaderboard, the tie-break
    // above is unreachable and these assertions would be measuring a page that no
    // longer exists. `OutcomeRow`'s hook is the table's own, never the ladder's.
    const html = render(PAYLOAD);
    expect(html).not.toContain('data-testid="outcome-row"');
    expect(html).toContain("All Outcomes");
  });
});
