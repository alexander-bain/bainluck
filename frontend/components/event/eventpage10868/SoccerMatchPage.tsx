"use client";

/**
 * #10868 — THE SOCCER MATCH SCREEN (web).
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a soccer fan's web event page
 * opens on the three-outcome chances (home / draw / away), the match's history
 * and the stories the match has content for, with All props and exact Details,
 * and prints the same answers as the iPhone screen.
 *
 * Presentation only, in native `SoccerEventPagePresentation10868`'s order:
 * the header (state and kickoff words), the three-outcome headline, the
 * scoreboard, the match context (the score's own clock, the match clock, the
 * projected final), then the history, the story stream and All props. It
 * receives `SoccerMatchViewModel` (built by `buildSoccerMatch` from data the
 * event page already holds) and adds no fetch, subscription, SWR key, timer or
 * animation. Native offers no About control on this screen (host `onAbout:
 * nil`), so none is drawn.
 *
 * Accessibility: headings in document order, real buttons, labelled values,
 * no motion, layouts that wrap at 375 px and at 200% text.
 */

import { useId } from "react";
import type { SoccerMatchViewModel } from "@/lib/eventPage10868/soccerMatch";
import type { SoccerSlot } from "@/lib/eventPage10868/soccerMatchTypes";
import { teamColorStyle } from "@/lib/teamColors";
import SoccerMatchHeadline from "./SoccerMatchHeadline";
import SoccerMatchHistoryChart from "./SoccerMatchHistoryChart";
import SoccerMatchStories from "./SoccerMatchStories";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";

function ContextLine({ slot }: { slot: SoccerSlot }) {
  return <p className={`text-sm ${slot.kind === "value" ? "text-text-primary" : "text-text-secondary"}`}>{slot.text}</p>;
}

export default function SoccerMatchPage({ match }: { match: SoccerMatchViewModel }) {
  const headingId = useId();
  const { header, headline } = match;
  const [home, , away] = headline.outcomes;

  // A team colour paints its own figure and line only when it clears the card-surface contrast floor
  // (`teamTextColor`, carried as `tint`); otherwise the series tokens stand in.
  const style = teamColorStyle(home.tint, away.tint);
  const lineColors = {
    home: home.tint ? "rgb(var(--team-home-primary))" : "var(--series-1)",
    away: away.tint ? "rgb(var(--team-away-primary))" : "var(--series-2)",
  };
  const score = header.score;
  const figures = score?.kind === "actual" ? score : null;
  const scoreLine: SoccerSlot | null =
    score?.kind === "actual"
      ? score.context
        ? { kind: "value", text: score.context }
        : null
      : score?.kind === "unavailable"
        ? { kind: "unavailable", text: score.text }
        : null;

  return (
    <section
      aria-labelledby={headingId}
      data-soccer-match={match.phase}
      className="space-y-6 rounded-xl border border-surface-border bg-surface-card p-4 text-text-primary sm:p-5"
      style={style}
    >
      <header className="space-y-3">
        <div className="space-y-0.5">
          <p className="text-sm font-semibold">{header.state}</p>
          {header.date && <p className="text-sm text-text-secondary">{header.date}</p>}
        </div>

        <SoccerMatchHeadline headline={headline} />

        {/* The scoreboard: home, the score when one is held, away. */}
        <h2
          id={headingId}
          className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-lg font-bold"
          aria-label={figures ? figures.spoken : `${header.home}, ${header.away}`}
        >
          <span className="min-w-0 break-words">{header.home}</span>
          {figures && (
            <span className="whitespace-nowrap text-2xl tabular-nums" aria-hidden="true">
              {figures.home}
              <span className="px-2 text-text-secondary">–</span>
              {figures.away}
            </span>
          )}
          <span className="min-w-0 break-words text-right">{header.away}</span>
        </h2>

        {(scoreLine || header.clock || header.projection) && (
          <div className="space-y-1" data-soccer-context="">
            {scoreLine && <ContextLine slot={scoreLine} />}
            {header.clock && <ContextLine slot={header.clock} />}
            {header.projection && (
              <div>
                <p className="text-sm font-semibold">{header.projection.title}</p>
                <ContextLine slot={header.projection.reading} />
              </div>
            )}
          </div>
        )}
      </header>

      <SoccerMatchHistoryChart history={match.history} colors={lineColors} />

      <SoccerMatchStories stream={match.stories} colors={lineColors} />

      <HockeyJourneyAllProps originals={match.originals} entryLabel={match.copy.allPropsLabel} />
    </section>
  );
}
