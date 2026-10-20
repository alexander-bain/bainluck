// #847 — THE CORRECTNESS CONSOLE ANSWERS "CAN WE TRUST OUR NUMBERS TODAY?"
// WITHOUT EVER TURNING AN UNREAD NUMBER GREEN.
//
// The page composes six existing endpoints into seven tiles. What these tests
// pin, metric by metric:
//   - units, denominator and the CITED threshold that colours each tile;
//   - zero versus missing: a count that is absent is unverified, a real zero
//     is a real zero, and a rate the server computes as 0 over an empty
//     denominator is NOT a failure;
//   - stale, partial, wrong-shape and failed reads are unverified, never green,
//     and a red seen in stale data is reported as stale-with-last-verdict;
//   - one failing read never blanks or holds its siblings (all six start at
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

import CorrectnessConsoleView, { CorrectnessTileCard } from "@/components/admin/CorrectnessConsole";
import { SENTINELS, SILENCE_MULTIPLIER } from "@/components/admin/SentinelsCard";
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
  evaluateSnapshotSparsity,
  evaluateSourceCoverage,
  evaluateWinnerCoverage,
  foldStates,
  GRID_SENTINEL_STALE_AFTER_S,
  mceState,
  SNAPSHOT_DIST_RETENTION_S,
  SOURCE_CLOCK_SKEW_S,
  startCorrectnessReads,
  startUiClock,
  summarize,
  TIER1_COVERAGE_SPORTS,
  UI_CLOCK_INTERVAL_MS,
  WINNERS_STALE_AFTER_S,
  type CorrectnessReads,
  type CorrectnessTile,
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

// The saved-only coverage route (`GET /api/admin/event-source-coverage/cached`,
// backend PR #11309, implementation c8d1cde5ca): fixtures mirror
// `tests/test_admin_event_source_coverage_cache.py` `_row`/`_last_good`/`_envelope`
// and the body `_coverage_response` builds, including its `tier1[]` projection
// over `admin_dashboard._TIER1_SPORTS`.
const COV_SOURCE_KEYS = ["odds_api", "espn", "statpal", "espn_wp", "model", "mlb", "kalshi", "polymarket"] as const;
const TIER1_SPORTS = ["basketball_nba", "americanfootball_nfl", "icehockey_nhl", "baseball_mlb", "basketball_ncaab", "golf_pga"];
type CovRow = Record<string, unknown> & { sport: string; total: number; expected_sources: Record<string, boolean> };

function coverageRow(sport: string, total: number, counts: Partial<Record<string, number>> = {}, expected: Partial<Record<string, boolean>> = {}): CovRow {
  const row: CovRow = { sport, total, live: 0, expected_sources: { ...Object.fromEntries(COV_SOURCE_KEYS.map((k) => [k, k !== "mlb"])), ...expected } as Record<string, boolean> };
  for (const k of COV_SOURCE_KEYS) row[k] = k === "mlb" ? 0 : total;
  return { ...row, ...counts };
}
function tier1Projection(rows: CovRow[] | null) {
  return TIER1_SPORTS.map((sport) => {
    const row = rows?.find((r) => r.sport === sport);
    if (!rows || !row) {
      return { sport, row_state: rows ? "no_in_window_events" : "missing_evidence", denominator: null, sources: null, health_verdict: "unverified" };
    }
    return {
      sport,
      row_state: "observed",
      denominator: row.total,
      sources: Object.fromEntries(
        COV_SOURCE_KEYS.map((k) => [k, { count: row[k], expected: row.expected_sources[k], share: (row[k] as number) / row.total }]),
      ),
      health_verdict: "unverified",
    };
  });
}
const ALL_TIER1_ROWS = () => TIER1_SPORTS.map((s) => coverageRow(s, 40));
function coverageLastGood(obsMinutesAgo: number, rows: CovRow[], over: Record<string, unknown> = {}) {
  const obs = NOW - obsMinutesAgo * 60_000;
  const iso = (ms: number) => new Date(ms).toISOString();
  return {
    complete: true,
    rows,
    unit: "events",
    rows_scope: "all sports returned by the accepted helper",
    observation_started_at: iso(obs),
    observation_finished_at: iso(obs + 1000),
    computed_at: iso(obs + 2000),
    published_at: iso(obs + 3000),
    window: {
      window_anchor: iso(obs),
      window_start: iso(obs - 7 * 86_400_000),
      window_end: iso(obs + 2 * 86_400_000),
      database_timezone: "UTC",
      transaction_isolation: "read committed",
      start_inclusive: true,
      end_inclusive: true,
    },
    source_provenance: {
      accepted_semantic_reference: "9ec74723560809a09674872b534376cca72d0a41",
      reference_is_production_adoption: false,
      executing_source_revision: "a".repeat(40),
      executing_release_version: "v5805",
      provenance_status: "deployment_reported",
      helper_file_sha256: "b".repeat(64),
      sql_literal_sha256: "c".repeat(64),
      expected_source_mapping_sha256: "d".repeat(64),
      source_last_updated_at: null,
      source_last_updated_status: "not_supplied_by_helper",
    },
    fresh_for_seconds: 1800,
    freshness_policy_status: "approved",
    retained_until: iso(obs + 3_600_000),
    ...over,
  };
}
const okAttempt = (lg: ReturnType<typeof coverageLastGood>) => ({ outcome: "ok", started_at: lg.observation_started_at, finished_at: lg.published_at, error: null });
function coverageBody(cacheState: string, freshness: string, reason: string, extra: Record<string, unknown> = {}) {
  const lastGood = (extra.last_good as ReturnType<typeof coverageLastGood> | undefined) ?? null;
  return {
    schema_version: 1,
    cache_state: cacheState,
    freshness,
    reason,
    producer_error: null,
    age_seconds: null,
    fresh_until: null,
    retained_until: null,
    expired_observation: null,
    last_good: null,
    latest_attempt: null,
    tier1: tier1Projection(lastGood ? (lastGood.rows as CovRow[]) : null),
    accepted_semantic_reference: "9ec74723560809a09674872b534376cca72d0a41",
    ...extra,
  };
}
/** A 200 hit, as the route answers for an approved, deployment-reported observation. */
function coverageHit(opts: { rows?: CovRow[]; obsMinutesAgo?: number; freshness?: string; reason?: string; lastGood?: Record<string, unknown>; extra?: Record<string, unknown> } = {}) {
  const obsMinutesAgo = opts.obsMinutesAgo ?? 5;
  const lg = coverageLastGood(obsMinutesAgo, opts.rows ?? ALL_TIER1_ROWS(), opts.lastGood);
  const freshness = opts.freshness ?? (obsMinutesAgo * 60 < 1800 ? "fresh" : "stale");
  const approved = freshness !== "unknown";
  return coverageBody("hit", freshness, opts.reason ?? (freshness === "fresh" ? "observed" : "observation_older_than_horizon"), {
    latest_attempt: okAttempt(lg),
    age_seconds: obsMinutesAgo * 60,
    fresh_until: approved ? new Date(Date.parse(lg.observation_started_at) + 1_800_000).toISOString() : null,
    retained_until: lg.retained_until,
    last_good: lg,
    ...opts.extra,
  });
}

/** Exactly what `boundedRead` returns for a saved-contract answer of this status. */
function saved(httpStatus: number, body: unknown): ReadResult {
  if (httpStatus === 200) return { status: "ok", data: body, ms: 120, httpStatus };
  if (httpStatus === 202) return { status: "error", kind: "pending", detail: "HTTP 202 — no cached result yet", ms: 120, httpStatus, body };
  return { status: "error", kind: "http", detail: `HTTP ${httpStatus}`, ms: 120, httpStatus, body };
}

// The saved-only link-rate route (`GET /api/admin/prediction-markets/link-rate/cached`,
// backend PR #11313, implementation 94f8fb578a): `payload` is the shape
// `_compute_link_rate` writes; the envelope is `_link_rate_cached_response`.
function lrRow(sport: string, league: string, open: number, linked: number) {
  return { sport, league, total: open, linked, open_total: open, open_linked: linked, link_rate: open ? (100 * linked) / open : 0, link_rate_all: open ? (100 * linked) / open : 0 };
}
const T1_LEAGUES: [string, string][] = [["football", "NFL"], ["basketball", "NBA"], ["baseball", "MLB"], ["hockey", "NHL"]];
const lrTotals = (n: number) => ({ total: n, linked: n, open_total: n, open_linked: n, link_rate_pct: 100, link_rate_all_pct: 100 });
function linkRatePayload(over: { kalshi?: unknown[]; polymarket?: unknown[]; extra?: Record<string, unknown>; generatedAt?: string } = {}) {
  const full = T1_LEAGUES.map(([s, l]) => lrRow(s, l, 10, 10));
  return {
    generated_at: over.generatedAt ?? minutesAgo(10),
    overall: { total_game_markets: 90, linked: 80, open_total: 80, open_linked: 72, link_rate_pct: 90, link_rate_all_pct: 88.9, link_rate_raw_pct: 85.2, excluded_open_upstream_coverage_gap: 6, denominator_note: "Headline rate uses open markets only." },
    kalshi: { totals: lrTotals(40), by_sport: over.kalshi ?? full },
    polymarket: { totals: lrTotals(40), by_sport: over.polymarket ?? full },
    ...over.extra,
  };
}
function linkRateBody(cacheState: string, reason: string, payload: Record<string, unknown> | null = null, freshness = "unknown") {
  const generatedAt = payload ? (payload.generated_at as string) : null;
  return {
    schema_version: 1,
    cache_state: cacheState,
    reason,
    freshness,
    freshness_basis: "age_from_generated_at_stamped_when_compute_returned",
    generated_at: generatedAt,
    age_seconds: generatedAt ? (NOW - Date.parse(generatedAt)) / 1000 : null,
    payload,
  };
}
/** A 200 hit: the route reports `freshness: "unreviewed"` for every ordinary hit. */
const linkRateHit = (payload: Record<string, unknown> = linkRatePayload()) =>
  saved(200, linkRateBody("hit", payload.stale === true ? "saved_snapshot_marked_stale" : "saved_snapshot", payload, "unreviewed"));

