// #847 — THE CORRECTNESS CONSOLE ANSWERS "CAN WE TRUST OUR NUMBERS TODAY?"
// WITHOUT EVER TURNING AN UNREAD NUMBER GREEN.
//
// The page composes five existing endpoints into six tiles. What these tests
// pin, metric by metric:
//   - units, denominator and the CITED threshold that colours each tile;
//   - zero versus missing: a count that is absent is unverified, a real zero
//     is a real zero, and a rate the server computes as 0 over an empty
//     denominator is NOT a failure;
//   - stale, partial, wrong-shape and failed reads are unverified, never green,
//     and a red seen in stale data is reported as stale-with-last-verdict;
//   - one failing read never blanks or holds its siblings (all five start at
//     once and report as each settles);
//   - a 401/403 is a statement about the credential, not the data (#6024);
//   - the page carries the three GA4 hooks before any return, reads with the
//     Authorization header (never `?secret=`), and never polls, retries or
//     busts a cache.
//
// No jsdom in this project: render tests use `renderToStaticMarkup`, which is
// enough to assert what a reader would see in every state. /admin is
// auth-gated, so under notice 49 this ships on tests plus rendered output;
// production timing and reader acceptance belong to measurement after release.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CorrectnessConsoleView from "@/components/admin/CorrectnessConsole";
import {
  ADMIN_READS,
  CORRECTNESS_ENDPOINTS,
  INITIAL_READS,
  boundedRead,
  evaluateAll,
  evaluateCategoryMce,
  evaluateGridHealth,
  evaluateGuessFamily,
  evaluateLinkRate,
  evaluateSourceCoverage,
  evaluateWinnerCoverage,
  foldStates,
  mceState,
  startCorrectnessReads,
  startUiClock,
  summarize,
  UI_CLOCK_INTERVAL_MS,
  WINNERS_STALE_AFTER_S,
  type CorrectnessReads,
  type ReadResult,
} from "@/lib/correctnessConsole";

const NOW = Date.parse("2026-10-19T21:00:00Z");
const minutesAgo = (m: number) => new Date(NOW - m * 60_000).toISOString();
const ok = (data: unknown): ReadResult => ({ status: "ok", data, ms: 120, httpStatus: 200 });

// ── fixtures, in the shapes the backend builds ─────────────────────────────

function winnerSource(over: Record<string, unknown> = {}) {
  // tradeable = 1000 - 100 = 900 = 850 + 30 + 20 + 0
  return {
    source: "kalshi",
    resolved: 1000,
    untradeable_excluded: 100,
    has_winner: 850,
    resolved_single_sided: 30,
    heuristic_resolved: 20,
    needs_backfill: 0,
    ...over,
  };
}
const winnersPayload = (sources: unknown[], computedAt: string | null = minutesAgo(20)) => ({
  sources,
  computed_at: computedAt,
});

function category(name: string, mce: number, n: number) {
  return { category: name, mce, mce_unweighted: mce, outcomes: n, ece: mce, mce_worst: mce, n, gated: false };
}
const freshEnvelope = { availability: "fresh", producer: { stalled: false, beats_missed: 0, age_s: 600 } };
// The envelope of the saved 2026-10-19 20:16Z monitor payload (Oct 13 curve):
// availability stale, main key absent, producer stalled 149 beats.
const staleEnvelope = {
  availability: "stale",
  cache: { status: "stale", reason: "main_key_absent", age_s: 538824, generated_at: "2026-10-13T14:35:40.360309+00:00" },
  producer: { task: "precompute_calibration_main", interval_s: 3600, stall_after_s: 14400, age_s: 538824, beats_missed: 149, stalled: true },
  staged: { measured: false, reason: "served_bank_empty" },
};

function coverageRow(sport: string, total: number, counts: Partial<Record<string, number>> = {}, expected: Record<string, boolean> | null = null) {
  const full = { odds_api: total, espn: total, statpal: total, kalshi: total, polymarket: total, ...counts };
  return {
    sport,
    total,
    live: 0,
    ...full,
    espn_wp: total,
    model: total,
    mlb: 0,
    expected_sources: expected ?? { odds_api: true, espn: true, statpal: true, espn_wp: true, model: true, mlb: false, kalshi: true, polymarket: true },
  };
}
const TIER1 = ["americanfootball_nfl", "basketball_nba", "baseball_mlb", "icehockey_nhl"];
const dashboardPayload = (rows: unknown[], generatedAt = minutesAgo(0)) => ({ generated_at: generatedAt, source_coverage: rows });

