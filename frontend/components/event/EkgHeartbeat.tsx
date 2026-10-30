'use client';

import { useEffect, useState } from 'react';

import type { LiveStreamStatus } from '@/hooks/useLiveEventStream';
import { presentEkg, type EkgMode, type EkgTracker } from '@/lib/event/ekgHeartbeat';

/**
 * #10090 — the event page's heartbeat ("EKG"), drawn under the headline.
 *
 * Whether it beats is decided in `lib/event/ekgHeartbeat` from evidence only
 * (the markets reporting in); this draws the answer. A beat replays the trace
 * once (keyed on the beat count) and leaves it faint; no report for 15 s draws
 * a flat line. Reduce Motion gets a still dot and "Ns ago" instead.
 */

interface EkgHeartbeatProps {
  tracker: EkgTracker;
  status: LiveStreamStatus;
  /** Injected for tests; otherwise the component ticks itself once a second. */
  now?: number;
}

const FLAT_PATH = 'M1 6 H39';
const BEAT_PATH = 'M1 6 H13 L15 4.5 L17 6 L19 1 L21.5 11 L23.5 6 L26 4.8 L28 6 H39';

const TONE: Record<EkgMode, string> = {
  beating: 'text-accent-live',
  flat: 'text-text-muted',
  interrupted: 'text-accent-warning',
};

const DOT_TONE: Record<EkgMode, string> = {
  beating: 'bg-accent-live',
  flat: 'bg-text-muted',
  interrupted: 'bg-accent-warning',
};

export default function EkgHeartbeat({ tracker, status, now }: EkgHeartbeatProps) {
  // The flat line must arrive without a frame, so the component re-reads the
  // clock once a second on its own rather than waiting for the page to render.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (now !== undefined) return;
    const id = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => clearInterval(id);
  }, [now]);

  const p = presentEkg(tracker, status, now ?? Date.now());

  return (
    <span
      role="img"
      aria-label={p.label}
      data-testid="ekg-heartbeat"
      data-ekg-mode={p.mode}
      data-ekg-beats={p.beats}
      className="inline-flex h-3 items-center"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 40 12"
        width="30"
        height="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`motion-reduce:hidden ${TONE[p.mode]}`}
      >
        {p.mode === 'beating' ? (
          <path key={p.beats} d={BEAT_PATH} pathLength={100} className={p.beats > 0 ? 'ekg-beat' : 'opacity-40'} />
        ) : (
          <path d={FLAT_PATH} />
        )}
      </svg>
      <span aria-hidden="true" className="hidden items-center gap-1 text-[10px] leading-3 text-text-muted motion-reduce:inline-flex">
        <span className={`h-1.5 w-1.5 rounded-full ${DOT_TONE[p.mode]}`} />
        {p.secondsSinceSignal !== null ? `${p.secondsSinceSignal}s ago` : null}
      </span>
    </span>
  );
}