// The Grid Sentinel's saved run, in the shape `_run_grid_sentinel` persists
// (`tasks/grid_sentinel.py`): scorecard.per_league[] carries each league's own
// verdict and its REAL / EXPLAINED / WATCH counts.
function league(name: string, over: Record<string, unknown> = {}) {
  return {
    league: name,
    verdict: "green",
    checks_skipped: [],
    phase: "regular",
    real_defects: 0,
    explained_artifacts: 0,
    watch: 0,
    teams: 30,
    columns: ["make_playoffs", "win_title"],
    cells_self_checked: 60,
    ...over,
  };
}
function sentinelPayload(
  perLeague: unknown[] = ["mlb", "nba", "nhl"].map((l) => league(l)),
  over: Record<string, unknown> = {},
) {
  const per = perLeague as Record<string, unknown>[];
  return {
    mode: "live",
    leagues: [],
    filed: [],
    errors: [],
    scorecard: {
      leagues_total: per.length,
      leagues_red: per.filter((l) => l.verdict === "red").length,
      leagues_green: per.filter((l) => l.verdict === "green").length,
      leagues_unverified: per.filter((l) => l.verdict === "green_unverified").length,
      per_league: per,
    },
    duration_seconds: 41.2,
    generated_at: minutesAgo(60),
    ...over,
  };
}
const gridRow = (t: CorrectnessTile, label: string) => t.rows.find((r) => r.label === label);

// The saved snapshot distribution, in the shape `compute_snapshot_distribution_impl`
// writes (`tasks/monitoring.py`): per source, six buckets partitioning
// `sampled_outcomes` (outcomes of the 200 most-recent open/active markets),
// `total_outcomes` over every open/active market of that source, and
// `sparse_pct` = round(100 * (zero + 1..5) / sampled, 1).
function snapSource(over: Record<string, unknown> = {}) {
  // 412 = 12 + 40 + 100 + 120 + 90 + 50; sparse 52 → 12.62% → 12.6
  return {
    source: "kalshi",
    total_outcomes: 9000,
    sampled_outcomes: 412,
    zero_snapshots: 12,
    "1_to_5": 40,
    "6_to_20": 100,
    "21_to_50": 120,
    "51_to_100": 90,
    "100_plus": 50,
    avg_snapshots: 38.4,
    median_snapshots: 31,
    sparse_pct: 12.6,
    ...over,
  };
}
// 600 = 300 + 150 + 100 + 30 + 15 + 5; sparse 450 → 75.0
const polySnap = (over: Record<string, unknown> = {}) =>
  snapSource({ source: "polymarket", total_outcomes: 3000, sampled_outcomes: 600, zero_snapshots: 300, "1_to_5": 150, "6_to_20": 100, "21_to_50": 30, "51_to_100": 15, "100_plus": 5, avg_snapshots: 4.9, median_snapshots: 0.5, sparse_pct: 75, ...over });
/** Every sampled outcome has 6+ snapshots: a real measured 0%. */
const zeroSparse = () =>
  snapSource({ source: "odds_api", total_outcomes: 500, sampled_outcomes: 200, zero_snapshots: 0, "1_to_5": 0, "6_to_20": 50, "21_to_50": 50, "51_to_100": 50, "100_plus": 50, avg_snapshots: 60.2, median_snapshots: 50.5, sparse_pct: 0 });
/** Every sampled outcome has no snapshot at all: a real measured 100%. */
const allSparse = () =>
  snapSource({ source: "odds_api", total_outcomes: 80, sampled_outcomes: 80, zero_snapshots: 80, "1_to_5": 0, "6_to_20": 0, "21_to_50": 0, "51_to_100": 0, "100_plus": 0, avg_snapshots: 0, median_snapshots: 0, sparse_pct: 100 });
function snapPayload(sources: unknown[] = [snapSource(), polySnap()], computedAt: unknown = minutesAgo(90)) {
  return { computed_at: computedAt, method: "200 most-recent markets per source (open/active only)", sources };
}
const snapRow = (t: CorrectnessTile, label: string) => t.rows.find((r) => r.label === label);
const SNAP_MISS_DETAIL = "No cached result. POST /api/admin/snapshots/distribution to compute.";

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

