/**
 * #5105 — the REAL Discover page (`app/discover/page.tsx`) wired to the opening
 * edition, mounted through `react-dom/client` with the real SWR, the real
 * paging / restore / transition / section helpers and the real section
 * component. Only the network (`fetchFeed`), auth, analytics, the price
 * stream and the leaf card components are replaced, and the internal option is
 * mocked ON (it ships OFF; the first suite proves that and the legacy path).
 *
 * Every payload is a local mocked page. Cards are `politics` events, a
 * category `spaceBySport` never moves, so served order is rendered order.
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig, useSWRConfig } from "swr";

let mockOptionOn = true;
jest.mock("@/lib/discover/openingEditionOption", () => ({
  get DISCOVER_OPENING_EDITION_ENABLED() {
    return mockOptionOn;
  },
}));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  fetchFeed: jest.fn(),
  fetchResolutions: jest.fn(),
}));
jest.mock("@/components/AuthProvider", () => ({
  useAuthContext: () => ({
    user: null,
    isLoading: false,
    isAuthenticated: false,
    isAuthAvailable: false,
    signInWithGoogle: jest.fn(),
    signInWithApple: jest.fn(),
    getToken: jest.fn(),
  }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: () => {}, isMaxReached: false }),
}));
jest.mock("@/hooks/useDiscoverPriceStream", () => ({
  // The price stream projects 1:1 and in order; identity here keeps the
  // page's own single subscription owner and visible-window slice in play.
  useDiscoverPriceStream: (groups: unknown[]) => ({ items: groups, setPriceVisibility: () => {} }),
}));
jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));
jest.mock("@/lib/discoverInteractions", () => ({
  ...jest.requireActual("@/lib/discoverInteractions"),
  getDiscoverItemAnalytics: (item: { data: { id?: number } }) => ({
    content_type: "event",
    item_id: String(item?.data?.id),
    category: "politics",
    item_name: "card",
    score: 0,
    market_type: "unshaped",
  }),
  recordDiscoverInteraction: () => {},
  sendDiscoverInteraction: () => {},
}));
jest.mock("@/lib/discover/feedFreshness", () => ({ isStale: () => false }));
jest.mock("@/components/discover/utils", () => ({
  ...jest.requireActual("@/components/discover/utils"),
  feedItemHasRenderableContent: (item: { data: { hide?: boolean } }) => !item.data.hide,
  collectSuppressedEnvelopes: () => [],
  feedItemCanBeGuessed: () => false,
}));
jest.mock("@/components/DiscoverCard", () => {
  const card = ({ groupedItem, positionIndex }: { groupedItem: { item: { data: { id: number; prob: number } } }; positionIndex: number }) => (
    <div data-card={`c${groupedItem.item.data.id}`} data-position={positionIndex}>
      {`c${groupedItem.item.data.id}:${groupedItem.item.data.prob}`}
    </div>
  );
  return { __esModule: true, default: card, GuessCard: () => null, DailyChallengeCard: () => null, ResolutionCard: () => null, ResolutionGroup: () => null };
});
jest.mock("@/components/discover/DiscoverCollectionCard", () => ({
  __esModule: true,
  default: ({ entry }: { entry: { slug: string } }) => <div data-card={`collection:${entry.slug}`} />,
}));
jest.mock("@/components/discover/MasonryCell", () => ({
  __esModule: true,
  MASONRY_GRID_CLASS: "grid",
  default: ({ children, className, ...rest }: { children: React.ReactNode; className?: string }) => (
    <div {...rest} data-class={className ?? ""}>{children}</div>
  ),
}));
const endOfFeed: { onRefresh?: () => void } = {};
jest.mock("@/components/discover/EndOfFeedCard", () => ({
  __esModule: true,
  default: ({ count, onRefresh }: { count: number; onRefresh: () => void }) => {
    endOfFeed.onRefresh = onRefresh;
    return <div data-end-of-feed={count} />;
  },
}));
const unavailable: { onRetry?: () => void } = {};
jest.mock("@/components/discover/FeedUnavailableNotice", () => ({
  __esModule: true,
  default: ({ onRetry, variant }: { onRetry: () => void; variant: string }) => {
    unavailable.onRetry = onRetry;
    return <div data-unavailable={variant} />;
  },
}));
jest.mock("@/components/discover/FeedBootScript", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/FirstRunOrientation", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/SignInToPersonalizeInvite", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/DiscoverSkeletonGrid", () => ({ __esModule: true, default: () => <div data-skeleton="1" /> }));

import DiscoverPage from "@/app/discover/page";
import { fetchFeed } from "@/lib/api";
import { CONTINUATION_HEADING } from "@/components/discover/ContinuationSections";
import { foldContinuationPage, type ContinuationSections as Sections } from "@/lib/discover/continuationSections";
import {
  FEED_EDITION_SNAPSHOT_VERSION,
  FEED_SECTION_SNAPSHOT_VERSION,
  FEED_SCROLL_KEY,
  FEED_SNAPSHOT_KEY,
  FEED_SNAPSHOT_MAX_ITEMS,
  FEED_SNAPSHOT_VERSION,
  serializeFeedSnapshot,
} from "@/lib/discover/feedRestore";

// ── a browser just big enough for the page ──────────────────────────────────

class MemoryStorage {
  private m = new Map<string, string>();
  getItem(k: string) { return this.m.has(k) ? this.m.get(k)! : null; }
  setItem(k: string, v: string) { this.m.set(k, String(v)); }
  removeItem(k: string) { this.m.delete(k); }
  clear() { this.m.clear(); }
  key(i: number) { return [...this.m.keys()][i] ?? null; }
  get length() { return this.m.size; }
}
type Observer = { cb: (entries: Array<{ isIntersecting: boolean }>) => void; options?: { rootMargin?: string }; active: boolean; node?: unknown };
const observers: Observer[] = [];
class FakeIntersectionObserver {
  private rec: Observer;
  constructor(cb: Observer["cb"], options?: Observer["options"]) {
    this.rec = { cb, options, active: true };
    observers.push(this.rec);
  }
  observe(node: unknown) { this.rec.node = node; }
  unobserve() {}
  disconnect() { this.rec.active = false; }
  takeRecords() { return []; }
}
const win = window as unknown as Record<string, unknown>;
const local = new MemoryStorage();
const session = new MemoryStorage();
Object.assign(win, {
  localStorage: local,
  sessionStorage: session,
  scrollY: 0,
  innerHeight: 844,
  scrollTo: () => {},
  setTimeout,
  clearTimeout,
});
Object.assign(globalThis, {
  localStorage: local,
  sessionStorage: session,
  IntersectionObserver: FakeIntersectionObserver,
  requestAnimationFrame: (cb: () => void) => setTimeout(cb, 0) as unknown as number,
  cancelAnimationFrame: (id: number) => clearTimeout(id),
});
const doc = document as unknown as Record<string, unknown>;
doc.visibilityState = "visible";
(doc.documentElement as Record<string, unknown>).scrollHeight = 1_000_000;

// ── fixtures ────────────────────────────────────────────────────────────────

type Card = { type: "event"; data: { id: number; sport: string; prob: number; hide?: boolean }; score: number };
const card = (id: number, prob = 0.5, extra: Partial<Card["data"]> = {}): Card => ({
  type: "event",
  data: { id, sport: "politics", prob, ...extra },
  score: 1000 - id,
});
const list = (n: number, from = 0, prob = 0.5) => Array.from({ length: n }, (_, i) => card(from + i, prob));

interface ReplyOpts {
  edition?: string | null;
  boundary?: number | null;
  status?: string;
  total?: number;
  limit?: number;
}
/** One served page of `deck`, the way `_feed_page_payload` shapes it. */
function reply(deck: unknown[], offset: number, opts: ReplyOpts = {}) {
  const total = opts.total ?? deck.length;
  const items = deck.slice(offset, offset + (opts.limit ?? 20));
  return {
    items,
    offset,
    total,
    has_more: offset + items.length < total,
    ...(opts.edition === null ? {} : { edition: opts.edition ?? "E1" }),
    ...(opts.boundary === undefined || opts.boundary === null ? {} : { continuation_start: opts.boundary }),
    ...(opts.status ? { edition_status: opts.status } : {}),
  };
}
const UNAVAILABLE = { items: [], offset: 0, total: 0, has_more: false, cache: { status: "unavailable" } };

