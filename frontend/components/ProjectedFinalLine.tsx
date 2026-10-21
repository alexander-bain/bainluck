/**
 * #2920 / #9483 — THE PROJECTED FINAL, READABLE AND NAMED, ON EVERY SURFACE.
 *
 * Production 2026-10-19, 49ers v Commanders (`/events/14780563`), before play:
 * the event page printed `Projected final: 30 – 22` in 11px muted type under
 * the sportsbook count, two numbers nobody had tied to a team; the league card
 * one tap back printed nothing, and the search card printed `Proj 30-22`.
 *
 * One component for the card rows and the event headline, so the label, the
 * order and the naming cannot drift between them:
 *
 *   - the full label, never "Proj";
 *   - each number beside its own team's name, in the order the surface lists
 *     the teams (the event headline and EventCard put home first; FeedCard
 *     puts away first), so the pair is readable without knowing that order;
 *   - main-value contrast (`text-text-primary`), not provenance styling;
 *   - one sentence for assistive tech that names both teams.
 *
 * It prints what it is handed. WHETHER there is a projection, and which pair,
 * is decided upstream in `lib/projectedFinalPair.ts` — one admission for the
 * cards and the page.
 */

import React from "react";

import { isFinalForecastLabel } from "@/lib/finalForecastComparison";

export interface ProjectedFinalSide {
  name: string;
  score: number;
}

export default function ProjectedFinalLine({
  label,
  first,
  second,
  order,
  variant,
  testId = "projected-final",
}: {
  label: string;
  first: ProjectedFinalSide;
  second: ProjectedFinalSide;
  /** Which team `first` is. Stamped on the DOM so a reader of the markup
   *  never has to guess the orientation either. */
  order: "home-away" | "away-home";
  variant: "card" | "hero";
  testId?: string;
}) {
  const [home, away] = order === "home-away" ? [first, second] : [second, first];
  const spoken = `${label}: ${first.name} ${first.score}, ${second.name} ${second.score}`;
  // A long name may wrap, but its score is glued to its last word by a
  // non-breaking space, so a number can never land on a line under the other
  // team. On a phone the headline stacks one team per line — its centre column
  // sits between two crests and has no room for both names side by side; the
  // comma is for the one-line (sm+) form only.
  const side = (s: ProjectedFinalSide) => (
    <span className="min-w-0 break-words">
      {s.name}
      {"\u00a0"}
      <span className="font-mono">{s.score}</span>
    </span>
  );
  const pair = (
    <span
      className={`flex min-w-0 font-semibold text-text-primary tabular-nums ${
        variant === "hero"
          ? "flex-col items-center sm:flex-row sm:flex-wrap sm:justify-center sm:gap-x-1.5 text-sm"
          : "flex-wrap justify-end gap-x-1.5 text-right text-xs"
      }`}
      aria-hidden="true"
    >
      <span className="min-w-0">
        {side(first)}
        <span className={variant === "hero" ? "hidden sm:inline" : undefined}>,</span>
      </span>
      {side(second)}
    </span>
  );
  return (
    <div
      role="group"
      aria-label={spoken}
      data-testid={testId}
      data-projected-final={`${home.score}-${away.score}`}
      data-projected-order={order}
      className={
        variant === "hero"
          ? "mt-2 flex flex-col items-center gap-0.5 min-w-0 text-center"
          : "mt-2 flex items-baseline justify-between gap-2 min-w-0"
      }
    >
      {/* #11296 — the final band's long label wraps inside its own box, at
          the same size, instead of taking room from what is beside it. The cap
          is a little under the one-line width of the earlier "Before scheduled
          start", so "Projection before scheduled start" breaks as "Projection
          before / scheduled start" and neither the card's numbers nor the
          headline's team columns lose room they had (the headline centre is
          sized by its content, so a one-line long label would widen it into
          the team columns). Only the final labels are capped (soccer's
          "Projection (90 min) before scheduled start" wraps the same way): the
          pre-game labels lay out as before, and soccer's "Projected final
          (90 min)" (~136px) is wider than the cap, so capping it would break a
          line that fits. */}
      <span
        className={`text-xs font-medium text-text-secondary flex-shrink-0${
          isFinalForecastLabel(label) ? " max-w-[8rem]" : ""
        }`}
        aria-hidden="true"
      >
        {label}
      </span>
      {pair}
    </div>
  );
}
