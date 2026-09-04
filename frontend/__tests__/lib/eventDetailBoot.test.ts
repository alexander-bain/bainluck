/**
 * LAT-P219 (#2846) — guards for the Event page's parse-time boot of its FOUR hero calls.
 *
 * WHAT EACH BLOCK WOULD HAVE TO SEE TO GO RED, stated so a green run is evidence rather than a mood:
 *
 *  • URL IDENTITY — any of the four boot URLs stops being byte-identical to what `lib/api.ts` puts
 *    on the wire. That silently turns the ship into FOUR wasted duplicate requests on a phone while
 *    every other test still passes (LAT-P171/P172). Pinned by driving the four real fetchers against
 *    a recording `fetch`, never by comparing two string builders to each other.
 *  • THE `hours` LITERAL — the page stops passing `EVENT_BOOT_HISTORY_HOURS`. This is the one
 *    parameter of the four not derivable from the id, so it is the only one that can drift; it WAS a
 *    bare `48` at the call site before this shipped.
 *  • THE RENDER SITE — the boot moves from the layout into the page. The page's first render, the one
 *    the SERVER emits, takes an early `if (eventLoading)` return that paints a spinner and nothing
 *    else, so a boot script in the page's main return would never reach the HTML, never execute and
 *    never park — while every test that renders the loaded state still passed. This block executes
 *    the real layout and asserts a boot script comes out of it.
 *  • THE MAP SLOT — a claim consumes a SIBLING's entry, or the slot survives exhaustion. This boot is
 *    the only one of four that parks more than one record, so the "claim mine, leave theirs" rule is
 *    new behaviour and is the thing most likely to break under edit.
 *  • ELIGIBILITY — the boot fires for a signed-in reader. Proven by executing the real script.
 *  • DEADLINE — a claim awaits a parked promise with no timeout. A parked fetch has no retries, so an
 *    un-raced claim is strictly WORSE than no boot during a #2724 spell. Both arms run.
 *
 * Node test environment (jest.config.js `testEnvironment: 'node'`), so `window` is installed per test
 * exactly the way `sportsFeedBoot.test.ts` and `hubBoot.test.ts` do it.
 */

import {
  BOOT_AUTH_KEY_PREFIX,
  FEED_BOOT_CLAIM_TIMEOUT_MS,
  type FeedBootRecord,
} from "@/lib/discover/feedBoot";
import { HUB_BOOT_CLAIM_TIMEOUT_MS } from "@/lib/tournament/hubBoot";
import {
  EVENT_BOOT_CLAIM_TIMEOUT_MS,
  EVENT_BOOT_GLOBAL,
  EVENT_BOOT_HISTORY_HOURS,
  claimEventBoot,
  eventBootEligibleFromKeys,
  eventBootPaths,
  eventBootScript,
  eventBootUrls,
} from "@/lib/event/detailBoot";
import {
  API_URL,
  fetchEvent,
  fetchEventHistory,
  fetchGameMarkets,
  fetchTeamProgression,
} from "@/lib/api";

const EVENT_ID = 15293206;

/** A localStorage stand-in with the APIs the boot script reads. */
function fakeStorage(entries: Record<string, string>) {
  const keys = () => Object.keys(entries);
  return {
    getItem: (k: string) => (k in entries ? entries[k] : null),
    setItem: (k: string, v: string) => {
      entries[k] = v;
    },
    removeItem: (k: string) => {
      delete entries[k];
    },
    get length() {
      return keys().length;
    },
    key: (i: number) => keys()[i] ?? null,
  };
}

/** Install a browser-ish global for the duration of one test, async-safe. */
async function withWindow(entries: Record<string, string>, run: () => void | Promise<void>) {
  const g = globalThis as unknown as Record<string, unknown>;
  const hadWindow = "window" in g;
  const previous = g.window;
  g.window = { localStorage: fakeStorage(entries) };
  try {
    await run();
  } finally {
    if (hadWindow) g.window = previous;
    else delete g.window;
    delete g[EVENT_BOOT_GLOBAL];
  }
}

function fakeResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response;
}

