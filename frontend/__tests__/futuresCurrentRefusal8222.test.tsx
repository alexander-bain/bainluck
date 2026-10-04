/**
 * #10453 (#8222) — an open futures market with no current prices stops opening
 * its trend chart on historical lines as if they were today's leaders.
 *
 * Specimen `/futures/61308736` at 390px (retained board-390.png, #8222): all 24
 * current prices withheld, yet the 1W chart opened on Mensik near 47%. Two doors
 * led there, and this file mounts the real page so both are exercised:
 *   1. the seed effect sorted withheld rows as 0 and seeded the top three;
 *   2. with nothing seeded, `visibleChartOutcomes` fell back to the first five
 *      histories — so filtering the seed alone would NOT have fixed it.
 *
 * The page is mounted with effects running (`minimalDom` + `createRoot`), not
 * rendered to static markup: static markup never runs the seed effect, and the
 * fallback is exactly what a static render shows.
 */
import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import {
  CHECK_AN_OUTCOME_CHART_NOTE,
  NO_CURRENT_PRICES_CHART_NOTE,
} from "@/lib/futuresDetailDisplay";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let MARKET: Record<string, unknown> | null = null;
let HISTORY: Record<string, unknown> | null = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const none = { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    if (key == null) return none;
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") return { ...none, data: MARKET };
    if (tag === "futures-history") return { ...none, data: HISTORY };
    return none;
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
// next/link prefetches through `requestIdleCallback`, which reads the browser
// global `self` that the minimal DOM does not provide. The link is not under test.
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: unknown }) =>
    React.createElement("a", { href: String(href), ...rest }, children),
}));

import FuturesDetailPage from "../app/futures/[id]/page";

/* ─────────────────────────────── fixture ─────────────────────────────── */

const NAMES = ["Jakub Mensik", "Jannik Sinner", "Carlos Alcaraz", "Taylor Fritz", "Alexander Zverev", "Casper Ruud"];
const ID0 = 9100;
const idOf = (name: string) => ID0 + NAMES.indexOf(name);
// Past prices: Mensik's week-old line sits near 47%, the shape the reader met.
const PAST = [0.47, 0.2, 0.12, 0.08, 0.06, 0.04];

function outcome(i: number, probability: number | null, extra: Record<string, unknown> = {}) {
  return {
    id: ID0 + i,
    name: NAMES[i],
    probability,
    rank: i + 1,
    opening_probability: null,
    probability_change_24h: null,
    american_odds: null,
    opening_american_odds: null,
    is_winner: false,
    resolution_source: null,
    last_updated: "2026-10-01T12:00:00+00:00",
    ...extra,
  };
}
function market(prices: (number | null)[], extra: Record<string, unknown> = {}) {
  return {
    id: 61308736,
    name: "Shanghai Masters Winner",
    status: "open",
    mutually_exclusive: true,
    source: "kalshi",
    created_at: "2026-09-20T00:00:00+00:00",
    outcomes: prices.map((p, i) => outcome(i, p)),
    ...extra,
  };
}
function history() {
  const point = (h: number, p: number) => ({
    timestamp: new Date(Date.UTC(2026, 8, 24 + Math.floor(h / 24), h % 24)).toISOString(),
    probability: p,
    american_odds: null,
    bookmaker: "consensus",
  });
  return {
    market_id: 61308736,
    market_name: "x",
    hours: 168,
    total_data_points: 72,
    sparse: false,
    outcomes: NAMES.map((name, i) => ({
      outcome_id: ID0 + i,
      name,
      history: Array.from({ length: 12 }, (_, h) => point(h * 6, PAST[i])),
    })),
  };
}
const ALL_WITHHELD = NAMES.map(() => null);

/* ─────────────────────────────── harness ─────────────────────────────── */

type El = HTMLElement & { [k: string]: unknown };
function descendants(node: El): El[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as El))];
}
function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return node[key] as Record<string, (arg?: unknown) => void>;
}
let host: El;
let root: ReturnType<typeof createRoot>;
function mount() {
  act(() => root.render(<FuturesDetailPage params={{ id: "61308736" }} />));
}
function byTestId(id: string): El[] {
  return descendants(host).filter((n) => n["data-testid"] === id);
}
/** True when the trend chart itself is on screen (its y-axis labels render). */
function chartDrawn(): boolean {
  return byTestId("chart-y-label").length > 0;
}
/** The names in the chart's legend — the lines actually drawn. */
function legendNames(): string[] {
  return descendants(host)
    .filter((n) => {
      const swatch = n.childNodes[0] as El | undefined;
      return n.tagName === "BUTTON" && swatch?.tagName === "SPAN" && !!swatch.style?.backgroundColor;
    })
    .map((n) => (n.childNodes[1] as El).textContent ?? "");
}
/** Click a row's chart checkbox, wherever the row sits (listed or folded). */
function toggleRow(name: string) {
  const row = byTestId("outcome-row").find((n) => n["data-outcome-name"] === name);
  expect(row).toBeDefined();
  const box = descendants(row!).find((n) => n.tagName === "BUTTON")!;
  act(() => reactProps(box).onClick({ preventDefault: () => {} }));
}
function text(): string {
  return host.textContent ?? "";
}

