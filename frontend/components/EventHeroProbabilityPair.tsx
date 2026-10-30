'use client';

import React, { useEffect, useRef } from 'react';

import {
  NO_READING,
  probabilityParts,
  type ProbabilityParts,
} from '../lib/probabilityDisplay';
import { teamTextColor } from '../lib/teamColors';
import { headlineDisplayAttributes, type HeadlineDisplayIdentity } from '../lib/displayIdentity';
import { tenthsPair, type TenthsParts } from '../lib/tenthsOptIn';

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
 * EXPORTED AND PURE for the same reason `shownPair` below is: it is the real
 * decision, testable for any integer a frame could print. Since #10092 the hero
 * prints only accepted values (no count), so the call site passes `shownHome`,
 * which is `homePct`.
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
   * live/034 S2 — mark a pushed change. Since #10092 the new number is printed
   * at once and only a short crossfade marks it (see `useChangeCue`); it never
   * counts through values no venue priced.
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
  /**
   * #6438 — has the VENUE graded this contest?
   *
   * `started` was the only state the no-reading slot knew, so a match that
   * finished four days ago printed "No price" in the largest type on the page
   * while the pill in the same card read `Settled · Draw 0-0`. That copy is
   * right for #5890's case — a started match whose prices were withdrawn — and
   * is simply the wrong question once the contest is graded: a settled market
   * having no price is its normal end state, not a deficiency to announce.
   *
   * WHY THE SLOT GOES EMPTY RATHER THAN PRINTING THE RESULT. The result is
   * already on this card, in the pill roughly 150px above, from the same two
   * payload keys. Printing it again between the crests states one fact twice in
   * one card. Alex's ruling is the other half: if a number cannot be shown
   * honestly, leave the space empty and do not explain the emptiness. So the
   * reader is left with the crests, the names and the settled pill, which is
   * the whole honest statement — and the container stays in the DOM, because
   * `hero-clip-probe` and `felt-load` anchor on its `data-testid`.
   *
   * Pass the page's OWN settled answer, not a second reading of the payload:
   * one state, one derivation (the lesson `venueSettledSummary` itself exists
   * for). Defaults false, so every existing caller keeps the string it has.
   */
  venueSettled?: boolean;
  /**
   * #8810 — has the match's AUTHORITY reported it stopped before it could be
   * played (ESPN "Postponed")?
   *
   * The hero printed the last pre-kickoff reading — a big 22% on
   * `/events/15315470` — over a pill that now reads "Postponed". A number
   * between the crests is a live call, and nobody is playing this match. So
   * the slot goes empty, exactly as it does for `venueSettled`: the pill
   * carries the state, and the container stays for the probes that anchor on
   * its `data-testid`. The pre-match journey stays in the chart below.
   *
   * Defaults false, so every existing caller renders exactly as before.
   */
  stopped?: boolean;
  /**
   * #10090 — which state this headline adopted (`lib/displayIdentity.ts`),
   * printed as `data-display-*` for samplers. Passive: it never changes what
   * is drawn. A slot with no reading reports `unavailable` whatever is passed.
   */
  displayIdentity?: HeadlineDisplayIdentity | null;
  /**
   * #10090 — print one decimal (`lib/tenthsOptIn.ts`). The event page passes
   * its one decision (on unless the reader opted out) to this hero and the chart's
   * end label together. Ignored on a venue-settled contest, which keeps the
   * whole-number pair. Defaults false, so every caller renders exactly as before.
   */
  tenths?: boolean;
}

/**
 * How long the change cue lasts. Short, and never long enough to overlap the 5s
 * minimum between pushed updates.
 */
const CUE_MS = 320;

