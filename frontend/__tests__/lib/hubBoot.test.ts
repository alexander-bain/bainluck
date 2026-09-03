// LAT-P217 — the tournament hub's request leaves at parse time, not after hydration.
//
// What each block here would have to see to go RED, stated so a green run is evidence rather than a
// mood:
//
//  • URL IDENTITY — the boot URL stops being byte-identical to the URL `fetchTournament` puts on the
//    wire. That is the failure that silently turns the ship into a wasted 79 KB duplicate request on
//    a phone while every other test still passes. Pinned by calling the real fetcher against a
//    recording `fetch`, not by comparing two string builders to each other.
//  • ELIGIBILITY — the boot fires for a signed-in reader, whose own request would carry an
//    `Authorization` header and is therefore not the request that was parked.
//  • CLAIM-ONCE / CROSS-SLUG — a parked record survives a mismatched claim, or a document that parked
//    one tournament satisfies a request for another.
//  • THE SHIP ITSELF — `fetchTournament` stops consuming the parked response and goes back to issuing
//    its own network request. Deleting the boot path outright fails here, so this is not a test that
//    passes if the feature is removed.
//  • FALLBACK — a non-2xx, rejected, or NEVER-SETTLING boot response stops falling through to the
//    normal retrying request. The never-settling arm is the #2724 case: a parked fetch has no timeout
//    of its own, and a bare await on it would strand a reader on a skeleton for as long as the server
//    holds the connection.
//  • ROUTE SCOPE — the boot script escapes into the root layout and starts costing every non-hub
//    surface a download nobody claims; or it leaves the loading branch, which is the only part of
//    this page that is server-rendered, and so stops being in the HTML at all.

import fs from "fs";
import path from "path";

import { BOOT_AUTH_KEY_PREFIX, type FeedBootRecord } from "@/lib/discover/feedBoot";
import {
  HUB_BOOT_CLAIM_TIMEOUT_MS,
  HUB_BOOT_GLOBAL,
  HUB_SECTIONS_FIRST,
  HUB_SECTIONS_REST,
  claimHubBoot,
  hubBootEligibleFromKeys,
  hubBootPath,
  hubBootScript,
  hubBootUrl,
} from "@/lib/tournament/hubBoot";
import { API_URL, fetchTournament } from "@/lib/api";

const ROOT = path.resolve(__dirname, "..", "..");
const SLUG = "us-open";

function readSource(relative: string): string {
  const source = fs.readFileSync(path.join(ROOT, relative), "utf8");
  // A source scan that cannot find its subject must RAISE, never quietly pass.
  if (source.trim().length === 0) throw new Error(`source scan target is empty: ${relative}`);
  return source;
}

function fakeStorage(entries: Record<string, string>) {
  const keys = () => Object.keys(entries);
  return {
    getItem: (k: string) => (k in entries ? entries[k] : null),
    get length() {
      return keys().length;
    },
    key: (i: number) => keys()[i] ?? null,
  };
}

function fakeResponse(opts: { ok?: boolean; body?: unknown }): Response {
  return {
    ok: opts.ok ?? true,
    status: opts.ok === false ? 500 : 200,
    headers: { get: () => null },
    json: async () => opts.body,
  } as unknown as Response;
}

const PAYLOAD = { title: "US Open", subtitle: "", boards: {}, grids: {} };

function parkBoot(record: Partial<FeedBootRecord>) {
  // The real inline script attaches its own no-op rejection handler before parking. Model that here
  // or an unclaimed rejected boot takes the whole worker down instead of failing an assertion.
  record.response?.catch(() => {});
  (globalThis as unknown as Record<string, unknown>)[HUB_BOOT_GLOBAL] = {
    url: hubBootUrl(API_URL, SLUG),
    startedAt: 0,
    readyAt: 10,
    response: null,
    ...record,
  };
}

afterEach(() => {
  delete (globalThis as unknown as Record<string, unknown>)[HUB_BOOT_GLOBAL];
  jest.restoreAllMocks();
});

describe("the boot URL is the URL the hub really requests", () => {
  it("matches what fetchTournament puts on the wire, byte for byte", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: PAYLOAD });
    }) as unknown as typeof fetch;

    await fetchTournament(SLUG);

    expect(seen).toEqual([hubBootUrl(API_URL, SLUG)]);
  });

  it("encodes a slug that needs encoding", () => {
    expect(hubBootPath("roland garros/x")).toBe("/api/tournaments/roland%20garros%2Fx");
  });
});

