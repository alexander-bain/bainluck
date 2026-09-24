/**
 * Observation support for the win-probability chart (#7878, web half).
 *
 * THE DEFECT. `OddsChart` buckets every series by minute, seeds every minute
 * of the domain, then forward-fills each plotted key through the seeded
 * minutes with no bound on how old the carried value is. A minute the source
 * reported and a minute nobody looked at come out identical, so a 3h17m hole
 * (issue specimen 15316479) and a 73.6-minute hole (specimen 15315912) were
 * both drawn as one solid line — and, on 15315912, a diagonal one, because the
 * two ends of the hole differed and recharts joined them.
 *
 * WHAT THE PAYLOAD CAN AND CANNOT TELL US. A `win_prob_history` point carries
 * `timestamp` (the row's `captured_at`), the value, `game_state`, and — only on
 * a live event — `live_edge: true` for the one point the backend synthesises at
 * "now" from the last real row (#920). It does NOT carry `valid_until` or
 * `reading_count`, which is where the snapshot table records "we looked again
 * and it had not moved". So, from the payload alone:
 *
 *   - a minute WITH a point is an observation (a real row, including the
 *     live-cadence heartbeat rows live/035 writes at an unchanged price);
 *   - a minute WITHOUT a point is ambiguous: pre-match, the dedup writes no
 *     row while a quote sits still, so silence is the NORMAL shape of an
 *     unchanged market; in game, the heartbeat floor means an unchanged quote
 *     still produces a row roughly every poll, so silence is unusual;
 *   - the synthetic `live_edge` point is a delivery time, not an observation.
 *
 * "Delivery time is not observation time." A re-served old quote is not a new
 * reading, and this module never treats it as one.
 *
 * THE DISPLAY POLICY (not a proof of outage). An interval between consecutive
 * observations is UNSUPPORTED when all of:
 *   1. both ends are at or after the scheduled commence time (pre-match
 *      intervals are never judged — measured pre-match p99 is 2.2h and the
 *      longest 5.6 days; a rule applied there would shatter every healthy
 *      pre-match line into confetti);
 *   2. it is longer than `SUPPORT_FLOOR_S` (600s — above Kalshi's measured
 *      in-game p99 of 227s and above the longest in-game interval Polymarket
 *      produced at all, 372s); and
 *   3. it is longer than `SUPPORT_CADENCE_MULTIPLE` (15) times the series'
 *      OWN median in-game interval, so a legitimately sparse series is judged
 *      against its own rhythm, never a stranger's.
 * The same rule judges the TRAILING interval from a series' last observation
 * to the chart's right edge (the synthetic live edge on a live game, or the
 * last minute the domain draws). Both numbers and the measurement behind them
 * are PR #7896's (native half of the same issue); this file uses the same
 * thresholds so the two surfaces agree about the same payload.
 *
 * WHAT THE CONSUMER DOES WITH THE VERDICT (in `OddsChart`):
 *   - interior unsupported interval: the solid line stops at the last
 *     observation and resumes at the next; a faint dashed CONNECTOR joins the
 *     two, explained on hover as missing observations, never as a price;
 *   - trailing unsupported interval: the solid line ends at the last
 *     observation, nothing is drawn after it, and the chart says how old that
 *     reading is;
 *   - a supported interval — including a genuinely re-observed unchanged
 *     quote — stays a solid line, exactly as today.
 *
 * MINIMAL PRODUCER CONTRACT that would replace the cadence heuristic with
 * evidence: serve `valid_until` (and `reading_count`) on each
 * `win_prob_history` point, as `history` points already carry. When a point
 * carries `valid_until`, the interval up to it is observed by definition and
 * this module honours it before any heuristic (see `observedUntil`). Absent
 * the field the consumer falls back to the policy above — it never invents
 * freshness from an unchanged value.
 *
 * SUPERSEDED FOR CLASSIFYING SERVERS (Codex card-B decision, 2026-09-24). The
 * `valid_until` idea above was refuted: a changed value closes the old row at
 * the NEW reading's time, so a row read at 10:00 and 10:01 and then silent
 * until 12:00 reads `valid_until=12:00` — a 119-minute hole that looks
 * covered. The producer shipped instead (#8438, `backend/app/utils/
 * winprob_evidence.py`): `evidence_contract = {v: "7878.v1", resolution_s}`
 * once per response, and an `evidence` key on every point that is NOT a plain
 * reading. When a payload carries that contract the chart runs
 * `classifyUnderContract` below and the cadence heuristic is not consulted:
 *
 *   - only a plain reading (no `evidence` key) or `observed` proves anything;
 *     `observed.covered_through` is the only thing that extends a reading's
 *     coverage past its own timestamp — `valid_until` never does;
 *   - `candle`, `price_history`, `terminal_row` and `final` points are still
 *     DRAWN where they fall (a venue aggregate and the result are real values)
 *     but extend no coverage; an unknown or malformed kind is treated the same
 *     way (fails closed);
 *   - `live_edge` stays a delivery time: it anchors the trailing interval and
 *     is never a reading;
 *   - an interval wider than `resolution_s` (G, 300s) is UNKNOWN — exactly G is
 *     covered. G is a display resolution, not a freshness SLA, and the chart
 *     says "no readings", never "the feed was down".
 *
 * Pre-match stays unjudged in contract mode too, for the reason in point 1
 * above (the pre-match writer stores no row while a quote sits still, so a
 * G-sized rule there would dash every healthy pre-match line); what changes is
 * that an interval straddling the start is judged from the start instead of
 * being left joined — the stretch after kick-off is in-game however it began.
 */