// Root's da9c review (024): the SAME healthy winners answer, read on a tab whose
// clock is behind its computed_at. `ageSeconds` clamps that to 0, so the TTL
// test alone called it current. Every case below changes one thing from the
// ordinary-clock control.
describe("winner coverage — no all-clear without a local age", () => {
  const healthy = () => winnersPayload([winnerSource()]);
  const computed = (body: ReturnType<typeof winnersPayload>) => Date.parse(body.computed_at as string);
  const winnerCard = (html: string) => {
    const start = html.indexOf('data-tile="winner_coverage"');
    return html.slice(start, html.indexOf("</section>", start));
  };

  it("the healthy answer is green and current on an ordinary clock (the control)", () => {
    const t = evaluateWinnerCoverage(ok(healthy()), NOW);
    expect(t).toMatchObject({ state: "green", headline: "Every source covered (1 sources)", asOf: minutesAgo(20) });
    expect(t.lastVerdict).toBeUndefined();
    expect(summarize([t]).status).toBe("good");
  });

  it("keeps the same answer as graded history, not current, when this tab's clock is ten minutes before computed_at", () => {
    const body = healthy();
    const control = evaluateWinnerCoverage(ok(body), NOW);
    const t = evaluateWinnerCoverage(ok(body), computed(body) - 10 * 60_000);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "green" });
    expect(t.headline).toBe(
      "Freshness unknown — it was computed more than 5 min ahead of this browser's clock. Last read: Every source covered (1 sources)",
    );
    // The producer's own time, the rows and their denominators and heuristic
    // disclosure are kept exactly; nothing is re-stamped or dropped.
    expect(t.asOf).toBe(body.computed_at);
    expect(t.rows).toEqual(control.rows);
    expect(t.rows[0]).toMatchObject({ value: "100.0% (900/900)", note: "0 with no resolution · 20 resolved by heuristic, not authority" });
    expect(summarize([t]).status).toBe("warning");
  });

  it("uses the existing 300 s skew tolerance: exactly at it is current, one ms past it is not", () => {
    const body = healthy();
    expect(SOURCE_CLOCK_SKEW_S).toBe(300);
    expect(evaluateWinnerCoverage(ok(body), computed(body) - SOURCE_CLOCK_SKEW_S * 1000).state).toBe("green");
    expect(evaluateWinnerCoverage(ok(body), computed(body) - SOURCE_CLOCK_SKEW_S * 1000 - 1)).toMatchObject({
      state: "freshness_unknown",
      lastVerdict: "green",
    });
  });

  it("keeps a red gap in future-stamped data as its last verdict — never dropped, never current", () => {
    const body = winnersPayload([winnerSource({ has_winner: 849, needs_backfill: 1 })]);
    const t = evaluateWinnerCoverage(ok(body), computed(body) - 10 * 60_000);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "red" });
    expect(t.headline).toBe(
      "Freshness unknown — it was computed more than 5 min ahead of this browser's clock. Last read: 1 of 1 sources have markets with no resolution",
    );
    expect(t.rows[0]).toMatchObject({ state: "red", value: "99.9% (899/900)", note: "1 with no resolution · 20 resolved by heuristic, not authority" });
    const html = renderToStaticMarkup(<CorrectnessTileCard tile={t} nowMs={computed(body) - 10 * 60_000} />);
    expect(html).toContain('data-last-verdict="red"');
    expect(html).toContain("The data read");
    expect(html).toContain("— not a current verdict.");
  });

  it("leaves the genuine stale, undated and unparseable cases as they were (stale, verdict kept)", () => {
    const at = (iso: unknown) => evaluateWinnerCoverage(ok({ sources: [winnerSource()], computed_at: iso }), NOW);
    // The 7200 s horizon is unchanged: at it, current; one second past, stale.
    expect(at(new Date(NOW - WINNERS_STALE_AFTER_S * 1000).toISOString()).state).toBe("green");
    expect(at(new Date(NOW - WINNERS_STALE_AFTER_S * 1000 - 1000).toISOString())).toMatchObject({ state: "stale", lastVerdict: "green" });
    expect(at(null)).toMatchObject({ state: "stale", lastVerdict: "green", asOf: null });
    // An unparseable time is shown as sent, never normalised into a date.
    expect(at("not-a-time")).toMatchObject({ state: "stale", lastVerdict: "green", asOf: "not-a-time" });
    expect(at(1760907600)).toMatchObject({ state: "stale", asOf: null });
  });

  it("does not turn an unknown or failed read into a clock verdict", () => {
    const behind = computed(healthy()) - 10 * 60_000;
    const refused: ReadResult = { status: "error", kind: "unauthorized", detail: "HTTP 403", ms: 40, httpStatus: 403 };
    const pending: ReadResult = { status: "error", kind: "pending", detail: "HTTP 202", ms: 40, httpStatus: 202 };
    expect(evaluateWinnerCoverage(refused, behind).state).toBe("unauthorized");
    expect(evaluateWinnerCoverage(pending, behind).state).toBe("unavailable");
    expect(evaluateWinnerCoverage({ status: "loading" }, behind).state).toBe("loading");
    expect(evaluateWinnerCoverage(ok({ sources: [{ source: "kalshi", resolved: "lots" }], computed_at: healthy().computed_at }), behind)).toMatchObject({
      state: "freshness_unknown",
      lastVerdict: "unavailable",
    });
  });

  it("an open tab whose clock moves behind computed_at and back re-judges on its ticks alone — no new request", () => {
    jest.useFakeTimers();
    const fetchSpy = jest.fn();
    const realFetch = global.fetch;
    global.fetch = fetchSpy as unknown as typeof fetch;
    try {
      const body = healthy();
      const read = ok(body);
      let wall = NOW;
      let judged = evaluateWinnerCoverage(read, wall);
      expect(judged.state).toBe("green");
      const stop = startUiClock(
        (t) => {
          judged = evaluateWinnerCoverage(read, t);
        },
        { doc: null, now: () => wall },
      );
      wall = computed(body) - 10 * 60_000; // the device clock is set back
      jest.advanceTimersByTime(UI_CLOCK_INTERVAL_MS);
      expect(judged).toMatchObject({ state: "freshness_unknown", lastVerdict: "green", asOf: body.computed_at });
      wall = NOW; // and corrected
      jest.advanceTimersByTime(UI_CLOCK_INTERVAL_MS);
      expect(judged).toMatchObject({ state: "green", asOf: body.computed_at });
      expect(judged.lastVerdict).toBeUndefined();
      expect(fetchSpy).not.toHaveBeenCalled();
      stop();
    } finally {
      global.fetch = realFetch;
      jest.useRealTimers();
    }
  });

  it("what a reader sees: the same page, tab clock behind, shows the winner card as history with no invented age", () => {
    const reads = healthyReads();
    const body = (reads.winners as { data: ReturnType<typeof winnersPayload> }).data;
    const behind = computed(body) - 10 * 60_000;
    const normal = winnerCard(renderToStaticMarkup(<CorrectnessConsoleView tiles={evaluateAll(reads, NOW)} nowMs={NOW} settledMs={10} />));
    expect(normal).toContain('data-state="green"');
    expect(normal).toContain("built 20 min ago");

    const card = winnerCard(renderToStaticMarkup(<CorrectnessConsoleView tiles={evaluateAll(reads, behind)} nowMs={behind} settledMs={10} />));
    expect(card).toContain('data-state="freshness_unknown"');
    expect(card).toContain('data-last-verdict="green"');
    expect(card).toContain(`data-as-of="${body.computed_at}"`);
    expect(card).toContain("Freshness unknown — it was computed more than 5 min ahead of this browser&#x27;s clock.");
    expect(card).toContain("built ahead of this browser&#x27;s clock");
    expect(card).not.toContain("built 0s ago");
    expect(card).toContain("100.0% (900/900)");
  });

  it("the header: a winners answer stamped past the tolerance stops counting as green, everything else unchanged", () => {
    const normalReads = healthyReads();
    const aheadReads = { ...normalReads, winners: ok(winnersPayload([winnerSource()], new Date(NOW + 10 * 60_000).toISOString())) };
    const normalTiles = evaluateAll(normalReads, NOW);
    const aheadTiles = evaluateAll(aheadReads, NOW);
    expect(normalTiles.filter((t) => t.state === "green").map((t) => t.key)).toEqual(["winner_coverage", "category_mce", "source_coverage"]);
    expect(aheadTiles.filter((t) => t.state === "green").map((t) => t.key)).toEqual(["category_mce", "source_coverage"]);
    expect(aheadTiles.filter((t) => t.key !== "winner_coverage")).toEqual(normalTiles.filter((t) => t.key !== "winner_coverage"));
    expect(summarize(normalTiles).summary).toBe("3 of 7 green · 4 unverified");
    expect(summarize(aheadTiles)).toEqual({ status: "warning", summary: "2 of 7 green · 5 unverified" });
    const html = renderToStaticMarkup(<CorrectnessConsoleView tiles={aheadTiles} nowMs={NOW} settledMs={10} />);
    expect(html).toContain("2 of 7 green · 5 unverified");
    expect(winnerCard(html)).toContain('data-state="freshness_unknown"');
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

// ── 4. source coverage (saved-only contract) ───────────────────────────────

describe("Tier-1 source coverage — from the saved observation only", () => {
  it("is green only when every expected Tier-1 cell is at 100%, aged from the OBSERVATION", () => {
    const body = coverageHit({ obsMinutesAgo: 5 });
    const t = evaluateSourceCoverage(saved(200, body), NOW);
    expect(t.state).toBe("green");
    // Six Tier-1 sports (Golf and NCAAB included) × five /health §G sources.
    expect(t.rows).toHaveLength(30);
    expect(t.rows.some((r) => r.label === "PGA Golf · ESPN")).toBe(true);
    expect(t.asOf).toBe((body.last_good as unknown as { observation_started_at: string }).observation_started_at);
    expect(t.evidence).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Window: events commencing"),
        "Produced by release v5805 at aaaaaaaaaa",
        expect.stringContaining("Fresh until"),
        expect.stringContaining("Kept until"),
      ]),
    );
  });

  it("is red when Kalshi is on 33 of 40 MLB events, from counts over that sport's own denominator", () => {
    const rows = ALL_TIER1_ROWS().map((r) => (r.sport === "baseball_mlb" ? coverageRow("baseball_mlb", 40, { kalshi: 33 }) : r));
    const t = evaluateSourceCoverage(saved(200, coverageHit({ rows })), NOW);
    expect(t.state).toBe("red");
    expect(t.rows[0]).toMatchObject({ label: "MLB · Kalshi", value: "82.5% (33/40)", state: "red" });
  });

  it("skips a source the row marks not expected, instead of counting it", () => {
    const rows = ALL_TIER1_ROWS().map((r) => (r.sport === "golf_pga" ? coverageRow("golf_pga", 12, { kalshi: 0 }, { kalshi: false }) : r));
    const t = evaluateSourceCoverage(saved(200, coverageHit({ rows })), NOW);
    expect(t.state).toBe("green");
    expect(t.rows.some((r) => r.label === "PGA Golf · Kalshi")).toBe(false);
  });

  it("keeps a Tier-1 sport with no events in the window on the tile, unmeasured — never a zero, never green", () => {
    const rows = ALL_TIER1_ROWS().filter((r) => r.sport !== "golf_pga");
    const t = evaluateSourceCoverage(saved(200, coverageHit({ rows })), NOW);
    expect(t.state).toBe("partial");
    expect(t.rows.find((r) => r.label === "PGA Golf")).toMatchObject({ value: "no events in window", state: "unavailable" });
  });

  it("ages into stale on this tab's clock at the saved fresh_until — no new request", () => {
    const body = coverageHit({ obsMinutesAgo: 25 });
    expect(evaluateSourceCoverage(saved(200, body), NOW).state).toBe("green");
    const later = evaluateSourceCoverage(saved(200, body), NOW + 5 * 60_000);
    expect(later).toMatchObject({ state: "stale", lastVerdict: "green" });
    expect(later.headline).toContain("30-min horizon");
  });

  it("reads the server's stale verdict as stale, keeping what the data said", () => {
    const rows = ALL_TIER1_ROWS().map((r) => (r.sport === "icehockey_nhl" ? coverageRow("icehockey_nhl", 40, { espn: 39 }) : r));
    const t = evaluateSourceCoverage(saved(200, coverageHit({ rows, obsMinutesAgo: 45 })), NOW);
    expect(t).toMatchObject({ state: "stale", lastVerdict: "red" });
  });

  it.each([
    ["freshness_policy_unreviewed", { fresh_for_seconds: null, freshness_policy_status: "unreviewed" }, "no reviewed freshness horizon"],
    ["source_identity_unknown", {}, "release that produced it is unknown"],
    ["observation_clock_in_future", {}, "observation time is in the future"],
  ])("never calls %s evidence current, however recent the read", (reason, lastGood, why) => {
    const t = evaluateSourceCoverage(saved(200, coverageHit({ freshness: "unknown", reason, lastGood })), NOW);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "green" });
    expect(t.headline).toContain(why);
  });

  it("shows a failed latest attempt beside the retained observation, without letting it refresh the evidence", () => {
    const body = coverageHit({ reason: "latest_attempt_failed", extra: { producer_error: { kind: "statement_timeout", code: "query_canceled" } } });
    const t = evaluateSourceCoverage(saved(200, body), NOW);
    expect(t.asOf).toBe((body.last_good as unknown as { observation_started_at: string }).observation_started_at);
    expect(t.evidence).toContain("Latest producer attempt failed: statement_timeout/query_canceled — the retained observation is shown");
  });

  it.each([
    [202, coverageBody("miss", "unknown", "no_cached_observation"), "nothing is saved yet", "no_cached_observation"],
    [503, coverageBody("error", "unknown", "read_deadline_exceeded"), "could not be read", "read_deadline_exceeded"],
    [503, coverageBody("malformed", "unknown", "count_exceeds_total"), "refused as malformed", "count_exceeds_total"],
    [503, coverageBody("partial", "unknown", "supplied_unknown"), "refused as incomplete", "supplied_unknown"],
    [
      503,
      coverageBody("producer_error", "unknown", "producer_failed_without_evidence", { producer_error: { kind: "statement_timeout", code: "query_canceled" } }),
      "producer failed and nothing earlier is saved",
      "statement_timeout/query_canceled",
    ],
  ])("HTTP %i keeps its own reason: %j", (status, body, words, reason) => {
    const t = evaluateSourceCoverage(saved(status, body), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [], asOf: null });
    expect(t.headline).toContain(words);
    expect(t.headline).toContain(reason);
  });

  it("reads an expired observation as unavailable and says when it was observed", () => {
    const body = coverageBody("expired", "unknown", "retained_evidence_expired", {
      retained_until: minutesAgo(10),
      expired_observation: { observation_started_at: minutesAgo(70), retained_until: minutesAgo(10) },
    });
    const t = evaluateSourceCoverage(saved(202, body), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [] });
    expect(t.headline).toContain("past its retention");
    expect(t.evidence?.[0]).toContain(minutesAgo(70));
  });

  it.each([
    ["a hit sent as 503", 503, coverageHit()],
    ["a miss sent as 200", 200, coverageBody("miss", "unknown", "no_cached_observation")],
    ["a hit without its observation", 200, coverageHit({ extra: { last_good: null } })],
    ["a hit with no tier1[]", 200, coverageHit({ extra: { tier1: null } })],
    ["an unknown schema version", 200, { ...coverageHit(), schema_version: 2 }],
    ["an unknown freshness word", 200, coverageHit({ freshness: "fresh-ish" })],
  ])("refuses %s as a wrong shape, never as data", (_label, status, body) => {
    const t = evaluateSourceCoverage(saved(status, body), NOW);
    expect(t.state).toBe("unavailable");
    expect(t.rows).toEqual([]);
  });

  it.each([
    ["a count above its denominator", { count: 41, expected: true, share: 1.025 }],
    ["a fractional count", { count: 39.5, expected: true, share: 0.9875 }],
    ["a missing expected flag", { count: 40, share: 1 }],
  ])("refuses the whole projection on %s", (_label, cell) => {
    const body = coverageHit();
    const nba = (body.tier1 as { sources: Record<string, unknown> }[])[0];
    nba.sources = { ...nba.sources, espn: cell };
    expect(evaluateSourceCoverage(saved(200, body), NOW)).toMatchObject({ state: "unavailable", rows: [] });
  });

  it("a 503 without the contract's body is a plain failed read", () => {
    const t = evaluateSourceCoverage({ status: "error", kind: "http", detail: "HTTP 503", ms: 30, httpStatus: 503 }, NOW);
    expect(t).toMatchObject({ state: "unavailable", headline: "Unavailable — HTTP 503" });
  });
});

