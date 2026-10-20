// #847 — the Correctness Console: "can we trust our numbers today?"
//
// One admin page composing EXISTING endpoints only — and, for source coverage
// and link rate, their SAVED-ONLY contracts (`/event-source-coverage/cached`,
// `/prediction-markets/link-rate/cached`), so opening the page never starts the
// live coverage query or the inline link-rate compute. This module is the whole
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
//   - source coverage   /health §G: Tier-1 source <100% → red. Current only
//                       inside the saved observation's own reviewed horizon.
//   - link rate         /health §D: Tier-1 open game-market link rate target 100%.
//                       No freshness horizon is reviewed for the saved snapshot,
//                       so it is graded but never called current (never green).
//   - grid health       the Grid Sentinel's own per-league verdict (CLAUDE.md:
//                       grid accuracy belongs to the Sentinel, RED means REAL).
//                       A raw audit penalty score is not a verdict and is not read.
//   - guess family      no existing endpoint reports it (see evaluateGuessFamily)
// Where no threshold is documented the tile says so rather than colouring.

/** Every state a tile, or a row inside one, can be in. */
export type CorrectnessState =
  | "green"
  | "amber"
  | "red"
  /** Read fine, but the artifact is older than its own producer cadence allows. */
  | "stale"
  /**
   * Read fine and graded, but there is no basis to call it current: no reviewed
   * freshness horizon, an unknown producing release, or a clock in the future.
   */
  | "freshness_unknown"
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
  /** Producer-side facts behind the number: window, provenance, horizons. */
  evidence?: string[];
}

export type CorrectnessTileKey =
  | "winner_coverage"
  | "guess_family"
  | "category_mce"
  | "source_coverage"
  | "link_rate"
  | "grid_health";

// ─── Read results ───────────────────────────────────────────────────────────

/**
 * The outcome of ONE bounded read. `data` is untrusted JSON. An error carries
 * `body` when a 202 / non-2xx answer was itself JSON: the saved-only routes say
 * WHY there is no number (miss, expired, malformed…) in exactly that body.
 */
export type ReadResult =
  | { status: "loading" }
  | { status: "ok"; data: unknown; ms: number; httpStatus: number }
  | { status: "error"; kind: ReadErrorKind; detail: string; ms: number; httpStatus?: number; body?: unknown };

export type ReadErrorKind = "unauthorized" | "http" | "timeout" | "network" | "parse" | "pending";

export const READ_TIMEOUT_MS = 10_000;

export interface CorrectnessReads {
  winners: ReadResult;
  calibration: ReadResult;
  sourceCoverage: ReadResult;
  linkRate: ReadResult;
  gridSentinel: ReadResult;
}

/**
 * The five endpoints. GET only, no bust/force/inline parameter. Coverage and
 * link rate read the saved-only routes: `/api/admin/dashboard` runs the live
 * coverage query and `/prediction-markets/link-rate` computes inline on a cold
 * cache, so neither is ever read from here — not even as a fallback.
 */
export const CORRECTNESS_ENDPOINTS = {
  winners: "/api/admin/backfill-winners/status",
  calibration: "/api/calibration",
  sourceCoverage: "/api/admin/event-source-coverage/cached",
  linkRate: "/api/admin/prediction-markets/link-rate/cached",
  gridSentinel: "/api/admin/grid-sentinel/last",
} as const satisfies Record<keyof CorrectnessReads, string>;