// ═══ latency/135 — THE BOOT PARKS THE FIRST SCREEN, NOT THE PAGE ═══════════════════════════════
//
// The hub now asks for its payload in two halves. `claimHubBoot` matches on the WHOLE URL, so the
// section is part of the identity this file exists to protect: a boot that parked `?sections=first`
// against a page effect that asked for everything is not a wasted claim, it is two requests with
// the slow one back on the critical path — LAT-P184's failure mode wearing a new parameter.
describe("the split", () => {
  it("boots the first screen, and that is the URL the page's first request uses", async () => {
    const script = hubBootScript("https://api.example.test", SLUG);
    const parked = `https://api.example.test${hubBootPath(SLUG, HUB_SECTIONS_FIRST)}`;
    expect(script).toContain(`"${parked}"`);
    expect(parked).toContain("?sections=first");

    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: PAYLOAD });
    }) as unknown as typeof fetch;
    await fetchTournament(SLUG, HUB_SECTIONS_FIRST);
    expect(seen).toEqual([hubBootUrl(API_URL, SLUG, HUB_SECTIONS_FIRST)]);
  });

  it("the parked first-screen response is claimed by the first-screen request", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: { title: "SHOULD NOT BE FETCHED" } });
    }) as unknown as typeof fetch;
    parkBoot({
      url: hubBootUrl(API_URL, SLUG, HUB_SECTIONS_FIRST),
      response: Promise.resolve(fakeResponse({ body: PAYLOAD })),
    });

    await expect(fetchTournament(SLUG, HUB_SECTIONS_FIRST)).resolves.toEqual(PAYLOAD);
    expect(seen).toEqual([]);
  });

  it("and NEVER by the second half's request, which asks for different bytes", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: PAYLOAD });
    }) as unknown as typeof fetch;
    parkBoot({
      url: hubBootUrl(API_URL, SLUG, HUB_SECTIONS_FIRST),
      response: Promise.resolve(fakeResponse({ body: { grids: "WRONG HALF" } })),
    });

    await expect(fetchTournament(SLUG, HUB_SECTIONS_REST)).resolves.toEqual(PAYLOAD);
    expect(seen).toEqual([hubBootUrl(API_URL, SLUG, HUB_SECTIONS_REST)]);
  });

  it("the page asks for the first screen FIRST and the rest after it", () => {
    const source = readSource("app/tournaments/[slug]/page.tsx");
    const first = source.indexOf("fetchTournament(slug, HUB_SECTIONS_FIRST)");
    const rest = source.indexOf("fetchTournament(slug, HUB_SECTIONS_REST)");
    expect(first).toBeGreaterThan(-1);
    expect(rest).toBeGreaterThan(first);
    // CHAINED, not raced. Two parallel requests share one bandwidth-bound pipe on Slow 4G and the
    // 67 KB half slows the 20 KB half down — the defect re-created one layer up. The `rest` call
    // sits inside the `first` continuation, so its text is after the `.then(` that opens it.
    expect(source.lastIndexOf(".then((payload)", rest)).toBeGreaterThan(first);
  });
});

describe("who may boot", () => {
  it("boots for a device with no persisted Firebase user", () => {
    expect(hubBootEligibleFromKeys([])).toBe(true);
    expect(hubBootEligibleFromKeys(["bainluck_session_id", "discover_dismissed"])).toBe(true);
  });

  it("does NOT boot for a signed-in reader, whose own request carries an Authorization header", () => {
    expect(hubBootEligibleFromKeys([`${BOOT_AUTH_KEY_PREFIX}key:[DEFAULT]`])).toBe(false);
    expect(
      hubBootEligibleFromKeys(["bainluck_session_id", `${BOOT_AUTH_KEY_PREFIX}k:[DEFAULT]`])
    ).toBe(false);
  });
});

describe("claimHubBoot", () => {
  it("returns the parked record for an exact URL match", () => {
    parkBoot({ response: Promise.resolve(fakeResponse({ body: PAYLOAD })) });
    expect(claimHubBoot(hubBootUrl(API_URL, SLUG))).not.toBeNull();
  });

  it("refuses a different tournament and still consumes the record", () => {
    parkBoot({ response: Promise.resolve(fakeResponse({ body: PAYLOAD })) });
    expect(claimHubBoot(hubBootUrl(API_URL, "roland-garros"))).toBeNull();
    expect(claimHubBoot(hubBootUrl(API_URL, SLUG))).toBeNull();
  });

  it("returns null when nothing is parked", () => {
    expect(claimHubBoot(hubBootUrl(API_URL, SLUG))).toBeNull();
  });
});

