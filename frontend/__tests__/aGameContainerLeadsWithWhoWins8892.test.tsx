/**
 * #8892 — A GAME'S MARKET PAGE LEADS WITH WHO WINS, NOT WITH AN OVER/UNDER.
 *
 * Production `/futures/61778284` at 390px, 2026-09-26 — *LoL: Cloud9 vs Team
 * Liquid (BO5) - LCS Playoffs*, `mutually_exclusive: false`:
 *
 *     71%  Over — O/U 3.5 Games          ← the hero, the pasted-link title, the card
 *     ...
 *     36%  Cloud9 — Match Winner         ← the number the title asks for, row 6
 *
 * A game container's legs answer DIFFERENT questions, so the highest-priced one is
 * only the most lopsided. The server now names the match-winner leg
 * (`lead_outcome_id`, lane1b's #8894) and every surface leads with it.
 *
 * 🔴 THE PAGE HAD TWO PATHS TO THE O/U LEG, NOT ONE. `leader` sorts by price, and
 * `pickHeroOutcome` on a `mutually_exclusive: false` board ignores `leader`
 * entirely (`pickLiveLeader`, #7439). Fixing only the sort leaves the hero on
 * "Over". `the hero leads with the match winner` is the assertion that kills that.
 *
 * Every other board serves `lead_outcome_id: null` (or no key, before #8894), and
 * the controls below pin that such a board renders exactly as it did.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
}));

let ACTIVE_MARKET: unknown = null;

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
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

const mockImageResponseCalls: React.ReactElement[] = [];
jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import FuturesDetailPage from "../app/futures/[id]/page";
import { generateMetadata } from "@/app/futures/[id]/layout";
import OgImage from "@/app/futures/[id]/opengraph-image";
import { readFileSync } from "fs";
import path from "path";
import {
  chartSeedsWithLead,
  pickCaptionSubject,
  pickChartSeedOutcomes,
  pickHeroOutcome,
  servedLeadOutcome,
} from "@/lib/futuresDetailDisplay";

/* ───────────────────────────── the specimen ───────────────────────────── */

const LEAD_ID = 233052896;

/**
 * `/api/futures/61778284` as production served it at 2026-09-26 ~19:15Z, every
 * leg in payload order, plus the `lead_outcome_id` #8894 serves for it. The
 * `probability_change_24h` values are invented and DIFFERENT per leg, so the
 * movement pill can say which row it was taken from.
 */
function cloud9(overrides: Record<string, unknown> = {}) {
  const leg = (id: number, name: string, probability: number, change: number) => ({
    id,
    name,
    probability,
    probability_change_24h: change,
    is_winner: null,
  });
  return {
    id: 61778284,
    name: "LoL: Cloud9 vs Team Liquid (BO5) - LCS Playoffs",
    status: "open",
    mutually_exclusive: false,
    market_type: "field",
    llm_sport_category: "esports",
    sport_name: null,
    hook_description: null,
    resolution_date: "2026-09-27T00:00:00Z",
    outcome_count: 8,
    outcomes: [
      leg(235154674, "Over — O/U 3.5 Games", 0.71, 0.09),
      leg(235154678, "Team Liquid — Game Handicap: TL (-1.5) vs Cloud9 (+1.5)", 0.44, 0.0),
      leg(235154676, "Cloud9 — Game 2 Winner", 0.425, 0.0),
      leg(235154677, "Cloud9 — Game 3 Winner", 0.415, 0.0),
      leg(235154675, "Cloud9 — Game 1 Winner", 0.405, 0.0),
      leg(LEAD_ID, "Cloud9 — Match Winner", 0.355, -0.04),
      leg(233176102, "Over — O/U 4.5 Games", 0.34, 0.0),
      leg(235154681, "Team Liquid — Game Handicap: TL (-2.5) vs Cloud9 (+2.5)", 0.205, 0.0),
    ],
    lead_outcome_id: LEAD_ID,
    ...overrides,
  };
}

/* ────────────────────────────── the harness ────────────────────────────── */

