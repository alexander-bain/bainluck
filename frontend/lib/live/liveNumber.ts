/**
 * THE LIVE LOOK — the decisions, with no React and no clock of their own.
 *
 * Alex, 2026-09-01, LIVE UPDATES ruling (2):
 *
 *   > live look = animated number (<=1 change/~5s) + "live · Ns ago" pulse +
 *   > last-10-min sparkline; illiquidity ring stays.
 *
 * Everything here is a pure function of (state, now). No `Date.now()`, no
 * timers, no effects — the hook supplies the clock. That is not tidiness: a
 * throttle and an age label are both *entirely* about time, so a version that
 * reads the clock internally can only be tested by sleeping, and a test that
 * sleeps is a test nobody runs at the boundaries (gotcha #44 — an anchor that
 * branches on the clock is not an anchor).
 *
 * ═══ 🔴 "ANIMATED" AND "NEVER SMOOTH" ARE NOT IN TENSION, AND THE RESOLUTION
 *     IS THE WHOLE DESIGN ═══
 *
 * The standing chart rulings (`components/Sparkline.tsx`, chart_census.md) say:
 * draw raw segments between real observations, never interpolate a curve the
 * data did not take. The obvious "animated number" — tweening 61 → 67 through
 * 62, 63, 64 — breaks exactly that rule, one digit at a time. For ~400ms the
 * hero would print 63%, and 63% is a probability no market ever quoted. On a
 * page whose entire argument is "this number is what the market thinks", that
 * is a small lie told sixty times an hour.
 *
 * So the NUMBER STEPS and the CHANGE is what animates: the digits go straight
 * from 61 to 67, and a brief tint marks that they moved and which way. Every
 * frame shows a number somebody actually quoted.
 *
 * ⚠️ `AnimatedProbability` in `components/discover/shared.tsx` DOES tween, and
 * is deliberately left alone: it counts up from zero ONCE on first intersection
 * — an entrance, not an update — and it never runs again while a value changes.
 * The two do different jobs and the distinction is exactly "is a reader
 * watching this number change".
 */

/** How long a displayed value is held before another change may be painted. */
export const LIVE_CHANGE_MIN_INTERVAL_MS = 5_000;

/** The sparkline window: the last ten minutes, and nothing older. */
export const LIVE_SPARKLINE_WINDOW_MS = 10 * 60 * 1000;

/**
 * Past this, the pulse stops claiming to be live.
 *
 * Aligned with LIVE UPDATES ruling (3) — "a source older than ~2 min drops OUT
 * of the live number". That ruling governs the BLEND (a backend job); this is
 * the same threshold applied to the blend's own timestamp, so a reader is never
 * shown a green dot over a number the blend rule would itself have dropped.
 */
export const LIVE_AGE_LIMIT_MS = 2 * 60 * 1000;

/** One observation of the blended number. */
export interface LivePoint {
  /** Probability in POINTS, 0-100 — the unit every surface renders. */
  value: number;
  /** When the blend observed it, epoch ms. NOT when we received the frame. */
  observedAt: number;
}

/** What the display is currently committed to showing. */
export interface LiveDisplayState {
  /** The point on screen, or null before the first one arrives. */
  shown: LivePoint | null;
  /** When `shown` was painted, epoch ms — the throttle's clock. */
  shownAt: number;
  /** A newer point received but not yet painted, held by the throttle. */
  pending: LivePoint | null;
  /** Sign of the last painted change, for the tint. 0 on the first paint. */
  lastDirection: -1 | 0 | 1;
}

export const INITIAL_LIVE_DISPLAY: LiveDisplayState = {
  shown: null,
  shownAt: 0,
  pending: null,
  lastDirection: 0,
};

/**
 * Fold one arriving point into the display state.
 *
 * ═══ WHY THE HELD POINT IS REPLACED RATHER THAN QUEUED ═══
 *
 * Twenty frames in five seconds must produce ONE repaint, and it must be the
 * LATEST value, not the first of the burst. A queue would paint the oldest held
 * point on the next tick and then be behind by a whole interval; replacing
 * means the throttle costs latency (up to 5s) but never costs currency.
 *
 * ⚠️ AND THAT LATENCY IS WHY `shown` CARRIES ITS OWN `observedAt`. The age
 * label must describe the number ON SCREEN, not the newest one received. A
 * pulse reading "2s ago" above a value the throttle is holding back by four
 * seconds is the honesty bug this whole feature is supposed to avoid — it would
 * be a fresher claim than the pixel it sits next to.
 */
export function receiveLivePoint(
  state: LiveDisplayState,
  point: LivePoint,
  now: number
): LiveDisplayState {
  // An out-of-order or replayed frame is dropped. SSE reconnects replay, and a
  // replayed older observation must not walk the hero backwards.
  if (state.shown && point.observedAt <= state.shown.observedAt) return state;
  if (state.pending && point.observedAt <= state.pending.observedAt) return state;

  // First paint is immediate: there is nothing on screen to protect from
  // flicker, and holding it back would just be a slower first render.
  if (!state.shown) {
    return { shown: point, shownAt: now, pending: null, lastDirection: 0 };
  }

  if (now - state.shownAt >= LIVE_CHANGE_MIN_INTERVAL_MS) {
    return commit(state, point, now);
  }
  return { ...state, pending: point };
}

