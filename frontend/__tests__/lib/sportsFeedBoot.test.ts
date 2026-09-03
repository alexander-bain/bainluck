/**
 * LAT-P218 — guards for the Sports tab's parse-time boot fetch.
 *
 * WHAT EACH BLOCK WOULD HAVE TO SEE TO GO RED, stated so a green run is evidence rather than a mood:
 *
 *  • URL IDENTITY — the boot URL stops being byte-identical to the URL `fetchFeed` puts on the wire.
 *    That is the failure that silently turns the ship into a wasted duplicate feed request on a phone
 *    while every other test still passes (LAT-P171/P172). Pinned by driving the real `fetchFeed`
 *    against a recording `fetch`, never by comparing two string builders to each other.
 *  • SLOT — the script parks somewhere `fetchFeed`'s existing claim does not read. That would make
 *    the ship a no-op that also measures as a no-op: the quietest possible failure.
 *  • ELIGIBILITY — the boot fires for a signed-in or returning reader, who must never be handed the
 *    shared anonymous feed. Proven over the whole key power set AND by executing the real script.
 *  • DEADLINE — the claim awaits a parked promise with no timeout. A parked fetch has no retries, so
 *    an un-raced claim is strictly WORSE than no boot during a #2724 database spell. Both arms run:
 *    a claim that resolves is used, a claim that never resolves falls through to the retrying path.
 *
 * Node test environment (jest.config.js `testEnvironment: 'node'`), so `window` is installed per test
 * exactly the way `feedBootStagedLoading.test.ts` and `hubBoot.test.ts` do it.
 */

import {
  BOOT_AUTH_KEY_PREFIX,
  BOOT_BLOCKING_KEYS,
  FEED_BOOT_CLAIM_TIMEOUT_MS,
  FEED_BOOT_GLOBAL,
  bootEligibleFromKeys,
  type FeedBootRecord,
} from "@/lib/discover/feedBoot";
import { HUB_BOOT_CLAIM_TIMEOUT_MS } from "@/lib/tournament/hubBoot";
import {
  SPORTS_FEED_MODE,
  bootSportsFeedPath,
  bootSportsFeedUrl,
  sportsBootEligibleFromKeys,
  sportsFeedBootScript,
} from "@/lib/sports/feedBoot";
import { API_URL, fetchFeed } from "@/lib/api";
import { initialFeedRequest } from "@/lib/discover/feedPaging";

/** A localStorage stand-in with the APIs the boot script and the real principal read use. */
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
    delete g[FEED_BOOT_GLOBAL];
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

function park(record: Partial<FeedBootRecord>) {
  // The real inline script attaches its own no-op rejection handler before parking, because nothing
  // guarantees the app ever claims the record. Model that or an unclaimed rejected boot takes the
  // whole worker down instead of failing an assertion.
  record.response?.catch(() => {});
  (globalThis as unknown as Record<string, unknown>)[FEED_BOOT_GLOBAL] = {
    url: bootSportsFeedUrl(API_URL),
    startedAt: 0,
    readyAt: 10,
    response: null,
    ...record,
  };
}

/** The exact params + opts `app/sports/page.tsx` passes on a cold load for a fresh signed-out reader. */
const sportsColdParams = () => {
  const { limit, offset } = initialFeedRequest();
  return { limit, offset, mode: SPORTS_FEED_MODE };
};
const SPORTS_COLD_OPTS = { sharedAnonEligible: true, authenticated: false };

function recordingFetch(wire: string[], body: unknown = { items: [{ id: "network" }] }) {
  return jest.fn(async (input: unknown) => {
    wire.push(String(input));
    return fakeResponse(body);
  }) as unknown as typeof fetch;
}

