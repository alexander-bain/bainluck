/**
 * #11616 L3(a)-(d) and the resolved raw-crown observation: the web detail hero
 * follows the row's supported verdict (`outcomeRowVerdict`), as iOS and search do.
 *
 * Root's ROOT-NATIVE-DELTA-DISPOSITION items 3-4, from lane1b's
 * NATIVE-DELTA-REVIEW-0d239c9d §3.1/§3.3:
 *   (a) an open exclusive/unstated board heroed Shai 97% while its own table
 *       printed Victor Won — "a verified result is not replaced by a prediction";
 *   (b) an independent board with no live row above 0 fell back to the price
 *       leader instead of its supported winner;
 *   (c) a served lead with a supported Won and no price was refused (Root chose
 *       L3(c) over Native rolling back to R2);
 *   (d) an open supported-winner hero printed its last price, not "Won".
 * And: a resolved board crowned a raw `is_winner` true whose source is null or
 * the retraction, which its own row, search and iOS all refuse.
 *
 * Mounted with effects running, like #8222's harness this file copies.
 */
import "./helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import {
  gradedWinner,
  pickHeroOutcome,
  servedLeadHeroOutcome,
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
import { generateMetadata as futuresMetadata } from "../app/futures/[id]/layout";
import producerFixture from "./fixtures/backend_to_web_fixtures_11616.json";


/* ─────────────────────────────── fixture ─────────────────────────────── */

type Leg = { name: string; p: number | null; won?: boolean | null; src?: string | null };
function board(legs: Leg[], extra: Record<string, unknown> = {}) {
  return {
    id: 11616, name: "Hero board", status: "open", mutually_exclusive: true,
    source: "kalshi", created_at: "2026-09-20T00:00:00+00:00",
    outcomes: legs.map((l, i) => ({
      id: 500 + i, name: l.name, probability: l.p, rank: i + 1,
      opening_probability: null, probability_change_24h: null, american_odds: null,
      opening_american_odds: null, is_winner: l.won ?? false,
      resolution_source: l.src ?? null, last_updated: "2026-10-27T12:00:00+00:00",
    })),
    ...extra,
  };
}
const WON = { won: true, src: "api_settlement" };

/* ─────────────────────────────── readers ─────────────────────────────── */


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
  act(() => root.render(<FuturesDetailPage params={{ id: "11616" }} />));
}
function byTestId(id: string): El[] {
  return descendants(host).filter((n) => n["data-testid"] === id);
}
function text(): string {
  return host.textContent ?? "";
}

beforeEach(() => {
  HISTORY = null;
  host = document.createElement("div") as unknown as El;
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  document.body.removeChild(host);
});


const one = (id: string) => byTestId(id).map((n) => n.textContent ?? "");
function hero() {
  return {
    percent: one("hero-percent"),
    openWon: one("hero-open-won-name"),
    openWonChip: one("hero-open-won-chip"),
    resolvedName: one("hero-resolved-name"),
    resolvedChip: one("hero-resolved-chip"),
  };
}

/* ─────────────────────────────── the ship ─────────────────────────────── */

describe("L3(a)+(d): an open exclusive board heroes its supported result as Won", () => {
  it.each([0.95, null])("Victor Won (price %p) over Shai 97%%", (victor) => {
    MARKET = board([{ name: "Shai Gilgeous-Alexander", p: 0.97 }, { name: "Victor Wembanyama", p: victor, ...WON }]);
    mount();
    const h = hero();
    expect(h.openWon).toEqual(["Victor Wembanyama"]);
    expect(h.openWonChip).toEqual(["Won"]);
    expect(h.percent).toEqual([]);
    expect(h.resolvedChip).toEqual([]); // still an open board: no RESOLVED chip
  });

  it("an unstated exclusivity claim reads as exclusive (serializer default)", () => {
    MARKET = board(
      [{ name: "Shai Gilgeous-Alexander", p: 0.97 }, { name: "Victor Wembanyama", p: 0.95, ...WON }],
      { mutually_exclusive: undefined },
    );
    mount();
    expect(hero().openWon).toEqual(["Victor Wembanyama"]);
  });

  it.each([
    ["a null source", null],
    ["a non-authoritative source on an open board", "manual"],
    ["the retraction", "ungradeable_result"],
  ])("CONTROL: a raw winner flag with %s is a price, not a result", (_label, src) => {
    MARKET = board([
      { name: "Shai Gilgeous-Alexander", p: 0.97 },
      { name: "Victor Wembanyama", p: 0.95, won: true, src: src as string | null },
    ]);
    mount();
    const h = hero();
    expect(h.openWon).toEqual([]);
    expect(h.percent).toEqual(["97"]);
  });
});

