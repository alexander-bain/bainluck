'use client';

import { useEffect, useState } from 'react';

import { STALE_MS } from '@/components/event/FreshnessChip';

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
  /**
   * ISO timestamp of the OLDEST fact the hero is showing (#4469) — see
   * `lib/event/heroFreshness`. It used to be the freshest price write, which is
   * how this badge came to print a green `live · 6s ago` over a score eight
   * minutes old.
   */
  updatedAt: string | null | undefined;
  /**
   * Which fact `updatedAt` belongs to, so the admission has a subject.
   *
   * Tooltip and screen reader ONLY. Standing notice 34 keeps method notes out of
   * the page body, and CERT-411 round 2 is why an age without a subject is not
   * good enough: a mark that says "8m" while the reader is looking at a
   * probability that ticked a second ago has to say WHICH thing is 8m old, or it
   * has traded one wrong impression for another.
   */
  oldestFact?: "price" | "score" | null;
  /** Whether the SSE stream is currently delivering. */
  connected: boolean;
}

/** Past this the number is not "live" in any useful sense; say so plainly. */
const STALE_AFTER_S = 120;

/**
 * THE BOUNDARY BELONGS TO THE FACT, NOT TO THE BADGE (#4469).
 *
 * `STALE_AFTER_S` is 120 because the PRICE is written every two minutes; a price
 * older than that means the feed missed a beat. The score is written on a
 * ten-minute beat, so 120s would call an ordinary, perfectly healthy score
 * "stale" almost all of the time — and once lane1 tightens that cadence the
 * score would sit right on the boundary and flicker between states.
 *
 * So the score gets the threshold that was already calibrated for it, rather
 * than a third number invented here: `FreshnessChip.STALE_MS`, five minutes,
 * whose own docblock argues it against this exact beat ("a stamp older than five
 * minutes means we are at least halfway to the next read"). That chip sits two
 * centimetres away on the same hero, on the same fact, and two thresholds for
 * one fact is how a dot and its caption end up disagreeing.
 */
const STALE_AFTER_S_BY_FACT = { price: STALE_AFTER_S, score: STALE_MS / 1000 };

function ageSeconds(updatedAt: string | null | undefined): number | null {
  if (!updatedAt) return null;
  const parsed = Date.parse(updatedAt);
  if (Number.isNaN(parsed)) return null;
  // Clamp at zero: clock skew between the dyno and the browser can put a
  // stamp slightly in the future, and "-3s ago" reads as a bug.
  return Math.max(0, Math.round((Date.now() - parsed) / 1000));
}

export default function LiveAgeStamp({
  updatedAt,
  oldestFact = null,
  connected,
}: LiveAgeStampProps) {
  const [age, setAge] = useState<number | null>(() => ageSeconds(updatedAt));

  useEffect(() => {
    setAge(ageSeconds(updatedAt));
    const tick = setInterval(() => setAge(ageSeconds(updatedAt)), 1000);
    return () => clearInterval(tick);
  }, [updatedAt]);

  if (age === null) return null;

  const stale = age > STALE_AFTER_S_BY_FACT[oldestFact ?? "price"];
  const label = age < 60 ? `${age}s ago` : `${Math.floor(age / 60)}m ago`;

  return (
    <span
      className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-semibold ${
        stale
          ? 'bg-surface-muted text-text-secondary'
          : 'bg-emerald-500/15 text-emerald-600'
      }`}
      // The number is the visible thing; the state is what a screen reader needs.
      //
      // "Waiting for a fresh price" was the only stale sentence this had, and on
      // a live tennis hero it is false in the most misleading direction: the
      // price is seconds old and the SCORE is what is behind (#4469). Keyed on
      // `oldestFact` so the sentence describes the fact the age actually came
      // from; with no fact named it says exactly what it always said.
      aria-label={
        stale
          ? oldestFact === "score"
            ? `Score last confirmed ${label}. The probability is newer.`
            : `Last update ${label}. Waiting for a fresh price.`
          : oldestFact === "score"
            ? `Live. Score confirmed ${label}.`
            : `Live. Updated ${label}.`
      }
      title={
        oldestFact === "score"
          ? `Score last confirmed ${label}. The probability is newer.`
          : undefined
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
