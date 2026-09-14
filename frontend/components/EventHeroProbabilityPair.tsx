'use client';

import { useEffect, useRef, useState } from 'react';

import {
  NO_READING,
  probabilityParts,
  type ProbabilityParts,
} from '../lib/probabilityDisplay';
import { teamTextColor } from '../lib/teamColors';

/**
 * What one side prints this frame — the marker and the digits, separately.
 *
 * #6064: the clamp runs on the PROBABILITY and the digits come from whatever
 * integer THIS FRAME decided, which is what makes it safe mid-tween. At 0.996
 * the count passes through 97, 98, 99 printing those bare, and lands on `>99` —
 * the marker appears exactly when the printed integer would claim a boundary
 * the value is not on, never because the number happens to be large.
 *
 * A side with no reading keeps its em dash: `homeProb` null is "we are
 * withholding this", which is not a probability and has no marker.
 *
 * EXPORTED AND PURE for the same reason `shownPair` below is, and the reason is
 * stated there: the harness renders with `renderToStaticMarkup`, effects never
 * run, and `useCountTo` seeds its state from the target — so no tween frame is
 * EVER observable through the DOM. A test that rendered and asserted would only
 * re-check the settled state. Testing this function across the frames
 * `shownPair` produces tests the real decision; the call site is then the
 * one-line read that it passes `shownHome`, not `homePct`.
 */
