// #847 — the Correctness Console: "can we trust our numbers today?"
//
// One admin page composing EXISTING endpoints only. This module is the whole
// judgment layer: every tile's threshold, denominator and freshness rule lives
// here as a pure function, so the rule can be read in one place and asserted
// without a browser (this project has no jsdom — render tests are
// `renderToStaticMarkup`).
//
// THE RULE EVERY EVALUATOR OBEYS: a tile is green only on positive proof. A
// failed read, an empty cache, a wrong shape, a stale artifact or a missing
// denominator is UNVERIFIED — never zero, never green (gotcha #53: an empty 200
// is a response shape, not an absence). A red seen in data that has since gone
// stale is reported as "stale, last read red", not silently upgraded or
// dropped.
//
// THRESHOLDS ARE CITED, NOT INVENTED. Each one names its source:
//   - winner coverage   CLAUDE.md "Thresholds for immediate action": is_winner
//                       coverage <100% on any source → fix (any gap is a bug)
//   - category MCE      red >10pp at N>100 (#847 scope, docs/archive/
//                       issue-roadmap-2026-q3.md); green <3pp (/health §F
//                       "MCE (target: <3pp)", and the payload's own
//                       scorecard.bar.reader_bar_pp = 3.0). Between is amber.
//   - source coverage   /health §G: Tier-1 source <100% → red
//   - link rate         /health §D: Tier-1 open game-market link rate target 100%
//   - grid health       CLAUDE.md "Thresholds for immediate action": <100 → act
//   - guess family      no existing endpoint reports it (see evaluateGuessFamily)
// Where no threshold is documented the tile says so rather than colouring.

/** Every state a tile, or a row inside one, can be in. */
export type CorrectnessState =
  | "green"
  | "amber"
  | "red"
  /** Read fine, but the artifact is older than its own producer cadence allows. */
  | "stale"
  /** Some rows measured, some could not be — no all-clear is possible. */
  | "partial"
  /** Could not be read, or read as a shape we cannot stand behind. */
  | "unavailable"
  /** The server refused this tab's credential — no statement about the site. */
  | "unauthorized"
  | "loading"
  /** Measured, but no documented threshold exists to colour it against. */
  | "no_threshold";

export interface CorrectnessRow {
  label: string;
  value: string;
  state: CorrectnessState;
  note?: string;
}

export interface CorrectnessTile {
  key: CorrectnessTileKey;
  title: string;
  state: CorrectnessState;
  /** One line: the number, or why there is none. */
  headline: string;
  /** What population this counts and what threshold colours it. */
  method: string;
  /** Endpoint(s) the tile was composed from. */
  source: string;
  /** When the PRODUCER built what we read (not when we fetched it). */
  asOf: string | null;
  /** For a stale tile: the verdict the stale data carried. */
  lastVerdict?: CorrectnessState;
  rows: CorrectnessRow[];
  /** Secondary rows that are NOT the metric — labelled as such. */
  related?: CorrectnessRow[];
  /** Wall-clock ms of the read(s) behind this tile, when measured. */
  readMs?: number | null;
}

export type CorrectnessTileKey =
  | "winner_coverage"
  | "guess_family"
  | "category_mce"
  | "source_coverage"
  | "link_rate"
  | "grid_health";

// ─── Read results ───────────────────────────────────────────────────────────

/** The outcome of ONE bounded read. `data` is untrusted JSON. */
export type ReadResult =
  | { status: "loading" }
  | { status: "ok"; data: unknown; ms: number; httpStatus: number }
  | { status: "error"; kind: ReadErrorKind; detail: string; ms: number; httpStatus?: number };

export type ReadErrorKind = "unauthorized" | "http" | "timeout" | "network" | "parse" | "pending";

export const READ_TIMEOUT_MS = 10_000;

export interface CorrectnessReads {
  winners: ReadResult;
  calibration: ReadResult;
  dashboard: ReadResult;
  linkRate: ReadResult;
  grids: ReadResult;
}

/** The five existing endpoints. GET only, no bust/force/inline parameter. */
export const CORRECTNESS_ENDPOINTS = {
  winners: "/api/admin/backfill-winners/status",
  calibration: "/api/calibration",
  dashboard: "/api/admin/dashboard",
  linkRate: "/api/admin/prediction-markets/link-rate",
  grids: "/api/admin/audit/all",
} as const satisfies Record<keyof CorrectnessReads, string>;

/** Which reads need the admin credential. `/api/calibration` is public. */
export const ADMIN_READS: ReadonlySet<keyof CorrectnessReads> = new Set([
  "winners",
  "dashboard",
  "linkRate",
  "grids",
]);

