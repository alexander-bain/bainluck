// LAT-P184 (D-C, staged loading) — the first screen's request leaves at parse
// time, not after hydration.
//
// What each block here would have to see to go RED, stated so a green run is
// evidence rather than a mood:
//
//  • URL IDENTITY — the boot URL stops being byte-identical to the URL
//    `fetchFeed` actually puts on the wire (a changed page size, a changed
//    event mix, a re-ordered query string, a zero offset that stops being
//    omitted). That is the failure that silently turns the ship into a wasted
//    duplicate request while every other test still passes.
//  • CONTAINMENT — `bootEligibleFromKeys` fires for a device state that
//    `decideFeedPrincipal` would NOT route to the shared anonymous feed. That
//    is the only way this ship can serve one reader another reader's feed, and
//    it is proved over the whole 32-state power set of the key classes.
//  • CLAIM-ONCE — a parked record survives a mismatched claim and can be picked
//    up by a later, differently-principled request.
//  • THE SHIP ITSELF — `fetchFeed` stops consuming the parked response and goes
//    back to issuing its own network request. Deleting the boot path outright
//    fails here, so this is not a test that "passes if the feature is removed".
//  • FALLBACK — a rejected, non-2xx, or unparseable boot response stops falling
//    through to the normal retrying request. That would strand a cold reader on
//    a blank feed, which is strictly worse than the defect being fixed.
//  • ROUTE SCOPE — the boot script escapes into the root layout and starts
//    costing every non-Discover surface a 65 KB download nobody claims.

import fs from "fs";
import path from "path";

import {
  BOOT_AUTH_KEY_PREFIX,
  BOOT_BLOCKING_KEYS,
  FEED_BOOT_GLOBAL,
  bootDurationMs,
  bootEligibleFromKeys,
  bootFeedPath,
  bootFeedUrl,
  claimBootFeed,
  feedBootScript,
  type FeedBootRecord,
} from "@/lib/discover/feedBoot";
import {
  decideFeedPrincipal,
  readClientPrincipalState,
} from "@/lib/discover/sharedAnonFeed";
import { FEED_EVENT_PCT, FEED_PAGE_LIMIT } from "@/lib/discover/feedPaging";
import { API_URL, fetchFeed } from "@/lib/api";

const ROOT = path.resolve(__dirname, "..", "..");

function readSource(relative: string): string {
  const full = path.join(ROOT, relative);
  const source = fs.readFileSync(full, "utf8");
  // A source scan that cannot find its subject must RAISE, never quietly pass.
  if (source.trim().length === 0) {
    throw new Error(`source scan target is empty: ${relative}`);
  }
  return source;
}

/** A localStorage stand-in with the two APIs the boot script and the real
 *  principal read use: `getItem`, plus `length`/`key` enumeration. */
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

/** Install a browser-ish global for the duration of one test. */
function withWindow(entries: Record<string, string>, run: () => void | Promise<void>) {
  const g = globalThis as unknown as Record<string, unknown>;
  const hadWindow = "window" in g;
  const previous = g.window;
  g.window = { localStorage: fakeStorage(entries) };
  const restore = () => {
    if (hadWindow) g.window = previous;
    else delete g.window;
  };
  let result: void | Promise<void>;
  try {
    result = run();
  } catch (err) {
    restore();
    throw err;
  }
  if (result && typeof (result as Promise<void>).then === "function") {
    return (result as Promise<void>).finally(restore);
  }
  restore();
  return undefined;
}

function parkBoot(record: Partial<FeedBootRecord>) {
  // The real inline script attaches its own no-op rejection handler before
  // parking (`p.catch(function(){})`), because nothing guarantees the app ever
  // claims the record. Model that here or an unclaimed rejected boot takes the
  // whole worker down instead of failing an assertion — which is exactly how
  // this fixture first misread a mutation as a pass.
  record.response?.catch(() => {});
  (globalThis as unknown as Record<string, unknown>)[FEED_BOOT_GLOBAL] = {
    url: bootFeedUrl(API_URL),
    startedAt: 0,
    readyAt: 10,
    response: null,
    ...record,
  };
}