// ── the network: every call is recorded and answered by the test ────────────

type Call = { params: Record<string, unknown>; opts?: Record<string, unknown>; resolve: (v: unknown) => void; reject: (e: unknown) => void };
const calls: Call[] = [];
const fetchMock = fetchFeed as jest.Mock;
fetchMock.mockImplementation((params: Record<string, unknown>, opts?: Record<string, unknown>) =>
  new Promise((resolve, reject) => { calls.push({ params, opts, resolve, reject }); }),
);
const pending = () => calls.filter((c) => !(c as Call & { done?: boolean }).done);

async function settle(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }
}
async function answer(call: Call, value: unknown) {
  (call as Call & { done?: boolean }).done = true;
  await act(async () => { call.resolve(value); });
  await settle();
}
function lastCall(): Call {
  return calls[calls.length - 1];
}

// ── mounting the real page ──────────────────────────────────────────────────

let root: Root | null = null;
let swrMutate: ((key: unknown) => Promise<unknown>) | null = null;
function CaptureMutate() {
  swrMutate = useSWRConfig().mutate as unknown as (key: unknown) => Promise<unknown>;
  return null;
}
async function mount(cache: Map<unknown, unknown> = new Map()) {
  const container = (document as unknown as { createElement: (t: string) => unknown }).createElement("div");
  (document as unknown as { body: { appendChild: (n: unknown) => void } }).body.appendChild(container);
  root = createRoot(container as Element);
  await act(async () => {
    root!.render(
      <SWRConfig value={{ provider: () => cache as never, dedupingInterval: 0 }}>
        <CaptureMutate />
        <DiscoverPage />
      </SWRConfig>,
    );
  });
  await settle();
  return container as unknown as Node;
}
async function unmount() {
  const current = root;
  root = null;
  await act(async () => { current?.unmount(); });
}
async function revalidate() {
  await act(async () => { void swrMutate!(["discover-feed", "anonymous"]); });
  await settle();
}
function attached(node: unknown): boolean {
  let at = node as { parentNode?: unknown } | null | undefined;
  while (at) {
    if (at === (document as unknown as { body: unknown }).body) return true;
    at = at.parentNode as typeof at;
  }
  return false;
}
/** The sentinel scrolls into the band and out again — only if a live observer
 *  is watching a sentinel that is actually in the document, as in a browser. */
async function fireSentinel() {
  const sentinel = observers.filter((o) => o.active && o.options?.rootMargin === "400px" && attached(o.node)).at(-1);
  if (!sentinel) throw new Error("no observed sentinel is in the document");
  await act(async () => { sentinel.cb([{ isIntersecting: true }]); });
  await act(async () => { sentinel.cb([{ isIntersecting: false }]); });
  await settle();
}

type Node = { childNodes: Node[]; nodeType: number; tagName?: string; textContent: string; [k: string]: unknown };
function walk(node: Node, out: Node[] = []): Node[] {
  out.push(node);
  for (const child of node.childNodes ?? []) walk(child, out);
  return out;
}
/** The page in document order: card ids, and `H` where the heading sits. */
function sequence(container: Node): string[] {
  return walk(container).flatMap((n) => {
    if (n.tagName === "H2" && n.textContent === CONTINUATION_HEADING) return ["H"];
    if (typeof n["data-card"] === "string") return [n["data-card"] as string];
    return [];
  });
}
const cardsOf = (container: Node) => sequence(container).filter((t) => t !== "H");
const headings = (container: Node) => sequence(container).filter((t) => t === "H").length;
const positions = (container: Node) => walk(container).filter((n) => n["data-position"] !== undefined).map((n) => Number(n["data-position"]));
const peeks = (container: Node) => walk(container).filter((n) => n["data-class"] === "animate-peek-right").length;
const textOf = (container: Node, id: string) => walk(container).find((n) => n["data-card"] === id)?.textContent;
const has = (container: Node, attr: string) => walk(container).some((n) => n[attr] !== undefined);
const ids = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => `c${from + i}`);
const storedSnapshot = () => JSON.parse(session.getItem(FEED_SNAPSHOT_KEY) ?? "null");

