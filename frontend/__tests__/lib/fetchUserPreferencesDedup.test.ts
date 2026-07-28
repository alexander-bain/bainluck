/**
 * L2-205 Item 2 — `GET /api/me/preferences` in-flight coalescing.
 *
 * L2-204 mounted `usePreferredSportProperty` app-wide (via `PinSyncEffect`),
 * which reads `useCategoryInterests` -> `fetchUserPreferences()`. On `/sports`
 * and `/preferences` the route ALSO mounts its own `useCategoryInterests`, so a
 * single hard authenticated load fired TWO identical `GET /api/me/preferences`
 * requests. `fetchUserPreferences` now coalesces concurrent same-identity
 * requests into one network call, keyed by auth token and cleared on settle.
 *
 * These are the invariants from the queue's Item 2 acceptance:
 *  - concurrent consumers on one load => at most one preferences fetch
 *  - cache is not persisted across loads (fresh request after settle)
 *  - a user switch never reuses the prior user's in-flight promise (no leak)
 *
 * Driven directly against a fake `global.fetch` + the registered auth-token
 * getter (no jsdom in this repo).
 */
export {}; // module scope

const ORIGINAL_FETCH = global.fetch;

type ApiModule = typeof import("@/lib/api");

/** Load a FRESH copy of lib/api so the module-level in-flight cache is reset. */
function loadApi(): ApiModule {
  let mod: ApiModule | undefined;
  jest.isolateModules(() => {
    mod = require("@/lib/api") as ApiModule;
  });
  return mod as ApiModule;
}

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

/** Flush pending microtasks + timers so async awaits settle. */
const flush = () => new Promise((r) => setTimeout(r, 0));

afterEach(() => {
  global.fetch = ORIGINAL_FETCH;
  jest.clearAllMocks();
});

describe("fetchUserPreferences in-flight coalescing (L2-205 Item 2)", () => {
  it("coalesces concurrent same-identity requests into one network call", async () => {
    const api = loadApi();
    api.setAuthTokenGetter(async () => "token-A");

    let resolveFetch!: (r: Response) => void;
    const pending = new Promise<Response>((r) => {
      resolveFetch = r;
    });
    const fetchMock = jest.fn(() => pending);
    global.fetch = fetchMock as unknown as typeof fetch;

    // Two concurrent consumers (route page + app-shell property) on one load.
    const p1 = api.fetchUserPreferences();
    const p2 = api.fetchUserPreferences();

    await flush(); // let both resolve token + coalesce onto one request

    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFetch(jsonResponse({ sport_affinities: { basketball_nba: 1 } }));
    const [r1, r2] = await Promise.all([p1, p2]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(r1).toBe(r2); // identical shared result
  });

  it("does not persist across loads: a fresh call after settle re-fetches", async () => {
    const api = loadApi();
    api.setAuthTokenGetter(async () => "token-A");
    const fetchMock = jest.fn(async () =>
      jsonResponse({ sport_affinities: {} }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    await api.fetchUserPreferences(); // settles -> in-flight cleared
    await api.fetchUserPreferences(); // new load -> fresh request

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a user switch never reuses the prior user's in-flight promise", async () => {
    const api = loadApi();

    let resolveA!: (r: Response) => void;
    const pendingA = new Promise<Response>((r) => {
      resolveA = r;
    });
    const fetchMock = jest
      .fn()
      .mockImplementationOnce(() => pendingA) // user A (kept in-flight)
      .mockImplementationOnce(async () =>
        jsonResponse({ sport_affinities: { team_b: 1 } }),
      ); // user B
    global.fetch = fetchMock as unknown as typeof fetch;

    api.setAuthTokenGetter(async () => "token-A");
    const pA = api.fetchUserPreferences();
    await flush();

    // Switch identity while A's request is still in-flight.
    api.setAuthTokenGetter(async () => "token-B");
    const pB = api.fetchUserPreferences();
    await flush();

    // B must have issued its own request, not ridden A's in-flight promise.
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveA(jsonResponse({ sport_affinities: { team_a_leak: 1 } }));
    const [rA, rB] = await Promise.all([pA, pB]);

    expect(rB).toEqual({ sport_affinities: { team_b: 1 } }); // B's own data
    expect(rA).toEqual({ sport_affinities: { team_a_leak: 1 } }); // A unaffected
  });
});