function renderPage(market: unknown): string {
  ACTIVE_MARKET = market;
  return renderToStaticMarkup(<FuturesDetailPage params={{ id: "61778284" }} />);
}

/** Text inside the first element carrying `data-testid`, or null (character scan, see #7906). */
function testIdText(html: string, id: string): string | null {
  const m = new RegExp(`data-testid="${id}"[^>]*>([\\s\\S]*?)</`).exec(html);
  if (!m) return null;
  let out = "";
  let inTag = false;
  for (const ch of m[1]) {
    if (ch === "<") inTag = true;
    else if (ch === ">") inTag = false;
    else if (!inTag) out += ch;
  }
  return out.trim();
}

function mockFetch(body: unknown): void {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  }) as unknown as typeof fetch;
}

async function titleFor(body: unknown): Promise<string> {
  mockFetch(body);
  const meta = await generateMetadata({ params: Promise.resolve({ id: "61778284" }) });
  return String(meta.title);
}

async function cardText(body: unknown): Promise<string> {
  mockImageResponseCalls.length = 0;
  mockFetch(body);
  await OgImage({ params: { id: "61778284" } });
  expect(mockImageResponseCalls).toHaveLength(1);
  const found: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (typeof node === "string" || typeof node === "number") {
      if (String(node).trim() !== "") found.push(String(node));
      return;
    }
    if (React.isValidElement(node)) walk((node.props as { children?: unknown }).children);
  };
  walk(mockImageResponseCalls[0]);
  return found.join(" ");
}

/* ═════════════════════════════ the rule ═════════════════════════════ */

describe("servedLeadOutcome", () => {
  const outs = cloud9().outcomes;

  test("returns the named row while it is on the board with a price", () => {
    expect(servedLeadOutcome(outs, LEAD_ID, "open")?.name).toBe("Cloud9 — Match Winner");
  });

  test.each([
    ["null (every non-container board)", null, "open"],
    ["absent (a build before #8894)", undefined, "open"],
    ["not on the board", 999, "open"],
    ["on a settled market — the grade decides that hero", LEAD_ID, "resolved"],
  ])("returns null when the id is %s", (_label, id, status) => {
    expect(servedLeadOutcome(outs, id as number | null | undefined, status)).toBeNull();
  });

  test("returns null when the named row has no price", () => {
    const unpriced = outs.map((o) => (o.id === LEAD_ID ? { ...o, probability: null } : o));
    expect(servedLeadOutcome(unpriced, LEAD_ID, "open")).toBeNull();
  });

  test("a price of 0 is still a price", () => {
    const zero = outs.map((o) => (o.id === LEAD_ID ? { ...o, probability: 0 } : o));
    expect(servedLeadOutcome(zero, LEAD_ID, "open")?.id).toBe(LEAD_ID);
  });

  test("the specimen discriminates: without the lead, the price rules pick the O/U leg", () => {
    // If this stops holding, every page assertion below stops discriminating.
    expect(pickHeroOutcome(outs, outs[0], false, false)?.name).toBe("Over — O/U 3.5 Games");
  });
});

/* ═════════════════════════════ the chart ═════════════════════════════ */

