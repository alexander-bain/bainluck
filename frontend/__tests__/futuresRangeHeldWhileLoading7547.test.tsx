/**
 * #7547 — a futures chart says which range is on screen while a newly tapped
 * range loads or fails. Old prices never sit silently under a newly lit chip.
 *
 * Specimen: /futures/199045 (ALCS winner) at 390px, 2026-10-17 13:49Z, Live's
 * before capture `artifacts/live/10955-199045-before-20261017/
 * futures-199045-390-chart-all.png`. "All" is lit and the x-axis reads
 * Oct 13 → Oct 17: the week chart, still drawn for the >6 s the All request
 * took, with nothing on the card saying so. `…-chart-all-18s.png` is the same
 * card once All arrived (Jun 19 → Oct 17).
 *
 * The page holds the previous chart on purpose (`keepPreviousData`, #7545:
 * unmounting it took the chips away mid-tap). What was missing is the label.
 * This file mounts the REAL page with the REAL SWR (`minimalDom` +
 * `createRoot`); only the network, the price stream and the chart leaf are
 * replaced. The chart leaf prints the first timestamp it was handed, so each
 * assertion reads which range's prices the reader is looking at.
 *
 * Every request is a deferred promise the test settles by hand, so "loading",
 * "failed", "answered late" and "answered out of order" are each a fixed state,
 * not a race.
 */
import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { SWRConfig } from "swr";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));
jest.mock("@/hooks/useMarketStream", () => ({ useMarketStream: () => {} }));
// The live price stream is Live's and is not under test here.
jest.mock("@/hooks/useFuturesDetailStream", () => ({ useFuturesDetailStream: () => {} }));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: unknown }) =>
    React.createElement("a", { href: String(href), ...rest }, children),
}));
// The chart leaf: which prices was it handed? (The first timestamp tells the
// week body from the whole-history body.)
jest.mock("@/components/FuturesChart", () => ({
  __esModule: true,
  FuturesChart: ({ historyData }: { historyData: { history: { timestamp: string }[] }[] }) =>
    React.createElement("div", { "data-testid": "drawn-from" }, historyData[0]?.history[0]?.timestamp ?? ""),
}));

type Body = Record<string, unknown>;
type Call = { rung: "1W" | "1M" | "all"; resolve: (b: Body) => void; reject: (e: Error) => void; settled: boolean };
const calls: Call[] = [];
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchFuturesMarket: jest.fn(async () => MARKET),
  fetchFuturesHistory: jest.fn(
    (_id: number, hours: number, _o?: unknown, _t?: unknown, _c?: unknown, options?: { range?: string }) =>
      new Promise<Body>((resolve, reject) => {
        const rung = options?.range === "full" ? "all" : hours === 168 ? "1W" : "1M";
        const call: Call = {
          rung,
          resolve: (b) => { call.settled = true; resolve(b); },
          reject: (e) => { call.settled = true; reject(e); },
          settled: false,
        };
        calls.push(call);
      }),
  ),
}));

import FuturesDetailPage from "../app/futures/[id]/page";

/* ─────────────────────────────── fixture ─────────────────────────────── */

const ID = 199045;
const CLE = 9001;
const TB = 9002;
let MARKET: Body = {};

function market(): Body {
  return {
    id: ID,
    name: "American League Champion",
    status: "open",
    mutually_exclusive: true,
    source: "polymarket",
    created_at: "2026-02-19T00:00:00+00:00",
    // Fresh, so the page opens on 1W (`defaultFuturesRange`).
    updated_at: new Date().toISOString(),
    outcomes: [
      { id: CLE, name: "Cleveland Guardians", probability: 0.62, rank: 1, is_winner: false, last_updated: new Date().toISOString() },
      { id: TB, name: "Tampa Bay Rays", probability: 0.38, rank: 2, is_winner: false, last_updated: new Date().toISOString() },
    ],
  };
}

const WEEK_FIRST = "2026-10-13T19:00:00.000Z";
const MONTH_FIRST = "2026-09-17T00:00:00.000Z";
const ALL_FIRST = "2026-06-19T00:00:00.000Z";