function fakeResponse(opts: {
  ok?: boolean;
  body?: unknown;
  headers?: Record<string, string>;
}): Response {
  const headers = opts.headers ?? {};
  return {
    ok: opts.ok ?? true,
    status: opts.ok === false ? 500 : 200,
    headers: { get: (k: string) => headers[k] ?? headers[k.toLowerCase()] ?? null },
    json: async () => opts.body,
  } as unknown as Response;
}

const FEED_BODY = { items: [], total: 0, limit: 20, offset: 0, has_more: false };

afterEach(() => {
  delete (globalThis as unknown as Record<string, unknown>)[FEED_BOOT_GLOBAL];
  jest.restoreAllMocks();
});

describe("the boot URL is the request fetchFeed actually issues", () => {
  it("builds the shared-anon initial path from the shared constants", () => {
    expect(bootFeedPath()).toBe(
      `/api/feed?limit=${FEED_PAGE_LIMIT}&event_pct=${FEED_EVENT_PCT}`
    );
    // A zero offset must be OMITTED, exactly as `fetchFeed` omits it.
    expect(bootFeedPath()).not.toContain("offset");
  });

  it("matches, byte for byte, the URL fetchFeed puts on the wire", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: unknown) => {
      seen.push(String(url));
      return fakeResponse({ body: FEED_BODY });
    }) as unknown as typeof fetch;

    await withWindow({}, async () => {
      await fetchFeed(
        { limit: FEED_PAGE_LIMIT, offset: 0, event_pct: FEED_EVENT_PCT },
        { sharedAnonEligible: true, authenticated: false }
      );
    });

    expect(seen).toHaveLength(1);
    expect(seen[0]).toBe(bootFeedUrl(API_URL));
  });
});

describe("boot eligibility is a strict SUBSET of shared-anon suppression", () => {
  // The five key classes the boot script inspects. Non-empty values, because
  // the real decision treats an EMPTY dismiss list as no evidence — that
  // asymmetry is the whole reason containment has to be proved rather than
  // assumed.
  const KEY_CLASSES: Array<[string, string]> = [
    ["bainluck_session_id", "sess-1"],
    ["discover_interaction_profile_v1", JSON.stringify({ categories: { nba: {} } })],
    ["discover_dismissed", JSON.stringify({ items: [{ id: "a", ts: 1 }] })],
    ["discover_has_swiped", "1"],
    [`${BOOT_AUTH_KEY_PREFIX}KEY:[DEFAULT]`, JSON.stringify({ uid: "u1" })],
  ];

  it("never fires where decideFeedPrincipal would not suppress the session id", () => {
    let fired = 0;
    for (let mask = 0; mask < 1 << KEY_CLASSES.length; mask++) {
      const entries: Record<string, string> = {};
      for (let bit = 0; bit < KEY_CLASSES.length; bit++) {
        if (mask & (1 << bit)) {
          const [k, v] = KEY_CLASSES[bit];
          entries[k] = v;
        }
      }
      const keys = Object.keys(entries);
      const eligible = bootEligibleFromKeys(keys);
      if (!eligible) continue;
      fired++;

      withWindow(entries, () => {
        const state = readClientPrincipalState();
        // The boot script fires before any interaction can have happened this
        // mount, and never for a reader with a persisted Firebase user.
        const decision = decideFeedPrincipal({
          authenticated: keys.some((k) => k.startsWith(BOOT_AUTH_KEY_PREFIX)),
          hasDurableSession: state.hasDurableSession,
          interactionAuthority: state.interactionAuthority,
          hasInMemoryInteraction: false,
        });
        expect({ mask, suppress: decision.suppressSessionId }).toEqual({
          mask,
          suppress: true,
        });
      });
    }
    // The containment claim is vacuous if the boot never fires at all.
    expect(fired).toBe(1); // exactly the empty-storage state
  });

  it("is blocked by each device-state key on its own", () => {
    for (const key of BOOT_BLOCKING_KEYS) {
      expect(bootEligibleFromKeys([key])).toBe(false);
    }
    expect(bootEligibleFromKeys([`${BOOT_AUTH_KEY_PREFIX}abc:[DEFAULT]`])).toBe(false);
    expect(bootEligibleFromKeys([])).toBe(true);
    // An unrelated key must NOT block — otherwise the ship quietly stops firing
    // the first time any other feature writes to localStorage.
    expect(bootEligibleFromKeys(["theme", "consent_v2"])).toBe(true);
  });

  it("mirrors the storage keys sharedAnonFeed.ts owns", () => {
    const src = readSource("lib/discover/sharedAnonFeed.ts");
    const declared = [
      ...src.matchAll(/^const [A-Z_]+_STORAGE_KEY = "([^"]+)";$/gm),
    ].map((m) => m[1]);
    if (declared.length === 0) {
      throw new Error(
        "source scan found no *_STORAGE_KEY declarations in sharedAnonFeed.ts — " +
          "the mirror guard cannot be evaluated and must not report a pass"
      );
    }
    expect([...BOOT_BLOCKING_KEYS].sort()).toEqual([...declared].sort());
  });
});

