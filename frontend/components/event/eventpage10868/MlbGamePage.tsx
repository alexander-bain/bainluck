"use client";

/**
 * #10868 — THE MLB GAME SCREEN (web), CORE CHECKPOINT.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a baseball fan's web event page
 * shows both teams' win chances, the score the page displays and the projected
 * final the page already admits together, with the two-team win history and
 * every original prop's exact Details. BINDING INCREMENT SHIP: after a baseball
 * game, the event page shows the actual run total against the offered lines,
 * alongside its win-probability history.
 *
 * PRESENTATION ONLY. It draws the model `buildMlbGame`
 * (lib/eventPage10868/mlbGame.ts) built from values the page already holds,
 * through the accepted components: `HockeyJourneyMatrix` (the team-paired
 * headline, its measured arrangement steps and its once-for-both-teams
 * absence lines), `HockeyJourneyHistoryChart` (the two-team history and its
 * own Details), `MlbRunTotalsCard` (after the final only: the run total against
 * every offered line, through its optional controlled selection) and
 * `HockeyJourneyAllProps` (every original with its exact Details). No fetch,
 * subscription, SWR key, timer, effect or animation is added here; the only
 * state is inside those components plus the run-line slot's scope and chosen
 * key (see THE CHOSEN RUN LINE).
 *
 * ORDER, top to bottom (native `BaseballEventPagePresentation10868`): the state
 * lines → the matrix, each column's source and clock said once under it (native
 * draws the provenance under the matrix; there is no About control) → the
 * history, with the final run-total card beside or under it → All props.
 *
 * DISPLAY ORDER: AWAY FIRST (Design D2, native baseball's order). The model is
 * in storage order (home first, each row and series tagged with its `side`);
 * `inDisplayOrder` makes immutable presentation copies picked by side. Nothing
 * is swapped by position and every id is unchanged.
 *
 * TEAM NAMES WITH NOTHING TO READ. When NO headline slot holds a readable value
 * (every column absent for both teams in the same words, and no result), the
 * shared matrix states each column once under "Both teams" and draws no team
 * row, so the teams would vanish. Only then are the model's own away and home
 * names listed here, once, away first, and with no figure. In every other case
 * the matrix names the teams and nothing is added; its shared absence lines are
 * unchanged.
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
 * THE CHOSEN RUN LINE (B1). The run-total card's chosen line is held ABOVE the
 * card by `MlbRunTotalsSlot`, a page-local slot that stays mounted in the row
 * whether or not a card is drawn. Its only state is the scope and the chosen
 * option key — never a totals model, line or probability. A same-scope pass
 * with no card (the matrix gone) draws nothing at all, and the key survives;
 * when this event's own matrix returns, the card opens on that key (or says
 * "Selected line unavailable" if the lines do not carry it exactly once — never
 * the default — and shows it again when it returns). A new scope (event or
 * phase) clears it, while rendering. One callback per deliberate tap; no
 * effect, timer or automatic selection. Native: `BaseballStoriesAdapter10868`
 * holds `selectedOptionKey` outside the card.
 *
 * THE HISTORY ROW (Design D4, built for the FINAL run-total card only; no empty
 * panel). `data-mlb-history-row` is a wrapping flex row with a 1.5rem gap. The
 * history is ALWAYS its first item, at the same place in the tree, so its chart
 * and disclosures never remount when the card comes or goes. The card is a
 * second item only for a final model whose `runTotals` is non-null (the slot
 * draws no element otherwise). Each item
 * grows from native's minimum readable width (`anchorMinWidth` 460 pt /
 * `storiesMinWidth` 360 pt, BaseballEventPagePresentation10868.swift, as
 * 28.75rem / 22.5rem flex bases) and may shrink below it (`min-w-0`): the two
 * sit side by side only while the row holds 28.75 + 1.5 + 22.5 = 52.75rem; below
 * that, the card wraps under the history and each takes the full row width.
 * Rem bases grow with the reader's text, so enlarged text stacks them. With no
 * card, the history alone fills the row exactly as before.
 */

