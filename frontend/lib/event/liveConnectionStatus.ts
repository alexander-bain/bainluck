/**
 * #10200 — THE CHART'S ONE CONNECTION STATUS, AS A PURE DECISION.
 *
 * A reader holding a live event page used to get a pulsing `live · 8s ago`
 * badge in the header and nothing else. It could not tell them apart:
 *
 *   * a quiet, healthy connection (nothing new has been priced),
 *   * a change that was actually adopted onto the page,
 *   * a transport that broke and is reconnecting — or came back,
 *   * a match that has finished.
 *
 * And the one bit it did carry came from the wrong place. `connected` is the
 * controller's DELIVERING flag: true on `open` before any price has been
 * published, false for a failed socket AND for a healthy one whose market went
 * quiet. So the transport's own observations are read here (`LiveStreamStatus`,
 * reported — never decided — by `liveStreamController`), and the page's
 * ACCEPTED value is read beside them.
 *
 * ═══ RECEIPT IS NOT ADOPTION ═══
 *
 * The page refuses frames: `p = null`, an older revision, a wrong phase, a raw
 * row on a folded hero. Some of those it answers with a refetch whose result is
 * adopted later, some with nothing. Feedback keyed on frame ARRIVAL would say
 * "Updated" over a number that never moved. So every bit of feedback here is
 * keyed on the held result's own price clock advancing — the value the hero is
 * actually printing, after every existing gate, by push or by poll. A heartbeat,
 * a reconnect or a mount never moves that clock, so none of them can earn
 * feedback or reset an age.
 *
 * ═══ WHAT THIS FILE DOES NOT DECIDE ═══
 *
 * Staleness and withdrawal. Those are `heroStampIsStale` / `liveClaimIsUnbacked`
 * and the header age badge's own `stale` branch; the page hands their answers
 * in as `priceMayBeOld` / `scoreMayBeOld`. A second copy of a freshness
 * threshold in here is how a status and a badge come to disagree (#4469).
 *
 * TIME IS A PARAMETER (gotcha #44): every function takes `now`.
 */

import type { LiveStreamStatus } from '@/hooks/useLiveEventStream';

/** How long a receipt ("Updated", "No change", "Updates resumed") is shown. */
export const CONNECTION_FEEDBACK_MS = 3_000;

export type ConnectionFeedbackKind = 'updated' | 'unchanged' | 'resumed';

export interface ConnectionTracker {
  eventId: number | null;
  /** Parsed price clock of the last adopted observation, ms. */
  lastObservedAt: number | null;
  /** What the hero printed for that observation (the displayed percent). */
  lastValueKey: string | null;
  /** A real transport failure was seen and no observation has been adopted since. */
  interrupted: boolean;
  feedback: { kind: ConnectionFeedbackKind; at: number } | null;
  /** This mount saw the page NOT terminal — so a terminal state is a transition it witnessed. */
  sawUnfinished: boolean;
}

export const EMPTY_CONNECTION_TRACKER: ConnectionTracker = {
  eventId: null,
  lastObservedAt: null,
  lastValueKey: null,
  interrupted: false,
  feedback: null,
  sawUnfinished: false,
};

export interface ConnectionObservation {
  eventId: number;
  status: LiveStreamStatus;
  /**
   * The ACCEPTED price clock — the held result's own observation stamp after
   * every gate (`hero_probability_observed_at`, else the freshest source write).
   */
  priceObservedAt: string | null | undefined;
  /** What the hero prints for that value — the displayed percent, as a key. */
  valueKey: string | null;
  /** Finished, venue-settled, or an authority stoppage. */
  terminal: boolean;
}