/**
 * One bounded read: a single attempt, aborted at `timeoutMs`, never retried.
 *
 * `doFetch` is injected so the page passes `adminFetch` (Authorization header,
 * never `?secret=`) for admin reads and plain `fetch` for the public one, and
 * tests pass a fake. An outer `signal` (unmount / reload) cancels it too.
 *
 * HTTP 202 is NOT success here: `backfill-winners/status` answers 202 with a
 * `detail` body when its cache is empty, and `res.ok` is true for 202. Reading
 * that body as the payload is exactly the empty-200 trap.
 */
export async function boundedRead(
  doFetch: (signal: AbortSignal) => Promise<Response>,
  opts: { timeoutMs?: number; signal?: AbortSignal; now?: () => number } = {},
): Promise<ReadResult> {
  const now = opts.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
  const started = now();
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, opts.timeoutMs ?? READ_TIMEOUT_MS);
  const onOuterAbort = () => ctrl.abort();
  opts.signal?.addEventListener("abort", onOuterAbort);
  const elapsed = () => Math.round(now() - started);
  try {
    let res: Response;
    try {
      res = await doFetch(ctrl.signal);
    } catch (err) {
      if (timedOut) return { status: "error", kind: "timeout", detail: `no answer within ${opts.timeoutMs ?? READ_TIMEOUT_MS} ms`, ms: elapsed() };
      return { status: "error", kind: "network", detail: err instanceof Error ? err.message : String(err), ms: elapsed() };
    }
    if (res.status === 401 || res.status === 403) {
      return { status: "error", kind: "unauthorized", detail: `HTTP ${res.status}`, ms: elapsed(), httpStatus: res.status };
    }
    if (res.status === 202) {
      const body = await res.text().catch(() => "");
      return { status: "error", kind: "pending", detail: `HTTP 202 — no cached result yet${body ? `: ${body.slice(0, 160)}` : ""}`, ms: elapsed(), httpStatus: 202 };
    }
    if (!res.ok) {
      return { status: "error", kind: "http", detail: `HTTP ${res.status}`, ms: elapsed(), httpStatus: res.status };
    }
    try {
      const data: unknown = await res.json();
      return { status: "ok", data, ms: elapsed(), httpStatus: res.status };
    } catch (err) {
      if (timedOut) return { status: "error", kind: "timeout", detail: `body not complete within ${opts.timeoutMs ?? READ_TIMEOUT_MS} ms`, ms: elapsed() };
      return { status: "error", kind: "parse", detail: err instanceof Error ? err.message : String(err), ms: elapsed() };
    }
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onOuterAbort);
  }
}

export const INITIAL_READS: CorrectnessReads = {
  winners: { status: "loading" },
  calibration: { status: "loading" },
  dashboard: { status: "loading" },
  linkRate: { status: "loading" },
  grids: { status: "loading" },
};

/**
 * Start all five reads at once and report each the moment it settles, so one
 * slow or failing endpoint never holds or blanks the others. Resolves with the
 * total wall-clock ms once every read has settled. Nothing here retries or
 * repeats: one call is one round of five requests.
 */
export async function startCorrectnessReads(
  fetchFor: (key: keyof CorrectnessReads) => (signal: AbortSignal) => Promise<Response>,
  onRead: (key: keyof CorrectnessReads, result: ReadResult) => void,
  opts: { signal?: AbortSignal; timeoutMs?: number; now?: () => number } = {},
): Promise<number> {
  const now = opts.now ?? (() => (typeof performance !== "undefined" ? performance.now() : Date.now()));
  const started = now();
  const keys = Object.keys(CORRECTNESS_ENDPOINTS) as (keyof CorrectnessReads)[];
  await Promise.all(
    keys.map((key) =>
      boundedRead(fetchFor(key), { signal: opts.signal, timeoutMs: opts.timeoutMs, now }).then((result) => {
        if (!opts.signal?.aborted) onRead(key, result);
      }),
    ),
  );
  return Math.round(now() - started);
}

// ─── The presentation clock ─────────────────────────────────────────────────

/** How often fetched evidence is re-judged against the wall clock. */
export const UI_CLOCK_INTERVAL_MS = 30_000;

type VisibilityDoc = Pick<Document, "addEventListener" | "removeEventListener" | "visibilityState">;

/**
 * Root finding 002 on e603826e7f: the page judged freshness against a clock
 * that only moved when a read settled, so after the last read a green tile
 * stayed green forever in a tab left open — evidence never aged into stale.
 *
 * This ticks a LOCAL clock: every `intervalMs`, and immediately when the tab
 * comes back from the background (timers are throttled while hidden). It only
 * calls `onTick(now)`. It issues no request, triggers no producer and never
 * touches a source's own timestamp — re-judging old evidence is the whole job.
 * Returns the cleanup the page runs on unmount.
 */
