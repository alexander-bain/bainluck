"use client";

/**
 * #10868 — THE FOOTBALL HEADLINE AND WIN HISTORY SECTION (web), on the accepted
 * hockey journey foundation.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: on the NFL routes a reader
 * compares both teams' earlier and current chances, the score and the projected
 * final with the two-team win history, and after the final compares the actual
 * result with the pregame forecast.
 *
 * PRESENTATION ONLY. It draws the view `buildFootballJourney`
 * (lib/eventPage10868/footballJourney.ts) built from data the page already
 * holds, through the hockey foundation's unchanged `HockeyJourneyMatrix` and
 * `HockeyJourneyHistoryChart`. No fetch, subscription, SWR key, timer or
 * animation. Its only state is the reader's own Info disclosure. Nothing runs on
 * mount or on layout: the two controls call the host only when the reader
 * activates them.
 *
 * WHY THE PROPS ARE DECLARED HERE, STRUCTURALLY. `__tests__/lib/
 * settledVocabulary.test.tsx` walks `components/**` and `lib/**` and requires
 * every component that transitively imports `lib/propGrade.ts` to be enrolled in
 * its census (`describe("every settled surface is enrolled in the census")` →
 * "no component that can state a verdict is left out of the census"; type-only
 * imports count, its scan reads every `from "…"`). `footballJourney.ts` reaches
 * `propGrade` through `hockeyJourney.ts`, and this section states no prop
 * verdict, so it imports neither: its prop shapes are declared below from
 * `hockeyJourneyTypes` (an import-free module) and the host passes the view in.
 * `__tests__/lib/footballJourney10868.test.ts` checks that the builder's output
 * is assignable to `FootballJourneySectionModel` (a `satisfies` the CI
 * typecheck enforces), so the two cannot drift silently. (`__tests__/**` is not
 * in the census walk, so that test may import these types.)
 *
 * HOST CONTRACT.
 *   - The host calls `buildFootballJourney({ event, history, host })` with the
 *     event it shows, the `/history` body it holds, the hero pair it resolved for
 *     THAT event, and the REQUIRED `liveClaimUnbacked` — the page's own
 *     `pageLiveClaimIsUnbacked` answer from its existing owner (the app mount
 *     that supplies it is not built here) — and passes the result as `model`. A
 *     refusal with words prints them; a refusal without words (not an NFL row)
 *     renders nothing.
 *   - `onOpenForecast` / `onOpenHistory` are offered as controls ONLY when the
 *     view admits a destination (`forecastAction` / `historyAction`) AND the host
 *     passes a callback. A nil callback means no control; an admitted destination
 *     without a callback means no control. There is no history control without
 *     the game's own drawn history.
 *   - The HOST OWNS the full reader those callbacks open: its route or sheet,
 *     Back, where focus goes and returns, and the held context (the same event,
 *     phase and bodies). A callback is not reader parity; this section does not
 *     build or imply a reader.
 *
 * DISPLAY ORDER: AWAY FIRST (Design 2026-10-31, native football's order). The
 * view arrives in canonical storage order (home first, every row and series
 * tagged with its `side`). `inDisplayOrder` makes immutable presentation copies
 * of `headline.matrix.rows` and `history.series`, picking each item by its own
 * `side` — no positional swap, no relabelling, nothing mutated, every id, point
 * id, reading and callback unchanged. The earlier forecast reads in the same
 * order. The shared renderers pick each team's name, tint, result, colour and
 * glyph by `side` (the matrix `teams[row.side]`; the chart `colorOf(series)` /
 * `shapes[series.side]`); the chart's local `[home, away] = history.series` is
 * only a name, so the one positional effect is SVG paint order — the
 * later-listed (home) line paints over the away line where they cross.
 *
 * LAYOUT. Header row: the state lines and, beside them, the compact Info
 * control (the hockey screen's accepted circled-info disclosure: lucide `Info`
 * glyph, the About words as its accessible name, a 44 px target, a real
 * `aria-expanded` button that opens a panel under the row and takes no row of
 * its own while closed) → the matrix (each column's role in its own title;
 * sources and clocks only in Info) → during play, the visible earlier forecast
 * directly under the matrix, beside the current projected final it is compared
 * with → the forecast control → the history chart (its own Details) → the
 * history control. Targets are 44 px (`min-h-11`); text wraps as words at 200%.
 */

