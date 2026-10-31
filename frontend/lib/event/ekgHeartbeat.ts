/**
 * #10090 — THE EVENT PAGE'S "EKG": A HEARTBEAT THAT BEATS ONLY WHEN THE MARKETS REPORT IN.
 *
 * Alex (2026-10-30): when the headline and chart hold still, a reader cannot
 * tell "nobody is trading" from "trades keep arriving at the same price". A
 * tiny heartbeat by the headline answers it: it beats when the markets report
 * in, and it goes flat when they stop.
 *
 * ═══ A BEAT IS EVIDENCE, NEVER A TIMER ═══
 *
 * Exactly two things earn a beat:
 *
 *   * the stream's `confirmed_at` (decision J) ADVANCING — the newest venue
 *     input that agreed with the published price. The value the hook hands the
 *     page is already C1-gated (null while a known commit floor is uncovered);
 *     a null adds nothing and erases nothing;
 *   * the ACCEPTED price clock advancing — the observation stamp of the value
 *     the hero actually prints, after every gate, preview included (the same
 *     clock `stepConnectionTracker` keys "Updated" on).
 *
 * Nothing else: a keep-alive heartbeat carries the same `confirmed_at` (no
 * advance), a re-read that returns the held value carries the same clock, and a
 * reconnect moves neither. While the transport is not open, advances are
 * recorded silently, so catch-up after a reconnect never beats on its own. And
 * an advance to a clock already older than the flat threshold is recorded
 * silently too: newer than what we had, but not a report made now.
 *
 * ═══ FLAT ═══
 *
 * `EKG_FLAT_AFTER_MS` = 15 s. Decision J's confirming heartbeats arrive about
 * every 6 s on a live game while the markets keep agreeing, so 15 s survives
 * two missed confirmations without flat-lining a healthy page; and it is below
 * the stream's 20 s keep-alive (`HEARTBEAT_INTERVAL_S`), so a stream that is
 * only keeping the connection alive reads flat before its next ping — which
 * cannot beat anyway.
 *
 * Interruption, connecting and the finish are the connection status's own
 * states (`LiveStreamStatus`, `liveConnectionStatus.ts`); this file only
 * decides whether the line moves.
 *
 * TIME IS A PARAMETER (gotcha #44): every function takes `now`.
 */

import type { LiveStreamStatus } from '@/hooks/useLiveEventStream';

/** No evidenced report for this long ⇒ the line is flat. See the header. */
export const EKG_FLAT_AFTER_MS = 15_000;
/** Bursts coalesce: at most one drawn beat per this long. */
export const EKG_MIN_BEAT_GAP_MS = 1_500;

export interface EkgTracker {
  eventId: number | null;
  /** Newest parsed `confirmed_at` seen for this event, ms. */
  confirmedAt: number | null;
  /** Newest parsed accepted price clock seen for this event, ms. */
  priceAt: number | null;
  /** When the markets last reported in, ms (a beat or a coalesced one). */
  lastSignalAt: number | null;
  /** When the last beat was DRAWN, ms. */
  beatAt: number | null;
  /** Drawn beats this mount — keys the animation so each beat replays once. */
  beats: number;
}

export const EMPTY_EKG_TRACKER: EkgTracker = {
  eventId: null,
  confirmedAt: null,
  priceAt: null,
  lastSignalAt: null,
  beatAt: null,
  beats: 0,
};

export interface EkgObservation {
  eventId: number;
  status: LiveStreamStatus;
  /** The hook's (C1-gated) `confirmed_at`, or null. */
  confirmedAt: string | null | undefined;
  /** The accepted price clock (`acceptedPriceClock` on the page). */
  priceObservedAt: string | null | undefined;
}

