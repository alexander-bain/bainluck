"use client";

/**
 * #10868 — the hockey journey's story stream (web). MANUAL: the reader moves
 * with Previous and Next, and nothing else moves the card. No playback, no
 * dwell, no timer, no ranking — hockey has no stream owner that ranks or
 * advances cards (native `HockeyJourneyPageInputAdapter10868`), so none is
 * invented here. The order is the screen's fixed one: points, then assists.
 *
 * It also HOLDS each story's player and milestone choice (native host
 * `pointsPlayer`/`pointsMilestone`/`assistsPlayer`/`assistsMilestone`), so a new
 * view model (a refresh) or moving between stories never rewrites what the
 * reader chose; only the reader's own explicit choice changes it.
 */

import { useId, useState } from "react";
import {
  NO_HELD_CHOICE,
  type HockeyJourneyHeldChoice,
  type HockeyJourneyStat,
  type HockeyJourneyViewModel,
} from "@/lib/eventPage10868/hockeyJourney";
import HockeyJourneyContributionCard from "./HockeyJourneyContributionCard";

export default function HockeyJourneyStories({ journey }: { journey: HockeyJourneyViewModel }) {
  const headingId = useId();
  const [index, setIndex] = useState(0);
  const [held, setHeld] = useState<Record<HockeyJourneyStat, HockeyJourneyHeldChoice>>({
    points: NO_HELD_CHOICE,
    assists: NO_HELD_CHOICE,
  });
  const stories = journey.stories;
  const count = stories.length;
  const at = count === 0 ? 0 : Math.min(index, count - 1);
  const story = stories[at];
  const card = story ? (story.id === "points" ? journey.points : journey.assists) : null;
  const previous = count > 1 ? stories[(at + count - 1) % count] : null;
  const next = count > 1 ? stories[(at + 1) % count] : null;

  return (
    <section aria-labelledby={headingId} aria-roledescription="story stream" className="space-y-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="text-base font-semibold">
          {journey.copy.streamHeading}
        </h3>
        {count > 1 && (
          <p className="text-sm text-text-secondary" aria-live="polite">
            {`${at + 1} of ${count}`}
            {story ? ` · ${story.name}` : ""}
          </p>
        )}
      </header>

      {journey.copy.manualStatus && <p className="text-sm text-text-secondary">{journey.copy.manualStatus}</p>}

      {card ? (
        <HockeyJourneyContributionCard
          key={card.stat}
          card={card}
          held={held[card.stat]}
          onHold={(next) => setHeld((prev) => ({ ...prev, [card.stat]: next }))}
        />
      ) : (
        <p className="rounded-lg bg-surface-deep p-3 text-sm text-text-secondary">{journey.copy.storyUnavailable}</p>
      )}

      {previous && next && (
        <nav aria-label={journey.copy.storiesLabel} className="flex flex-wrap justify-between gap-2">
          <button
            type="button"
            onClick={() => setIndex((at + count - 1) % count)}
            className="min-h-11 rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            Previous
            <span className="text-text-secondary font-normal">{` · ${previous.name}`}</span>
          </button>
          <button
            type="button"
            onClick={() => setIndex((at + 1) % count)}
            className="min-h-11 rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
          >
            Next
            <span className="text-text-secondary font-normal">{` · ${next.name}`}</span>
          </button>
        </nav>
      )}
    </section>
  );
}