import { useId, useState } from "react";
import { Info } from "lucide-react";
import type {
  HockeyJourneyHeadline,
  HockeyJourneyHistory,
  HockeyJourneyPhase,
  HockeyJourneySide,
  HockeyJourneySlot,
} from "@/lib/eventPage10868/hockeyJourneyTypes";
import { teamColorStyle } from "@/lib/teamColors";
import HockeyJourneyMatrix from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart from "./HockeyJourneyHistoryChart";

/** The earlier forecast drawn under the matrix during play. */
export interface FootballJourneySectionEarlierForecast {
  title: string;
  home: HockeyJourneySlot;
  away: HockeyJourneySlot;
}

/** A destination the view admits; drawn as a control only with the host's callback. */
export interface FootballJourneySectionAction {
  label: string;
}

/** The section's view when it applies (`FootballJourneyView`, structurally). */
export interface FootballJourneySectionView {
  kind: "journey";
  eventId: number;
  phase: HockeyJourneyPhase;
  headline: HockeyJourneyHeadline;
  earlierForecast: FootballJourneySectionEarlierForecast | null;
  history: HockeyJourneyHistory;
  historyForeign: boolean;
  info: { label: string; lines: string[] };
  forecastAction: FootballJourneySectionAction | null;
  historyAction: FootballJourneySectionAction | null;
}

/** Why the section draws no journey (`FootballJourneyRefusal`, structurally). */
export interface FootballJourneySectionRefusal {
  kind: "refused";
  /** The words to show instead; null renders nothing. */
  words: string | null;
  /** The authority's own word for a stopped or voided game, when it gave one. */
  state: string | null;
}

export type FootballJourneySectionModel = FootballJourneySectionView | FootballJourneySectionRefusal;

export interface FootballJourneySectionProps {
  model: FootballJourneySectionModel;
  /** Opens the host's forecast reader. Absent or null: no forecast control. */
  onOpenForecast?: (() => void) | null;
  /** Opens the host's win-history reader. Absent or null: no history control. */
  onOpenHistory?: (() => void) | null;
}

/** The accessible name of the refused section (the authority's state and the absence words stay its content). */
export const REFUSED_SECTION_LABEL = "Football game status";

/**
 * The order the section PRESENTS the two teams in. A flip is this line, the
 * `"away-home"` order flag footballJourney.ts passes to `suspendedSummary`, and
 * test expectations.
 */
export const FOOTBALL_DISPLAY_ORDER: readonly [HockeyJourneySide, HockeyJourneySide] = ["away", "home"];

/**
 * An immutable presentation copy of a side-tagged pair, in display order, each
 * item picked by its OWN `side`. A pair that is not exactly one home and one away
 * is returned in its given order: nothing is swapped by position.
 */
export function inDisplayOrder<T extends { side: HockeyJourneySide }>(pair: readonly [T, T]): [T, T] {
  const first = pair.find((item) => item.side === FOOTBALL_DISPLAY_ORDER[0]);
  const second = pair.find((item) => item.side === FOOTBALL_DISPLAY_ORDER[1]);
  return first && second ? [first, second] : [pair[0], pair[1]];
}

const CONTROL_CLASS =
  "inline-flex min-h-11 items-center rounded-lg border border-surface-border px-3 text-sm font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand";

function SlotText({ slot }: { slot: HockeyJourneySlot }) {
  if (slot.kind === "absent") return <span className="break-words text-text-secondary">{slot.text}</span>;
  return (
    <>
      <span aria-hidden="true" className="whitespace-nowrap font-semibold tabular-nums">
        {slot.text}
      </span>
      <span className="sr-only">{slot.spoken}</span>
    </>
  );
}

