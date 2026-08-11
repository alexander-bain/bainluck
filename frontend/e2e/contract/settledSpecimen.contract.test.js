"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");

const {
  PROP_BEARING_SPORTS,
  LISTING_LIMIT,
  MAX_PROP_PROBES,
  specimenListings,
  newestFirst,
  isSettledCandidate,
  findSettledEventWithProps,
} = require("../helpers/settledSpecimen");

/**
 * UX-P053 (#1650) — the specimen finder, pinned against fixtures.
 *
 * WHY FIXTURES AND NOT A DISPATCH. The previous two versions of this finder were
 * only ever exercised against the live slate, and the live slate is what defeated
 * them: run 31448073014 failed at 18:10 PT because the completed window held 16
 * events, 14 soccer + 1 tennis + one prop-less MLB game, and nothing else was
 * reachable at that hour. A rail whose only test is "dispatch it and see" cannot
 * tell a broken finder from a thin evening.
 *
 * The fixtures below encode the REAL production shapes measured 2026-08-11:
 *   - `/api/events?status=completed` — `commence_time` ASC, day-bounded, with the
 *     prop-bearing games (when any exist) at the END.
 *   - `/api/events/highlights?min_percentile=0` — a 3-day lookback that reaches
 *     event 15191147 (81 props, 60 graded), the specimen this pack exists to
 *     photograph.
 *
 * Both directions per gotcha #43: the finder must reach the specimen it used to
 * miss, AND must still return null on a slate that genuinely has none — because
 * "no evidence collected" is not a pass on this rail, and a finder that invents a
 * specimen would open a false green on exactly the surface #1650 lives on.
 */

const API = "https://api.example.test";

/** Build a fake `get` over a url -> body map. Records what was fetched. */
function fakeGet(routes, log) {
  return async (url) => {
    if (log) log.push(url);
    const hit = Object.keys(routes).find((k) => url.startsWith(k));
    if (hit === undefined) return { ok: () => false, json: async () => ({}) };
    const body = routes[hit];
    if (body === "ERROR") throw new Error("network down");
    if (body === "NOT_OK") return { ok: () => false, json: async () => ({}) };
    return { ok: () => true, json: async () => body };
  };
}

const ev = (id, commence, status = "completed") => ({ id, commence_time: commence, status });
const props = (n, graded) => ({
  player_props: Array.from({ length: n }, (_, i) => ({ hit: i < graded ? true : null })),
});

/** The measured MLB lookback: the 81-prop specimen is NOT the newest entry. */
const MLB_HIGHLIGHTS = {
  highlights: [
    ev(15191123, "2026-08-09T17:35:00+00:00"), // Yankees/Braves — 0 props
    ev(15191038, "2026-08-10T00:20:00+00:00"), // Padres/Astros — 0 props (newest)
    ev(15185953, "2026-08-09T16:15:00+00:00"),
    ev(15191147, "2026-08-09T17:35:00+00:00"), // THE SPECIMEN — 81 props, 60 graded
  ],
};

describe("#1650 specimen finder — the listings it asks", () => {
  it("asks the LOOKBACK before the day-bounded listing", () => {
    const urls = specimenListings(API).map((l) => l.url);
    const firstDayBounded = urls.findIndex((u) => u.includes("/api/events?status=completed"));
    const lastLookback = urls.map((u) => u.includes("/highlights")).lastIndexOf(true);
    assert.ok(lastLookback < firstDayBounded, "every lookback listing must precede every day-bounded one");
  });

  it("opens the interestingness filter — at the default of 75 the specimen is invisible", () => {
    for (const l of specimenListings(API).filter((x) => x.url.includes("/highlights"))) {
      assert.match(l.url, /min_percentile=0/, `${l.url} must not inherit min_percentile=75`);
    }
  });

  it("keeps the day-bounded listings as fallbacks rather than replacing them", () => {
    const urls = specimenListings(API).map((l) => l.url);
    assert.ok(
      urls.some((u) => u.includes("/api/events?status=completed") && !u.includes("sport=")),
      "the unfiltered completed listing must survive as the last resort",
    );
    for (const sport of PROP_BEARING_SPORTS) {
      assert.ok(urls.some((u) => u.includes(`/highlights`) && u.includes(`sport=${sport}`)));
      assert.ok(urls.some((u) => u.includes(`status=completed`) && u.includes(`sport=${sport}`)));
    }
  });

  it("reads each listing shape from its own key", async () => {
    const listings = specimenListings(API);
    const lookback = listings.find((l) => l.url.includes("/highlights"));
    const dayBound = listings.find((l) => l.url.includes("status=completed"));
    assert.deepEqual(lookback.pick({ highlights: [1, 2] }), [1, 2]);
    assert.equal(lookback.pick({ events: [1, 2] }), undefined);
    assert.deepEqual(dayBound.pick({ events: [3] }), [3]);
  });
});

