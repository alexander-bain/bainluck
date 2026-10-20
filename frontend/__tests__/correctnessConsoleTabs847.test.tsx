// #847 — THE CONSOLE CARRIES THE WHOLE MATCHING AND SOURCE INTELLIGENCE VIEWS,
// FROM SAVED EVIDENCE ONLY, WITHOUT STARTING A CALCULATION WHEN A TAB OPENS.
//
// What these tests pin:
//   - parity: every section of `/admin/matching` and `/admin/source-intelligence`
//     renders in its tab from a representative saved payload, through the SAME
//     presentation module both routes import;
//   - eligibility: the tabs read only the three `/cached` saved readers, and
//     Matching reuses the overview's link-rate read instead of sending another;
//   - laziness: the overview starts no tab read; a tab's reads start once per
//     round, are bounded and never retried, and an aborted round's answers are
//     dropped;
//   - honesty: a miss, a refused/oversized/malformed snapshot, a failed read and
//     a refused credential each show as exactly that with NO numbers; a hit is
//     never called current, and its age moves with the page's clock;
//   - accessibility: tab/panel ids, aria-selected/controls, roving tabindex and
//     the arrow/Home/End keys; Back/Refresh ride the `?tab=` query.
//
// No jsdom here: render tests use `renderToStaticMarkup`. Rendered-browser
// evidence at 390px/desktop is separate (fixture-labelled) evidence.

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import CorrectnessConsoleView, { ConsoleTabList } from "@/components/admin/CorrectnessConsole";
import { MatchingTabPanel, SourceIntelligenceTabPanel } from "@/components/admin/CorrectnessConsoleTabs";
import SourceIntelligenceView from "@/app/admin/_views/SourceIntelligenceView";
import { CORRECTNESS_ENDPOINTS, evaluateAll, INITIAL_READS, type ReadResult } from "@/lib/correctnessConsole";
import {
  CONSOLE_TABS,
  INITIAL_TAB_READS,
  SAVED_READER_CACHE_STATUS,
  TAB_READ_ENDPOINTS,
  TAB_READ_GROUPS,
  consoleTabSearch,
  linkRateSection,
  maturedLinkageSection,
  parseConsoleTab,
  sectionState,
  sourceIntelligenceSection,
  sportCardsSection,
  startTabReads,
  tabAfterKey,
  tabKeysToStart,
  type TabReadKey,
} from "@/lib/correctnessConsoleTabs";

const NOW = Date.parse("2026-10-20T19:00:00Z");
const BUILT = "2026-10-20T18:48:00+00:00"; // 12 min before NOW
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

// ── representative saved payloads (the shapes the real producers write) ─────

function maturedPayload() {
  return {
    headline_pct: 75.0,
    status: "ok",
    checkable_pairs: 4,
    backed: 3,
    phantom: 1,
    events_checked: 3,
    events_consistent: 2,
    by_source: {
      kalshi: { total: 2, backed: 2, phantom: 0, backed_pct: 100.0 },
      polymarket: { total: 2, backed: 1, phantom: 1, backed_pct: 50.0 },
    },
    misses: [{ event_id: 9101, source: "polymarket", sport: "americanfootball_nfl", matchup: "Jets @ Bills" }],
    window: "NOW-6h..NOW+24h",
    unlinked_held: {
      headline_unlinked_held: 2,
      status: "ok",
      events_checked: 3,
      candidates_scanned: 41,
      derivatives_excluded: 1,
      misses: [
        { event_id: 9102, source: "kalshi", sport: "icehockey_nhl", matchup: "Bruins @ Rangers", market_id: 77, market_name: "Bruins vs Rangers Winner", commence_time: "2026-10-20T23:00:00+00:00" },
        { event_id: 9103, source: "polymarket", sport: "basketball_nba", matchup: "Celtics @ Knicks", market_id: 78, market_name: "Celtics vs. Knicks", commence_time: "2026-10-21T00:00:00+00:00" },
      ],
      by_source: { kalshi: 1, polymarket: 1 },
      definition: "Unlinked-but-held: a Kalshi/Polymarket game-WINNER (moneyline) market we hold whose both teams match an imminent event.",
    },
    generated_at: BUILT,
  };
}

function sportCardsPayload() {
  return {
    schema_version: 1,
    generated_at: BUILT,
    as_of: BUILT,
    observation_finished_at: "2026-10-20T18:48:01+00:00",
    window: { column: "events.commence_time", days: 14, start: "2026-10-06T18:48:00+00:00", start_inclusive: true, end: null },
    transaction: { isolation: "repeatable read", read_only: true },
    accuracy: {
      period_days: 14,
      sports: {
        basketball_nba: { total: 10, sources: { odds_api: 9, espn: 10, statpal: 7 }, commence_time_sources: { odds_api: 6, espn: 4 }, odds_api_linked_pct: 90.0, reliability: "HIGH" },
        icehockey_nhl: { total: 5, sources: { odds_api: 2, espn: 5, statpal: 0 }, commence_time_sources: { espn: 5 }, odds_api_linked_pct: 40.0, reliability: "LOW" },
        americanfootball_nfl: { total: 4, sources: { odds_api: 4, espn: 4, statpal: 4 }, commence_time_sources: { odds_api: 3, null: 1 }, odds_api_linked_pct: 100.0, reliability: "HIGH" },
        soccer_epl: { total: 6, sources: { odds_api: 0, espn: 6, statpal: 6 }, commence_time_sources: { statpal: 6 }, odds_api_linked_pct: 0.0, reliability: "LOW" },
      },
      summary: { total_sports: 4, high_reliability: 2, medium_reliability: 0, low_reliability: 2 },
    },
  };
}