export default function FootballJourneySection({ model, onOpenForecast, onOpenHistory }: FootballJourneySectionProps) {
  const earlierId = useId();
  const infoId = useId();
  const [infoOpen, setInfoOpen] = useState(false);

  if (model.kind === "refused") {
    if (model.words === null) return null;
    return (
      <section
        aria-label={REFUSED_SECTION_LABEL}
        data-football-journey="refused"
        className="space-y-1 rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-primary"
      >
        {model.state && <p className="font-semibold">{model.state}</p>}
        <p className="text-text-secondary">{model.words}</p>
      </section>
    );
  }

  const { earlierForecast, info } = model;
  // Presentation copies, away first, picked by side. The view itself is never mutated.
  const headline: HockeyJourneyHeadline = {
    ...model.headline,
    matrix: { ...model.headline.matrix, rows: inDisplayOrder(model.headline.matrix.rows) },
  };
  const history: HockeyJourneyHistory = { ...model.history, series: inDisplayOrder(model.history.series) };
  // A team colour paints its own line only when it clears the contrast floor (`tint`); otherwise the
  // series tokens stand in — the hockey screen's rule, unchanged.
  const style = teamColorStyle(headline.home.tint, headline.away.tint);
  const lineColors = {
    home: headline.home.tint ? "rgb(var(--team-home-primary))" : "var(--series-1)",
    away: headline.away.tint ? "rgb(var(--team-away-primary))" : "var(--series-2)",
  };
  const teams = { home: headline.home, away: headline.away };
  const hasInfo = info.lines.length > 0;
  const forecastControl = model.forecastAction && onOpenForecast ? model.forecastAction : null;
  const historyControl = model.historyAction && onOpenHistory ? model.historyAction : null;

  return (
    <section
      aria-label={headline.spokenLabel}
      data-football-journey={model.phase}
      data-history-foreign={model.historyForeign ? "true" : undefined}
      className="space-y-5 rounded-xl border border-surface-border bg-surface-card p-4 text-text-primary sm:p-5"
      style={style}
    >
      <header className="space-y-2">
        <div data-football-header-row="" className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-0.5">
            <p className="break-words text-sm font-semibold">{headline.state}</p>
            {headline.stateContext && <p className="break-words text-sm text-text-secondary">{headline.stateContext}</p>}
          </div>
          {hasInfo && (
            <button
              type="button"
              aria-expanded={infoOpen}
              aria-controls={infoId}
              onClick={() => setInfoOpen((open) => !open)}
              data-football-info-toggle=""
              className={`-mr-2 -mt-1 inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full text-text-primary hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
                infoOpen ? "bg-surface-elevated" : ""
              }`}
            >
              {/* rem-sized, so the glyph grows with the reader's text like the target does. */}
              <Info aria-hidden="true" className="h-5 w-5" />
              <span className="sr-only">{info.label}</span>
            </button>
          )}
        </div>
        {hasInfo && (
          <div id={infoId} hidden={!infoOpen} data-football-info="" className="rounded-lg bg-surface-deep p-3">
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {info.lines.map((line, i) => (
                <li key={`${i}:${line}`} className="break-words">
                  {line}
                </li>
              ))}
            </ul>
          </div>
        )}
      </header>

      <HockeyJourneyMatrix headline={headline} inlineProvenance={false} />

      {earlierForecast && (
        <div role="group" aria-labelledby={earlierId} data-football-earlier-forecast="" className="text-sm">
          <p id={earlierId} className="font-semibold text-text-primary">
            {earlierForecast.title}
          </p>
          <dl className="mt-1 flex flex-wrap gap-x-6 gap-y-1">
            {headline.matrix.rows.map(({ side }) => (
              <div key={side} data-side={side} className="flex min-w-0 flex-wrap items-baseline gap-x-1">
                <dt className="break-words font-medium text-text-secondary">{teams[side].name}</dt>
                <dd>
                  <SlotText slot={earlierForecast[side]} />
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {forecastControl && onOpenForecast && (
        <button type="button" onClick={() => onOpenForecast()} className={CONTROL_CLASS} data-football-control="forecast">
          {forecastControl.label}
        </button>
      )}

      <HockeyJourneyHistoryChart history={history} colors={lineColors} />

      {historyControl && onOpenHistory && (
        <button type="button" onClick={() => onOpenHistory()} className={CONTROL_CLASS} data-football-control="history">
          {historyControl.label}
        </button>
      )}
    </section>
  );
}