describe("the chart the page opens on", () => {
  const outs = cloud9().outcomes;
  const lead = outs.find((o) => o.id === LEAD_ID)!;
  const priceSeeds = pickChartSeedOutcomes(outs, false, false);
  const allHistory = new Set(outs.map((o) => o.id));

  test("the specimen discriminates: the price seeds leave the lead off and caption the O/U leg", () => {
    expect(priceSeeds.map((o) => o.id)).not.toContain(LEAD_ID);
    const drawn = new Set(priceSeeds.map((o) => o.id));
    expect(pickCaptionSubject(outs, drawn)?.name).toBe("Over — O/U 3.5 Games");
  });

  test("🔴 draws the lead's line alone, so the caption is about the hero's leg", () => {
    const seeds = chartSeedsWithLead(priceSeeds, lead, allHistory);
    expect(seeds.map((o) => o.id)).toEqual([LEAD_ID]);
    const drawn = new Set(seeds.map((o) => o.id));
    expect(pickCaptionSubject(outs, drawn)?.name).toBe("Cloud9 — Match Winner");
  });

  test("history not loaded yet: the lead still seeds", () => {
    expect(chartSeedsWithLead(priceSeeds, lead, new Set()).map((o) => o.id)).toEqual([LEAD_ID]);
  });

  test("a lead with no history rows keeps the price seeds, not an empty chart", () => {
    const withoutLead = new Set([...allHistory].filter((id) => id !== LEAD_ID));
    expect(chartSeedsWithLead(priceSeeds, lead, withoutLead)).toBe(priceSeeds);
  });

  test("no lead: the price seeds, untouched", () => {
    expect(chartSeedsWithLead(priceSeeds, null, allHistory)).toBe(priceSeeds);
  });

  test("the page's seed effect asks the helper, with the served lead", () => {
    // The effect does not run under SSR and this suite has no DOM, so the wiring
    // is read from source; the rule itself is asserted above.
    const page = readFileSync(path.join(__dirname, "../app/futures/[id]/page.tsx"), "utf8");
    expect(page).toMatch(/const seeds = chartSeedsWithLead\(priceSeeds, leadOutcome, historyIds\);/);
    expect(page).toMatch(/historyOutcomes, leadOutcome\]\);/);
  });
});

/* ═════════════════════════════ the page ═════════════════════════════ */

describe("the futures page", () => {
  test("positive control: the live hero renders on the specimen", () => {
    const html = renderPage(cloud9({ lead_outcome_id: null }));
    expect(testIdText(html, "hero-percent")).toBe("71");
    expect(testIdText(html, "hero-outcome-name")).toBe("Over — O/U 3.5 Games");
  });

  test("🔴 the hero leads with the match winner, number and name together", () => {
    const html = renderPage(cloud9());
    expect(testIdText(html, "hero-outcome-name")).toBe("Cloud9 — Match Winner");
    expect(testIdText(html, "hero-percent")).toBe("36");
  });

  test("the movement pill is the lead leg's, not the O/U leg's", () => {
    const control = renderPage(cloud9({ lead_outcome_id: null }));
    const shipped = renderPage(cloud9());
    // Over moved +9, Cloud9 −4: each pill carries its own row's number.
    expect(testIdText(control, "hero-movement")).toContain("9");
    expect(testIdText(shipped, "hero-movement")).toContain("4");
    expect(testIdText(shipped, "hero-movement")).not.toContain("9");
  });

  test("the O/U leg keeps its row — only the hero moved", () => {
    const html = renderPage(cloud9());
    expect(html).toContain("O/U 3.5 Games");
  });

  test("a settled container is untouched: the grade decides, not the pointer", () => {
    const settled = cloud9({
      status: "resolved",
      outcomes: cloud9().outcomes.map((o) => ({
        ...o,
        is_winner: o.name === "Over — O/U 3.5 Games",
      })),
    });
    const withLead = renderPage(settled);
    const without = renderPage({ ...settled, lead_outcome_id: null });
    expect(withLead).toBe(without);
  });
});

/* ═════════════════════════ the pasted link ═════════════════════════ */

describe("the pasted link's title and card", () => {
  test("control: without the lead, the title leads with the O/U leg", async () => {
    expect(await titleFor(cloud9({ lead_outcome_id: null }))).toContain("Over — O/U 3.5 Games 71%");
  });

  test("🔴 the title leads with the match winner", async () => {
    const title = await titleFor(cloud9());
    expect(title).toContain("Cloud9 — Match Winner 36%");
    expect(title).not.toContain("O/U 3.5");
  });

  test("control: without the lead, the card draws the O/U leg", async () => {
    expect(await cardText(cloud9({ lead_outcome_id: null }))).toContain("Over — O/U 3.5 Games");
  });

  test("🔴 the card draws the match winner", async () => {
    const text = await cardText(cloud9());
    expect(text).toContain("Cloud9 — Match Winner");
    expect(text).not.toContain("O/U 3.5");
  });
});