function linkRatePayload(extra: Record<string, unknown> = {}) {
  const row = (sport: string, league: string, open_total: number, open_linked: number) => ({
    sport, league, total: open_total + 2, linked: open_linked + 1, open_total, open_linked,
    link_rate: open_total ? Math.round((open_linked / open_total) * 1000) / 10 : 0,
    link_rate_all: 50.0,
  });
  return {
    overall: { total_game_markets: 120, linked: 90, link_rate_pct: 84.2, open_total: 76, open_linked: 64, link_rate_all_pct: 75.0 },
    kalshi: { totals: { total: 70, linked: 55, open_total: 46, open_linked: 40, link_rate_pct: 87.0, link_rate_all_pct: 78.6 }, by_sport: [row("football", "NFL", 30, 28), row("hockey", "NHL", 16, 12)] },
    polymarket: { totals: { total: 50, linked: 35, open_total: 30, open_linked: 24, link_rate_pct: 80.0, link_rate_all_pct: 70.0 }, by_sport: [row("basketball", "NBA", 30, 24)] },
    generated_at: BUILT,
    ...extra,
  };
}

function siPayload() {
  const buckets = [0, 3, 6, 9].map((idx) => ({ idx, n: 40 + idx, avg_prob: idx / 10 + 0.05, actual: idx / 10 + 0.04 }));
  return {
    generated_at: BUILT,
    coverage: {
      total_events: 1200,
      multi_source_events: 900,
      by_source_count: [{ sources: 1, events: 300 }, { sources: 2, events: 500 }, { sources: 3, events: 400 }],
      by_sport: [
        { sport: "basketball_nba", total: 700, betting: 690, espn: 650, stat_model: 600, kalshi: 300, polymarket: 280, mlb: 0 },
        { sport: "soccer_usa_mls", total: 500, betting: 480, espn: 400, stat_model: 0, kalshi: 20, polymarket: 60, mlb: 0 },
      ],
    },
    source_accuracy: [
      { source: "betting", observations: 1100, brier: 0.198, brier_ci: 0.004, mae: 0.39, buckets },
      { source: "espn", observations: 1000, brier: 0.205, brier_ci: 0.005, mae: 0.4, buckets },
      { source: "stat_model", observations: 600, brier: 0.215, brier_ci: 0.006, mae: 0.41, buckets },
      { source: "kalshi", observations: 300, brier: 0.201, brier_ci: 0.008, mae: 0.39, buckets },
      { source: "polymarket", observations: 280, brier: 0.203, brier_ci: 0.009, mae: 0.4, buckets },
    ],
    disagreements: {
      total_comparisons: 5000,
      rate_5pp: 0.123,
      rate_10pp: 0.041,
      rate_20pp: 0.008,
      by_sport: [{ sport: "basketball_nba", comparisons: 3000, rate_5pp: 0.11 }, { sport: "soccer_usa_mls", comparisons: 2000, rate_5pp: 0.14 }],
      pairwise: [
        { source_a: "betting", source_b: "espn", count: 400, avg_divergence: 0.08, a_closer_pct: 0.61, by_phase: { pre: { comparisons: 200, a_closer_pct: 0.6 } }, by_sport: { basketball_nba: { comparisons: 300, a_closer_pct: 0.62 }, soccer_usa_mls: { comparisons: 15, a_closer_pct: 0.5 } } },
        { source_a: "kalshi", source_b: "polymarket", count: 120, avg_divergence: 0.07, a_closer_pct: 0.45, by_phase: {}, by_sport: { basketball_nba: { comparisons: 120, a_closer_pct: 0.45 } } },
      ],
    },
    case_studies: [
      {
        event_id: 4242, home_team: "Knicks", away_team: "Celtics", sport: "basketball_nba", score: "101-99", home_won: true, max_divergence: 0.31, date: "2026-10-12T23:30:00+00:00",
        series: {
          betting: [{ t: "2026-10-12T23:40:00+00:00", p: 0.45 }, { t: "2026-10-13T00:40:00+00:00", p: 0.7 }],
          espn: [{ t: "2026-10-12T23:40:00+00:00", p: 0.3 }, { t: "2026-10-13T00:40:00+00:00", p: 0.82 }],
        },
      },
    ],
  };
}

/** The `saved_reader_response` envelope, exactly as the backend builds it. */
function envelope(cacheState: string, reason: string, payload: Record<string, unknown> | null, extra: Record<string, unknown> = {}) {
  return {
    schema_version: 1,
    cache_state: cacheState,
    reason,
    freshness: payload ? "unreviewed" : "unknown",
    freshness_basis: "age_from_generated_at_stamped_when_compute_returned",
    served_key: payload ? "bainluck:admin:x" : null,
    served_from: payload ? "primary" : null,
    saved_bytes: payload ? 1234 : null,
    max_saved_bytes: 2097152,
    generated_at: payload ? payload.generated_at : null,
    age_seconds: payload ? 720 : null,
    payload,
    ...extra,
  };
}
/** The link-rate reader's own (older) envelope: no served_* fields. */
function linkEnvelope(cacheState: string, reason: string, payload: Record<string, unknown> | null) {
  return { schema_version: 1, cache_state: cacheState, reason, freshness: payload ? "unreviewed" : "unknown", freshness_basis: "x", generated_at: payload ? payload.generated_at : null, age_seconds: payload ? 720 : null, payload };
}

const ok = (data: unknown, ms = 42): ReadResult => ({ status: "ok", data, ms, httpStatus: 200 });
const pending = (body: unknown): ReadResult => ({ status: "error", kind: "pending", detail: "HTTP 202", ms: 30, httpStatus: 202, body });
const http = (status: number, body?: unknown): ReadResult => ({ status: "error", kind: "http", detail: `HTTP ${status}`, ms: 30, httpStatus: status, body });
const refusedAuth: ReadResult = { status: "error", kind: "unauthorized", detail: "HTTP 403", ms: 12, httpStatus: 403 };

const hitML = () => maturedLinkageSection(ok(envelope("hit", "saved_snapshot", maturedPayload())));
const hitSC = () => sportCardsSection(ok(envelope("hit", "saved_snapshot", sportCardsPayload())));
const hitLR = () => linkRateSection(ok(linkEnvelope("hit", "saved_snapshot", linkRatePayload())));
const hitSI = () => sourceIntelligenceSection(ok(envelope("hit", "saved_snapshot", siPayload())));

