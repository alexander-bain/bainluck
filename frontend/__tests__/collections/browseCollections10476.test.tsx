/**
 * #10476 — WEB BROWSE OPENS THE PUBLISHED NFL WEEK WITHOUT GUESSING ITS URL.
 *
 * Alex (Oct 4): Browse only opened a categories menu, so Week 4 could not be
 * found. The menu now asks `GET /api/containers/discover` when it opens and
 * links each hub Discover's own `admitCollection` accepts.
 *
 * `testEnvironment` is `node` with no DOM, so:
 * - the request lifecycle (open / close / timeout / stale answer / reuse) is
 *   driven on the loader object directly;
 * - the menu block is SSR-rendered from a loader already in each state;
 * - the two navs are SSR-rendered with Browse forced open (their only
 *   `useState(false)` is the open flag) so the real markup — collections AND
 *   every category — is read, not a description of it.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

const forceOpen = { value: false };

jest.mock("react", () => {
  const actual = jest.requireActual("react");
  return {
    ...actual,
    useState: (initial: unknown) =>
      forceOpen.value && initial === false ? [true, () => {}] : actual.useState(initial),
  };
});
jest.mock("next/link", () => {
  const ReactLib = jest.requireActual("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/navigation", () => ({ usePathname: () => "/sports" }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));

// The navs build their loader lazily through this factory; under SSR the menu
// renders whatever state that loader is already in.
let navLoader: import("@/lib/browseCollections").BrowseCollectionsLoader | null = null;
jest.mock("@/lib/browseCollections", () => {
  const actual = jest.requireActual("@/lib/browseCollections");
  return {
    ...actual,
    createBrowseCollectionsLoader: (...args: unknown[]) => navLoader ?? actual.createBrowseCollectionsLoader(...args),
  };
});

import {
  admitBrowseCollections,
  browseCollectionsUrl,
  createBrowseCollectionsLoader,
  BROWSE_COLLECTIONS_LIMIT,
  type BrowseCollectionsLoader,
} from "@/lib/browseCollections";
import PublishedCollectionsMenu from "@/components/collections/PublishedCollectionsMenu";
import DesktopNav from "@/components/DesktopNav";
import BottomNav from "@/components/BottomNav";

// ── fixtures: the production read's exact card shape (read 2026-10-04 19:05Z) ──

function nflWeek(week: number, overrides: Record<string, unknown> = {}) {
  const slug = `nfl-2026-week-${week}`;
  return {
    type: "collection",
    text: `NFL 2026 · Week ${week}`,
    id: week + 3,
    slug,
    name: `NFL 2026 · Week ${week}`,
    state: "published",
    revision: 34,
    edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week },
    status: "scheduled",
    window_start: null,
    window_end: null,
    game_count: week === 4 ? 16 : 15,
    question_count: week === 4 ? 3431 : 38,
    matched_event_ids: [],
    destination: { kind: "container", slug, web: `/collections/${slug}`, api: `/api/containers/${slug}` },
    ...overrides,
  };
}

const LIVE_BODY = { collections: [nflWeek(4), nflWeek(5)] };

const CATEGORIES = [
  ["MMA", "/hub/mma"],
  ["Boxing", "/hub/boxing"],
  ["Golf", "/hub/golf"],
  ["Tennis", "/hub/tennis"],
  ["Esports", "/hub/esports"],
  ["Politics", "/politics"],
  ["2026 Midterms", "/event/election/2026-midterms"],
  ["Entertainment", "/entertainment"],
  ["Economics", "/economics"],
  ["Weather", "/weather"],
  ["About", "/about"],
];

function jsonResponse(body: unknown, ok = true): Response {
  return { ok, json: () => Promise.resolve(body) } as unknown as Response;
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

/** A fetch whose answers the test releases by hand. */
function manualFetch() {
  const calls: { url: string; signal: AbortSignal; resolve: (r: Response) => void; reject: (e: unknown) => void }[] = [];
  const fetchImpl = ((url: string, init: RequestInit) =>
    new Promise<Response>((resolve, reject) => {
      calls.push({ url, signal: init.signal as AbortSignal, resolve, reject });
    })) as unknown as typeof fetch;
  return { calls, fetchImpl };
}

async function readyLoader(body: unknown = LIVE_BODY): Promise<BrowseCollectionsLoader> {
  const loader = createBrowseCollectionsLoader({ fetchImpl: (() => Promise.resolve(jsonResponse(body))) as unknown as typeof fetch });
  loader.open();
  await flush();
  expect(loader.getState().status).toBe("ready");
  return loader;
}

