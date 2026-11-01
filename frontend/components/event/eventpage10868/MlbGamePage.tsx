"use client";

/**
 * #10868 — THE MLB GAME SCREEN (web), CORE CHECKPOINT.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a baseball fan's web event page
 * shows both teams' win chances, the score the page displays and the projected
 * final the page already admits together, with the two-team win history and
 * every original prop's exact Details.
 *
 * PRESENTATION ONLY. It draws the model `buildMlbGame`
 * (lib/eventPage10868/mlbGame.ts) built from values the page already holds,
 * through the accepted shared components, unchanged: `HockeyJourneyMatrix`
 * (the team-paired headline, its measured arrangement steps and its
 * once-for-both-teams absence lines), `HockeyJourneyHistoryChart` (the
 * two-team history and its own Details) and `HockeyJourneyAllProps` (every
 * original with its exact Details). No fetch, subscription, SWR key, timer,
 * effect or animation is added here; the only state is inside those three.
 *
 * ORDER, top to bottom (native `BaseballEventPagePresentation10868`): the state
 * lines → the matrix, each column's source and clock said once under it (native
 * draws the provenance under the matrix; there is no About control) → the
 * history → All props.
 *
 * DISPLAY ORDER: AWAY FIRST (Design D2, native baseball's order). The model is
 * in storage order (home first, each row and series tagged with its `side`);
 * `inDisplayOrder` makes immutable presentation copies picked by side. Nothing
 * is swapped by position and every id is unchanged.
 *
 * HEADLINE PROMINENCE. Every figure is in the matrix: the lead column (the
 * current chance during play, else the first; the final runs after the final)
 * is its largest figure in the team's colour, and runs and the projected final
 * sit in the same aligned grid as the chances — never a small grey line under
 * it. `compactColumns` lets four columns stay aligned at a phone width before
 * the matrix falls back to one labelled block per team; at an enlarged text
 * size it goes straight to those blocks (the matrix's own measured steps).
 *
 * RESET ON EVENT OR PHASE. The history and All props are keyed by the model's
 * `scope` (`mlb:<event>:<phase>`), which changes only when the event or the
 * phase does — so an open Details, an open list or a chart disclosure never
 * survives into another game or another phase, and a refresh in the same scope
 * keeps every one of them (All props holds each open Details by the original's
 * exact key). Never give this section a key that changes per refresh.
 *
 * FUTURE (Design D4, NOT built here; no empty panel): when the approved story
 * cards land, they sit BESIDE the history at regular width when both keep
 * native's minimum widths (`anchorMinWidth` 460 pt / `storiesMinWidth` 360 pt,
 * BaseballEventPagePresentation10868.swift, as 28.75rem / 22.5rem bases in a
 * wrapping row), and stack history-then-stories on phones and at enlarged text.
 * The insertion point is marked below (`data-mlb-history-row`).
 */

import type { HockeyJourneyHeadline, HockeyJourneyHistory } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { MLB_WORDS, type MlbGameModel } from "@/lib/eventPage10868/mlbGame";
import { teamColorStyle } from "@/lib/teamColors";
import HockeyJourneyMatrix from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart from "./HockeyJourneyHistoryChart";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";
import { inDisplayOrder } from "./FootballJourneySection";

export default function MlbGamePage({ model }: { model: MlbGameModel }) {
  if (model.kind === "refused") {
    if (model.words === null) return null;
    return (
      <section
        aria-label={MLB_WORDS.refusedLabel}
        data-mlb-game="refused"
        className="space-y-1 rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-text-primary"
      >
        {model.state && <p className="break-words font-semibold">{model.state}</p>}
        <p className="break-words text-text-secondary">{model.words}</p>
      </section>
    );
  }

  // Presentation copies, away first, picked by side. The model is never mutated.
  const headline: HockeyJourneyHeadline = {
    ...model.headline,
    matrix: { ...model.headline.matrix, rows: inDisplayOrder(model.headline.matrix.rows) },
  };
  const history: HockeyJourneyHistory = { ...model.history, series: inDisplayOrder(model.history.series) };
  // A team colour paints its own figure and line only when it clears the card-surface contrast floor
  // (`tint`); otherwise the series tokens stand in — the hockey screen's rule, unchanged.
  const style = teamColorStyle(headline.home.tint, headline.away.tint);
  const lineColors = {
    home: headline.home.tint ? "rgb(var(--team-home-primary))" : "var(--series-1)",
    away: headline.away.tint ? "rgb(var(--team-away-primary))" : "var(--series-2)",
  };

  return (
    <section
      aria-label={headline.spokenLabel}
      data-mlb-game={model.phase}
      data-history-foreign={model.historyForeign ? "true" : undefined}
      className="space-y-6 rounded-xl border border-surface-border bg-surface-card p-4 text-text-primary sm:p-5"
      style={style}
    >
      <header className="space-y-0.5">
        <p className="break-words text-sm font-semibold">{headline.state}</p>
        {headline.stateContext && <p className="break-words text-sm text-text-secondary">{headline.stateContext}</p>}
      </header>

      <HockeyJourneyMatrix headline={headline} inlineProvenance compactColumns />

      {/* D4 insertion point: the approved stories join this row beside the history (see header). */}
      <div data-mlb-history-row="">
        <HockeyJourneyHistoryChart key={model.scope} history={history} colors={lineColors} />
      </div>

      <HockeyJourneyAllProps key={model.originals.scope} originals={model.originals} entryLabel={model.allPropsLabel} />
    </section>
  );
}