describe("claimBootFeed", () => {
  it("returns the record on an exact URL match", () => {
    const response = Promise.resolve(fakeResponse({ body: FEED_BODY }));
    parkBoot({ response });
    const claimed = claimBootFeed(bootFeedUrl(API_URL));
    expect(claimed?.response).toBe(response);
  });

  it("consumes the record even when the URL does not match", () => {
    parkBoot({ response: Promise.resolve(fakeResponse({ body: FEED_BODY })) });
    expect(claimBootFeed("https://example.test/api/feed?limit=1")).toBeNull();
    // Consumed: a second, correctly-addressed claim must not find it.
    expect(claimBootFeed(bootFeedUrl(API_URL))).toBeNull();
  });

  it("claims at most once", () => {
    parkBoot({ response: Promise.resolve(fakeResponse({ body: FEED_BODY })) });
    expect(claimBootFeed(bootFeedUrl(API_URL))).not.toBeNull();
    expect(claimBootFeed(bootFeedUrl(API_URL))).toBeNull();
  });

  it("rejects a parked record with no usable response", () => {
    parkBoot({ response: null });
    expect(claimBootFeed(bootFeedUrl(API_URL))).toBeNull();
  });

  it("reports the boot fetch's own wire time, not the time until it was claimed", () => {
    expect(bootDurationMs({ url: "", startedAt: 40, readyAt: 300, response: null }, 9000)).toBe(260);
    // Headers not seen yet: fall back to now, never to a negative number.
    expect(bootDurationMs({ url: "", startedAt: 40, readyAt: null, response: null }, 90)).toBe(50);
    expect(bootDurationMs({ url: "", startedAt: 40, readyAt: 10, response: null }, 90)).toBe(0);
  });
});

