'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * The event page hero's two giant percents — #2085.
 *
 * WHY THIS IS A COMPONENT AND NOT STILL FOUR SPANS INLINE IN `page.tsx`.
 * The defect it fixes is a RENDERING one: two probabilities that are an exact
 * complement by construction, rounded independently, printing 101. A guard that
 * only drives `resolveProbability` stays green if the page keeps calling
 * `Math.round(homeProb * 100)` in the JSX and ignores the percents the resolver
 * decided — the pure-library half passes while the screen is still wrong. The
 * pair is extracted so the thing under test is the thing on screen.
 *
 * It renders NOTHING but the pair. Everything around it — the settled winner
 * treatment, the trend indicator, the source label, the opening line — stays in
 * the page, because none of it is part of this decision.
 */

interface EventHeroProbabilityPairProps {
  /** The probabilities themselves. Unchanged by #2085; still what the rail reads. */
  homeProb: number | null;
  awayProb: number | null;
  /**
   * The whole percents to PRINT, decided together by `resolveProbability`
   * (served by the backend when the pair is `current_odds`, otherwise derived
   * locally through the shared `renderedDuelPercents`).
   *
   * Nullable and separately guarded rather than defaulted: a caller that
   * forgets them must print an em-dash, not silently fall back to the
   * independent rounding this component exists to delete.
   */
  homePct: number | null;
  awayPct: number | null;
  homeColor?: string | null;
  awayColor?: string | null;
  probSourceLabel?: string | null;
  /**
   * live/034 S2 — count the number to its new value instead of swapping it.
   *
   * Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES 2): a live look is an
   * animated number. Off by default, so every non-pushed caller renders exactly
   * as before and the #2085 guard keeps testing the same thing.
   */
  animate?: boolean;
}

/** How long the count takes. Comfortably under the 5s minimum between updates. */
const TWEEN_MS = 600;

/**
 * Count `target` from wherever it was, in whole percents.
 *
 * NOT smoothing (the ruling forbids it): this interpolates only between two
 * values the server actually sent, and always lands exactly on the newer one.
 * It never invents a reading, and it never lags behind the latest value — a new
 * target mid-flight retargets from where the count currently is rather than
 * queueing, so the number cannot fall behind a fast-moving market.
 */
function useCountTo(target: number | null, enabled: boolean): number | null {
  const [shown, setShown] = useState<number | null>(target);
  const frame = useRef<number | null>(null);
  // What is currently on screen, readable without re-subscribing the effect.
  const shownRef = useRef<number | null>(target);
  shownRef.current = shown;

  useEffect(() => {
    if (target === null) {
      setShown(null);
      return;
    }
    // First paint, or animation off: land immediately. Counting up from nothing
    // on load would animate a number that never moved.
    if (!enabled || shownRef.current === null) {
      setShown(target);
      return;
    }
    const from = shownRef.current;
    if (from === target) return;

    // Respect the OS setting. An animated number is a nicety; motion sickness
    // is not.
    if (
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) {
      setShown(target);
      return;
    }

    const started = performance.now();
    const step = (nowMs: number) => {
      const t = Math.min(1, (nowMs - started) / TWEEN_MS);
      // easeOutCubic — fast off the mark, settles gently.
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(from + (target - from) * eased));
      if (t < 1) frame.current = requestAnimationFrame(step);
      else setShown(target); // land EXACTLY on the served value, never near it
    };
    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      frame.current = null;
    };
  }, [target, enabled]);

  return shown;
}

/**
 * Which pair of whole percents to PRINT this frame.
 *
 * Exported and pure on purpose. The invariant that matters — the two sides are
 * complements, never independently rounded to 101 — has to hold on every
 * intermediate frame of the count, and the test harness renders with
 * `renderToStaticMarkup`, where effects never run and no tween is ever
 * observable. Testing this function exhaustively tests the real decision;
 * asserting it through the DOM would only ever re-test the settled state.
 */
export function shownPair(
  homePct: number | null,
  awayPct: number | null,
  countedHome: number | null,
  animate: boolean,
): { home: number | null; away: number | null } {
  const midFlight =
    animate && countedHome !== null && homePct !== null && countedHome !== homePct;
  if (!midFlight) return { home: homePct, away: awayPct };
  // Derived from the counted side, never counted separately.
  return { home: countedHome, away: 100 - (countedHome as number) };
}

export default function EventHeroProbabilityPair({
  homeProb,
  awayProb,
  homePct,
  awayPct,
  homeColor,
  awayColor,
  probSourceLabel,
  animate = false,
}: EventHeroProbabilityPairProps) {
  const home = homeColor || "#111827";
  const away = awayColor || "#94A3B8";

  // The pair is ONE decision (#2085), so only ONE side is counted and the other
  // is derived from it. Tweening the two independently would let them disagree
  // mid-flight and print 101 — the exact defect this component exists to
  // delete, reintroduced one frame at a time.
  const countedHome = useCountTo(homePct, animate);
  const { home: shownHome, away: shownAway } = shownPair(
    homePct, awayPct, countedHome, animate,
  );

  // #3459 — NEITHER side has a number. Drawing the chrome anyway produced
  // `—%–—%`: at `text-[48px] font-black` an em-dash is a 41px solid rectangle,
  // so the hero photographed as two redaction bars each trailed by a naked `%`,
  // and a reader could not tell "we are withholding this" from "the number
  // failed to draw". A `%` with nothing in front of it is not a withheld value,
  // it is a broken one. Say it in words instead.
  //
  // Only the both-null case changes. One side known and the other not still
  // prints the pair with an em-dash, because there the dash sits BESIDE a real
  // number and reads as the comparison it is.
  const noReading = homeProb === null && awayProb === null;

  if (noReading) {
    return (
      <div
        className="flex items-baseline"
        data-testid="event-hero-probability"
        data-probability=""
        data-probability-source={probSourceLabel ?? ""}
      >
        <span className="text-lg font-semibold text-text-muted leading-none">
          No price yet
        </span>
      </div>
    );
  }

  return (
    // UX-P003: the hero's half of "card == hero == chart". The rail reads
    // `data-probability` here and on the Discover card that links to this page,
    // and fails if they disagree. It stays the PROBABILITY, not the printed
    // percent — #2085 changed what is drawn, not what is asserted.
    <div
      className="flex items-baseline"
      data-testid="event-hero-probability"
      data-probability={homeProb ?? ""}
      data-probability-source={probSourceLabel ?? ""}
    >
      <span
        className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        style={{ color: home }}
      >
        {homeProb !== null && shownHome !== null ? shownHome : "—"}
      </span>
      <span
        className="text-lg font-bold leading-none ml-0.5"
        style={{ color: home }}
      >
        %
      </span>
      <span className="text-lg font-light text-text-muted mx-1.5 self-center">
        {"–"}
      </span>
      <span
        className="text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        style={{ color: away }}
      >
        {awayProb !== null && shownAway !== null ? shownAway : "—"}
      </span>
      <span
        className="text-lg font-bold leading-none ml-0.5"
        style={{ color: away }}
      >
        %
      </span>
    </div>
  );
}