/** Which reads need the admin credential. `/api/calibration` is public. */
export const ADMIN_READS: ReadonlySet<keyof CorrectnessReads> = new Set([
  "winners",
  "sourceCoverage",
  "linkRate",
  "gridSentinel",
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
 * that body as the payload is exactly the empty-200 trap. A 202 or non-2xx
 * body that parses as JSON is kept as the error's `body` — never as `data`.
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
      const text = await res.text().catch(() => "");
      return { status: "error", kind: "pending", detail: `HTTP 202 — no cached result yet${text ? `: ${text.slice(0, 160)}` : ""}`, ms: elapsed(), httpStatus: 202, body: parseJsonBody(text) };
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return { status: "error", kind: "http", detail: `HTTP ${res.status}`, ms: elapsed(), httpStatus: res.status, body: parseJsonBody(text) };
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

function parseJsonBody(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

export const INITIAL_READS: CorrectnessReads = {
  winners: { status: "loading" },
  calibration: { status: "loading" },
  sourceCoverage: { status: "loading" },
  linkRate: { status: "loading" },
  gridSentinel: { status: "loading" },
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
  const unverified = states.some(
    (s) => s === "unavailable" || s === "stale" || s === "freshness_unknown" || s === "partial" || s === "no_threshold",
  );
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
  freshness_unknown: 3,
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

// ─── Saved-only contracts (coverage + link rate) ────────────────────────────
//
// Both routes answer from a saved cache and nothing else, with a typed
// `cache_state` that the HTTP status must agree with. Anything that does not
// match is refused as a wrong shape — never read as "no data" or as a number.

/** `cache_state` → the HTTP status the route sends with it. */
const COVERAGE_CACHE_STATUS: Record<string, number> = {
  hit: 200,
  miss: 202,
  expired: 202,
  error: 503,
  malformed: 503,
  partial: 503,
  producer_error: 503,
};
const LINK_RATE_CACHE_STATUS: Record<string, number> = {
  hit: 200,
  miss: 202,
  error: 503,
  malformed: 503,
  unavailable: 503,
};
export const SAVED_CONTRACT_SCHEMA_VERSION = 1;

interface SavedAnswer {
  body: Record<string, unknown>;
  cacheState: string;
  reason: string;
  ms: number;
}

type TileBase = Omit<CorrectnessTile, "state" | "headline" | "rows" | "asOf">;

/**
 * The saved-contract body behind a read, or a finished tile when there is none:
 * loading / refused / timed out / unparseable reads keep their generic tiles,
 * and a 202 or 503 WITHOUT the contract's body is a plain failed read.
 */
function savedAnswer(base: TileBase, read: ReadResult, statusFor: Record<string, number>): SavedAnswer | CorrectnessTile {
  if (read.status === "loading") return readFailureTile(base, read)!;
  const httpStatus = read.httpStatus;
  const body = read.status === "ok" ? read.data : read.kind === "pending" || read.kind === "http" ? read.body : undefined;
  const isContract =
    isObj(body) &&
    body.schema_version === SAVED_CONTRACT_SCHEMA_VERSION &&
    typeof body.cache_state === "string" &&
    Object.prototype.hasOwnProperty.call(statusFor, body.cache_state) &&
    typeof body.reason === "string";
  if (!isContract) {
    return readFailureTile(base, read) ?? wrongShape(base, "not the saved-evidence contract", read.ms);
  }
  const cacheState = body.cache_state as string;
  if (statusFor[cacheState] !== httpStatus) {
    return wrongShape(base, `cache_state ${cacheState} sent as HTTP ${httpStatus ?? "unknown"}`, read.ms);
  }
  return { body, cacheState, reason: body.reason as string, ms: read.ms };
}

function isTile(x: SavedAnswer | CorrectnessTile): x is CorrectnessTile {
  return "key" in x;
}

/** A whole count: integers only — the saved contracts never carry fractions. */
function asWhole(v: unknown): number | null {
  return typeof v === "number" && Number.isInteger(v) && v >= 0 ? v : null;
}

function asTime(v: unknown): string | null {
  const s = asStr(v);
  return s && Number.isFinite(Date.parse(s)) ? s : null;
}

/** A server reason code, shown verbatim but bounded. */
function code(v: unknown): string {
  const s = asStr(v);
  return s ? s.slice(0, 80) : "reason not given";
}

const NO_NUMBER_HEADLINE: Record<string, string> = {
  miss: "Unavailable — nothing is saved yet, and this page does not compute it",
  expired: "Unavailable — the saved observation is past its retention",
  error: "Unavailable — the saved evidence could not be read",
  malformed: "Unavailable — the saved evidence was refused as malformed",
  partial: "Unavailable — the saved evidence was refused as incomplete",
  producer_error: "Unavailable — the producer failed and nothing earlier is saved",
  unavailable: "Unavailable — the saved snapshot records no data",
};

/** Why a saved answer is not current, in words, keyed by the server's reason. */
const NOT_CURRENT_WHY: Record<string, string> = {
  freshness_policy_unreviewed: "no reviewed freshness horizon was saved with it",
  source_identity_unknown: "the release that produced it is unknown",
  observation_clock_in_future: "its observation time is in the future",
  generated_at_in_future: "its generated_at is in the future",
  observation_older_than_horizon: "the observation is older than its 30-min horizon",
};

function producerErrorText(err: unknown): string | null {
  if (!isObj(err)) return null;
  return `${code(err.kind)}/${code(err.code)}`;
}

/** Freshness is out of the question: keep the graded verdict as history. */
function notCurrent(tile: CorrectnessTile, state: "stale" | "freshness_unknown", prefix: string): CorrectnessTile {
  return { ...tile, state, lastVerdict: tile.state, headline: `${prefix}. Last read: ${tile.headline}` };
}

// ─── 4. Source coverage ─────────────────────────────────────────────────────

/** The five sources /health §G checks, by coverage-row field name. */
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
  basketball_ncaab: "NCAAB",
  golf_pga: "PGA Golf",
};

/**
 * `/api/admin/event-source-coverage/cached`: the saved observation of the
 * dashboard's coverage query. The Tier-1 list is the route's own `tier1[]`
 * projection (every Tier-1 sport, Golf included, each over ITS OWN event
 * denominator) — a sport the observation had no events for stays on the tile as
 * unmeasured. A source the row marks not expected is skipped, not counted green.
 *
 * Current only on the route's `freshness: "fresh"`, and only until the saved
 * `fresh_until` (observation start + the reviewed 30 min) passes on this tab's
 * clock. `stale` reads stale; `unknown` (unreviewed policy, unknown release,
 * future clock) is graded but never current. Every non-hit answer keeps its own
 * reason. Nothing here asks the server to compute, warm or refresh.
 */
export function evaluateSourceCoverage(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "source_coverage" as const,
    title: "Tier-1 source coverage",
    method:
      "Share of each Tier-1 sport's events in the saved observation's window carrying each expected source, over that sport's own event count. Any expected source below 100% → red (/health §G). Age is from when the observation started, never from when this page read it.",
    source: CORRECTNESS_ENDPOINTS.sourceCoverage,
  };
  const saved = savedAnswer(base, read, COVERAGE_CACHE_STATUS);
  if (isTile(saved)) return saved;
  const { body: b, cacheState, reason, ms } = saved;
  const producerError = producerErrorText(b.producer_error);

  if (cacheState !== "hit") {
    const expired = isObj(b.expired_observation) ? asTime(b.expired_observation.observation_started_at) : null;
    const evidence = [
      ...(expired ? [`Expired observation started ${expired}, retained until ${code(b.retained_until)}`] : []),
      ...(producerError ? [`Latest producer attempt failed: ${producerError}`] : []),
    ];
    return {
      ...base,
      state: "unavailable",
      headline: `${NO_NUMBER_HEADLINE[cacheState]} (${code(reason)}${producerError && cacheState === "producer_error" ? `; ${producerError}` : ""})`,
      rows: [],
      asOf: null,
      readMs: ms,
      ...(evidence.length ? { evidence } : {}),
    };
  }

  const lg = isObj(b.last_good) ? b.last_good : null;
  const observedAt = lg ? asTime(lg.observation_started_at) : null;
  const tier1 = Array.isArray(b.tier1) ? b.tier1 : null;
  const freshness = b.freshness;
  if (!lg || !observedAt || lg.complete !== true || lg.unit !== "events" || !tier1 || tier1.length === 0) {
    return wrongShape(base, "a hit without its observation", ms);
  }
  if (freshness !== "fresh" && freshness !== "stale" && freshness !== "unknown") {
    return wrongShape(base, "unknown freshness", ms);
  }

  const rows: CorrectnessRow[] = [];
  for (const entry of tier1) {
    const sport = isObj(entry) ? asStr(entry.sport) : null;
    if (!isObj(entry) || !sport) return wrongShape(base, "a Tier-1 row without a sport", ms);
    const label = SPORT_LABEL[sport] ?? sport;
    if (entry.row_state === "no_in_window_events") {
      rows.push({ label, value: "no events in window", state: "unavailable", note: "nothing measured for this sport" });
      continue;
    }
    const total = asWhole(entry.denominator);
    if (entry.row_state !== "observed" || total === null || total === 0 || !isObj(entry.sources)) {
      return wrongShape(base, `Tier-1 row ${label}`, ms);
    }
    for (const src of COVERAGE_SOURCES) {
      const cell = entry.sources[src];
      const n = isObj(cell) ? asWhole(cell.count) : null;
      if (!isObj(cell) || n === null || n > total || typeof cell.expected !== "boolean") {
        return wrongShape(base, `Tier-1 row ${label} · ${COVERAGE_LABEL[src]}`, ms);
      }
      if (cell.expected === false) continue;
      rows.push({
        label: `${label} · ${COVERAGE_LABEL[src]}`,
        value: `${pct(n, total)} (${fmt(n)}/${fmt(total)})`,
        state: n >= total ? "green" : "red",
      });
    }
  }
  const graded = foldStates(rows.map((r) => r.state));
  rows.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state]);
  const red = rows.filter((r) => r.state === "red").length;
  const headline =
    graded === "green" ? "Every expected Tier-1 source on every event" : `${red} of ${rows.length} sport × source cells below 100%`;

  const evidence: string[] = [];
  const win = isObj(lg.window) ? lg.window : null;
  if (win && asTime(win.window_start) && asTime(win.window_end)) {
    evidence.push(`Window: events commencing ${code(win.window_start)} through ${code(win.window_end)}, both inclusive`);
  }
  const prov = isObj(lg.source_provenance) ? lg.source_provenance : null;
  if (prov) {
    const rev = asStr(prov.executing_source_revision);
    const rel = asStr(prov.executing_release_version);
    evidence.push(
      prov.provenance_status === "deployment_reported"
        ? `Produced by release ${rel ?? "unknown"} at ${rev ? rev.slice(0, 10) : "unknown revision"}`
        : "Producing release unknown",
    );
  }
  const freshUntil = asTime(b.fresh_until);
  const retainedUntil = asTime(b.retained_until);
  if (freshUntil) evidence.push(`Fresh until ${freshUntil}`);
  if (retainedUntil) evidence.push(`Kept until ${retainedUntil}`);
  if (producerError) evidence.push(`Latest producer attempt failed: ${producerError} — the retained observation is shown`);

  const tile: CorrectnessTile = { ...base, state: graded, headline, rows, asOf: observedAt, readMs: ms, evidence };
  if (retainedUntil && nowMs >= Date.parse(retainedUntil)) {
    return notCurrent(tile, "stale", "Stale — the saved observation has passed its retention in this open tab");
  }
  if (freshness === "fresh") {
    if (!freshUntil) return wrongShape(base, "fresh without fresh_until", ms);
    if (nowMs >= Date.parse(freshUntil)) {
      return notCurrent(tile, "stale", "Stale — the observation aged past its 30-min horizon in this open tab");
    }
    return tile;
  }
  if (freshness === "stale") return notCurrent(tile, "stale", `Stale — ${NOT_CURRENT_WHY.observation_older_than_horizon}`);
  const why = NOT_CURRENT_WHY[reason] ?? (reason === "latest_attempt_failed" ? "the server reports its freshness unknown" : code(reason));
  return notCurrent(tile, "freshness_unknown", `Freshness unknown — ${why}`);
}