describe("L3(b): an independent open board keeps a live lead, else its supported winner", () => {
  it("a live row above 0 leads (#7439)", () => {
    MARKET = board(
      [{ name: "↑ 4.25%", p: 0.4 }, { name: "↓ 3.5%", p: 0.95, ...WON }],
      { mutually_exclusive: false },
    );
    mount();
    const h = hero();
    expect(h.percent).toEqual(["40"]);
    expect(h.openWon).toEqual([]);
  });

  it("with every live row at 0 the supported winner leads, as Won", () => {
    MARKET = board(
      [{ name: "↑ 4.25%", p: 0.0 }, { name: "↓ 3.5%", p: null, ...WON }],
      { mutually_exclusive: false },
    );
    mount();
    expect(hero().openWon).toEqual(["↓ 3.5%"]);
  });
});

describe("L3(c): a served lead with a supported Won and no price stays the hero", () => {
  it("a container's settled match-winner leg leads over its O/U leg (#8892)", () => {
    MARKET = board(
      [{ name: "Over — O/U 3.5 Games", p: 0.71 }, { name: "Cloud9 — Match Winner", p: null, ...WON }],
      { mutually_exclusive: false, lead_outcome_id: 501 },
    );
    mount();
    expect(hero().openWon).toEqual(["Cloud9 — Match Winner"]);
  });

  it("CONTROL: a priceless lead with only a raw flag is refused; the live leader leads", () => {
    MARKET = board(
      [{ name: "Over — O/U 3.5 Games", p: 0.71 }, { name: "Cloud9 — Match Winner", p: null, won: true }],
      { mutually_exclusive: false, lead_outcome_id: 501 },
    );
    mount();
    const h = hero();
    expect(h.openWon).toEqual([]);
    expect(h.percent).toEqual(["71"]);
  });
});

describe("resolved raw crown: only a supported Won is crowned", () => {
  it.each([
    ["a null source", null],
    ["the retraction", "ungradeable_result"],
  ])("a raw true with %s names nobody", (_label, src) => {
    MARKET = board(
      [{ name: "Tadej Pogacar", p: 0.6, won: true, src: src as string | null }, { name: "Enric Mas", p: 0.4 }],
      { status: "resolved" },
    );
    mount();
    const h = hero();
    expect(h.resolvedName).toEqual([]);
    expect(h.resolvedChip).toEqual(["Resolved"]);
  });

  it("CONTROL: a supported grade is crowned", () => {
    MARKET = board(
      [{ name: "Tadej Pogacar", p: 0.6 }, { name: "Enric Mas", p: 0.4, ...WON }],
      { status: "resolved" },
    );
    mount();
    const h = hero();
    expect(h.resolvedName).toEqual(["Enric Mas"]);
    expect(h.resolvedChip).toEqual(["Won"]);
  });

  it("#8280: among supported winners the side-naming leg is crowned (Kings, 114108)", () => {
    MARKET = board(
      [
        { name: "O/U 5.5", p: 1, ...WON },
        { name: "O/U 6.5", p: 1, ...WON },
        { name: "Kings", p: 1, ...WON },
        { name: "Spread -1.5", p: 0, won: false, src: "api_settlement" },
      ],
      { status: "resolved", mutually_exclusive: false },
    );
    mount();
    expect(hero().resolvedName).toEqual(["Kings"]);
  });
});

