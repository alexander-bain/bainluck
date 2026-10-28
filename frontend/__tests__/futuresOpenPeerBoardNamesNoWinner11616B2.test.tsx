/**
 * #11616 B2 — an OPEN board with several supported peer winners crowns none of
 * them, on the page or in the shared link.
 *
 * lane1b DELTA-REVIEW-6430a461 §3, ruled blocking by Root (ROOT-6430-REVIEW-
 * DISPOSITION): "BMW PGA Championship - Make the Cut", still `open` after the cut
 * (gotcha #33's window), `participation`, `mutually_exclusive: false`, no lead;
 * Aberg and McIlroy a supported `Won`, Fleetwood and Rahm a supported loss at 0.
 * At 6430a461 both arms (winners at 1.0, winners unpriced) rendered
 *
 *   page hero   "Ludvig Aberg · Won"
 *   og:title    "Ludvig Aberg won - BMW PGA Championship - Make the Cut"
 *   picture     Aberg / WON
 *
 * — #7906's false claim, which `gradedWinner` refuses on the resolved twin of the
 * same board. The inputs below are lane1b's `zzLane1bProbePeerOpen6430` arms
 * verbatim, plus the contradicted-exclusive shape Root's ruling names.
 *
 * Mounted with effects running, like `futuresDetailHeroSupportedResult11616`.
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
import { generateMetadata as futuresMetadata } from "../app/futures/[id]/layout";
import m1uDetail73 from "./fixtures/m1u_detail_73_0e5d583a.json";

/* ─────────────────────────────── inputs ─────────────────────────────── */

const W = { is_winner: true, resolution_source: "api_settlement" };
const L = { is_winner: false, resolution_source: "api_settlement" };
const MAKE_THE_CUT = "BMW PGA Championship - Make the Cut";

// lane1b's two B2 arms, byte for byte (ids, prices, ranks, verdicts).
const ARMS: Record<string, Record<string, unknown>[]> = {
  "winners at 1.0": [
    { id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 1, ...W },
    { id: 2, name: "Tommy Fleetwood", probability: 0.0, rank: 3, ...L },
    { id: 3, name: "Rory McIlroy", probability: 1.0, rank: 2, ...W },
    { id: 4, name: "Jon Rahm", probability: 0.0, rank: 4, ...L },
  ],
  "winners unpriced": [
    { id: 1, name: "Ludvig Aberg", probability: null, rank: null, ...W },
    { id: 2, name: "Tommy Fleetwood", probability: 0.0, rank: 1, ...L },
    { id: 3, name: "Rory McIlroy", probability: null, rank: null, ...W },
    { id: 4, name: "Jon Rahm", probability: 0.0, rank: 2, ...L },
  ],
};

function makeTheCut(
  outcomes: Record<string, unknown>[],
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: 61010898, name: MAKE_THE_CUT, status: "open",
    mutually_exclusive: false, market_type: "participation", lead_outcome_id: null,
    outcome_count: outcomes.length, outcomes, ...extra,
  };
}

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

function page(body: Record<string, unknown>) {
  MARKET = body;
  act(() => root.render(<FuturesDetailPage params={{ id: String(body.id) }} />));
  const text = (id: string) =>
    descendants(host).filter((n) => n["data-testid"] === id).map((n) => n.textContent ?? "");
  const rows = descendants(host)
    .filter((n) => n["data-testid"] === "outcome-row")
    .map((row) => {
      const verdict = descendants(row).find((n) => n["data-testid"] === "outcome-verdict");
      return [String(row["data-outcome-name"]), verdict?.textContent ?? null] as const;
    });
  return {
    percent: text("hero-percent"),
    openWon: text("hero-open-won-name"),
    openWonChip: text("hero-open-won-chip"),
    resolvedName: text("hero-resolved-name"),
    rowVerdicts: Object.fromEntries(rows),
  };
}

function respondWith(body: unknown) {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true, status: 200, json: async () => body,
  }) as unknown as typeof fetch;
}

async function share(body: Record<string, unknown>) {
  const id = String(body.id);
  respondWith(body);
  const meta = await futuresMetadata({ params: Promise.resolve({ id }) });
  mockImageResponseCalls.length = 0;
  respondWith(body);
  await (FuturesOgImage as unknown as (a: { params: unknown }) => Promise<unknown>)({
    params: { id },
  });
  if (mockImageResponseCalls.length !== 1) throw new Error("expected one picture");
  const picture = renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const og = meta.openGraph as { title?: unknown } | undefined;
  return {
    title: String(meta.title),
    ogTitle: String(og?.title),
    description: String(meta.description),
    picture,
  };
}