// ─── 5. Link rate ───────────────────────────────────────────────────────────

const TIER1_LEAGUES: [string, string][] = [
  ["football", "NFL"],
  ["basketball", "NBA"],
  ["baseball", "MLB"],
  ["hockey", "NHL"],
];

/**
 * `/prediction-markets/link-rate/cached`: the saved link-rate snapshot, never
 * the inline compute. Graded on Tier-1 OPEN game markets per venue from COUNTS
 * — the payload's `link_rate` is `0` when `open_total` is 0, which would read a
 * nothing as a failure. The all-markets rate and its exclusions are shown,
 * uncoloured: no threshold is documented for them.
 *
 * NEVER CURRENT: the route says `freshness: "unreviewed"` — no horizon has been
 * reviewed for this payload, and its `generated_at` is stamped when the compute
 * RETURNED. So the tile shows the graded verdict as history with its age and is
 * never green; a snapshot the payload itself marks `stale` reads stale.
 */
export function evaluateLinkRate(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "link_rate" as const,
    title: "Game-market link rate",
    method:
      "Tier-1 (NFL/NBA/MLB/NHL) open Kalshi and Polymarket game markets linked to an event. Target 100% (/health §D); below → red. The overall rate has no documented threshold. Age is from the snapshot's generated_at (when its computation finished); no freshness horizon is reviewed for it, so it is never shown as current.",
    source: CORRECTNESS_ENDPOINTS.linkRate,
  };
  const saved = savedAnswer(base, read, LINK_RATE_CACHE_STATUS);
  if (isTile(saved)) return saved;
  const { body: b, cacheState, reason, ms } = saved;
  const d = isObj(b.payload) ? b.payload : null;

  if (cacheState !== "hit") {
    const detail = cacheState === "unavailable" && d ? code(d.stale_reason) : code(reason);
    const asOf = cacheState === "unavailable" ? asTime(b.generated_at) : null;
    return { ...base, state: "unavailable", headline: `${NO_NUMBER_HEADLINE[cacheState]} (${detail})`, rows: [], asOf, readMs: ms };
  }
  const asOf = asTime(b.generated_at);
  if (!d || !asOf || d.generated_at !== b.generated_at) return wrongShape(base, "a hit without its snapshot", ms);
  if (b.freshness !== "unreviewed" && b.freshness !== "unknown") return wrongShape(base, "unknown freshness", ms);
  if (!isObj(d.kalshi) || !isObj(d.polymarket)) return wrongShape(base, "no venue blocks", ms);
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
  const graded = foldStates(rows.map((r) => r.state));
  rows.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state]);
  const red = rows.filter((r) => r.state === "red").length;
  const headline = graded === "green" ? "Every open Tier-1 game market linked" : `${red} of ${rows.length} venue × league cells below 100%`;
  const tile: CorrectnessTile = {
    ...base,
    state: graded,
    headline,
    rows,
    related,
    asOf,
    readMs: ms,
    evidence: [`Snapshot age ${formatAge(ageSeconds(asOf, nowMs))}, from generated_at; freshness ${code(b.freshness)}`],
  };
  if (d.stale === true) return notCurrent(tile, "stale", `Stale snapshot (${code(d.stale_reason)})`);
  if (b.freshness === "unknown") return notCurrent(tile, "freshness_unknown", `Freshness unknown — ${NOT_CURRENT_WHY[reason] ?? code(reason)}`);
  return notCurrent(tile, "freshness_unknown", "Freshness unreviewed — no horizon is reviewed for this snapshot, so it is not a current verdict");
}