function lrRow(sport: string, league: string, open: number, linked: number) {
  return { sport, league, total: open, linked, open_total: open, open_linked: linked, link_rate: open ? (100 * linked) / open : 0, link_rate_all: 0 };
}
const T1_LEAGUES: [string, string][] = [["football", "NFL"], ["basketball", "NBA"], ["baseball", "MLB"], ["hockey", "NHL"]];
function linkRatePayload(over: { kalshi?: unknown[]; polymarket?: unknown[]; extra?: Record<string, unknown>; generatedAt?: string } = {}) {
  const full = T1_LEAGUES.map(([s, l]) => lrRow(s, l, 10, 10));
  return {
    generated_at: over.generatedAt ?? minutesAgo(10),
    overall: { open_total: 80, open_linked: 72, link_rate_pct: 90, link_rate_raw_pct: 85.2, excluded_open_upstream_coverage_gap: 6, denominator_note: "Headline rate uses open markets only." },
    kalshi: { totals: {}, by_sport: over.kalshi ?? full },
    polymarket: { totals: {}, by_sport: over.polymarket ?? full },
    ...over.extra,
  };
}

function gridsPayload(grids: Record<string, unknown>, generatedAt = minutesAgo(10)) {
  return { generated_at: generatedAt, scores: {}, avg_score: null, grids };
}
const allGrids100 = { nba: { health_score: 100, findings: [] }, nhl: { health_score: 100, findings: [] }, mlb: { health_score: 100, findings: [] }, golf: { health_score: 100, findings: [] } };

// ── 1. winner coverage ─────────────────────────────────────────────────────

describe("winner coverage — the gap is markets with no resolution at all", () => {
  it("is green only when every source's gap is zero, and prints the denominator", () => {
    const t = evaluateWinnerCoverage(ok(winnersPayload([winnerSource(), winnerSource({ source: "polymarket" })])), NOW);
    expect(t.state).toBe("green");
    expect(t.rows[0].value).toBe("100.0% (900/900)");
    // Heuristic resolutions are counted as answered but never called authoritative.
    expect(t.rows[0].note).toContain("20 resolved by heuristic, not authority");
  });

  it("turns red on a single unresolved market, and never rounds the gap to 100%", () => {
    const big = winnerSource({ resolved: 100_100, untradeable_excluded: 100, has_winner: 99_949, needs_backfill: 1, resolved_single_sided: 30, heuristic_resolved: 20 });
    const t = evaluateWinnerCoverage(ok(winnersPayload([big])), NOW);
    expect(t.state).toBe("red");
    expect(t.rows[0].value.startsWith("99.9%")).toBe(true);
    expect(t.rows[0].value).not.toContain("100.0%");
  });

  it("reads a MISSING count as unverified, not as zero gap", () => {
    const { needs_backfill: _drop, ...noGap } = winnerSource();
    void _drop;
    const t = evaluateWinnerCoverage(ok(winnersPayload([noGap])), NOW);
    expect(t.rows[0].state).toBe("unavailable");
    expect(t.state).not.toBe("green");
  });

  it("refuses a row whose four counts do not partition its denominator", () => {
    const t = evaluateWinnerCoverage(ok(winnersPayload([winnerSource({ has_winner: 851 })])), NOW);
    expect(t.rows[0].state).toBe("unavailable");
    expect(t.rows[0].note).toContain("do not add up");
  });

  it("keeps a healthy source green beside a broken sibling (partial, not blanked)", () => {
    const t = evaluateWinnerCoverage(ok(winnersPayload([winnerSource(), { source: "polymarket", resolved: "lots" }])), NOW);
    expect(t.rows.map((r) => r.state)).toEqual(["green", "unavailable"]);
    expect(t.state).toBe("partial");
  });

  it("treats the empty-cache 202 as unavailable, not as a payload", async () => {
    const r = await boundedRead(async () => new Response(JSON.stringify({ detail: "No cached result yet." }), { status: 202 }));
    expect(r).toMatchObject({ status: "error", kind: "pending", httpStatus: 202 });
    const t = evaluateWinnerCoverage(r, NOW);
    expect(t.state).toBe("unavailable");
    expect(t.headline).toContain("producer has not written its cache");
  });

  it("reports stale — with the verdict the stale data carried — past two producer beats", () => {
    const t = evaluateWinnerCoverage(ok(winnersPayload([winnerSource()], minutesAgo(121))), NOW);
    expect(t.state).toBe("stale");
    expect(t.lastVerdict).toBe("green");
    const red = evaluateWinnerCoverage(ok(winnersPayload([winnerSource({ has_winner: 849, needs_backfill: 1 })], minutesAgo(500))), NOW);
    expect(red.state).toBe("stale");
    expect(red.lastVerdict).toBe("red");
  });

  it("treats an undated payload as stale, never current", () => {
    expect(evaluateWinnerCoverage(ok(winnersPayload([winnerSource()], null)), NOW).state).toBe("stale");
  });

  it("refuses a wrong shape instead of drawing an empty green", () => {
    expect(evaluateWinnerCoverage(ok({ detail: "No cached result yet." }), NOW).state).toBe("unavailable");
    expect(evaluateWinnerCoverage(ok(winnersPayload([])), NOW).state).toBe("unavailable");
  });
});