describe("the helpers the unfurl and picture share", () => {
  const rows = [
    { id: 1, name: "A", probability: 0.6, is_winner: true, resolution_source: null },
    { id: 2, name: "B", probability: 0.4, is_winner: false, resolution_source: null },
  ];
  it("gradedWinner refuses a raw true the row refuses", () => {
    expect(gradedWinner(rows, rows[0], "resolved")).toBeNull();
    const supported = rows.map((r) => (r.id === 1 ? { ...r, resolution_source: "api_settlement" } : r));
    expect(gradedWinner(supported, supported[0], "resolved")?.id).toBe(1);
  });
  it("a peer-shaped board counts supported grades, not raw flags (#7906)", () => {
    const peers = [
      { id: 1, name: "A", probability: 0.6, is_winner: true, resolution_source: "api_settlement" },
      { id: 2, name: "B", probability: 0.4, is_winner: true, resolution_source: null },
    ];
    expect(gradedWinner(peers, peers[0], "resolved", "participation")?.id).toBe(1);
    const two = peers.map((r) => ({ ...r, resolution_source: "api_settlement" }));
    expect(gradedWinner(two, two[0], "resolved", "participation")).toBeNull();
  });
  it("servedLeadHeroOutcome admits a priced lead or a supported priceless Won, never on a resolved board", () => {
    const legs = [
      { id: 1, probability: 0.7, is_winner: false, resolution_source: null },
      { id: 2, probability: null, is_winner: true, resolution_source: "api_settlement" },
    ];
    expect(servedLeadHeroOutcome(legs, 1, "open")?.id).toBe(1);
    expect(servedLeadHeroOutcome(legs, 2, "open")?.id).toBe(2);
    expect(servedLeadHeroOutcome(legs, 2, "resolved")).toBeNull();
    expect(servedLeadHeroOutcome(legs, null, "open")).toBeNull();
  });
  it("an open board keeps served order among several supported winners (iOS R1 parity)", () => {
    const legs = [
      { name: "O/U 5.5", probability: 0.99, is_winner: true, resolution_source: "api_settlement" },
      { name: "Kings", probability: 0.98, is_winner: true, resolution_source: "api_settlement" },
    ];
    expect(pickHeroOutcome(legs, legs[0], false, true)).toBe(legs[0]);
    expect(pickHeroOutcome(legs, legs[0], true, true)).toBe(legs[1]); // settled: side first
  });
  it("pickHeroOutcome on an open exclusive board without a supported winner keeps the leader", () => {
    const legs = [
      { name: "A", probability: 0.97, is_winner: false, resolution_source: null },
      { name: "B", probability: 0.95, is_winner: true, resolution_source: null },
    ];
    expect(pickHeroOutcome(legs, legs[0], false, true)).toBe(legs[0]);
  });
});

/* ──────────── T1: Native's own inputs, verbatim (accepted f35750c9) ──────────── */

/**
 * lane1b EARLY-REPAIR-REVIEW-e3de8f84 §4 (T1): the three Native XCTest inputs
 * Root named, byte-for-byte in their decoded shape — not analogues. Source:
 * `ios/Bain Luck/BainLuckTests/FuturesDetailHeroResult11616Tests.swift` at
 * f35750c988bf (`row`/`market` helpers: id 11616, "Awards field", kalshi,
 * resolved, `mutually_exclusive: false` unless stated; a nil price/grade/source
 * is JSON null) and `FuturesHeroNamesTheWinningSide8280Tests.swift` (id 114108,
 * "Kings vs. Blue Jackets", resolved, `mutually_exclusive: false`).
 */
type NativeRow = { id: number; name: string; price?: number; won?: boolean; source?: string };
function nativeRow(r: NativeRow) {
  return {
    id: r.id, name: r.name, probability: r.price ?? null,
    is_winner: r.won ?? null, resolution_source: r.source ?? null,
  };
}
function nativeMarket(
  rows: NativeRow[],
  { status = "resolved", source = "kalshi", lead }: { status?: string; source?: string; lead?: number } = {},
) {
  const value: Record<string, unknown> = {
    id: 11616, name: "Awards field", status, source, outcomes: rows.map(nativeRow),
    mutually_exclusive: false,
  };
  if (lead !== undefined) value.lead_outcome_id = lead;
  return value;
}

