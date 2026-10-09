import { isQuoteStreamStatus } from "./eventQuoteStream";
import { isFinishedStatus } from "./eventState";
import { compareFoldRevision, frameFoldOrder, parseFoldRevision } from "./foldRevision";
import { PINNABLE_HERO_SOURCE } from "./chartEdgePin";
import type { LiveStreamFrame } from "./liveStreamController";
import type { OddsHistoryPoint, WinProbHistoryPoint } from "./types";

// One hour at the nominal five-second publication cadence. This is a bound on
// session memory, not a sampling rule: every accepted frame keeps its own time.
export const MAX_LIVE_CHART_FRAMES = 720;
export type LiveChartPoint = { timestamp: string; home_probability: number };

/**
 * One accepted publication: the BLEND the event stamped, and — when the frame
 * carried a usable one — the venue reading behind it.
 *
 * The two are different quantities and they go to different places. `p` is the
 * answer ("the blend is the product"); `source_probability` is one feed's own
 * price, the same number the backend persists into
 * `win_prob_history[<source>][].home_probability` (`live_blend_refresh` stamps
 * both from one reading). Keeping the source reading here does not put it on
 * the plot — `mergeLiveChartHistory` decides that, under one narrow rule.
 */
export type LiveChartFrame = LiveChartPoint & {
  source?: string;
  source_probability?: number;
  rev?: Record<string, number> | null;
};

export type ChartHistory = {
  aggregate_line?: LiveChartPoint[] | null;
  win_prob_history?: Record<string, WinProbHistoryPoint[]> | null;
  history?: OddsHistoryPoint[] | null;
};

/** Record the published BLEND, never the individual venue's source_value. */
export function rememberLiveChartFrame(
  points: LiveChartFrame[], frame: LiveStreamFrame, eventId: number,
): LiveChartFrame[] {
  if (frame.event_id !== eventId || !isQuoteStreamStatus(frame.status) ||
      typeof frame.p !== "number" || !Number.isFinite(frame.p) ||
      frame.p < 0 || frame.p > 1 || !Number.isFinite(Date.parse(frame.updated_at))) {
    return points;
  }
  const instant = Date.parse(frame.updated_at);
  const existing = points.find(point => Date.parse(point.timestamp) === instant);
  if (existing?.home_probability === frame.p) return points;
  const next: LiveChartFrame = {
    timestamp: frame.updated_at, home_probability: frame.p,
    ...(frame.rev ? { rev: frame.rev } : {}),
  };
  // Carried on the same validity bar as `p`: a probability, finite, in range.
  // A frame missing it is still a perfectly good blend observation — it simply
  // extends nothing below.
  if (typeof frame.source === "string" && frame.source !== "" &&
      typeof frame.source_value === "number" && Number.isFinite(frame.source_value) &&
      frame.source_value >= 0 && frame.source_value <= 1) {
    next.source = frame.source;
    next.source_probability = frame.source_value;
  }
  return [
    ...points.filter(point => Date.parse(point.timestamp) !== instant),
    next,
  ].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .slice(-MAX_LIVE_CHART_FRAMES);
}