// ── 2. guess family ────────────────────────────────────────────────────────

describe("guess family — a stated contract blocker, not a substituted metric", () => {
  it("is unverified with no headline number, and names the four guess sources", () => {
    const t = evaluateGuessFamily(ok(winnersPayload([winnerSource()])), ok({ heuristic_filter: { excluded_by_source: { kalshi: 20392, polymarket: 33142 } }, generated_at: "2026-10-13T14:35:40Z" }));
    expect(t.state).toBe("unavailable");
    expect(t.headline).toBe("Not reported by any existing cached endpoint");
    expect(t.rows).toEqual([]);
    for (const s of ["pass2_guess", "binary_higher_wins", "multi_max_prob", "pass3_threshold"]) expect(t.method).toContain(s);
  });

  it("shows nearby counts only as related, uncoloured, and says the curve EXCLUDES them", () => {
    const t = evaluateGuessFamily(ok(winnersPayload([winnerSource()])), ok({ heuristic_filter: { excluded_by_source: { kalshi: 20392 } }, generated_at: "2026-10-13T14:35:40Z" }));
    const labels = (t.related ?? []).map((r) => r.label);
    expect(labels).toEqual(["kalshi — markets resolved by heuristic", "kalshi — outcomes held out of the published curve"]);
    expect((t.related ?? []).every((r) => r.state === "no_threshold")).toBe(true);
    expect(t.related?.[1].note).toContain("2026-10-13");
  });

  it("does not fabricate related rows when its inputs failed", () => {
    const t = evaluateGuessFamily({ status: "error", kind: "timeout", detail: "x", ms: 10_000 }, { status: "loading" });
    expect(t.related).toEqual([]);
    expect(t.state).toBe("unavailable");
  });
});

// ── 3. per-category MCE ────────────────────────────────────────────────────

