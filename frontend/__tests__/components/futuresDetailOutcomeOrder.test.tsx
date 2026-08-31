/**
 * UX-P230 — THE RENDERED ORDER, not the helper's return value.
 *
 * `__tests__/lib/futuresOutcomeSort.test.ts` proves the comparator obeys one
 * ascending convention. This file proves the PAGE obeys the comparator: it
 * SSR-renders the real `app/futures/[id]/page.tsx` against a verbatim production
 * payload and reads the order off the painted rows.
 *
 * The invariant, and it is the one a reader actually leans on:
 *
 *     Under the page's own default sort, the FIRST row is the outcome the hero
 *     is about.
 *
 * That is the assertion that would have caught this the day it shipped, and the
 * reason it is stated against the HERO rather than against a re-sorted copy of the
 * payload: the hero and the table are the two things a reader sees together, and
 * the defect was precisely that they disagreed. A guard that re-derived "the
 * leader" from the fixture would agree with a page that had moved the hero too.
 *
 * `leader` on the page is computed independently of `sortedOutcomes` (page.tsx
 * sorts a fresh copy `(b.probability) - (a.probability)` and takes `[0]`), so the
 * two really are separate producers — which is how they were able to disagree.
 *
 * ═══ WHAT SHIPPED BEFORE ═══
 *
 * Market 109441 rendered `3, 3, 4, 5, 5, 6, 7, 27` under a pill reading
 * "Probability ↓", with Amazon — the 27% subject of the hero directly above —
 * as the LAST of eight rows.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import market109441 from "../fixtures/uxp230_futures_109441.json";
import market109349 from "../fixtures/uxp230_futures_109349.json";

// The page reads `?utm_source` etc. off the search params; none are set here.
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

// Which market the swr mock serves. Set per test before rendering.
let ACTIVE_MARKET: unknown = market109441;

// Key-aware swr mock. Only the market envelope matters here; every other fetch
// (history, related events, progression, group) resolves empty so the outcome
// table is rendered from the payload and nothing else.
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
  usePinnedFutures: () => ({
    isPinned: () => false,
    togglePin: () => {},
    isMaxReached: false,
  }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FuturesDetailPage from "../../app/futures/[id]/page";

/** The rendered row order, read off the painted markup. */
function renderedOutcomeNames(html: string): string[] {
  const names: string[] = [];
  const re = /data-outcome-name="([^"]*)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    names.push(
      m[1]
        .replace(/&quot;/g, '"')
        .replace(/&#x27;/g, "'")
        .replace(/&amp;/g, "&"),
    );
  }
  return names;
}

function render(market: unknown, id: string): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id }} />);
}

describe("UX-P230: the futures table's first row is the hero's leader", () => {
  test("the harness renders the real table (positive control)", () => {
    // A guard that silently rendered a loading shell would pass every assertion
    // below vacuously. Prove the table is on the page first.
    const html = render(market109441, "109441");
    expect(html).toContain("All Outcomes");
    expect(renderedOutcomeNames(html)).toHaveLength(8);
    // And the sort pill really is claiming descending probability.
    expect(html).toContain("Probability");
  });

  test("109441: Amazon is the FIRST row, not the last", () => {
    const html = render(market109441, "109441");
    const rows = renderedOutcomeNames(html);
    expect(rows[0]).toBe("Amazon");
    expect(rows[rows.length - 1]).not.toBe("Amazon");
  });

  test("109441: the hero's outcome and the first row name the same thing", () => {
    const html = render(market109441, "109441");
    const rows = renderedOutcomeNames(html);

    // The hero's subject, read from the payload the way the page reads it: the
    // highest-probability outcome. On this market it is not a generic label, so
    // the hero prints the name verbatim and we can see it in the markup.
    const outcomes = market109441.outcomes as { name: string; probability: number | null }[];
    const heroName = [...outcomes].sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))[0]
      .name;
    expect(html).toContain(heroName);

    // The whole defect in one line.
    expect(rows[0]).toBe(heroName);
  });

  test("109441: the rendered rows descend by probability, top to bottom", () => {
    const html = render(market109441, "109441");
    const rows = renderedOutcomeNames(html);
    const byName = new Map(
      (market109441.outcomes as { name: string; probability: number | null }[]).map((o) => [
        o.name,
        o.probability ?? 0,
      ]),
    );
    const rendered = rows.map((n) => byName.get(n) ?? 0);
    expect(rendered.map((p) => Math.round(p * 100))).toEqual([27, 7, 6, 5, 5, 4, 3, 3]);
    for (let i = 1; i < rendered.length; i++) {
      expect(rendered[i - 1]).toBeGreaterThanOrEqual(rendered[i]);
    }
  });

  test("the page SORTS — it does not merely pass the payload's order through", () => {
    // Production hands `/api/futures/<id>` back already descending by probability,
    // so a page that dropped the sort entirely would still render 109441 correctly
    // and every assertion above would pass vacuously. Feed it the same eight
    // outcomes in a deliberately wrong order and require the page to fix them.
    const shuffled = {
      ...market109441,
      outcomes: [...(market109441.outcomes as { name: string }[])].reverse(),
    };
    expect((shuffled.outcomes as { name: string }[])[0].name).toBe("Peacock"); // wrong on arrival

    const rows = renderedOutcomeNames(render(shuffled, "109441"));
    expect(rows).toHaveLength(8);
    expect(rows[0]).toBe("Amazon");
    expect(rows[rows.length - 1]).toBe("Peacock");
  });

  test("109349: 'Before 2027' at 15% leads the table", () => {
    // Second market, and a different hero path: every outcome name here is
    // date-shaped, so the hero prints "Yes" rather than the name. The table is
    // still required to lead with the leader.
    const html = render(market109349, "109349");
    const rows = renderedOutcomeNames(html);
    expect(rows).toHaveLength(4);
    expect(rows[0]).toBe("Before 2027");
    const byName = new Map(
      (market109349.outcomes as { name: string; probability: number | null }[]).map((o) => [
        o.name,
        o.probability ?? 0,
      ]),
    );
    expect(rows.map((n) => Math.round((byName.get(n) ?? 0) * 100))).toEqual([15, 7, 1, 1]);
  });
});