function parseClock(value: string | null | undefined): number | null {
  if (typeof value !== 'string') return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

/** Only an open socket can be hearing the markets; everything else is silent. */
function transportOpen(status: LiveStreamStatus): boolean {
  return status === 'open' || status === 'quiet';
}

function newer(next: number | null, prev: number | null): boolean {
  return next !== null && (prev === null || next > prev);
}

/**
 * Advance the tracker by one render's observation. IDEMPOTENT for a repeated
 * input — the same clock is not newer twice — so a render that runs twice
 * cannot draw a second beat.
 */
export function stepEkgTracker(prev: EkgTracker, obs: EkgObservation, now: number): EkgTracker {
  const confirmed = parseClock(obs.confirmedAt);
  const price = parseClock(obs.priceObservedAt);

  // A new event (a client-side navigation) starts from its baseline: the
  // clocks it mounts with are what it already had, never a report it heard.
  // The line is flat until the first one (the stream sends a heartbeat as
  // soon as its replay is out, so on a healthy page that is about a second).
  if (prev.eventId !== obs.eventId) {
    return { ...EMPTY_EKG_TRACKER, eventId: obs.eventId, confirmedAt: confirmed, priceAt: price };
  }

  const confirmedAdvanced = newer(confirmed, prev.confirmedAt);
  const priceAdvanced = newer(price, prev.priceAt);
  const next: EkgTracker = {
    ...prev,
    confirmedAt: confirmedAdvanced ? confirmed : prev.confirmedAt,
    priceAt: priceAdvanced ? price : prev.priceAt,
  };
  // An advance is a report only if the report is recent. The first heartbeat
  // after a connect "advances" from nothing, and on a market that went quiet
  // minutes ago its `confirmed_at` is minutes old: that is not a beat.
  const advancedTo = Math.max(
    confirmedAdvanced ? (confirmed as number) : -Infinity,
    priceAdvanced ? (price as number) : -Infinity,
  );
  if (!Number.isFinite(advancedTo) || now - advancedTo >= EKG_FLAT_AFTER_MS) return next;
  if (!transportOpen(obs.status)) return next;

  next.lastSignalAt = now;
  if (prev.beatAt === null || now - prev.beatAt >= EKG_MIN_BEAT_GAP_MS) {
    next.beatAt = now;
    next.beats = prev.beats + 1;
  }
  return next;
}

export type EkgMode = 'beating' | 'flat' | 'interrupted';

export interface EkgPresentation {
  mode: EkgMode;
  /** Keys the drawn beat; 0 = none drawn yet this mount. */
  beats: number;
  /** Whole seconds since the markets last reported in, or null for never. */
  secondsSinceSignal: number | null;
  /** For screen readers and the reduced-motion text. */
  label: string;
}

export function presentEkg(tracker: EkgTracker, status: LiveStreamStatus, now: number): EkgPresentation {
  const since = tracker.lastSignalAt === null ? null : Math.max(0, now - tracker.lastSignalAt);
  const secondsSinceSignal = since === null ? null : Math.floor(since / 1000);
  const ago = secondsSinceSignal === null
    ? 'no update yet'
    : `last update ${secondsSinceSignal} second${secondsSinceSignal === 1 ? '' : 's'} ago`;
  if (status === 'retrying') {
    return { mode: 'interrupted', beats: tracker.beats, secondsSinceSignal, label: 'Markets reporting: updates interrupted' };
  }
  const alive = transportOpen(status) && since !== null && since < EKG_FLAT_AFTER_MS;
  return { mode: alive ? 'beating' : 'flat', beats: tracker.beats, secondsSinceSignal, label: `Markets reporting: ${ago}` };
}

/** What `ekgDraws` reads off the page; each field is the page's own value. */
export interface EkgDrawInputs {
  /** The reader's choice (`useEkgOptIn`): ON unless `?ekg=0` was remembered. */
  optIn: boolean;
  /** The page subscribes to the quote stream (`canSubscribeEventQuotes`). */
  quoteEligible: boolean;
  /** The page's `isLive`: status `live` AND the game has started. */
  isLive: boolean;
  /** The connection status's terminal label (finished, settled, stoppage), or null. */
  terminalLabel: string | null;
}

/**
 * Whether the page draws the heartbeat at all (Alex decision 66: ON by default
 * FOR LIVE GAMES). The quote stream also subscribes pre-game and while
 * suspended, so `quoteEligible` alone would draw a heartbeat on every upcoming
 * game's page — one it has not earned. A suspended game gets none either; its
 * stoppage label already hid it.
 */
export function ekgDraws({ optIn, quoteEligible, isLive, terminalLabel }: EkgDrawInputs): boolean {
  return optIn && quoteEligible && isLive && !terminalLabel;
}