const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&gt;/g, ">").replace(/&lt;/g, "<").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/\s+/g, " ");
const renderMatching = (over: Partial<React.ComponentProps<typeof MatchingTabPanel>> = {}, nowMs = NOW) =>
  renderToStaticMarkup(<MatchingTabPanel matured={hitML()} sportCards={hitSC()} linkRate={hitLR()} nowMs={nowMs} {...over} />);

// ── the tab model ───────────────────────────────────────────────────────────

describe("tabs, the URL and the keyboard", () => {
  it("reads the tab from ?tab= and treats anything else as the overview", () => {
    expect(parseConsoleTab("?tab=matching")).toBe("matching");
    expect(parseConsoleTab("?tab=source-intelligence")).toBe("source_intelligence");
    expect(parseConsoleTab("?x=1&tab=matching")).toBe("matching");
    expect(parseConsoleTab("")).toBe("overview");
    expect(parseConsoleTab("?tab=overview")).toBe("overview");
    expect(parseConsoleTab("?tab=../admin")).toBe("overview");
    expect(parseConsoleTab("?tab=source_intelligence")).toBe("overview");
  });

  it("writes ?tab= for a tab, drops it for the overview, and keeps every other parameter", () => {
    expect(consoleTabSearch("", "matching")).toBe("?tab=matching");
    expect(consoleTabSearch("?tab=matching", "source_intelligence")).toBe("?tab=source-intelligence");
    expect(consoleTabSearch("?tab=matching", "overview")).toBe("");
    expect(consoleTabSearch("?debug=1&tab=matching", "overview")).toBe("?debug=1");
    for (const t of CONSOLE_TABS) expect(parseConsoleTab(consoleTabSearch("?debug=1", t.key))).toBe(t.key);
  });

  it("moves with the arrows (wrapping) and jumps with Home/End; other keys do nothing", () => {
    expect(tabAfterKey("ArrowRight", "overview")).toBe("matching");
    expect(tabAfterKey("ArrowRight", "source_intelligence")).toBe("overview");
    expect(tabAfterKey("ArrowLeft", "overview")).toBe("source_intelligence");
    expect(tabAfterKey("Home", "source_intelligence")).toBe("overview");
    expect(tabAfterKey("End", "overview")).toBe("source_intelligence");
    expect(tabAfterKey("Enter", "matching")).toBeNull();
    expect(tabAfterKey("a", "matching")).toBeNull();
  });

  it("draws an accessible tablist: ids, aria-selected/controls and one tab stop", () => {
    const html = renderToStaticMarkup(<ConsoleTabList active="matching" onSelect={() => {}} />);
    expect(html).toContain('role="tablist"');
    expect(html.match(/role="tab"/g)).toHaveLength(3);
    expect(html).toMatch(/id="console-tab-matching"[^>]*aria-selected="true"[^>]*aria-controls="console-panel-matching"[^>]*tabindex="0"/);
    expect(html).toMatch(/id="console-tab-overview"[^>]*aria-selected="false"[^>]*tabindex="-1"/);
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
  });
});

// ── what the tabs read, and when ────────────────────────────────────────────

describe("eligibility and laziness of the tab reads", () => {
  it("reads only the three saved-only readers, plainly", () => {
    expect(TAB_READ_ENDPOINTS).toEqual({
      maturedLinkage: "/api/admin/prediction-markets/matured-linkage/cached",
      sportCards: "/api/admin/schedule/accuracy/cached",
      sourceIntelligence: "/api/admin/source-intelligence/cached",
    });
    for (const p of Object.values(TAB_READ_ENDPOINTS)) {
      expect(p).not.toContain("?");
      expect(p.endsWith("/cached")).toBe(true);
    }
  });

  it("Matching reuses the overview's link-rate read: no tab group sends a link-rate request", () => {
    expect(TAB_READ_GROUPS).toEqual({ matching: ["maturedLinkage", "sportCards"], source_intelligence: ["sourceIntelligence"] });
    const all = Object.values(TAB_READ_GROUPS).flat() as string[];
    expect(all).not.toContain("linkRate");
    expect(Object.values(TAB_READ_ENDPOINTS)).not.toContain(CORRECTNESS_ENDPOINTS.linkRate);
  });

  it("the overview starts no tab read; a tab starts its group once per round", () => {
    expect(tabKeysToStart("overview", new Set())).toEqual([]);
    expect(tabKeysToStart("matching", new Set())).toEqual(["maturedLinkage", "sportCards"]);
    expect(tabKeysToStart("matching", new Set<TabReadKey>(["maturedLinkage", "sportCards"]))).toEqual([]);
    expect(tabKeysToStart("source_intelligence", new Set<TabReadKey>(["maturedLinkage"]))).toEqual(["sourceIntelligence"]);
  });

  it("starts only the keys asked for, reports each as it settles, and never retries", async () => {
    const calls: string[] = [];
    const seen: string[] = [];
    await startTabReads(
      ["sourceIntelligence"],
      (key) => async () => {
        calls.push(key);
        return new Response(JSON.stringify(envelope("miss", "no_saved_snapshot_or_retained_copy", null)), { status: 202 });
      },
      (key, r) => seen.push(`${key}:${r.status === "error" ? r.kind : r.status}`),
    );
    expect(calls).toEqual(["sourceIntelligence"]);
    expect(seen).toEqual(["sourceIntelligence:pending"]);
  });

  it("is bounded: a read that never answers times out once and is not repeated", async () => {
    let calls = 0;
    const seen: ReadResult[] = [];
    await startTabReads(
      ["maturedLinkage"],
      () => (signal) => {
        calls += 1;
        return new Promise<Response>((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
      },
      (_, r) => seen.push(r),
      { timeoutMs: 20 },
    );
    expect(calls).toBe(1);
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ status: "error", kind: "timeout" });
  });

  it("drops every answer from an aborted round (Reload, unmount, a new credential)", async () => {
    const ctrl = new AbortController();
    const seen: string[] = [];
    const run = startTabReads(
      ["maturedLinkage", "sportCards"],
      () => async (signal) => {
        ctrl.abort();
        if (signal.aborted) throw new Error("aborted");
        return new Response("{}", { status: 200 });
      },
      (key) => seen.push(key),
      { signal: ctrl.signal },
    );
    await run;
    expect(seen).toEqual([]);
  });
});