describe("#1650 specimen finder — ordering", () => {
  it("reverses the ASC listing, because props are on the LATEST games", () => {
    const asc = [
      ev(1, "2026-08-10T00:00:00+00:00"),
      ev(2, "2026-08-10T17:00:00+00:00"),
      ev(3, "2026-08-10T22:30:00+00:00"),
    ];
    assert.deepEqual(newestFirst(asc).map((e) => e.id), [3, 2, 1]);
  });

  it("does not mutate its input", () => {
    const asc = [ev(1, "2026-08-10T00:00:00+00:00"), ev(2, "2026-08-10T22:00:00+00:00")];
    newestFirst(asc);
    assert.deepEqual(asc.map((e) => e.id), [1, 2], "the caller's array must be untouched");
  });

  it("survives an unparseable or missing date instead of throwing", () => {
    const messy = [ev(1, "not-a-date"), ev(2, "2026-08-10T22:00:00+00:00"), { id: 3 }];
    assert.deepEqual(newestFirst(messy).map((e) => e.id), [2, 1, 3]);
    assert.deepEqual(newestFirst(null), []);
  });
});

describe("#1650 specimen finder — which entries are eligible", () => {
  it("rejects a live or scheduled game: #1650 cannot occur on one", () => {
    assert.equal(isSettledCandidate({ status: "live" }), false);
    assert.equal(isSettledCandidate({ status: "scheduled" }), false);
  });

  it("accepts settled states, and an entry the listing already filtered", () => {
    assert.equal(isSettledCandidate({ status: "completed" }), true);
    assert.equal(isSettledCandidate({ status: "closed" }), true);
    assert.equal(isSettledCandidate({ id: 1 }), true, "no status = the query already filtered it");
    assert.equal(isSettledCandidate(null), false);
  });
});