beforeEach(() => {
  mockOptionOn = true;
  calls.length = 0;
  observers.length = 0;
  local.clear();
  session.clear();
  delete win.__blDiscoverDocumentSeen;
  endOfFeed.onRefresh = undefined;
  unavailable.onRetry = undefined;
});
afterEach(async () => {
  await unmount();
});

// ─────────────────────────────────────────────────────────────────────────────

describe("#5105 option OFF (the shipped value): today's page exactly", () => {
  it("ships the option false", () => {
    expect(jest.requireActual("@/lib/discover/openingEditionOption").DISCOVER_OPENING_EDITION_ENABLED).toBe(false);
  });

  it("renders one flat list with no heading, pins nothing and writes today's snapshot bytes", async () => {
    mockOptionOn = false;
    const deck = list(40);
    const page = await mount();
    expect(calls).toHaveLength(1);
    expect(calls[0].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    expect(sequence(page)).toEqual(ids(0, 20));
    expect(has(page, "data-discover-section")).toBe(false);
    const stored = storedSnapshot();
    expect(stored.v).toBe(FEED_SNAPSHOT_VERSION);
    expect("sections" in stored || "cursor" in stored).toBe(false);
    // Legacy paging: count cursor, no token.
    await fireSentinel();
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15 });
  });
});

describe("#5105 option ON — one initial request, one window, one heading", () => {
  it("issues exactly the legacy initial request once, and no uninvited second one", async () => {
    const page = await mount();
    expect(calls).toHaveLength(1);
    expect(calls[0].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    expect(calls[0].opts).toEqual({ sharedAnonEligible: true, authenticated: false });
    await answer(calls[0], reply(list(33), 0, { boundary: 3 }));
    await settle(10);
    expect(calls).toHaveLength(1);
    expect(cardsOf(page)).toHaveLength(20);
  });

  it("opening 3 + continuation 30 under a global window of 20: 20 cards, one heading, one first position, raw-cursor paging", async () => {
    const deck = list(33);
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
    expect(cardsOf(page)).toHaveLength(20);
    expect(headings(page)).toBe(1);
    expect(peeks(page)).toBe(1);
    expect(positions(page)).toEqual(Array.from({ length: 20 }, (_, i) => i));

    await fireSentinel();
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E1" });
    await answer(calls[1], reply(deck, 20, { boundary: 3, status: "pinned" }));
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 33)]);
    expect(positions(page)).toEqual(Array.from({ length: 33 }, (_, i) => i));
    expect(peeks(page)).toBe(1);
  });

  it("classifies by raw server position before filtering: a filtered first continuation card moves nothing", async () => {
    const deck = list(30);
    deck[1] = card(1, 0.5, { hide: true });
    deck[3] = card(3, 0.5, { hide: true });
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    expect(sequence(page)).toEqual(["c0", "c2", "H", ...ids(4, 20)]);
    expect(positions(page).slice(0, 3)).toEqual([0, 1, 2]);
  });

  it("boundary 0: the heading leads and there is still one first position", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(30), 0, { boundary: 0 }));
    expect(sequence(page)).toEqual(["H", ...ids(0, 20)]);
    expect(peeks(page)).toBe(1);
    expect(positions(page)[0]).toBe(0);
  });

  it("every opening card filtered: the continuation begins at the top under its heading", async () => {
    const deck = list(30);
    for (const n of [0, 1, 2]) deck[n] = card(n, 0.5, { hide: true });
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    expect(sequence(page)).toEqual(["H", ...ids(3, 20)]);
  });

  it("no surviving continuation card: no heading", async () => {
    const deck = list(20);
    deck[18] = card(18, 0.5, { hide: true });
    deck[19] = card(19, 0.5, { hide: true });
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary: 18 }));
    expect(sequence(page)).toEqual(ids(0, 18));
  });

  it("a collection stays in the section the server placed it in", async () => {
    const hub = (slug: string, week: number) => ({
      type: "collection",
      data: {
        state: "published", id: week, revision: 1, name: `Week ${week}`, slug,
        edition: { league: "nfl", kind: "nfl_week", season: 2026, week, stage: "Regular Season" },
        game_count: 3, question_count: 0,
        destination: { kind: "container", slug, web: `/collections/${slug}` },
      },
    });
    // c0 c1 [hubA] | c3 c4 [hubB] c6 ... — hubA's followers are all continuation.
    const deck: unknown[] = [card(0), card(1), hub("nfl-2026-week-5", 5), card(3), card(4), hub("nfl-2026-week-6", 6), ...list(14, 6)];
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    expect(sequence(page)).toEqual([
      "c0", "c1", "collection:nfl-2026-week-5", "H", "c3", "c4", "collection:nfl-2026-week-6", ...ids(6, 20),
    ]);
  });
});

describe("#5105 option ON — current bodies and late replies", () => {
  it("a pinned background refresh renders the fresh price in place", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(30), 0, { boundary: 3 }));
    expect(textOf(page, "c1")).toBe("c1:0.5");
    await revalidate();
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" });
    const moved = list(30);
    moved[1] = card(1, 0.73);
    moved[4] = card(4, 0.12);
    await answer(calls[1], reply(moved, 0, { boundary: 3, status: "pinned" }));
    expect(textOf(page, "c1")).toBe("c1:0.73");
    expect(textOf(page, "c4")).toBe("c4:0.12");
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
  });

  it("an old in-flight page cannot touch the deck that replaced its edition", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(40), 0, { boundary: 3 }));
    await fireSentinel();
    const oldPage = calls[1];
    expect(oldPage.params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E1" });
    // While page two is in flight, a background tick finds E1 retired at page zero.
    await revalidate();
    await answer(calls[2], reply(list(30, 100), 0, { edition: "E2", boundary: 0, status: "expired" }));
    expect(sequence(page)).toEqual(["H", ...ids(100, 120)]);
    await answer(oldPage, reply(list(40), 20, { boundary: 3, status: "pinned" }));
    expect(sequence(page)).toEqual(["H", ...ids(100, 120)]);
    expect(calls).toHaveLength(3);
  });
});