// ── the saved-reader envelope ───────────────────────────────────────────────

describe("each section shows numbers only for a checked hit", () => {
  it("a hit carries the payload, its clock and which record answered", () => {
    const s = hitML();
    expect(s.kind).toBe("hit");
    if (s.kind !== "hit") return;
    expect(s.data.headline_pct).toBe(75);
    expect(s.generatedAt).toBe(BUILT);
    expect(s.servedFrom).toBe("primary");
    expect(sectionState(s)).toBe("freshness_unknown");
  });

  it.each([
    ["miss", 202, pending],
    ["error", 503, (b: unknown) => http(503, b)],
    ["oversized", 503, (b: unknown) => http(503, b)],
    ["malformed", 503, (b: unknown) => http(503, b)],
  ] as const)("cache_state %s (HTTP %d) is absent, with its reason and no numbers", (state, status, as) => {
    expect(SAVED_READER_CACHE_STATUS[state]).toBe(status);
    for (const parse of [maturedLinkageSection, sportCardsSection, sourceIntelligenceSection]) {
      const s = parse(as(envelope(state, `why_${state}`, null)));
      expect(s).toMatchObject({ kind: "absent", cacheState: state, reason: `why_${state}` });
      expect(sectionState(s)).toBe("unavailable");
    }
  });

  it("refuses a cache_state sent under the wrong HTTP status", () => {
    const s = maturedLinkageSection(ok(envelope("miss", "no_saved_snapshot", null)));
    expect(s).toMatchObject({ kind: "refused" });
    expect(maturedLinkageSection(pending(envelope("hit", "saved_snapshot", maturedPayload())))).toMatchObject({ kind: "refused" });
  });

  it("a failed read without the contract is a failed read; a refused credential is not a statement about data", () => {
    expect(maturedLinkageSection(http(500))).toMatchObject({ kind: "failed" });
    expect(maturedLinkageSection({ status: "error", kind: "timeout", detail: "no answer", ms: 10000 })).toMatchObject({ kind: "failed" });
    expect(sourceIntelligenceSection(refusedAuth)).toMatchObject({ kind: "unauthorized" });
    expect(sectionState(sourceIntelligenceSection(refusedAuth))).toBe("unauthorized");
    expect(sportCardsSection({ status: "loading" })).toEqual({ kind: "loading" });
    expect(sportCardsSection(ok({ sports: {} }))).toMatchObject({ kind: "refused", what: "not the saved-evidence contract" });
  });

  it("only Source Intelligence may serve the retained copy, and says so", () => {
    const retained = envelope("hit", "primary_missing_served_retained_copy", siPayload(), { served_from: "retained_stale" });
    const si = sourceIntelligenceSection(ok(retained));
    expect(si).toMatchObject({ kind: "hit", servedFrom: "retained_stale" });
    const ml = maturedLinkageSection(ok(envelope("hit", "saved_snapshot", maturedPayload(), { served_from: "retained_stale" })));
    expect(ml).toMatchObject({ kind: "refused", what: "unknown served_from" });
  });

  it("refuses a hit whose envelope clock is not its payload's", () => {
    const body = envelope("hit", "saved_snapshot", maturedPayload(), { generated_at: "2026-10-20T18:00:00+00:00" });
    expect(maturedLinkageSection(ok(body))).toMatchObject({ kind: "refused" });
  });

  it("the link-rate section reads the overview's envelope, including its stale marker and its no-data state", () => {
    const stale = linkRateSection(ok(linkEnvelope("hit", "saved_snapshot_marked_stale", linkRatePayload({ stale: true, stale_reason: "compute_timeout" }))));
    expect(stale).toMatchObject({ kind: "hit", staleReason: "compute_timeout" });
    expect(sectionState(stale)).toBe("stale");
    const none = linkRateSection(http(503, linkEnvelope("unavailable", "saved_snapshot_unavailable", { unavailable: true, stale_reason: "no_rows", generated_at: BUILT })));
    expect(none).toMatchObject({ kind: "absent", cacheState: "unavailable", reason: "no_rows" });
  });
});