/* ─────────────────────────────── the ship ─────────────────────────────── */

describe.each(Object.keys(ARMS))("B2: open Make the Cut, %s", (arm) => {
  it("the page hero names nobody and every row keeps its own result", () => {
    const h = page(makeTheCut(ARMS[arm]));
    expect(h.openWon).toEqual([]);
    expect(h.openWonChip).toEqual([]);
    // No winner's last price becomes a forecast in place of the crown.
    expect(h.percent).toEqual([]);
    expect(h.rowVerdicts["Ludvig Aberg"]).toBe("Won");
    expect(h.rowVerdicts["Rory McIlroy"]).toBe("Won");
  });

  it("the title, og:title, description and picture name nobody", async () => {
    const s = await share(makeTheCut(ARMS[arm]));
    expect(s.title).toBe(MAKE_THE_CUT);
    expect(s.ogTitle).toBe(`${MAKE_THE_CUT} | Bain Luck`);
    for (const text of [s.title, s.description, s.picture]) {
      expect(text).not.toMatch(/Aberg|McIlroy|\bwon\b|\bWON\b|100%/);
    }
    expect(s.picture).toContain(MAKE_THE_CUT);
  });
});

describe("B2: an exclusivity claim contradicted by two supported winners", () => {
  // Root's ruling names this door too (`mutually_exclusive === true`, any shape).
  const contradicted = (p: number | null) =>
    makeTheCut(
      ARMS["winners at 1.0"].map((o) => (o.is_winner ? { ...o, probability: p } : o)),
      { name: "Set 1 Winner", mutually_exclusive: true, market_type: null },
    );

  it.each([1.0, null])("winners at %p: page and share name nobody", async (p) => {
    const h = page(contradicted(p));
    expect(h.openWon).toEqual([]);
    expect(h.openWonChip).toEqual([]);
    expect(h.percent).toEqual([]);
    const s = await share(contradicted(p));
    expect(s.title).toBe("Set 1 Winner");
    for (const text of [s.title, s.description, s.picture]) {
      expect(text).not.toMatch(/Aberg|McIlroy|\bwon\b|\bWON\b|100%/);
    }
  });

  // Native's own contradiction input (`testAnOpenExclusiveBoardWithTwoSupported
  // WinnersNamesNeither`), whose share is "Awards field on Bain Luck": the live
  // row is not shared as the board's price either, since the page names nobody.
  it("Native's input: neither winner, and not the live row's price", async () => {
    const body = {
      id: 11616, name: "Awards field", status: "open", mutually_exclusive: true, outcome_count: 3,
      outcomes: [
        { id: 1, name: "SK Beveren", probability: null, rank: null, ...W },
        { id: 2, name: "Draw", probability: null, rank: null, ...W },
        { id: 3, name: "Away", probability: 0.2, rank: 1, is_winner: null, resolution_source: null },
      ],
    };
    const h = page(body);
    expect(h.openWon).toEqual([]);
    expect(h.openWonChip).toEqual([]);
    expect(h.percent).toEqual([]);
    const s = await share(body);
    expect(s.title).toBe("Awards field");
    for (const text of [s.title, s.description, s.picture]) {
      expect(text).not.toMatch(/Beveren|Draw|Away|20%|\bwon\b|\bWON\b/);
    }
  });
});

/* ─────────────────────────────── controls ─────────────────────────────── */