describe("category MCE — red >10pp at N>100, green <3pp, amber between", () => {
  it.each([
    [2.99, 5000, "green"],
    [3, 5000, "amber"],
    [10, 5000, "amber"],
    [10.01, 101, "red"],
    [25, 100, "no_threshold"],
    [1, 0, "unavailable"],
  ] as const)("mce %p at N=%p is %p", (mce, n, state) => {
    expect(mceState(mce, n)).toBe(state);
  });

  it("grades a fresh curve and lists the worst category first", () => {
    const t = evaluateCategoryMce(ok({ ...freshEnvelope, generated_at: minutesAgo(10), by_category: [category("tennis", 1.3, 162848), category("hockey", 12.4, 5000), category("soccer", 4.1, 250323)] }));
    expect(t.state).toBe("red");
    expect(t.rows.map((r) => r.label)).toEqual(["hockey", "soccer", "tennis"]);
    expect(t.rows[0].note).toBe("N = 5,000");
  });

  it("never paints the saved stale Oct-13 curve green — it reads stale, with the server's reasons", () => {
    const t = evaluateCategoryMce(ok({ ...staleEnvelope, generated_at: "2026-10-13T14:35:40.360309+00:00", by_category: [category("tennis", 1.33, 162848), category("baseball", 1.35, 148520)] }));
    expect(t.state).toBe("stale");
    expect(t.lastVerdict).toBe("green");
    expect(t.headline).toContain("availability: stale");
    expect(t.headline).toContain("producer stalled, 149 beats missed");
  });

  it("requires positive proof: no envelope, or fresh with an unreported producer, is stale", () => {
    const body = { by_category: [category("tennis", 1, 5000)], generated_at: minutesAgo(5) };
    expect(evaluateCategoryMce(ok(body)).state).toBe("stale");
    expect(evaluateCategoryMce(ok({ ...body, availability: "fresh" })).state).toBe("stale");
    expect(evaluateCategoryMce(ok({ ...body, ...freshEnvelope })).state).toBe("green");
  });

  it("shows small categories but does not let them vote; nothing graded is no verdict", () => {
    const t = evaluateCategoryMce(ok({ ...freshEnvelope, by_category: [category("tiny", 30, 50)] }));
    expect(t.state).toBe("unavailable");
    expect(t.rows[0].note).toContain("not graded");
  });

  it("reads a category with no mce as unverified rather than 0pp", () => {
    const t = evaluateCategoryMce(ok({ ...freshEnvelope, by_category: [{ category: "x", n: 5000 }, category("y", 1, 5000)] }));
    expect(t.rows.find((r) => r.label === "x")?.value).toBe("—");
    expect(t.state).toBe("partial");
  });
});

// ── 4. source coverage ─────────────────────────────────────────────────────

describe("Tier-1 source coverage — every expected source on every event", () => {
  it("is green only when every expected Tier-1 cell is at 100%", () => {
    const t = evaluateSourceCoverage(ok(dashboardPayload(TIER1.map((s) => coverageRow(s, 40)))), NOW);
    expect(t.state).toBe("green");
    expect(t.rows).toHaveLength(20);
  });

  it("skips a source the row marks not expected, instead of counting it", () => {
    const rows = TIER1.map((s) => coverageRow(s, 40, s === "americanfootball_nfl" ? { statpal: 0 } : {}, s === "americanfootball_nfl" ? { odds_api: true, espn: true, statpal: false, kalshi: true, polymarket: true } : null));
    const t = evaluateSourceCoverage(ok(dashboardPayload(rows)), NOW);
    expect(t.state).toBe("green");
    expect(t.rows.some((r) => r.label === "NFL · StatPal")).toBe(false);
  });

  it("is red when Kalshi is on 33 of 40 MLB events", () => {
    const rows = TIER1.map((s) => coverageRow(s, 40, s === "baseball_mlb" ? { kalshi: 33 } : {}));
    const t = evaluateSourceCoverage(ok(dashboardPayload(rows)), NOW);
    expect(t.state).toBe("red");
    expect(t.rows[0]).toMatchObject({ label: "MLB · Kalshi", value: "82.5% (33/40)", state: "red" });
  });

  it("cannot be green when a Tier-1 sport is missing from the denominator", () => {
    const t = evaluateSourceCoverage(ok(dashboardPayload(TIER1.slice(1).map((s) => coverageRow(s, 40)))), NOW);
    expect(t.state).toBe("partial");
    expect(t.rows.find((r) => r.label === "NFL")?.state).toBe("unavailable");
  });

  it("reads the panel's error marker as unavailable, never as an empty list", () => {
    const t = evaluateSourceCoverage(ok(dashboardPayload([{ error: "canceling statement due to statement timeout" }])), NOW);
    expect(t.state).toBe("unavailable");
    expect(t.headline).toContain("query failed");
  });

  it("an empty list is nothing measured, not complete coverage", () => {
    expect(evaluateSourceCoverage(ok(dashboardPayload([])), NOW).state).toBe("unavailable");
  });
});

// ── 5. link rate ───────────────────────────────────────────────────────────