describe("#1650 specimen finder — the search", () => {
  it("REACHES the specimen the day-bounded listing could not see", async () => {
    const log = [];
    const get = fakeGet(
      {
        [`${API}/api/events/highlights?days=3&sport=baseball_mlb`]: MLB_HIGHLIGHTS,
        [`${API}/api/events/15191147/game-markets`]: props(81, 60),
        [`${API}/api/events/15191123/game-markets`]: props(0, 0),
        [`${API}/api/events/15191038/game-markets`]: props(0, 0),
        [`${API}/api/events/15185953/game-markets`]: props(0, 0),
      },
      log,
    );

    const found = await findSettledEventWithProps(get, API);
    assert.deepEqual(found, { id: 15191147, propCount: 81, gradedCount: 60 });
  });

  it("counts ONLY an explicit `hit` as graded — a defaulted false is not a verdict", async () => {
    const get = fakeGet({
      [`${API}/api/events/highlights?days=3&sport=baseball_mlb`]: { highlights: [ev(7, "2026-08-10T00:00:00+00:00")] },
      [`${API}/api/events/7/game-markets`]: {
        player_props: [{ hit: true }, { hit: false }, { hit: null }, {}],
      },
    });
    const found = await findSettledEventWithProps(get, API);
    assert.equal(found.propCount, 4);
    assert.equal(found.gradedCount, 2, "true and false are verdicts; null and absent are not");
  });

  it("returns NULL on a slate with no props — the rail must fail, not invent evidence", async () => {
    // The real 2026-08-11T01:10Z slate: soccer, tennis, one prop-less MLB game.
    const get = fakeGet({
      [`${API}/api/events/highlights?days=3&sport=baseball_mlb`]: {
        highlights: [ev(15191038, "2026-08-10T00:20:00+00:00")],
      },
      [`${API}/api/events/15191038/game-markets`]: props(0, 0),
      [`${API}/api/events?status=completed`]: {
        events: [ev(15191879, "2026-08-10T00:00:00+00:00"), ev(15184840, "2026-08-10T22:30:00+00:00")],
      },
      [`${API}/api/events/15191879/game-markets`]: props(0, 0),
      [`${API}/api/events/15184840/game-markets`]: props(0, 0),
    });
    assert.equal(await findSettledEventWithProps(get, API), null);
  });

  it("skips a live game even when it publishes props", async () => {
    const get = fakeGet({
      [`${API}/api/events/highlights?days=3&sport=baseball_mlb`]: {
        highlights: [ev(99, "2026-08-11T01:00:00+00:00", "live"), ev(42, "2026-08-10T20:00:00+00:00")],
      },
      [`${API}/api/events/99/game-markets`]: props(50, 0),
      [`${API}/api/events/42/game-markets`]: props(12, 9),
    });
    const found = await findSettledEventWithProps(get, API);
    assert.equal(found.id, 42, "the live game must never be chosen, however many props it has");
  });

  it("never spends more than MAX_PROP_PROBES game-markets fetches", async () => {
    const log = [];
    const many = { highlights: Array.from({ length: 40 }, (_, i) => ev(1000 + i, "2026-08-10T00:00:00+00:00")) };
    const routes = { [`${API}/api/events/highlights`]: many, [`${API}/api/events?status=completed`]: many };
    for (let i = 0; i < 40; i += 1) routes[`${API}/api/events/${1000 + i}/game-markets`] = props(0, 0);

    assert.equal(await findSettledEventWithProps(fakeGet(routes, log), API), null);
    const probes = log.filter((u) => u.includes("/game-markets")).length;
    assert.equal(probes, MAX_PROP_PROBES, `spent ${probes} probes, budget is ${MAX_PROP_PROBES}`);
  });

  it("does not re-probe an event that appears in two listings", async () => {
    const log = [];
    const shared = { highlights: [ev(500, "2026-08-10T00:00:00+00:00")] };
    const get = fakeGet(
      {
        [`${API}/api/events/highlights`]: shared,
        [`${API}/api/events?status=completed`]: { events: [ev(500, "2026-08-10T00:00:00+00:00")] },
        [`${API}/api/events/500/game-markets`]: props(0, 0),
      },
      log,
    );
    await findSettledEventWithProps(get, API);
    const probes = log.filter((u) => u.includes("/500/game-markets")).length;
    assert.equal(probes, 1, "the same event must not spend the budget twice");
  });

  it("treats a dead listing as a dead SOURCE, not a dead search", async () => {
    const get = fakeGet({
      [`${API}/api/events/highlights?days=3&sport=baseball_mlb`]: "ERROR",
      [`${API}/api/events/highlights?days=3&sport=basketball_nba`]: "NOT_OK",
      [`${API}/api/events?status=completed&limit=${LISTING_LIMIT}&sport=baseball_mlb`]: {
        events: [ev(77, "2026-08-10T20:00:00+00:00")],
      },
      [`${API}/api/events/77/game-markets`]: props(30, 30),
    });
    const found = await findSettledEventWithProps(get, API);
    assert.equal(found.id, 77, "one broken listing must not abort the whole search");
  });

  it("survives a malformed body without throwing", async () => {
    const get = fakeGet({
      [`${API}/api/events/highlights`]: { highlights: "not-an-array" },
      [`${API}/api/events?status=completed`]: { events: [{ id: "abc" }, null, ev(9, "2026-08-10T00:00:00+00:00")] },
      [`${API}/api/events/9/game-markets`]: { player_props: null },
    });
    assert.equal(await findSettledEventWithProps(get, API), null);
  });
});