beforeEach(() => {
  MARKET = market(ALL_WITHHELD);
  HISTORY = history();
  host = document.createElement("div") as unknown as El;
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.removeChild(host);
});

/* ─────────────────────────────── the ship ─────────────────────────────── */

describe("#10453 all prices withheld: the chart draws no automatic lines", () => {
  it("opens on the honest no-current-prices state, with no chart and no legend", () => {
    mount();
    expect(chartDrawn()).toBe(false);
    expect(legendNames()).toEqual([]);
    expect(byTestId("futures-trend-no-current-prices").map((n) => n.textContent)).toEqual([
      NO_CURRENT_PRICES_CHART_NOTE,
    ]);
    // The card keeps its heading and range controls, and every row keeps its checkbox.
    expect(text()).toContain("Probability Trend");
    for (const name of NAMES) {
      const row = byTestId("outcome-row").find((n) => n["data-outcome-name"] === name)!;
      expect(descendants(row).some((n) => n.tagName === "BUTTON")).toBe(true);
    }
    // No movement caption about a withheld row.
    expect(text()).not.toMatch(/pts (from opening|in the last 24h)/);
  });

  it("checking a withheld row draws its unchanged history, labelled as past prices", () => {
    const before = JSON.stringify(HISTORY);
    mount();
    toggleRow("Jakub Mensik");
    expect(chartDrawn()).toBe(true);
    expect(legendNames()).toEqual(["Jakub Mensik"]);
    expect(byTestId("futures-trend-unpriced-line").map((n) => n.textContent)).toEqual([
      "No current price for Jakub Mensik. Its line shows past prices.",
    ]);
    expect(byTestId("futures-trend-no-current-prices")).toHaveLength(0);
    // The served history is never edited.
    expect(JSON.stringify(HISTORY)).toBe(before);
  });

  it("unchecking it again returns to the empty state — no hidden first-five fallback", () => {
    mount();
    toggleRow("Jakub Mensik");
    toggleRow("Jakub Mensik");
    expect(chartDrawn()).toBe(false);
    expect(legendNames()).toEqual([]);
    expect(byTestId("futures-trend-no-current-prices")).toHaveLength(1);
    expect(byTestId("futures-trend-unpriced-line")).toHaveLength(0);
  });

  it("prices that arrive before any reader choice seed the normal defaults", () => {
    mount();
    expect(chartDrawn()).toBe(false);
    MARKET = market([null, 0.3, 0.25, null, null, null]);
    mount();
    expect(legendNames().sort()).toEqual(["Carlos Alcaraz", "Jannik Sinner"]);
    expect(byTestId("futures-trend-no-current-prices")).toHaveLength(0);
    expect(byTestId("futures-trend-unpriced-line")).toHaveLength(0);
  });

  it("prices that arrive after the reader chose never overwrite that choice", () => {
    mount();
    toggleRow("Casper Ruud");
    MARKET = market([null, 0.3, 0.25, null, null, null]);
    mount();
    expect(legendNames()).toEqual(["Casper Ruud"]);
  });
});

describe("#10453 partly priced and settled boards", () => {
  it("a mixed board seeds only rows priced now, and an explicit 0 is a price", () => {
    MARKET = market([null, 0.3, null, 0, null, null]);
    mount();
    expect(legendNames().sort()).toEqual(["Jannik Sinner", "Taylor Fritz"]);
    expect(byTestId("futures-trend-unpriced-line")).toHaveLength(0);
  });

  it("clearing the selection on a mixed board falls back to priced lines only", () => {
    MARKET = market([null, 0.3, null, 0, null, null]);
    mount();
    toggleRow("Jannik Sinner");
    toggleRow("Taylor Fritz");
    expect(legendNames().sort()).toEqual(["Jannik Sinner", "Taylor Fritz"]);
    expect(byTestId("futures-trend-unpriced-line")).toHaveLength(0);
  });

  it("a mixed board whose priced rows have no history in a new range does not claim 'no current prices'", () => {
    MARKET = market([null, 0.3, null, null, null, null]);
    mount();
    expect(legendNames()).toEqual(["Jannik Sinner"]);
    // The reader clears the seed; the fallback is still the priced line alone.
    toggleRow("Jannik Sinner");
    expect(legendNames()).toEqual(["Jannik Sinner"]);
    // Another range where only withheld rows have history.
    const h = history();
    h.outcomes = h.outcomes.filter((o) => o.outcome_id !== idOf("Jannik Sinner"));
    HISTORY = h;
    mount();
    expect(legendNames()).toEqual([]);
    expect(byTestId("futures-trend-no-current-prices").map((n) => n.textContent)).toEqual([
      CHECK_AN_OUTCOME_CHART_NOTE,
    ]);
  });

  it("CONTROL: a resolved board still opens on its winner and runner-up", () => {
    MARKET = market(ALL_WITHHELD, { status: "resolved" });
    (MARKET.outcomes as Record<string, unknown>[])[2].is_winner = true;
    mount();
    expect(chartDrawn()).toBe(true);
    expect(legendNames()).toContain("Carlos Alcaraz");
    expect(byTestId("futures-trend-no-current-prices")).toHaveLength(0);
    expect(byTestId("futures-trend-unpriced-line")).toHaveLength(0);
  });
});