function menu(loader: BrowseCollectionsLoader, open = true, pathname: string | null = "/") {
  return renderToStaticMarkup(
    <PublishedCollectionsMenu open={open} pathname={pathname} variant="mobile" onNavigate={() => {}} loader={loader} />,
  );
}

// ── which hubs become links ─────────────────────────────────────────────────

describe("#10476 only hubs Discover would open become Browse links", () => {
  test("the published Week 4 and Week 5 hubs, in served order, at their canonical pages", () => {
    const entries = admitBrowseCollections(LIVE_BODY)!;
    expect(entries.map((e) => [e.name, e.href])).toEqual([
      ["NFL 2026 · Week 4", "/collections/nfl-2026-week-4"],
      ["NFL 2026 · Week 5", "/collections/nfl-2026-week-5"],
    ]);
    expect(entries[0].subtitle).toBe("16 games · 3431 questions");
  });

  test.each([
    ["unpublished", { state: "unpublished" }],
    ["withdrawn", { state: "withdrawn" }],
    ["empty (no games, no questions)", { game_count: 0, question_count: 0 }],
    ["edition disagreeing with the slug (wrong week)", { edition: { kind: "nfl_week", league: "nfl", season: 2026, stage: "Regular Season", week: 6 } }],
    ["an edition this ship does not offer", { edition: { kind: "theme", league: "nfl", season: 2026, stage: null, week: null } }],
    ["a destination off the canonical page", { destination: { kind: "container", slug: "nfl-2026-week-5", web: "https://elsewhere.example/x", api: "" } }],
    ["no destination", { destination: null }],
    ["a destination for another slug", { destination: { kind: "container", slug: "nfl-2026-week-4", web: "/collections/nfl-2026-week-4" } }],
    ["no name", { name: "  " }],
  ])("%s never becomes a link, and its sibling still does", (_label, overrides) => {
    const entries = admitBrowseCollections({ collections: [nflWeek(4), nflWeek(5, overrides)] })!;
    expect(entries.map((e) => e.href)).toEqual(["/collections/nfl-2026-week-4"]);
  });

  test("garbage cards and a card that throws on read are dropped alone", () => {
    const hostile = {};
    Object.defineProperty(hostile, "state", { get() { throw new Error("boom"); }, enumerable: true });
    const entries = admitBrowseCollections({ collections: [null, 7, "x", [], hostile, nflWeek(4), nflWeek(4)] })!;
    expect(entries.map((e) => e.slug)).toEqual(["nfl-2026-week-4"]);
  });

  test("a body that is not the read's shape is a failure, not 'none published'", () => {
    expect(admitBrowseCollections({ collections: [] })).toEqual([]);
    for (const bad of [null, undefined, "x", [], {}, { collections: {} }, { items: [nflWeek(4)] }]) {
      expect(admitBrowseCollections(bad)).toBeNull();
    }
  });

  test("whatever week is served is what shows — nothing is pinned to Week 4", () => {
    expect(admitBrowseCollections({ collections: [nflWeek(9)] })!.map((e) => e.href)).toEqual(["/collections/nfl-2026-week-9"]);
    for (const file of ["lib/browseCollections.ts", "components/collections/PublishedCollectionsMenu.tsx", "components/DesktopNav.tsx", "components/BottomNav.tsx"]) {
      const src = readFileSync(join(process.cwd(), file), "utf8");
      expect(src).not.toMatch(/week-\d|nfl-20\d\d|Week \d/);
    }
  });

  test("never more than the read's cap", () => {
    const many = Array.from({ length: 30 }, (_, i) => nflWeek(i + 1));
    expect(admitBrowseCollections({ collections: many })).toHaveLength(BROWSE_COLLECTIONS_LIMIT);
    expect(browseCollectionsUrl("https://api.test")).toBe(`https://api.test/api/containers/discover?limit=${BROWSE_COLLECTIONS_LIMIT}`);
  });
});

// ── the request lifecycle ───────────────────────────────────────────────────