export function sideParts(prob: number | null, shown: number | null): ProbabilityParts {
  if (prob === null || shown === null) return { marker: null, digits: NO_READING };
  return probabilityParts(prob, { rendered: shown });
}

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
  /**
   * #6238 — is the away slot DELIBERATELY not printed?
   *
   * Distinct from `awayProb === null`, and the distinction is the whole reason
   * this is a separate prop rather than an inference:
   *
   *   * `awayProb === null` means **we have no reading for this side**. The hero
   *     prints the em-dash, because the dash sits beside a real number and reads
   *     as the comparison it is. Unchanged.
   *   * `awayWithheld` means **we hold a number and it is not a legitimate away
   *     price**. On a draw-priced sport the served away figure is `1 − home`,
   *     i.e. "the home team does not win" — away win OR draw — so there is no
   *     away price to be missing. The SLOT does not apply.
   *
   * ── WHY OMIT RATHER THAN DASH, MEASURED ON PIXELS AND NOT ARGUED ──────────
   *
   * The first cut of #6238 passed `awayProb={null}` and stopped there, which is
   * the dash path above. Twelve green tests and a LOOK at 390px
   * (`artifacts/ux-1266/after-6238-15301234-hero.png`, first cut) showed why
   * that is wrong HERE: at `text-[48px] font-black` an em-dash is a ~41px solid
   * rectangle, so the hero drew **`69% – ▬%`** — a grey redaction bar trailed by
   * a naked `%`. #3459 already wrote that sentence about the both-null case:
   * *"A `%` with nothing in front of it is not a withheld value, it is a broken
   * one."* It is just as true of one side, and on a draw-priced sport it is not
   * an edge case — it is every soccer match, permanently.
   *
   * So the away numerals, their `%` and the separator are omitted entirely and
   * the hero prints ONE named number between the two crests, which is the shape
   * #6238 asked for ("shows one named number and withholds the second slot").
   * The crests and names around this component are untouched, so the reader
   * still sees who the number belongs to.
   *
   * Defaults false, so every existing caller renders exactly as before.
   */
  awayWithheld?: boolean;
  /**
   * #5890 — has this match started?
   *
   * Only the no-reading copy reads it. "No price yet" is a promise about the
   * future, and on a match that kicked off last night it is simply false: the
   * prices existed and were withdrawn. That state used to be rare enough to
   * ignore (a dark match whose chart had no usable point); refusing to
   * un-withdraw a price makes it the normal render for ~280 started events in a
   * 48-hour window, so the tense has to be right.
   *
   * Defaults false, so every existing caller keeps the exact string it has.
   */
  started?: boolean;
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
  awayWithheld = false,
  started = false,
}: EventHeroProbabilityPairProps) {
  // #5696 — THE BIGGEST NUMBER ON THE SITE, PAINTED WHITE ON A WHITE CARD.
  //
  // `/events/15297678` (Everton at Tottenham, live 76', 2026-09-12) rendered
  // `– 37 %`: Tottenham's 63% was in the DOM at full opacity, on screen, and
  // computed `rgb(255, 255, 255)`. Spurs' stored `primary_color` is `#ffffff`
  // and `--surface-card` is `#FFFFFF`. A reader saw one number and could not
  // tell whose it was, while `Opened 64% – 36%` two lines below printed both.
  //
  // #5165 already shipped the floor for exactly this class; it had been adopted
  // in one component. This is the same floor, not a new rule.
  //
  // THE AWAY FALLBACK MOVED, AND THAT IS PART OF THE FIX. It was `#94A3B8`
  // (slate-400), which is 2.56:1 against the card — below the very floor this
  // routes to it, so a white away club would have traded 1.00:1 for 2.56:1 and
  // the guard would have been circular. `--text-secondary` (#6B7280, 4.83:1) is
  // what #5165 chose for the same reason and is still visibly the quieter of
  // the two, so the home/away hierarchy the slate was carrying survives.
  const home = teamTextColor(homeColor) || "#111827";
  const away = teamTextColor(awayColor) || "var(--text-secondary)";

  // The pair is ONE decision (#2085), so only ONE side is counted and the other
  // is derived from it. Tweening the two independently would let them disagree
  // mid-flight and print 101 — the exact defect this component exists to
  // delete, reintroduced one frame at a time.
  const countedHome = useCountTo(homePct, animate);
  const { home: shownHome, away: shownAway } = shownPair(
    homePct, awayPct, countedHome, animate,
  );

  // #6064 — the clamp the whole rest of the site applies, finally applied here.
  const homeParts = sideParts(homeProb, shownHome);
  const awayParts = sideParts(awayProb, shownAway);

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
  // #5866 — the two big numerals carry `text-[34px] min-[360px]:text-[48px]`,
  // so only viewports NARROWER than 360 see the smaller size; 390 and up are
  // untouched. That breakpoint exists because the event hero's centre column
  // became shrinkable in the same ship: it no longer pushes the away crest off
  // the screen, but a block that may shrink and holds a pair that cannot wrap
  // will overlap its neighbours instead. Measured on /events/14780147 at 320px:
  // the centre's budget is 144px and this pair's max-content was 188.5px, and
  // the shot showed "81" printed across the Chargers bolt. Trading an
  // off-screen crest for an overlapping numeral is not a fix.
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
          {started ? "No price" : "No price yet"}
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
      {/* #6064 — THE MARKER RIDES WITH THE `%`, NOT WITH THE NUMERAL.
          `>` at `text-[48px] font-black` is a ~30px glyph, and the centre
          column is shrinkable with a 144px budget at 320px (#5866), so putting
          it in the giant span would buy the clamp by reintroducing the overlap
          that ship measured. At `text-lg` it matches the sign it qualifies and
          reads as part of the value rather than as a stray chevron. The
          numeral spans keep their exact class list, so #5866's guard still
          sees two of them. */}
      {homeParts.marker && (
        <span
          className="text-lg font-bold leading-none mr-0.5"
          style={{ color: home }}
        >
          {homeParts.marker}
        </span>
      )}
      <span
        className="text-[34px] min-[360px]:text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        style={{ color: home }}
      >
        {homeParts.digits}
      </span>
      <span
        className="text-lg font-bold leading-none ml-0.5"
        style={{ color: home }}
      >
        %
      </span>
      {/* #6238 — the separator belongs to the PAIR, so it goes with the slot.
          Leaving a dangling en-dash after a withheld away side would read as a
          number that failed to draw, which is the thing being avoided. */}
      {!awayWithheld && (
      <span className="text-lg font-light text-text-muted mx-1.5 self-center">
        {"–"}
      </span>
      )}
      {!awayWithheld && awayParts.marker && (
        <span
          className="text-lg font-bold leading-none mr-0.5"
          style={{ color: away }}
        >
          {awayParts.marker}
        </span>
      )}
      {!awayWithheld && (
      <span
        className="text-[34px] min-[360px]:text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        style={{ color: away }}
      >
        {awayParts.digits}
      </span>
      )}
      {!awayWithheld && (
      <span
        className="text-lg font-bold leading-none ml-0.5"
        style={{ color: away }}
      >
        %
      </span>
      )}
    </div>
  );
}