describe("link rate — Tier-1 open game markets, graded from counts", () => {
  it("is green when every venue × league is fully linked, with the overall rate shown uncoloured", () => {
    const t = evaluateLinkRate(ok(linkRatePayload()), NOW);
    expect(t.state).toBe("green");
    expect(t.related?.[0]).toMatchObject({ value: "90.0% (72/80)", state: "no_threshold" });
  });

  it("does not read the server's link_rate=0 over zero open markets as a failure", () => {
    const kalshi = T1_LEAGUES.map(([s, l]) => (l === "NFL" ? lrRow(s, l, 0, 0) : lrRow(s, l, 10, 10)));
    const t = evaluateLinkRate(ok(linkRatePayload({ kalshi })), NOW);
    expect(t.rows.find((r) => r.label === "Kalshi · NFL")).toMatchObject({ state: "unavailable", value: "no open markets" });
    expect(t.state).toBe("partial");
  });

  it("is red at 9 of 10, and matches league case-insensitively", () => {
    const polymarket = T1_LEAGUES.map(([s, l]) => (l === "NHL" ? lrRow(s, "nhl", 10, 9) : lrRow(s, l, 10, 10)));
    const t = evaluateLinkRate(ok(linkRatePayload({ polymarket })), NOW);
    expect(t.state).toBe("red");
    expect(t.rows[0]).toMatchObject({ label: "Polymarket · NHL", value: "90.0% (9/10)" });
  });

  it("never grades a snapshot the route itself marked stale", () => {
    const t = evaluateLinkRate(ok(linkRatePayload({ extra: { stale: true, stale_reason: "compute_timeout" } })), NOW);
    expect(t.state).toBe("stale");
    expect(t.headline).toContain("compute_timeout");
  });

  it("reads the route's no-snapshot degrade as unavailable", () => {
    const t = evaluateLinkRate(ok({ generated_at: minutesAgo(0), stale: true, unavailable: true, stale_reason: "compute_error", overall: {}, kalshi: {}, polymarket: {} }), NOW);
    expect(t.state).toBe("unavailable");
  });

  it("is stale past the cache TTL", () => {
    expect(evaluateLinkRate(ok(linkRatePayload({ generatedAt: minutesAgo(61) })), NOW).state).toBe("stale");
  });
});

// ── 6. grid health ─────────────────────────────────────────────────────────

describe("grid health — every grid at 100", () => {
  it("is green only when all four grids score 100", () => {
    expect(evaluateGridHealth(ok(gridsPayload(allGrids100)), NOW).state).toBe("green");
  });

  it("is red at 99", () => {
    const t = evaluateGridHealth(ok(gridsPayload({ ...allGrids100, mlb: { health_score: 99, findings: [{}, {}] } })), NOW);
    expect(t.state).toBe("red");
    expect(t.rows.find((r) => r.label === "MLB")).toMatchObject({ value: "99/100", note: "2 findings" });
  });

  it("an errored or missing grid blocks the all-clear", () => {
    const { golf: _g, ...three } = allGrids100;
    void _g;
    expect(evaluateGridHealth(ok(gridsPayload({ ...allGrids100, nhl: { status: "error", error: "No JSON" } })), NOW).state).toBe("partial");
    expect(evaluateGridHealth(ok(gridsPayload(three)), NOW).state).toBe("partial");
  });

  it("is stale past the cache TTL", () => {
    expect(evaluateGridHealth(ok(gridsPayload(allGrids100, minutesAgo(90))), NOW).state).toBe("stale");
  });
});

// ── reads: bounded, isolated, concurrent ───────────────────────────────────