describe("#10476 the menu asks once per open, gives up, and ignores late answers", () => {
  test("open → loading → ready", async () => {
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u" });
    expect(loader.getState().status).toBe("idle");
    loader.open();
    expect(loader.getState().status).toBe("loading");
    await flush();
    expect(calls).toHaveLength(1);
    calls[0].resolve(jsonResponse(LIVE_BODY));
    await flush();
    expect(loader.getState()).toMatchObject({ status: "ready" });
    expect(loader.getState().entries).toHaveLength(2);
  });

  test("closing mid-request aborts it, and its late answer changes nothing", async () => {
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u" });
    loader.open();
    await flush();
    loader.close();
    expect(calls[0].signal.aborted).toBe(true);
    expect(loader.getState().status).toBe("idle");
    calls[0].resolve(jsonResponse(LIVE_BODY));
    await flush();
    expect(loader.getState()).toEqual({ status: "idle", entries: [] });
  });

  test("an older request answering after a newer one started is ignored", async () => {
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u" });
    loader.open();
    await flush();
    loader.close();
    loader.open();
    await flush();
    expect(calls).toHaveLength(2);
    calls[0].resolve(jsonResponse({ collections: [nflWeek(5)] }));
    await flush();
    expect(loader.getState().status).toBe("loading");
    calls[1].resolve(jsonResponse(LIVE_BODY));
    await flush();
    expect(loader.getState().entries.map((e) => e.slug)).toEqual(["nfl-2026-week-4", "nfl-2026-week-5"]);
  });

  test("a read that never answers is abandoned at the bound", async () => {
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u", timeoutMs: 5 });
    loader.open();
    await flush();
    calls[0].signal.addEventListener("abort", () => calls[0].reject(new Error("aborted")));
    await new Promise((r) => setTimeout(r, 20));
    expect(calls[0].signal.aborted).toBe(true);
    expect(loader.getState()).toEqual({ status: "failed", entries: [] });
  });

  test.each([
    ["a non-2xx answer", () => Promise.resolve(jsonResponse(LIVE_BODY, false))],
    ["a network error", () => Promise.reject(new Error("offline"))],
    ["a malformed body", () => Promise.resolve(jsonResponse({ nope: true }))],
    ["a body that is not JSON", () => Promise.resolve({ ok: true, json: () => Promise.reject(new SyntaxError("x")) })],
  ])("%s fails quietly and the next open tries again", async (_label, impl) => {
    let n = 0;
    const fetchImpl = (() => (n++ === 0 ? impl() : Promise.resolve(jsonResponse(LIVE_BODY)))) as unknown as typeof fetch;
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u" });
    loader.open();
    await flush();
    expect(loader.getState()).toEqual({ status: "failed", entries: [] });
    loader.open();
    await flush();
    expect(loader.getState().status).toBe("ready");
  });

  test("a good answer is reused for a while, then asked again without showing the old one meanwhile", async () => {
    let clock = 0;
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u", now: () => clock, freshMs: 1000 });
    loader.open();
    await flush();
    calls[0].resolve(jsonResponse(LIVE_BODY));
    await flush();
    loader.close(); // nothing in flight: a no-op that keeps the answer
    clock = 999;
    loader.open();
    expect(calls).toHaveLength(1);
    expect(loader.getState().status).toBe("ready");
    clock = 1000;
    loader.open();
    expect(loader.getState()).toEqual({ status: "loading", entries: [] });
    await flush();
    expect(calls).toHaveLength(2);
    calls[1].resolve(jsonResponse({ collections: [nflWeek(5, { state: "withdrawn" })] }));
    await flush();
    expect(loader.getState()).toEqual({ status: "ready", entries: [] });
  });

  test("subscribers hear every change and can leave", async () => {
    const { calls, fetchImpl } = manualFetch();
    const loader = createBrowseCollectionsLoader({ fetchImpl, url: "u" });
    const heard: string[] = [];
    const leave = loader.subscribe(() => heard.push(loader.getState().status));
    loader.open();
    await flush();
    calls[0].resolve(jsonResponse(LIVE_BODY));
    await flush();
    leave();
    loader.close();
    expect(heard).toEqual(["loading", "ready"]);
  });
});

// ── the menu block ──────────────────────────────────────────────────────────

describe("#10476 the Collections block renders only what it may link", () => {
  test("ready: a labelled group of real links to each hub", async () => {
    const html = menu(await readyLoader());
    expect(html).toContain('role="group"');
    expect(html).toMatch(/aria-labelledby="([^"]+)"[\s\S]*id="\1"[^>]*>Collections</);
    expect(html).toContain('<a href="/collections/nfl-2026-week-4"');
    expect(html).toContain('<a href="/collections/nfl-2026-week-5"');
    expect(html).toContain("NFL 2026 · Week 4");
    expect(html).toContain("15 games · 38 questions");
    expect(html).not.toContain("aria-current");
  });

  test("the hub a reader is on is marked current", async () => {
    const html = menu(await readyLoader(), true, "/collections/nfl-2026-week-4");
    expect(html).toMatch(/<a href="\/collections\/nfl-2026-week-4" aria-current="page"/);
    expect(html).not.toMatch(/<a href="\/collections\/nfl-2026-week-5" aria-current/);
  });

  test("loading: a short status line, no links, marked busy", () => {
    const loader = createBrowseCollectionsLoader({ fetchImpl: (() => new Promise(() => {})) as unknown as typeof fetch, url: "u" });
    loader.open();
    const html = menu(loader);
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("<a ");
    loader.close();
  });

  test("failed, none published, nothing admissible, or menu shut: no block at all", async () => {
    const failed = createBrowseCollectionsLoader({ fetchImpl: (() => Promise.reject(new Error("x"))) as unknown as typeof fetch, url: "u" });
    failed.open();
    await flush();
    expect(menu(failed)).toBe("");
    expect(menu(await readyLoader({ collections: [] }))).toBe("");
    expect(menu(await readyLoader({ collections: [nflWeek(4, { state: "unpublished" })] }))).toBe("");
    expect(menu(await readyLoader(), false)).toBe("");
  });
});

