/**
 * UX-P236 — THE REFUSAL HAS TO REACH THE READER WHO ALREADY HAS THE BIRD.
 *
 * ═══ WHAT CERT-610 FOUND, AND WHY IT WAS RIGHT ═══
 *
 * UX-P235 shipped the refusal (board item 14: *a wrong logo is worse than no
 * logo*) into `getWikipediaImage`'s FETCH path. But `getWikipediaImage` reads
 * `img_wiki_*` out of localStorage first, and that cache has a 24-hour TTL. So
 * for every reader who had already opened `/futures/109441` — which is to say
 * everyone who had seen the defect Alex reported — the new predicate never ran.
 * They kept being served `Peacock_Plumage.jpg` from their own browser for up to
 * a day. The predicate was correct and the ship did not land.
 *
 * The cert's words: *"the unchanged 24-hour `img_wiki_*` client cache is read
 * before the new metadata refusal ... the new predicate never runs for them."*
 *
 * ═══ THE REPAIR, AND WHY IT IS NOT A CACHE-KEY BUMP ═══
 *
 * Bumping the key would fix the eight outcomes Alex looked at, once, and would
 * re-arm the identical trap for the next person who edits the refusal rules —
 * because the verdict would still be frozen at WRITE time. Instead the entry now
 * stores the EVIDENCE Wikipedia returned (`type`, `description`, the thumbnail
 * URL) and the refusal is re-decided on every READ.
 *
 * Two consequences, and both are asserted below rather than asserted in prose:
 *   1. a pre-repair entry is discarded, so the bird goes away on the next paint;
 *   2. a change to `NOT_A_BRAND_DESCRIPTIONS` applies to entries that are
 *      already in the reader's cache, with no version to bump and no refetch.
 *
 * ═══ WHAT WOULD MAKE THIS FILE VACUOUS ═══
 *
 * "Never serve from cache" would pass every refusal assertion here and quietly
 * put 25 network round trips on a page that renders 25 rows, on a day when cold
 * loads are a named priority. So every refusal test below is paired with a
 * fetch-count control, and `a kept brand is served from cache with NO fetch` is
 * the test that fails if the cache is disabled instead of corrected.
 */

import {
  __resetWikipediaLookupState,
  getWikipediaImage,
} from "@/lib/images";

const BIRD_URL = "https://upload.wikimedia.org/Peacock_Plumage.jpg";
const HULU_URL = "https://upload.wikimedia.org/Hulu_logo.svg.png";

/** VERBATIM from the Wikipedia summary API, 2026-08-31 — the bird Alex saw. */
const PEACOCK_SUMMARY = {
  type: "standard",
  title: "Peafowl",
  description: "Group of large game birds",
  thumbnail: { source: BIRD_URL },
};

const HULU_SUMMARY = {
  type: "standard",
  title: "Hulu",
  description: "American video streaming service",
  thumbnail: { source: HULU_URL },
};

/**
 * `testEnvironment` is `node` and `jest-environment-jsdom` is not installed, so
 * the store is stubbed rather than mocked away. It is a real read/write/delete
 * surface: the tests below assert on what is actually left in it, which a
 * `jest.fn()` shim could not show.
 */
function installLocalStorage(): Map<string, string> {
  const store = new Map<string, string>();
  const localStorageStub = {
    getItem: (k: string) => (store.has(k) ? (store.get(k) as string) : null),
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size;
    },
  };
  (global as unknown as { window: unknown }).window = { localStorage: localStorageStub };
  (global as unknown as { localStorage: unknown }).localStorage = localStorageStub;
  return store;
}

const CACHE_KEY = "img_wiki_peacock";
const HULU_KEY = "img_wiki_hulu";

/** The exact bytes UX-P235's build wrote: a bare URL, no metadata, no shape marker. */
function seedPreRepairEntry(store: Map<string, string>, key: string, url: string | null): void {
  store.set(key, JSON.stringify({ data: url, ts: Date.now() }));
}

/** The post-repair shape: the evidence, not the verdict. */
function seedRepairedEntry(
  store: Map<string, string>,
  key: string,
  entry: { url: string | null; type?: string | null; description?: string | null },
): void {
  store.set(key, JSON.stringify({ data: { k: "wiki-summary-1", ...entry }, ts: Date.now() }));
}

