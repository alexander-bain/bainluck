/**
 * #5105 — the web/server connection gate, page side.
 *
 * `discoverPageOpeningEdition5105.test.tsx` mounts the REAL Discover page but
 * answers it with payloads it writes itself; the backend route tests drive the
 * REAL `get_feed` but stop at its JSON. This file joins the two: every reply
 * here is a response `get_feed` actually produced, recorded with its raw body
 * by `backend/tests/integration/test_discover_web_transcript_5105.py` into
 * `__tests__/fixtures/discover5105ServerTranscript.json` (served switch ON,
 * fixed request clocks, dict Redis, mocked DB — regenerate it there, never by
 * hand).
 *
 * The page runs with the REAL `fetchFeed` and `apiFetch`; only `global.fetch`
 * is replaced. Each request the page puts on the wire must be byte-for-byte
 * the one the backend answered — path, query (offset, the issued edition
 * token) and session header — and is answered with exactly the recorded bytes
 * as a real `Response`. Nothing in an envelope is retyped: edition, offset,
 * `continuation_start`, `edition_status` and `cache` metadata are the server's.
 *
 * Replaced, as in the sibling harness: auth, analytics, the price stream, and
 * the leaf card components (which print the card's server identity). The
 * internal option is mocked ON (the local switch-on release candidate also ships
 * it ON).
 */
import "../helpers/minimalDom";
import * as fs from "fs";
import * as path from "path";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SWRConfig, useSWRConfig } from "swr";

jest.mock("@/lib/discover/openingEditionOption", () => ({ DISCOVER_OPENING_EDITION_ENABLED: true }));
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
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
  getDiscoverItemAnalytics: (item: { type: string; data: { id?: number; key?: string } }) => ({
    content_type: item.type,
    item_id: String(item?.data?.id ?? item?.data?.key),
    category: "other",
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
  // The synthetic server cards carry identities, not market bodies.
  feedItemHasRenderableContent: () => true,
  collectSuppressedEnvelopes: () => [],
  feedItemCanBeGuessed: () => false,
}));
jest.mock("@/components/DiscoverCard", () => {
  const card = ({ groupedItem, positionIndex }: { groupedItem: { item: { type: string; data: { id?: number; key?: string } } }; positionIndex: number }) => {
    const { type, data } = groupedItem.item;
    return <div data-card={`${type}:${data.id ?? data.key}`} data-position={positionIndex} />;
  };
  return { __esModule: true, default: card, GuessCard: () => null, DailyChallengeCard: () => null, ResolutionCard: () => null, ResolutionGroup: () => null };
});
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
import { API_URL } from "@/lib/api";
import { CONTINUATION_HEADING } from "@/components/discover/ContinuationSections";
import { FEED_EDITION_SNAPSHOT_VERSION, FEED_SNAPSHOT_KEY } from "@/lib/discover/feedRestore";

// ── the transcript ──────────────────────────────────────────────────────────

type Step = {
  label: string;
  clock: string;
  request: { url: string; session: string | null };
  status: number;
  headers: Record<string, string>;
  body: string;
};
const TRANSCRIPT_PATH = path.join(__dirname, "..", "fixtures", "discover5105ServerTranscript.json");
const transcript = JSON.parse(fs.readFileSync(TRANSCRIPT_PATH, "utf8")) as {
  generator: string;
  session: string;
  scenarios: Record<string, Step[]>;
};
const REPO = path.join(__dirname, "..", "..", "..");

/** The server's own envelope of a step, for reading what it ISSUED. */
const served = (step: Step) => JSON.parse(step.body) as { edition?: string; items: unknown[] };

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
Object.assign(win, { localStorage: local, sessionStorage: session, scrollY: 0, innerHeight: 844, scrollTo: () => {}, setTimeout, clearTimeout });
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