describe("#5105 option ON — a retired edition restarts from page zero once", () => {
  async function retiredTail() {
    const page = await mount();
    await answer(calls[0], reply(list(40), 0, { boundary: 3 }));
    await fireSentinel();
    await answer(calls[1], reply(list(40, 500), 20, { edition: "E9", status: "expired" }));
    return page;
  }

  it("keeps the visible deck and asks for one unpinned page zero, then replaces atomically", async () => {
    const page = await retiredTail();
    const restarts = calls.slice(2);
    expect(restarts).toHaveLength(1);
    expect(restarts[0].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    // Nothing of the retired page was appended; the reader's deck is intact.
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);

    await answer(restarts[0], reply(list(40, 200), 0, { edition: "E2", boundary: 0 }));
    expect(sequence(page)).toEqual(["H", ...ids(200, 220)]);
    expect(calls).toHaveLength(3);
    // The window and its seed reset with the edition: one advance pages again.
    await fireSentinel();
    expect(calls).toHaveLength(4);
    expect(calls[3].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E2" });
  });

  it("an unavailable replacement keeps the deck and its cursor and raises the retry state, without re-asking", async () => {
    const page = await retiredTail();
    await answer(calls[2], UNAVAILABLE);
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    await settle(10);
    expect(calls).toHaveLength(3);

    // Retry asks for ONE page zero pinned to the held edition (the retired page
    // zero IS the current list). The old frontier is not paged beside it: a
    // retired reply there would only ask for a second, competing replacement.
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    const retried = calls.slice(3);
    expect(retried.map((c) => c.params)).toEqual([{ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" }]);
    expect(has(page, "data-unavailable")).toBe(false);
    await answer(retried[0], reply(list(30, 300), 0, { edition: "E3", boundary: 2, status: "expired" }));
    expect(sequence(page)).toEqual(["c300", "c301", "H", ...ids(302, 320)]);
    // The new edition's window is fresh; nothing more is asked.
    await settle(10);
    expect(calls).toHaveLength(4);
  });

  it("an unsupported replacement (untokened over a section deck) is refused the same way", async () => {
    const page = await retiredTail();
    await answer(calls[2], reply(list(40, 200), 0, { edition: null }));
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    expect(calls).toHaveLength(3);
  });

  it("a thrown replacement keeps the deck and raises the retry state", async () => {
    const page = await retiredTail();
    (calls[2] as Call & { done?: boolean }).done = true;
    await act(async () => { calls[2].reject(new Error("network")); });
    await settle();
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    expect(calls).toHaveLength(3);
  });
});

describe("#5105 option ON — Back restores the sections; refresh opens a new edition", () => {
  async function browse(deckSize: number, pages: number, boundary: number) {
    const deck = list(deckSize);
    const page = await mount();
    await answer(calls[0], reply(deck, 0, { boundary }));
    for (let p = 1; p < pages; p += 1) {
      await fireSentinel();
      await answer(lastCall(), reply(deck, p * 20, { boundary, status: "pinned" }));
    }
    return { deck, page };
  }

  it("restores the section deck before any cached reply, and keeps pinning", async () => {
    const cache = new Map<unknown, unknown>();
    const deck = list(60);
    let page = await mount(cache);
    await answer(calls[0], reply(deck, 0, { boundary: 3 }));
    await fireSentinel();
    await answer(calls[1], reply(deck, 20, { boundary: 3, status: "pinned" }));
    expect(cardsOf(page)).toHaveLength(40);
    const stored = storedSnapshot();
    expect(stored.v).toBe(FEED_SECTION_SNAPSHOT_VERSION);
    expect(stored.cursor).toBe(40);
    expect(stored.hasMore).toBe(true);
    await unmount();

    // Back: SWR still holds the cold page-zero reply of the first mount. Taken
    // as current it would replace the restored 40 cards with 20.
    page = await mount(cache);
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 40)]);
    const revalidation = lastCall();
    expect(revalidation.params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" });
    await answer(revalidation, reply(deck, 0, { boundary: 3, status: "pinned" }));
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 40)]);

    // The restored window and its seed belong to the restored edition; paging
    // continues from the stored raw cursor with the token.
    const before = calls.length;
    await fireSentinel();
    expect(calls.length).toBe(before + 1);
    expect(lastCall().params).toEqual({ limit: 20, offset: 40, event_pct: 0.15, edition: "E1" });
    // ...and a retirement there replaces the restored deck and resets BOTH seeds.
    await answer(lastCall(), reply(list(60, 700), 40, { edition: "E7", status: "superseded" }));
    await answer(lastCall(), reply(list(60, 800), 0, { edition: "E8", boundary: 1 }));
    expect(sequence(page)).toEqual(["c800", "H", ...ids(801, 820)]);
    const afterReplace = calls.length;
    await fireSentinel();
    expect(calls.length).toBe(afterReplace + 1);
    expect(lastCall().params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E8" });
  });

  it("an exhausted 160-card deck restored through the 120 cap still reaches the omitted 40", async () => {
    const cache = new Map<unknown, unknown>();
    const { deck, page: first } = await browse(160, 8, 5);
    expect(cardsOf(first)).toHaveLength(160);
    const stored = storedSnapshot();
    expect(stored.page1.length + stored.rest.length).toBe(FEED_SNAPSHOT_MAX_ITEMS);
    // Neither the old cursor (160, skips the tail) nor the old hasMore (false, strands it).
    expect(stored.cursor).toBe(120);
    expect(stored.hasMore).toBe(true);
    await unmount();

    const page = await mount(cache);
    expect(cardsOf(page)).toHaveLength(120);
    expect(headings(page)).toBe(1);
    await answer(lastCall(), reply(deck, 0, { boundary: 5, status: "pinned" }));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 120, event_pct: 0.15, edition: "E1" });
    await answer(lastCall(), reply(deck, 120, { boundary: 5, status: "pinned" }));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 140, event_pct: 0.15, edition: "E1" });
    await answer(lastCall(), reply(deck, 140, { boundary: 5, status: "pinned" }));
    expect(sequence(page)).toEqual([...ids(0, 5), "H", ...ids(5, 160)]);
    expect(walk(page).some((n) => n["data-end-of-feed"] !== undefined)).toBe(true);
  });

  it("a manual refresh replaces the restored edition and resets BOTH window seeds", async () => {
    const cache = new Map<unknown, unknown>();
    const { deck, page: first } = await browse(60, 3, 3);
    // The window holds the whole exhausted deck: the end-of-feed card shows.
    expect(walk(first).some((n) => n["data-end-of-feed"] !== undefined)).toBe(true);
    await unmount();

    const page = await mount(cache);
    expect(cardsOf(page)).toHaveLength(60);
    await answer(lastCall(), reply(deck, 0, { boundary: 3, status: "pinned" }));
    expect(endOfFeed.onRefresh).toBeDefined();
    const before = calls.length;
    await act(async () => { endOfFeed.onRefresh!(); });
    await settle();
    expect(calls.length).toBe(before + 1);
    // Unpinned: the reader asked for the current list.
    expect(lastCall().params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(lastCall(), reply(list(40, 900), 0, { edition: "E5", boundary: 4 }));
    expect(sequence(page)).toEqual([...ids(900, 904), "H", ...ids(904, 920)]);
    // A seed left at the restored 60 would sit out this advance.
    await fireSentinel();
    expect(calls.length).toBe(before + 2);
    expect(lastCall().params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E5" });
  });

  it("a manual refresh still refuses an empty page one (today's rule) and keeps the deck", async () => {
    const { page } = await browse(20, 1, 3);
    expect(endOfFeed.onRefresh).toBeDefined();
    await act(async () => { endOfFeed.onRefresh!(); });
    await settle();
    await answer(lastCall(), { items: [], offset: 0, total: 0, has_more: false });
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
  });

  it("a token-less legacy snapshot restores as today's page and is reconciled, not replaced", async () => {
    const legacy = serializeFeedSnapshot({ page1: list(20), rest: list(20, 20), visibleCount: 40, hasMore: true })!;
    expect(JSON.parse(legacy).v).toBe(FEED_SNAPSHOT_VERSION);
    session.setItem(FEED_SNAPSHOT_KEY, legacy);
    win.__blDiscoverDocumentSeen = true; // a client-side Back
    const page = await mount();
    expect(cardsOf(page)).toEqual(ids(0, 40));
    expect(calls[0].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    const moved = list(20);
    moved[2] = card(2, 0.9);
    await answer(calls[0], reply(moved, 0, { boundary: 3 }));
    expect(cardsOf(page)).toEqual(ids(0, 40));
    expect(textOf(page, "c2")).toBe("c2:0.9");
    expect(headings(page)).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Root review of 01edbca29c — copied verbatim from ROOT-PAGE-RETURN-REPRO.test.tsx
// (all three FAILED, EXIT 1, on 01edbca29c).

describe("Root independent page return cases", () => {
  it("a new mount without a snapshot accepts its fresh response despite the old cold SWR reply", async () => {
    const cache = new Map<unknown, unknown>();
    let page = await mount(cache);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    expect(cardsOf(page)).toEqual(ids(0,20));
    await unmount();
    session.clear();
    local.clear();
    const before = calls.length;
    page = await mount(cache);
    expect(calls.length).toBe(before + 1);
    await answer(lastCall(), reply(list(40,200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(cardsOf(page)).toEqual(ids(200,220));
  });
  it("Back retains the edition token for an enabled full opening without a continuation boundary", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mount(cache);
    await answer(calls[0], reply(list(40), 0, { edition: "FULL" }));
    expect(cardsOf(page)).toEqual(ids(0,20));
    await unmount();
    const before = calls.length;
    await mount(cache);
    expect(calls.length).toBe(before + 1);
    expect(lastCall().params.edition).toBe("FULL");
  });
});

it("Root late old transport failure cannot freeze an accepted replacement", async () => {
  const page = await mount();
  await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
  await fireSentinel();
  const oldTail = lastCall();
  await revalidate();
  await answer(lastCall(), reply(list(40,200), 0, { boundary: 3, edition: "NEW", status: "expired" }));
  expect(cardsOf(page)).toEqual(ids(200,220));
  (oldTail as Call & { done?: boolean }).done = true;
  await act(async () => { oldTail.reject(new Error("old request timed out")); });
  await settle();
  expect(has(page,"data-unavailable")).toBe(false);
});

// ─────────────────────────────────────────────────────────────────────────────

async function reject(call: Call, error = new Error("network")) {
  (call as Call & { done?: boolean }).done = true;
  await act(async () => { call.reject(error); });
  await settle();
}

// The app keeps ONE SWR cache and its request bookkeeping across a client-side
// navigation; only the page unmounts. `mount()` above remounts the provider
// too, which makes SWR drop that bookkeeping, so these tests navigate inside
// one provider instead.
let showPage: ((on: boolean) => void) | null = null;
function Navigator() {
  const [on, setOn] = React.useState(true);
  showPage = setOn;
  return on ? <DiscoverPage /> : null;
}
async function mountApp(cache: Map<unknown, unknown>) {
  const container = (document as unknown as { createElement: (t: string) => unknown }).createElement("div");
  (document as unknown as { body: { appendChild: (n: unknown) => void } }).body.appendChild(container);
  root = createRoot(container as Element);
  await act(async () => {
    root!.render(
      <SWRConfig value={{ provider: () => cache as never, dedupingInterval: 0 }}>
        <CaptureMutate />
        <Navigator />
      </SWRConfig>,
    );
  });
  await settle();
  return container as unknown as Node;
}
async function leavePage() {
  await act(async () => { showPage!(false); });
  await settle();
}
async function returnToPage() {
  await act(async () => { showPage!(true); });
  await settle();
}
/** No Back snapshot or scroll mark; the first-deck preview is left alone. */
function dropBackSnapshot() {
  session.removeItem(FEED_SNAPSHOT_KEY);
  session.removeItem(FEED_SCROLL_KEY);
}

describe("#5105 option ON — a request belongs to the mount that issued it", () => {
  it("a return with no snapshot takes its own reply over the earlier mount's cached one (one provider, as in the app)", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    await leavePage();
    session.clear();
    local.clear();
    const before = calls.length;
    await returnToPage();
    expect(calls.length).toBe(before + 1);
    expect(cardsOf(page)).toEqual([]);
    // The refused cached reply is not an answer: loading, not an empty end card.
    expect(has(page, "data-skeleton")).toBe(true);
    expect(has(page, "data-end-of-feed")).toBe(false);
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    expect(has(page, "data-skeleton")).toBe(false);
    await settle(10);
    expect(calls.length).toBe(before + 1);
  });

  it("if that return's own request fails, the reader gets the failed-load retry — not a blank page", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    await leavePage();
    session.clear();
    local.clear();
    await returnToPage();
    await reject(lastCall());
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-skeleton")).toBe(false);
    expect(walk(page).some((n) => n["data-unavailable"] === "empty")).toBe(true);
  });

  it("an own reply the edition refuses ends the wait on the retry state (no endless skeleton, no false end card)", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    await leavePage();
    session.clear();
    local.clear();
    await returnToPage();
    // Unrequested status on an unpinned request: refused, nothing adopted.
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "X", status: "pinned" }));
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-skeleton")).toBe(false);
    // A refused reply is not an empty edition: nothing was accepted, so the
    // reader is offered Retry, never told they are caught up.
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(walk(page).some((n) => n["data-unavailable"] === "empty")).toBe(true);
  });

  it("a fast return inside SWR's dedupe window refuses the earlier mount's in-flight reply and asks once for its own", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    expect(calls).toHaveLength(1);
    await leavePage();
    session.clear();
    local.clear();
    await returnToPage();
    // SWR shares the earlier mount's in-flight request and skips its own.
    expect(calls).toHaveLength(1);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    expect(cardsOf(page)).toEqual([]);
    // ...so this mount asks once, unpinned (it holds no deck), and only once.
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(calls[1], reply(list(40, 200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    await settle(10);
    expect(calls).toHaveLength(2);
  });

  it("the first-deck preview still paints, and this mount's own reply replaces it — not the cached one", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    await leavePage();
    dropBackSnapshot();
    const before = calls.length;
    await returnToPage();
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(calls.length).toBe(before + 1);
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    expect(calls.length).toBe(before + 1);
  });
});

describe("#5105 option ON — a first opening the edition refuses offers Retry, never \"caught up\"", () => {
  /** Nonempty, sectioned, and missing the token that binds the section. */
  const untokenedOpening = (from = 0) => reply(list(40, from), 0, { boundary: 3, edition: null });
  const showsRetry = (page: Node) => walk(page).some((n) => n["data-unavailable"] === "empty");

  it("a cold page whose own first reply is refused shows the retry state, not the empty end card", async () => {
    const page = await mount();
    expect(calls).toHaveLength(1);
    await answer(calls[0], untokenedOpening());
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-skeleton")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(showsRetry(page)).toBe(true);
    // Raising the notice asks nothing by itself: no retry loop.
    await settle(10);
    expect(calls).toHaveLength(1);
  });

  it("Retry is one unpinned page zero; a supported reply clears the notice and paints the opening", async () => {
    const page = await mount();
    await answer(calls[0], untokenedOpening());
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(calls[1], reply(list(40, 200), 0, { boundary: 3, edition: "E2" }));
    expect(has(page, "data-unavailable")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(sequence(page)).toEqual(["c200", "c201", "c202", "H", ...ids(203, 220)]);
    await settle(10);
    expect(calls).toHaveLength(2);
  });

  it("a Retry the edition refuses again comes back to Retry, once, and still never ends the feed", async () => {
    const page = await mount();
    await answer(calls[0], untokenedOpening());
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    await answer(calls[1], untokenedOpening(200));
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(showsRetry(page)).toBe(true);
    await settle(10);
    expect(calls).toHaveLength(2);
  });

  it("control: a valid, complete, empty first reply is still the genuine end of the feed", async () => {
    const page = await mount();
    await answer(calls[0], reply([], 0, { edition: null }));
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(true);
  });

  it("control: a typed-unavailable first reply keeps its existing retry state", async () => {
    const page = await mount();
    await answer(calls[0], UNAVAILABLE);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(showsRetry(page)).toBe(true);
  });

  it("control: a refused reply to a cold request another page zero has overtaken is inert", async () => {
    const page = await mount();
    await answer(calls[0], untokenedOpening());
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    const overtaken = calls[1];
    // A background revalidation lands first and opens the edition.
    await revalidate();
    expect(calls).toHaveLength(3);
    await answer(calls[2], reply(list(40, 200), 0, { boundary: 3, edition: "E2" }));
    expect(sequence(page)).toEqual(["c200", "c201", "c202", "H", ...ids(203, 220)]);
    await answer(overtaken, untokenedOpening(400));
    expect(has(page, "data-unavailable")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(sequence(page)).toEqual(["c200", "c201", "c202", "H", ...ids(203, 220)]);
  });

  it("control: an earlier mount's refused reply is not this mount's answer — it waits for its own", async () => {
    const cache = new Map<unknown, unknown>();
    const page = await mountApp(cache);
    expect(calls).toHaveLength(1);
    await leavePage();
    session.clear();
    local.clear();
    await returnToPage();
    expect(calls).toHaveLength(1);
    await answer(calls[0], untokenedOpening());
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(has(page, "data-skeleton")).toBe(true);
    expect(calls).toHaveLength(2);
    await answer(calls[1], reply(list(40, 200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
  });

  it("control: an accepted deck keeps today's quiet refusal of a later unsupported page zero", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(40), 0, { boundary: 3 }));
    await revalidate();
    // Pinned request, reply without its status: refused, the held deck stays.
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3 }));
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);
    expect(has(page, "data-unavailable")).toBe(false);
  });
});