// Root's 502f review: the SAME complete fresh answer, read on a tab whose clock is
// behind the observation, and projections that drop or repeat a roster member.
describe("Tier-1 source coverage — no all-clear without a local age or the whole roster", () => {
  const obsStart = (body: ReturnType<typeof coverageHit>) => Date.parse((body.last_good as unknown as { observation_started_at: string }).observation_started_at);
  const tier1Of = (body: ReturnType<typeof coverageHit>) => body.tier1 as { sport: string }[];

  it("the complete fresh answer is green on an ordinary clock (the control every case below changes one thing in)", () => {
    const t = evaluateSourceCoverage(saved(200, coverageHit()), NOW);
    expect(t).toMatchObject({ state: "green", headline: "Every expected Tier-1 source on every event" });
    expect(t.rows).toHaveLength(30);
  });

  it("keeps the same answer as graded history, not current, when this tab's clock is ten minutes before the observation", () => {
    const body = coverageHit();
    const clock = obsStart(body) - 10 * 60_000;
    const t = evaluateSourceCoverage(saved(200, body), clock);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "green" });
    expect(t.headline).toBe(
      "Freshness unknown — its observation started more than 5 min ahead of this browser's clock. Last read: Every expected Tier-1 source on every event",
    );
    // The producer's own time and the graded rows are kept; nothing is re-stamped.
    expect(t.asOf).toBe((body.last_good as unknown as { observation_started_at: string }).observation_started_at);
    expect(t.rows).toHaveLength(30);
    expect(summarize([t]).status).not.toBe("good");
  });

  it("uses the grid tile's existing skew tolerance: just inside it is current, just past it is not", () => {
    const body = coverageHit();
    expect(evaluateSourceCoverage(saved(200, body), obsStart(body) - SOURCE_CLOCK_SKEW_S * 1000).state).toBe("green");
    expect(evaluateSourceCoverage(saved(200, body), obsStart(body) - SOURCE_CLOCK_SKEW_S * 1000 - 1000).state).toBe("freshness_unknown");
  });

  it("the same tab reads current again once its clock is back past the observation — no new request", () => {
    const body = coverageHit();
    expect(evaluateSourceCoverage(saved(200, body), obsStart(body) - 10 * 60_000).state).toBe("freshness_unknown");
    expect(evaluateSourceCoverage(saved(200, body), NOW).state).toBe("green");
  });

  it("names the contract roster the backend projects (admin_dashboard._TIER1_SPORTS), Golf and NCAAB included", () => {
    expect([...TIER1_COVERAGE_SPORTS]).toEqual(TIER1_SPORTS);
  });

  it("refuses a projection carrying only one of the six sports instead of grading the one that arrived", () => {
    const body = coverageHit();
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: tier1Of(body).slice(0, 1) }), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [], asOf: null });
    expect(t.headline).toBe("Unavailable — unexpected response shape (Tier-1 rows missing for NFL, NHL, MLB, NCAAB, PGA Golf)");
  });

  it.each([
    ["PGA Golf", "golf_pga"],
    ["NCAAB", "basketball_ncaab"],
  ])("refuses a projection that silently omits %s — unlike a sport sent as having no events", (label, sport) => {
    const body = coverageHit();
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: tier1Of(body).filter((r) => r.sport !== sport) }), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [] });
    expect(t.headline).toContain(`Tier-1 rows missing for ${label}`);
  });

  it("refuses one sport repeated six times — six rows is not six sports", () => {
    const body = coverageHit();
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: tier1Of(body).map(() => tier1Of(body)[0]) }), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [] });
    expect(t.headline).toBe("Unavailable — unexpected response shape (Tier-1 row NBA sent more than once)");
  });

  it("refuses a repeat that takes a missing sport's place, keeping the length at six", () => {
    const body = coverageHit();
    const rows = tier1Of(body);
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: [...rows.slice(0, 5), rows[0]] }), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [] });
  });

  it("refuses a sport outside the v1 roster", () => {
    const body = coverageHit();
    const extra = { ...tier1Of(body)[0], sport: "soccer_epl" };
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: [...tier1Of(body), extra] }), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [] });
    expect(t.headline).toContain("soccer_epl, not a Tier-1 sport");
  });

  it("does not depend on the projection's order", () => {
    const body = coverageHit();
    const t = evaluateSourceCoverage(saved(200, { ...body, tier1: [...tier1Of(body)].reverse() }), NOW);
    expect(t.state).toBe("green");
    expect(t.rows).toHaveLength(30);
  });
});

// ── 5. link rate (saved-only contract) ─────────────────────────────────────

describe("link rate — Tier-1 open game markets from the saved snapshot, never called current", () => {
  it("grades a fully linked snapshot but keeps it off green: no freshness horizon is reviewed", () => {
    const t = evaluateLinkRate(linkRateHit(), NOW);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "green", asOf: minutesAgo(10) });
    expect(t.headline).toContain("Freshness unreviewed");
    expect(t.related?.[0]).toMatchObject({ value: "90.0% (72/80)", state: "no_threshold" });
    expect(t.related?.[1]).toMatchObject({ value: "85.2%", note: "6 open markets excluded as upstream gaps" });
    expect(t.evidence?.[0]).toBe("Snapshot age 10 min ago, from generated_at; freshness unreviewed");
  });

  it("does not read the server's link_rate=0 over zero open markets as a failure", () => {
    const kalshi = T1_LEAGUES.map(([s, l]) => (l === "NFL" ? lrRow(s, l, 0, 0) : lrRow(s, l, 10, 10)));
    const t = evaluateLinkRate(linkRateHit(linkRatePayload({ kalshi })), NOW);
    expect(t.rows.find((r) => r.label === "Kalshi · NFL")).toMatchObject({ state: "unavailable", value: "no open markets" });
    expect(t.lastVerdict).toBe("partial");
  });

  it("keeps a red seen at 9 of 10 as the data's verdict, matching league case-insensitively", () => {
    const polymarket = T1_LEAGUES.map(([s, l]) => (l === "NHL" ? lrRow(s, "nhl", 10, 9) : lrRow(s, l, 10, 10)));
    const t = evaluateLinkRate(linkRateHit(linkRatePayload({ polymarket })), NOW);
    expect(t).toMatchObject({ state: "freshness_unknown", lastVerdict: "red" });
    expect(t.rows[0]).toMatchObject({ label: "Polymarket · NHL", value: "90.0% (9/10)", state: "red" });
  });

  it("reads a snapshot the payload itself marks stale as stale, with its reason", () => {
    const t = evaluateLinkRate(linkRateHit(linkRatePayload({ extra: { stale: true, stale_reason: "compute_timeout" } })), NOW);
    expect(t).toMatchObject({ state: "stale", lastVerdict: "green" });
    expect(t.headline).toContain("compute_timeout");
  });

  it("a generated_at in the future is freshness unknown, never current", () => {
    const payload = linkRatePayload({ generatedAt: new Date(NOW + 600_000).toISOString() });
    const t = evaluateLinkRate(saved(200, linkRateBody("hit", "generated_at_in_future", payload, "unknown")), NOW);
    expect(t.state).toBe("freshness_unknown");
    expect(t.headline).toContain("generated_at is in the future");
  });

  it("the saved no-data snapshot is unavailable with ITS reason", () => {
    const payload = { generated_at: minutesAgo(3), stale: true, unavailable: true, stale_reason: "compute_error", overall: {}, kalshi: {}, polymarket: {} };
    const t = evaluateLinkRate(saved(503, linkRateBody("unavailable", "saved_snapshot_unavailable", payload)), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [], asOf: minutesAgo(3) });
    expect(t.headline).toContain("records no data (compute_error)");
  });

  it.each([
    [202, linkRateBody("miss", "no_saved_snapshot"), "nothing is saved yet", "no_saved_snapshot"],
    [503, linkRateBody("error", "redis_unavailable"), "could not be read", "redis_unavailable"],
    [503, linkRateBody("malformed", "non_finite_number"), "refused as malformed", "non_finite_number"],
  ])("HTTP %i keeps its own reason: %j", (status, body, words, reason) => {
    const t = evaluateLinkRate(saved(status, body), NOW);
    expect(t).toMatchObject({ state: "unavailable", rows: [], asOf: null });
    expect(t.headline).toContain(words);
    expect(t.headline).toContain(reason);
  });

  it.each([
    ["a hit sent as 503", 503, linkRateBody("hit", "saved_snapshot", linkRatePayload(), "unreviewed")],
    ["a hit claiming 'fresh' (not in this contract)", 200, linkRateBody("hit", "saved_snapshot", linkRatePayload(), "fresh")],
    ["an envelope stamp that is not the payload's", 200, { ...linkRateBody("hit", "saved_snapshot", linkRatePayload(), "unreviewed"), generated_at: minutesAgo(0) }],
    ["a hit with no payload", 200, { ...linkRateBody("hit", "saved_snapshot", linkRatePayload(), "unreviewed"), payload: null }],
  ])("refuses %s as a wrong shape", (_label, status, body) => {
    expect(evaluateLinkRate(saved(status, body), NOW)).toMatchObject({ state: "unavailable", rows: [] });
  });
});

// ── 6. grid health ─────────────────────────────────────────────────────────

