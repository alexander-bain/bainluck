/**
 * #11616 HM — the hero's movement pill and its "last move" date belong to the row
 * the hero names, never to the price leader.
 *
 * lane1b DELTA-REVIEW-5c1e51b3 §5b, scoped into #11629 by Root
 * (ROOT-5C1E51B3-REVIEW-DISPOSITION): on LR1/LR3 with Aberg +0.12 and Fleetwood
 * −0.07 in 24h, the page read
 *
 *   hero     "42%  Tommy Fleetwood  ↑ 12.0 pts"
 *   picture  "42% ↓ -7% 24h Tommy Fleetwood"
 *
 * The pill was Aberg's move: `movement` and `movementLabel` read `leader` (the
 * highest price, Aberg's settled 1.0) while the number and name read
 * `heroOutcome`. HM1/HM3/HM4 are lane1b's `zzLane1bProbeHeroMovement5c1e` inputs;
 * the two rows' stamps differ here (they were equal in the probe) so the date
 * cannot silently come from the other row either.
 *
 * Harness: `futuresOpenPeerBoardNamesNoWinner11616B2.test.tsx`.
 */
import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

const mockImageResponseCalls: React.ReactElement[] = [];
jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));
jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let MARKET: Record<string, unknown> | null = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const none = { data: undefined, error: undefined, isLoading: false, mutate: () => {} };
    if (key == null) return none;
    const tag = Array.isArray(key) ? key[0] : key;
    if (tag === "futures-market") return { ...none, data: MARKET };
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
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: unknown }) =>
    React.createElement("a", { href: String(href), ...rest }, children),
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import FuturesOgImage from "../app/futures/[id]/opengraph-image";

/* ─────────────────────────────── inputs ─────────────────────────────── */

const W = { is_winner: true, resolution_source: "api_settlement" };
const L = { is_winner: false, resolution_source: "api_settlement" };
const LIVE = { is_winner: null, resolution_source: null };
const MAKE_THE_CUT = "BMW PGA Championship - Make the Cut";

// Noon UTC, a week apart: the reader's day is the same in every time zone the
// label can be rendered in, and the two rows can never share a date.
const ABERG_STAMP = "2026-10-20T12:00:00Z"; // "Oct 20"
const FLEETWOOD_STAMP = "2026-10-27T12:00:00Z"; // "Oct 27"

type Row = Record<string, unknown>;
const ABERG: Row = {
  id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 1, ...W,
  probability_change_24h: 0.12, last_updated: ABERG_STAMP,
};
const MCILROY: Row = {
  id: 3, name: "Rory McIlroy", probability: 1.0, rank: 2, ...W,
  probability_change_24h: 0.3, last_updated: "2026-10-21T12:00:00Z",
};
const FLEETWOOD: Row = {
  id: 2, name: "Tommy Fleetwood", probability: 0.42, rank: 3, ...LIVE,
  probability_change_24h: -0.07, last_updated: FLEETWOOD_STAMP,
};
const RAHM: Row = { id: 4, name: "Jon Rahm", probability: 0.0, rank: 4, ...L };

function board(outcomes: Row[], extra: Row = {}): Row {
  return {
    id: 61010898, name: MAKE_THE_CUT, status: "open",
    mutually_exclusive: false, market_type: "participation", lead_outcome_id: null,
    outcome_count: outcomes.length, outcomes, ...extra,
  };
}
const withFleetwood = (patch: Row) => (rows: Row[]) =>
  rows.map((r) => (r.id === 2 ? { ...r, ...patch } : r));

// lane1b's three cases (HM1/HM3/HM4), with the stamps made to differ.
const HM1 = (rows = [ABERG, MCILROY, FLEETWOOD, RAHM]) => board(rows);
const HM3 = (rows = [ABERG, { ...FLEETWOOD, rank: 2 }, { ...RAHM, rank: 3 }]) =>
  board(rows, { market_type: null, name: "Independent board" });
const HM4 = (rows = [ABERG, MCILROY, FLEETWOOD, RAHM]) => board(rows, { lead_outcome_id: 2 });

/* ─────────────────────────────── readers ─────────────────────────────── */

type El = HTMLElement & { [k: string]: unknown };
function descendants(node: El): El[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as El))];
}
let host: El;
let root: ReturnType<typeof createRoot>;

beforeEach(() => {
  host = document.createElement("div") as unknown as El;
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.removeChild(host);
});

function hero(body: Row) {
  MARKET = body;
  act(() => root.render(<FuturesDetailPage params={{ id: String(body.id) }} />));
  const text = (id: string) =>
    descendants(host).filter((n) => n["data-testid"] === id).map((n) => (n.textContent ?? "").trim());
  return {
    percent: text("hero-percent"),
    name: text("hero-outcome-name"),
    openWon: text("hero-open-won-name"),
    movement: text("hero-movement"),
    window: text("hero-movement-window"),
  };
}

async function picture(body: Row): Promise<string> {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => body,
  }) as unknown as typeof fetch;
  mockImageResponseCalls.length = 0;
  await (FuturesOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: { id: String(body.id) },
  });
  if (mockImageResponseCalls.length !== 1) throw new Error("expected one picture");
  return renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/* ─────────────────────────────── the ship ─────────────────────────────── */