describe("#5105 option ON — a refused reply over the saved first-deck preview keeps the cards and offers Retry", () => {
  /** Nonempty, sectioned, and missing the token that binds the section. */
  const untokenedOpening = (from = 0) => reply(list(40, from), 0, { boundary: 3, edition: null });
  const showsInlineRetry = (page: Node) => walk(page).some((n) => n["data-unavailable"] === "inline");
  const UPDATING = "Updating saved cards…";
  const UNAVAILABLE_LINE = "Saved cards · updates unavailable";
  /** Back to Discover with no Back snapshot: the saved first deck paints while this mount's own page zero is asked. */
  async function returnWithPreview() {
    const page = await mountApp(new Map<unknown, unknown>());
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    await leavePage();
    dropBackSnapshot();
    await returnToPage();
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(page.textContent).toContain(UPDATING);
    return page;
  }

  it("a refused own reply keeps the saved cards, ends the updating line on inline Retry, and asks nothing by itself", async () => {
    const page = await returnWithPreview();
    const issued = calls.length;
    await answer(lastCall(), untokenedOpening(200));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(showsInlineRetry(page)).toBe(true);
    expect(page.textContent).toContain(UNAVAILABLE_LINE);
    expect(page.textContent).not.toContain(UPDATING);
    expect(has(page, "data-end-of-feed")).toBe(false);
    await settle(10);
    expect(calls.length).toBe(issued);
  });

  it("Retry is one unpinned page zero; a supported reply replaces the preview and clears the notice and its line", async () => {
    const page = await returnWithPreview();
    await answer(lastCall(), untokenedOpening(200));
    const issued = calls.length;
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls.length).toBe(issued + 1);
    // The preview is not an accepted edition: nothing to pin to.
    expect(lastCall().params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "CURRENT" }));
    expect(sequence(page)).toEqual(["c200", "c201", "c202", "H", ...ids(203, 220)]);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(page.textContent).not.toContain(UNAVAILABLE_LINE);
    expect(page.textContent).not.toContain(UPDATING);
    expect(has(page, "data-end-of-feed")).toBe(false);
    await settle(10);
    expect(calls.length).toBe(issued + 1);
  });

  it("a Retry refused again keeps the saved cards and comes back to Retry, one request per press", async () => {
    const page = await returnWithPreview();
    await answer(lastCall(), untokenedOpening(200));
    const issued = calls.length;
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls.length).toBe(issued + 1);
    await answer(lastCall(), UNAVAILABLE);
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(showsInlineRetry(page)).toBe(true);
    expect(page.textContent).toContain(UNAVAILABLE_LINE);
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls.length).toBe(issued + 2);
    expect(lastCall().params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(lastCall(), untokenedOpening(400));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(showsInlineRetry(page)).toBe(true);
    expect(page.textContent).not.toContain(UPDATING);
    expect(has(page, "data-end-of-feed")).toBe(false);
    await settle(10);
    expect(calls.length).toBe(issued + 2);
  });

  it("control: a refused reply to a Retry that another page zero has overtaken is inert", async () => {
    const page = await returnWithPreview();
    await answer(lastCall(), untokenedOpening(200));
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    const overtaken = lastCall();
    await revalidate();
    const current = lastCall();
    expect(current).not.toBe(overtaken);
    await answer(current, reply(list(40, 600), 0, { boundary: 3, edition: "CURRENT" }));
    expect(sequence(page)).toEqual(["c600", "c601", "c602", "H", ...ids(603, 620)]);
    await answer(overtaken, untokenedOpening(400));
    expect(sequence(page)).toEqual(["c600", "c601", "c602", "H", ...ids(603, 620)]);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(has(page, "data-end-of-feed")).toBe(false);
  });

  it("control: an earlier mount's refused reply is not this mount's answer — the preview keeps updating and Retry stays away", async () => {
    const page = await mountApp(new Map<unknown, unknown>());
    await answer(calls[0], reply(list(40), 0, { boundary: 3, edition: "OLD" }));
    await revalidate();
    const earlier = lastCall();
    expect(earlier.params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "OLD" });
    await leavePage();
    dropBackSnapshot();
    await returnToPage();
    expect(cardsOf(page)).toEqual(ids(0, 20));
    await answer(earlier, untokenedOpening(200));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(has(page, "data-unavailable")).toBe(false);
    expect(page.textContent).toContain(UPDATING);
    const own = lastCall();
    expect(own).not.toBe(earlier);
    expect(own.params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(own, reply(list(40, 600), 0, { boundary: 3, edition: "CURRENT" }));
    expect(sequence(page)).toEqual(["c600", "c601", "c602", "H", ...ids(603, 620)]);
    expect(page.textContent).not.toContain(UPDATING);
  });
});