/** Park a full four-entry map, overriding one URL's record. */
function parkMap(overrides: Record<string, Partial<FeedBootRecord>> = {}) {
  const map: Record<string, FeedBootRecord> = {};
  for (const url of eventBootUrls(API_URL, EVENT_ID)) {
    const record: FeedBootRecord = {
      url,
      startedAt: 0,
      readyAt: 10,
      response: null,
      ...(overrides[url] ?? {}),
    };
    // The real inline script attaches its own no-op rejection handler before parking, because
    // nothing guarantees the app ever claims the record. Model that or an unclaimed rejected boot
    // takes the whole worker down instead of failing an assertion.
    record.response?.catch(() => {});
    map[url] = record;
  }
  (globalThis as unknown as Record<string, unknown>)[EVENT_BOOT_GLOBAL] = map;
  return map;
}

function recordingFetch(wire: string[], body: unknown = { id: "network" }) {
  return jest.fn(async (input: unknown) => {
    wire.push(String(input));
    return fakeResponse(body);
  }) as unknown as typeof fetch;
}

describe("LAT-P219 · the four boot URLs are the URLs that reach the wire", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
  });

  it("each of the four fetchers puts its own boot URL on the wire, byte for byte", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      // Nothing parked, so every one of these falls through to the real network path — which is
      // exactly the URL the boot must match.
      await fetchEvent(EVENT_ID);
      await fetchGameMarkets(EVENT_ID);
      await fetchTeamProgression(EVENT_ID);
      await fetchEventHistory(EVENT_ID, EVENT_BOOT_HISTORY_HOURS);
    });
    // The assertion that matters. Not "one builder equals another builder I also wrote".
    expect(wire).toEqual(eventBootUrls(API_URL, EVENT_ID));
  });

  it("parks exactly the four calls that gate the hero, and nothing that does not", () => {
    const paths = eventBootPaths(EVENT_ID);
    expect(paths).toHaveLength(4);
    // The three second-wave calls start AFTER the hero paints (3,394 / 4,245 / 6,341 ms on the
    // measured waterfall). Parking them would spend request budget for no first-screen gain.
    const joined = paths.join(" ");
    expect(joined).not.toContain("/api/feed");
    expect(joined).not.toContain("search/trending");
    expect(joined).not.toContain("related-futures");
  });

  it("carries the shared history window, not a second copy of the number", () => {
    expect(eventBootPaths(EVENT_ID)).toContain(
      `/api/events/${EVENT_ID}/history?hours=${EVENT_BOOT_HISTORY_HOURS}`
    );
  });

  it("pins the window at 48 h — the value the page has always asked for", () => {
    // Every other assertion in this file passes EVENT_BOOT_HISTORY_HOURS to both sides, so they move
    // together and none of them can see the constant itself drift. Changing it is a PRODUCT change
    // to how much history the chart draws, not a boot detail, and it should have to be deliberate.
    // (Found by mutation: 48 -> 24 left all 19 tests green.)
    expect(EVENT_BOOT_HISTORY_HOURS).toBe(48);
  });
});

describe("LAT-P219 · the page consumes the shared history window", () => {
  // A SOURCE SCAN, and it says so — frontend jest here cannot render the client page (no effects).
  // The defect it pins is real and was live until this ship: `fetchEventHistory(eventId, 48)` with a
  // bare literal, while the boot built `?hours=48` from its own constant. Two builders that must stay
  // equal is precisely LAT-P171/P172's shape, and a drift here costs a silent duplicate request.
  function readPageSource(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs") as typeof import("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path") as typeof import("path");
    const file = path.join(__dirname, "..", "..", "app", "events", "[id]", "page.tsx");
    const src = fs.readFileSync(file, "utf8");
    // A scan whose target vanished must go RED, not silently pass over an empty string.
    if (src.trim().length === 0) throw new Error(`source scan target is empty: ${file}`);
    return src;
  }

  it("passes EVENT_BOOT_HISTORY_HOURS to fetchEventHistory, never a literal", () => {
    const src = readPageSource();
    expect(src).toContain("fetchEventHistory(eventId, EVENT_BOOT_HISTORY_HOURS)");
    expect(src).not.toContain("fetchEventHistory(eventId, 48)");
  });
});