describe("fetchFeed consumes the parked boot response", () => {
  it("issues NO network request when the boot response is claimable", async () => {
    const spy = jest.fn();
    global.fetch = spy as unknown as typeof fetch;
    parkBoot({
      response: Promise.resolve(
        fakeResponse({
          body: FEED_BODY,
          headers: { "X-Feed-Cache": "hit", "X-Feed-Elapsed-Ms": "7.1" },
        })
      ),
    });

    await withWindow({}, async () => {
      const out = await fetchFeed(
        { limit: FEED_PAGE_LIMIT, offset: 0, event_pct: FEED_EVENT_PCT },
        { sharedAnonEligible: true, authenticated: false }
      );
      expect(out).toEqual(FEED_BODY);
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("does NOT claim a boot response for a session-scoped reader", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: unknown) => {
      seen.push(String(url));
      return fakeResponse({ body: FEED_BODY });
    }) as unknown as typeof fetch;
    const bootBody = { ...FEED_BODY, total: 999 };
    parkBoot({ response: Promise.resolve(fakeResponse({ body: bootBody })) });

    await withWindow({ bainluck_session_id: "sess-1" }, async () => {
      const out = await fetchFeed(
        { limit: FEED_PAGE_LIMIT, offset: 0, event_pct: FEED_EVENT_PCT },
        { sharedAnonEligible: true, authenticated: false }
      );
      // The shared-anon body must NOT reach a reader with a durable session.
      expect(out).toEqual(FEED_BODY);
    });
    expect(seen).toHaveLength(1);
  });

  it.each([
    ["a rejected boot fetch", () => Promise.reject(new Error("offline"))],
    ["a non-2xx boot response", () => Promise.resolve(fakeResponse({ ok: false, body: {} }))],
    [
      "an unparseable boot body",
      () =>
        Promise.resolve({
          ok: true,
          headers: { get: () => null },
          json: async () => {
            throw new Error("bad json");
          },
        } as unknown as Response),
    ],
  ])("falls back to the normal retrying request on %s", async (_label, make) => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: unknown) => {
      seen.push(String(url));
      return fakeResponse({ body: FEED_BODY });
    }) as unknown as typeof fetch;
    parkBoot({ response: make() });

    await withWindow({}, async () => {
      const out = await fetchFeed(
        { limit: FEED_PAGE_LIMIT, offset: 0, event_pct: FEED_EVENT_PCT },
        { sharedAnonEligible: true, authenticated: false }
      );
      expect(out).toEqual(FEED_BODY);
    });
    expect(seen).toEqual([bootFeedUrl(API_URL)]);
  });
});

describe("the inline script", () => {
  const script = feedBootScript("https://api.example.test");

  it("names the boot URL, every blocking key, the auth prefix and the slot", () => {
    expect(script).toContain(`"https://api.example.test${bootFeedPath()}"`);
    for (const key of BOOT_BLOCKING_KEYS) expect(script).toContain(`"${key}"`);
    expect(script).toContain(`"${BOOT_AUTH_KEY_PREFIX}"`);
    expect(script).toContain(`"${FEED_BOOT_GLOBAL}"`);
  });

  it("cannot terminate the script element that carries it", () => {
    expect(script.toLowerCase()).not.toContain("</script");
  });

  it("handles its own rejection so a dead network is not an unhandled rejection", () => {
    expect(script).toContain("p.catch(");
  });

  it("runs as written: eligible storage boots, blocked storage does not", () => {
    const run = (entries: Record<string, string>) => {
      const calls: string[] = [];
      const w: Record<string, unknown> = {
        localStorage: fakeStorage(entries),
        performance: { now: () => 5 },
      };
      w.fetch = (url: string) => {
        calls.push(url);
        return Promise.resolve(fakeResponse({ body: FEED_BODY }));
      };
      // eslint-disable-next-line no-new-func
      new Function("window", "fetch", `with(window){${script}}`)(w, w.fetch);
      return { calls, parked: w[FEED_BOOT_GLOBAL] as FeedBootRecord | undefined };
    };

    const booted = run({});
    expect(booted.calls).toEqual([`https://api.example.test${bootFeedPath()}`]);
    expect(booted.parked?.url).toBe(`https://api.example.test${bootFeedPath()}`);

    for (const key of BOOT_BLOCKING_KEYS) {
      const blocked = run({ [key]: "x" });
      expect({ key, calls: blocked.calls, parked: blocked.parked }).toEqual({
        key,
        calls: [],
        parked: undefined,
      });
    }
    const signedIn = run({ [`${BOOT_AUTH_KEY_PREFIX}k:[DEFAULT]`]: "{}" });
    expect(signedIn.calls).toEqual([]);
  });
});

describe("the boot script is scoped to the Discover route", () => {
  it("is rendered by the Discover page", () => {
    const page = readSource("app/discover/page.tsx");
    expect(page).toContain("<FeedBootScript />");
    expect(page).toContain('from "@/components/discover/FeedBootScript"');
  });

  it("is NOT rendered by the root layout, which every other surface also pays for", () => {
    const layout = readSource("app/layout.tsx");
    expect(layout).not.toContain("FeedBootScript");
    expect(layout).not.toContain("feedBootScript");
  });
});