describe("#5105 option ON — a tokened opening with no continuation keeps its edition through Back", () => {
  it("stores the token and raw cursor, restores flat, and pins the revalidation and the next page", async () => {
    const cache = new Map<unknown, unknown>();
    const deck = list(40);
    let page = await mount(cache);
    await answer(calls[0], reply(deck, 0, { edition: "FULL" }));
    const stored = storedSnapshot();
    expect(stored.v).toBe(FEED_EDITION_SNAPSHOT_VERSION);
    expect(stored.cursor).toBe(20);
    expect(stored.hasMore).toBe(true);
    expect(stored.sections.boundary).toBeNull();
    await unmount();

    page = await mount(cache);
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(headings(page)).toBe(0);
    expect(lastCall().params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "FULL" });
    await answer(lastCall(), reply(deck, 0, { edition: "FULL", status: "pinned" }));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "FULL" });
    await answer(lastCall(), reply(deck, 20, { edition: "FULL", status: "pinned" }));
    expect(sequence(page)).toEqual(ids(0, 40));
  });

  it("an exhausted 160-card deck restored through the 120 cap still reaches the omitted 40, with its token", async () => {
    const cache = new Map<unknown, unknown>();
    const deck = list(160);
    const first = await mount(cache);
    await answer(calls[0], reply(deck, 0, {}));
    for (let p = 1; p < 8; p += 1) {
      await fireSentinel();
      await answer(lastCall(), reply(deck, p * 20, { status: "pinned" }));
    }
    expect(cardsOf(first)).toHaveLength(160);
    const stored = storedSnapshot();
    expect(stored.v).toBe(FEED_EDITION_SNAPSHOT_VERSION);
    expect(stored.cursor).toBe(120);
    expect(stored.hasMore).toBe(true);
    await unmount();

    const page = await mount(cache);
    expect(cardsOf(page)).toHaveLength(120);
    await answer(lastCall(), reply(deck, 0, { status: "pinned" }));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 120, event_pct: 0.15, edition: "E1" });
    await answer(lastCall(), reply(deck, 120, { status: "pinned" }));
    await fireSentinel();
    await answer(lastCall(), reply(deck, 140, { status: "pinned" }));
    expect(sequence(page)).toEqual(ids(0, 160));
    expect(headings(page)).toBe(0);
  });

  it("OFF, the same tokened opening still writes today's v2 bytes", async () => {
    mockOptionOn = false;
    await mount();
    await answer(calls[0], reply(list(40), 0, { edition: "FULL" }));
    const stored = storedSnapshot();
    expect(stored.v).toBe(FEED_SNAPSHOT_VERSION);
    expect("sections" in stored || "cursor" in stored).toBe(false);
  });
});