/** The only contract version this client knows how to read. */
export const EVIDENCE_CONTRACT_V = "7878.v1";

/** One reading of one series, as the chart sees it. */
export interface SupportObservation {
  /** `captured_at`, ms since epoch. */
  atMs: number;
  /**
   * `valid_until`, ms since epoch, when the payload carries it — "we looked
   * again at this time and it still read this value". Extends support to
   * that instant with no heuristic.
   */
  observedUntilMs?: number;
  /**
   * The backend's synthetic right-edge point (`live_edge: true`), or the
   * settled terminal point — anything that is NOT a reading of the source.
   * A synthetic point anchors the trailing interval; it is never an
   * observation and never seeds the cadence.
   */
  synthetic?: boolean;
  /**
   * Contract mode only: a point that is drawn at its time but proves nothing
   * about observation — a venue candle or price-history backfill, a finished
   * game's rewritten terminal row, the synthesised result, or any evidence
   * kind this client does not know. It can END an interval (the line has to
   * reach it somehow) but never extends coverage past its own instant.
   */
  notEvidence?: boolean;
}

export interface UnsupportedInterval {
  /** Last observation before the hole (ms). */
  fromMs: number;
  /** Next observation after the hole, or the trailing anchor (ms). */
  toMs: number;
  /** `interior` resumes at a later observation; `trailing` never does. */
  kind: "interior" | "trailing";
}

export interface SeriesSupport {
  /** Unsupported intervals in time order; empty for a healthy series. */
  unsupported: UnsupportedInterval[];
  /** Last real observation (ms), or null when the series has none. */
  lastObservedMs: number | null;
  /**
   * The series' own in-game cadence (median interval between consecutive
   * observations with both ends at/after `gameStartMs`), or null when there
   * are no such intervals — in which case nothing is judged.
   */
  inGameMedianS: number | null;
}

export const SUPPORT_FLOOR_S = 600;
export const SUPPORT_CADENCE_MULTIPLE = 15;

export interface SupportOptions {
  /** Scheduled commence time (ms). `null` ⇒ no in-game domain ⇒ nothing judged. */
  gameStartMs: number | null;
  /**
   * The chart's right edge (ms): the last minute the domain draws. When the
   * series carries a synthetic live-edge point that point's time is used
   * instead, because that is where the forward-fill would otherwise carry to.
   */
  domainEndMs: number | null;
  floorS?: number;
  cadenceMultiple?: number;
  /**
   * The served contract's `resolution_s` (see `evidenceResolutionS`). When set
   * the series is judged by `classifyUnderContract` and the floor/cadence
   * heuristic is not consulted at all.
   */
  evidenceResolutionS?: number | null;
}

/**
 * `resolution_s` from a served `evidence_contract`, or null when the payload
 * carries no contract this client can read — in which case the caller keeps
 * the cadence heuristic, exactly as it did before the producer shipped.
 */
export function evidenceResolutionS(contract: unknown): number | null {
  if (!contract || typeof contract !== "object") return null;
  const { v, resolution_s } = contract as { v?: unknown; resolution_s?: unknown };
  if (v !== EVIDENCE_CONTRACT_V) return null;
  if (typeof resolution_s !== "number" || !Number.isFinite(resolution_s) || resolution_s <= 0) return null;
  return resolution_s;
}

