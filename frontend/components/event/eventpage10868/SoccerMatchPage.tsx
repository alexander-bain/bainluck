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
 * FULL-SIZE READERS (native host reader sheet, `reader(card)`): "Full chart"
 * opens the same history in `SoccerMatchReader` with the chart's expanded
 * layout (taller plot, nothing else changed), under the compact names, score
 * and state and the same three-outcome headline; it is offered only while the
 * history has a plot to show (native `expand`). The story stream's "Open full
 * card" reader gets the same compact context. One reader at a time: while one
 * is open the other's entry rests, and a new event or phase closes both (the
 * stream's reading-scope rule, `match.stories.scope`).
 *
 * Accessibility: headings in document order, real buttons, labelled values,
 * no motion, layouts that wrap at 375 px and at 200% text.
 */

import { useId, useRef, useState } from "react";
import type { SoccerMatchViewModel } from "@/lib/eventPage10868/soccerMatch";
import type { SoccerMatchHeader, SoccerMatchScore, SoccerSlot } from "@/lib/eventPage10868/soccerMatchTypes";
import { teamColorStyle } from "@/lib/teamColors";
import SoccerMatchHeadline from "./SoccerMatchHeadline";
import SoccerMatchHistoryChart from "./SoccerMatchHistoryChart";
import SoccerMatchStories from "./SoccerMatchStories";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";
import SoccerMatchReader, { SOCCER_READER_WORDS, soccerReaderEntry } from "./SoccerMatchReader";
import { useIsomorphicLayoutEffect } from "./useFrameMeasure";

function ContextLine({ slot }: { slot: SoccerSlot }) {
  return <p className={`text-sm ${slot.kind === "value" ? "text-text-primary" : "text-text-secondary"}`}>{slot.text}</p>;
}

type SoccerScoreFigures = Extract<SoccerMatchScore, { kind: "actual" }>;

/**
 * The reader's compact match context (native `compactHeader`): the names and
 * the held score on one wrapping line, then the state words. Not a heading and
 * no id: the page's scoreboard heading stays the only one.
 */
function ReaderContext({ header, figures }: { header: SoccerMatchHeader; figures: SoccerScoreFigures | null }) {
  return (
    <div className="space-y-1" data-soccer-reader-context="">
      <p className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 font-bold">
        <span className="sr-only">{figures ? figures.spoken : `${header.home}, ${header.away}`}</span>
        <span className="min-w-0 break-words text-base font-semibold" aria-hidden="true">
          {header.home}
        </span>
        {figures && (
          <span className="whitespace-nowrap text-lg tabular-nums" aria-hidden="true">
            {figures.home}
            <span className="px-2 text-text-secondary">–</span>
            {figures.away}
          </span>
        )}
        <span className="min-w-0 break-words text-right text-base font-semibold" aria-hidden="true">
          {header.away}
        </span>
      </p>
      <p className="text-sm text-text-secondary">{header.state}</p>
    </div>
  );
}

/** Which of the page's readers is open, in one reading scope. */
interface SoccerPageReaders {
  scope: string;
  history: boolean;
  story: boolean;
}

const closedReaders = (scope: string): SoccerPageReaders => ({ scope, history: false, story: false });

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

  // The page's readers share the stream's reading scope: a new event or phase closes them, as it resets the stream.
  const scope = match.stories.scope;
  const [stored, setStored] = useState<SoccerPageReaders>(() => closedReaders(scope));
  if (stored.scope !== scope) setStored(closedReaders(scope));
  const readers = stored.scope === scope ? stored : closedReaders(scope);
  const setReaders = (change: Partial<Omit<SoccerPageReaders, "scope">>) =>
    setStored((prev) => ({ ...(prev.scope === scope ? prev : closedReaders(scope)), ...change }));
  const page = useRef<HTMLElement>(null);
  const chartEntry = useRef<HTMLButtonElement>(null);
  const openedIn = useRef<string | null>(null);
  const scopeNow = useRef(scope);
  useIsomorphicLayoutEffect(() => {
    scopeNow.current = scope;
  });
  // Native offers `expand` only on a history with a plot; an absence has nothing larger to show.
  const plotted = !match.history.absence && Boolean(match.history.domain);
  const openHistory = () => {
    if (readers.story || readers.history) return;
    openedIn.current = scope;
    setReaders({ history: true });
  };
  const historyReturn = () => {
    const own = chartEntry.current;
    if (openedIn.current === scopeNow.current && own?.isConnected && !own.disabled) return own;
    return soccerReaderEntry(page.current, "history");
  };
  const readerContext = <ReaderContext header={header} figures={figures} />;

  return (
    <section
      ref={page}
      aria-labelledby={headingId}
      data-soccer-match={match.phase}
      // Pixel padding: identical to p-4 / sm:p-5 at normal text, and not doubled at
      // enlarged text, so a long team name keeps the room (#10868 P2).
      className="space-y-6 rounded-xl border border-surface-border bg-surface-card p-[16px] text-text-primary sm:p-[20px]"
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
          {/* The team names wear the headline's outcome-label role (text-base semibold): a fixed type role that scales with the reader's text, never fit-to-width. */}
          <span className="min-w-0 break-words text-base font-semibold" data-soccer-scoreboard-name="home">
            {header.home}
          </span>
          {figures && (
            <span className="whitespace-nowrap text-2xl tabular-nums" aria-hidden="true">
              {figures.home}
              <span className="px-2 text-text-secondary">–</span>
              {figures.away}
            </span>
          )}
          <span className="min-w-0 break-words text-right text-base font-semibold" data-soccer-scoreboard-name="away">
            {header.away}
          </span>
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

      <div className="space-y-3">
        <SoccerMatchHistoryChart history={match.history} colors={lineColors} />
        {plotted && (
          <button
            ref={chartEntry}
            type="button"
            disabled={readers.story || readers.history}
            aria-label={`${SOCCER_READER_WORDS.fullChart}: ${match.history.title}`}
            onClick={openHistory}
            data-soccer-reader-entry="history"
            className="min-h-11 w-full rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand sm:w-auto"
          >
            {SOCCER_READER_WORDS.fullChart}
          </button>
        )}
      </div>

      <SoccerMatchStories
        stream={match.stories}
        colors={lineColors}
        readerContext={readerContext}
        readerBlocked={readers.history}
        onReaderOpenChange={(open) => setReaders({ story: open })}
      />

      <HockeyJourneyAllProps originals={match.originals} entryLabel={match.copy.allPropsLabel} />

      {/* The history reader stays open through a live update, even one that takes its plot away: the chart then says so in its own words. */}
      {readers.history && (
        <SoccerMatchReader
          kind="history"
          title={match.history.title}
          context={readerContext}
          onClose={() => setReaders({ history: false })}
          returnTo={historyReturn}
        >
          <SoccerMatchHeadline headline={headline} />
          <SoccerMatchHistoryChart history={match.history} colors={lineColors} layout="expanded" />
        </SoccerMatchReader>
      )}
    </section>
  );
}