// ─── 6. Grid health ─────────────────────────────────────────────────────────

/** The leagues the Grid Sentinel audits (`tasks/grid_sentinel.py` GRID_LEAGUES). */
export const SENTINEL_GRID_LEAGUES = ["mlb", "nba", "nhl"] as const;
/**
 * Grids this tile has always shown that the Sentinel does NOT audit. Each stays
 * on the tile as "no Sentinel coverage" — unverified, never green, never
 * dropped — until a Sentinel run reports a verdict for it.
 */
export const UNCOVERED_GRIDS = ["golf"] as const;
/**
 * The Sentinels card's silence rule for this same rail (`SentinelsCard.tsx`:
 * daily 07:25 UTC beat × SILENCE_MULTIPLIER 1.5). Judged on the run's own
 * `generated_at`, never on when we fetched it.
 */
export const GRID_SENTINEL_BEAT_HOURS = 24;
export const GRID_SENTINEL_SILENCE_MULTIPLIER = 1.5;
export const GRID_SENTINEL_STALE_AFTER_S = GRID_SENTINEL_BEAT_HOURS * GRID_SENTINEL_SILENCE_MULTIPLIER * 3600;
/** A run stamp further ahead of this browser's clock than this is not a valid stamp. */
export const SOURCE_CLOCK_SKEW_S = 300;