describe.each([
  ["HM1 peer board, two Won + Fleetwood live", HM1],
  ["HM3 independent board, one Won + Fleetwood live", HM3],
  ["HM4 peer board, served live lead Fleetwood", HM4],
])("%s", (_label, make) => {
  it("the pill and its date are Fleetwood's, beside Fleetwood's 42%", () => {
    const h = hero(make());
    expect(h.percent).toEqual(["42"]);
    expect(h.name).toEqual(["Tommy Fleetwood"]);
    expect(h.movement).toEqual(["↓ 7.0 pts"]);
    expect(h.window).toEqual(["last move · Oct 27"]);
    expect([...h.movement, ...h.window].join(" ")).not.toMatch(/12\.0|30\.0|Oct 20|Oct 21/);
  });

  it("the shared picture states the same move", async () => {
    const p = await picture(make());
    expect(p).toContain("42%");
    expect(p).toContain("-7%");
    expect(p).toContain("Tommy Fleetwood");
    expect(p).not.toMatch(/\+12%|\+30%|Aberg|McIlroy/);
  });
});

describe("the hero's own stamp, never a fresher row's", () => {
  it("a hero last moved a fortnight ago is dated then, not by Aberg's newer stamp", () => {
    const rows = withFleetwood({ last_updated: "2026-10-13T12:00:00Z" })([
      { ...ABERG, last_updated: "2026-10-27T12:00:00Z" }, MCILROY, FLEETWOOD, RAHM,
    ]);
    const h = hero(HM1(rows));
    expect(h.movement).toEqual(["↓ 7.0 pts"]);
    expect(h.window).toEqual(["last move · Oct 13"]);
  });

  it("an unstamped hero says plain 'last move', not the leader's date", () => {
    const h = hero(HM1(withFleetwood({ last_updated: null })([ABERG, MCILROY, FLEETWOOD, RAHM])));
    expect(h.movement).toEqual(["↓ 7.0 pts"]);
    expect(h.window).toEqual(["last move"]);
  });
});

describe("a hero with no move of its own shows no pill", () => {
  it.each([
    ["null", null],
    ["zero", 0],
  ])("Fleetwood's 24h change is %s: no pill and no date, Aberg's +12 never borrowed", (_l, change) => {
    for (const make of [HM1, HM3]) {
      const rows = make === HM1
        ? [ABERG, MCILROY, FLEETWOOD, RAHM]
        : [ABERG, { ...FLEETWOOD, rank: 2 }, { ...RAHM, rank: 3 }];
      const h = hero(make(withFleetwood({ probability_change_24h: change })(rows)));
      expect(h.percent).toEqual(["42"]);
      expect(h.name).toEqual(["Tommy Fleetwood"]);
      expect(h.movement).toEqual([]);
      expect(h.window).toEqual([]);
    }
  });
});

/* ─────────────────────── opposite controls (unchanged) ─────────────────────── */

describe("controls: the pill still shows where it should and stays refused where it was", () => {
  it("a live board with no winner: the price leader IS the hero and keeps its move", () => {
    const lowry: Row = {
      id: 5, name: "Shane Lowry", probability: 0.6, rank: 1, ...LIVE,
      probability_change_24h: 0.05, last_updated: "2026-10-25T12:00:00Z",
    };
    const h = hero(board([lowry, { ...FLEETWOOD, rank: 2 }]));
    expect(h.name).toEqual(["Shane Lowry"]);
    expect(h.movement).toEqual(["↑ 5.0 pts"]);
    expect(h.window).toEqual(["last move · Oct 25"]);
  });

  it("result: a served Won lead shows Won, never a move", () => {
    const h = hero(board([ABERG, MCILROY, FLEETWOOD, RAHM], { lead_outcome_id: 3 }));
    expect(h.openWon).toEqual(["Rory McIlroy"]);
    expect(h.percent).toEqual([]);
    expect(h.movement).toEqual([]);
    expect(h.window).toEqual([]);
  });

  it("withheld: an open peer board with two supported winners and no live row shows no move", () => {
    const h = hero(board([ABERG, MCILROY, { ...FLEETWOOD, probability: 0.0, ...L }, RAHM]));
    expect(h.percent).toEqual([]);
    expect(h.openWon).toEqual([]);
    expect(h.movement).toEqual([]);
    expect(h.window).toEqual([]);
  });

  it("resolved: a settled board shows no move", () => {
    const h = hero(board([ABERG, { ...FLEETWOOD, probability: 0.0, ...L }], {
      status: "resolved", mutually_exclusive: true, market_type: null,
    }));
    expect(h.movement).toEqual([]);
    expect(h.window).toEqual([]);
  });

  it("unavailable: a hero with no price shows no number and no move", () => {
    const h = hero(board([{ ...FLEETWOOD, probability: null }]));
    expect(h.percent).toEqual([]);
    expect(h.movement).toEqual([]);
    expect(h.window).toEqual([]);
  });
});