describe("payload checks refuse what the view would misdraw (each beside its unmutated control)", () => {
  type Case = [string, (p: Record<string, unknown>) => void, (r: ReadResult) => { kind: string }, () => Record<string, unknown>];
  const cases: Case[] = [
    ["misses do not reconcile with phantoms", (p) => { (p.misses as unknown[]).pop(); }, maturedLinkageSection, maturedPayload],
    ["backed + phantom is not the denominator", (p) => { p.backed = 4; }, maturedLinkageSection, maturedPayload],
    ["a 100% headline over an empty slate", (p) => { p.status = "insufficient_slate"; }, maturedLinkageSection, maturedPayload],
    ["unlinked_held misses do not reconcile", (p) => { (p.unlinked_held as { headline_unlinked_held: number }).headline_unlinked_held = 5; }, maturedLinkageSection, maturedPayload],
    ["a miss without its matchup", (p) => { delete (p.misses as Record<string, unknown>[])[0].matchup; }, maturedLinkageSection, maturedPayload],
    // Internally consistent zero (every count 0, empty provenance), so only the
    // denominator rule can refuse it: a zero card is a defect, never a measurement.
    ["a sport card with a zero denominator", (p) => { (p.accuracy as { sports: Record<string, unknown> }).sports.basketball_nba = { total: 0, sources: { odds_api: 0, espn: 0, statpal: 0 }, commence_time_sources: {}, odds_api_linked_pct: 0, reliability: "LOW" }; }, sportCardsSection, sportCardsPayload],
    ["a source count above its total", (p) => { ((p.accuracy as { sports: Record<string, { sources: { espn: number } }> }).sports.basketball_nba).sources.espn = 11; }, sportCardsSection, sportCardsPayload],
    ["a 7-day window", (p) => { (p.window as { days: number }).days = 7; }, sportCardsSection, sportCardsPayload],
    ["a window start that is not 14 days before as_of", (p) => { (p.window as { start: string }).start = "2026-10-07T18:48:00+00:00"; }, sportCardsSection, sportCardsPayload],
    ["a window with an upper bound", (p) => { (p.window as { end: string | null }).end = BUILT; }, sportCardsSection, sportCardsPayload],
    ["provenance that does not sum to the total", (p) => { ((p.accuracy as { sports: Record<string, { commence_time_sources: Record<string, number> }> }).sports.icehockey_nhl).commence_time_sources.espn = 4; }, sportCardsSection, sportCardsPayload],
    ["coverage that does not reconcile", (p) => { (p.coverage as { total_events: number }).total_events = 1300; }, sourceIntelligenceSection, siPayload],
    ["a Brier score outside [0,1]", (p) => { (p.source_accuracy as { brier: number }[])[0].brier = 1.2; }, sourceIntelligenceSection, siPayload],
    ["a calibration bucket past idx 9", (p) => { (p.source_accuracy as { buckets: { idx: number }[] }[])[0].buckets[0].idx = 10; }, sourceIntelligenceSection, siPayload],
    ["a pairwise sport cell without a count", (p) => { delete ((p.disagreements as { pairwise: { by_sport: Record<string, Record<string, unknown>> }[] }).pairwise[0].by_sport.basketball_nba).comparisons; }, sourceIntelligenceSection, siPayload],
    ["a case-study point that is not a number", (p) => { ((p.case_studies as { series: Record<string, { p: unknown }[]> }[])[0].series.betting[0]).p = "0.4"; }, sourceIntelligenceSection, siPayload],
  ];
  it.each(cases)("%s", (_name, mutate, parse, make) => {
    const control = make();
    expect(parse(ok(envelope("hit", "saved_snapshot", control))).kind).toBe("hit");
    const bad = clone(control);
    mutate(bad);
    expect(parse(ok(envelope("hit", "saved_snapshot", bad))).kind).toBe("refused");
  });
});

// ── Matching tab parity ─────────────────────────────────────────────────────