describe("LAT-P218 · the sports boot URL is the URL that reaches the wire", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
  });

  it("equals the URL fetchFeed puts on the wire for the page's own cold-load call", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      await fetchFeed(sportsColdParams(), SPORTS_COLD_OPTS);
    });
    expect(wire).toHaveLength(1);
    // The assertion that matters. Not "one builder equals another builder I also wrote".
    expect(wire[0]).toBe(bootSportsFeedUrl(API_URL));
  });

  it("carries mode=sports and NO event_pct — Discover's boot URL would have missed", () => {
    const path = bootSportsFeedPath();
    expect(path).toContain(`mode=${SPORTS_FEED_MODE}`);
    // Discover's `bootFeedPath()` sets event_pct. Copying it here is the mistake this pins shut.
    expect(path).not.toContain("event_pct");
  });

  it("omits a zero offset, because fetchFeed does", () => {
    // `fetchFeed` writes offset only `if (params?.offset)`. A boot URL carrying `offset=0` is a
    // different URL and claims nothing.
    expect(bootSportsFeedPath()).not.toContain("offset=");
  });
});

describe("LAT-P218 · who the sports boot fires for", () => {
  it("is the same rule as Discover's, not a second copy of it", () => {
    const universe = [
      ...BOOT_BLOCKING_KEYS,
      `${BOOT_AUTH_KEY_PREFIX}abc:[DEFAULT]`,
      "unrelated_key",
    ];
    for (let mask = 0; mask < 1 << universe.length; mask++) {
      const keys = universe.filter((_, i) => mask & (1 << i));
      expect(sportsBootEligibleFromKeys(keys)).toBe(bootEligibleFromKeys(keys));
    }
  });

  it("refuses when any device-state key is present", () => {
    for (const key of BOOT_BLOCKING_KEYS) {
      expect(sportsBootEligibleFromKeys([key])).toBe(false);
    }
  });

  it("refuses when a firebase user is persisted", () => {
    expect(sportsBootEligibleFromKeys([`${BOOT_AUTH_KEY_PREFIX}AIzaKey:[DEFAULT]`])).toBe(false);
  });

  it("fires for a brand-new install", () => {
    expect(sportsBootEligibleFromKeys([])).toBe(true);
    expect(sportsBootEligibleFromKeys(["some_unrelated_key"])).toBe(true);
  });
});

describe("LAT-P218 · the script the document renders", () => {
  it("parks into the slot fetchFeed already claims from", () => {
    expect(sportsFeedBootScript("https://api.example.com")).toContain(
      JSON.stringify(FEED_BOOT_GLOBAL)
    );
  });

  it("parks the sports URL against the given origin", () => {
    expect(sportsFeedBootScript("https://api.example.com")).toContain(
      JSON.stringify(bootSportsFeedUrl("https://api.example.com"))
    );
  });

  it("checks every blocking key and the auth prefix BEFORE fetching", () => {
    const script = sportsFeedBootScript("https://api.example.com");
    for (const key of BOOT_BLOCKING_KEYS) expect(script).toContain(key);
    expect(script).toContain(BOOT_AUTH_KEY_PREFIX);
    expect(script.indexOf(BOOT_AUTH_KEY_PREFIX)).toBeLessThan(script.indexOf("fetch("));
  });

  it("handles its own rejection, so a dead network is not an unhandled rejection", () => {
    expect(sportsFeedBootScript("https://api.example.com")).toContain("p.catch(function(){})");
  });

  it("EXECUTED FOR REAL: boots a fresh install, refuses a returning reader, refuses a signed-in one", () => {
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
        return Promise.resolve(fakeResponse({ items: [] }));
      };
      const script = sportsFeedBootScript("https://api.example.com");
      // eslint-disable-next-line no-new-func
      new Function("window", "fetch", `with(window){${script}}`)(w, w.fetch);
      return { calls, parked: w[FEED_BOOT_GLOBAL] as FeedBootRecord | undefined };
    };

    const fresh = run({});
    expect(fresh.calls).toEqual([bootSportsFeedUrl("https://api.example.com")]);
    expect(fresh.parked?.url).toBe(bootSportsFeedUrl("https://api.example.com"));

    for (const key of BOOT_BLOCKING_KEYS) {
      const returning = run({ [key]: "x" });
      expect(returning.calls).toEqual([]);
      expect(returning.parked).toBeUndefined();
    }

    const signedIn = run({ [`${BOOT_AUTH_KEY_PREFIX}AIzaKey:[DEFAULT]`]: "{}" });
    expect(signedIn.calls).toEqual([]);
    expect(signedIn.parked).toBeUndefined();
  });
});