const GRID_LABEL: Record<string, string> = { mlb: "MLB", nba: "NBA", nhl: "NHL", golf: "Golf" };
const gridLabel = (g: string) => GRID_LABEL[g] ?? g.toUpperCase();

/** The rail's own fail-honest statuses (`routes/admin.py` `_sentinel_last_payload`). */
const RAIL_STATUS_HEADLINE: Record<string, string> = {
  no_run_cached: "Unavailable — no Grid Sentinel run is saved in either store",
  unparseable: "Unavailable — the saved Sentinel run does not decode",
  wrong_shape: "Unavailable — the saved Sentinel run is not an object",
};

/** Coverage rows for when no run can be read: nothing about any grid is known. */
function gridRowsWithoutEvidence(): CorrectnessRow[] {
  return [
    ...SENTINEL_GRID_LEAGUES.map((g) => ({ label: gridLabel(g), value: "—", state: "unavailable" as const, note: "no readable Sentinel run" })),
    ...UNCOVERED_GRIDS.map(uncoveredRow),
  ];
}

function uncoveredRow(g: string): CorrectnessRow {
  return {
    label: gridLabel(g),
    value: "no Sentinel coverage",
    state: "unavailable",
    note: `The Grid Sentinel audits ${SENTINEL_GRID_LEAGUES.map(gridLabel).join(", ")} only — no verdict exists for this grid`,
  };
}

