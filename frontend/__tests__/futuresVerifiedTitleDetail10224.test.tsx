/**
 * #10224 — the web NFL title detail renders the verified server response.
 *
 * Rendered through the real page over the server's own route output for
 * 86832 (the sportsbook board) — see
 * `__tests__/lib/verifiedTitleDetail10224.test.ts` for fixture provenance.
 * Hero: the shown outcome's value and ITS contributors. Chart: the requested
 * source's history under the timeline's own label, with /history never asked.
 * Controls: an opted-in page the server refused, and a single-contributor hero.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsRefused from "./fixtures/verifiedTitle10224/detail-odds-refused.json";
import oddsTimeline from "./fixtures/verifiedTitle10224/timeline-odds-verified.json";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let MARKET: unknown = null;
const KEYS: unknown[][] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    const k = key as unknown[];
    KEYS.push(k);
    if (k[0] === "futures-market") return { data: MARKET, error: undefined, isLoading: false, mutate: () => {} };
    if (k[0] === "futures-verified-timeline") {
      return {
        data: { marketId: k[1], hours: k[2], payload: structuredClone(oddsTimeline) },
        error: undefined, isLoading: false, isValidating: false, mutate: () => {},
      };
    }
    if (k[0] === "futures-history") {
      return { data: { market_id: 86832, market_name: "x", hours: 168, outcomes: [] }, error: undefined, isLoading: false, mutate: () => {} };
    }
    return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
  },
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));
jest.mock("@/hooks/useMarketStream", () => ({ useMarketStream: () => {} }));

import FuturesDetailPage from "../app/futures/[id]/page";

function render(market: unknown): string {
  MARKET = market;
  KEYS.length = 0;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "86832" }} />);
}
const text = (html: string, testid: string) => {
  const m = html.match(new RegExp(`data-testid="${testid}"[^>]*>([\\s\\S]*?)</(?:div|p|span)>`));
  return m ? m[1].replace(/<[^>]+>/g, "") : null;
};
/** The hero footer's label: the span after its dots row. */
const heroContributors = (html: string) => {
  const at = html.indexOf('data-testid="hero-contributors"');
  if (at < 0) return null;
  const rest = html.slice(at);
  const afterDots = rest.slice(rest.indexOf("</div>") + "</div>".length);
  return afterDots.slice(0, afterDots.indexOf("</div>")).replace(/<[^>]+>/g, "");
};

describe("#10224 verified title detail", () => {
  it("asks for verified detail under its own key, and the timeline — never /history", () => {
    render(structuredClone(oddsVerified));
    expect(KEYS.some((k) => k[0] === "futures-market" && k[2] === "verified_title")).toBe(true);
    expect(KEYS.some((k) => k[0] === "futures-verified-timeline" && k[1] === 86832)).toBe(true);
    expect(KEYS.some((k) => k[0] === "futures-history")).toBe(false);
  });

  it("the hero prints the verified value with the shown outcome's contributors", () => {
    const html = render(structuredClone(oddsVerified));
    expect(text(html, "hero-percent")).toBe("13");
    expect(heroContributors(html)).toBe("Blended from Sportsbooks · Kalshi · Polymarket");
    expect(html).not.toContain("Aggregated from");
    // Notice 33: the sportsbook venue is "Sportsbooks", never bare "books".
    expect(html).not.toMatch(/\bbooks\b/i);
  });

  it("the chart names its authentic history from the timeline response", () => {
    const html = render(structuredClone(oddsVerified));
    expect(text(html, "futures-trend-history-basis")).toBe("Sportsbooks history");
    expect(html).toContain("Buffalo Bills");
  });

  it("a single contributor reads as one source, not a blend", () => {
    const market = structuredClone(oddsVerified) as { outcomes: { contributing_sources: string[] }[] };
    market.outcomes[0].contributing_sources = ["kalshi"];
    const html = render(market);
    expect(heroContributors(html)).toBe("From Kalshi");
    expect(html).not.toContain("Blended from");
  });

  it("CONTROL: an opted-in page the server refused renders source mode, as before", () => {
    const html = render(structuredClone(oddsRefused));
    expect(html).not.toContain('data-testid="hero-contributors"');
    expect(html).not.toContain('data-testid="futures-trend-history-basis"');
    expect(KEYS.some((k) => k[0] === "futures-history" && k[1] === 86832)).toBe(true);
    expect(KEYS.some((k) => k[0] === "futures-verified-timeline")).toBe(false);
  });
});