/**
 * Extend the SERVED source series with this session's own readings of them.
 *
 * WHY THIS EXISTS (#8066's remainder, handed over by ux/1443). The backend
 * emits `aggregate_line` only where it blended two or more sources. #920 put
 * the stream's blend into that array, which on a single-source event drew a
 * 2-vertex line under the blend's name over the real one; #8066 fixed the
 * chart to require the blend to be the BACKEND's. Correct — and it costs a
 * single-source live page its push speed, because the only line on that plot
 * is the source line, and nothing was feeding it. It then advanced on the 32 s
 * poll while the page held a reading three seconds old. This pays that back.
 *
 * TWO RULES, BOTH LOAD-BEARING:
 *
 *   1. NEVER MINT A SERIES. A source the payload does not already carry is
 *      skipped, however good its frames. Creating `win_prob_history[x]` from
 *      two pushed frames would put a 2-vertex line on the plot with no legend
 *      entry, no colour and no served history behind it — #8066 again, wearing
 *      the source's face instead of the blend's.
 *   2. STRICTLY NEWER THAN THE LAST REAL READING, AND NEVER BEHIND A STALE
 *      ENDPOINT. A live payload can end in the backend's synthetic `live_edge`
 *      point at "now" carrying the last STORED value. A pushed reading stamped
 *      after that stored reading but before the edge is newer than the number
 *      the edge carries — the backend stores only some publications (#10090:
 *      on 15319175 it stored 0.36 at 19:20:19 and never 218's 0.37 at
 *      19:20:28), so the next poll's edge at 19:20:57 still carried 0.36 and
 *      dropping the reading froze the line one revision behind the headline.
 *      So such a reading is inserted before the edge, and the edge carries the
 *      newest one at or before its own time: what the backend would have
 *      served had it stored that publication. The edge keeps its delivery time
 *      and flag; nothing is drawn backwards because the endpoint moves with
 *      the reading. Ties with a REAL served point go to the served point.
 *      "The last real reading" includes its `observed` coverage: a reading
 *      at or before `covered_through` is older than the backend's proof that
 *      the served value still held, so it changes nothing.
 *   3. AN EXCURSION ALREADY DRAWN IS NOT ERASED BY A LATER SPARSE ROW (#10795).
 *      Rule 2 is about the ENDPOINT. Applied to every reading, it threw away
 *      the dip the page had just drawn as soon as the backend stored any later
 *      row. On 15325669 the reader watched 0.565 → 0.525 → 0.51 → 0.565 at
 *      20:18:32; the next history response stored a later reading, the cutoff
 *      moved past the dip, and the line went flat. A blended page never lost
 *      it, because `aggregate_line` keeps every session frame. So the session's
 *      readings that fall strictly between two served points stay, under the
 *      tail's own rules (`sessionReadingsBetween`).
 *
 * What lands is an observation, not a delivery: these frames are stamped at
 * `live_blend_refresh`'s write time, so they carry no `live_edge` flag and
 * `chartObservationSupport` counts them as the real readings they are. Nothing
 * is carried forward or interpolated — `away_probability` is `null` because
 * the frame does not carry one, never the previous point's.
 */
function extendServedSourceSeries(
  served: Record<string, WinProbHistoryPoint[]> | null | undefined,
  points: LiveChartFrame[],
): Record<string, WinProbHistoryPoint[]> | null {
  if (!served) return null;
  let next: Record<string, WinProbHistoryPoint[]> | null = null;
  for (const [source, series] of Object.entries(served)) {
    if (!series?.length) continue;
    const edge = Date.parse(series[series.length - 1].timestamp);
    if (!Number.isFinite(edge)) continue;
    // The trailing synthetic edge(s), if any, and the real reading before them.
    let real = series.length - 1;
    while (real >= 0 && isSyntheticEdge(series[real])) real--;
    const lastRead = real >= 0 && real < series.length - 1 ? Date.parse(series[real].timestamp) : edge;
    if (!Number.isFinite(lastRead)) continue;
    // A real reading served as `observed` was seen again, unmoved, through
    // `covered_through`; a pushed reading at or before that is older than the
    // proof and must not overwrite it. Only a REAL reading's coverage counts —
    // the edge's own evidence is a delivery time, never an observation.
    const coverage = real >= 0 && series[real].evidence?.kind === "observed"
      ? Date.parse(series[real].evidence?.covered_through ?? "") : NaN;
    const readAt = Number.isFinite(coverage) && coverage > lastRead ? coverage : lastRead;
    // `points` is kept sorted by `rememberLiveChartFrame`, so a filter
    // preserves that order.
    const own = points
      .filter(point => point.source === source && typeof point.source_probability === "number")
      .map(sessionReading);
    const readings = own.filter(point => Date.parse(point.timestamp) > readAt);
    const interior = real >= 0 ? sessionReadingsBetween(series, real, own) : [];
    let behind = readings.filter(point => Date.parse(point.timestamp) <= edge);
    const ahead = readings.filter(point => Date.parse(point.timestamp) > edge);
    // Readings that only re-confirm the carried value change no endpoint;
    // #10671 already records them as coverage, and nothing is drawn for them.
    if (!behind.some(point => point.home_probability !== series[real]?.home_probability)) behind = [];
    if (behind.length === 0 && ahead.length === 0 && interior.length === 0) continue;
    // No reading in `interior` shares an instant with a served point, so the
    // order is total.
    const head = interior.length === 0 ? series.slice(0, real + 1)
      : [...series.slice(0, real + 1), ...interior]
        .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
    let tail: WinProbHistoryPoint[] = [];
    if (behind.length > 0) {
      // Each synthetic point re-delivers the newest reading at or before it.
      const carried = series.slice(real + 1).map(point => {
        const at = Date.parse(point.timestamp);
        let newest: WinProbHistoryPoint | null = null;
        for (const reading of behind) if (Date.parse(reading.timestamp) <= at) newest = reading;
        return newest === null || newest.home_probability === point.home_probability ? point
          : { ...point, home_probability: newest.home_probability, away_probability: null, draw_probability: null };
      });
      // Stable sort: a reading tied with an edge stays before it.
      tail = [...behind, ...carried]
        .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
    }
    next ??= { ...served };
    next[source] = behind.length > 0
      ? [...head, ...tail, ...ahead]
      : [...head, ...series.slice(real + 1), ...ahead];
  }
  return next;
}