/**
 * One `scorecard.per_league[]` entry → a row. The Sentinel's `verdict` is the
 * authority (`grid_verdict`): `red` only for a REAL defect, `green_unverified`
 * when a check could not run, `green` otherwise. EXPLAINED (season-window
 * artifacts) and WATCH (blend-hidden source disagreement) are counted on the
 * row and never change its colour. A red is red even if its counts are
 * unreadable; a green is green only when its counts prove it.
 */
function sentinelLeagueRow(league: string, e: Record<string, unknown>): CorrectnessRow {
  const label = gridLabel(league);
  const verdict = asStr(e.verdict);
  const real = asCount(e.real_defects);
  const explained = asCount(e.explained_artifacts);
  const watch = asCount(e.watch);
  const skipped = Array.isArray(e.checks_skipped) ? e.checks_skipped.map((c) => String(c)) : null;
  const phase = asStr(e.phase);
  const n = (v: number | null) => (v === null ? "?" : fmt(v));
  const counts = `${n(real)} REAL · ${n(explained)} explained (season-window, not filed) · ${n(watch)} watch (blend-hidden, never red)`;
  const tail = [skipped && skipped.length > 0 ? `checks skipped: ${skipped.join(", ")}` : null, phase ? `phase: ${phase}` : null]
    .filter(Boolean)
    .join(" · ");
  const note = tail ? `${counts} · ${tail}` : counts;
  if (verdict === "red") {
    return { label, value: real ? `${fmt(real)} REAL defect${real === 1 ? "" : "s"}` : "REAL defects", state: "red", note };
  }
  if (verdict === "green_unverified") {
    return { label, value: "green, unverified", state: "partial", note: skipped && skipped.length > 0 ? note : `${note} · a check did not run` };
  }
  if (verdict === "green") {
    if (real === null || explained === null || watch === null || skipped === null) {
      return { label, value: "—", state: "unavailable", note: `green claimed, but a count is missing · ${note}` };
    }
    if (real > 0) {
      return { label, value: "—", state: "unavailable", note: `green claimed with REAL defects counted — inconsistent · ${note}` };
    }
    if (skipped.length > 0) return { label, value: "green, unverified", state: "partial", note };
    return { label, value: "clean", state: "green", note };
  }
  return { label, value: "—", state: "unavailable", note: `unknown verdict "${verdict ?? "missing"}" · ${note}` };
}

/** The run's own stamp, or why it cannot be used. */
function sentinelStamp(d: Record<string, unknown>, nowMs: number): { asOf: string | null; problem: string | null } {
  const raw = d.generated_at;
  const asOf = asStr(raw);
  if (asOf === null) return { asOf: null, problem: "the run carries no timestamp" };
  const t = Date.parse(asOf);
  if (!Number.isFinite(t)) return { asOf: null, problem: `the run's timestamp does not parse ("${asOf.slice(0, 40)}")` };
  if (t - nowMs > SOURCE_CLOCK_SKEW_S * 1000) return { asOf, problem: "the run's timestamp is in the future" };
  return { asOf, problem: null };
}