// minimalDom's `appendChild`/`insertBefore` do not detach a node from where it
// already sits, so a keyed React MOVE (a card that changes seat between two
// renders) leaves a stale copy at its old index. A browser moves the node; so
// does this page's DOM, for the elements it creates.
{
  type El = { parentNode?: { removeChild: (c: unknown) => unknown } | null; appendChild: (c: El) => El; insertBefore: (c: El, ref: unknown) => El };
  const d = document as unknown as { createElement: (t: string) => El };
  const create = d.createElement;
  d.createElement = (tag: string) => {
    const el = create(tag);
    const append = el.appendChild;
    const insert = el.insertBefore;
    el.appendChild = (c) => { c.parentNode?.removeChild(c); return append(c); };
    el.insertBefore = (c, ref) => { c.parentNode?.removeChild(c); return insert(c, ref); };
    return el;
  };
}

// ── the wire: the real fetchFeed's requests, held until a step answers ──────

type Wire = { url: string; session: string | null; resolve: (r: Response) => void; done: boolean };
const wire: Wire[] = [];
const offFeed: string[] = [];
const FEED_PREFIX = `${API_URL}/api/feed?`;
beforeAll(() => {
  // A fresh visitor's first request goes out session-less; the id the page
  // mints for every later one is the id the backend recorded.
  jest.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(transcript.session as `${string}-${string}-${string}-${string}-${string}`);
  global.fetch = jest.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (!url.startsWith(FEED_PREFIX)) {
      offFeed.push(url);
      return Promise.reject(new Error(`unexpected request ${url}`));
    }
    const headers = (init?.headers ?? {}) as Record<string, string>;
    return new Promise<Response>((resolve) => {
      wire.push({ url: url.slice(API_URL.length), session: headers["x-session-id"] ?? null, resolve, done: false });
    });
  }) as unknown as typeof fetch;
});
const open = () => wire.filter((w) => !w.done);

async function settle(rounds = 6) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
  }
}

/** The page's ONE outstanding request must be the step's request; it gets the
 *  step's recorded bytes. Returns what the page put on the wire. */
async function serve(step: Step) {
  const pending = open();
  expect(pending.map((w) => ({ url: w.url, session: w.session }))).toEqual([step.request]);
  const call = pending[0];
  call.done = true;
  await act(async () => {
    call.resolve(new Response(step.body, { status: step.status, headers: step.headers }));
  });
  await settle();
  return call;
}

// ── mounting the real page ──────────────────────────────────────────────────