describe("the Matching tab carries the whole Matching view", () => {
  it("renders the headline, misses, unlinked-held, the 14-day sport cards, the venue diagnostic and the static sections", () => {
    const html = renderMatching();
    const t = text(html);
    // header + verdict as history
    expect(t).toContain("Are events properly linked across data sources?");
    expect(t).toContain("15/19 Tier 1 events have Odds API data (79%)"); // nba 9/10 + nhl 2/5 + nfl 4/4; NCAAB absent
    expect(t).toContain("The saved sport cards read was Watch — not a current verdict.");
    expect(t).not.toMatch(/\bHealthy\b/);
    // matured linkage
    expect(html).toContain('data-section="matured-linkage"');
    expect(t).toContain("75%");
    expect(t).toContain("3/4 imminent blend sources linked · 2/3 events consistent");
    expect(t).toContain("americanfootball_nfl: Jets @ Bills — polymarket in blend, no linked market");
    // unlinked held
    expect(html).toContain('data-held-state="ok"');
    expect(t).toContain('icehockey_nhl: Bruins @ Rangers — kalshi market "Bruins vs Rangers Winner" held, not linked');
    expect(t).toContain("3 imminent events checked · 41 unlinked open markets scanned · 1 derivative markets excluded");
    // tier-1 cards: every sport the snapshot has, none it lacks
    for (const k of ["basketball_nba", "icehockey_nhl", "americanfootball_nfl"]) expect(html).toContain(`data-sport-card="${k}"`);
    expect(html).not.toContain('data-sport-card="basketball_ncaab"');
    expect(t).toContain("9/10 (90%)");
    expect(t).toContain("2/5 (40%)");
    expect(t).toContain("10 events (14 days)");
    expect(t).toContain("Do Tier 2 sports have sportsbook coverage?");
    // link-rate diagnostic (collapsed when its legacy status is good; summary still carries counts)
    expect(t).toContain("64/76 open game markets linked (84.2%) — diagnostic, not the headline");
    // static sections are in the tab
    expect(t).toContain("What does each source contribute?");
  });

  it("states provenance for every data section, with the sport-card window and no-upper-bound", () => {
    const t = text(renderMatching());
    expect(t).toContain("Matured linkage: Saved snapshot, built 12 min ago · freshness unreviewed");
    expect(t).toContain("Sport cards: Saved snapshot, built 12 min ago");
    expect(t).toContain("events with commence_time ≥ 2026-10-06T18:48:00Z (14 days before the snapshot), no upper bound — future games count");
    expect(t).toContain("Game-market link rate: Saved snapshot, built 12 min ago");
    expect(t).toContain(TAB_READ_ENDPOINTS.maturedLinkage);
    expect(t).toContain(TAB_READ_ENDPOINTS.sportCards);
    expect(t).toContain(CORRECTNESS_ENDPOINTS.linkRate);
  });

  it("mutes every section-level verdict: no live green dot or tick on saved data", () => {
    const html = renderMatching();
    expect(html.match(/data-verdict-muted=""/g)?.length).toBe(4);
    expect(html).not.toContain("w-2 h-2 rounded-full shrink-0 bg-accent-live");
  });

  it("ages with the page's local clock, and never prints an age for a build ahead of it", () => {
    expect(text(renderMatching({}, NOW + 2 * 3600_000))).toContain("Matured linkage: Saved snapshot, built 2 h ago");
    expect(text(renderMatching({}, Date.parse(BUILT) - 3600_000))).toContain("built ahead of this browser's clock");
  });

  it("lists every miss, folding past the first eight", () => {
    const p: Record<string, unknown> = maturedPayload();
    p.misses = Array.from({ length: 11 }, (_, i) => ({ event_id: 9200 + i, source: "kalshi", sport: "baseball_mlb", matchup: `Team${i} @ Home${i}` }));
    p.phantom = 11;
    p.checkable_pairs = 14;
    p.headline_pct = 21.4;
    p.by_source = { kalshi: { total: 14, backed: 3, phantom: 11, backed_pct: 21.4 } };
    const html = renderMatching({ matured: maturedLinkageSection(ok(envelope("hit", "saved_snapshot", p))) });
    expect(text(html)).toContain("Show all 11");
    for (let i = 0; i < 11; i++) expect(text(html)).toContain(`Team${i} @ Home${i}`);
  });

  it("an unlinked-held check that failed in the snapshot is unverified, not zero", () => {
    const p = maturedPayload() as Record<string, unknown>;
    p.unlinked_held = { status: "error", error: "statement timeout" };
    const html = renderMatching({ matured: maturedLinkageSection(ok(envelope("hit", "saved_snapshot_with_unlinked_held_error", p))) });
    expect(html).toContain('data-held-state="error"');
    expect(text(html)).toContain("Unverified — this check failed when the snapshot was built (statement timeout)");
  });

  it.each([
    ["miss", pending(envelope("miss", "no_saved_snapshot", null)), "nothing is saved yet, and this page does not compute it (no_saved_snapshot)"],
    ["oversized", http(503, envelope("oversized", "saved_snapshot_exceeds_read_bound", null)), "larger than the read bound"],
    ["malformed", http(503, envelope("malformed", "invalid_window", null)), "refused as malformed (invalid_window)"],
    ["timeout", { status: "error", kind: "timeout", detail: "no answer within 10000 ms", ms: 10000 } as ReadResult, "Unverified — the read failed (no answer within 10000 ms)"],
  ])("sport cards %s: a notice in place of every card, never a zero card", (_n, read, words) => {
    const html = renderMatching({ sportCards: sportCardsSection(read) });
    const t = text(html);
    expect(t).toContain(words);
    expect(html).not.toContain("data-sport-card");
    expect(t).not.toMatch(/0\/0/);
    expect(t).not.toContain("Tier 1 events have Odds API data");
    expect(html).toMatch(/data-tab-header="" data-state="partial"/);
    // its siblings still render
    expect(t).toContain("75%");
    expect(t).toContain("64/76 open game markets linked");
  });

  it("matured linkage absent: one notice for the headline and unlinked-held, siblings intact", () => {
    const html = renderMatching({ matured: maturedLinkageSection(pending(envelope("miss", "no_saved_snapshot", null))) });
    expect(html).toContain('data-notice="matured-linkage"');
    expect(html).not.toContain("data-held-state");
    expect(text(html)).not.toMatch(/\b75%/);
    expect(html).toContain('data-sport-card="basketball_nba"');
  });

  it("link rate still reading: the diagnostic says Loading, no venue cards", () => {
    const html = renderMatching({ linkRate: linkRateSection(INITIAL_READS.linkRate) });
    expect(html).not.toContain("data-venue-card");
    expect(text(html)).toContain("Diagnostic: all-market coverage (Kalshi/Polymarket → events) Loading...");
  });

  it("link rate absent: the diagnostic opens on the notice instead of venue cards", () => {
    const html = renderMatching({ linkRate: linkRateSection(pending(linkEnvelope("miss", "no_saved_snapshot", null))) });
    expect(html).toContain('data-notice="link-rate"');
    expect(html).not.toContain("data-venue-card");
    expect(text(html)).toContain("nothing is saved yet, and this page does not compute it (no_saved_snapshot)");
  });

  it("a refused credential everywhere: not-authorized, with the auth notice, and no numbers", () => {
    const html = renderMatching({
      matured: maturedLinkageSection(refusedAuth),
      sportCards: sportCardsSection(refusedAuth),
      linkRate: linkRateSection(refusedAuth),
      authNotice: <div data-auth-notice="" />,
    });
    expect(html).toMatch(/data-tab-header="" data-state="unauthorized"/);
    expect(html).toContain("data-auth-notice");
    expect(html).not.toContain("data-sport-card");
    expect(html).not.toContain("data-venue-card");
  });

  it("while reading: loading, never a verdict", () => {
    const html = renderMatching({ matured: maturedLinkageSection(INITIAL_TAB_READS.maturedLinkage), sportCards: sportCardsSection(INITIAL_TAB_READS.sportCards) });
    expect(html).toMatch(/data-tab-header="" data-state="loading"/);
    expect(html).not.toContain("not a current verdict.");
  });
});

// ── Source Intelligence tab parity ──────────────────────────────────────────

describe("the Source Intelligence tab carries the whole view", () => {
  const render = (si = hitSI(), nowMs = NOW) => renderToStaticMarkup(<SourceIntelligenceTabPanel si={si} nowMs={nowMs} />);

  it("renders stat cards, coverage heatmap, Brier + calibration curves, disagreement rates, leaderboard, pairwise table, case-study chart and methodology", () => {
    const html = render();
    const t = text(html);
    for (const title of ["The Data", "Source Accuracy", "When Sources Disagree", "Who Was Right?", "Dramatic Disagreements", "Methodology"]) {
      expect(html).toContain(`data-section="${title}"`);
    }
    expect(t).toContain("1,200 Events Analyzed");
    expect(t).toContain("75% of events");
    expect(t).toContain("Events by Number of Sources");
    expect(t).toContain("NBA");
    expect(t).toContain("MLS");
    expect(t).toContain("0.198 ± 0.004");
    expect(t).toContain("n=1,100");
    expect(html).toContain("<svg"); // calibration + disagreement charts
    expect(t).toContain("Sources diverge >5pp in 12.3% of matched observations");
    expect(t).toContain("Head-to-Head Leaderboard");
    expect(t).toContain("Pairwise Head-to-Head");
    expect(t).toContain("61.0%");
    expect(html).toContain('href="/events/4242"');
    expect(t).toContain("31pp peak divergence");
    expect(t).toContain("Well-covered events only.");
    // the verdict, as history
    expect(t).toContain("The saved snapshot read was OK — not a current verdict.");
    expect(t).not.toMatch(/\bHealthy\b/);
  });

  it("the pairwise filter offers every sport in the payload (local filtering, no request)", () => {
    const html = render();
    expect(html).toContain('<option value="all" selected="">All Sports</option>');
    expect(html).toContain('<option value="basketball_nba">NBA</option>');
    expect(html).toContain('<option value="soccer_usa_mls">MLS</option>');
  });

  it("names a dark core source as history, with the legacy action note", () => {
    const p = siPayload();
    p.source_accuracy = p.source_accuracy.filter((s) => s.source !== "kalshi");
    const t = text(render(sourceIntelligenceSection(ok(envelope("hit", "saved_snapshot", p)))));
    expect(t).toContain("Kalshi reports zero measured observations across all sports");
    expect(t).toContain("The saved snapshot read was Watch — not a current verdict.");
  });

  it("says when it is showing the retained copy, and how old that copy is", () => {
    const retained = envelope("hit", "primary_missing_served_retained_copy", { ...siPayload(), generated_at: "2026-10-20T13:30:00+00:00" }, { served_from: "retained_stale", generated_at: "2026-10-20T13:30:00+00:00" });
    const html = render(sourceIntelligenceSection(ok(retained)));
    expect(html).toContain('data-served-from="retained_stale"');
    expect(text(html)).toContain("Retained copy — the primary snapshot was missing, so the previous build's copy is shown, built 6 h ago");
  });

  it.each([
    ["miss", pending(envelope("miss", "no_saved_snapshot_or_retained_copy", null)), "nothing is saved yet"],
    ["error", http(503, envelope("error", "read_deadline_exceeded", null)), "could not be read (read_deadline_exceeded)"],
    ["refused", ok(envelope("hit", "saved_snapshot", { generated_at: BUILT, coverage: {} })), "this page refused the saved snapshot"],
    ["unauthorized", refusedAuth, "Not authorized"],
  ])("%s: a notice and no numbers", (_n, read, words) => {
    const html = render(sourceIntelligenceSection(read));
    expect(text(html)).toContain(words);
    expect(html).not.toContain('data-section="The Data"');
    expect(html).not.toContain("<svg");
  });
});