export function startUiClock(
  onTick: (nowMs: number) => void,
  opts: { intervalMs?: number; doc?: VisibilityDoc | null; now?: () => number } = {},
): () => void {
  const now = opts.now ?? Date.now;
  const doc = opts.doc === undefined ? (typeof document !== "undefined" ? document : null) : opts.doc;
  const tick = () => onTick(now());
  const timer = setInterval(tick, opts.intervalMs ?? UI_CLOCK_INTERVAL_MS);
  const onVisible = () => {
    if (doc?.visibilityState === "visible") tick();
  };
  doc?.addEventListener("visibilitychange", onVisible);
  return () => {
    clearInterval(timer);
    doc?.removeEventListener("visibilitychange", onVisible);
  };
}

// ─── Small, total readers over untrusted JSON ───────────────────────────────

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** A finite, non-negative count — or null. `"12"`, NaN, -1, true are not counts. */
export function asCount(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
}

function asNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function asStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}

/** Age in seconds of an ISO timestamp, or null when it does not parse. */
export function ageSeconds(iso: string | null, nowMs: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.round((nowMs - t) / 1000));
}

export function formatAge(s: number | null): string {
  if (s === null) return "age unknown";
  if (s < 90) return `${s}s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function pct(n: number, d: number): string {
  if (d <= 0) return "—";
  const p = (100 * n) / d;
  // Never round a gap up to "100%": 99.97% must not read as complete.
  if (n < d && p >= 99.95) return "99.9%";
  return `${p.toFixed(1)}%`;
}

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Fold row states into a tile state. Precedence: a red seen is red; otherwise
 * anything unverified blocks the all-clear; amber before green; green only
 * when EVERY row is green and there is at least one.
 */
export function foldStates(states: CorrectnessState[]): CorrectnessState {
  if (states.length === 0) return "unavailable";
  if (states.includes("red")) return "red";
  const unverified = states.some((s) => s === "unavailable" || s === "stale" || s === "partial" || s === "no_threshold");
  const anyMeasured = states.some((s) => s === "green" || s === "amber");
  if (unverified) return anyMeasured ? "partial" : states.includes("stale") ? "stale" : "unavailable";
  if (states.includes("amber")) return "amber";
  return states.every((s) => s === "green") ? "green" : "partial";
}

/** Apply a freshness verdict on top of a threshold verdict. */
function withFreshness(tile: CorrectnessTile, stale: boolean): CorrectnessTile {
  if (!stale) return tile;
  return { ...tile, state: "stale", lastVerdict: tile.state };
}

/** The tile for a read that failed or has not settled. */
function readFailureTile(base: Omit<CorrectnessTile, "state" | "headline" | "rows" | "asOf">, read: ReadResult): CorrectnessTile | null {
  if (read.status === "loading") {
    return { ...base, state: "loading", headline: "Loading…", rows: [], asOf: null, readMs: null };
  }
  if (read.status === "error") {
    const state: CorrectnessState = read.kind === "unauthorized" ? "unauthorized" : "unavailable";
    const headline =
      read.kind === "unauthorized"
        ? "Not authorized — this says nothing about the data"
        : read.kind === "timeout"
          ? `Unavailable — ${read.detail}`
          : read.kind === "pending"
            ? "Unavailable — the producer has not written its cache"
            : `Unavailable — ${read.detail}`;
    return { ...base, state, headline, rows: [], asOf: null, readMs: read.ms };
  }
  return null;
}

function wrongShape(base: Omit<CorrectnessTile, "state" | "headline" | "rows" | "asOf">, what: string, ms: number): CorrectnessTile {
  return { ...base, state: "unavailable", headline: `Unavailable — unexpected response shape (${what})`, rows: [], asOf: null, readMs: ms };
}

// ─── 1. Winner coverage ─────────────────────────────────────────────────────

/** Two producer beats (hourly at :35) — also the cache TTL, 7200 s. */
export const WINNERS_STALE_AFTER_S = 2 * 3600;

/**
 * `backfill-winners/status` `sources[]`. Per source, the tradeable resolved
 * markets partition exactly into four counts (see
 * `tasks/precompute_backfill_winners_status.py`, #940):
 *   has_winner            a winning outcome, or every price ≤ 0.10
 *   resolved_single_sided authoritatively resolved with no winner by structure
 *   heuristic_resolved    resolved by a non-authoritative (guess/soft) source
 *   needs_backfill        NO resolution source at all — the genuine gap
 * and `untradeable_excluded` sits outside the denominator. A source whose four
 * counts do not sum to `resolved - untradeable_excluded` is reported as
 * inconsistent rather than coloured.
 *
 * The gap that turns a source red is `needs_backfill`. Heuristic resolutions
 * are not counted as a gap here — they have an answer — but they are not
 * claimed authoritative either: they are shown on every row.
 */
export function evaluateWinnerCoverage(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "winner_coverage" as const,
    title: "Winner coverage",
    method:
      "Per source: resolved, tradeable markets that have a resolution. Any market with no resolution at all is a gap → red (CLAUDE.md: any gap is a bug). Markets with no tradeable price are outside the denominator.",
    source: CORRECTNESS_ENDPOINTS.winners,
  };
  const failed = readFailureTile(base, read);
  if (failed) return failed;
  if (read.status !== "ok") return wrongShape(base, "no data", 0);
  const d = read.data;
  if (!isObj(d) || !Array.isArray(d.sources)) return wrongShape(base, "no sources[]", read.ms);
  const asOf = asStr(d.computed_at);
  const rows: CorrectnessRow[] = [];
  for (const s of d.sources) {
    if (!isObj(s)) continue;
    const name = asStr(s.source) ?? "unknown source";
    const resolved = asCount(s.resolved);
    const hasWinner = asCount(s.has_winner);
    const single = asCount(s.resolved_single_sided);
    const heuristic = asCount(s.heuristic_resolved);
    const gap = asCount(s.needs_backfill);
    const untradeable = asCount(s.untradeable_excluded);
    if (
      resolved === null || hasWinner === null || single === null ||
      heuristic === null || gap === null || untradeable === null
    ) {
      rows.push({ label: name, value: "—", state: "unavailable", note: "a count is missing from this row" });
      continue;
    }
    const tradeable = resolved - untradeable;
    if (hasWinner + single + heuristic + gap !== tradeable) {
      rows.push({ label: name, value: "—", state: "unavailable", note: "counts do not add up to the denominator" });
      continue;
    }
    if (tradeable === 0) {
      rows.push({ label: name, value: "no tradeable resolved markets", state: "unavailable" });
      continue;
    }
    const covered = tradeable - gap;
    rows.push({
      label: name,
      value: `${pct(covered, tradeable)} (${fmt(covered)}/${fmt(tradeable)})`,
      state: gap === 0 ? "green" : "red",
      note: `${fmt(gap)} with no resolution · ${fmt(heuristic)} resolved by heuristic, not authority`,
    });
  }
  if (rows.length === 0) return { ...base, state: "unavailable", headline: "Unavailable — no sources reported", rows, asOf, readMs: read.ms };
  const state = foldStates(rows.map((r) => r.state));
  const red = rows.filter((r) => r.state === "red").length;
  const headline =
    state === "green"
      ? `Every source covered (${rows.length} sources)`
      : red > 0
        ? `${red} of ${rows.length} sources have markets with no resolution`
        : `Not all sources could be verified`;
  const age = ageSeconds(asOf, nowMs);
  const tile: CorrectnessTile = { ...base, state, headline, rows, asOf, readMs: read.ms };
  return withFreshness(tile, age === null || age > WINNERS_STALE_AFTER_S);
}

// ─── 2. Guess family ────────────────────────────────────────────────────────

/** The tier-0 GUESS_FAMILY (`utils/resolution_authority.py`, architecture-reference). */
export const GUESS_FAMILY_SOURCES = ["pass2_guess", "binary_higher_wins", "multi_max_prob", "pass3_threshold"] as const;

/**
 * CONTRACT BLOCKER, stated rather than papered over.
 *
 * No existing cached endpoint reports a count of the tier-0 guess family. The
 * only route that counts guesses at all, `/api/admin/audit-pass2-guess`, is a
 * live multi-query scan of `futures_outcomes` that counts `pass2_guess` alone —
 * a different population, and a heavy read this page must not add.
 *
 * Two cached counts sit NEAR it and are shown as related, each named for what
 * it is, neither coloured and neither summed into a "guess count":
 *   - status `heuristic_resolved` — no-winner MARKETS resolved by any
 *     non-authoritative source (guess family AND soft-terminal sources);
 *   - `/api/calibration` `heuristic_filter.excluded_by_source` — OUTCOMES held
 *     OUT of the published curve (pass2_guess / pass2_loser / all_losers).
 *     A count of guesses kept out of the curve is not a claim that the curve
 *     contains guesses.
 */
export function evaluateGuessFamily(winners: ReadResult, calibration: ReadResult): CorrectnessTile {
  const related: CorrectnessRow[] = [];
  if (winners.status === "ok" && isObj(winners.data) && Array.isArray(winners.data.sources)) {
    for (const s of winners.data.sources) {
      if (!isObj(s)) continue;
      const n = asCount(s.heuristic_resolved);
      related.push({
        label: `${asStr(s.source) ?? "unknown"} — markets resolved by heuristic`,
        value: n === null ? "—" : fmt(n),
        state: n === null ? "unavailable" : "no_threshold",
        note: "no-winner markets, guess family + soft-terminal sources",
      });
    }
  }
  if (calibration.status === "ok" && isObj(calibration.data)) {
    const hf = calibration.data.heuristic_filter;
    const by = isObj(hf) ? hf.excluded_by_source : null;
    if (isObj(by)) {
      for (const [src, v] of Object.entries(by)) {
        const n = asCount(v);
        related.push({
          label: `${src} — outcomes held out of the published curve`,
          value: n === null ? "—" : fmt(n),
          state: n === null ? "unavailable" : "no_threshold",
          note: `as of curve built ${asStr(calibration.data.generated_at) ?? "at an unknown time"}`,
        });
      }
    }
  }
  return {
    key: "guess_family",
    title: "Guess-family count",
    state: "unavailable",
    headline: "Not reported by any existing cached endpoint",
    method: `The guess family is ${GUESS_FAMILY_SOURCES.join(", ")}. No existing endpoint reports its count from a cache, and no threshold for it is documented. The related counts below are different populations.`,
    source: `${CORRECTNESS_ENDPOINTS.winners} · ${CORRECTNESS_ENDPOINTS.calibration}`,
    asOf: null,
    rows: [],
    related,
    readMs: null,
  };
}

// ─── 3. Per-category MCE ────────────────────────────────────────────────────

export const MCE_GREEN_BELOW_PP = 3;
export const MCE_RED_ABOVE_PP = 10;
export const MCE_RED_MIN_N = 100;

export function mceState(mce: number | null, n: number | null): CorrectnessState {
  if (mce === null || n === null || n === 0) return "unavailable";
  if (n <= MCE_RED_MIN_N) return "no_threshold";
  if (mce > MCE_RED_ABOVE_PP) return "red";
  if (mce < MCE_GREEN_BELOW_PP) return "green";
  return "amber";
}

const STATE_RANK: Record<CorrectnessState, number> = {
  red: 0,
  unavailable: 1,
  amber: 2,
  stale: 3,
  partial: 3,
  no_threshold: 4,
  green: 5,
  unauthorized: 6,
  loading: 7,
};

/**
 * `/api/calibration` `by_category[]`. The tile is current only on POSITIVE
 * proof: `availability === "fresh"` AND `producer.stalled === false`. Anything
 * else — a stale/empty/degraded declaration, a stalled or unknown producer, an
 * older payload with no envelope — reads as stale, with the server's own words
 * for why.
 */
export function evaluateCategoryMce(read: ReadResult): CorrectnessTile {
  const base = {
    key: "category_mce" as const,
    title: "Calibration error by category",
    method: `MCE in percentage points, per published category, with N outcomes. Red above ${MCE_RED_ABOVE_PP}pp when N > ${MCE_RED_MIN_N}; green below ${MCE_GREEN_BELOW_PP}pp (/health target); amber between.`,
    source: CORRECTNESS_ENDPOINTS.calibration,
  };
  const failed = readFailureTile(base, read);
  if (failed) return failed;
  if (read.status !== "ok") return wrongShape(base, "no data", 0);
  const d = read.data;
  if (!isObj(d) || !Array.isArray(d.by_category)) return wrongShape(base, "no by_category[]", read.ms);
  const asOf = asStr(d.generated_at);
  const scored: { row: CorrectnessRow; mce: number }[] = [];
  for (const c of d.by_category) {
    if (!isObj(c)) continue;
    const mce = asNum(c.mce);
    const n = asCount(c.n) ?? asCount(c.outcomes);
    const state = mceState(mce, n);
    scored.push({
      mce: mce ?? -1,
      row: {
        label: asStr(c.category) ?? "unknown category",
        value: mce === null ? "—" : `${mce.toFixed(2)}pp`,
        state,
        note: n === null ? "N unknown" : `N = ${fmt(n)}${state === "no_threshold" ? ` (at or below ${MCE_RED_MIN_N}, not graded)` : ""}`,
      },
    });
  }
  // Worst first: by state, then by error within a state.
  scored.sort((a, b) => STATE_RANK[a.row.state] - STATE_RANK[b.row.state] || b.mce - a.mce);
  const rows = scored.map((s) => s.row);
  if (rows.length === 0) return { ...base, state: "unavailable", headline: "Unavailable — no published categories", rows, asOf, readMs: read.ms };
  const graded = rows.filter((r) => r.state === "green" || r.state === "amber" || r.state === "red");
  // Ungraded (N ≤ floor) rows are shown but do not vote; with nothing graded
  // there is no verdict to give.
  const voting = rows.filter((r) => r.state !== "no_threshold").map((r) => r.state);
  const state = graded.length > 0 ? foldStates(voting) : "unavailable";
  const red = rows.filter((r) => r.state === "red").length;
  const amber = rows.filter((r) => r.state === "amber").length;
  const headline = `${rows.length} categories · ${red} red · ${amber} amber · ${graded.length - red - amber} green`;

  const availability = asStr(d.availability);
  const producer = isObj(d.producer) ? d.producer : null;
  const stalled = producer && typeof producer.stalled === "boolean" ? producer.stalled : null;
  const proven = availability === "fresh" && stalled === false;
  const tile: CorrectnessTile = { ...base, state, headline, rows, asOf, readMs: read.ms };
  if (proven) return tile;
  const missed = producer ? asCount(producer.beats_missed) : null;
  const why = [
    `availability: ${availability ?? "not declared"}`,
    stalled === null
      ? "producer state not reported"
      : stalled
        ? `producer stalled${missed !== null ? `, ${fmt(missed)} beats missed` : ""}`
        : "producer running",
  ].join(" · ");
  return { ...withFreshness(tile, true), headline: `Stale curve — ${why}. Last read: ${headline}` };
}

// ─── 4. Source coverage ─────────────────────────────────────────────────────

export const TIER1_SPORT_KEYS = ["americanfootball_nfl", "basketball_nba", "baseball_mlb", "icehockey_nhl"] as const;
/** The five sources /health §G checks, by `source_coverage` field name. */
export const COVERAGE_SOURCES = ["odds_api", "espn", "statpal", "kalshi", "polymarket"] as const;
const COVERAGE_LABEL: Record<(typeof COVERAGE_SOURCES)[number], string> = {
  odds_api: "Odds API",
  espn: "ESPN",
  statpal: "StatPal",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};
const SPORT_LABEL: Record<string, string> = {
  americanfootball_nfl: "NFL",
  basketball_nba: "NBA",
  baseball_mlb: "MLB",
  icehockey_nhl: "NHL",
};
/** Computed live per request; an hour-old answer means something is wrong. */
export const DASHBOARD_STALE_AFTER_S = 3600;

/**
 * `/api/admin/dashboard` `source_coverage[]`: per sport, events commencing in
 * the last 7 days through the next 2, and how many carry each source. A source
 * the row's own `expected_sources` marks false is skipped, not counted green.
 * A Tier-1 sport with no row has nothing measured, which blocks the all-clear.
 * The panel's failure shape is `[{"error": …}]` — unavailable, never empty.
 */
export function evaluateSourceCoverage(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "source_coverage" as const,
    title: "Tier-1 source coverage",
    method:
      "Share of NFL/NBA/MLB/NHL events (commencing 7 days ago through 2 days ahead) carrying each expected source. Any expected source below 100% → red (/health §G).",
    source: `${CORRECTNESS_ENDPOINTS.dashboard} → source_coverage`,
  };
  const failed = readFailureTile(base, read);
  if (failed) return failed;
  if (read.status !== "ok") return wrongShape(base, "no data", 0);
  const d = read.data;
  if (!isObj(d) || !Array.isArray(d.source_coverage)) return wrongShape(base, "no source_coverage[]", read.ms);
  const asOf = asStr(d.generated_at);
  const list = d.source_coverage;
  if (list.length > 0 && isObj(list[0]) && "error" in list[0]) {
    return { ...base, state: "unavailable", headline: "Unavailable — the coverage query failed on the server", rows: [], asOf, readMs: read.ms };
  }
  const rows: CorrectnessRow[] = [];
  for (const sport of TIER1_SPORT_KEYS) {
    const row = list.find((r) => isObj(r) && r.sport === sport);
    const label = SPORT_LABEL[sport];
    if (!isObj(row)) {
      rows.push({ label, value: "no events in window", state: "unavailable", note: "nothing measured for this sport" });
      continue;
    }
    const total = asCount(row.total);
    if (total === null || total === 0) {
      rows.push({ label, value: total === 0 ? "no events in window" : "—", state: "unavailable" });
      continue;
    }
    const expected = isObj(row.expected_sources) ? row.expected_sources : null;
    for (const src of COVERAGE_SOURCES) {
      if (expected && expected[src] === false) continue;
      const n = asCount(row[src]);
      if (n === null) {
        rows.push({ label: `${label} · ${COVERAGE_LABEL[src]}`, value: "—", state: "unavailable", note: "count missing" });
        continue;
      }
      rows.push({
        label: `${label} · ${COVERAGE_LABEL[src]}`,
        value: `${pct(n, total)} (${fmt(n)}/${fmt(total)})`,
        state: n >= total ? "green" : "red",
      });
    }
  }
  const state = foldStates(rows.map((r) => r.state));
  rows.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state]);
  const red = rows.filter((r) => r.state === "red").length;
  const headline = state === "green" ? "Every expected Tier-1 source on every event" : `${red} of ${rows.length} sport × source cells below 100%`;
  const age = ageSeconds(asOf, nowMs);
  return withFreshness({ ...base, state, headline, rows, asOf, readMs: read.ms }, age === null || age > DASHBOARD_STALE_AFTER_S);
}

// ─── 5. Link rate ───────────────────────────────────────────────────────────

/** Two producer beats (every 30 min) — also the cache TTL, 3600 s. */
export const LINK_RATE_STALE_AFTER_S = 3600;
const TIER1_LEAGUES: [string, string][] = [
  ["football", "NFL"],
  ["basketball", "NBA"],
  ["baseball", "MLB"],
  ["hockey", "NHL"],
];

/**
 * `/prediction-markets/link-rate`. Graded on Tier-1 OPEN game markets per venue
 * from COUNTS — the payload's `link_rate` is `0` when `open_total` is 0, which
 * would read a nothing as a failure. The all-markets rate and its exclusions are
 * shown, uncoloured: no threshold is documented for them. A payload the route
 * marks `stale` (served the last snapshot after a failed compute) or
 * `unavailable` (no snapshot at all) is never graded current.
 */
export function evaluateLinkRate(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "link_rate" as const,
    title: "Game-market link rate",
    method:
      "Tier-1 (NFL/NBA/MLB/NHL) open Kalshi and Polymarket game markets linked to an event. Target 100% (/health §D); below → red. The overall rate has no documented threshold.",
    source: CORRECTNESS_ENDPOINTS.linkRate,
  };
  const failed = readFailureTile(base, read);
  if (failed) return failed;
  if (read.status !== "ok") return wrongShape(base, "no data", 0);
  const d = read.data;
  if (!isObj(d)) return wrongShape(base, "not an object", read.ms);
  const asOf = asStr(d.generated_at);
  if (d.unavailable === true) {
    return { ...base, state: "unavailable", headline: `Unavailable — no snapshot (${asStr(d.stale_reason) ?? "reason not given"})`, rows: [], asOf, readMs: read.ms };
  }
  if (!isObj(d.kalshi) || !isObj(d.polymarket)) return wrongShape(base, "no venue blocks", read.ms);
  const rows: CorrectnessRow[] = [];
  for (const venue of ["kalshi", "polymarket"] as const) {
    const block = d[venue] as Record<string, unknown>;
    const bySport = Array.isArray(block.by_sport) ? block.by_sport : null;
    const vLabel = venue === "kalshi" ? "Kalshi" : "Polymarket";
    if (!bySport) {
      rows.push({ label: vLabel, value: "—", state: "unavailable", note: "no by_sport[]" });
      continue;
    }
    for (const [sport, league] of TIER1_LEAGUES) {
      const row = bySport.find(
        (r) => isObj(r) && r.sport === sport && typeof r.league === "string" && r.league.toUpperCase() === league,
      );
      const label = `${vLabel} · ${league}`;
      if (!isObj(row)) {
        rows.push({ label, value: "no markets", state: "unavailable", note: "nothing measured" });
        continue;
      }
      const open = asCount(row.open_total);
      const linked = asCount(row.open_linked);
      if (open === null || linked === null) {
        rows.push({ label, value: "—", state: "unavailable", note: "count missing" });
        continue;
      }
      if (open === 0) {
        rows.push({ label, value: "no open markets", state: "unavailable", note: "nothing open to link" });
        continue;
      }
      rows.push({ label, value: `${pct(linked, open)} (${fmt(linked)}/${fmt(open)})`, state: linked >= open ? "green" : "red" });
    }
  }
  const related: CorrectnessRow[] = [];
  const ov = isObj(d.overall) ? d.overall : null;
  if (ov) {
    const open = asCount(ov.open_total);
    const linked = asCount(ov.open_linked);
    related.push({
      label: "All sports — open game markets linked",
      value: open && linked !== null ? `${pct(linked, open)} (${fmt(linked)}/${fmt(open)})` : "—",
      state: open && linked !== null ? "no_threshold" : "unavailable",
      note: asStr(ov.denominator_note) ?? undefined,
    });
    const raw = asNum(ov.link_rate_raw_pct);
    const gapOpen = asCount(ov.excluded_open_upstream_coverage_gap);
    if (raw !== null && open) {
      related.push({
        label: "All sports — with upstream-gap markets kept in",
        value: `${raw.toFixed(1)}%`,
        state: "no_threshold",
        note: gapOpen !== null ? `${fmt(gapOpen)} open markets excluded as upstream gaps` : undefined,
      });
    }
  }
  const state = foldStates(rows.map((r) => r.state));
  rows.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state]);
  const red = rows.filter((r) => r.state === "red").length;
  const headline = state === "green" ? "Every open Tier-1 game market linked" : `${red} of ${rows.length} venue × league cells below 100%`;
  const age = ageSeconds(asOf, nowMs);
  const tile: CorrectnessTile = { ...base, state, headline, rows, related, asOf, readMs: read.ms };
  const routeStale = d.stale === true;
  const out = withFreshness(tile, routeStale || age === null || age > LINK_RATE_STALE_AFTER_S);
  return routeStale ? { ...out, headline: `Stale snapshot (${asStr(d.stale_reason) ?? "reason not given"}). Last read: ${headline}` } : out;
}

// ─── 6. Grid health ─────────────────────────────────────────────────────────

/** The grids `_compute_audit_all_grids` audits. */
export const EXPECTED_GRIDS = ["nba", "nhl", "mlb", "golf"] as const;
/** Two producer beats (every 30 min) — also the cache TTL, 3600 s. */
export const GRIDS_STALE_AFTER_S = 3600;

/** `/api/admin/audit/all`: `grids.{nba,nhl,mlb,golf}.health_score` out of 100. */
export function evaluateGridHealth(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "grid_health" as const,
    title: "Championship grid health",
    method: "Matching-quality audit score per grid, out of 100. Below 100 → red (CLAUDE.md: grid health <100% → investigate). A grid whose audit errored is unverified.",
    source: CORRECTNESS_ENDPOINTS.grids,
  };
  const failed = readFailureTile(base, read);
  if (failed) return failed;
  if (read.status !== "ok") return wrongShape(base, "no data", 0);
  const d = read.data;
  if (!isObj(d) || !isObj(d.grids)) return wrongShape(base, "no grids{}", read.ms);
  const asOf = asStr(d.generated_at);
  const rows: CorrectnessRow[] = [];
  for (const g of EXPECTED_GRIDS) {
    const grid = d.grids[g];
    const label = g.toUpperCase();
    if (!isObj(grid)) {
      rows.push({ label, value: "—", state: "unavailable", note: "grid not in the audit" });
      continue;
    }
    const score = asNum(grid.health_score);
    if (score === null || !Number.isInteger(score)) {
      rows.push({ label, value: "—", state: "unavailable", note: asStr(grid.status) === "error" ? "audit errored" : "no score" });
      continue;
    }
    const findings = Array.isArray(grid.findings) ? grid.findings.length : null;
    rows.push({
      label,
      value: `${score}/100`,
      state: score >= 100 ? "green" : "red",
      note: findings === null ? undefined : `${findings} finding${findings === 1 ? "" : "s"}`,
    });
  }
  const state = foldStates(rows.map((r) => r.state));
  const red = rows.filter((r) => r.state === "red").length;
  const headline = state === "green" ? `All ${rows.length} grids at 100` : `${red} of ${rows.length} grids below 100`;
  const age = ageSeconds(asOf, nowMs);
  return withFreshness({ ...base, state, headline, rows, asOf, readMs: read.ms }, age === null || age > GRIDS_STALE_AFTER_S);
}

// ─── The page as a whole ────────────────────────────────────────────────────

export function evaluateAll(reads: CorrectnessReads, nowMs: number): CorrectnessTile[] {
  return [
    evaluateWinnerCoverage(reads.winners, nowMs),
    evaluateGuessFamily(reads.winners, reads.calibration),
    evaluateCategoryMce(reads.calibration),
    evaluateSourceCoverage(reads.dashboard, nowMs),
    evaluateLinkRate(reads.linkRate, nowMs),
    evaluateGridHealth(reads.grids, nowMs),
  ];
}

export interface ConsoleSummary {
  status: "good" | "warning" | "critical" | "loading" | "unauthorized";
  summary: string;
}

/**
 * The page header. `good` needs all six tiles green — which today it cannot be,
 * because the guess-family tile has no endpoint. That is the honest answer to
 * "can we trust our numbers today?" while one of the six cannot be read.
 */
export function summarize(tiles: CorrectnessTile[]): ConsoleSummary {
  const n = (s: CorrectnessState) => tiles.filter((t) => t.state === s).length;
  // The guess-family tile is composed from the other reads and never loads on
  // its own, so it does not count toward "still loading" or "all refused".
  const readTiles = tiles.filter((t) => t.key !== "guess_family");
  if (readTiles.length > 0 && readTiles.every((t) => t.state === "loading")) {
    return { status: "loading", summary: "Loading the correctness reads…" };
  }
  // A 401/403 is a statement about this tab's credential (#6024). Only when
  // NOTHING admin-backed answered is the header about the credential instead.
  const adminTiles = readTiles.filter((t) => t.key !== "category_mce");
  if (adminTiles.length > 0 && adminTiles.every((t) => t.state === "unauthorized" || t.state === "loading") && adminTiles.some((t) => t.state === "unauthorized")) {
    return { status: "unauthorized", summary: "This tab's admin credential was rejected — the data's health is unknown, not bad." };
  }
  const green = n("green");
  const red = n("red");
  const unverified = tiles.length - green - red - n("amber") - n("loading");
  const parts = [`${green} of ${tiles.length} green`];
  if (red) parts.push(`${red} red`);
  if (n("amber")) parts.push(`${n("amber")} amber`);
  if (unverified) parts.push(`${unverified} unverified`);
  if (n("loading")) parts.push(`${n("loading")} loading`);
  const status = red > 0 ? "critical" : green === tiles.length ? "good" : "warning";
  return { status, summary: parts.join(" · ") };
}