describe("grid health — the Grid Sentinel's verdict, with Golf's gap kept visible", () => {
  it("three clean Sentinel leagues are NOT an all-clear while Golf has no coverage", () => {
    const t = evaluateGridHealth(ok(sentinelPayload()), NOW);
    expect(t.state).toBe("partial");
    expect(t.rows.map((r) => [r.label, r.state])).toEqual([
      ["MLB", "green"],
      ["NBA", "green"],
      ["NHL", "green"],
      ["Golf", "unavailable"],
    ]);
    expect(gridRow(t, "Golf")).toMatchObject({ value: "no Sentinel coverage" });
    expect(t.headline).toBe("MLB, NBA, NHL clean per the Grid Sentinel — Golf has no Sentinel coverage, so no all-clear");
    expect(t.source).toBe("/api/admin/grid-sentinel/last");
    expect(t.asOf).toBe(minutesAgo(60));
  });

  it("a REAL defect is red, and stays red whatever else the run says", () => {
    const t = evaluateGridHealth(ok(sentinelPayload([league("mlb", { verdict: "red", real_defects: 2, watch: 7 }), league("nba"), league("nhl")])), NOW);
    expect(t.state).toBe("red");
    expect(gridRow(t, "MLB")).toMatchObject({ state: "red", value: "2 REAL defects" });
    expect(gridRow(t, "MLB")!.note).toContain("7 watch (blend-hidden, never red)");
    expect(t.headline).toBe("1 of 3 Sentinel leagues have REAL defects · no Sentinel coverage: Golf");
    // A red whose count is unreadable is still red: the verdict is the authority.
    const odd = evaluateGridHealth(ok(sentinelPayload([league("mlb", { verdict: "red", real_defects: "two" }), league("nba"), league("nhl")])), NOW);
    expect(gridRow(odd, "MLB")).toMatchObject({ state: "red", value: "REAL defects" });
  });

  it("WATCH never creates red, and EXPLAINED keeps its meaning — both counted, neither colours the row", () => {
    const t = evaluateGridHealth(ok(sentinelPayload([league("mlb", { watch: 12 }), league("nba", { explained_artifacts: 4 }), league("nhl", { watch: 3, explained_artifacts: 1 })])), NOW);
    expect(t.rows.slice(0, 3).map((r) => r.state)).toEqual(["green", "green", "green"]);
    expect(gridRow(t, "MLB")!.note).toContain("12 watch (blend-hidden, never red)");
    expect(gridRow(t, "NBA")!.note).toContain("4 explained (season-window, not filed)");
    expect(t.related).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "WATCH — blend-hidden source disagreement, never red", value: "15", state: "no_threshold" }),
        expect.objectContaining({ label: "EXPLAINED — season-window artifacts, not filed", value: "5", state: "no_threshold" }),
      ]),
    );
  });

  it("a skipped check is unverified — green_unverified, or a green that lists a skipped check", () => {
    const unverified = evaluateGridHealth(ok(sentinelPayload([league("mlb", { verdict: "green_unverified", checks_skipped: ["freshness"] }), league("nba"), league("nhl")])), NOW);
    expect(gridRow(unverified, "MLB")).toMatchObject({ state: "partial", value: "green, unverified" });
    expect(gridRow(unverified, "MLB")!.note).toContain("checks skipped: freshness");
    expect(unverified.state).toBe("partial");
    const borrowed = evaluateGridHealth(ok(sentinelPayload([league("mlb", { checks_skipped: ["freshness"] }), league("nba"), league("nhl")])), NOW);
    expect(gridRow(borrowed, "MLB")!.state).toBe("partial");
  });

  it("a green is green only when its counts prove it", () => {
    for (const bad of [{ real_defects: 1 }, { real_defects: undefined }, { watch: "3" }, { explained_artifacts: -1 }, { checks_skipped: "freshness" }]) {
      const t = evaluateGridHealth(ok(sentinelPayload([league("mlb", bad), league("nba"), league("nhl")])), NOW);
      expect(gridRow(t, "MLB")!.state).toBe("unavailable");
    }
  });

  it.each([["amber"], ["GREEN"], [null], [undefined]])("an unknown verdict (%p) is unverified, never green or red", (verdict) => {
    const t = evaluateGridHealth(ok(sentinelPayload([league("mlb", { verdict }), league("nba"), league("nhl")])), NOW);
    expect(gridRow(t, "MLB")!.state).toBe("unavailable");
    expect(gridRow(t, "MLB")!.note).toContain("unknown verdict");
  });

  it("a league missing from the run, or reported twice, blocks the all-clear", () => {
    const missing = evaluateGridHealth(ok(sentinelPayload([league("mlb"), league("nba")], { errors: [{ deadline: "stopped before nhl" }] })), NOW);
    expect(gridRow(missing, "NHL")).toMatchObject({ state: "unavailable", note: "not in the last Sentinel run" });
    expect(missing.related).toEqual(expect.arrayContaining([expect.objectContaining({ label: "Errors in the run", value: "1" })]));
    const twice = evaluateGridHealth(ok(sentinelPayload([league("mlb"), league("mlb", { verdict: "red", real_defects: 1 }), league("nba"), league("nhl")])), NOW);
    expect(gridRow(twice, "MLB")).toMatchObject({ state: "unavailable", note: "reported more than once in one run" });
    const empty = evaluateGridHealth(ok(sentinelPayload([])), NOW);
    expect(empty.state).toBe("unavailable");
  });

  it("a league the Sentinel starts covering is judged by its verdict, and its gap row goes away", () => {
    const t = evaluateGridHealth(ok(sentinelPayload(["mlb", "nba", "nhl", "golf"].map((l) => league(l)))), NOW);
    expect(t.state).toBe("green");
    expect(gridRow(t, "Golf")).toMatchObject({ state: "green", value: "clean" });
    expect(t.rows.filter((r) => r.value === "no Sentinel coverage")).toEqual([]);
  });

  it.each([
    [{ status: "no_run_cached", key: "bainluck:grid_sentinel:last" }, "no Grid Sentinel run is saved"],
    [{ status: "unparseable", key: "k", error_class: "JSONDecodeError" }, "does not decode (JSONDecodeError)"],
    [{ status: "wrong_shape", key: "k", error_class: "list" }, "is not an object"],
    [{ status: "something_new" }, 'unrecognised rail status "something_new"'],
    [{ scorecard: { per_league: "x" }, generated_at: minutesAgo(5) }, "no scorecard.per_league[]"],
    [[], "not an object"],
  ])("rail answer %p is unverified, with every grid still listed", (body, words) => {
    const t = evaluateGridHealth(ok(body), NOW);
    expect(t.state).toBe("unavailable");
    expect(t.headline).toContain(words);
    expect(t.rows.map((r) => r.label)).toEqual(["MLB", "NBA", "NHL", "Golf"]);
    expect(t.rows.every((r) => r.state === "unavailable")).toBe(true);
  });

  it("a 503 says the evidence store could not be read", () => {
    const t = evaluateGridHealth({ status: "error", kind: "http", detail: "HTTP 503", ms: 30, httpStatus: 503 }, NOW);
    expect(t).toMatchObject({ state: "unavailable", headline: "Unavailable — the Sentinel's evidence store could not be read (HTTP 503)" });
    expect(gridRow(t, "Golf")).toMatchObject({ value: "no Sentinel coverage" });
  });

  it("the old raw-score payload can turn the tile neither green nor red", () => {
    const allGrids100 = { nba: { health_score: 100, findings: [] }, nhl: { health_score: 100, findings: [] }, mlb: { health_score: 100, findings: [] }, golf: { health_score: 100, findings: [] } };
    const raw100 = evaluateGridHealth(ok({ generated_at: minutesAgo(5), scores: {}, avg_score: 100, grids: allGrids100 }), NOW);
    expect(raw100.state).toBe("unavailable");
    const raw40 = evaluateGridHealth(ok({ generated_at: minutesAgo(5), grids: { ...allGrids100, mlb: { health_score: 40, findings: [{}] } } }), NOW);
    expect(raw40.state).toBe("unavailable");
    // A penalty score riding along on a Sentinel entry is ignored: the verdict decides.
    const mixed = evaluateGridHealth(
      ok(sentinelPayload([league("mlb", { verdict: "red", real_defects: 1, health_score: 100 }), league("nba", { health_score: 12 }), league("nhl")])),
      NOW,
    );
    expect(gridRow(mixed, "MLB")!.state).toBe("red");
    expect(gridRow(mixed, "NBA")!.state).toBe("green");
    expect(JSON.stringify(mixed)).not.toMatch(/\/100/);
  });

  it("goes stale on the Sentinels card's own silence rule, judged on the run's stamp", () => {
    expect(GRID_SENTINEL_STALE_AFTER_S).toBe(SENTINELS.find((x) => x.key === "grid")!.beatIntervalHours * SILENCE_MULTIPLIER * 3600);
    expect(SENTINELS.find((x) => x.key === "grid")!.endpoint).toBe(CORRECTNESS_ENDPOINTS.gridSentinel);
    const limitMin = GRID_SENTINEL_STALE_AFTER_S / 60;
    expect(evaluateGridHealth(ok(sentinelPayload(undefined, { generated_at: minutesAgo(limitMin - 1) })), NOW).state).toBe("partial");
    const old = evaluateGridHealth(ok(sentinelPayload(undefined, { generated_at: minutesAgo(limitMin + 1) })), NOW);
    expect(old).toMatchObject({ state: "stale", lastVerdict: "partial", asOf: minutesAgo(limitMin + 1) });
    expect(old.headline).toMatch(/^Stale — the last run is .* past 36 h\. Last read: /);
    const oldRed = evaluateGridHealth(
      ok(sentinelPayload([league("mlb", { verdict: "red", real_defects: 1 }), league("nba"), league("nhl")], { generated_at: minutesAgo(limitMin + 1) })),
      NOW,
    );
    expect(oldRed).toMatchObject({ state: "stale", lastVerdict: "red" });
  });

  it.each([
    [undefined, "carries no timestamp"],
    ["not a date", "does not parse"],
    [new Date(NOW + 3600_000).toISOString(), "in the future"],
  ])("a missing or invalid run stamp (%p) is stale, never current", (stamp, words) => {
    const t = evaluateGridHealth(ok(sentinelPayload(undefined, { generated_at: stamp })), NOW);
    expect(t.state).toBe("stale");
    expect(t.headline).toContain(words);
  });

  it("degraded provenance is stale; a sound durable copy says where it came from", () => {
    const stamp = minutesAgo(60);
    const prov = (over: Record<string, unknown>) => ({ source: "durable", generated_at: stamp, complete: true, note: "served from the durable store", ...over });
    for (const bad of [{ health: "UNKNOWN", contract_errors: ["checksum_mismatch"] }, { complete: false }, { generated_at: minutesAgo(600) }]) {
      const t = evaluateGridHealth(ok(sentinelPayload(undefined, { provenance: prov(bad) })), NOW);
      expect(t.state).toBe("stale");
    }
    expect(evaluateGridHealth(ok(sentinelPayload(undefined, { provenance: "junk" })), NOW).state).toBe("stale");
    const good = evaluateGridHealth(ok(sentinelPayload(undefined, { provenance: prov({}), mode: "detect_only" })), NOW);
    expect(good.state).toBe("partial");
    expect(good.related).toEqual(
      expect.arrayContaining([expect.objectContaining({ label: "Evidence served from", value: "durable store (last-known state)", note: "served from the durable store · detect-only run (issues not filed)" })]),
    );
  });

  it("ages into stale in a tab left open, with no new request", () => {
    jest.useFakeTimers();
    const fetchSpy = jest.fn();
    const realFetch = global.fetch;
    global.fetch = fetchSpy as unknown as typeof fetch;
    try {
      const read = ok(sentinelPayload());
      let judged = evaluateGridHealth(read, NOW);
      expect(judged.state).toBe("partial");
      const base = jest.now();
      const stop = startUiClock((t) => (judged = evaluateGridHealth(read, t)), { doc: null, now: () => NOW + (jest.now() - base) });
      jest.advanceTimersByTime(GRID_SENTINEL_STALE_AFTER_S * 1000 - 3600_000 + 60_000);
      expect(judged).toMatchObject({ state: "stale", lastVerdict: "partial", asOf: minutesAgo(60) });
      expect(fetchSpy).not.toHaveBeenCalled();
      stop();
    } finally {
      global.fetch = realFetch;
      jest.useRealTimers();
    }
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

  it("starts every read before any settles, and one failure does not hold the rest", async () => {
    const started: string[] = [];
    const settled: string[] = [];
    let releaseSlow: () => void = () => {};
    const slow = new Promise<void>((res) => (releaseSlow = res));
    const ms = startCorrectnessReads(
      (key) => async () => {
        started.push(key);
        if (key === "gridSentinel") throw new Error("network down");
        if (key === "sourceCoverage") await slow;
        return new Response(JSON.stringify({ key }), { status: 200 });
      },
      (key) => settled.push(key),
    );
    await new Promise((r) => setTimeout(r, 5));
    expect(started.sort()).toEqual(Object.keys(CORRECTNESS_ENDPOINTS).sort());
    // Everything but the slow read has already reported, the failure included.
    expect(settled.sort()).toEqual(["calibration", "gridSentinel", "linkRate", "snapshotDistribution", "winners"]);
    releaseSlow();
    expect(typeof (await ms)).toBe("number");
    expect(settled).toContain("sourceCoverage");
  });

  it("keeps a saved route's JSON reason on a 202 or 503 as the error body — never as data", async () => {
    const miss = linkRateBody("miss", "no_saved_snapshot");
    const r202 = await boundedRead(async () => new Response(JSON.stringify(miss), { status: 202 }));
    expect(r202).toMatchObject({ status: "error", kind: "pending", httpStatus: 202, body: miss });
    const bad = coverageBody("malformed", "unknown", "duplicate_sport");
    const r503 = await boundedRead(async () => new Response(JSON.stringify(bad), { status: 503 }));
    expect(r503).toMatchObject({ status: "error", kind: "http", httpStatus: 503, body: bad });
    expect(evaluateSourceCoverage(r503, NOW).headline).toBe("Unavailable — the saved evidence was refused as malformed (duplicate_sport)");
    expect(evaluateLinkRate(r202, NOW).headline).toBe("Unavailable — nothing is saved yet, and this page does not compute it (no_saved_snapshot)");
    const plain = await boundedRead(async () => new Response("Service Unavailable", { status: 503 }));
    expect(plain).toMatchObject({ kind: "http", httpStatus: 503, body: undefined });
  });

  it("opening and reloading the console request only the saved routes — never /dashboard or the computing link-rate GET", async () => {
    const requested: string[] = [];
    // The page's own mapping: one GET of CORRECTNESS_ENDPOINTS[key] per read.
    const fetchFor = (key: keyof CorrectnessReads) => async () => {
      requested.push(CORRECTNESS_ENDPOINTS[key]);
      return new Response(JSON.stringify(key === "sourceCoverage" ? coverageBody("miss", "unknown", "no_cached_observation") : linkRateBody("miss", "no_saved_snapshot")), { status: 202 });
    };
    await startCorrectnessReads(fetchFor, () => {}); // open
    await startCorrectnessReads(fetchFor, () => {}); // Reload
    expect(requested).toHaveLength(12);
    expect(requested.filter((p) => p === "/api/admin/snapshots/distribution")).toHaveLength(2);
    expect(requested.filter((p) => p === "/api/admin/event-source-coverage/cached")).toHaveLength(2);
    expect(requested.filter((p) => p === "/api/admin/prediction-markets/link-rate/cached")).toHaveLength(2);
    for (const p of requested) {
      expect(p).not.toMatch(/\/api\/admin\/dashboard\b/);
      expect(p).not.toMatch(/\/prediction-markets\/link-rate(?!\/cached$)/);
      expect(p).not.toContain("?");
    }
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

// ── 7. snapshot sparsity ───────────────────────────────────────────────────

describe("snapshot sparsity — a sampled number, shown without a colour", () => {
  it("shows each source's sparse share of its SAMPLED outcomes, never green, with the population beside it", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload()), NOW);
    expect(t.state).toBe("no_threshold");
    expect(t.title).toBe("Price-history sparsity");
    expect(snapRow(t, "kalshi")).toMatchObject({ value: "12.6% sparse (52 of 412 sampled outcomes)", state: "no_threshold" });
    expect(snapRow(t, "kalshi")!.note).toContain("Population, not the denominator: 9,000 outcomes on all open/active kalshi markets (the sample is 4.6% of it)");
    expect(snapRow(t, "kalshi")!.note).toContain("0: 12 · 1–5: 40 · 6–20: 100 · 21–50: 120 · 51–100: 90 · over 100: 50 · median 31 · mean 38.4");
    expect(snapRow(t, "polymarket")).toMatchObject({ value: "75.0% sparse (450 of 600 sampled outcomes)", state: "no_threshold" });
    expect(t.headline).toBe("2 sources sampled · sparse share 12.6% to 75.0% of each source's sampled outcomes · no reviewed threshold");
    expect(t.asOf).toBe(minutesAgo(90));
    expect(t.method).toContain("200 most-recent open/active markets");
    expect(t.method).toContain("never the denominator");
    expect(t.evidence).toContain("Producer's method: 200 most-recent markets per source (open/active only)");
  });

  it("never adds sources together: no pooled share appears anywhere on the tile", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload()), NOW);
    const text = JSON.stringify(t);
    // Pooled over both: (52 + 450) / (412 + 600) = 49.6%; summed percentages: 87.6%.
    expect(text).not.toContain("49.6%");
    expect(text).not.toContain("87.6%");
    expect(text).not.toContain("1,012");
  });

  it("a real measured 0% and a real measured 100% are both numbers, neither coloured", () => {
    const zero = evaluateSnapshotSparsity(ok(snapPayload([zeroSparse()])), NOW);
    expect(zero.state).toBe("no_threshold");
    expect(zero.rows[0]).toMatchObject({ value: "0.0% sparse (0 of 200 sampled outcomes)", state: "no_threshold" });
    expect(zero.headline).toBe("1 source sampled · sparse share 0.0% of its sampled outcomes · no reviewed threshold");
    const all = evaluateSnapshotSparsity(ok(snapPayload([allSparse()])), NOW);
    expect(all.state).toBe("no_threshold");
    expect(all.rows[0]).toMatchObject({ value: "100.0% sparse (80 of 80 sampled outcomes)", state: "no_threshold" });
    expect(all.headline).toContain("sparse share 100.0%");
    for (const t of [zero, all]) {
      expect(["green", "amber", "red"]).not.toContain(t.state);
      expect(t.rows.every((r) => r.state === "no_threshold")).toBe(true);
    }
  });

  it("never rounds a sample that is not all sparse up to 100%", () => {
    // 2499 of 2500 = 99.96% → the producer rounds to 100.0, which agrees within its rounding.
    const s = snapSource({ sampled_outcomes: 2500, total_outcomes: 2500, zero_snapshots: 2000, "1_to_5": 499, "6_to_20": 1, "21_to_50": 0, "51_to_100": 0, "100_plus": 0, avg_snapshots: 0.4, median_snapshots: 0, sparse_pct: 100 });
    const t = evaluateSnapshotSparsity(ok(snapPayload([s])), NOW);
    expect(t.rows[0].value).toBe("99.9% sparse (2,499 of 2,500 sampled outcomes)");
    expect(t.headline).toContain("sparse share 99.9%");
  });

  it("divides by the sample, not the population: the same buckets read the same whatever the population", () => {
    const small = snapSource({ total_outcomes: 412 });
    const huge = snapSource({ total_outcomes: 4_000_000 });
    const a = evaluateSnapshotSparsity(ok(snapPayload([small])), NOW).rows[0];
    const b = evaluateSnapshotSparsity(ok(snapPayload([huge])), NOW).rows[0];
    expect(a.value).toBe("12.6% sparse (52 of 412 sampled outcomes)");
    expect(b.value).toBe(a.value);
    expect(a.note).toContain("412 outcomes on all open/active kalshi markets (the sample is 100.0% of it)");
    expect(b.note).toContain("4,000,000 outcomes on all open/active kalshi markets (the sample is 0.0% of it)");
    // 52 / 4,000,000 would be 0.0013% — the population never becomes the denominator.
    expect(b.value).not.toMatch(/^0\.0%/);
  });

  it("refuses a row whose buckets do not add up to its sample, keeping the healthy sibling", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload([snapSource({ "100_plus": 51 }), polySnap()])), NOW);
    expect(snapRow(t, "kalshi")).toMatchObject({ value: "—", state: "unavailable", note: "the six buckets add to 413, not the 412 sampled" });
    expect(snapRow(t, "polymarket")!.state).toBe("no_threshold");
    expect(t.state).toBe("partial");
    expect(t.headline).toBe("1 source sampled · sparse share 75.0% of its sampled outcomes · no reviewed threshold · 1 row could not be read");
  });

  it("checks sparse_pct against its own buckets within the producer's one-decimal rounding", () => {
    const read = (pctValue: unknown) => evaluateSnapshotSparsity(ok(snapPayload([snapSource({ sparse_pct: pctValue })])), NOW).rows[0];
    // 52 / 412 = 12.621%
    expect(read(12.6).state).toBe("no_threshold");
    expect(read(12.65).state).toBe("no_threshold");
    expect(read(12.7)).toMatchObject({ state: "unavailable", note: "sparse_pct 12.7% disagrees with its buckets (12.62%)" });
    expect(read(50)).toMatchObject({ state: "unavailable" });
    expect(read(101).note).toBe("sparse_pct is missing or outside 0–100");
    expect(read(-1).note).toBe("sparse_pct is missing or outside 0–100");
    expect(read("12.6").note).toBe("sparse_pct is missing or outside 0–100");
    expect(read(undefined).note).toBe("sparse_pct is missing or outside 0–100");
  });

  it("refuses a median or mean that contradicts the buckets", () => {
    // 75% sparse: the median outcome has at most 5 snapshots.
    expect(evaluateSnapshotSparsity(ok(snapPayload([polySnap({ median_snapshots: 40 })])), NOW).rows[0]).toMatchObject({
      state: "unavailable",
      note: "median 40 disagrees with 450 of 600 sparse",
    });
    // 12.6% sparse: the median outcome has at least 6.
    expect(evaluateSnapshotSparsity(ok(snapPayload([snapSource({ median_snapshots: 3 })])), NOW).rows[0].state).toBe("unavailable");
    // Every outcome at zero snapshots: the mean and median are zero.
    expect(evaluateSnapshotSparsity(ok(snapPayload([{ ...allSparse(), avg_snapshots: 0.3 }])), NOW).rows[0]).toMatchObject({
      state: "unavailable",
      note: "mean 0.3 disagrees with its buckets",
    });
    expect(evaluateSnapshotSparsity(ok(snapPayload([{ ...zeroSparse(), avg_snapshots: 4 }])), NOW).rows[0].state).toBe("unavailable");
    expect(evaluateSnapshotSparsity(ok(snapPayload([snapSource({ avg_snapshots: null })])), NOW).rows[0].note).toBe(
      "avg_snapshots or median_snapshots is missing or negative",
    );
  });

  it("names a missing, fractional or string count instead of reading it as zero", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload([snapSource({ zero_snapshots: undefined, "1_to_5": "40", "6_to_20": 99.5 })])), NOW);
    expect(t.rows[0]).toMatchObject({ label: "kalshi", value: "—", state: "unavailable", note: "not a whole count: zero_snapshots, 1_to_5, 6_to_20" });
    expect(t.state).toBe("unavailable");
    expect(t.headline).toBe("Unavailable — none of the 1 source rows could be read");
  });

  it("refuses a sample larger than its population, and a sample of nothing", () => {
    expect(evaluateSnapshotSparsity(ok(snapPayload([snapSource({ total_outcomes: 400 })])), NOW).rows[0].note).toBe(
      "412 sampled from a population of 400 — inconsistent",
    );
    const empty = snapSource({ sampled_outcomes: 0, zero_snapshots: 0, "1_to_5": 0, "6_to_20": 0, "21_to_50": 0, "51_to_100": 0, "100_plus": 0, sparse_pct: 0 });
    expect(evaluateSnapshotSparsity(ok(snapPayload([empty])), NOW).rows[0].note).toBe("no sampled outcomes — nothing was measured");
  });

  it("a source sent twice is shown once, unverified, and neither copy counts", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload([snapSource(), polySnap(), snapSource({ sparse_pct: 12.6 })])), NOW);
    const kalshi = t.rows.filter((r) => r.label === "kalshi");
    expect(kalshi).toEqual([{ label: "kalshi", value: "—", state: "unavailable", note: "sent 2 times in one result — no copy is used" }]);
    expect(t.state).toBe("partial");
    expect(t.headline).toContain("sparse share 75.0% of its sampled outcomes");
    expect(t.headline).not.toContain("12.6%");
  });

  it("keeps an unnamed row visible as unverified", () => {
    const t = evaluateSnapshotSparsity(ok(snapPayload([snapSource({ source: "" }), "junk", polySnap()])), NOW);
    expect(t.rows.filter((r) => r.label === "unnamed source")).toHaveLength(2);
    expect(t.state).toBe("partial");
  });

  it("an empty source list and a wrong shape are unverified, never 0%", () => {
    const empty = evaluateSnapshotSparsity(ok(snapPayload([])), NOW);
    expect(empty).toMatchObject({ state: "unavailable", headline: "Unavailable — the saved result lists no sources, which is not 0%" });
    expect(evaluateSnapshotSparsity(ok({ computed_at: minutesAgo(5) }), NOW).headline).toBe("Unavailable — unexpected response shape (no sources[])");
    expect(evaluateSnapshotSparsity(ok([snapSource()]), NOW).state).toBe("unavailable");
  });
});

