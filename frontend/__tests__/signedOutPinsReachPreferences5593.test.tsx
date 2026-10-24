/**
 * #5593 — a signed-out reader's pins reach `/preferences`.
 *
 * Reproduced on production 2026-10-22 01:4xZ through the real control, clean
 * signed-out context, 390px: `/futures/114584` Pin → `Pinned`, stored under
 * `bainluck_pinnedFutures:anon` → reload, still Pinned → `/preferences` printed
 * the PINNED heading over nothing, with ZERO API requests.
 *
 * Cause: the section's visibility read the pin hooks' three-state scope (the
 * anonymous bucket is real state), but its card fetch was keyed on
 * `resolvePrincipal`, which is `null` when signed out — a null SWR key never
 * dispatches. The fix keys the card fetch on `scopeOwner(resolveScope(...))`.
 *
 * Rendered, not source-scanned: each row drives the real page through
 * `renderToStaticMarkup` with an SWR stand-in that runs the page's OWN fetcher
 * for the key the page asked for, then re-renders with that body — so the
 * binding and the render gate are the page's, not this file's.
 *
 *   TZ=UTC npx jest --testPathPatterns=signedOutPinsReachPreferences5593
 */

import React from "react";

type Auth = { user: { uid: string } | null; isAuthenticated: boolean; isLoading: boolean };
type Key = (string | number)[] | null;

const SIGNED_OUT: Auth = { user: null, isAuthenticated: false, isLoading: false };
const RESTORING: Auth = { user: null, isAuthenticated: false, isLoading: true };
const ACCT_A: Auth = { user: { uid: "acct-a" }, isAuthenticated: true, isLoading: false };

const MARKET = { id: 114584, name: "MLB World Series Champion 2026" };
const EVENT = { id: 777, home_team: "Home FC", away_team: "Away FC" };

interface World {
  auth: Auth;
  pinnedFutures: number[];
  pinnedEvents: number[];
  /** SWR's cache, keyed by the serialized key the page asked for. */
  cache: Map<string, unknown>;
  /** When set, every key reads this record — a stale/kept body (keepPreviousData). */
  forceRecord?: unknown;
  keys: Key[];
  fetchers: Array<{ key: Key; fetcher: () => Promise<unknown> }>;
  apiCalls: string[];
}

const pinHook = (ids: number[]) => () => ({
  pinnedIds: ids,
  isPinned: (id: number) => ids.includes(id),
  togglePin: () => {},
  isMaxReached: false,
});

function register(world: World) {
  jest.doMock("@/hooks", () => ({
    usePageTracking: () => {},
    useScrollDepth: () => {},
    useEngagementTime: () => {},
    usePinnedEvents: pinHook(world.pinnedEvents),
    usePinnedFutures: pinHook(world.pinnedFutures),
  }));
  jest.doMock("@/hooks/useCategoryInterests", () => ({
    ...jest.requireActual("@/hooks/useCategoryInterests"),
    useCategoryInterests: () => ({ interests: {}, setInterest: () => {}, isLoading: false }),
  }));
  jest.doMock("next/navigation", () => ({
    useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
    useParams: () => ({}),
  }));
  jest.doMock("@/components/AuthProvider", () => ({
    useAuthContext: () => ({ ...world.auth, signOut: () => {} }),
  }));
  jest.doMock("@/lib/api", () => ({
    fetchUserPreferences: () => {
      world.apiCalls.push("prefs");
      return Promise.resolve({ favorites: [] });
    },
    removeFavorite: () => Promise.resolve(),
    fetchEventsByIds: (ids: number[]) => {
      world.apiCalls.push(`events:${ids.join(",")}`);
      return Promise.resolve(ids.includes(EVENT.id) ? [EVENT] : []);
    },
    fetchFuturesByIds: (ids: number[]) => {
      world.apiCalls.push(`futures:${ids.join(",")}`);
      return Promise.resolve(ids.includes(MARKET.id) ? [MARKET] : []);
    },
  }));
  // Card internals are not under test; each stands in as the link a reader taps.
  jest.doMock("@/components/FuturesCard", () => ({
    __esModule: true,
    default: ({ market }: { market: { id: number; name: string } }) =>
      React.createElement("a", { href: `/futures/${market.id}` }, market.name),
  }));
  jest.doMock("@/components/EventCard", () => ({
    __esModule: true,
    default: ({ event }: { event: { id: number; home_team: string } }) =>
      React.createElement("a", { href: `/event/${event.id}` }, event.home_team),
  }));
  jest.doMock("@/components/Analytics/TelemetryPreferences", () => ({
    TelemetryPreferences: () => null,
  }));
  jest.doMock("swr", () => ({
    __esModule: true,
    default: (key: Key, fetcher: () => Promise<unknown>) => {
      world.keys.push(key);
      if (key) world.fetchers.push({ key, fetcher });
      const data = key
        ? (world.forceRecord ?? world.cache.get(JSON.stringify(key)))
        : world.forceRecord;
      return { data, error: undefined, isLoading: false, mutate: () => {} };
    },
  }));
}