describe("#5105 option ON — a failure is inert once its request is no longer current", () => {
  it("a late failed replacement cannot freeze the page zero that replaced its deck", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(40), 0, { boundary: 3 }));
    await fireSentinel();
    await answer(calls[1], reply(list(40, 500), 20, { edition: "E9", status: "expired" }));
    const replacement = calls[2];
    expect(replacement.params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await revalidate();
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "NEW", status: "expired" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    await reject(replacement);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(cardsOf(page)).toEqual(ids(200, 220));
  });

  it("a late failed manual refresh cannot freeze the page zero that replaced its deck", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(20), 0, { boundary: 3 }));
    expect(endOfFeed.onRefresh).toBeDefined();
    await act(async () => { endOfFeed.onRefresh!(); });
    await settle();
    const refresh = lastCall();
    expect(refresh.params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await revalidate();
    await answer(lastCall(), reply(list(40, 200), 0, { boundary: 3, edition: "NEW", status: "expired" }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    await reject(refresh);
    expect(has(page, "data-unavailable")).toBe(false);
    expect(cardsOf(page)).toEqual(ids(200, 220));
  });

  it("a CURRENT failed page still raises the retry and keeps every card; the retry holds the frontier until it resolves", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(60), 0, { boundary: 3 }));
    await fireSentinel();
    await reject(calls[1]);
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 20)]);

    // An unavailable retry: one page zero, the notice comes back, no page beside it.
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls).toHaveLength(3);
    expect(calls[2].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" });
    await answer(calls[2], UNAVAILABLE);
    await settle(10);
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    expect(calls).toHaveLength(3);

    // A pinned retry: only after it resolves does the pager resume the window
    // the reader had already asked for — once.
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    expect(calls).toHaveLength(4);
    expect(calls[3].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" });
    await answer(calls[3], reply(list(60), 0, { boundary: 3, status: "pinned" }));
    expect(calls).toHaveLength(5);
    expect(calls[4].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E1" });
    await answer(calls[4], reply(list(60), 20, { boundary: 3, status: "pinned" }));
    expect(has(page, "data-unavailable")).toBe(false);
    expect(sequence(page)).toEqual(["c0", "c1", "c2", "H", ...ids(3, 40)]);
  });
});