function sessionReading(point: LiveChartFrame): WinProbHistoryPoint {
  return {
    timestamp: point.timestamp,
    home_probability: point.source_probability as number,
    away_probability: null,
  };
}

/**
 * #10795 — the session's readings that sit strictly between two served points
 * at or before the last real reading, `series[real]`.
 *
 * Each interval between consecutive served points is judged on its own, with
 * the same bar the tail uses after `series[real]`:
 *
 *   - It moved. A run whose readings all equal the served value that opened
 *     the interval proves only "it held", and that is #10671's evidence to
 *     record, not a line to draw. A run with one differing reading keeps ALL
 *     of its readings, so the reversal is drawn at its real time too.
 *   - The backend's proof wins. A reading at or before an `observed` point's
 *     `covered_through` is not admitted. A reading at the same instant as a
 *     served point is not admitted either.
 *   - It has a real reading to join. Nothing goes before the first served
 *     point, after a synthetic point, or after a served point with no number.
 *     A gap the server left open stays open.
 *
 * Only readings this page received are used (at most `MAX_LIVE_CHART_FRAMES`).
 * Nothing persists: a reload shows durable history only.
 */
function sessionReadingsBetween(
  series: WinProbHistoryPoint[], real: number, own: WinProbHistoryPoint[],
): WinProbHistoryPoint[] {
  const lastRead = Date.parse(series[real].timestamp);
  const runs = new Map<number, WinProbHistoryPoint[]>();
  let opening = -1;
  for (const reading of own) {
    const at = Date.parse(reading.timestamp);
    if (!Number.isFinite(at)) continue;
    if (!(at < lastRead)) break;
    while (opening < real && Date.parse(series[opening + 1].timestamp) < at) opening++;
    if (opening < 0 || Date.parse(series[opening + 1].timestamp) === at) continue;
    const from = series[opening];
    const value = from.home_probability;
    if (isSyntheticEdge(from) || typeof value !== "number" || !Number.isFinite(value)) continue;
    const held = from.evidence?.kind === "observed" ? Date.parse(from.evidence.covered_through ?? "") : NaN;
    if (Number.isFinite(held) && at <= held) continue;
    const run = runs.get(opening);
    if (run) run.push(reading); else runs.set(opening, [reading]);
  }
  const kept: WinProbHistoryPoint[] = [];
  for (const [index, run] of runs) {
    const value = series[index].home_probability;
    if (run.some(reading => reading.home_probability !== value)) kept.push(...run);
  }
  return kept;
}

/** The backend's synthetic "now" point (#920 / #7878): a delivery time, not a reading. */
function isSyntheticEdge(point: WinProbHistoryPoint): boolean {
  return point.live_edge === true || point.evidence?.kind === "live_edge";
}

/**
 * #10671 — a source that re-confirmed its last served value while the page was
 * open was observed through that confirmation.
 *
 * The backend stores a `win_prob_history` row only when a source's value
 * CHANGES, so a model that re-publishes the same number every minute leaves
 * one stored row and then silence. Under the 7878.v1 contract that silence is
 * a trailing hole: the chart withdrew the line and printed "last reading
 * 9:11 PM · none in the 5m since" on 15324650 while the page had received the
 * model's 0.9262 again at 9:15 and 9:16. Those frames sit before the served
 * `live_edge`, so `extendServedSourceSeries` rightly cannot draw them.
 *
 * What they prove is the contract's own `observed` shape — "looked again, it
 * had not moved" — so that is what the last served reading gets:
 * `covered_through` = the latest frame for that source that carries exactly the
 * same value, counting only frames before the first one that differs (after a
 * change, an equal value later is a return, not a continuation). Nothing is
 * drawn, no value is moved, and a reading the contract marks as anything but a
 * plain reading or `observed` is left alone (fails closed, as the chart does).
 */
