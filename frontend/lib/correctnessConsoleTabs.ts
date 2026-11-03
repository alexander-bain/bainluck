// #847 — the Correctness Console's Matching and Source Intelligence tabs.
//
// The tabs carry the full `/admin/matching` and `/admin/source-intelligence`
// views, read ONLY from saved evidence:
//
//   Matching            matured-linkage headline + misses + unlinked-held
//                         → `/prediction-markets/matured-linkage/cached`
//                       the 14-day Tier-1/Tier-2 sport cards
//                         → `/schedule/accuracy/cached`
//                       the all-market Kalshi/Polymarket diagnostic
//                         → the overview's OWN `/link-rate/cached` read, reused:
//                           the tab sends no second link-rate request
//   Source Intelligence → `/source-intelligence/cached` (primary, or the
//                           retained copy when the primary is missing)
//
// None of those routes computes, warms a cache or starts a producer; the legacy
// GETs those pages use do (inline compute on a miss, or per-call aggregates),
// and are never read from here — not even as a fallback.
//
// LAZY AND ISOLATED. The overview's six reads are unchanged. A tab's reads start
// the first time that tab is shown in a round (Reload starts a new round), each
// is one bounded attempt with the overview's deadline and no retry, and every
// result is stored under its own read key — so a late answer can only ever
// render inside the panel that asked for it.
//
// THE SAME RULE AS THE TILES. A section shows numbers only for a `hit` whose
// payload this module has checked. A miss, a refused or oversized snapshot, a
// failed read or a refused credential is shown as exactly that, with no numbers.
// No saved payload here carries a reviewed freshness horizon, so a hit is never
// called current: the view's own colours are labelled as what the snapshot
// read, and its age keeps moving with the page's local clock.

import type {
  AccuracyData,
  LinkRateData,
  MaturedLinkageData,
  UnlinkedHeld,
} from "@/app/admin/_views/MatchingView";
import type { SourceIntelligenceData } from "@/lib/api";
import {
  LINK_RATE_CACHE_STATUS,
  SOURCE_CLOCK_SKEW_S,
  ageSeconds,
  boundedRead,
  formatAge,
  type CorrectnessState,
  type ReadResult,
} from "@/lib/correctnessConsole";

// ─── Tabs, the URL and the keyboard ─────────────────────────────────────────

export type ConsoleTab = "overview" | "matching" | "source_intelligence";

export const CONSOLE_TABS: readonly { key: ConsoleTab; label: string; param: string | null }[] = [
  { key: "overview", label: "Overview", param: null },
  { key: "matching", label: "Matching", param: "matching" },
  { key: "source_intelligence", label: "Source Intelligence", param: "source-intelligence" },
];

export const TAB_QUERY_PARAM = "tab";

/** The tab a URL names. Anything unknown is the overview — never an error page. */
export function parseConsoleTab(search: string): ConsoleTab {
  const param = new URLSearchParams(search).get(TAB_QUERY_PARAM);
  return CONSOLE_TABS.find((t) => t.param !== null && t.param === param)?.key ?? "overview";
}

