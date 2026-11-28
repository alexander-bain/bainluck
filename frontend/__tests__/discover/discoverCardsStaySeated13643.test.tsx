/**
 * #13643 — "Discover on the web rearranges its cards while you are reading it"
 *
 * Proves that once an opening edition is seated on Discover web:
 * 1. Background 120s revalidation ticks (including retired `invalidated` /
 *    `expired` / `superseded` replies whose server order changed completely)
 *    NEVER move, add, or drop rendered cards;
 * 2. Fresh prices/numbers on held cards STILL land in place;
 * 3. When newer cards exist, `"New cards available"` appears at the top and
 *    replaces the deck ONLY when clicked;
 * 4. Hitting a retired edition while scrolling down (`offset > 0`) OR after a
 *    120s retired background tick holds seated cards AND keeps paging into
 *    the newer edition strictly below held seats (zero bottom refresh wall);
 * 5. A failed retired-tail read surfaces retry without moving held cards or
 *    scrolling back to the top;
 * 6. A held card whose fresh copy is old or empty keeps its prior body and
 *    shows the "From earlier · no longer updating" mark (`discover-card-aged-mark`);
 * 7. `useSWR` disables reconnect revalidation (`revalidateOnReconnect: false`).
 */

import "../helpers/minimalDom";
import * as fs from "fs";
import * as path from "path";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig, useSWRConfig } from "swr";
import { appendUnseenCards, hasNewerDeckCards, reconcileHeldBodies, refreshHeldBodiesInPlace } from "@/lib/discover/editionOrder";