// ── both navs ───────────────────────────────────────────────────────────────

function hrefsIn(html: string): string[] {
  return Array.from(html.matchAll(/<a href="([^"]+)"/g), (m) => m[1]);
}

describe("#10476 desktop and phone Browse both show collections above every category", () => {
  beforeEach(async () => {
    navLoader = await readyLoader();
    forceOpen.value = true;
  });
  afterEach(() => {
    forceOpen.value = false;
    navLoader = null;
  });

  test.each([
    ["desktop", () => <DesktopNav />, "desktop-browse-panel"],
    ["phone", () => <BottomNav />, "mobile-browse-panel"],
  ])("%s: Week 4 and Week 5 links, then all eleven categories unchanged", (_label, render, panelId) => {
    const html = renderToStaticMarkup(render());
    const hrefs = hrefsIn(html);
    const week4 = hrefs.indexOf("/collections/nfl-2026-week-4");
    expect(week4).toBeGreaterThanOrEqual(0);
    expect(hrefs[week4 + 1]).toBe("/collections/nfl-2026-week-5");
    const categories = CATEGORIES.map(([, href]) => hrefs.indexOf(href));
    expect(categories.every((i) => i > week4 + 1)).toBe(true);
    expect(categories).toEqual([...categories].sort((a, b) => a - b));
    for (const [label] of CATEGORIES) expect(html).toContain(label);
    // The panel is the button's controlled region and plain links, not an
    // ARIA menu (whose items would have to be menuitems with arrow keys).
    expect(html).toContain(`aria-controls="${panelId}"`);
    expect(html).toContain(`id="${panelId}"`);
    expect(html).toContain('aria-expanded="true"');
    expect(html).not.toContain('role="menu"');
    expect(html).not.toContain("menuitem");
  });

  test("phone: the sheet is bounded above the tab bar and scrolls, so every link stays tappable", () => {
    const html = renderToStaticMarkup(<BottomNav />);
    const panel = html.match(/<div id="mobile-browse-panel" class="([^"]+)"/);
    expect(panel).not.toBeNull();
    expect(panel![1]).toContain("max-h-[calc(100dvh-7rem)]");
    expect(panel![1]).toContain("overflow-y-auto");
    expect(panel![1]).not.toContain("overflow-hidden");
  });

  test("desktop: the dropdown is bounded and scrolls", () => {
    const html = renderToStaticMarkup(<DesktopNav />);
    const panel = html.match(/<div id="desktop-browse-panel" class="([^"]+)"/);
    expect(panel![1]).toMatch(/max-h-\[[^\]]+\]/);
    expect(panel![1]).toContain("overflow-y-auto");
  });

  test("shut, neither nav renders a collection link — Discover, Sports and My Stuff stay where they were", () => {
    forceOpen.value = false;
    for (const html of [renderToStaticMarkup(<DesktopNav />), renderToStaticMarkup(<BottomNav />)]) {
      expect(hrefsIn(html).filter((h) => h.startsWith("/collections/"))).toEqual([]);
      expect(hrefsIn(html)).toEqual(["/", "/sports", "/my-stuff"]);
      expect(html).toContain('aria-expanded="false"');
      expect(html).not.toContain("aria-controls");
    }
  });

  test("following a link, Escape, or any page change shuts Browse (source wiring)", () => {
    for (const file of ["components/DesktopNav.tsx", "components/BottomNav.tsx"]) {
      const src = readFileSync(join(process.cwd(), file), "utf8");
      expect(src).toMatch(/<PublishedCollectionsMenu[\s\S]*?onNavigate=\{\(href\) => \{\s*setBrowseOpen\(false\);/);
      expect(src).toMatch(/useEffect\(\(\) => \{\s*setBrowseOpen\(false\);\s*\}, \[pathname\]\);/);
      expect(src).toMatch(/e\.key === "Escape"/);
    }
  });
});