describe("one bounded read per endpoint", () => {
  it.each([401, 403])("HTTP %i is unauthorized — a credential fact, not a data fact", async (status) => {
    const r = await boundedRead(async () => new Response("Invalid admin secret", { status }));
    expect(r).toMatchObject({ status: "error", kind: "unauthorized" });
    const t = evaluateGridHealth(r, NOW);
    expect(t.state).toBe("unauthorized");
    expect(t.headline).toContain("says nothing about the data");
  });

  it("HTTP 500 and an unparseable body are unavailable", async () => {
    expect(await boundedRead(async () => new Response("boom", { status: 500 }))).toMatchObject({ kind: "http", httpStatus: 500 });
    expect(await boundedRead(async () => new Response("not json", { status: 200 }))).toMatchObject({ kind: "parse" });
  });

  it("aborts at its timeout and reports timeout, not a network fault", async () => {
    const hang = (signal: AbortSignal) =>
      new Promise<Response>((_res, rej) => signal.addEventListener("abort", () => rej(new Error("aborted"))));
    const r = await boundedRead(hang, { timeoutMs: 20 });
    expect(r).toMatchObject({ status: "error", kind: "timeout" });
    expect(evaluateLinkRate(r, NOW).state).toBe("unavailable");
  });

  it("starts all five reads before any settles, and one failure does not hold the rest", async () => {
    const started: string[] = [];
    const settled: string[] = [];
    let releaseSlow: () => void = () => {};
    const slow = new Promise<void>((res) => (releaseSlow = res));
    const ms = startCorrectnessReads(
      (key) => async () => {
        started.push(key);
        if (key === "grids") throw new Error("network down");
        if (key === "dashboard") await slow;
        return new Response(JSON.stringify({ key }), { status: 200 });
      },
      (key) => settled.push(key),
    );
    await new Promise((r) => setTimeout(r, 5));
    expect(started.sort()).toEqual(Object.keys(CORRECTNESS_ENDPOINTS).sort());
    // Everything but the slow read has already reported, the failure included.
    expect(settled.sort()).toEqual(["calibration", "grids", "linkRate", "winners"]);
    releaseSlow();
    expect(typeof (await ms)).toBe("number");
    expect(settled).toContain("dashboard");
  });

  it("reports nothing after the page aborts (unmount / reload)", async () => {
    const ctrl = new AbortController();
    const seen: string[] = [];
    const p = startCorrectnessReads(() => async () => new Response("{}", { status: 200 }), (k) => seen.push(k), { signal: ctrl.signal });
    ctrl.abort();
    await p;
    expect(seen).toEqual([]);
  });
});

// ── the presentation clock (Root 002 on e603826e7f) ───────────────────────

describe("fetched evidence ages into stale in a tab left open — with no new request", () => {
  function fakeDoc() {
    const listeners = new Set<() => void>();
    const doc = {
      visibilityState: "visible" as DocumentVisibilityState,
      addEventListener: (_t: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_t: string, fn: () => void) => listeners.delete(fn),
      fire() {
        listeners.forEach((fn) => fn());
      },
      listeners,
    };
    return doc;
  }

  afterEach(() => jest.useRealTimers());

  it("turns a green winner tile stale after its TTL passes, judged on the ticking clock only", () => {
    jest.useFakeTimers();
    const fetchSpy = jest.fn();
    const realFetch = global.fetch;
    global.fetch = fetchSpy as unknown as typeof fetch;
    try {
      const loadedAt = NOW;
      // A snapshot 20 minutes old at load — green.
      const read = ok(winnersPayload([winnerSource()], minutesAgo(20)));
      let clock = loadedAt;
      let judged = evaluateWinnerCoverage(read, clock);
      expect(judged.state).toBe("green");
      const doc = fakeDoc();
      const base = jest.now();
      const stop = startUiClock(
        (t) => {
          clock = t;
          judged = evaluateWinnerCoverage(read, clock);
        },
        { doc: doc as unknown as Document, now: () => loadedAt + (jest.now() - base) },
      );
      // Still inside the two-beat TTL 99 minutes later (20 + 99 = 119 min old).
      jest.advanceTimersByTime(99 * 60_000);
      expect(judged.state).toBe("green");
      // Past it: the same fetched evidence is now stale, its verdict kept as history.
      jest.advanceTimersByTime(2 * 60_000);
      expect((clock - Date.parse(minutesAgo(20))) / 1000).toBeGreaterThan(WINNERS_STALE_AFTER_S);
      expect(judged).toMatchObject({ state: "stale", lastVerdict: "green" });
      // The source's own timestamp never moved; nothing was fetched.
      expect(judged.asOf).toBe(minutesAgo(20));
      expect(fetchSpy).not.toHaveBeenCalled();
      stop();
    } finally {
      global.fetch = realFetch;
    }
  });

  it("re-judges at once when the tab returns from the background, not at the next tick", () => {
    jest.useFakeTimers();
    const doc = fakeDoc();
    const ticks: number[] = [];
    let wall = NOW;
    const stop = startUiClock((t) => ticks.push(t), { doc: doc as unknown as Document, now: () => wall });
    wall = NOW + 3 * 3600_000; // hidden for three hours; throttled timers never fired
    doc.visibilityState = "hidden";
    doc.fire();
    expect(ticks).toEqual([]);
    doc.visibilityState = "visible";
    doc.fire();
    expect(ticks).toEqual([wall]);
    stop();
  });

  it("ticks on its interval and stops completely on unmount", () => {
    jest.useFakeTimers();
    const doc = fakeDoc();
    const ticks: number[] = [];
    const stop = startUiClock((t) => ticks.push(t), { doc: doc as unknown as Document });
    jest.advanceTimersByTime(UI_CLOCK_INTERVAL_MS * 3);
    expect(ticks).toHaveLength(3);
    stop();
    expect(doc.listeners.size).toBe(0);
    jest.advanceTimersByTime(UI_CLOCK_INTERVAL_MS * 10);
    doc.fire();
    expect(ticks).toHaveLength(3);
    expect(jest.getTimerCount()).toBe(0);
  });

  it("shows the reader the time the tiles were judged against", () => {
    const html = renderToStaticMarkup(
      <CorrectnessConsoleView tiles={evaluateAll(INITIAL_READS, NOW)} nowMs={NOW + 3 * 3600_000} settledMs={null} />,
    );
    expect(html).toContain('data-judged-at="2026-10-20T00:00:00.000Z"');
    expect(html).toContain("Judged against the clock at");
    expect(html).toContain("12:00:00 AM UTC");
  });
});