import { useState } from "react";
import type { HockeyJourneyHeadline, HockeyJourneyHistory } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { MLB_WORDS, type MlbGameModel } from "@/lib/eventPage10868/mlbGame";
import type { MlbFinalTotals } from "@/lib/eventPage10868/mlbRunTotals";
import { teamColorStyle } from "@/lib/teamColors";
import HockeyJourneyMatrix, { matrixSharedAbsences } from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart from "./HockeyJourneyHistoryChart";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";
import MlbRunTotalsCard, { type MlbRunTotalsColors } from "./MlbRunTotalsCard";
import { inDisplayOrder } from "./FootballJourneySection";

/**
 * The row's second item: holds the chosen run line for `scope` and draws the
 * card only while `totals` exists. Stays mounted when it draws nothing, so a
 * same-scope absence keeps the key (B1, see header). State = scope + key only.
 */
function MlbRunTotalsSlot({
  totals,
  scope,
  colors,
}: {
  totals: MlbFinalTotals | null;
  scope: string;
  colors: MlbRunTotalsColors;
}) {
  const [chosen, setChosen] = useState<{ scope: string; key: string | null }>(() => ({ scope, key: null }));
  // A new event or phase clears the choice while rendering, whether or not a card is drawn.
  if (chosen.scope !== scope) setChosen({ scope, key: null });
  const held = chosen.scope === scope ? chosen.key : null;
  if (!totals) return null;
  return (
    <div data-mlb-row-item="runTotals" className="min-w-0 grow basis-[22.5rem]">
      <MlbRunTotalsCard
        totals={totals}
        scope={scope}
        colors={colors}
        selection={{ held, onSelect: (key) => setChosen({ scope, key }) }}
      />
    </div>
  );
}

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
  // No readable slot and no result: the matrix draws no team row (every column is a shared absence).
  const { matrix } = headline;
  const namesOnly =
    matrix.rows.every((row) => !row.result && row.values.every((slot) => slot.kind === "absent")) &&
    matrixSharedAbsences(matrix).length === matrix.columns.length;
  // A team colour paints its own figure and line only when it clears the card-surface contrast floor
  // (`tint`); otherwise the series tokens stand in — the hockey screen's rule, unchanged.
  const style = teamColorStyle(headline.home.tint, headline.away.tint);
  const lineColors = {
    home: headline.home.tint ? "rgb(var(--team-home-primary))" : "var(--series-1)",
    away: headline.away.tint ? "rgb(var(--team-away-primary))" : "var(--series-2)",
  };
  // The final run-total card: a FINAL model with a built card only (the builder already holds it to the final).
  const runTotals = model.phase === "final" ? model.runTotals : null;

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

      {/* One wrapper in every case, so the matrix never remounts when the names line comes or goes. */}
      <div className="space-y-2">
        {namesOnly && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-base font-semibold" data-mlb-team-names="">
            {[headline.away, headline.home].map((team) => (
              <li key={team.side} className="min-w-0 break-words" style={team.tint ? { color: team.tint } : undefined}>
                {team.name}
              </li>
            ))}
          </ul>
        )}
        <HockeyJourneyMatrix headline={headline} inlineProvenance compactColumns />
      </div>

      {/* D4: the history, then (final only) the run-total card; side by side while both bases fit (see header). */}
      <div data-mlb-history-row="" className="flex flex-wrap gap-6">
        <div data-mlb-row-item="history" className="min-w-0 grow basis-[28.75rem]">
          <HockeyJourneyHistoryChart key={model.scope} history={history} colors={lineColors} />
        </div>
        <MlbRunTotalsSlot totals={runTotals} scope={model.scope} colors={lineColors} />
      </div>

      <HockeyJourneyAllProps key={model.originals.scope} originals={model.originals} entryLabel={model.allPropsLabel} />
    </section>
  );
}