describe("LAT-P219 · the boot is rendered by the LAYOUT, because the page's server render is a spinner", () => {
  // THE TRAP THIS PINS: `app/events/[id]/page.tsx` returns early on `if (eventLoading)`, and that is
  // the branch the SERVER renders. A boot script in the page's main return reaches the browser never.
  // So this executes the real layout and looks for a script in what comes out.
  //
  // Executed, not scanned: a source scan would pass on a layout that imports the component and never
  // renders it ([[r_getsource_guard_vacuous_when]] is exactly this shape).
  //
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const layoutModule = require("@/app/events/[id]/layout");
  const EventDetailLayout = layoutModule.default as (props: {
    children: React.ReactNode;
    params: Promise<{ id: string }>;
  }) => Promise<{ props: { children: unknown[] } }>;

  /** Flatten a returned element tree to the list of `data-testid`s it contains. */
  function testIds(node: unknown, out: string[] = []): string[] {
    if (!node || typeof node !== "object") return out;
    if (Array.isArray(node)) {
      for (const child of node) testIds(child, out);
      return out;
    }
    const el = node as { props?: Record<string, unknown>; type?: unknown };
    const id = el.props?.["data-testid"];
    if (typeof id === "string") out.push(id);
    // A React element for a function component has not rendered yet, so call it to see inside.
    if (typeof el.type === "function" && el.props) {
      try {
        testIds((el.type as (p: unknown) => unknown)(el.props), out);
      } catch {
        /* not a plain sync component — the testid check above is the assertion */
      }
    }
    if (el.props?.children) testIds(el.props.children, out);
    return out;
  }

  it("EXECUTED: the layout emits a boot script for a numeric id", async () => {
    const tree = await EventDetailLayout({
      children: null,
      params: Promise.resolve({ id: String(EVENT_ID) }),
    });
    expect(testIds(tree)).toContain("event-boot");
  });

  it("REGRESSION: emits NO boot script for a non-numeric id", async () => {
    const tree = await EventDetailLayout({
      children: null,
      params: Promise.resolve({ id: "not-an-id" }),
    });
    expect(testIds(tree)).not.toContain("event-boot");
  });
});

describe("LAT-P219 · who the event boot fires for", () => {
  it("refuses when a firebase user is persisted", () => {
    expect(eventBootEligibleFromKeys([`${BOOT_AUTH_KEY_PREFIX}AIzaKey:[DEFAULT]`])).toBe(false);
  });

  it("fires for a signed-out reader, including a returning one", () => {
    // Unlike Discover's, this boot has no device-state disqualifiers: the endpoints take an id and
    // no principal, so a returning anonymous reader's own request is byte-identical to the boot's.
    expect(eventBootEligibleFromKeys([])).toBe(true);
    expect(eventBootEligibleFromKeys(["bainluck_session_id", "discover_dismissed"])).toBe(true);
  });

  it("EXECUTED FOR REAL: boots four calls for a signed-out reader, nothing for a signed-in one", () => {
    // Reading the script is not the same as running it. This evaluates the emitted source against a
    // fake window, which is the only thing that can catch a guard that is present but unreachable.
    const run = (entries: Record<string, string>) => {
      const calls: string[] = [];
      const w: Record<string, unknown> = {
        localStorage: fakeStorage({ ...entries }),
        performance: { now: () => 5 },
      };
      w.fetch = (url: string) => {
        calls.push(url);
        return Promise.resolve(fakeResponse({}));
      };
      const script = eventBootScript("https://api.example.com", EVENT_ID);
      // eslint-disable-next-line no-new-func
      new Function("window", "fetch", `with(window){${script}}`)(w, w.fetch);
      return {
        calls,
        parked: w[EVENT_BOOT_GLOBAL] as Record<string, FeedBootRecord> | undefined,
      };
    };

    const fresh = run({});
    expect(fresh.calls).toEqual(eventBootUrls("https://api.example.com", EVENT_ID));
    // Every parked record is keyed by its own URL and carries it — the claim checks both.
    for (const url of eventBootUrls("https://api.example.com", EVENT_ID)) {
      expect(fresh.parked?.[url]?.url).toBe(url);
    }

    const signedIn = run({ [`${BOOT_AUTH_KEY_PREFIX}AIzaKey:[DEFAULT]`]: "{}" });
    expect(signedIn.calls).toEqual([]);
    expect(signedIn.parked).toBeUndefined();
  });
});