describe("UX-P236: the reader who already has the bird", () => {
  const realFetch = global.fetch;
  let store: Map<string, string>;
  let fetchCount: number;

  function serve(body: Record<string, unknown>) {
    fetchCount = 0;
    global.fetch = (async () => {
      fetchCount++;
      return { ok: true, json: async () => body };
    }) as unknown as typeof fetch;
  }

  beforeEach(() => {
    __resetWikipediaLookupState();
    store = installLocalStorage();
    fetchCount = 0;
  });

  afterAll(() => {
    global.fetch = realFetch;
    delete (global as unknown as { window?: unknown }).window;
    delete (global as unknown as { localStorage?: unknown }).localStorage;
  });

  test("🔴 CERT-610: a bird cached by the PRE-REPAIR build is not served", async () => {
    // The whole finding, in one case. Before the repair this resolved to
    // BIRD_URL straight out of the cache and the refusal never executed.
    seedPreRepairEntry(store, CACHE_KEY, BIRD_URL);
    serve(PEACOCK_SUMMARY);

    await expect(getWikipediaImage("Peacock")).resolves.toBeNull();
  });

  test("the refetched entry is rewritten in the repaired shape", async () => {
    seedPreRepairEntry(store, CACHE_KEY, BIRD_URL);
    serve(PEACOCK_SUMMARY);

    await getWikipediaImage("Peacock");

    // So the NEXT read is a cache hit that refuses, rather than a second round
    // trip. Note this is the write path doing the work, not the delete — see
    // the following test for the case where the delete is what matters.
    const raw = JSON.parse(store.get(CACHE_KEY) as string);
    expect(raw.data.k).toBe("wiki-summary-1");
  });

  test("🔴 the bird does not survive a FAILED refetch either", async () => {
    // The case that makes dropping the stale entry load-bearing rather than
    // tidy. On the happy path the refetch overwrites the poisoned key anyway,
    // so a test that only checks the happy path would pass with the delete
    // removed. Here the network is gone: nothing is written, and if the stale
    // entry were merely IGNORED rather than dropped it would still be sitting
    // there — ready to be served again by any future reader of that key, and
    // occupying LRU budget that a live entry needs.
    seedPreRepairEntry(store, CACHE_KEY, BIRD_URL);
    global.fetch = (async () => {
      throw new Error("network is gone");
    }) as unknown as typeof fetch;

    await expect(getWikipediaImage("Peacock")).resolves.toBeNull();
    expect(store.has(CACHE_KEY)).toBe(false);
  });

  test("a pre-repair entry for a REAL brand is re-resolved, and the brand survives", async () => {
    // The cost of discarding pre-repair entries is one refetch per name. It must
    // not cost the ambition Alex likes: Hulu comes back.
    //
    // The fetch-count assertion is what makes this discriminating rather than
    // decorative: against the blocked bytes the same URL came back with NO
    // fetch, straight from the poisoned entry, and a value-only assertion
    // therefore passed pre-repair for entirely the wrong reason.
    seedPreRepairEntry(store, HULU_KEY, HULU_URL);
    serve(HULU_SUMMARY);

    await expect(getWikipediaImage("Hulu")).resolves.toBe(HULU_URL);
    expect(fetchCount).toBe(1);
  });

  test("a pre-repair NEGATIVE entry is also discarded — null was a verdict too", async () => {
    // `cacheSet(key, null)` was written both for "no article" AND for "refused".
    // The two are indistinguishable in the old shape, so neither can be trusted:
    // a name refused by a rule we have since corrected would otherwise stay
    // blank for a day.
    seedPreRepairEntry(store, HULU_KEY, null);
    serve(HULU_SUMMARY);

    await expect(getWikipediaImage("Hulu")).resolves.toBe(HULU_URL);
  });
});

describe("UX-P236: the policy is re-applied on every read, not frozen at write", () => {
  const realFetch = global.fetch;
  let store: Map<string, string>;
  let fetchCount: number;

  function serveUnexpected() {
    fetchCount = 0;
    global.fetch = (async () => {
      fetchCount++;
      return { ok: true, json: async () => HULU_SUMMARY };
    }) as unknown as typeof fetch;
  }

  beforeEach(() => {
    __resetWikipediaLookupState();
    store = installLocalStorage();
    serveUnexpected();
  });

  afterAll(() => {
    global.fetch = realFetch;
    delete (global as unknown as { window?: unknown }).window;
    delete (global as unknown as { localStorage?: unknown }).localStorage;
  });

  test("🔴 a cached bird is refused WITHOUT a refetch", async () => {
    // This is the property a cache-key bump would not have. The entry is in the
    // repaired shape and perfectly fresh; it is refused because the rules are
    // consulted now, not because the entry is old.
    seedRepairedEntry(store, CACHE_KEY, {
      url: BIRD_URL,
      type: "standard",
      description: "Group of large game birds",
    });

    await expect(getWikipediaImage("Peacock")).resolves.toBeNull();
    expect(fetchCount).toBe(0);
  });

  test("a kept brand is served from cache with NO fetch — the cache still works", async () => {
    // The control. If the repair were "stop trusting the cache", this fails.
    seedRepairedEntry(store, HULU_KEY, {
      url: HULU_URL,
      type: "standard",
      description: "American video streaming service",
    });

    await expect(getWikipediaImage("Hulu")).resolves.toBe(HULU_URL);
    expect(fetchCount).toBe(0);
  });

  test("🔴 the EVIDENCE is what is stored — the refused URL is still in the entry", async () => {
    // The structural claim behind "a later rule change reaches cached readers".
    // If `cacheSet` stored the verdict (null) instead, relaxing a rule could
    // never restore this image without a refetch, and tightening one could never
    // remove an image without a key bump. Storing what Wikipedia SAID is what
    // makes the read-time decision possible at all.
    global.fetch = (async () => ({
      ok: true,
      json: async () => PEACOCK_SUMMARY,
    })) as unknown as typeof fetch;

    await expect(getWikipediaImage("Peacock")).resolves.toBeNull();

    const entry = JSON.parse(store.get(CACHE_KEY) as string).data;
    expect(entry.url).toBe(BIRD_URL);
    expect(entry.description).toBe("Group of large game birds");
  });

  test("a 404 caches the absence and does not re-ask", async () => {
    let calls = 0;
    global.fetch = (async () => {
      calls++;
      return { ok: false, json: async () => ({}) };
    }) as unknown as typeof fetch;

    await expect(getWikipediaImage("Nonesuch Brand")).resolves.toBeNull();
    await expect(getWikipediaImage("Nonesuch Brand")).resolves.toBeNull();
    expect(calls).toBe(1);
  });
});