// ── the console with its tabs ───────────────────────────────────────────────

describe("the console view with tabs", () => {
  const tiles = evaluateAll(INITIAL_READS, NOW);
  const view = (active: "overview" | "matching" | "source_intelligence", panels = {}) =>
    renderToStaticMarkup(<CorrectnessConsoleView tiles={tiles} nowMs={NOW} settledMs={null} tabs={{ active, onSelect: () => {}, panels }} />);

  it("keeps the overview's tiles in the page while another tab is shown — hidden, not wiped", () => {
    const html = view("matching", { matching: <div data-x="m" /> });
    expect(html).toMatch(/role="tabpanel" id="console-panel-overview" aria-labelledby="console-tab-overview" hidden=""/);
    // No tabpanel may carry a display utility: `grid`/`flex`/`block` beat the
    // hidden attribute's display:none and draw a hidden panel anyway.
    for (const tag of html.match(/<div[^>]*role="tabpanel"[^>]*>/g) ?? []) {
      expect(tag).not.toMatch(/class="[^"]*\b(grid|flex|block|inline-block|table)\b/);
    }
    expect(html.match(/data-tile="/g)).toHaveLength(tiles.length);
    expect(html).toMatch(/id="console-panel-matching"[^>]*data-panel="matching"><div data-x="m">/);
    expect(html).not.toMatch(/id="console-panel-matching"[^>]*hidden/);
  });

  it("a tab never shown has an empty panel: nothing mounted behind it", () => {
    const html = view("overview");
    expect(html).toMatch(/id="console-panel-matching"[^>]*hidden=""[^>]*data-panel="matching"><\/div>/);
    expect(html).toMatch(/id="console-panel-source_intelligence"[^>]*hidden=""[^>]*data-panel="source_intelligence"><\/div>/);
  });

  it("without tabs it is the overview exactly as before", () => {
    const html = renderToStaticMarkup(<CorrectnessConsoleView tiles={tiles} nowMs={NOW} settledMs={null} />);
    expect(html).not.toContain('role="tab');
  });
});

// ── shared presentation and source guards ───────────────────────────────────

describe("one presentation, two routes, no extra tracking or computation", () => {
  const root = path.join(__dirname, "..");
  const code = (rel: string) =>
    fs
      .readFileSync(path.join(root, rel), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  const page = code("app/admin/correctness/page.tsx");
  const tabsLib = code("lib/correctnessConsoleTabs.ts");
  const panels = code("components/admin/CorrectnessConsoleTabs.tsx");
  const matchingView = code("app/admin/_views/MatchingView.tsx");
  const siView = code("app/admin/_views/SourceIntelligenceView.tsx");
  const legacyMatching = code("app/admin/matching/page.tsx");
  const legacySI = code("app/admin/source-intelligence/page.tsx");

  it("only the console imports the carried-over views; the standalone pages stay their own", () => {
    // A module two routes import becomes a numbered SHARED chunk, which the
    // shipped-copy gate (ruling 141) reads as a reader surface. One importer
    // keeps this staff copy inside the app/admin/correctness route chunk.
    expect(legacyMatching).not.toContain("_views/");
    expect(legacySI).not.toContain("_views/");
    // Runtime importers only: a type-only import emits no code into any chunk.
    const importers: string[] = [];
    const walk = (d: string) => {
      for (const e of fs.readdirSync(path.join(root, d), { withFileTypes: true })) {
        const rel = path.join(d, e.name);
        if (e.isDirectory()) walk(rel);
        else if (/\.(ts|tsx)$/.test(e.name)) {
          const runtime = code(rel).match(/^import (?!type )[\s\S]*?from "@\/app\/admin\/_views\/[^"]+";/gm) ?? [];
          if (runtime.length > 0) importers.push(rel);
        }
      }
    };
    for (const d of ["app", "components", "lib", "hooks"]) walk(d);
    expect(importers).toEqual(["components/admin/CorrectnessConsoleTabs.tsx"]);
  });

  /**
   * PARITY OF COPY. Every reader-visible sentence on the standalone pages —
   * JSX text and string literals — is carried by the tab's views, so the tab
   * cannot quietly lose a section, a caveat or an action note. The few legacy
   * strings that are not carried are listed with the reason.
   */
  const NOT_CARRIED: Record<string, string> = {
    "Loading analysis...": "the tab's typed loading notice replaces the page-level spinner",
    "Admin: Data Quality — Matching": "the standalone page's GA title; the console tracks itself once",
  };

  const sentences = (src: string): string[] => {
    const out = new Set<string>();
    const norm = (x: string) => x.replace(/\s+/g, " ").trim();
    for (const m of src.matchAll(/>([^<>{}]+)</g)) out.add(norm(m[1]));
    for (const m of src.matchAll(/"([^"\n]{12,})"/g)) out.add(norm(m[1]));
    // Copy only: drop className strings and the code a `>=` comparison drags in.
    return [...out].filter((x) => x.length >= 12 && / /.test(x) && /[A-Za-z]{3}/.test(x) && !/[=;]/.test(x) && !/^[:?]/.test(x) && !/^[:?]/.test(x) && !/^[a-z0-9:\-/[\].% ]+$/.test(x));
  };
  it.each([
    ["/admin/matching", () => legacyMatching, () => matchingView + panels],
    ["/admin/source-intelligence", () => legacySI, () => siView + panels],
  ])("every reader-visible sentence of %s is carried into the tab", (_route, legacy, carried) => {
    const have = carried().replace(/\s+/g, " ");
    const all = sentences(legacy());
    // Non-vacuity: the extractor really reads the page's copy.
    expect(all.length).toBeGreaterThan(20);
    const missing = all.filter((x) => !have.includes(x) && !(x in NOT_CARRIED));
    expect(missing).toEqual([]);
  });

  it("every NOT_CARRIED exclusion is still needed — the list cannot grow stale or hide a carried line", () => {
    const legacyAll = [...sentences(legacyMatching), ...sentences(legacySI)];
    const have = (matchingView + siView + panels).replace(/\s+/g, " ");
    const wrong = Object.keys(NOT_CARRIED).filter((k) => !legacyAll.includes(k) || have.includes(k));
    expect(wrong).toEqual([]);
  });

  it("the shared views and panels track nothing and fetch nothing", () => {
    for (const src of [matchingView, siView, panels]) {
      expect(src).not.toMatch(/usePageTracking|useScrollDepth|useEngagementTime|useSWR|adminFetch|fetch\(|useAdminAuth/);
    }
  });

  it("each route keeps its own three GA4 hooks before any return", () => {
    for (const src of [page, legacyMatching, legacySI]) {
      const body = src.slice(src.indexOf("export default function"));
      const firstReturn = body.indexOf("return");
      for (const hook of ["usePageTracking(", "useScrollDepth(", "useEngagementTime("]) {
        const at = body.indexOf(hook);
        expect(at).toBeGreaterThan(-1);
        expect(at).toBeLessThan(firstReturn);
      }
    }
  });

  it("the standalone routes still read their own endpoints (removing them is out of scope)", () => {
    expect(legacyMatching).toContain('"/api/admin/schedule/accuracy?days=14"');
    expect(legacyMatching).toContain('"/api/admin/prediction-markets/link-rate"');
    expect(legacyMatching).toContain('"/api/admin/prediction-markets/matured-linkage"');
    expect(legacySI).toContain("fetchSourceIntelligence");
  });

  it("the console never names a computing route, a refresh/bust input or a producer", () => {
    const all = page + tabsLib + panels;
    expect(all).not.toMatch(/\/schedule\/accuracy(?!\/cached)/);
    expect(all).not.toMatch(/\/matured-linkage(?!\/cached)/);
    expect(all).not.toMatch(/["'`]\/api\/source-intelligence/);
    expect(all).not.toMatch(/fetchSourceIntelligence|refresh=|bust|force=|days=|warm|enqueue|send_task|\.delay\(/i);
    expect(all).not.toMatch(/method:\s*["'`]?(?:POST|PUT|PATCH|DELETE)/i);
    expect(page).not.toContain("setInterval");
  });

  it("tab reads carry the credential as a header, with the round's abort signal", () => {
    expect(page).toContain("adminFetch(TAB_READ_ENDPOINTS[key], secret, { signal, cache: \"no-store\" })");
    expect(page).toMatch(/startTabReads\([\s\S]*\{ signal: current\.ctrl\.signal \}/);
    expect(page + tabsLib).not.toMatch(/[?&]secret=/);
  });

  it("each panel is handed only its own reads, so a late answer cannot render under another view", () => {
    const si = page.slice(page.indexOf("<SourceIntelligenceTabPanel"), page.indexOf("/>", page.indexOf("<SourceIntelligenceTabPanel")));
    expect(si).not.toMatch(/matured|sportCards|linkRate/);
    const m = page.slice(page.indexOf("<MatchingTabPanel"), page.indexOf("/>", page.indexOf("<MatchingTabPanel")));
    expect(m).not.toMatch(/\bsi\b|sourceIntelligence/);
    expect(page).toContain("const linkRate = useMemo(() => linkRateSection(reads.linkRate), [reads.linkRate]);");
  });

  it("Back and Refresh ride the URL: pushState on select, popstate restores, the initial tab is read from it", () => {
    expect(page).toContain("window.history.pushState(window.history.state, \"\", url)");
    expect(page).toContain('window.addEventListener("popstate", onPop)');
    expect(page).toContain("parseConsoleTab(window.location.search)");
  });

  it("the shared Source Intelligence view renders standalone with a legacy-style header (regression)", () => {
    const si = hitSI();
    if (si.kind !== "hit") throw new Error("fixture must parse");
    const html = renderToStaticMarkup(<SourceIntelligenceView data={si.data} header={<h1>legacy header</h1>} updated={<p>Updated</p>} />);
    expect(html).toContain("legacy header");
    expect(html).toContain('data-section="Methodology"');
  });

  it("no reader-facing 'book(s)/bookmaker' wording reaches either tab", () => {
    const html = renderMatching() + renderToStaticMarkup(<SourceIntelligenceTabPanel si={hitSI()} nowMs={NOW} />);
    expect(text(html)).not.toMatch(/\bbook(s|maker|makers)\b/i);
  });
});
