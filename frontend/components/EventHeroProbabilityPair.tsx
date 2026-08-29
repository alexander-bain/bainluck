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
}

export default function EventHeroProbabilityPair({
  homeProb,
  awayProb,
  homePct,
  awayPct,
  homeColor,
  awayColor,
  probSourceLabel,
}: EventHeroProbabilityPairProps) {
  const home = homeColor || "#111827";
  const away = awayColor || "#94A3B8";

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
        {homeProb !== null && homePct !== null ? homePct : "—"}
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
        {awayProb !== null && awayPct !== null ? awayPct : "—"}
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