/** The query string for `tab`, keeping every other parameter as it was. */
export function consoleTabSearch(search: string, tab: ConsoleTab): string {
  const params = new URLSearchParams(search);
  const param = CONSOLE_TABS.find((t) => t.key === tab)?.param ?? null;
  if (param === null) params.delete(TAB_QUERY_PARAM);
  else params.set(TAB_QUERY_PARAM, param);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** WAI-ARIA tabs: arrows move (and wrap), Home/End jump. Other keys: null. */
export function tabAfterKey(key: string, current: ConsoleTab): ConsoleTab | null {
  const i = CONSOLE_TABS.findIndex((t) => t.key === current);
  const n = CONSOLE_TABS.length;
  switch (key) {
    case "ArrowRight":
      return CONSOLE_TABS[(i + 1) % n].key;
    case "ArrowLeft":
      return CONSOLE_TABS[(i - 1 + n) % n].key;
    case "Home":
      return CONSOLE_TABS[0].key;
    case "End":
      return CONSOLE_TABS[n - 1].key;
    default:
      return null;
  }
}

export const tabId = (tab: ConsoleTab) => `console-tab-${tab}`;
export const panelId = (tab: ConsoleTab) => `console-panel-${tab}`;

// ─── The tab reads ──────────────────────────────────────────────────────────

export type TabReadKey = "maturedLinkage" | "sportCards" | "sourceIntelligence";

/** GET only; no bust/refresh/days parameter exists on these routes or is sent. */
export const TAB_READ_ENDPOINTS = {
  maturedLinkage: "/api/admin/prediction-markets/matured-linkage/cached",
  sportCards: "/api/admin/schedule/accuracy/cached",
  sourceIntelligence: "/api/admin/source-intelligence/cached",
} as const satisfies Record<TabReadKey, string>;

/**
 * Which reads a tab starts. Matching's link-rate section is NOT here: it is the
 * overview's `linkRate` read, already in flight from the moment the page opens.
 */
export const TAB_READ_GROUPS: Record<Exclude<ConsoleTab, "overview">, readonly TabReadKey[]> = {
  matching: ["maturedLinkage", "sportCards"],
  source_intelligence: ["sourceIntelligence"],
};

/**
 * The reads to start when `tab` is shown: its group minus what this round has
 * already started. The overview starts nothing here — its six reads are the
 * page's own — and a tab shown twice in one round is never read twice.
 */
export function tabKeysToStart(tab: ConsoleTab, started: ReadonlySet<TabReadKey>): TabReadKey[] {
  if (tab === "overview") return [];
  return TAB_READ_GROUPS[tab].filter((k) => !started.has(k));
}

export type TabReads = Record<TabReadKey, ReadResult>;

export const INITIAL_TAB_READS: TabReads = {
  maturedLinkage: { status: "loading" },
  sportCards: { status: "loading" },
  sourceIntelligence: { status: "loading" },
};

/**
 * Start `keys` at once and report each as it settles — the overview's
 * contract: one bounded attempt per endpoint, never retried, cancelled by the
 * outer signal (unmount, Reload, a new credential). Every tab read needs the
 * admin credential, so the page passes `adminFetch` (Authorization header).
 */
export async function startTabReads(
  keys: readonly TabReadKey[],
  fetchFor: (key: TabReadKey) => (signal: AbortSignal) => Promise<Response>,
  onRead: (key: TabReadKey, result: ReadResult) => void,
  opts: { signal?: AbortSignal; timeoutMs?: number; now?: () => number } = {},
): Promise<number> {
  const now = opts.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
  const started = now();
  await Promise.all(
    keys.map((key) =>
      boundedRead(fetchFor(key), { signal: opts.signal, timeoutMs: opts.timeoutMs, now }).then((result) => {
        if (!opts.signal?.aborted) onRead(key, result);
      }),
    ),
  );
  return Math.round(now() - started);
}

// ─── The saved-reader envelope ──────────────────────────────────────────────

/** `cache_state` → HTTP status, for the three `saved_snapshot_read` routes. */
export const SAVED_READER_CACHE_STATUS: Record<string, number> = {
  hit: 200,
  miss: 202,
  error: 503,
  oversized: 503,
  malformed: 503,
};

/** What one section can show. Only `hit` carries numbers. */
export type SavedSection<T> =
  | { kind: "loading" }
  | { kind: "unauthorized"; detail: string; ms: number }
  /** The read failed and no saved-contract body came back. */
  | { kind: "failed"; detail: string; ms: number }
  /** The route answered, in its contract, that it has no number. */
  | { kind: "absent"; cacheState: string; reason: string; ms: number }
  /** The route said hit, but this page could not stand behind the payload. */
  | { kind: "refused"; what: string; ms: number }
  | {
      kind: "hit";
      data: T;
      generatedAt: string;
      freshness: "unreviewed" | "unknown";
      reason: string;
      servedFrom: "primary" | "retained_stale" | null;
      /** The payload itself says it is stale (link rate's `stale` marker). */
      staleReason: string | null;
      ms: number;
    };

class Refusal extends Error {}

function need(ok: unknown, what: string): asserts ok {
  if (!ok) throw new Refusal(what);
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
const isCount = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v >= 0;
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const inRange = (v: unknown, lo: number, hi: number): v is number => isNum(v) && v >= lo && v <= hi;
const isName = (v: unknown): v is string => typeof v === "string" && v !== "";
const isTime = (v: unknown): v is string => typeof v === "string" && Number.isFinite(Date.parse(v));

/** A server word, shown verbatim but bounded. */
function word(v: unknown): string {
  return typeof v === "string" && v.trim() ? v.slice(0, 80) : "reason not given";
}

function parseSaved<T>(
  read: ReadResult,
  opts: {
    statusFor: Record<string, number>;
    servedFrom: readonly ("primary" | "retained_stale")[] | null;
    check: (payload: Record<string, unknown>) => T;
    staleReason?: (payload: Record<string, unknown>) => string | null;
  },
): SavedSection<T> {
  if (read.status === "loading") return { kind: "loading" };
  if (read.status === "error" && read.kind === "unauthorized") {
    return { kind: "unauthorized", detail: read.detail, ms: read.ms };
  }
  const body = read.status === "ok" ? read.data : read.kind === "pending" || read.kind === "http" ? read.body : undefined;
  const isContract =
    isObj(body) &&
    body.schema_version === 1 &&
    typeof body.cache_state === "string" &&
    Object.prototype.hasOwnProperty.call(opts.statusFor, body.cache_state) &&
    typeof body.reason === "string";
  if (!isContract) {
    if (read.status === "error") return { kind: "failed", detail: read.detail, ms: read.ms };
    return { kind: "refused", what: "not the saved-evidence contract", ms: read.ms };
  }
  const cacheState = body.cache_state as string;
  if (opts.statusFor[cacheState] !== read.httpStatus) {
    return { kind: "refused", what: `cache_state ${cacheState} sent as HTTP ${read.httpStatus ?? "unknown"}`, ms: read.ms };
  }
  if (cacheState !== "hit") {
    const p = isObj(body.payload) ? body.payload : null;
    const reason = cacheState === "unavailable" && p ? word(p.stale_reason) : word(body.reason);
    return { kind: "absent", cacheState, reason, ms: read.ms };
  }
  try {
    const p = body.payload;
    need(isObj(p), "a hit without its payload");
    need(isTime(body.generated_at) && body.generated_at === p.generated_at, "generated_at does not match its payload");
    need(body.freshness === "unreviewed" || body.freshness === "unknown", "unknown freshness");
    let servedFrom: "primary" | "retained_stale" | null = null;
    if (opts.servedFrom) {
      need(
        typeof body.served_from === "string" && (opts.servedFrom as readonly string[]).includes(body.served_from),
        "unknown served_from",
      );
      servedFrom = body.served_from as "primary" | "retained_stale";
    }
    const data = opts.check(p);
    return {
      kind: "hit",
      data,
      generatedAt: body.generated_at as string,
      freshness: body.freshness as "unreviewed" | "unknown",
      reason: body.reason as string,
      servedFrom,
      staleReason: opts.staleReason ? opts.staleReason(p) : null,
      ms: read.ms,
    };
  } catch (err) {
    if (err instanceof Refusal) return { kind: "refused", what: err.message, ms: read.ms };
    throw err;
  }
}

// ─── Matured linkage (+ unlinked-held) ──────────────────────────────────────

function checkMiss(m: unknown, what: string) {
  need(isObj(m) && isCount(m.event_id) && isName(m.source) && isName(m.sport) && typeof m.matchup === "string", what);
}

function checkUnlinkedHeld(h: unknown): UnlinkedHeld {
  need(isObj(h), "unlinked_held missing");
  if (h.status === "error") {
    need(typeof h.error === "string", "unlinked_held error without its text");
    return { status: "error", error: h.error.slice(0, 160) };
  }
  need(h.status === "ok" || h.status === "insufficient_slate", "unknown unlinked_held status");
  need(isCount(h.headline_unlinked_held) && isCount(h.events_checked), "unlinked_held counts missing");
  need(Array.isArray(h.misses) && h.misses.length === h.headline_unlinked_held, "unlinked_held misses do not reconcile");
  for (const m of h.misses) {
    checkMiss(m, "an unlinked_held miss without its event");
    need(m.market_name === undefined || m.market_name === null || typeof m.market_name === "string", "an unlinked_held miss with a bad market name");
  }
  for (const k of ["candidates_scanned", "derivatives_excluded"] as const) {
    need(h[k] === undefined || isCount(h[k]), `unlinked_held ${k} is not a count`);
  }
  return h as unknown as UnlinkedHeld;
}

function checkMaturedLinkage(p: Record<string, unknown>): MaturedLinkageData {
  need(p.status === "ok" || p.status === "insufficient_slate", "unknown status");
  need(typeof p.window === "string", "no window");
  const counts = ["checkable_pairs", "backed", "phantom", "events_checked", "events_consistent"] as const;
  need(counts.every((k) => isCount(p[k])), "a count is missing");
  const [total, backed, phantom, checked, consistent] = counts.map((k) => p[k] as number);
  need(backed + phantom === total && consistent <= checked, "counts do not reconcile");
  need((p.status === "insufficient_slate") === (total === 0), "status does not match its denominator");
  need(total === 0 ? p.headline_pct === null : inRange(p.headline_pct, 0, 100), "headline is not a rate over its pairs");
  need(Array.isArray(p.misses) && p.misses.length === phantom, "misses do not reconcile with phantoms");
  for (const m of p.misses) checkMiss(m, "a miss without its event");
  return { ...(p as unknown as MaturedLinkageData), unlinked_held: checkUnlinkedHeld(p.unlinked_held) };
}

export function maturedLinkageSection(read: ReadResult): SavedSection<MaturedLinkageData> {
  return parseSaved(read, { statusFor: SAVED_READER_CACHE_STATUS, servedFrom: ["primary"], check: checkMaturedLinkage });
}

// ─── The 14-day sport cards ─────────────────────────────────────────────────

export const SPORT_CARD_WINDOW_DAYS = 14;

export interface SportCardsSnapshot {
  accuracy: AccuracyData;
  asOf: string;
  windowStart: string;
}

function checkSportCards(p: Record<string, unknown>): SportCardsSnapshot {
  need(p.schema_version === 1, "unsupported snapshot version");
  need(isTime(p.as_of) && p.generated_at === p.as_of, "as_of is not its generated_at");
  const w = p.window;
  need(
    isObj(w) &&
      w.column === "events.commence_time" &&
      w.days === SPORT_CARD_WINDOW_DAYS &&
      w.start_inclusive === true &&
      w.end === null &&
      isTime(w.start),
    "not the 14-day window",
  );
  need(
    Date.parse(p.as_of as string) - Date.parse(w.start as string) === SPORT_CARD_WINDOW_DAYS * 86_400_000,
    "window start is not 14 days before as_of",
  );
  const a = p.accuracy;
  need(isObj(a) && a.period_days === SPORT_CARD_WINDOW_DAYS && isObj(a.sports), "no sport cards");
  for (const [name, card] of Object.entries(a.sports as Record<string, unknown>)) {
    need(isName(name) && isObj(card), "a sport card without a name");
    need(isCount(card.total) && card.total > 0, `${name}: no denominator`);
    const total = card.total;
    const src = card.sources;
    need(
      isObj(src) && ["odds_api", "espn", "statpal"].every((k) => isCount(src[k]) && (src[k] as number) <= total),
      `${name}: source counts missing or above the total`,
    );
    const prov = card.commence_time_sources;
    need(
      isObj(prov) && Object.values(prov).every(isCount) && Object.values(prov).reduce<number>((s, v) => s + (v as number), 0) === total,
      `${name}: provenance does not reconcile`,
    );
  }
  return { accuracy: a as unknown as AccuracyData, asOf: p.as_of as string, windowStart: w.start as string };
}

export function sportCardsSection(read: ReadResult): SavedSection<SportCardsSnapshot> {
  return parseSaved(read, { statusFor: SAVED_READER_CACHE_STATUS, servedFrom: ["primary"], check: checkSportCards });
}

// ─── Link rate (the overview's read, reused) ────────────────────────────────

function checkLinkRate(p: Record<string, unknown>): LinkRateData {
  const block = (v: unknown, totalKey: string, rateKeys: string[]) =>
    isObj(v) &&
    isCount(v[totalKey]) &&
    isCount(v.linked) &&
    isCount(v.open_total) &&
    isCount(v.open_linked) &&
    rateKeys.every((k) => inRange(v[k], 0, 100));
  need(block(p.overall, "total_game_markets", ["link_rate_pct"]), "no overall counts");
  for (const venue of ["kalshi", "polymarket"] as const) {
    const v = p[venue];
    need(isObj(v) && block(v.totals, "total", ["link_rate_pct"]) && Array.isArray(v.by_sport), `no ${venue} block`);
    for (const row of v.by_sport as unknown[]) {
      need(isObj(row) && isName(row.sport) && (row.league === null || typeof row.league === "string") && block(row, "total", []), `a ${venue} league row is incomplete`);
    }
  }
  return p as unknown as LinkRateData;
}

export function linkRateSection(read: ReadResult): SavedSection<LinkRateData> {
  return parseSaved(read, {
    statusFor: LINK_RATE_CACHE_STATUS,
    servedFrom: null,
    check: checkLinkRate,
    staleReason: (p) => (p.stale === true ? word(p.stale_reason) : null),
  });
}

// ─── Source Intelligence ────────────────────────────────────────────────────

export const SI_COVERAGE_SOURCES = ["betting", "espn", "stat_model", "kalshi", "polymarket", "mlb"] as const;

function checkSourceIntelligence(p: Record<string, unknown>): SourceIntelligenceData {
  const c = p.coverage;
  need(isObj(c) && isCount(c.total_events) && isCount(c.multi_source_events), "no coverage counts");
  need(Array.isArray(c.by_sport) && Array.isArray(c.by_source_count), "no coverage tables");
  for (const r of c.by_sport as unknown[]) {
    need(isObj(r) && isName(r.sport) && isCount(r.total) && SI_COVERAGE_SOURCES.every((s) => isCount(r[s])), "a coverage row is incomplete");
  }
  for (const r of c.by_source_count as unknown[]) need(isObj(r) && isCount(r.sources) && isCount(r.events), "an overlap row is incomplete");
  const bySport = c.by_sport as { total: number }[];
  const overlap = c.by_source_count as { sources: number; events: number }[];
  need(bySport.reduce((s, r) => s + r.total, 0) === c.total_events, "coverage does not reconcile with its total");
  need(overlap.filter((r) => r.sources >= 2).reduce((s, r) => s + r.events, 0) === c.multi_source_events, "multi-source count does not reconcile");

  need(Array.isArray(p.source_accuracy), "no source accuracy");
  for (const r of p.source_accuracy as unknown[]) {
    need(
      isObj(r) && isName(r.source) && isCount(r.observations) && inRange(r.brier, 0, 1) && inRange(r.brier_ci, 0, Infinity) && Array.isArray(r.buckets),
      "a source accuracy row is incomplete",
    );
    for (const b of r.buckets as unknown[]) {
      need(isObj(b) && isCount(b.idx) && b.idx <= 9 && isCount(b.n) && inRange(b.avg_prob, 0, 1) && inRange(b.actual, 0, 1), "a calibration bucket is incomplete");
    }
  }

  const d = p.disagreements;
  need(isObj(d) && isCount(d.total_comparisons) && ["rate_5pp", "rate_10pp", "rate_20pp"].every((k) => inRange(d[k], 0, 1)), "no disagreement rates");
  need(Array.isArray(d.by_sport) && Array.isArray(d.pairwise), "no disagreement tables");
  for (const r of d.by_sport as unknown[]) need(isObj(r) && isName(r.sport) && isCount(r.comparisons) && inRange(r.rate_5pp, 0, 1), "a disagreement row is incomplete");
  for (const r of d.pairwise as unknown[]) {
    need(
      isObj(r) && isName(r.source_a) && isName(r.source_b) && isCount(r.count) && inRange(r.avg_divergence, 0, 1) && inRange(r.a_closer_pct, 0, 1),
      "a pairwise row is incomplete",
    );
    for (const split of ["by_phase", "by_sport"] as const) {
      const cells = r[split];
      need(isObj(cells) && Object.values(cells).every((x) => isObj(x) && isCount(x.comparisons) && inRange(x.a_closer_pct, 0, 1)), `a pairwise ${split} cell is incomplete`);
    }
  }

  need(Array.isArray(p.case_studies), "no case studies");
  for (const r of p.case_studies as unknown[]) {
    need(
      isObj(r) &&
        isCount(r.event_id) &&
        isName(r.sport) &&
        typeof r.score === "string" &&
        typeof r.date === "string" &&
        typeof r.home_won === "boolean" &&
        inRange(r.max_divergence, 0, 1) &&
        [r.home_team, r.away_team].every((t) => t === null || typeof t === "string") &&
        isObj(r.series),
      "a case study is incomplete",
    );
    for (const pts of Object.values(r.series as Record<string, unknown>)) {
      need(Array.isArray(pts) && pts.every((pt) => isObj(pt) && typeof pt.t === "string" && isNum(pt.p)), "a case-study series is incomplete");
    }
  }
  return p as unknown as SourceIntelligenceData;
}

export function sourceIntelligenceSection(read: ReadResult): SavedSection<SourceIntelligenceData> {
  return parseSaved(read, {
    statusFor: SAVED_READER_CACHE_STATUS,
    servedFrom: ["primary", "retained_stale"],
    check: checkSourceIntelligence,
  });
}

// ─── Words for a section's state ────────────────────────────────────────────

/** The console state a section is in — a hit is never current (see header). */
export function sectionState(s: SavedSection<unknown>): CorrectnessState {
  switch (s.kind) {
    case "loading":
      return "loading";
    case "unauthorized":
      return "unauthorized";
    case "hit":
      return s.staleReason !== null ? "stale" : "freshness_unknown";
    default:
      return "unavailable";
  }
}

const ABSENT_HEADLINE: Record<string, string> = {
  miss: "Unavailable — nothing is saved yet, and this page does not compute it",
  error: "Unavailable — the saved evidence could not be read",
  oversized: "Unavailable — the saved snapshot is larger than the read bound, so it was not decoded",
  malformed: "Unavailable — the saved evidence was refused as malformed",
  unavailable: "Unavailable — the saved snapshot records no data",
};

/** One line saying why a section has no numbers, or that it is still reading. */
export function sectionNoNumberText(s: SavedSection<unknown>): string {
  switch (s.kind) {
    case "loading":
      return "Reading the saved snapshot…";
    case "unauthorized":
      return `Not authorized (${s.detail}) — the server refused this tab's credential; this says nothing about the data`;
    case "failed":
      return `Unverified — the read failed (${s.detail})`;
    case "absent":
      return `${ABSENT_HEADLINE[s.cacheState] ?? "Unavailable"} (${s.reason})`;
    case "refused":
      return `Unavailable — this page refused the saved snapshot: ${s.what}`;
    case "hit":
      return "";
  }
}

const FRESHNESS_UNKNOWN_WHY: Record<string, string> = {
  generated_at_in_future: "the server saw its build time in the future",
};

/**
 * Provenance for a hit: which saved record answered, how old it is against
 * THIS page's clock, and why it is not a current verdict.
 */
export function sectionProvenance(
  s: Extract<SavedSection<unknown>, { kind: "hit" }>,
  nowMs: number,
): { record: string; built: string; freshness: string } {
  const ahead = Date.parse(s.generatedAt) - nowMs > SOURCE_CLOCK_SKEW_S * 1000;
  const record =
    s.servedFrom === "retained_stale"
      ? "Retained copy — the primary snapshot was missing, so the previous build's copy is shown"
      : "Saved snapshot";
  const built = ahead ? "built ahead of this browser's clock" : `built ${formatAge(ageSeconds(s.generatedAt, nowMs))}`;
  const freshness =
    s.staleReason !== null
      ? `the snapshot marks itself stale (${s.staleReason})`
      : s.freshness === "unknown"
        ? `freshness unknown — ${FRESHNESS_UNKNOWN_WHY[s.reason] ?? word(s.reason)}`
        : "freshness unreviewed — no horizon is reviewed for it, so its colours are what it read, not a current verdict";
  return { record, built, freshness };
}