describe("snapshot sparsity — every way of having no number stays distinguishable from a measured 0%", () => {
  const hang = (signal: AbortSignal) => new Promise<Response>((_res, rej) => signal.addEventListener("abort", () => rej(new Error("aborted"))));

  it("the route's cache-miss 404 says nothing is saved — and never repeats the instruction to compute", async () => {
    const r = await boundedRead(async () => new Response(JSON.stringify({ detail: SNAP_MISS_DETAIL }), { status: 404 }));
    expect(r).toMatchObject({ status: "error", kind: "http", httpStatus: 404, body: { detail: SNAP_MISS_DETAIL } });
    const t = evaluateSnapshotSparsity(r, NOW);
    expect(t).toMatchObject({ state: "unavailable", headline: "Unavailable — no saved result (HTTP 404), and this page does not compute one", rows: [], asOf: null });
    const html = renderToStaticMarkup(<CorrectnessTileCard tile={t} nowMs={NOW} />);
    expect(html).not.toContain("POST");
    expect(html).not.toContain("to compute.");
  });

  it("separates the no-result answer from every other way of not reading a number", async () => {
    const headlines = new Map<string, CorrectnessTile>();
    headlines.set("miss", evaluateSnapshotSparsity(await boundedRead(async () => new Response(JSON.stringify({ detail: SNAP_MISS_DETAIL }), { status: 404 })), NOW));
    headlines.set("other 404", evaluateSnapshotSparsity(await boundedRead(async () => new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })), NOW));
    headlines.set("401", evaluateSnapshotSparsity(await boundedRead(async () => new Response("Invalid admin secret", { status: 401 })), NOW));
    headlines.set("202", evaluateSnapshotSparsity(await boundedRead(async () => new Response(JSON.stringify({ status: "queued" }), { status: 202 })), NOW));
    headlines.set("deadline", evaluateSnapshotSparsity(await boundedRead(hang, { timeoutMs: 20 }), NOW));
    headlines.set("malformed body", evaluateSnapshotSparsity(await boundedRead(async () => new Response("<html>", { status: 200 })), NOW));
    headlines.set("wrong shape", evaluateSnapshotSparsity(await boundedRead(async () => new Response(JSON.stringify({ status: "queued", task_id: "x" }), { status: 200 })), NOW));
    headlines.set("500", evaluateSnapshotSparsity(await boundedRead(async () => new Response("boom", { status: 500 })), NOW));
    const measuredZero = evaluateSnapshotSparsity(ok(snapPayload([zeroSparse()])), NOW);

    expect(headlines.get("401")!.state).toBe("unauthorized");
    expect(headlines.get("401")!.headline).toContain("says nothing about the data");
    expect(headlines.get("other 404")!.headline).toBe("Unavailable — HTTP 404 without the route's no-saved-result answer");
    expect(headlines.get("202")!.headline).toBe("Unavailable — HTTP 202, which this route never sends for a saved result");
    expect(headlines.get("deadline")!.headline).toBe("Unavailable — no answer within 20 ms");
    expect(headlines.get("wrong shape")!.headline).toBe("Unavailable — unexpected response shape (no sources[])");
    const texts = [...headlines.values()].map((t) => t.headline);
    expect(new Set(texts).size).toBe(texts.length);
    for (const t of headlines.values()) {
      expect(["unavailable", "unauthorized"]).toContain(t.state);
      expect(t.rows).toEqual([]);
      expect(t.headline).not.toContain("0.0%");
      expect(t.headline).not.toBe(measuredZero.headline);
    }
    expect(measuredZero.state).toBe("no_threshold");
  });

  it("a missing or unparseable computed_at keeps the numbers but has no age", () => {
    for (const [stamp, why] of [
      [null, "the result carries no computed_at"],
      [undefined, "the result carries no computed_at"],
      ["yesterday", "its computed_at does not parse"],
      [1729400000, "its computed_at does not parse"],
    ] as const) {
      const body: Record<string, unknown> = snapPayload([zeroSparse()]);
      if (stamp === undefined) delete body.computed_at;
      else body.computed_at = stamp;
      const t = evaluateSnapshotSparsity(ok(body), NOW);
      expect(t.state).toBe("freshness_unknown");
      expect(t.headline).toBe(`Freshness unknown — ${why}. Last read: 1 source sampled · sparse share 0.0% of its sampled outcomes · no reviewed threshold`);
      expect(t.asOf).toBeNull();
      expect(t.rows[0].value).toBe("0.0% sparse (0 of 200 sampled outcomes)");
    }
  });
});