function body(first: string, hours: number, empty = false): Body {
  const t0 = new Date(first).getTime();
  const points = (p: number) =>
    [0, 1, 2].map((i) => ({
      timestamp: new Date(t0 + i * 24 * 3600 * 1000).toISOString(),
      probability: p,
      american_odds: null,
      bookmaker: "consensus",
    }));
  return {
    market_id: ID,
    market_name: "American League Champion",
    hours,
    actual_hours: hours,
    sparse: false,
    total_data_points: empty ? 0 : 6,
    outcomes: empty
      ? []
      : [
          { outcome_id: CLE, name: "Cleveland Guardians", history: points(0.62) },
          { outcome_id: TB, name: "Tampa Bay Rays", history: points(0.38) },
        ],
  };
}
const WEEK = () => body(WEEK_FIRST, 168);
const MONTH = () => body(MONTH_FIRST, 720);
const ALL = () => body(ALL_FIRST, 5800);

/* ─────────────────────────────── harness ─────────────────────────────── */

type El = HTMLElement & { [k: string]: unknown };
function descendants(node: El): El[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as El))];
}
function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return node[key] as Record<string, (arg?: unknown) => void>;
}
const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
async function settle() {
  await act(async () => { await delay(5); });
}
async function until(predicate: () => boolean, what: string) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error(`never reached: ${what}`);
    await settle();
  }
}

let host: El;
let root: ReturnType<typeof createRoot>;

function byTestId(id: string): El[] {
  return descendants(host).filter((n) => n["data-testid"] === id);
}
/** The first timestamp of the prices the chart is drawing, or null when none. */
function drawnFrom(): string | null {
  const el = byTestId("drawn-from")[0];
  return el ? el.textContent : null;
}
/** The held-range line, or null when the card prints none. */
function heldLine(): string | null {
  const el = byTestId("futures-trend-range-held")[0];
  if (!el) return null;
  // The sentence without the retry button's label.
  return Array.from(el.childNodes)
    .filter((n) => (n as El).tagName !== "BUTTON")
    .map((n) => (n.nodeType === 3 ? (n as unknown as { data: string }).data : (n as El).textContent ?? ""))
    .join("")
    .trim();
}
function chip(label: string): El {
  const found = descendants(host).filter(
    (n) => n.tagName === "BUTTON" && n["aria-pressed"] !== undefined && n.textContent === label,
  );
  expect(found).toHaveLength(1);
  return found[0];
}
function litChip(): string {
  return ["1W", "1M", "All"].filter((l) => String(chip(l)["aria-pressed"]) === "true").join(",");
}
async function tap(label: string) {
  await act(async () => { reactProps(chip(label)).onClick(); });
  await settle();
}
function retryButton(): El | undefined {
  return descendants(host).find((n) => n.tagName === "BUTTON" && n.textContent === "Try again");
}
function trendCard(): El | undefined {
  return descendants(host).find((n) => n["data-range-picked"] !== undefined);
}
function text(): string {
  return host.textContent ?? "";
}
/** The newest request for a rung that has not been answered yet. */
function pending(rung: Call["rung"]): Call {
  const open = calls.filter((c) => c.rung === rung && !c.settled);
  expect(open.length).toBeGreaterThan(0);
  return open[open.length - 1];
}
async function answer(rung: Call["rung"], b: Body) {
  await act(async () => { pending(rung).resolve(b); await delay(5); });
  await settle();
}
async function fail(rung: Call["rung"]) {
  await act(async () => { pending(rung).reject(new Error("HTTP 503")); await delay(5); });
  await settle();
}

async function mountOnWeek(week: Body = WEEK()) {
  await act(async () => {
    root.render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0, shouldRetryOnError: false }}>
        <FuturesDetailPage params={{ id: String(ID) }} />
      </SWRConfig>,
    );
  });
  await until(() => calls.some((c) => c.rung === "1W"), "the 1W request");
  await answer("1W", week);
}