/**
 * #10092 — THE NEW NUMBER IS PRINTED AT ONCE; ONLY THE CUE MOVES.
 *
 * This used to be `useCountTo`, a 600ms easeOutCubic count from the old whole
 * percent to the new one (live/034 S2). Every number it printed in between —
 * 22, 31, 37 on the way from 9 to 42 — was a probability no venue ever priced,
 * shown in the biggest type on the page, for 600ms after the accepted frame had
 * already reached the hero input and the chart in under a millisecond (replayed
 * at e5b9fc77e7, #10092). The chart beside it showed the real point while the
 * hero was still counting toward it.
 *
 * Now the digits are the prop, in the same render the frame arrives in, so the
 * only numbers that ever reach the screen are the old accepted value and the
 * new one. The real change is marked by a short opacity crossfade on the digits
 * — no colour, no arrow, nothing that could read as a second source's reading
 * — driven through the Web Animations API on the DOM node, so it causes no
 * extra React render and cannot hold the value back:
 *
 *   * first paint, an unchanged value, or a value appearing/disappearing: no cue
 *     (there is no "change" to mark, and animating a number that never moved
 *     would claim one);
 *   * `prefers-reduced-motion: reduce`: no cue, value already exact;
 *   * a new frame mid-cue: the running cue is CANCELLED and restarted — the
 *     value is already the newest one, so there is nothing to queue.
 *
 * `enabled` is the page's `streamConnected` (the `animate` prop): on the 32s
 * poll a plain swap is the honest rendering, exactly as before.
 */
