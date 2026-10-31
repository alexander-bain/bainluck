"use client";

/**
 * #10868 — THE HOCKEY JOURNEY SCREEN (web, route `nhl-journey`).
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a hockey fan sees, in one
 * probability-first section, each team's chances before, during and after the
 * game beside the goals and the (honestly absent) forecasts, a two-team history
 * that leaves unrecorded time blank, the points and assists stories, and every
 * original prop — the same answers the iPhone screen prints.
 *
 * Presentation only. It receives `HockeyJourneyViewModel` (built by
 * `buildHockeyJourney` from data the event page already holds) and adds no
 * fetch, subscription, SWR key, timer or animation. Its only state is the
 * reader's own: the About disclosure, the story shown, the player and
 * milestone chosen, and which Details are open.
 *
 * Accessibility: real buttons with `aria-expanded`/`aria-controls`, headings
 * in document order (matrix → history → stories → All props), labelled values,
 * no motion to reduce, and layouts that wrap at 375 px and at 200% text.
 *
 * About is the approved design's compact info control beside the header
 * (`HockeyJourneyPage.tsx`'s `InfoCircledIcon` button, prototype): an icon with
 * the About words as its accessible name and a 44 px target, so it never takes
 * a header row of its own on a phone. Its content is unchanged.
 */

import { useId, useState } from "react";
import { Info } from "lucide-react";
import type { HockeyJourneyViewModel } from "@/lib/eventPage10868/hockeyJourney";
import { teamColorStyle } from "@/lib/teamColors";
import HockeyJourneyMatrix from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart from "./HockeyJourneyHistoryChart";
import HockeyJourneyStories from "./HockeyJourneyStories";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";

export default function HockeyJourneyPage({ journey }: { journey: HockeyJourneyViewModel }) {
  const headingId = useId();
  const aboutId = useId();
  const [aboutOpen, setAboutOpen] = useState(false);
  const { headline } = journey;

  // A team colour paints its own line only when it clears the card-surface
  // contrast floor (`teamTextColor`, carried as `tint`); otherwise the series
  // tokens stand in, so a pale kit colour never draws an invisible line.
  const style = teamColorStyle(headline.home.tint, headline.away.tint);
  const lineColors = {
    home: headline.home.tint ? "rgb(var(--team-home-primary))" : "var(--series-1)",
    away: headline.away.tint ? "rgb(var(--team-away-primary))" : "var(--series-2)",
  };

  return (
    <section
      aria-labelledby={headingId}
      data-hockey-journey={journey.phase}
      className="space-y-6 rounded-xl border border-surface-border bg-surface-card p-4 text-text-primary sm:p-5"
      style={style}
    >
      <header className="space-y-2">
        {/* The info control shares a row with the state lines only: the title takes the card's full width
            below it, so at large text the target's column never narrows the event's name. */}
        <div data-hockey-journey-header-row="" className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-0.5">
            <p className="text-sm font-semibold">{headline.state}</p>
            {headline.stateContext && <p className="text-sm text-text-secondary">{headline.stateContext}</p>}
          </div>
          <button
            type="button"
            aria-expanded={aboutOpen}
            aria-controls={aboutId}
            onClick={() => setAboutOpen((open) => !open)}
            className={`-mr-2 -mt-1 inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-text-primary hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
              aboutOpen ? "bg-surface-elevated" : ""
            }`}
          >
            {/* rem-sized, so the icon grows with the reader's text like the target does. */}
            <Info aria-hidden="true" className="h-5 w-5" />
            <span className="sr-only">{journey.header.aboutLabel}</span>
          </button>
        </div>
        <h2 id={headingId} className="break-words text-lg font-bold">
          {journey.header.title}
        </h2>
        <div id={aboutId} hidden={!aboutOpen} className="rounded-lg bg-surface-deep p-3">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {journey.about.map((line, i) => (
              <li key={`${i}:${line}`} className="break-words">
                {line}
              </li>
            ))}
          </ul>
        </div>
      </header>

      {/* Column sources and clocks live in About once the view model has verified About holds every one;
          the game state, its context and the result words stay here. */}
      <HockeyJourneyMatrix headline={headline} inlineProvenance={!journey.provenanceInAbout} />

      {headline.historicalForecast && (
        <p className="text-sm">
          <span className="font-medium text-text-secondary">{headline.historicalForecast.title}: </span>
          <span className="font-semibold">{headline.historicalForecast.reading}</span>
        </p>
      )}

      <HockeyJourneyHistoryChart history={journey.history} colors={lineColors} />

      <HockeyJourneyStories journey={journey} />

      <HockeyJourneyAllProps originals={journey.originals} entryLabel={journey.copy.allPropsLabel} />
    </section>
  );
}