// ── the page as a whole ────────────────────────────────────────────────────

function healthyReads(): CorrectnessReads {
  return {
    winners: ok(winnersPayload([winnerSource()])),
    calibration: ok({ ...freshEnvelope, generated_at: minutesAgo(10), by_category: [category("tennis", 1.3, 5000)] }),
    dashboard: ok(dashboardPayload(TIER1.map((s) => coverageRow(s, 40)))),
    linkRate: ok(linkRatePayload()),
    grids: ok(gridsPayload(allGrids100)),
  };
}

describe("the header verdict", () => {
  it("is never 'good' while the guess-family tile cannot be read — five green is still a warning", () => {
    const tiles = evaluateAll(healthyReads(), NOW);
    expect(tiles.filter((t) => t.state === "green").map((t) => t.key)).toEqual(["winner_coverage", "category_mce", "source_coverage", "link_rate", "grid_health"]);
    expect(summarize(tiles)).toEqual({ status: "warning", summary: "5 of 6 green · 1 unverified" });
  });

  it("is critical on any red tile", () => {
    const reads = { ...healthyReads(), grids: ok(gridsPayload({ ...allGrids100, nba: { health_score: 90 } })) };
    expect(summarize(evaluateAll(reads, NOW)).status).toBe("critical");
  });

  it("is about the credential when every admin read was refused, even though the public curve answered", () => {
    const refused: ReadResult = { status: "error", kind: "unauthorized", detail: "HTTP 403", ms: 40, httpStatus: 403 };
    const reads = { ...healthyReads(), winners: refused, dashboard: refused, linkRate: refused, grids: refused };
    expect(summarize(evaluateAll(reads, NOW)).status).toBe("unauthorized");
  });

  it("is loading before anything settles", () => {
    expect(summarize(evaluateAll(INITIAL_READS, NOW)).status).toBe("loading");
  });

  it("folds states with red first and green only on all-green", () => {
    expect(foldStates(["green", "red", "unavailable"])).toBe("red");
    expect(foldStates(["green", "stale"])).toBe("partial");
    expect(foldStates(["stale"])).toBe("stale");
    expect(foldStates([])).toBe("unavailable");
    expect(foldStates(["green", "amber"])).toBe("amber");
  });
});