function confirmServedSourceCoverage(
  served: Record<string, WinProbHistoryPoint[]> | null | undefined,
  points: LiveChartFrame[],
): Record<string, WinProbHistoryPoint[]> | null {
  if (!served) return null;
  let next: Record<string, WinProbHistoryPoint[]> | null = null;
  for (const [source, series] of Object.entries(served)) {
    if (!series?.length) continue;
    let index = series.length - 1;
    while (index >= 0 && (series[index].live_edge === true || series[index].evidence?.kind === "live_edge")) index--;
    if (index < 0) continue;
    const reading = series[index];
    const kind = reading.evidence?.kind;
    if (kind !== undefined && kind !== "observed") continue;
    const value = reading.home_probability;
    const readAt = Date.parse(reading.timestamp);
    if (typeof value !== "number" || !Number.isFinite(readAt)) continue;
    // `points` is sorted by `rememberLiveChartFrame`.
    let confirmed: string | null = null;
    for (const point of points) {
      if (point.source !== source || typeof point.source_probability !== "number" ||
          !(Date.parse(point.timestamp) > readAt)) continue;
      if (point.source_probability !== value) break;
      confirmed = point.timestamp;
    }
    if (confirmed === null) continue;
    const held = kind === "observed" ? Date.parse(reading.evidence?.covered_through ?? "") : NaN;
    if (Number.isFinite(held) && held >= Date.parse(confirmed)) continue;
    next ??= { ...served };
    next[source] = series.map((point, i) => i === index
      ? { ...point, evidence: { kind: "observed", covered_through: confirmed as string } }
      : point);
  }
  return next;
}

/**
 * Sportsbook consensus lives in `history`, not `win_prob_history.betting`.
 * Without a served blend, it is MODE B's existing primary line. Extend that
 * line with the betting source's own observations, never the blended `p` or
 * invented individual bookmaker quotes. The frame carries no away/draw,
 * total or projected scores, so those fields stay unknown on its new point.
 */
function extendServedBettingHistory(
  served: OddsHistoryPoint[] | null | undefined, points: LiveChartFrame[],
): OddsHistoryPoint[] | null {
  if (!served?.length) return null;
  const last = served[served.length - 1];
  const edge = Math.max(Date.parse(last.timestamp), Date.parse(last.valid_until ?? last.timestamp));
  if (!Number.isFinite(edge)) return null;
  const added = points.filter(point => point.source === "betting" &&
    typeof point.source_probability === "number" &&
    Number.isFinite(point.source_probability) &&
    point.source_probability >= 0 && point.source_probability <= 1 &&
    Date.parse(point.timestamp) > edge);
  if (added.length === 0) return null;
  return [...served, ...added.map(point => ({
    timestamp: point.timestamp, home_probability: point.source_probability!,
    away_probability: null, over_under: null,
    projected_home_score: null, projected_away_score: null, bookmaker: "aggregate",
  }))];
}

/**
 * Add actual publications received while this page was open. Polls can be
 * coarser than push; retaining the session's observations preserves a real
 * spike and reversal in the input series between polls. The main chart still
 * buckets by minute; on a live page it inks each minute's real low-to-high
 * (`intraMinuteRanges`, #10093), so the excursion stays visible there.
 * Persisted history wins exact-time ties.
 * Never move an old endpoint to a new value or manufacture a timestamp.
 *
 * `history` is the SERVED response, so `aggregate_line` here is the backend's
 * own — the same question `page.tsx` answers for the chart as
 * `backendBlendServed` (#8066). Where the backend blended, the blend line
 * carries the push and the source series keep exactly their served points and
 * values. Where it did not, the source line is the line the reader reads the
 * match off, and it is the one that has to keep up. Either way a source that
 * re-confirmed its last served value extends that reading's coverage
 * (`confirmServedSourceCoverage`, #10671) — evidence only, nothing drawn.
 */