let root: Root | null = null;
async function mount(cache: Map<unknown, unknown> = new Map()) {
  const container = (document as unknown as { createElement: (t: string) => unknown }).createElement("div");
  (document as unknown as { body: { appendChild: (n: unknown) => void } }).body.appendChild(container);
  root = createRoot(container as Element);
  await act(async () => {
    root!.render(
      <SWRConfig value={{ provider: () => cache as never, dedupingInterval: 0 }}>
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
function attached(node: unknown): boolean {
  let at = node as { parentNode?: unknown } | null | undefined;
  while (at) {
    if (at === (document as unknown as { body: unknown }).body) return true;
    at = at.parentNode as typeof at;
  }
  return false;
}
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
/** The page in document order: server identities, and `H` where the heading sits. */
function sequence(container: Node): string[] {
  return walk(container).flatMap((n) => {
    if (n.tagName === "H2" && n.textContent === CONTINUATION_HEADING) return ["H"];
    if (typeof n["data-card"] === "string") return [n["data-card"] as string];
    return [];
  });
}
const cardsOf = (c: Node) => sequence(c).filter((t) => t !== "H");
const positions = (c: Node) => walk(c).filter((n) => n["data-position"] !== undefined).map((n) => Number(n["data-position"]));
const peeks = (c: Node) => walk(c).filter((n) => n["data-class"] === "animate-peek-right").length;
const has = (c: Node, attr: string) => walk(c).some((n) => n[attr] !== undefined);
const notice = (c: Node) => walk(c).find((n) => n["data-unavailable"] !== undefined)?.["data-unavailable"];
const range = (n: number, from = 0) => Array.from({ length: n }, (_, i) => from + i);
const F = (...ids: number[]) => ids.map((i) => `futures:${i}`);
const E = (...ids: number[]) => ids.map((i) => `event:${i}`);
const unique = (list: string[]) => new Set(list).size === list.length;
const query = (w: Wire) => Object.fromEntries(new URLSearchParams(w.url.split("?")[1]));

beforeEach(() => {
  wire.length = 0;
  offFeed.length = 0;
  observers.length = 0;
  local.clear();
  session.clear();
  delete win.__blDiscoverDocumentSeen;
  unavailable.onRetry = undefined;
});
afterEach(async () => {
  await unmount();
  expect(open()).toEqual([]);
  expect(offFeed).toEqual([]);
});

// ─────────────────────────────────────────────────────────────────────────────

describe("#5105 transcript provenance", () => {
  it("names a generator that exists, and holds every sequence this file plays", () => {
    expect(fs.existsSync(path.join(REPO, transcript.generator))).toBe(true);
    expect(Object.keys(transcript.scenarios).sort()).toEqual([
      "boundary_zero", "empty_vs_refusal", "full_opening_back", "sparse_opening", "tournament_start", "unavailable_replacement",
    ]);
  });
});

describe("#5105 the real page consumes the real server's responses", () => {
  it("sparse opening 3 + live continuation: one heading, one first position, the issued token and raw cursor, one global window", async () => {
    const [p0, p1] = transcript.scenarios.sparse_opening;
    const page = await mount();
    await serve(p0);
    expect(sequence(page)).toEqual([...F(0, 1, 2), "H", ...E(...range(17, 1))]);
    expect(cardsOf(page)).toHaveLength(20);
    expect(peeks(page)).toBe(1);
    expect(positions(page)).toEqual(range(20));
    expect(has(page, "data-end-of-feed")).toBe(false);

    await fireSentinel();
    const asked = await serve(p1);
    expect(query(asked)).toEqual({ limit: "20", offset: "20", event_pct: "0.15", edition: served(p0).edition });
    expect(sequence(page)).toEqual([...F(0, 1, 2), "H", ...E(...range(30, 1))]);
    expect(positions(page)).toEqual(range(33));
    expect(peeks(page)).toBe(1);
    expect(has(page, "data-end-of-feed")).toBe(true);
    await settle(10);
    expect(open()).toEqual([]);
  });

  it("boundary 0 (no eligible opening): the heading leads, zero is not missing, one first position", async () => {
    const [p0, p1] = transcript.scenarios.boundary_zero;
    const page = await mount();
    await serve(p0);
    expect(sequence(page)).toEqual(["H", ...E(...range(20, 1))]);
    expect(peeks(page)).toBe(1);
    expect(positions(page)).toEqual(range(20));
    await fireSentinel();
    const asked = await serve(p1);
    expect(query(asked)).toEqual({ limit: "20", offset: "20", event_pct: "0.15", edition: served(p0).edition });
    expect(sequence(page)).toEqual(["H", ...E(...range(25, 1))]);
  });

  it("a tournament starts under the pin: the retired page 20 is never appended; one unpinned page zero replaces the deck with its newcomer", async () => {
    const [p0, retired, fresh, p1, lookahead] = transcript.scenarios.tournament_start;
    const before = ["futures:0", "tournament:t-open", ...F(...range(18, 1))];
    const replaced = F(0, 500, ...range(8, 1)).concat("tournament:t-open", F(...range(9, 9)));
    const page = await mount();
    await serve(p0);
    expect(sequence(page)).toEqual(before);

    await fireSentinel();
    const asked = await serve(retired);
    expect(query(asked)).toEqual({ limit: "20", offset: "20", event_pct: "0.15", edition: served(p0).edition });
    // Nothing of the retired edition's page 20 reached the screen.
    expect(sequence(page)).toEqual(before);

    const restart = await serve(fresh);
    expect(query(restart)).toEqual({ limit: "20", event_pct: "0.15" });
    expect(sequence(page)).toEqual(replaced);
    expect(peeks(page)).toBe(1);
    expect(positions(page)).toEqual(range(20));

    // The new edition's window and cursor: one advance, pinned to the token
    // the server issued with the replacement.
    await fireSentinel();
    const next = await serve(p1);
    expect(query(next)).toEqual({ limit: "20", offset: "20", event_pct: "0.15", edition: served(fresh).edition });
    expect(sequence(page)).toEqual([...replaced, ...F(...range(20, 18))]);
    expect(unique(cardsOf(page))).toBe(true);

    // The window reached what the page holds, so its existing look-ahead asks
    // for page 40 of the same edition. Held, not shown: one global window of 40.
    const ahead = await serve(lookahead);
    expect(query(ahead)).toEqual({ limit: "20", offset: "40", event_pct: "0.15", edition: served(fresh).edition });
    expect(sequence(page)).toEqual([...replaced, ...F(...range(20, 18))]);
    expect(positions(page)).toEqual(range(40));
    await fireSentinel();
    expect(sequence(page)).toEqual([...replaced, ...F(...range(26, 18))]);
    expect(unique(cardsOf(page))).toBe(true);
    expect(has(page, "data-end-of-feed")).toBe(true);
    await settle(10);
    expect(open()).toEqual([]);
  });

  it("the current deck is unsupported at replacement: the visible deck stays, Retry is actionable and recovers once, without duplicates", async () => {
    const [p0, retired, refused, retry] = transcript.scenarios.unavailable_replacement;
    const before = ["futures:0", "tournament:t-open", ...F(...range(18, 1))];
    const page = await mount();
    await serve(p0);
    await fireSentinel();
    await serve(retired);
    expect(sequence(page)).toEqual(before);

    await serve(refused);
    expect(sequence(page)).toEqual(before);
    expect(notice(page)).toBe("inline");
    expect(has(page, "data-end-of-feed")).toBe(false);
    await settle(10);
    expect(open()).toEqual([]);

    expect(unavailable.onRetry).toBeDefined();
    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    const asked = await serve(retry);
    expect(query(asked)).toEqual({ limit: "20", event_pct: "0.15", edition: served(p0).edition });
    expect(sequence(page)).toEqual(F(0, 500, ...range(8, 1)).concat("tournament:t-open", F(...range(9, 9))));
    expect(has(page, "data-unavailable")).toBe(false);
    expect(unique(cardsOf(page))).toBe(true);
    await settle(10);
    expect(open()).toEqual([]);
  });

  it("a full opening with no heading keeps its token through Back: the revalidation and the next page are pinned to it", async () => {
    const [p0, again, p1] = transcript.scenarios.full_opening_back;
    const cache = new Map<unknown, unknown>();
    let page = await mount(cache);
    await serve(p0);
    expect(sequence(page)).toEqual(F(...range(20)));
    const stored = JSON.parse(session.getItem(FEED_SNAPSHOT_KEY) ?? "null");
    expect(stored.v).toBe(FEED_EDITION_SNAPSHOT_VERSION);
    expect(stored.cursor).toBe(20);
    await unmount();

    page = await mount(cache);
    expect(sequence(page)).toEqual(F(...range(20)));
    const revalidation = await serve(again);
    expect(query(revalidation)).toEqual({ limit: "20", event_pct: "0.15", edition: served(p0).edition });
    expect(sequence(page)).toEqual(F(...range(20)));
    await fireSentinel();
    const asked = await serve(p1);
    expect(query(asked)).toEqual({ limit: "20", offset: "20", event_pct: "0.15", edition: served(p0).edition });
    expect(sequence(page)).toEqual(F(...range(40)));
  });

  it("a genuinely complete empty feed is the end state; a refused first opening is Retry, which recovers", async () => {
    const [empty, refused, retry] = transcript.scenarios.empty_vs_refusal;
    let page = await mount();
    await serve(empty);
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-end-of-feed")).toBe(true);
    expect(has(page, "data-unavailable")).toBe(false);
    await unmount();

    // A different fresh visitor, whose own first page zero is refused.
    local.clear();
    session.clear();
    page = await mount();
    await serve(refused);
    expect(cardsOf(page)).toEqual([]);
    expect(has(page, "data-end-of-feed")).toBe(false);
    expect(notice(page)).toBe("empty");
    await settle(10);
    expect(open()).toEqual([]);

    await act(async () => { unavailable.onRetry!(); });
    await settle(10);
    const asked = await serve(retry);
    expect(query(asked)).toEqual({ limit: "20", event_pct: "0.15" });
    expect(sequence(page)).toEqual(F(...range(20)));
    expect(has(page, "data-unavailable")).toBe(false);
  });
});
