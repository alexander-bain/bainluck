/**
 * #10224 — the web NFL title detail renders the verified server response.
 *
 * Rendered through the real page over the server's own route output for
 * 86832 (the sportsbook board) — see
 * `__tests__/lib/verifiedTitleDetail10224.test.ts` for fixture provenance.
 * Hero: the shown outcome's value and ITS contributors. Chart: the market's own
 * `/history` (#10244 — never the raw-median timeline) under its source's label.
 * Games This Week: the table's verified number per outcome id (#10243).
 * Controls: an opted-in page the server refused, and a single-contributor hero.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import oddsVerified from "./fixtures/verifiedTitle10224/detail-odds-verified.json";
import oddsRefused from "./fixtures/verifiedTitle10224/detail-odds-refused.json";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let MARKET: unknown = null;
/** `/history`'s consensus series, the shape the source page has always drawn. */
const point = (h: number, p: number) => ({
  timestamp: new Date(Date.UTC(2026, 9, 2, h)).toISOString(), probability: p, american_odds: null, bookmaker: "consensus",
});
const HISTORY = {
  market_id: 86832, market_name: "x", hours: 168, total_data_points: 24, sparse: false,
  outcomes: [
    { outcome_id: 1309486, name: "Buffalo Bills", history: Array.from({ length: 12 }, (_, h) => point(h, 0.1125)) },
    { outcome_id: 1309485, name: "Los Angeles Rams", history: Array.from({ length: 12 }, (_, h) => point(h, 0.11)) },
  ],
};
/** `/related-events` as production served it on 86832: SOURCE values (#10243). */
const RELATED = {
  market_id: 86832,
  market_name: "x",
  events: [
    {
      event_id: 1, home_team: "Los Angeles Rams", away_team: "Buffalo Bills",
      commence_time: "2099-10-04T20:25:00Z", status: "scheduled", sport: "americanfootball_nfl",
      home_score: null, away_score: null,
      linked_teams: [
        { side: "home", team_name: "Los Angeles Rams", outcome_id: 1309485, outcome_name: "Los Angeles Rams",
          probability: 0.107361, american_odds: 831, rank: 2, outcome_is_team: true },
        { side: "away", team_name: "Buffalo Bills", outcome_id: 1309486, outcome_name: "Buffalo Bills",
          probability: 0.112913, american_odds: 786, rank: 1, outcome_is_team: true },
      ],
    },
  ],
};
const KEYS: unknown[][] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    const k = key as unknown[];
    KEYS.push(k);
    if (k[0] === "futures-market") return { data: MARKET, error: undefined, isLoading: false, mutate: () => {} };
    if (k[0] === "futures-history") {
      return { data: structuredClone(HISTORY), error: undefined, isLoading: false, mutate: () => {} };
    }
    if (k[0] === "futures-related-events") return { data: RELATED, error: undefined, isLoading: false, mutate: () => {} };
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
/** Tags stripped by a character scan, not a regex replace (CodeQL's
 * incomplete-sanitization rule — same helper as futuresBaselineRender.test). */
function stripTags(html: string): string {
  let out = "";
  let inTag = false;
  for (const ch of html) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out;
}
const text = (html: string, testid: string) => {
  const m = html.match(new RegExp(`data-testid="${testid}"[^>]*>([\\s\\S]*?)</(?:div|p|span)>`));
  return m ? stripTags(m[1]) : null;
};
/** The hero footer's label: the span after its dots row. */
const heroContributors = (html: string) => {
  const at = html.indexOf('data-testid="hero-contributors"');
  if (at < 0) return null;
  const rest = html.slice(at);
  const afterDots = rest.slice(rest.indexOf("</div>") + "</div>".length);
  return stripTags(afterDots.slice(0, afterDots.indexOf("</div>")));
};

describe("#10224 verified title detail", () => {
  it("asks for verified detail under its own key, and draws /history — never the raw-median timeline (#10244)", () => {
    render(structuredClone(oddsVerified));
    expect(KEYS.some((k) => k[0] === "futures-market" && k[2] === "verified_title")).toBe(true);
    expect(KEYS.some((k) => k[0] === "futures-history" && k[1] === 86832)).toBe(true);
    expect(KEYS.some((k) => String(k[0]).includes("timeline"))).toBe(false);
  });

  it("Games This Week prints the table's verified number, not the source value (#10243)", () => {
    const html = render(structuredClone(oddsVerified));
    const at = html.indexOf("Games This Week");
    expect(at).toBeGreaterThan(-1);
    const strip = stripTags(html.slice(at));
    expect(strip).toMatch(/Buffalo Bills\s*13%/);
    expect(strip).toMatch(/Los Angeles Rams\s*11%/);
    expect(strip).not.toMatch(/Buffalo Bills\s*11%/);
  });

  it("CONTROL: a source-mode page's strip prints the route's own values", () => {
    const html = render(structuredClone(oddsRefused));
    const strip = stripTags(html.slice(html.indexOf("Games This Week")));
    expect(strip).toMatch(/Buffalo Bills\s*11%/);
  });

  it("the hero prints the verified value with the shown outcome's contributors", () => {
    const html = render(structuredClone(oddsVerified));
    expect(text(html, "hero-percent")).toBe("13");
    expect(heroContributors(html)).toBe("Aggregated from Sportsbooks · Kalshi · Polymarket");
    expect(html).not.toMatch(/Aggregated from <strong[^>]*>\d+ sources/);
    // Notice 33: the sportsbook venue is "Sportsbooks", never bare "books".
    expect(html).not.toMatch(/\bbooks\b/i);
  });

  it("the chart names whose history it draws", () => {
    const html = render(structuredClone(oddsVerified));
    expect(text(html, "futures-trend-history-basis")).toBe("Sportsbooks history");
    expect(html).toContain("Buffalo Bills");
  });

  it("a single contributor reads as one source, not a blend", () => {
    const market = structuredClone(oddsVerified) as { outcomes: { contributing_sources: string[] }[] };
    market.outcomes[0].contributing_sources = ["kalshi"];
    const html = render(market);
    expect(heroContributors(html)).toBe("From Kalshi");
    expect(html).not.toContain("Aggregated from");
  });

  it("CONTROL: an opted-in page the server refused renders source mode, as before", () => {
    const html = render(structuredClone(oddsRefused));
    expect(html).not.toContain('data-testid="hero-contributors"');
    expect(html).not.toContain('data-testid="futures-trend-history-basis"');
    expect(KEYS.some((k) => k[0] === "futures-history" && k[1] === 86832)).toBe(true);
  });
});