export function mergeLiveChartHistory<T extends ChartHistory>(
  history: T | undefined, points: LiveChartFrame[] = [],
): T | undefined {
  if (!history || points.length === 0) return history;
  const served = history.aggregate_line ?? [];
  const instants = new Set(served.map(point => Date.parse(point.timestamp)));
  const added = points.filter(point => !instants.has(Date.parse(point.timestamp)));
  const confirmed = confirmServedSourceCoverage(history.win_prob_history, points);
  const extended = served.length === 0
    ? extendServedSourceSeries(confirmed ?? history.win_prob_history, points) ?? confirmed
    : confirmed;
  const betting = served.length === 0
    ? extendServedBettingHistory(history.history, points)
    : null;
  if (added.length === 0 && extended === null && betting === null) return history;
  const next = { ...history };
  if (added.length > 0) {
    // Plot points, not frames: the source reading rides in the buffer so the
    // branch above can use it, and must not leak into the blend's own array.
    next.aggregate_line = [...served, ...added.map(
      ({ timestamp, home_probability }) => ({ timestamp, home_probability }),
    )].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }
  if (extended !== null) next.win_prob_history = extended;
  if (betting !== null) next.history = betting;
  return next;
}

/** The subset of the detail payload `appendHeroObservation` reads. */
export type HeroObservation = {
  status?: string | null;
  hero_probability?: number | null;
  hero_probability_source?: string | null;
  hero_probability_observed_at?: string | null;
  win_probability_sources?: Record<string, { updated_at?: string | null } | null | undefined> | null;
};

/** The subset of the SERVED history payload that dates its pinned edge. */
export type ServedEdgeClock = ChartHistory & {
  blend_edge_pinned?: boolean | null;
  blend_edge_observed_at?: string | null;
};

/**
 * When the headline's blend was observed, as the string the point is stamped
 * with. The contract's `hero_probability_observed_at` when the payload carries
 * the key — `null` there means provenance was incomplete, which is unknown, not
 * a cue to guess. A payload from before the contract falls back to the newest
 * source stamp, as #8749 first read it.
 */
function heroObservationStamp(hero: HeroObservation): string | null {
  const declared = hero.hero_probability_observed_at;
  if (declared !== undefined) {
    return typeof declared === "string" && Number.isFinite(Date.parse(declared)) ? declared : null;
  }
  let stamp: string | null = null;
  let clock = -Infinity;
  for (const source of Object.values(hero.win_probability_sources ?? {})) {
    const at = source?.updated_at;
    const t = typeof at === "string" ? Date.parse(at) : NaN;
    if (Number.isFinite(t) && t > clock) { clock = t; stamp = at as string; }
  }
  return stamp;
}

/**
 * #8749 — the blend the HEADLINE shows reaches the chart when it is the newer
 * of the two.
 *
 * The headline reads the detail payload and the frames; the blend line reads
 * the history payload and the frames. Once a frame has arrived the page no
 * longer pins the line's edge to the headline (#920 — a push is an observation
 * at its own time), so a routine detail refresh that carries a newer blend
 * moved the headline and left the line where it was. Production, live/617:
 * TB@PHI read 35% over a line ending 36.3 until the stream delivered the same
 * price 1.24 s later; PIT@DET read 53% over 53.2 for nine seconds.
 *
 * The headline's blend is an observation like any frame, and it carries the
 * same clock a frame does: `applyLiveFrame` writes a frame's `updated_at` into
 * its source, and the detail route serves every source's own write stamp, so
 * the newest stamp is when that blend was last fed. Three rules:
 *
 *   1. STRICTLY NEWER THAN THE LINE. An older headline never overwrites or
 *      follows a newer edge; that direction is `adoptNewerBlendEdge`'s, which
 *      moves the headline instead.
 *   2. NEVER MINT A SERIES. No served blend line, nothing added (#8066).
 *   3. NO INVENTED TIME. The point is stamped with the source's own string.
 *
 * THE SYNTHETIC EDGE (PR #8758). When the newest point is the backend's pinned
 * "now" edge, its timestamp is the minute history was SERVED and its price may
 * be a cached detail hero observed well before that. So it is ordered by
 * `blend_edge_observed_at`, never by its minute: a headline observed strictly
 * after the edge's price replaces that price in place if it falls at or before
 * the serve minute (the line ends on the newer number without a point drawn
 * backwards), or is appended at its own clock if it falls after. An unknown
 * edge clock decides nothing. A `served` payload from before the contract
 * keeps the original rule.
 *
 * Returns the SAME object whenever nothing is added, so memoized consumers see
 * no new value. When the stream later delivers this publication at the same
 * instant, `mergeLiveChartHistory` has already put it on the line and the
 * frame's point simply coincides with it.
 */