let mockOptionOn = true;
jest.mock("@/lib/launchSurfaces", () => ({
  get CHALLENGE_SURFACES_ENABLED() {
    return false;
  },
}));
jest.mock("@/lib/discover/openingEditionOption", () => ({
  get DISCOVER_OPENING_EDITION_ENABLED() {
    return mockOptionOn;
  },
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: (props: React.ComponentProps<"a">) => <a {...props} />,
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
jest.mock("@/components/DiscoverCard", () => {
  const card = ({
    groupedItem,
    positionIndex,
  }: {
    groupedItem: { item: { data: { id: number; prob: number } } };
    positionIndex: number;
  }) => (
    <div data-card={`c${groupedItem.item.data.id}`} data-position={positionIndex}>
      {`c${groupedItem.item.data.id}:${groupedItem.item.data.prob}`}
    </div>
  );
  return {
    __esModule: true,
    default: card,
    GuessCard: () => null,
    DailyChallengeCard: () => null,
    ResolutionCard: () => null,
    ResolutionGroup: () => null,
  };
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
jest.mock("@/components/discover/EndOfFeedCard", () => ({
  __esModule: true,
  default: ({ count }: { count: number }) => <div data-end-of-feed={count} />,
}));
const unavailableState: { onRetry?: () => void } = {};
jest.mock("@/components/discover/FeedUnavailableNotice", () => ({
  __esModule: true,
  default: ({ variant, onRetry }: { variant: string; onRetry?: () => void }) => {
    unavailableState.onRetry = onRetry;
    return <div data-unavailable={variant} />;
  },
}));
jest.mock("@/components/discover/FeedBootScript", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/FirstRunOrientation", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/SignInToPersonalizeInvite", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/discover/DiscoverSkeletonGrid", () => ({ __esModule: true, default: () => <div data-skeleton="1" /> }));

import DiscoverPage from "@/app/discover/page";
import { fetchFeed } from "@/lib/api";

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
const scrollToCalls: Array<Record<string, unknown>> = [];
Object.assign(win, {
  localStorage: local,
  sessionStorage: session,
  scrollY: 0,
  innerHeight: 844,
  scrollTo: (opts: Record<string, unknown>) => { scrollToCalls.push(opts); },
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

type Card = {
  type: "event";
  data: {
    id: number;
    sport: string;
    prob: number;
    status: string;
    current_odds: { home_probability: number };
    away_team: string;
    home_team: string;
  };
  score: number;
};
const card = (id: number, prob = 0.5, status = "live"): Card => ({
  type: "event",
  data: {
    id,
    sport: "politics",
    prob,
    status,
    away_team: `Away ${id}`,
    home_team: `Home ${id}`,
    current_odds: { home_probability: prob },
  },
  score: 1000 - id,
});
const list = (n: number, from = 0, prob = 0.5) => Array.from({ length: n }, (_, i) => card(from + i, prob));

function reply(items: unknown[], offset: number, opts: { edition?: string; boundary?: number; status?: string; total?: number; hasMore?: boolean } = {}) {
  const total = opts.total ?? 60;
  return {
    items,
    offset,
    total,
    has_more: opts.hasMore ?? offset + items.length < total,
    edition: opts.edition ?? "E1",
    ...(opts.boundary !== undefined ? { continuation_start: opts.boundary } : {}),
    ...(opts.status ? { edition_status: opts.status } : {}),
  };
}

type Call = { params: Record<string, unknown>; resolve: (v: unknown) => void; reject: (e: unknown) => void };
const calls: Call[] = [];
(fetchFeed as jest.Mock).mockImplementation((params: Record<string, unknown>) =>
  new Promise((resolve, reject) => { calls.push({ params, resolve, reject }); }),
);

async function settle(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }
}
async function answer(call: Call, value: unknown) {
  await act(async () => { call.resolve(value); });
  await settle();
}

let root: Root | null = null;
let swrMutate: ((key: unknown) => Promise<unknown>) | null = null;
function CaptureMutate() {
  swrMutate = useSWRConfig().mutate as unknown as (key: unknown) => Promise<unknown>;
  return null;
}
type Node = { childNodes: Node[]; nodeType: number; tagName?: string; textContent: string; [k: string]: unknown };
function walk(node: Node, out: Node[] = []): Node[] {
  out.push(node);
  for (const child of node.childNodes ?? []) walk(child, out);
  return out;
}
function attached(node: unknown): boolean {
  let at = node as { parentNode?: unknown } | null | undefined;
  while (at) {
    if (at === (document as unknown as { body: unknown }).body) return true;
    at = at.parentNode as typeof at;
  }
  return false;
}
function reactProps(node: Node): { onClick?: () => void } {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"));
  return key ? (node[key] as { onClick?: () => void }) : {};
}
const findByTestId = (container: Node, id: string) => walk(container).find((n) => n["data-testid"] === id);
const findAllByTestId = (container: Node, id: string) => walk(container).filter((n) => n["data-testid"] === id);
const cardsOf = (container: Node) => walk(container).flatMap((n) => (typeof n["data-card"] === "string" ? [n["data-card"] as string] : []));
const textOf = (container: Node, id: string) => walk(container).find((n) => n["data-card"] === id)?.textContent;
const ids = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => `c${from + i}`);

async function mount() {
  const container = (document as unknown as { createElement: (t: string) => unknown }).createElement("div");
  (document as unknown as { body: { appendChild: (n: unknown) => void } }).body.appendChild(container);
  root = createRoot(container as Element);
  await act(async () => {
    root!.render(
      <SWRConfig value={{ provider: () => new Map() as never, dedupingInterval: 0 }}>
        <CaptureMutate />
        <DiscoverPage />
      </SWRConfig>,
    );
  });
  await settle();
  return container as unknown as Node;
}
async function revalidate() {
  await act(async () => { void swrMutate!(["discover-feed", "anonymous"]); });
  await settle();
}
async function fireSentinel() {
  const sentinel = observers.filter((o) => o.active && o.options?.rootMargin === "400px" && attached(o.node)).at(-1);
  if (!sentinel) throw new Error("no observed sentinel is in the document");
  await act(async () => { sentinel.cb([{ isIntersecting: true }]); });
  await act(async () => { sentinel.cb([{ isIntersecting: false }]); });
  await settle();
}

beforeEach(() => {
  mockOptionOn = true;
  calls.length = 0;
  observers.length = 0;
  scrollToCalls.length = 0;
  unavailableState.onRetry = undefined;
  local.clear();
  session.clear();
});
afterEach(async () => {
  const current = root;
  root = null;
  await act(async () => { current?.unmount(); });
});

describe("#13643 — pure seat-preservation helpers", () => {
  it("refreshHeldBodiesInPlace updates matching cards in place and never adds, drops, or reorders", () => {
    const a1 = card(1, 0.5);
    const b1 = card(2, 0.4);
    const c1 = card(3, 0.6);
    const prev = [a1, b1, c1];

    const a2 = card(1, 0.72);
    const staleB = card(2, 0.99, "closed");
    const extra = card(99, 0.3);
    const out = refreshHeldBodiesInPlace(
      prev,
      [extra, a2, staleB],
      (item) => `event-${item.data.id}`,
      (item) => item.data.status !== "closed",
    );

    expect(out.map((x) => x.data.id)).toEqual([1, 2, 3]);
    expect(out[0]).toBe(a2);
    expect(out[1]).toBe(b1);
    expect(out[2]).toBe(c1);
  });

  it("hasNewerDeckCards detects reorders and new arrivals without mutating anything", () => {
    const base = [card(1), card(2), card(3)];
    expect(hasNewerDeckCards(base, [card(1), card(2), card(3)], (x) => String(x.data.id))).toBe(false);
    expect(hasNewerDeckCards(base, [card(2), card(1), card(3)], (x) => String(x.data.id))).toBe(true);
    expect(hasNewerDeckCards(base, [card(99), card(1), card(2)], (x) => String(x.data.id))).toBe(true);
  });

  it("reconcileHeldBodies tracks refreshed and rejected ids and appendUnseenCards appends only unseen tail", () => {
    const prev = [card(1, 0.5), card(2, 0.4)];
    const r = reconcileHeldBodies(
      prev,
      [card(1, 0.7), card(2, 0.99, "closed"), card(99, 0.3)],
      (x) => String(x.data.id),
      (x) => x.data.status !== "closed",
    );
    expect(r.items[0].data.prob).toBe(0.7);
    expect(r.items[1]).toBe(prev[1]);
    expect(r.refreshedIds).toEqual(["1"]);
    expect(r.rejectedIds).toEqual(["2"]);

    const appended = appendUnseenCards(r.items, [card(2, 0.4), card(99, 0.3), card(100, 0.2)], (x) => String(x.data.id));
    expect(appended.appended.map((x) => x.data.id)).toEqual([99, 100]);
    expect(appended.next.map((x) => x.data.id)).toEqual([1, 2, 99, 100]);
  });
});

describe("#13643 — Discover on web never rearranges seated cards while open", () => {
  it("holds the first twenty cards across retired background ticks, applies in-place prices, and refreshes only when clicked", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(20, 0, 0.5), 0, { edition: "E1", boundary: 3 }));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(findByTestId(page, "discover-new-cards-button")).toBeUndefined();

    // First background tick: server retires E1 with a reordered + newcomers list,
    // including an updated price for already-seated card c1 (0.5 -> 0.73).
    await revalidate();
    expect(calls[1].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15, edition: "E1" });
    const retiredTick = [...list(19, 100, 0.4), card(1, 0.73)].reverse();
    await answer(calls[1], reply(retiredTick, 0, { edition: "E2", boundary: 0, status: "invalidated" }));

    // Every single one of the first 20 seated cards stays in exact same order,
    // while c1 receives its updated 0.73 number in place.
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(textOf(page, "c1")).toBe("c1:0.73");
    const pill = findByTestId(page, "discover-new-cards-button");
    expect(pill).toBeDefined();

    // Second background tick: still no reorder, no duplicate uninvited page-0 restart.
    await revalidate();
    await answer(calls[2], reply(list(20, 200, 0.2), 0, { edition: "E3", boundary: 2, status: "expired" }));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(calls).toHaveLength(3);

    // Only clicking "New cards available" asks unpinned page 0, scrolls to top, and swaps order.
    await act(async () => { reactProps(findByTestId(page, "discover-new-cards-button")!).onClick!(); });
    await settle();
    expect(scrollToCalls.length).toBeGreaterThanOrEqual(1);
    expect(calls).toHaveLength(4);
    expect(calls[3].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(calls[3], reply(list(20, 200, 0.2), 0, { edition: "E3", boundary: 2 }));
    expect(cardsOf(page)).toEqual(ids(200, 220));
    expect(findByTestId(page, "discover-new-cards-button")).toBeUndefined();
  });

  it("keeps paging below held cards after a 120s retired background tick without moving held seats", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(20, 0, 0.5), 0, { edition: "E1", boundary: 3, total: 60 }));
    expect(cardsOf(page)).toEqual(ids(0, 20));

    // At 120s, E1 is retired and E2's page 0 introduces unseen cards 100..118 plus held c1.
    await revalidate();
    const retiredPage0 = [card(1, 0.66), ...list(19, 100, 0.4)];
    await answer(calls[1], reply(retiredPage0, 0, { edition: "E2", boundary: 0, status: "invalidated", total: 60 }));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(textOf(page, "c1")).toBe("c1:0.66");
    expect(findByTestId(page, "discover-new-cards-button")).toBeDefined();

    // Reader scrolls down past card 20: E2's unseen page-0 cards flush strictly BELOW held seats,
    // without dropping E1 seats or emitting any bottom refresh blocker.
    await fireSentinel();
    expect(cardsOf(page)).toEqual([...ids(0, 20), ...ids(100, 119)]);
    expect(findByTestId(page, "discover-retired-refresh-button")).toBeUndefined();

    // Lookahead/scroll continues fetching E2's offset=20 and offset=40 pinned to E2 until exhausted.
    expect(calls).toHaveLength(3);
    expect(calls[2].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E2" });
    await answer(calls[2], reply(list(20, 120, 0.3), 20, { edition: "E2", status: "pinned", total: 60 }));
    await fireSentinel();
    expect(cardsOf(page)).toEqual([...ids(0, 20), ...ids(100, 119), ...ids(120, 140)]);
    expect(calls).toHaveLength(4);
    expect(calls[3].params).toEqual({ limit: 20, offset: 40, event_pct: 0.15, edition: "E2" });
    await answer(calls[3], reply(list(20, 140, 0.3), 40, { edition: "E2", status: "pinned", total: 60 }));
    expect(cardsOf(page)).toEqual([...ids(0, 20), ...ids(100, 119), ...ids(120, 160)]);
    expect(walk(page).some((n) => n["data-end-of-feed"] !== undefined)).toBe(true);
  });

  it("keeps paging below held cards when scrolling hits a retired edition, and retries failed tail without moving seats", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(20, 0, 0.5), 0, { edition: "E1", boundary: 3, total: 60 }));

    await fireSentinel();
    expect(calls).toHaveLength(2);
    expect(calls[1].params).toEqual({ limit: 20, offset: 20, event_pct: 0.15, edition: "E1" });
    await answer(calls[1], reply(list(20, 500, 0.5), 20, { edition: "E9", status: "expired", total: 60 }));

    // Seated cards 0..19 stay untouched; unseen E9 cards append strictly below; lookahead continues at offset=40 with E9; no bottom wall.
    expect(cardsOf(page)).toEqual([...ids(0, 20), ...ids(500, 520)]);
    expect(findByTestId(page, "discover-new-cards-button")).toBeDefined();
    expect(findByTestId(page, "discover-retired-refresh-button")).toBeUndefined();
    expect(calls).toHaveLength(3);
    expect(calls[2].params).toEqual({ limit: 20, offset: 40, event_pct: 0.15, edition: "E9" });

    // A failed tail read raises inline retry (not end-of-feed), keeps every held card, and retry recovers WITHOUT scrolling to top.
    await act(async () => { calls[2].reject(new Error("network")); });
    await settle();
    expect(findByTestId(page, "discover-retired-refresh-button")).toBeUndefined();
    expect(walk(page).some((n) => n["data-unavailable"] === "inline")).toBe(true);
    expect(unavailableState.onRetry).toBeDefined();
    const scrollsBeforeRetry = scrollToCalls.length;
    await act(async () => { unavailableState.onRetry!(); });
    await settle();
    expect(scrollToCalls.length).toBe(scrollsBeforeRetry);
    expect(calls).toHaveLength(4);
    expect(calls[3].params).toEqual({ limit: 20, offset: 40, event_pct: 0.15, edition: "E9" });
    await answer(calls[3], reply(list(20, 520, 0.5), 40, { edition: "E9", status: "pinned", total: 60 }));
    await fireSentinel();
    expect(cardsOf(page)).toEqual([...ids(0, 20), ...ids(500, 540)]);

    // Clicking the top pill resets atomically to the fresh edition.
    await act(async () => { reactProps(findByTestId(page, "discover-new-cards-button")!).onClick!(); });
    await settle();
    expect(calls).toHaveLength(5);
    expect(calls[4].params).toEqual({ limit: 20, offset: 0, event_pct: 0.15 });
    await answer(calls[4], reply(list(20, 300, 0.6), 0, { edition: "E10", boundary: 1 }));
    expect(cardsOf(page)).toEqual(ids(300, 320));
    expect(findByTestId(page, "discover-new-cards-button")).toBeUndefined();
  });

  it("shows a quiet aged mark when a held card's fresh body is empty or old, and clears when updated", async () => {
    const page = await mount();
    await answer(calls[0], reply(list(20, 0, 0.5), 0, { edition: "E1", boundary: 3 }));
    expect(findAllByTestId(page, "discover-card-aged-mark")).toHaveLength(0);

    // Background reply carries an aged ("closed") replacement for c1. Seat & price stay, quiet mark appears.
    await revalidate();
    await answer(calls[1], reply([card(1, 0.99, "closed"), ...list(19, 100, 0.4)], 0, { edition: "E2", boundary: 0, status: "invalidated" }));
    expect(cardsOf(page)).toEqual(ids(0, 20));
    expect(textOf(page, "c1")).toBe("c1:0.5");
    const marks = findAllByTestId(page, "discover-card-aged-mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("From earlier · no longer updating");

    // Later fresh renderable reply for c1 replaces body in place and clears the mark.
    await revalidate();
    await answer(calls[2], reply([card(1, 0.81, "live"), ...list(19, 100, 0.4)], 0, { edition: "E3", boundary: 0, status: "expired" }));
    expect(textOf(page, "c1")).toBe("c1:0.81");
    expect(findAllByTestId(page, "discover-card-aged-mark")).toHaveLength(0);
  });

  it("disables SWR focus and reconnect revalidation on discover-feed", () => {
    const src = fs.readFileSync(path.join(__dirname, "../../app/discover/page.tsx"), "utf8");
    const idx = src.indexOf('["discover-feed", requestPrincipal]');
    const swrBlock = src.slice(idx, idx + 1400);
    expect(swrBlock).toContain("revalidateOnFocus: false");
    expect(swrBlock).toContain("revalidateOnReconnect: false");
  });
});