describe("T1: the three Native inputs, the same answer on web", () => {
  it("11616Tests:82 — an explicit open lead keeps its unpriced supported result", () => {
    // row(1, "Match winner", won: true, source: "api_settlement"), row(2, "Prop", price: 0.9);
    // status "open", lead 1. Native: hero id 1, value .verdict(.won).
    const m = nativeMarket(
      [{ id: 1, name: "Match winner", won: true, source: "api_settlement" }, { id: 2, name: "Prop", price: 0.9 }],
      { status: "open", lead: 1 },
    );
    MARKET = m;
    mount();
    const h = hero();
    expect(h.openWon).toEqual(["Match winner"]);
    expect(h.openWonChip).toEqual(["Won"]);
    expect(h.percent).toEqual([]);
    const legs = m.outcomes as Parameters<typeof servedLeadHeroOutcome>[0];
    expect((servedLeadHeroOutcome(legs, 1, "open") as { id?: number } | null)?.id).toBe(1);
  });

  it("8280Tests:89 — an unsupported winner flag on a side does not outrank a supported line", () => {
    // row(1, "O/U 5.5", price: 0.99, won: true, source: "game_score"),
    // row(2, "Kings", price: 0.99, won: true, source: nil); source "kalshi". Native: hero id 1.
    const m = {
      ...nativeMarket([
        { id: 1, name: "O/U 5.5", price: 0.99, won: true, source: "game_score" },
        { id: 2, name: "Kings", price: 0.99, won: true },
      ]),
      id: 114108, name: "Kings vs. Blue Jackets",
    };
    MARKET = m;
    mount();
    const h = hero();
    expect(h.resolvedName).toEqual(["O/U 5.5"]);
    expect(h.resolvedChip).toEqual(["Won"]);
    const legs = m.outcomes as Parameters<typeof gradedWinner>[0];
    expect((gradedWinner(legs, legs[0], "resolved") as { id?: number } | null)?.id).toBe(1);
  });

  it("11616Tests:241 — one supported winner served last and priced lowest is still named", async () => {
    // row(1, "Yes", price: 0.6), row(2, "No", price: 0.4),
    // row(3, "Push", price: 0.01, won: true, source: "game_score"). Native: hero id 3,
    // .verdict(.won), share "Push: Won — Awards field on Bain Luck".
    const m = nativeMarket([
      { id: 1, name: "Yes", price: 0.6 },
      { id: 2, name: "No", price: 0.4 },
      { id: 3, name: "Push", price: 0.01, won: true, source: "game_score" },
    ]);
    MARKET = m;
    mount();
    const h = hero();
    expect(h.resolvedName).toEqual(["Push"]);
    expect(h.resolvedChip).toEqual(["Won"]);
    expect(h.percent).toEqual([]);
    // The web share is the unfurl: it names the same result, no percent.
    const body = m;
    global.fetch = jest.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => body,
    }) as unknown as typeof fetch;
    const meta = await futuresMetadata({ params: { id: "11616" } } as never);
    expect(meta.title).toBe("Push won - Awards field");
    expect(String(meta.description)).toMatch(/^Push won \(Awards field\)\./);
    expect(String(meta.title)).not.toMatch(/%/);
  });
});

/* ──────── B1 / T2: one producer run, search and detail on the same input ──────── */

/**
 * The committed fixture is written by the backend's own producers and pinned
 * byte-for-byte by `test_committed_web_fixture_matches_actual_backend_producers`,
 * so the detail payload mounted here and the search rows compared against it
 * come from one input.
 */
type Served = { id?: number; name: string };
const FIXTURE = producerFixture as unknown as Record<
  string,
  {
    fresh_detail: Record<string, unknown>;
    fresh_search: { top_outcomes: Served[] };
    fresh_typeahead_top_outcomes?: Served[];
  }
>;

describe("B1: an unsupported raw flag beside a supported winner (open, independent)", () => {
  const entry = FIXTURE.b1_open_independent_raw_flag_beside_supported_winner;

  it("detail heroes the supported winner as Won; search's card and dropdown lead with it", () => {
    MARKET = entry.fresh_detail;
    mount();
    const h = hero();
    expect(h.openWon).toEqual(["Beta rung"]);
    expect(h.percent).toEqual([]);
    expect(entry.fresh_search.top_outcomes[0]).toMatchObject({ id: 2, name: "Beta rung" });
    expect(entry.fresh_typeahead_top_outcomes?.[0].name).toBe("Beta rung");
  });

  it("the served detail carries no lead, so the hero is chosen by the row rule alone", () => {
    expect(entry.fresh_detail.lead_outcome_id).toBeNull();
    const outcomes = entry.fresh_detail.outcomes as Parameters<typeof pickHeroOutcome>[0];
    const picked = pickHeroOutcome(outcomes, outcomes[0], false, false) as { id?: number } | null;
    expect(picked?.id).toBe(entry.fresh_search.top_outcomes[0].id);
  });
});

describe("T2: an open board whose field won (the route-reachable arm)", () => {
  const entry = FIXTURE.t2_open_field_winner;

  it("detail heroes Other as Won and search's card leads with Other", () => {
    MARKET = entry.fresh_detail;
    mount();
    expect(hero().openWon).toEqual(["Other"]);
    expect(entry.fresh_search.top_outcomes[0].name).toBe("Other");
  });
});