/** The additive `provenance` block (`durable_snapshots.read_sentinel_evidence`), when present. */
function sentinelProvenance(d: Record<string, unknown>, asOf: string | null): { problem: string | null; row: CorrectnessRow | null } {
  const mode = asStr(d.mode);
  const modeNote = mode === "detect_only" ? "detect-only run (issues not filed)" : null;
  if (!("provenance" in d)) {
    return { problem: null, row: { label: "Evidence served from", value: "cache, no provenance block", state: "no_threshold", note: modeNote ?? undefined } };
  }
  const p = d.provenance;
  if (!isObj(p)) return { problem: "its provenance block is unreadable", row: null };
  const problems: string[] = [];
  if (p.health === "UNKNOWN" || (Array.isArray(p.contract_errors) && p.contract_errors.length > 0)) {
    problems.push("its two evidence stores disagree");
  }
  if (p.complete === false) problems.push("its evidence is marked incomplete");
  const pStamp = asStr(p.generated_at);
  if (pStamp !== null && asOf !== null && Date.parse(pStamp) !== Date.parse(asOf)) {
    problems.push("its provenance timestamp disagrees with the run's own");
  }
  const source = asStr(p.source);
  const value = source === "durable" ? "durable store (last-known state)" : source === "volatile" ? "Redis" : source ?? "unknown store";
  const note = [asStr(p.note), modeNote].filter(Boolean).join(" · ") || undefined;
  return {
    problem: problems.length > 0 ? problems.join("; ") : null,
    row: { label: "Evidence served from", value, state: problems.length > 0 ? "unavailable" : "no_threshold", note },
  };
}

/**
 * `/api/admin/grid-sentinel/last`: the Grid Sentinel's saved run, read as-is.
 * This rail never computes. The page never triggers the Sentinel, never falls
 * back to the cockpit or the raw grid audit, and does not warm a cache.
 *
 * The tile cannot be green while any grid it shows has no Sentinel coverage.
 * That gap is visible on purpose; it is not a waiver of the requirement.
 */
