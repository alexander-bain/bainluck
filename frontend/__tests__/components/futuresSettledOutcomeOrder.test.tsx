/**
 * UX-P232 — THE RENDERED ORDER ON A SETTLED PAGE.
 *
 * `__tests__/lib/futuresSettledOutcomeSort.test.ts` proves the rule. This file
 * proves the PAGE obeys it, by SSR-rendering the real `app/futures/[id]/page.tsx`
 * against a verbatim production payload and reading the order off the painted rows
 * — the same shape as UX-P230's `futuresDetailOutcomeOrder.test.tsx`, which covers
 * the OPEN half.
 *
 * Both halves are needed and neither substitutes for the other: CERT-598's block
 * was not that the comparator was wrong, but that the page never handed it the one
 * fact it needed. A helper test alone cannot see an argument the page fails to pass.
 *
 * ═══ WHAT SHIPPED BEFORE ═══
 *
 * Market 59748620 ("Arsenal vs Coventry: First Goalscorer", resolved) renders a
 * hero reading **Kai Havertz — Won**, and directly beneath it a section headed
 * **"Final Results"** whose first row was **Christos Tzolis at 99%, who did not
 * score**. Havertz was row three.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import resolvedMarket from "../fixtures/uxp232_futures_59748620_resolved.json";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = resolvedMarket;

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

const WINNER = "Kai Havertz";
const PRICE_LEADER = "Christos Tzolis";

describe("UX-P232: a settled futures page paints the winner first", () => {
  test("the harness renders the real SETTLED table (positive control)", () => {
    // A loading shell, or a page that failed to read this market as resolved,
    // would pass every assertion below vacuously. Prove the settled table first.
    const html = render(resolvedMarket, "59748620");
    expect(html).toContain("Final Results");
    expect(html).not.toContain("All Outcomes");
    expect(renderedOutcomeNames(html)).toHaveLength(13);
  });

  test("the first painted row is the winner, not the 99% loser", () => {
    const rows = renderedOutcomeNames(render(resolvedMarket, "59748620"));
    expect(rows[0]).toBe(WINNER);
    expect(rows[1]).toBe(PRICE_LEADER);
  });

  test("the hero and the first row name the same person — the whole defect", () => {
    const html = render(resolvedMarket, "59748620");
    const rows = renderedOutcomeNames(html);

    // The hero's subject on a resolved market is the GRADED WINNER, read from the
    // payload the way `pickHeroOutcome` reads it.
    const outcomes = resolvedMarket.outcomes as { name: string; is_winner?: boolean | null }[];
    const heroName = outcomes.find((o) => o.is_winner === true)?.name;
    expect(heroName).toBe(WINNER);
    expect(html).toContain(heroName as string);

    expect(rows[0]).toBe(heroName);
  });

  test("the page SORTS a settled payload — it does not pass the arrival order through", () => {
    // Production hands this market back with Tzolis first, so a page that dropped
    // the settled ordering would already be wrong; but a page that dropped ALL
    // sorting could still look right on some other payload. Shuffle so the winner
    // arrives LAST and require the page to lift him.
    const shuffled = {
      ...resolvedMarket,
      outcomes: [...(resolvedMarket.outcomes as { name: string }[])].reverse(),
    };
    const arriving = (shuffled.outcomes as { name: string }[]).map((o) => o.name);
    expect(arriving[arriving.length - 1]).toBe(PRICE_LEADER);
    expect(arriving.indexOf(WINNER)).toBeGreaterThan(0); // not already first

    const rows = renderedOutcomeNames(render(shuffled, "59748620"));
    expect(rows).toHaveLength(13);
    expect(rows[0]).toBe(WINNER);
  });

  test("the same market rendered OPEN leads with the price leader again", () => {
    // The negative control that pins the gate to `market.status`. If the page
    // started keying the winner-first rule off `is_winner` alone, this row would
    // move — and a live market would be claiming a result it does not have.
    const asOpen = { ...resolvedMarket, status: "open" };
    const rows = renderedOutcomeNames(render(asOpen, "59748620"));
    expect(rows[0]).toBe(PRICE_LEADER);
    expect(rows.indexOf(WINNER)).toBeGreaterThan(0);
  });
});