describe("LAT-P219 · the map slot: claim mine, leave theirs", () => {
  afterEach(() => {
    delete (globalThis as unknown as Record<string, unknown>)[EVENT_BOOT_GLOBAL];
  });

  it("returns the record for its own URL and CONSUMES only that entry", () => {
    const urls = eventBootUrls(API_URL, EVENT_ID);
    parkMap({ [urls[0]]: { response: Promise.resolve(fakeResponse({})) } });

    const got = claimEventBoot(urls[0]);
    expect(got?.url).toBe(urls[0]);

    const slot = (globalThis as unknown as Record<string, unknown>)[EVENT_BOOT_GLOBAL] as Record<
      string,
      unknown
    >;
    // The claimed entry is gone...
    expect(slot[urls[0]]).toBeUndefined();
    // ...and its three siblings, whose requests have not run yet, are untouched. THIS is the rule
    // that differs from the three single-record boots, where a claim discards the whole slot.
    expect(Object.keys(slot).sort()).toEqual(urls.slice(1).sort());
  });

  it("returns null for a URL it did not park, and leaves every entry alone", () => {
    const urls = eventBootUrls(API_URL, EVENT_ID);
    parkMap();
    expect(claimEventBoot(`${API_URL}/api/events/999/game-markets`)).toBeNull();
    const slot = (globalThis as unknown as Record<string, unknown>)[EVENT_BOOT_GLOBAL] as Record<
      string,
      unknown
    >;
    expect(Object.keys(slot).sort()).toEqual([...urls].sort());
  });

  it("drops the slot once the last entry is claimed, so a soft navigation finds nothing stale", () => {
    const urls = eventBootUrls(API_URL, EVENT_ID);
    parkMap(Object.fromEntries(urls.map((u) => [u, { response: Promise.resolve(fakeResponse({})) }])));
    for (const url of urls) expect(claimEventBoot(url)).not.toBeNull();
    expect((globalThis as unknown as Record<string, unknown>)[EVENT_BOOT_GLOBAL]).toBeUndefined();
  });

  it("returns null when nothing was parked at all — the soft-navigation case", () => {
    expect(claimEventBoot(eventBootUrls(API_URL, EVENT_ID)[0])).toBeNull();
  });

  it("a different event's id can never claim this one's record", () => {
    // `fetchEventsByIds` calls `fetchEvent` in a loop; only the booted id may match.
    parkMap({});
    expect(claimEventBoot(`${API_URL}/api/events/${EVENT_ID + 1}`)).toBeNull();
  });
});

describe("LAT-P219 · the claim is raced against a deadline", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    jest.useRealTimers();
  });

  it("agrees with the other two boots' deadline — one number, three modules", () => {
    expect(EVENT_BOOT_CLAIM_TIMEOUT_MS).toBe(HUB_BOOT_CLAIM_TIMEOUT_MS);
    expect(EVENT_BOOT_CLAIM_TIMEOUT_MS).toBe(FEED_BOOT_CLAIM_TIMEOUT_MS);
  });

  it("CONTROL: a parked response that resolves is used, and no second request is issued", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      const urls = eventBootUrls(API_URL, EVENT_ID);
      parkMap({
        [urls[0]]: { response: Promise.resolve(fakeResponse({ id: "booted" })) },
      });
      const out = (await fetchEvent(EVENT_ID)) as unknown as { id: string };
      expect(out.id).toBe("booted");
      expect(wire).toEqual([]); // the whole point: the network was not touched again
    });
  });

  it("CONTROL: a parked NON-2xx falls through to the retrying path", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      const urls = eventBootUrls(API_URL, EVENT_ID);
      parkMap({
        [urls[1]]: {
          response: Promise.resolve({
            ok: false,
            status: 503,
            headers: { get: () => null },
            json: async () => ({}),
          } as unknown as Response),
        },
      });
      await fetchGameMarkets(EVENT_ID);
      expect(wire).toEqual([urls[1]]);
    });
  });

  it("CONTROL: a parked fetch that REJECTS falls through rather than throwing at the reader", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      const urls = eventBootUrls(API_URL, EVENT_ID);
      parkMap({ [urls[2]]: { response: Promise.reject(new Error("dead network")) } });
      await expect(fetchTeamProgression(EVENT_ID)).resolves.toBeDefined();
      expect(wire).toEqual([urls[2]]);
    });
  });

  it("REGRESSION: a parked response that never resolves falls through to the retrying path", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    jest.useFakeTimers();
    await withWindow({}, async () => {
      const urls = eventBootUrls(API_URL, EVENT_ID);
      // The #2724 shape: the server holds the connection and this never settles.
      parkMap({ [urls[0]]: { response: new Promise<Response>(() => {}), readyAt: null } });
      const pending = fetchEvent(EVENT_ID);

      // Before the deadline nothing has fallen through — this proves the TIMER, not just the outcome.
      await Promise.resolve();
      expect(wire).toEqual([]);

      jest.advanceTimersByTime(EVENT_BOOT_CLAIM_TIMEOUT_MS + 1);
      await pending;
      expect(wire).toEqual([urls[0]]);
    });
  });
});