function parseClock(value: string | null | undefined): number | null {
  if (typeof value !== 'string') return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

/**
 * Advance the tracker by one render's observation.
 *
 * IDEMPOTENT for a repeated input — the same clock is not "newer" twice — so a
 * render that runs twice (StrictMode, a re-render with nothing new) cannot mint
 * a second receipt.
 */
export function stepConnectionTracker(
  prev: ConnectionTracker,
  obs: ConnectionObservation,
  now: number,
): ConnectionTracker {
  const observedAt = parseClock(obs.priceObservedAt);

  // A different event — a client-side navigation — starts from nothing. The
  // first observation of a mount is the BASELINE, never a change.
  if (prev.eventId !== obs.eventId) {
    return {
      eventId: obs.eventId,
      lastObservedAt: observedAt,
      lastValueKey: obs.valueKey,
      interrupted: obs.status === 'retrying',
      feedback: null,
      sawUnfinished: !obs.terminal,
    };
  }

  // Finished overrides everything: no receipt survives into it and no late
  // callback can mint one after it.
  if (obs.terminal) {
    return { ...prev, interrupted: false, feedback: null };
  }

  const next: ConnectionTracker = { ...prev, sawUnfinished: true };
  if (obs.status === 'retrying') next.interrupted = true;

  const newer =
    observedAt !== null && (prev.lastObservedAt === null || observedAt > prev.lastObservedAt);
  if (!newer) {
    // The printed value can still move without a newer clock (a fallback
    // reading changed). Track it so the next real receipt compares against
    // what was on screen — but claim nothing about it.
    next.lastValueKey = obs.valueKey;
    return next;
  }

  next.lastObservedAt = observedAt;
  const changed = obs.valueKey !== prev.lastValueKey;
  next.lastValueKey = obs.valueKey;

  // "Updates resumed" is earned by an observation ADOPTED after an interruption
  // with the transport no longer failing. While it is still retrying, a polled
  // value is recorded but the interruption stands — the socket has not
  // recovered, and saying so would be the lie.
  if (prev.interrupted && obs.status !== 'retrying') {
    next.interrupted = false;
    next.feedback = { kind: 'resumed', at: now };
  } else {
    next.feedback = { kind: changed ? 'updated' : 'unchanged', at: now };
  }
  return next;
}

export type ConnectionTone = 'live' | 'steady' | 'attention' | 'neutral';

export interface ConnectionPresentation {
  /** The button's visible words. Semantic state — never a ticking age. */
  label: string;
  tone: ConnectionTone;
  /** Gentle breathing dot — only a healthy open connection earns motion. */
  breathes: boolean;
  /**
   * What a screen reader is told politely, or '' for nothing. Only the
   * transitions a reader would want interrupting them — interruption,
   * recovery, the finish — never a heartbeat or a receipt.
   */
  announcement: string;
}

export interface ConnectionPresentationInput {
  status: LiveStreamStatus;
  /** Finished / settled / stopped words, or null when the match is not over. */
  terminalLabel: string | null;
  /** The header badge's own stale/withdrawn answer, when the oldest fact is the price. */
  priceMayBeOld: boolean;
  /** The same answer when the oldest visible fact is the score. */
  scoreMayBeOld: boolean;
}

const BASE: Record<LiveStreamStatus, { label: string; tone: ConnectionTone; breathes: boolean }> = {
  connecting: { label: 'Connecting', tone: 'neutral', breathes: false },
  open: { label: 'Connected · waiting', tone: 'live', breathes: true },
  // A rollover is the server asking for a fresh socket on schedule. It is the
  // healthy path, so it reads exactly as the connection it continues.
  rollover: { label: 'Connected · waiting', tone: 'live', breathes: true },
  quiet: { label: 'Connected · checking', tone: 'steady', breathes: false },
  retrying: { label: 'Updates interrupted · reconnecting', tone: 'attention', breathes: false },
  unavailable: { label: 'Checking for updates', tone: 'neutral', breathes: false },
  // The server said the match ended; the page refetches. Until the result
  // lands, the honest word is that it is checking.
  closed: { label: 'Checking for updates', tone: 'neutral', breathes: false },
  idle: { label: 'Checking for updates', tone: 'neutral', breathes: false },
};

/** One render's words for the status, from the tracker and the page's own answers. */
export function presentConnectionStatus(
  tracker: ConnectionTracker,
  input: ConnectionPresentationInput,
  now: number,
): ConnectionPresentation {
  if (input.terminalLabel) {
    return { label: input.terminalLabel, tone: 'neutral', breathes: false, announcement: input.terminalLabel };
  }
  // A healthy socket never hides old evidence: the warnings outrank every
  // connection word, in the neutral styling the header badge's stale branch uses.
  if (input.priceMayBeOld) {
    return { label: 'Price may be old', tone: 'neutral', breathes: false, announcement: '' };
  }
  if (input.scoreMayBeOld) {
    return { label: 'Score may be old', tone: 'neutral', breathes: false, announcement: '' };
  }
  if (input.status === 'retrying') {
    const base = BASE.retrying;
    return { ...base, announcement: base.label };
  }
  const fb = tracker.feedback;
  if (fb && now - fb.at >= 0 && now - fb.at < CONNECTION_FEEDBACK_MS) {
    if (fb.kind === 'resumed') {
      return { label: 'Updates resumed', tone: 'steady', breathes: false, announcement: 'Updates resumed' };
    }
    if (fb.kind === 'updated') {
      return { label: 'Updated', tone: 'steady', breathes: false, announcement: '' };
    }
    // "Connected" is a claim about the socket; only an open one may make it.
    const connected = input.status === 'open' || input.status === 'rollover' || input.status === 'quiet';
    return {
      label: connected ? 'Connected · no change' : 'No change',
      tone: 'steady',
      breathes: false,
      announcement: '',
    };
  }
  return { ...BASE[input.status], announcement: '' };
}

/** A clock for the tap details: wall time with its zone, or null when absent/unparseable. */
export function formatObservationClock(iso: string | null | undefined): string | null {
  const t = parseClock(iso);
  if (t === null) return null;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(t));
}