function useChangeCue(
  target: number | null,
  enabled: boolean,
): React.RefObject<HTMLDivElement> {
  const container = useRef<HTMLDivElement>(null);
  const previous = useRef<number | null>(target);
  const running = useRef<Animation[]>([]);

  useEffect(() => {
    const from = previous.current;
    previous.current = target;
    if (!enabled || from === null || target === null || from === target) return;
    if (
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }
    const root = container.current;
    if (!root) return;
    for (const a of running.current) a.cancel();
    running.current = [];
    root.dataset.changeCue = target > from ? 'up' : 'down';
    root.querySelectorAll<HTMLElement>('[data-hero-digits]').forEach((el) => {
      if (typeof el.animate !== 'function') return;
      running.current.push(
        el.animate([{ opacity: 0.55 }, { opacity: 1 }], {
          duration: CUE_MS,
          easing: 'ease-out',
        }),
      );
    });
  }, [target, enabled]);

  useEffect(
    () => () => {
      for (const a of running.current) a.cancel();
    },
    [],
  );

  return container;
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
  venueSettled = false,
  stopped = false,
  displayIdentity = null,
  tenths: tenthsOn = false,
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

  // #10092 — no count: the printed pair IS the accepted pair, this render.
  // `shownPair` is still the one place the pair is decided (#2085); with no
  // in-between frame it returns the served pair unchanged.
  const cueRef = useChangeCue(homePct, animate);
  const { home: shownHome, away: shownAway } = shownPair(
    homePct, awayPct, homePct, animate,
  );

  // #6064 — the clamp the whole rest of the site applies, finally applied here.
  const homeWhole = sideParts(homeProb, shownHome);
  const awayWhole = sideParts(awayProb, shownAway);
  // #10090 — tenths from the adopted probability, when the page asks for them.
  // Off, every value below is today's: the whole parts, no decimal span, no
  // added style and the numeral class unchanged.
  const tenths =
    tenthsOn && !venueSettled ? tenthsPair(homeProb, awayWithheld ? null : awayProb) : null;
  // A side today's pair prints as no reading stays no reading: tenths add a
  // digit to a number, they never supply one.
  const toParts = (t: TenthsParts | null, fallback: ProbabilityParts) =>
    t && fallback.digits !== NO_READING
      ? { marker: t.marker, digits: t.whole, decimal: t.decimal }
      : { ...fallback, decimal: '' };
  const homeParts = toParts(tenths?.home ?? null, homeWhole);
  const awayParts = toParts(tenths?.away ?? null, awayWhole);
  // Two numeral widths are reserved while a decimal prints, so 9.8 -> 10.2
  // does not shift the pair. A band (`<1`) prints no decimal and reserves
  // nothing, so no gap opens after its marker.
  const reserve = { minWidth: '2ch', textAlign: 'right' as const, display: 'inline-block' };
  const homeDigitsStyle = homeParts.decimal ? reserve : {};
  const awayDigitsStyle = awayParts.decimal ? reserve : {};
  // A two-sided tenths pair at today's 48px is ~242px and runs into the crests
  // and player photos at 390px. The space between the two 56px photo boxes is
  // ~214px at 390, and the boxes can shrink: a 38px pair (214.3px) squeezed
  // them to 51.8px ovals rather than overflowing (PR #11697 review). So the
  // pair is sized to fit that space with room to spare and never moves the
  // photos — 35px numerals and a 24px decimal at 390, 32px / 20px at 375,
  // 28px / 18px at 360 (each side's gap >= 4px, photos loaded or failed;
  // below 360 the pair has its own row, #11301). One named number
  // (#6238) has the room and keeps 48px, and a band pair (`<1` / `>99`)
  // prints no decimal, so it keeps today's markup exactly.
  const fitTenths = !awayWithheld && (homeParts.decimal !== '' || awayParts.decimal !== '');
  const fitDigitsClass =
    'text-[28px] min-[375px]:text-[32px] min-[390px]:text-[35px] sm:text-[44px] font-black tracking-tight leading-none tabular-nums';
  const decimalClass = 'text-[18px] min-[375px]:text-[20px] min-[390px]:text-[24px] font-black tracking-tight leading-none tabular-nums';

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
  // #10108 — 360 to 389 takes one more step, `42px`. At 360 the 48px pair is
  // ~186px wide in a ~184px gap between the crests: production TNF
  // (/events/14780550, 10/1) printed "41" against the Browns crest and "%"
  // against the Steelers crest. 42px frees ~8px a side; 390 and up unchanged.
  const noReading = homeProb === null && awayProb === null;

  if (stopped) {
    return (
      <div
        className="flex items-baseline"
        data-testid="event-hero-probability"
        data-probability=""
        data-probability-source={probSourceLabel ?? ""}
        data-stopped="true"
        {...headlineDisplayAttributes(null)}
      />
    );
  }

  if (noReading) {
    return (
      <div
        className="flex items-baseline"
        data-testid="event-hero-probability"
        data-probability=""
        data-probability-source={probSourceLabel ?? ""}
        {...headlineDisplayAttributes(null)}
      >
        {/* #6438 — a graded contest says nothing here; the settled pill in this
            same card already carries the result. See the `venueSettled` prop. */}
        {!venueSettled && (
          <span className="text-lg font-semibold text-text-muted leading-none">
            {started ? "No price" : "No price yet"}
          </span>
        )}
      </div>
    );
  }

  // #11301 — below 360px the page wraps this pair onto its own full-width
  // row under the two team cells, and each figure must sit under its own
  // team. Four auto margins do it — the pair's first span, its last span and
  // both sides of the dash — so the free width splits a quarter, a half, a
  // quarter. The dash keeps its box but is not drawn: two figures in two cells
  // are not a pair read across a gap. Set from the CONTAINER, so the numeral
  // and `%` spans keep their exact class lists for every reader that finds
  // them by those (#2085's duel invariant, #6064, the capture probes).
  return (
    // UX-P003: the hero's half of "card == hero == chart". The rail reads
    // `data-probability` here and on the Discover card that links to this page,
    // and fails if they disagree. It stays the PROBABILITY, not the printed
    // percent — #2085 changed what is drawn, not what is asserted.
    <div
      ref={cueRef}
      className="flex items-baseline max-[359px]:w-full max-[359px]:[&>:first-child]:ml-auto max-[359px]:[&>:last-child]:mr-auto"
      data-testid="event-hero-probability"
      data-probability={homeProb ?? ""}
      data-probability-source={probSourceLabel ?? ""}
      {...headlineDisplayAttributes(homeProb === null ? null : displayIdentity)}
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
        className={
          fitTenths
            ? fitDigitsClass
            : "text-[34px] min-[360px]:text-[42px] min-[390px]:text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        }
        style={{ color: home, ...homeDigitsStyle }}
        data-hero-digits=""
      >
        {homeParts.digits}
      </span>
      {homeParts.decimal && (
        <span className={decimalClass} style={{ color: home }} data-hero-decimal="">
          {homeParts.decimal}
        </span>
      )}
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
      <span className="text-lg font-light text-text-muted mx-1.5 self-center max-[359px]:mx-auto max-[359px]:invisible">
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
        className={
          fitTenths
            ? fitDigitsClass
            : "text-[34px] min-[360px]:text-[42px] min-[390px]:text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"
        }
        style={{ color: away, ...awayDigitsStyle }}
        data-hero-digits=""
      >
        {awayParts.digits}
      </span>
      )}
      {!awayWithheld && awayParts.decimal && (
        <span className={decimalClass} style={{ color: away }} data-hero-decimal="">
          {awayParts.decimal}
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
