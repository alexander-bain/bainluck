'use client';

import { useEffect, useState } from 'react';

/**
 * live/034 S2 — "live · Ns ago".
 *
 * Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES 2): a live look is an animated
 * number, a "live · Ns ago" pulse, and a last-10-min sparkline.
 *
 * This replaces the "Next update: 32" countdown on a pushed event, because on a
 * pushed event there is no next update to count down to — updates arrive. The
 * honest thing to show instead is how old the number actually is.
 *
 * THE RULE: the age counts from the STAMPED write time, never from when the
 * packet arrived or when this component mounted. Those would reset on every
 * heartbeat and reconnect, so a stream that was alive but delivering nothing
 * would read "1s ago" forever while showing a number minutes old. The age going
 * UP is the signal that something upstream has gone quiet, and it must be
 * allowed to say so.
 */

interface LiveAgeStampProps {
  /** ISO timestamp of the freshest source write. */
  updatedAt: string | null | undefined;
  /** Whether the SSE stream is currently delivering. */
  connected: boolean;
}

/** Past this the number is not "live" in any useful sense; say so plainly. */
const STALE_AFTER_S = 120;

function ageSeconds(updatedAt: string | null | undefined): number | null {
  if (!updatedAt) return null;
  const parsed = Date.parse(updatedAt);
  if (Number.isNaN(parsed)) return null;
  // Clamp at zero: clock skew between the dyno and the browser can put a
  // stamp slightly in the future, and "-3s ago" reads as a bug.
  return Math.max(0, Math.round((Date.now() - parsed) / 1000));
}

export default function LiveAgeStamp({ updatedAt, connected }: LiveAgeStampProps) {
  const [age, setAge] = useState<number | null>(() => ageSeconds(updatedAt));

  useEffect(() => {
    setAge(ageSeconds(updatedAt));
    const tick = setInterval(() => setAge(ageSeconds(updatedAt)), 1000);
    return () => clearInterval(tick);
  }, [updatedAt]);

  if (age === null) return null;

  const stale = age > STALE_AFTER_S;
  const label = age < 60 ? `${age}s ago` : `${Math.floor(age / 60)}m ago`;

  return (
    <span
      className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-semibold ${
        stale
          ? 'bg-surface-muted text-text-secondary'
          : 'bg-emerald-500/15 text-emerald-600'
      }`}
      // The number is the visible thing; the state is what a screen reader needs.
      aria-label={
        stale
          ? `Last update ${label}. Waiting for a fresh price.`
          : `Live. Updated ${label}.`
      }
    >
      <span
        className={`w-2 h-2 rounded-full ${
          stale
            ? 'bg-text-muted'
            : // The pulse animates ONLY while the stream is delivering. A
              // pulsing dot on a dead stream is a lie told once a second.
              `bg-emerald-500 ${connected ? 'animate-pulse' : ''}`
        }`}
      />
      <span className="tabular-nums">
        {stale ? label : `live · ${label}`}
      </span>
    </span>
  );
}