describe("controls: what B2 must not move", () => {
  it("one supported participant winner keeps its crown on page and share", async () => {
    const body = makeTheCut([
      { id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 1, ...W },
      { id: 2, name: "Tommy Fleetwood", probability: 0.0, rank: 2, ...L },
    ]);
    const h = page(body);
    expect(h.openWon).toEqual(["Ludvig Aberg"]);
    expect(h.openWonChip).toEqual(["Won"]);
    const s = await share(body);
    expect(s.title).toBe(`Ludvig Aberg won - ${MAKE_THE_CUT}`);
    expect(s.picture).toContain("Ludvig Aberg WON");
  });

  it("raw and retracted flags cannot manufacture a second winner", async () => {
    const body = makeTheCut([
      { id: 3, name: "Rory McIlroy", probability: 1.0, rank: 1, is_winner: true, resolution_source: null },
      { id: 4, name: "Jon Rahm", probability: 1.0, rank: 2, is_winner: true, resolution_source: "ungradeable_result" },
      { id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 3, ...W },
      { id: 2, name: "Tommy Fleetwood", probability: 0.0, rank: 4, ...L },
    ]);
    const h = page(body);
    expect(h.openWon).toEqual(["Ludvig Aberg"]);
    const s = await share(body);
    expect(s.title).toBe(`Ludvig Aberg won - ${MAKE_THE_CUT}`);
  });

  it("M1-U, an exclusive board with one supported winner, still shares Shai won", async () => {
    const body = m1uDetail73 as unknown as Record<string, unknown>;
    const h = page(body);
    expect(h.openWon).toEqual(["Shai Gilgeous-Alexander"]);
    const s = await share(body);
    expect(s.title).toBe("Shai Gilgeous-Alexander won - NBA MVP Winner 2027");
  });

  it("a genuine live row still leads the page of a peer board with several winners", async () => {
    const body = makeTheCut([
      { id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 1, ...W },
      { id: 3, name: "Rory McIlroy", probability: 1.0, rank: 2, ...W },
      { id: 2, name: "Tommy Fleetwood", probability: 0.42, rank: 3, is_winner: null, resolution_source: null },
      { id: 4, name: "Jon Rahm", probability: 0.0, rank: 4, ...L },
    ]);
    const h = page(body);
    expect(h.percent).toEqual(["42"]);
    expect(h.openWonChip).toEqual([]);
    // The link no longer prices a winner as a forecast ("Ludvig Aberg 100%" at
    // 6430a461): it states the board, and names no crown either.
    const s = await share(body);
    expect(s.title).toBe(MAKE_THE_CUT);
    expect(s.picture).not.toMatch(/Aberg|McIlroy|100%|\bWON\b/);
  });

  // The shape door is keyed positively (Native's `…KeepServedOrder` loop): a
  // ladder, a grouped independent board or no shape keeps its first winner.
  it.each(["quantity", "duel", "field", null])(
    "shape %p: plural winners are the design and the first is still named",
    async (shape) => {
      const body = makeTheCut(
        [
          { id: 1, name: "77° or above", probability: 1.0, rank: 1, ...W },
          { id: 2, name: "78° or above", probability: 1.0, rank: 2, ...W },
          { id: 3, name: "82° or above", probability: 0.0, rank: 3, is_winner: null, resolution_source: null },
        ],
        { name: "NYC high temperature", market_type: shape },
      );
      expect(page(body).openWon).toEqual(["77° or above"]);
      const s = await share(body);
      expect(s.title).toBe("77° or above won - NYC high temperature");
    },
  );

  it("the resolved twin of the B2 board still names nobody (#7906)", async () => {
    const body = makeTheCut(ARMS["winners at 1.0"], { status: "resolved" });
    const h = page(body);
    expect(h.resolvedName).toEqual([]);
    const s = await share(body);
    expect(s.title).toBe(MAKE_THE_CUT);
  });

  // N3 — the served-lead arm of `openHeroResult`: an independent board whose
  // priced lead is a supported Won shares that result, not "Cloud9 98%".
  it("an explicit supported served lead is shared as the result", async () => {
    const body = {
      id: 61778284, name: "LoL: Cloud9 vs Team Liquid (BO5)", status: "open",
      mutually_exclusive: false, market_type: null, lead_outcome_id: 2, outcome_count: 2,
      outcomes: [
        { id: 1, name: "Over — O/U 3.5 Games", probability: 0.71, rank: 2, is_winner: null, resolution_source: null },
        { id: 2, name: "Cloud9 — Match Winner", probability: 0.98, rank: 1, ...W },
      ],
    };
    const h = page(body);
    expect(h.openWon).toEqual(["Cloud9 — Match Winner"]);
    const s = await share(body);
    expect(s.title).toBe("Cloud9 — Match Winner won - LoL: Cloud9 vs Team Liquid (BO5)");
    expect(s.title).not.toContain("98%");
  });

  // Declared boundary, the same as Native's `futuresDetailHeroOutcome` (its lead
  // arm runs before the B2 refusal): a lead the server names is the leg the venue
  // corroborates (#8894), not a pick among peers, so B2 does not withhold it.
  it("a served lead keeps its crown even where the winners are several", async () => {
    const body = makeTheCut(
      [
        { id: 1, name: "Ludvig Aberg", probability: 1.0, rank: 1, ...W },
        { id: 3, name: "Rory McIlroy", probability: 1.0, rank: 2, ...W },
      ],
      { name: "Set 1 Winner", mutually_exclusive: true, market_type: null, lead_outcome_id: 3 },
    );
    const h = page(body);
    expect(h.openWon).toEqual(["Rory McIlroy"]);
    const s = await share(body);
    expect(s.title).toBe("Rory McIlroy won - Set 1 Winner");
  });
});