const realFetch = global.fetch;
beforeEach(() => {
  calls.length = 0;
  MARKET = market();
  // Any other request a child makes stays pending: nothing leaves the test.
  global.fetch = jest.fn(() => new Promise<Response>(() => {})) as unknown as typeof fetch;
  (window as unknown as Record<string, unknown>).history = { state: null, replaceState: jest.fn() };
  host = document.createElement("div") as unknown as El;
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(async () => {
  await act(async () => root.unmount());
  document.body.removeChild(host);
  global.fetch = realFetch;
});

const LOADING_ALL = "Loading this market's history — showing the last 7 days until it arrives.";
const FAILED_ALL = "Couldn't load this market's history. Showing the last 7 days.";

/* ─────────────────────────────── the ship ─────────────────────────────── */

describe("#7547 the chart names the range it is drawing while a new one loads", () => {
  it("control: on an answered range there is no held line and nothing is dimmed", async () => {
    await mountOnWeek();
    expect(litChip()).toBe("1W");
    expect(drawnFrom()).toBe(WEEK_FIRST);
    expect(heldLine()).toBeNull();
    // (`?? "false"`: the control must pass on the pre-fix page too, which has
    // no busy flag at all.)
    expect(String(trendCard()?.["aria-busy"] ?? "false")).toBe("false");
  });

  it("tapping All keeps the week chart, lit All, and SAYS it is still the week (the specimen)", async () => {
    await mountOnWeek();
    await tap("All");
    // The reader's pick is lit, and the request for it is out.
    expect(litChip()).toBe("All");
    expect(calls.filter((c) => c.rung === "all")).toHaveLength(1);
    // The usable chart is not blanked …
    expect(drawnFrom()).toBe(WEEK_FIRST);
    // … and it is no longer silent about being the week.
    expect(heldLine()).toBe(LOADING_ALL);
    expect(String(trendCard()!["aria-busy"])).toBe("true");

    await answer("all", ALL());
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(heldLine()).toBeNull();
    expect(String(trendCard()!["aria-busy"])).toBe("false");
    expect(litChip()).toBe("All");
  });

  it("the coverage sentence never compares the new request with the held answer", async () => {
    // The held All body (5800h) against a pending 1M request (720h) read
    // "Limited history for 30 days — showing 242 days": a widening that never
    // happened, about a range that had not answered yet.
    await mountOnWeek();
    await tap("All");
    await answer("all", ALL());
    await tap("1M");
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(text()).not.toMatch(/Limited history/);
    // Control: the week, served from cache, is the current answer — no line.
    await tap("1W");
    expect(drawnFrom()).toBe(WEEK_FIRST);
    expect(heldLine()).toBeNull();
  });
});

describe("#7547 a failed range says it failed, keeps the held chart, and can be retried", () => {
  it("never shows an empty or 'limited history' state for a request that failed", async () => {
    await mountOnWeek();
    await tap("All");
    await fail("all");

    expect(litChip()).toBe("All"); // the reader's choice is kept
    expect(drawnFrom()).toBe(WEEK_FIRST); // the real week is still drawn
    expect(heldLine()).toBe(FAILED_ALL);
    expect(text()).not.toContain("Limited price history available");
    expect(text()).not.toContain("Not enough price history yet");
    expect(String(trendCard()!["aria-busy"])).toBe("false");

    // Try again asks for the picked range again and goes back to loading.
    const before = calls.filter((c) => c.rung === "all").length;
    expect(retryButton()).toBeDefined();
    await act(async () => { reactProps(retryButton()!).onClick(); });
    await settle();
    expect(calls.filter((c) => c.rung === "all")).toHaveLength(before + 1);
    expect(heldLine()).toBe(LOADING_ALL);
    expect(retryButton()).toBeUndefined();

    await answer("all", ALL());
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(heldLine()).toBeNull();
  });

  it("a range the reader already left can fail without touching the screen", async () => {
    await mountOnWeek();
    await tap("All");
    await tap("1W"); // back to the answered week before All comes back
    expect(heldLine()).toBeNull();
    await fail("all");
    expect(litChip()).toBe("1W");
    expect(drawnFrom()).toBe(WEEK_FIRST);
    expect(heldLine()).toBeNull();
    expect(text()).not.toContain("Couldn't load");
  });
});

describe("#7547 rapid taps: only the picked range's answer reaches the chart", () => {
  it("a late answer for an abandoned range does not draw, nor end the loading line", async () => {
    await mountOnWeek();
    await tap("1M");
    await tap("All");
    expect(litChip()).toBe("All");
    expect(heldLine()).toBe(LOADING_ALL);

    await answer("1M", MONTH()); // the reader has moved on from 1M
    expect(drawnFrom()).toBe(WEEK_FIRST);
    expect(heldLine()).toBe(LOADING_ALL);

    await answer("all", ALL());
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(heldLine()).toBeNull();

    // And 1M, now cached, is served the moment it is picked.
    await tap("1M");
    expect(drawnFrom()).toBe(MONTH_FIRST);
    expect(heldLine()).toBeNull();
  });

  it("out of order: the picked range answers first, the abandoned one later changes nothing", async () => {
    await mountOnWeek();
    await tap("1M");
    await tap("All");
    await answer("all", ALL());
    expect(drawnFrom()).toBe(ALL_FIRST);
    await answer("1M", MONTH());
    expect(litChip()).toBe("All");
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(heldLine()).toBeNull();
  });

  it("the held line names the range actually drawn, not the last one tapped", async () => {
    await mountOnWeek();
    await tap("All");
    await answer("all", ALL());
    await tap("1M");
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(heldLine()).toBe("Loading the last 30 days — showing this market's history until it arrives.");
  });
});

describe("#7547 an empty range stays on screen while a longer one loads", () => {
  it("tapping a longer range from 'No prices in the last 7 days' keeps the card and its chips", async () => {
    await mountOnWeek(body(WEEK_FIRST, 168, true));
    expect(text()).toContain("No prices in the last 7 days");
    await tap("All");
    // Before: the empty state unmounted for the whole request, chips and all.
    expect(text()).toContain("No prices in the last 7 days");
    expect(litChip()).toBe("All");
    expect(heldLine()).toBe(LOADING_ALL);

    await answer("all", ALL());
    expect(drawnFrom()).toBe(ALL_FIRST);
    expect(text()).not.toContain("No prices in");
    expect(heldLine()).toBeNull();
  });
});

describe("#7547 the title row holds still while the held line comes and goes", () => {
  // Shopper's 390px readback of PR #11185 (artifacts/shopper/pass-0470,
  // r3-0-initial vs r3-b-1W-to-All-pending vs r3-b-1W-to-All-done): with the
  // chips and their note inside the title row, the note's arrival re-ran that
  // row's width split against the Over Time / By Stage toggle. The title went
  // two lines → one and back, and the chart jumped ~30 px on every range tap.
  function cls(n: El): string {
    return String(n["class"] ?? n["className"] ?? "");
  }
  function titleRow(): El {
    const card = trendCard()!;
    const h2 = descendants(card).find((n) => n.tagName === "H2" && /Probability Trend/.test(n.textContent ?? ""))!;
    let n = h2.parentNode as El | null;
    while (n && n !== card && !/\bjustify-between\b/.test(cls(n))) n = n.parentNode as El | null;
    expect(n && n !== card).toBeTruthy();
    return n!;
  }
  function holds(row: El, target: El | undefined): boolean {
    return target != null && descendants(row).includes(target);
  }

  it("neither the chips nor the held line nor the coverage line share the title row", async () => {
    await mountOnWeek();
    expect(holds(titleRow(), chip("1W"))).toBe(false);
    await tap("All");
    const held = byTestId("futures-trend-range-held")[0];
    expect(held).toBeDefined(); // the held line is on screen in this state …
    expect(holds(titleRow(), held)).toBe(false); // … but outside the row the toggle sits in
    expect(holds(titleRow(), chip("All"))).toBe(false);
    // … and they are still in the trend card, under the title.
    expect(descendants(trendCard()!).includes(held)).toBe(true);
  });
});