describe("fetchTournament consumes the parked response", () => {
  it("returns the boot body without issuing a second request", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: { title: "SHOULD NOT BE FETCHED" } });
    }) as unknown as typeof fetch;
    parkBoot({ response: Promise.resolve(fakeResponse({ body: PAYLOAD })) });

    await expect(fetchTournament(SLUG)).resolves.toEqual(PAYLOAD);
    expect(seen).toEqual([]);
  });

  it("falls through to the normal request when the boot response is not ok", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: PAYLOAD });
    }) as unknown as typeof fetch;
    parkBoot({ response: Promise.resolve(fakeResponse({ ok: false, body: {} })) });

    await expect(fetchTournament(SLUG)).resolves.toEqual(PAYLOAD);
    expect(seen).toEqual([hubBootUrl(API_URL, SLUG)]);
  });

  it("falls through when the boot fetch rejected", async () => {
    const seen: string[] = [];
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      seen.push(String(url));
      return fakeResponse({ body: PAYLOAD });
    }) as unknown as typeof fetch;
    parkBoot({ response: Promise.reject(new Error("dead network")) });

    await expect(fetchTournament(SLUG)).resolves.toEqual(PAYLOAD);
    expect(seen).toEqual([hubBootUrl(API_URL, SLUG)]);
  });

  it("does not wait forever on a boot fetch that never settles (#2724)", async () => {
    jest.useFakeTimers();
    try {
      const seen: string[] = [];
      global.fetch = jest.fn(async (url: RequestInfo | URL) => {
        seen.push(String(url));
        return fakeResponse({ body: PAYLOAD });
      }) as unknown as typeof fetch;
      // A promise that never resolves is exactly what a request held behind a migration lock looks
      // like from the browser: no error, no body, no timeout of its own.
      parkBoot({ response: new Promise<Response>(() => {}) });

      const pending = fetchTournament(SLUG);
      await jest.advanceTimersByTimeAsync(HUB_BOOT_CLAIM_TIMEOUT_MS + 1);

      await expect(pending).resolves.toEqual(PAYLOAD);
      expect(seen).toEqual([hubBootUrl(API_URL, SLUG)]);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("the inline script", () => {
  const script = hubBootScript("https://api.example.test", SLUG);

  it("names the boot URL, the auth prefix and the slot", () => {
    // latency/135: the parked URL carries the section. It is the whole identity `claimHubBoot`
    // matches on, so it is asserted with the section rather than without it.
    expect(script).toContain(
      `"https://api.example.test${hubBootPath(SLUG, HUB_SECTIONS_FIRST)}"`
    );
    expect(script).toContain(`"${BOOT_AUTH_KEY_PREFIX}"`);
    expect(script).toContain(`"${HUB_BOOT_GLOBAL}"`);
  });

  it("cannot terminate the script element that carries it", () => {
    expect(script.toLowerCase()).not.toContain("</script");
  });

  it("handles its own rejection so a dead network is not an unhandled rejection", () => {
    expect(script).toContain("p.catch(");
  });

  it("runs as written: a signed-out device boots, a signed-in one does not", () => {
    const run = (entries: Record<string, string>) => {
      const calls: string[] = [];
      const w: Record<string, unknown> = {
        localStorage: fakeStorage(entries),
        performance: { now: () => 5 },
      };
      w.fetch = (url: string) => {
        calls.push(url);
        return Promise.resolve(fakeResponse({ body: PAYLOAD }));
      };
      // eslint-disable-next-line no-new-func
      new Function("window", "fetch", `with(window){${script}}`)(w, w.fetch);
      return { calls, parked: w[HUB_BOOT_GLOBAL] as FeedBootRecord | undefined };
    };

    const booted = run({});
    const bootUrl = `https://api.example.test${hubBootPath(SLUG, HUB_SECTIONS_FIRST)}`;
    expect(booted.calls).toEqual([bootUrl]);
    expect(booted.parked?.url).toBe(bootUrl);

    const signedIn = run({ [`${BOOT_AUTH_KEY_PREFIX}k:[DEFAULT]`]: "{}" });
    expect({ calls: signedIn.calls, parked: signedIn.parked }).toEqual({
      calls: [],
      parked: undefined,
    });
  });
});

describe("the boot script is scoped to the hub route, in its server-rendered branch", () => {
  const page = readSource("app/tournaments/[slug]/page.tsx");

  it("is rendered by the hub page", () => {
    expect(page).toContain("<HubBootScript slug={slug} />");
    expect(page).toContain('from "@/components/tournament/HubBootScript"');
  });

  it("sits in the loading branch, the only part of this page the server renders", () => {
    const loadingBranch = page.slice(page.indexOf("if (loading) {"), page.indexOf("if (error || !data)"));
    expect(loadingBranch).toContain("<HubBootScript slug={slug} />");
  });

  it("is NOT rendered by the root layout, which every other surface also pays for", () => {
    const layout = readSource("app/layout.tsx");
    expect(layout).not.toContain("HubBootScript");
    expect(layout).not.toContain("hubBootScript");
  });
});