export function appendHeroObservation<T extends ChartHistory>(
  history: T | undefined, hero: HeroObservation | null | undefined,
  served?: ServedEdgeClock | null,
): T | undefined {
  if (!history || !hero || !isQuoteStreamStatus(hero.status) ||
      hero.hero_probability_source !== PINNABLE_HERO_SOURCE) return history;
  const p = hero.hero_probability;
  if (typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1) return history;
  const line = history.aggregate_line;
  if (!line || line.length === 0) return history;

  const stamp = heroObservationStamp(hero);
  if (stamp === null) return history;
  const clock = Date.parse(stamp);

  let edge = line[0];
  for (const point of line) {
    if (Date.parse(point.timestamp) > Date.parse(edge.timestamp)) edge = point;
  }
  const edgeTime = Date.parse(edge.timestamp);
  if (!Number.isFinite(edgeTime) || edge.home_probability === p) return history;

  const servedLine = served?.aggregate_line;
  const servedEdge = servedLine?.[servedLine.length - 1];
  const synthetic = served?.blend_edge_pinned === true &&
    served.blend_edge_observed_at !== undefined &&
    servedEdge !== undefined && Date.parse(servedEdge.timestamp) === edgeTime;
  if (synthetic) {
    const observed = Date.parse(served.blend_edge_observed_at ?? "");
    if (!Number.isFinite(observed) || clock <= observed) return history;
    if (clock <= edgeTime) {
      return {
        ...history,
        aggregate_line: line.map(point => point === edge ? { ...point, home_probability: p } : point),
      };
    }
  } else if (clock <= edgeTime) {
    return history;
  }
  return { ...history, aggregate_line: [...line, { timestamp: stamp, home_probability: p }] };
}

/** Raw row prices cannot represent an opening label or a multi-row fold.
 * Preserve historical observations from the same row; an authoritative pair
 * supplies the current folded edge instead of a made-up aggregate. */
export function quoteChartFrames(
  points: LiveChartFrame[] = [],
  hero: (HeroObservation & { blend_fold_revision?: unknown }) | null | undefined,
): LiveChartFrame[] {
  if (!hero || !isQuoteStreamStatus(hero.status) || hero.hero_probability_source !== "blend") return [];
  return points.filter(point => {
    const order = frameFoldOrder(hero.blend_fold_revision, point.rev);
    if (order === "incomparable") return false;
    // A delayed old commit may carry a newer observation clock. It is not
    // permission to draw a value the headline correctly refused at the edge.
    // A newer revision can carry the same price and clock as this frame (the
    // revision bumps on ANY bag change, #10090: held rev 219 stamped with rev
    // 218's clock), so a frame AT the held clock that carries the held value
    // is the very reading the headline shows. An unknown clock admits nothing:
    // without it a delayed old commit cannot be told from an earlier one.
    if (order === "older") {
      const heldAt = Date.parse(hero.hero_probability_observed_at ?? "");
      if (!Number.isFinite(heldAt)) return false;
      const at = Date.parse(point.timestamp);
      return at < heldAt || (at === heldAt && point.home_probability === hero.hero_probability);
    }
    return true;
  });
}

/**
 * #10751 — the frames the page actually DREW while quotes were eligible, and
 * the held vector they were admitted against.
 *
 * Not the hook's bank: `useLiveEventStream` keeps every valid callback, before
 * the fold filter above, and keeps it after transport stops. Retaining that
 * would resurrect frames the headline refused. This is the RESULT of
 * `quoteChartFrames` on the last eligible render, replaced on every one, so a
 * membership change that refuses a frame drops it here too.
 */
export type AdmittedChartFrames = {
  eventId: number;
  points: LiveChartFrame[];
  foldRevision: unknown;
};