/** The subset of a served `win_prob_history` point the contract reads. */
export interface ContractPoint {
  timestamp: string;
  live_edge?: boolean;
  evidence?: unknown;
}

/**
 * One served point as the contract classifies it. `valid_until` is never read.
 * Returns null for an unparseable timestamp (the point cannot testify either way).
 */
export function contractObservation(p: ContractPoint): SupportObservation | null {
  const atMs = Date.parse(p.timestamp);
  if (!Number.isFinite(atMs)) return null;
  const evidence = p.evidence;
  const kind =
    evidence && typeof evidence === "object" ? (evidence as { kind?: unknown }).kind : undefined;
  if (p.live_edge === true || kind === "live_edge") return { atMs, synthetic: true };
  // No key at all: a plain reading at its own timestamp.
  if (evidence === undefined || evidence === null) return { atMs };
  if (kind === "observed") {
    const raw = (evidence as { covered_through?: unknown }).covered_through;
    const through = typeof raw === "string" ? Date.parse(raw) : NaN;
    // A malformed span proves nothing beyond the reading itself.
    return Number.isFinite(through) && through > atMs ? { atMs, observedUntilMs: through } : { atMs };
  }
  // candle · price_history · terminal_row · final · anything unrecognised.
  return { atMs, notEvidence: true };
}

/**
 * Judge one series. Pure; sorts its input; never drops an observation.
 */
export function classifySeriesSupport(
  observations: SupportObservation[],
  opts: SupportOptions,
): SeriesSupport {
  if (opts.evidenceResolutionS != null) {
    return classifyUnderContract(observations, opts, opts.evidenceResolutionS);
  }
  const floorS = opts.floorS ?? SUPPORT_FLOOR_S;
  const multiple = opts.cadenceMultiple ?? SUPPORT_CADENCE_MULTIPLE;

  const real = observations
    .filter((o) => !o.synthetic && Number.isFinite(o.atMs))
    .sort((a, b) => a.atMs - b.atMs);
  const synthetic = observations
    .filter((o) => o.synthetic && Number.isFinite(o.atMs))
    .sort((a, b) => a.atMs - b.atMs);

  if (real.length === 0) {
    return { unsupported: [], lastObservedMs: null, inGameMedianS: null };
  }
  const lastObservedMs = real[real.length - 1].atMs;
  const gameStart = opts.gameStartMs;
  if (gameStart === null || !Number.isFinite(gameStart)) {
    return { unsupported: [], lastObservedMs, inGameMedianS: null };
  }

  // The series' own in-game rhythm, over exactly the intervals the rule can
  // act on: a long pre-match sleep cannot inflate it and thereby excuse a
  // real in-game hole. Upper median, as the native half computes it.
  const inGame: number[] = [];
  for (let i = 1; i < real.length; i++) {
    if (real[i - 1].atMs >= gameStart) {
      inGame.push((real[i].atMs - real[i - 1].atMs) / 1000);
    }
  }
  if (inGame.length === 0) {
    return { unsupported: [], lastObservedMs, inGameMedianS: null };
  }
  const sortedIntervals = [...inGame].sort((a, b) => a - b);
  const medianS = sortedIntervals[Math.floor(sortedIntervals.length / 2)];
  const boundS = Math.max(floorS, multiple * medianS);

  const unsupported: UnsupportedInterval[] = [];

  const judge = (from: SupportObservation, toMs: number, kind: UnsupportedInterval["kind"]) => {
    // A `valid_until` that reaches the far end is evidence; no heuristic.
    const coveredUntil = from.observedUntilMs ?? from.atMs;
    const holeStartMs = Math.max(from.atMs, coveredUntil);
    if (holeStartMs >= toMs) return;
    if (holeStartMs < gameStart || toMs < gameStart) return; // pre-match: never judged
    const seconds = (toMs - holeStartMs) / 1000;
    if (seconds > boundS) {
      unsupported.push({ fromMs: holeStartMs, toMs, kind });
    }
  };

  for (let i = 1; i < real.length; i++) {
    judge(real[i - 1], real[i].atMs, "interior");
  }

  // Trailing: to the synthetic live edge if the payload served one after the
  // last real point, else to the drawn domain's end.
  const last = real[real.length - 1];
  const liveEdge = synthetic.length > 0 ? synthetic[synthetic.length - 1].atMs : null;
  const trailingAnchor =
    liveEdge !== null && liveEdge > last.atMs
      ? liveEdge
      : opts.domainEndMs !== null && Number.isFinite(opts.domainEndMs)
        ? opts.domainEndMs
        : null;
  if (trailingAnchor !== null) {
    judge(last, trailingAnchor, "trailing");
  }

  return { unsupported, lastObservedMs, inGameMedianS: medianS };
}