export function evaluateGridHealth(read: ReadResult, nowMs: number): CorrectnessTile {
  const base = {
    key: "grid_health" as const,
    title: "Championship grid health",
    method:
      `Grid Sentinel verdict per league (daily 07:25 UTC). Red only for a REAL defect. EXPLAINED (season-window artifacts) and WATCH (blend-hidden source disagreement) are counted and never red. A skipped check is unverified. The Sentinel covers ${SENTINEL_GRID_LEAGUES.map(gridLabel).join(", ")}; ${UNCOVERED_GRIDS.map(gridLabel).join(", ")} has no Sentinel coverage and stays unverified. Stale ${GRID_SENTINEL_STALE_AFTER_S / 3600} h after the run (1.5× its beat). Not a raw audit penalty score.`,
    source: CORRECTNESS_ENDPOINTS.gridSentinel,
  };
  const failed = readFailureTile(base, read);
  if (failed) {
    if (failed.state === "loading") return failed;
    const headline = read.status === "error" && read.httpStatus === 503 ? "Unavailable — the Sentinel's evidence store could not be read (HTTP 503)" : failed.headline;
    return { ...failed, headline, rows: gridRowsWithoutEvidence() };
  }
  if (read.status !== "ok") return { ...wrongShape(base, "no data", 0), rows: gridRowsWithoutEvidence() };
  const d = read.data;
  if (!isObj(d)) return { ...wrongShape(base, "not an object", read.ms), rows: gridRowsWithoutEvidence() };
  const sc = isObj(d.scorecard) ? d.scorecard : null;
  if (!sc) {
    const status = asStr(d.status);
    const known = status !== null ? RAIL_STATUS_HEADLINE[status] : undefined;
    const errClass = asStr(d.error_class);
    const headline = known
      ? `${known}${errClass ? ` (${errClass})` : ""}`
      : status !== null
        ? `Unavailable — unrecognised rail status "${status.slice(0, 40)}"`
        : "Unavailable — unexpected response shape (no Sentinel scorecard)";
    return { ...base, state: "unavailable", headline, rows: gridRowsWithoutEvidence(), asOf: null, readMs: read.ms };
  }
  if (!Array.isArray(sc.per_league)) {
    return { ...wrongShape(base, "no scorecard.per_league[]", read.ms), rows: gridRowsWithoutEvidence() };
  }
  const entries = sc.per_league.filter(isObj);
  const leagueOf = (e: Record<string, unknown>) => (asStr(e.league) ?? "").toLowerCase();
  const reported = [...new Set(entries.map(leagueOf).filter((l) => l !== ""))];
  const covered = [...SENTINEL_GRID_LEAGUES, ...reported.filter((l) => !(SENTINEL_GRID_LEAGUES as readonly string[]).includes(l))];

  const rows: CorrectnessRow[] = [];
  for (const g of covered) {
    const matches = entries.filter((e) => leagueOf(e) === g);
    if (matches.length === 0) {
      rows.push({ label: gridLabel(g), value: "—", state: "unavailable", note: "not in the last Sentinel run" });
    } else if (matches.length > 1) {
      rows.push({ label: gridLabel(g), value: "—", state: "unavailable", note: "reported more than once in one run" });
    } else {
      rows.push(sentinelLeagueRow(g, matches[0]));
    }
  }
  const gaps = UNCOVERED_GRIDS.filter((g) => !covered.includes(g));
  for (const g of gaps) rows.push(uncoveredRow(g));

  const sentinelRows = rows.slice(0, covered.length);
  const red = sentinelRows.filter((r) => r.state === "red").length;
  const clean = sentinelRows.filter((r) => r.state === "green").length;
  const gapText = gaps.length > 0 ? ` · no Sentinel coverage: ${gaps.map(gridLabel).join(", ")}` : "";
  const headline =
    red > 0
      ? `${red} of ${covered.length} Sentinel leagues have REAL defects${gapText}`
      : clean === covered.length && gaps.length > 0
        ? `${covered.map(gridLabel).join(", ")} clean per the Grid Sentinel — ${gaps.map(gridLabel).join(", ")} has no Sentinel coverage, so no all-clear`
        : clean === covered.length
          ? `All ${covered.length} grids clean per the Grid Sentinel`
          : `${clean} of ${covered.length} Sentinel leagues verified clean${gapText}`;

  const related: CorrectnessRow[] = [];
  const sum = (k: string) => {
    const vals = entries.map((e) => asCount(e[k]));
    return vals.some((v) => v === null) ? null : vals.reduce<number>((a, v) => a + (v ?? 0), 0);
  };
  const explainedTotal = sum("explained_artifacts");
  const watchTotal = sum("watch");
  related.push({ label: "EXPLAINED — season-window artifacts, not filed", value: explainedTotal === null ? "—" : fmt(explainedTotal), state: explainedTotal === null ? "unavailable" : "no_threshold" });
  related.push({ label: "WATCH — blend-hidden source disagreement, never red", value: watchTotal === null ? "—" : fmt(watchTotal), state: watchTotal === null ? "unavailable" : "no_threshold" });
  const errors = Array.isArray(d.errors) ? d.errors : [];
  if (errors.length > 0) {
    related.push({ label: "Errors in the run", value: fmt(errors.length), state: "unavailable", note: JSON.stringify(errors[0]).slice(0, 160) });
  }

  const { asOf, problem: stampProblem } = sentinelStamp(d, nowMs);
  const prov = sentinelProvenance(d, asOf);
  if (prov.row) related.push(prov.row);

  const state = foldStates(rows.map((r) => r.state));
  const tile: CorrectnessTile = { ...base, state, headline, rows, related, asOf, readMs: read.ms };
  const age = stampProblem ? null : ageSeconds(asOf, nowMs);
  const why =
    stampProblem ??
    prov.problem ??
    (age !== null && age > GRID_SENTINEL_STALE_AFTER_S ? `the last run is ${formatAge(age)}, past ${GRID_SENTINEL_STALE_AFTER_S / 3600} h` : null);
  if (!why) return tile;
  return { ...withFreshness(tile, true), headline: `Stale — ${why}. Last read: ${headline}` };
}

// ─── The page as a whole ────────────────────────────────────────────────────

export function evaluateAll(reads: CorrectnessReads, nowMs: number): CorrectnessTile[] {
  return [
    evaluateWinnerCoverage(reads.winners, nowMs),
    evaluateGuessFamily(reads.winners, reads.calibration),
    evaluateCategoryMce(reads.calibration),
    evaluateSourceCoverage(reads.sourceCoverage, nowMs),
    evaluateLinkRate(reads.linkRate, nowMs),
    evaluateGridHealth(reads.gridSentinel, nowMs),
  ];
}

export interface ConsoleSummary {
  status: "good" | "warning" | "critical" | "loading" | "unauthorized";
  summary: string;
}

/**
 * The page header. `good` needs all six tiles green — which today it cannot be,
 * because the guess-family tile has no endpoint and the grid tile has no
 * Sentinel coverage for Golf. That is the honest answer to "can we trust our
 * numbers today?" while part of the six cannot be read.
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