describe("snapshot sparsity — judged on this tab's clock, with no new request", () => {
  afterEach(() => jest.useRealTimers());

  it("a computed_at ahead of this tab's clock is freshness unknown past the existing 300 s tolerance", () => {
    const stampAt = (msAhead: number) => new Date(NOW + msAhead).toISOString();
    expect(evaluateSnapshotSparsity(ok(snapPayload(undefined, stampAt(SOURCE_CLOCK_SKEW_S * 1000))), NOW).state).toBe("no_threshold");
    const ahead = evaluateSnapshotSparsity(ok(snapPayload(undefined, stampAt(SOURCE_CLOCK_SKEW_S * 1000 + 1))), NOW);
    expect(ahead.state).toBe("freshness_unknown");
    expect(ahead.headline).toMatch(/^Freshness unknown — it was computed more than 5 min ahead of this browser's clock\. Last read: 2 sources sampled/);
    // The stamp is kept as the record's own; the card prints no invented age.
    expect(ahead.asOf).toBe(stampAt(SOURCE_CLOCK_SKEW_S * 1000 + 1));
    const html = renderToStaticMarkup(<CorrectnessTileCard tile={ahead} nowMs={NOW} />);
    expect(html).toContain("built ahead of this browser&#x27;s clock");
    expect(html).not.toContain("built 0s ago");
  });

  it("is stale only past the producer's own 24 h retention — exactly at it is not", () => {
    const stampAgo = (ms: number) => new Date(NOW - ms).toISOString();
    expect(evaluateSnapshotSparsity(ok(snapPayload(undefined, stampAgo(SNAPSHOT_DIST_RETENTION_S * 1000))), NOW).state).toBe("no_threshold");
    const old = evaluateSnapshotSparsity(ok(snapPayload(undefined, stampAgo(SNAPSHOT_DIST_RETENTION_S * 1000 + 1))), NOW);
    expect(old.state).toBe("stale");
    expect(old.headline).toMatch(/^Stale — older than the producer's 24 h retention in this open tab\. Last read: /);
  });

  it("one fetched record moves from ahead-of-clock to readable to stale on the UI clock alone", () => {
    jest.useFakeTimers();
    const fetchSpy = jest.fn();
    const realFetch = global.fetch;
    global.fetch = fetchSpy as unknown as typeof fetch;
    try {
      // The tab's clock starts ten minutes behind the record's computed_at.
      const computedAt = new Date(NOW).toISOString();
      const read = ok(snapPayload(undefined, computedAt));
      const loadedAt = NOW - 10 * 60_000;
      let judged = evaluateSnapshotSparsity(read, loadedAt);
      expect(judged.state).toBe("freshness_unknown");
      const base = jest.now();
      const stop = startUiClock((t) => (judged = evaluateSnapshotSparsity(read, t)), {
        doc: null,
        now: () => loadedAt + (jest.now() - base),
      });
      jest.advanceTimersByTime(6 * 60_000); // now 4 min behind: inside the tolerance
      expect(judged.state).toBe("no_threshold");
      jest.advanceTimersByTime((10 + 24 * 60) * 60_000); // past 24 h after computed_at
      expect(judged.state).toBe("stale");
      expect(judged.asOf).toBe(computedAt);
      expect(fetchSpy).not.toHaveBeenCalled();
      stop();
    } finally {
      global.fetch = realFetch;
    }
  });
});

describe("snapshot sparsity — what a reader sees", () => {
  const tile = evaluateSnapshotSparsity(ok(snapPayload([snapSource(), polySnap(), snapSource({ source: "odds_api", "100_plus": 49 })])), NOW);
  const html = renderToStaticMarkup(<CorrectnessTileCard tile={tile} nowMs={NOW} />);

  it("labels the panel, the sample and the population, with its state as a word", () => {
    expect(html).toContain('data-tile="snapshot_sparsity" data-state="partial"');
    expect(html).toContain("Price-history sparsity");
    expect(html).toContain("Partly verified");
    expect(html).toContain("No threshold");
    expect(html).toContain("12.6% sparse (52 of 412 sampled outcomes)");
    expect(html).toContain("Population, not the denominator: 9,000 outcomes");
    expect(html).toContain("the six buckets add to 411, not the 412 sampled");
    expect(html).toContain("/api/admin/snapshots/distribution · built 2 h ago");
    expect(html).toContain("not a reviewed freshness horizon");
  });

  it("never draws a verdict colour or an OK badge on this panel", () => {
    expect(html).not.toMatch(/>OK</);
    expect(html).not.toMatch(/>Act now</);
    expect(html).not.toMatch(/>Watch</);
    expect(html).not.toContain("text-accent-live");
    expect(html).not.toContain("text-accent-danger");
    expect(html).not.toContain("text-accent-warning");
  });

  it("joins the page overview as unverified, never as green", () => {
    const tiles = evaluateAll({ ...INITIAL_READS, snapshotDistribution: ok(snapPayload([zeroSparse()])) }, NOW);
    const page = renderToStaticMarkup(<CorrectnessConsoleView tiles={tiles} nowMs={NOW} settledMs={null} />);
    expect(page).toContain('data-tile="snapshot_sparsity" data-state="no_threshold"');
    expect(summarize(tiles).summary).toContain("unverified");
    expect(summarize(tiles).summary).toMatch(/^0 of 7 green/);
  });
});

// ── the page as a whole ────────────────────────────────────────────────────

function healthyReads(): CorrectnessReads {
  return {
    winners: ok(winnersPayload([winnerSource()])),
    calibration: ok({ ...freshEnvelope, generated_at: minutesAgo(10), by_category: [category("tennis", 1.3, 5000)] }),
    sourceCoverage: saved(200, coverageHit()),
    linkRate: linkRateHit(),
    gridSentinel: ok(sentinelPayload()),
    snapshotDistribution: ok(snapPayload()),
  };
}

describe("the header verdict", () => {
  it("is never 'good' while the guess family cannot be read, Golf has no Sentinel coverage and sparsity has no threshold", () => {
    const tiles = evaluateAll(healthyReads(), NOW);
    expect(tiles.filter((t) => t.state === "green").map((t) => t.key)).toEqual(["winner_coverage", "category_mce", "source_coverage"]);
    expect(tiles.find((t) => t.key === "grid_health")!.state).toBe("partial");
    // The saved link-rate snapshot has no reviewed freshness horizon: graded, never current.
    expect(tiles.find((t) => t.key === "link_rate")).toMatchObject({ state: "freshness_unknown", lastVerdict: "green" });
    expect(tiles.find((t) => t.key === "snapshot_sparsity")!.state).toBe("no_threshold");
    expect(summarize(tiles)).toEqual({ status: "warning", summary: "3 of 7 green · 4 unverified" });
  });

  it("is critical on any red tile", () => {
    const reads = { ...healthyReads(), gridSentinel: ok(sentinelPayload([league("mlb"), league("nba", { verdict: "red", real_defects: 1 }), league("nhl")])) };
    expect(summarize(evaluateAll(reads, NOW)).status).toBe("critical");
  });

  it("is about the credential when every admin read was refused, even though the public curve answered", () => {
    const refused: ReadResult = { status: "error", kind: "unauthorized", detail: "HTTP 403", ms: 40, httpStatus: 403 };
    const reads = { ...healthyReads(), winners: refused, sourceCoverage: refused, linkRate: refused, gridSentinel: refused, snapshotDistribution: refused };
    expect(summarize(evaluateAll(reads, NOW)).status).toBe("unauthorized");
    // One admin read that answered keeps the header about the data.
    expect(summarize(evaluateAll({ ...reads, snapshotDistribution: healthyReads().snapshotDistribution }, NOW)).status).toBe("warning");
  });

  it("is loading before anything settles", () => {
    expect(summarize(evaluateAll(INITIAL_READS, NOW)).status).toBe("loading");
  });

  it("folds states with red first and green only on all-green", () => {
    expect(foldStates(["green", "red", "unavailable"])).toBe("red");
    expect(foldStates(["green", "stale"])).toBe("partial");
    expect(foldStates(["stale"])).toBe("stale");
    expect(foldStates(["green", "freshness_unknown"])).toBe("partial");
    expect(foldStates([])).toBe("unavailable");
    expect(foldStates(["green", "amber"])).toBe("amber");
  });
});

describe("what a reader sees", () => {
  const mixed: CorrectnessReads = {
    ...healthyReads(),
    calibration: ok({ ...staleEnvelope, generated_at: "2026-10-13T14:35:40Z", by_category: [category("tennis", 1.33, 162848)] }),
    gridSentinel: { status: "error", kind: "timeout", detail: "no answer within 10000 ms", ms: 10_000 },
  };
  const html = renderToStaticMarkup(
    <CorrectnessConsoleView tiles={evaluateAll(mixed, NOW)} nowMs={NOW} settledMs={10_012} />,
  );

  it("draws all seven tiles, each with its state as a word and a data attribute", () => {
    for (const key of ["winner_coverage", "guess_family", "category_mce", "source_coverage", "link_rate", "grid_health", "snapshot_sparsity"]) {
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

  it("draws the saved link rate as 'Freshness unknown' with its verdict as history, and lists the producer evidence", () => {
    const lr = html.slice(html.indexOf('data-tile="link_rate"'), html.indexOf('data-tile="grid_health"'));
    expect(lr).toContain('data-state="freshness_unknown" data-last-verdict="green"');
    expect(lr).toContain("Freshness unknown");
    expect(lr).toContain("was OK");
    expect(lr).not.toMatch(/>OK</);
    expect(lr).toContain("Snapshot age 10 min ago, from generated_at; freshness unreviewed");
    const cov = html.slice(html.indexOf('data-tile="source_coverage"'), html.indexOf('data-tile="link_rate"'));
    expect(cov).toContain('data-state="green"');
    expect(cov).toContain("Produced by release v5805");
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

  it("reads the Grid Sentinel's saved run only — never the raw grid audit, the cockpit, or a Sentinel trigger", () => {
    expect(CORRECTNESS_ENDPOINTS.gridSentinel).toBe("/api/admin/grid-sentinel/last");
    for (const p of Object.values(CORRECTNESS_ENDPOINTS)) expect(p).not.toMatch(/audit\/all|cockpit|\/run\b/);
    expect(page + lib).not.toMatch(/audit\/all|\/cockpit|grid-sentinel\/run|_compute_audit_all_grids/);
    expect(lib).not.toContain("health_score");
  });

  it("never names the live-computing coverage or link-rate routes — no fallback, no warming", () => {
    expect(CORRECTNESS_ENDPOINTS.sourceCoverage).toBe("/api/admin/event-source-coverage/cached");
    expect(CORRECTNESS_ENDPOINTS.linkRate).toBe("/api/admin/prediction-markets/link-rate/cached");
    expect(page + lib).not.toContain("/api/admin/dashboard");
    expect(page + lib).not.toMatch(/prediction-markets\/link-rate(?!\/cached)/);
    expect(page + lib).not.toMatch(/refresh=|warm|enqueue|send_task/i);
  });

  it("reads the saved snapshot distribution with a plain GET — never its POST, a fallback or a computation", () => {
    expect(CORRECTNESS_ENDPOINTS.snapshotDistribution).toBe("/api/admin/snapshots/distribution");
    expect(ADMIN_READS.has("snapshotDistribution")).toBe(true);
    // Named once, in the endpoint table; the page sends it through the shared GET mapping.
    expect(lib.match(/snapshots\/distribution/g)).toHaveLength(1);
    expect(page).not.toContain("snapshots/distribution");
    expect(page + lib).not.toMatch(/method:\s*["'`]?(?:POST|PUT|PATCH|DELETE)/i);
    expect(page + lib).not.toMatch(/compute_snapshot_distribution|\.delay\(/);
  });

  it("keeps the public calibration read free of the admin credential", () => {
    expect(ADMIN_READS.has("calibration")).toBe(false);
    expect([...ADMIN_READS].sort()).toEqual(["gridSentinel", "linkRate", "snapshotDistribution", "sourceCoverage", "winners"]);
  });

  it("is reachable from the admin sidebar", () => {
    const sidebar = fs.readFileSync(path.join(root, "components/admin/AdminSidebar.tsx"), "utf8");
    expect(sidebar).toContain('href: "/admin/correctness"');
  });
});