/**
 * Judge one series under the served evidence contract (see the header).
 * Every consecutive pair of DRAWN points is an interval; its hole starts where
 * the earlier point's proven coverage ends (its own instant, or
 * `covered_through` for an `observed` reading) and is unsupported when it is
 * wider than G. `inGameMedianS` is always null: no cadence is consulted.
 */
function classifyUnderContract(
  observations: SupportObservation[],
  opts: SupportOptions,
  resolutionS: number,
): SeriesSupport {
  const drawn = observations
    .filter((o) => !o.synthetic && Number.isFinite(o.atMs))
    .sort((a, b) => a.atMs - b.atMs);
  const synthetic = observations
    .filter((o) => o.synthetic && Number.isFinite(o.atMs))
    .sort((a, b) => a.atMs - b.atMs);
  const proving = drawn.filter((o) => !o.notEvidence);
  const lastObservedMs = proving.length > 0 ? proving[proving.length - 1].atMs : null;

  const gameStart = opts.gameStartMs;
  if (drawn.length === 0 || gameStart === null || !Number.isFinite(gameStart)) {
    return { unsupported: [], lastObservedMs, inGameMedianS: null };
  }

  const unsupported: UnsupportedInterval[] = [];
  const judge = (from: SupportObservation, toMs: number, kind: UnsupportedInterval["kind"]) => {
    const coveredUntil = from.notEvidence ? from.atMs : Math.max(from.atMs, from.observedUntilMs ?? from.atMs);
    // Pre-match is not judged; the part of an interval after the start is.
    const holeStartMs = Math.max(coveredUntil, gameStart);
    if (toMs <= holeStartMs) return;
    if ((toMs - holeStartMs) / 1000 > resolutionS) {
      unsupported.push({ fromMs: holeStartMs, toMs, kind });
    }
  };

  for (let i = 1; i < drawn.length; i++) {
    judge(drawn[i - 1], drawn[i].atMs, "interior");
  }

  const last = drawn[drawn.length - 1];
  const liveEdge = synthetic.length > 0 ? synthetic[synthetic.length - 1].atMs : null;
  const trailingAnchor =
    liveEdge !== null && liveEdge > last.atMs
      ? liveEdge
      : opts.domainEndMs !== null && Number.isFinite(opts.domainEndMs)
        ? opts.domainEndMs
        : null;
  if (trailingAnchor !== null) {
    judge(last, trailingAnchor, "trailing");
  }

  return { unsupported, lastObservedMs, inGameMedianS: null };
}

/** Where a minute bucket stands relative to a series' unsupported intervals. */
export type BucketSupport =
  | { kind: "supported" }
  | { kind: "gap"; interval: UnsupportedInterval };

/**
 * Classify one minute bucket. `bucketMs` is the bucket's floored minute. A
 * bucket is "in the hole" when it lies strictly after the last observation's
 * minute and strictly before the next observation's minute — the two endpoint
 * minutes keep their real values so the solid line ends and resumes ON the
 * observations rather than one minute short of them.
 */
export function bucketSupport(bucketMs: number, support: SeriesSupport): BucketSupport {
  for (const iv of support.unsupported) {
    const fromMinute = Math.floor(iv.fromMs / 60_000) * 60_000;
    const toMinute = Math.floor(iv.toMs / 60_000) * 60_000;
    if (bucketMs > fromMinute && (iv.kind === "trailing" ? bucketMs <= toMinute : bucketMs < toMinute)) {
      return { kind: "gap", interval: iv };
    }
  }
  return { kind: "supported" };
}

/** "3h 17m" / "45m" / "<1m" — for the stale-edge caption and tooltip. */
export function formatAge(ms: number): string {
  const totalMin = Math.floor(Math.max(0, ms) / 60_000);
  if (totalMin < 1) return "<1m";
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h === 0) return `${m}m`;
  if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return `${h}h ${m}m`;
}