function renderOnce(world: World): string {
  let markup = "";
  jest.isolateModules(() => {
    register(world);
    /* eslint-disable @typescript-eslint/no-var-requires */
    const render = require("react-dom/server").renderToStaticMarkup;
    const Page = require("@/app/preferences/page").default;
    /* eslint-enable @typescript-eslint/no-var-requires */
    markup = render(React.createElement(Page));
  });
  return markup;
}

/** Render, run every fetcher the page dispatched (as SWR would), render again. */
async function renderSettled(world: World): Promise<string> {
  world.fetchers = [];
  renderOnce(world);
  for (const { key, fetcher } of world.fetchers) {
    world.cache.set(JSON.stringify(key), await fetcher());
  }
  world.keys = [];
  return renderOnce(world);
}

function newWorld(over: Partial<World>): World {
  return {
    auth: SIGNED_OUT,
    pinnedFutures: [],
    pinnedEvents: [],
    cache: new Map(),
    keys: [],
    fetchers: [],
    apiCalls: [],
    ...over,
  };
}

const pinnedKeys = (w: World, resource: string) =>
  w.keys.filter((k): k is (string | number)[] => !!k && k[1] === resource);

describe("#5593 — signed out, the reader's own pins are named and openable", () => {
  it("a pinned futures market is fetched and rendered as a link to its board", async () => {
    const w = newWorld({ pinnedFutures: [MARKET.id] });
    const markup = await renderSettled(w);

    expect(w.apiCalls).toContain(`futures:${MARKET.id}`);
    expect(markup).toContain(MARKET.name);
    expect(markup).toContain(`href="/futures/${MARKET.id}"`);
    // The key carries the anonymous owner, never a user principal.
    const [key] = pinnedKeys(w, "pinned-futures");
    expect(key).toEqual(["prefs", "pinned-futures", "anon:device", MARKET.id]);
  });

  it("a pinned event is fetched and rendered too (same section, same defect)", async () => {
    const w = newWorld({ pinnedEvents: [EVENT.id] });
    const markup = await renderSettled(w);
    expect(w.apiCalls).toContain(`events:${EVENT.id}`);
    expect(markup).toContain(`href="/event/${EVENT.id}"`);
  });

  it("the account-only record (Your Teams) is still never requested signed out", async () => {
    const w = newWorld({ pinnedFutures: [MARKET.id] });
    await renderSettled(w);
    expect(w.apiCalls).not.toContain("prefs");
    expect(w.keys.filter((k) => k && k[1] === "user-preferences")).toEqual([]);
  });
});

describe("#5593 — the account boundary (#1496) is unchanged", () => {
  it("while auth is restoring, no pinned fetch dispatches and nothing renders", async () => {
    const w = newWorld({ auth: RESTORING, pinnedFutures: [MARKET.id] });
    const markup = await renderSettled(w);
    expect(w.apiCalls).toEqual([]);
    expect(pinnedKeys(w, "pinned-futures")).toEqual([]);
    expect(markup).not.toContain(MARKET.name);
  });

  it("signed in, the key carries the account principal, not the device owner", async () => {
    const w = newWorld({ auth: ACCT_A, pinnedFutures: [MARKET.id] });
    const markup = await renderSettled(w);
    const [key] = pinnedKeys(w, "pinned-futures");
    expect(key).toEqual(["prefs", "pinned-futures", "user:acct-a", MARKET.id]);
    expect(markup).toContain(MARKET.name);
  });

  it("anonymous → account: a body fetched for the device bucket never renders under the account", async () => {
    const anon = newWorld({ pinnedFutures: [MARKET.id] });
    await renderSettled(anon);
    const anonRecord = anon.cache.get(
      JSON.stringify(["prefs", "pinned-futures", "anon:device", MARKET.id]),
    );
    expect(anonRecord).toBeDefined();

    // The kept body is served for every key (keepPreviousData / a late response).
    const acct = newWorld({ auth: ACCT_A, pinnedFutures: [MARKET.id], forceRecord: anonRecord });
    expect(renderOnce(acct)).not.toContain(MARKET.name);
  });

  it("account → signed out: the account's body never renders for the device bucket", async () => {
    const a = newWorld({ auth: ACCT_A, pinnedFutures: [MARKET.id] });
    await renderSettled(a);
    const acctRecord = a.cache.get(
      JSON.stringify(["prefs", "pinned-futures", "user:acct-a", MARKET.id]),
    );
    expect(acctRecord).toBeDefined();

    const out = newWorld({ pinnedFutures: [MARKET.id], forceRecord: acctRecord });
    expect(renderOnce(out)).not.toContain(MARKET.name);
  });
});