describe("what a reader sees", () => {
  const mixed: CorrectnessReads = {
    ...healthyReads(),
    calibration: ok({ ...staleEnvelope, generated_at: "2026-10-13T14:35:40Z", by_category: [category("tennis", 1.33, 162848)] }),
    grids: { status: "error", kind: "timeout", detail: "no answer within 10000 ms", ms: 10_000 },
  };
  const html = renderToStaticMarkup(
    <CorrectnessConsoleView tiles={evaluateAll(mixed, NOW)} nowMs={NOW} settledMs={10_012} />,
  );

  it("draws all six tiles, each with its state as a word and a data attribute", () => {
    for (const key of ["winner_coverage", "guess_family", "category_mce", "source_coverage", "link_rate", "grid_health"]) {
      expect(html).toContain(`data-tile="${key}"`);
    }
    expect(html).toContain('data-tile="category_mce" data-state="stale" data-last-verdict="green"');
    expect(html).toContain('data-tile="grid_health" data-state="unavailable"');
    expect(html).toContain("not a current verdict");
    expect(html).toContain("Unverified");
    expect(html).toContain("All reads settled in 10012 ms");
    expect(html).toContain('data-read-ms="120"');
  });

  it("shows a stale tile's row verdicts as history ('was …'), never as a live call", () => {
    const staleTile = html.slice(html.indexOf('data-tile="category_mce"'), html.indexOf('data-tile="source_coverage"'));
    expect(staleTile).toContain("was OK");
    expect(staleTile).not.toMatch(/>OK</);
    expect(staleTile).not.toContain("text-accent-live");
    // A current tile keeps its live badge.
    const freshTile = html.slice(html.indexOf('data-tile="winner_coverage"'), html.indexOf('data-tile="guess_family"'));
    expect(freshTile).toMatch(/>OK</);
  });

  it("keeps the header off green and names the stale curve's reasons", () => {
    expect(html).toContain('data-console-status="warning"');
    expect(html).toContain("producer stalled, 149 beats missed");
  });

  it("is single-column at phone width, wraps long text and labels each tile", () => {
    expect(html).toContain("grid grid-cols-1 lg:grid-cols-2");
    expect(html).toContain("min-w-0");
    expect(html).toContain("break-words");
    expect(html).toMatch(/<section aria-labelledby="correctness-winner_coverage"/);
    expect(html).toContain('id="correctness-winner_coverage"');
  });

  it("uses design tokens only — no raw colour classes, no hex", () => {
    expect(html).not.toMatch(/(?:text|bg|border)-(?:red|green|yellow|gray|slate|zinc)-\d/);
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}\b/);
  });

  it("never says 'books' or 'bookmakers' (notice 33)", () => {
    expect(html).not.toMatch(/\bbook(s|maker|makers)\b/i);
  });
});

// ── source guards on the page itself ───────────────────────────────────────

describe("the page's own contract", () => {
  const root = path.join(__dirname, "..");
  // Code only: the files' comments legitimately NAME what they refuse to do.
  const code = (rel: string) =>
    fs
      .readFileSync(path.join(root, rel), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  const page = code("app/admin/correctness/page.tsx");
  const lib = code("lib/correctnessConsole.ts");

  it("calls the three GA4 hooks before any return", () => {
    const body = page.slice(page.indexOf("export default function"));
    const firstReturn = body.indexOf("return");
    for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
      const at = body.indexOf(hook);
      expect(at).toBeGreaterThan(-1);
      expect(at).toBeLessThan(firstReturn);
    }
  });

  it("sends the admin credential as a header, never in a query string", () => {
    expect(page).toContain("adminFetch(path, secret");
    expect(page + lib).not.toMatch(/[?&]secret=/);
  });

  it("reads existing endpoints plainly: no bust/force/inline, no polling, no retries", () => {
    for (const p of Object.values(CORRECTNESS_ENDPOINTS)) expect(p).not.toContain("?");
    expect(page + lib).not.toMatch(/bust|force=|inline=|refreshInterval|maxRetries/);
    expect(page).not.toMatch(/method:\s*["']POST/);
    // The ONE timer is the presentation clock, which the tests below prove
    // issues no request; the page itself owns none.
    expect(page).not.toContain("setInterval");
    expect(lib.match(/setInterval\(/g)).toHaveLength(1);
    const clock = lib.slice(lib.indexOf("export function startUiClock"));
    expect(clock.slice(0, clock.indexOf("\n}\n"))).toContain("setInterval(");
    expect(page).toMatch(/useEffect\(\(\) => startUiClock\(setNowMs\), \[\]\)/);
  });

  it("keeps the public calibration read free of the admin credential", () => {
    expect(ADMIN_READS.has("calibration")).toBe(false);
    expect([...ADMIN_READS].sort()).toEqual(["dashboard", "grids", "linkRate", "winners"]);
  });

  it("is reachable from the admin sidebar", () => {
    const sidebar = fs.readFileSync(path.join(root, "components/admin/AdminSidebar.tsx"), "utf8");
    expect(sidebar).toContain('href: "/admin/correctness"');
  });
});