/**
 * Paint a held point once its interval has elapsed. Called on the display tick.
 *
 * Separate from `receiveLivePoint` because a burst that stops leaves a pending
 * point with no further frame to carry it in — "the last update of a burst is
 * silently never shown" is the classic throttle bug and it is invisible in
 * testing, because tests send steady traffic.
 */
export function tickLiveDisplay(state: LiveDisplayState, now: number): LiveDisplayState {
  if (!state.pending) return state;
  if (now - state.shownAt < LIVE_CHANGE_MIN_INTERVAL_MS) return state;
  return commit(state, state.pending, now);
}

function commit(state: LiveDisplayState, point: LivePoint, now: number): LiveDisplayState {
  const previous = state.shown?.value ?? point.value;
  // Direction is judged on the RENDERED integer, not the raw float. 61.4 → 61.6
  // is a change in the payload and not a change on screen, and tinting digits
  // that did not move is the animation crying wolf.
  const moved = Math.round(point.value) - Math.round(previous);
  return {
    shown: point,
    shownAt: now,
    pending: null,
    lastDirection: moved > 0 ? 1 : moved < 0 ? -1 : 0,
  };
}

/**
 * How the pulse should read, given the age of the number ON SCREEN.
 *
 * Three states, and the third is the one that matters: past `LIVE_AGE_LIMIT_MS`
 * the dot stops being green and the label stops saying "live". A live-looking
 * chip over a two-minute-old number is precisely the failure the Flow Sentinel
 * hunts, and the fix is that the honest label is the ONLY label available here.
 *
 * ⚠️ The word "stale" is our `price_state` enum and is banned in reader copy
 * (`lib/copyBans.ts`, JARGON_BANS). The degraded label says what it means.
 */
export type LivePulseTone = "live" | "waiting" | "paused";

export interface LivePulse {
  tone: LivePulseTone;
  /** The whole chip text, e.g. "live · 12s ago". */
  label: string;
  /** Age in ms, for a title attribute and for tests. */
  ageMs: number;
}

/** "12s ago" / "4m ago" / "2h ago" — whole units, never a decimal. */
export function formatLiveAge(ageMs: number): string {
  const s = Math.max(0, Math.floor(ageMs / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

export function livePulse(observedAt: number | null, now: number): LivePulse | null {
  if (observedAt == null || !Number.isFinite(observedAt)) return null;
  // A timestamp in the future is a clock disagreement between the reader's
  // machine and ours, not a fresher number. Clamp to zero rather than printing
  // "-3s ago", and never let it read as MORE live than the present.
  const ageMs = Math.max(0, now - observedAt);
  if (ageMs > LIVE_AGE_LIMIT_MS) {
    return { tone: "paused", label: `updates paused · ${formatLiveAge(ageMs)}`, ageMs };
  }
  // Under two seconds the number is effectively now, and "live · 0s ago" reads
  // like a broken clock.
  if (ageMs < 2000) return { tone: "live", label: "live", ageMs };
  return { tone: "live", label: `live · ${formatLiveAge(ageMs)}`, ageMs };
}

/**
 * The last ten minutes of the series, oldest first.
 *
 * ⚠️ RETURNS THE POINTS, NOT A VALUE ARRAY, and the caller decides whether
 * there are enough to draw. A window with one observation in it is a dot, not a
 * trend, and `Sparkline` handed one point draws a zero-length path — an empty
 * SVG box that reads as "we have no data" when the truth is "nothing has
 * changed for nine minutes". Those need different treatments, so the decision
 * is `hasLiveSparkline` below rather than a silent empty render.
 */
export function liveWindow(
  points: readonly LivePoint[],
  now: number,
  windowMs: number = LIVE_SPARKLINE_WINDOW_MS
): LivePoint[] {
  const floor = now - windowMs;
  return points
    .filter((p) => Number.isFinite(p.value) && p.observedAt > floor && p.observedAt <= now)
    .sort((a, b) => a.observedAt - b.observedAt);
}

/** Fewer than this in the window and the sparkline is not drawn. */
export const LIVE_SPARKLINE_MIN_POINTS = 3;

export function hasLiveSparkline(windowed: readonly LivePoint[]): boolean {
  if (windowed.length < LIVE_SPARKLINE_MIN_POINTS) return false;
  // A perfectly flat window draws a horizontal rule, which is TRUE and worth
  // drawing: "this has not moved in ten minutes" is information on a live card.
  // Only absence of observations suppresses it.
  return true;
}

/**
 * Append an observation to a bounded ring, newest last.
 *
 * The cap is a memory bound, not a display bound — `liveWindow` decides what is
 * shown. Sized so a 2s cadence fills ten minutes twice over, because a burst
 * must not evict the window it is supposed to draw.
 */
export const LIVE_SERIES_CAP = 600;

export function appendLivePoint(
  series: readonly LivePoint[],
  point: LivePoint
): LivePoint[] {
  const last = series[series.length - 1];
  if (last && point.observedAt <= last.observedAt) return series as LivePoint[];
  const next = [...series, point];
  return next.length > LIVE_SERIES_CAP ? next.slice(next.length - LIVE_SERIES_CAP) : next;
}