describe("LAT-P218 · the script does not move the page", () => {
  // A SOURCE SCAN, and it says so. Frontend jest here cannot render the page (no effects, no layout),
  // so this cannot be proven by measuring a margin — but the defect is real and cheap to pin:
  // `space-y-5` compiles to `& > * + * { margin-top: 1.25rem }`. A <script> renders nothing yet IS an
  // element child, so placing it first INSIDE that wrapper makes LeagueChips the second child and
  // pushes the whole page down 1.25rem. An invisible instrument causing a visible layout shift is the
  // worst trade a latency change can make, and it would not show up in any timing number.
  //
  // Discover's boot script sits inside its root div safely because that div has no `space-y`; copying
  // that placement here is exactly the mistake this guards.
  function readPageSource(): string {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require("fs") as typeof import("fs");
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require("path") as typeof import("path");
    const file = path.join(__dirname, "..", "..", "app", "sports", "page.tsx");
    const src = fs.readFileSync(file, "utf8");
    // A scan whose target vanished must go RED, not silently pass over an empty string.
    if (src.trim().length === 0) throw new Error(`source scan target is empty: ${file}`);
    return src;
  }

  it("renders <SportsFeedBootScript /> BEFORE the space-y wrapper opens", () => {
    const src = readPageSource();
    const script = src.indexOf("<SportsFeedBootScript />");
    const wrapper = src.indexOf('<div className="space-y-5">');
    expect(script).toBeGreaterThan(-1);
    expect(wrapper).toBeGreaterThan(-1);
    expect(script).toBeLessThan(wrapper);
  });

  it("the page still has exactly one boot script", () => {
    const src = readPageSource();
    expect(src.split("<SportsFeedBootScript />").length - 1).toBe(1);
  });
});

describe("LAT-P218 · the claim is raced against a deadline", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    jest.useRealTimers();
  });

  it("agrees with the hub's deadline — one number, two modules", () => {
    expect(FEED_BOOT_CLAIM_TIMEOUT_MS).toBe(HUB_BOOT_CLAIM_TIMEOUT_MS);
  });

  it("CONTROL: a parked response that resolves is used, and no second request is issued", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    await withWindow({}, async () => {
      park({ response: Promise.resolve(fakeResponse({ items: [{ id: "booted" }] })) });
      const out = (await fetchFeed(sportsColdParams(), SPORTS_COLD_OPTS)) as unknown as {
        items: { id: string }[];
      };
      expect(out.items[0].id).toBe("booted");
      expect(wire).toEqual([]); // the whole point: the network was not touched again
    });
  });

  it("REGRESSION: a parked response that never resolves falls through to the retrying path", async () => {
    const wire: string[] = [];
    global.fetch = recordingFetch(wire);
    jest.useFakeTimers();
    await withWindow({}, async () => {
      // The #2724 shape: the server holds the connection and this never settles.
      park({ response: new Promise<Response>(() => {}), readyAt: null });
      const pending = fetchFeed(sportsColdParams(), SPORTS_COLD_OPTS);

      // Before the deadline nothing has fallen through — this proves the TIMER, not just the outcome.
      // Without it the test would pass identically against a claim that never awaited at all.
      await Promise.resolve();
      await Promise.resolve();
      expect(wire).toEqual([]);

      jest.advanceTimersByTime(FEED_BOOT_CLAIM_TIMEOUT_MS);
      jest.useRealTimers();
      const out = (await pending) as unknown as { items: { id: string }[] };
      expect(out.items[0].id).toBe("network");
      expect(wire).toEqual([bootSportsFeedUrl(API_URL)]);
    });
  });
});