export function admitChartFrames(
  eventId: number, points: LiveChartFrame[] = [],
  hero: (HeroObservation & { blend_fold_revision?: unknown }) | null | undefined,
): AdmittedChartFrames {
  return { eventId, points: quoteChartFrames(points, hero), foldRevision: hero?.blend_fold_revision ?? null };
}

/** The subset of the finished detail payload the selector reads. */
export type FinishedHero = {
  id?: number;
  status?: string | null;
  completed_at?: string | null;
  blend_fold_revision?: unknown;
};

/** The subset of the SERVED history payload the selector reads. */
export type FinishedServed = ChartHistory & {
  event_id?: number;
  completed_at?: string | null;
};

/**
 * #10751 — a finished game keeps the movement it already drew while its
 * history read catches up.
 *
 * The detail and history are separate reads. A completed detail ends quote
 * eligibility, and the page used to pass no frames at all, so the chart fell
 * back to the OLD served body and the excursion the reader had just watched
 * vanished until the next history response. The settled hero was right; the
 * journey under it lost its last minutes.
 *
 * This returns only frames from `admitted` — never a frame admitted after the
 * finish, never one the live filter refused — and only when every proof holds.
 * Any doubt returns `[]`, which is exactly the old behaviour:
 *
 *   1. SAME EVENT, EXPLICITLY FINISHED. The admission, the detail and the
 *      served body all name this event, and the detail says completed/closed.
 *   2. A SERVED BLEND. The current body carries the backend's own aggregate
 *      line (#8066); nothing here mints one for a source-only response.
 *   3. COMPARABLE, AND NOT BEHIND. The terminal detail's one-row vector is at
 *      least as new as the vector the frames were admitted against, and at
 *      least as new as each frame's own. Missing, malformed, folded or
 *      changed membership is not comparable evidence.
 *   4. A KNOWN COMPLETION BOUND. The detail's `completed_at`, tightened by the
 *      served body's when it carries a valid one; a frame after it is not
 *      pre-finish movement. An unparseable bound on either side is a
 *      contradiction, not a cue to guess. This is an upper bound only — not
 *      a whistle time — and `OddsChart`'s own game-end and range filters still
 *      decide what is drawn.
 *
 * Each frame keeps its own value, revision and clock; `mergeLiveChartHistory`
 * still lets a later REST point win an exact-time tie. No result endpoint, no
 * interpolation, and no live status — `appendHeroObservation` and
 * `pinChartEdgeToHero` keep standing down for a settled hero.
 */
export function finishedChartFrames(
  admitted: AdmittedChartFrames | null | undefined,
  eventId: number,
  hero: FinishedHero | null | undefined,
  served: FinishedServed | null | undefined,
): LiveChartFrame[] {
  if (!admitted || admitted.eventId !== eventId || admitted.points.length === 0) return [];
  if (!hero || (hero.id !== undefined && hero.id !== eventId) || !isFinishedStatus(hero.status)) return [];
  if (!served || served.event_id !== eventId || !served.aggregate_line?.length) return [];

  const completed = Date.parse(hero.completed_at ?? "");
  if (!Number.isFinite(completed)) return [];
  let bound = completed;
  if (served.completed_at !== undefined && served.completed_at !== null) {
    const servedBound = Date.parse(served.completed_at);
    if (!Number.isFinite(servedBound)) return [];
    bound = Math.min(bound, servedBound);
  }

  const terminal = parseFoldRevision(hero.blend_fold_revision);
  const atAdmission = parseFoldRevision(admitted.foldRevision);
  if (!terminal || !atAdmission) return [];
  const since = compareFoldRevision(terminal, atAdmission);
  if (since !== "same" && since !== "newer") return [];

  return admitted.points.filter(point => {
    // `frameFoldOrder` refuses a folded terminal vector (a raw-row frame never
    // computed a multi-row fold) and an unversioned frame: both incomparable.
    const order = frameFoldOrder(terminal, point.rev);
    if (order !== "same" && order !== "older") return false;
    const at = Date.parse(point.timestamp);
    const p = point.home_probability;
    return Number.isFinite(at) && at <= bound &&
      typeof p === "number" && Number.isFinite(p) && p >= 0 && p <= 1;
  });
}