describe("#5105 option ON — an accepted reply refreshes the bodies already on screen", () => {
  it("an overlapping page of a tokened opening updates the held card, not only the deck", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(40), 0, {}));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E1" });
    await answer(lastCall(), {
      items: [card(19, 0.91), ...list(19, 20)],
      offset: 20,
      total: 40,
      has_more: true,
      edition: "E1",
      edition_status: "pinned",
    });
    expect(textOf(page, "c19")).toBe("c19:0.91");
    expect(cardsOf(page)).toEqual(ids(0, 39));
  });

  it("a repeated window of a restored section deck updates the tail cards it re-sends", async () => {
    const all = list(60);
    const pageId = (item: Card) => `event-${item.data.id}`;
    let deck: Sections<Card> | null = null;
    for (const offset of [0, 20]) {
      const folded = foldContinuationPage(deck, { items: all.slice(offset, offset + 20), offset, total: 60, edition: "E1", continuation_start: 3 }, pageId);
      if (folded.status !== "ok") throw new Error(folded.reason);
      deck = folded.sections;
    }
    // c30 was received but not kept, so the stored cursor moves back to 30 and
    // the next page re-sends c31..c39, which ARE on screen.
    const kept = all.slice(0, 40).filter((c) => c.data.id !== 30);
    const raw = serializeFeedSnapshot({ page1: kept.slice(0, 20), rest: kept.slice(20), visibleCount: 39, hasMore: true }, { deck: deck!, cursor: 40, getId: pageId })!;
    expect(JSON.parse(raw).cursor).toBe(30);
    session.setItem(FEED_SNAPSHOT_KEY, raw);
    win.__blDiscoverDocumentSeen = true; // a client-side Back
    const page = await mount();
    expect(textOf(page, "c35")).toBe("c35:0.5");
    await answer(lastCall(), reply(all, 0, { boundary: 3, status: "pinned" }));
    await fireSentinel();
    expect(lastCall().params).toEqual({ limit: 20, offset: 30, event_pct: 0.15, edition: "E1" });
    const repriced = list(60, 0, 0.66);
    await answer(lastCall(), reply(repriced, 30, { boundary: 3, status: "pinned" }));
    expect(textOf(page, "c35")).toBe("c35:0.66");
    expect(textOf(page, "c39")).toBe("c39:0.66");
    expect(textOf(page, "c30")).toBe("c30:0.66");
  });
});
