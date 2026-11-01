"use client";

/**
 * #10868 — THE MLB GAME SCREEN (web), CORE CHECKPOINT.
 *
 * PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: a baseball fan's web event page
 * shows both teams' win chances, the score the page displays and the projected
 * final the page already admits together, with the two-team win history and
 * every original prop's exact Details. RUN-TOTAL SHIP: before and during play
 * the run milestones show each pregame chance, admitted in-game chance and the
 * runs so far apart; after the game the actual run total stands against the
 * offered lines — both alongside the win-probability history. READER SHIP
 * (I2): the run-total card offers "Open full card"; a fan explores the same
 * card full size, closes it, and returns to the same choice and place.
 *
 * PRESENTATION ONLY. It draws the model `buildMlbGame`
 * (lib/eventPage10868/mlbGame.ts) built from values the page already holds,
 * through the accepted components: `HockeyJourneyMatrix` (the team-paired
 * headline, its measured arrangement steps and its once-for-both-teams
 * absence lines), `HockeyJourneyHistoryChart` (the two-team history and its
 * own Details), `MlbRunTotalsCard` (the final run total against every offered
 * line after the game; S2a's milestone visual before first pitch and during
 * play; through its optional controlled selection) and
 * `HockeyJourneyAllProps` (every original with its exact Details), plus
 * `MlbRunTotalsReader` (the same run-total card full size, I1). No fetch,
 * subscription, SWR key, timer, effect or animation is added here; the only
 * state is inside those components plus the run-line slot's scope, chosen key,
 * reader-open flag and full-size-unavailable flag (see THE CHOSEN RUN LINE and
 * THE FULL-SIZE READER).
 *
 * ORDER, top to bottom (native `BaseballEventPagePresentation10868`): the state
 * lines → the matrix, each column's source and clock said once under it (native
 * draws the provenance under the matrix; there is no About control) → the
 * history, with the run-total card of this phase beside or under it → All
 * props.
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
 * THE FULL-SIZE READER (I2). The same slot also holds whether the reader is
 * open and whether the last attempt could not open — still no model, line or
 * probability. With a card, "Open full card" (spoken "Open full card: Run
 * totals") sits inside the run-total row item, under the card, disabled while
 * the reader is open; a status line beside it says "Full-size view
 * unavailable…" after a failed attempt until the next attempt or a new scope.
 * The reader (`MlbRunTotalsReader`, over the unchanged `SoccerMatchReader`
 * shell, which owns the modal, focus and scroll) gets the SAME phase-agreed
 * input and the SAME selection object as the page card, so a choice in either
 * is the other's. It sits after the row item as a fragment sibling, so it
 * stays mounted while open even when a same-scope pass has no input (the page
 * then draws no row item; the reader says only its absence words) and its
 * dialog is out of the row's flow (top layer). A new scope clears the key and
 * closes the reader in the same render: no frame shows it for the old phase.
 * Its compact context is read only from the built headline (see
 * `runReaderContext`). Focus returns (R-F3) to the entry while it is connected
 * and enabled, else to the history row — a persistent, programmatically
 * focusable local anchor, named as a group ("Win probability and run totals")
 * so a returned focus says where it landed — while the page remains; null only
 * once the page is gone. No Previous / Next and no Details (owed).
 *
 * PHASE AGREEMENT (S2c). The card is drawn only when its input agrees with the
 * page's phase: after the final a `kind: "final"` input; before first pitch and
 * during play a `kind: "milestones"` input whose own phase IS the page's phase.
 * Anything else — a constructed or stale mismatch — draws no card (never a
 * final card during play, never another phase's milestones).
 *
 * THE HISTORY ROW (Design D4, built for the run-total card in every phase; no
 * empty panel). `data-mlb-history-row` is a wrapping flex row with a 1.5rem
 * gap. The history is ALWAYS its first item, at the same place in the tree, so
 * its chart and disclosures never remount when the card comes or goes. The
 * card is a second item only while an agreeing input exists (the slot draws no
 * element otherwise). Each item
 * grows from native's minimum readable width (`anchorMinWidth` 460 pt /
 * `storiesMinWidth` 360 pt, BaseballEventPagePresentation10868.swift, as
 * 28.75rem / 22.5rem flex bases) and may shrink below it (`min-w-0`): the two
 * sit side by side only while the row holds 28.75 + 1.5 + 22.5 = 52.75rem; below
 * that, the card wraps under the history and each takes the full row width.
 * Rem bases grow with the reader's text, so enlarged text stacks them. With no
 * card, the history alone fills the row exactly as before.
 */

import { useRef, useState, type RefObject } from "react";
import type { HockeyJourneyHeadline, HockeyJourneyHistory, HockeyJourneyPhase } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { MLB_WORDS, type MlbGameModel } from "@/lib/eventPage10868/mlbGame";
import type { MlbRunTotalsInput } from "@/lib/eventPage10868/mlbRunTotals";
import { teamColorStyle } from "@/lib/teamColors";
import HockeyJourneyMatrix, { matrixSharedAbsences } from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart from "./HockeyJourneyHistoryChart";
import HockeyJourneyAllProps from "./HockeyJourneyAllProps";
import MlbRunTotalsCard, { type MlbRunTotalsColors, type MlbRunTotalsSelection } from "./MlbRunTotalsCard";
import MlbRunTotalsReader, { MLB_RUN_READER_WORDS, type MlbRunReaderContext } from "./MlbRunTotalsReader";
import { SOCCER_READER_WORDS } from "./SoccerMatchReader";
import { inDisplayOrder } from "./FootballJourneySection";

/**
 * The run-total input only when it agrees with the page's phase (see PHASE
 * AGREEMENT): final ↔ `kind: "final"`; before / live ↔ `kind: "milestones"` of
 * that same phase. Otherwise null: no card.
 */
function runTotalsForPhase(phase: HockeyJourneyPhase, input: MlbRunTotalsInput | null): MlbRunTotalsInput | null {
  if (!input) return null;
  if (phase === "final") return input.kind === "final" ? input : null;
  return input.kind === "milestones" && input.phase === phase ? input : null;
}

/**
 * The history row's accessible name, as a group: it is where focus returns when
 * the reader's entry is gone (R-F3). Native baseball's two card names
 * (`BaseballPageInputAdapter10868.Words.history` "Win probability" and
 * `.runTotals` "Run totals"), joined.
 */
export const MLB_HISTORY_ROW_LABEL = "Win probability and run totals";

/** The runs column of each phase's matrix (mlbGame.ts `mlbGameMatrix`): live index 2, final index 1, none before. */
const RUNS_COLUMN: Partial<Record<HockeyJourneyPhase, number>> = { live: 2, final: 1 };

/**
 * The reader's compact context, read ONLY from the built headline (native
 * `compactScore` + `compactHeader`): away first, each team's short name else
 * its name; both runs slots' printed text only when the matrix is this phase's
 * and BOTH are values (else no pair — never a 0, a half pair or the event row);
 * then the state words. No new formatting.
 */
function runReaderContext(phase: HockeyJourneyPhase, headline: HockeyJourneyHeadline): MlbRunReaderContext {
  const { matrix } = headline;
  const column = matrix.phase === phase ? RUNS_COLUMN[phase] : undefined;
  const runsOf = (side: "home" | "away") =>
    column === undefined ? null : (matrix.rows.find((row) => row.side === side)?.values[column] ?? null);
  const away = runsOf("away");
  const home = runsOf("home");
  return {
    away: headline.away.short ?? headline.away.name,
    home: headline.home.short ?? headline.home.name,
    score: away?.kind === "value" && home?.kind === "value" ? { away: away.text, home: home.text } : null,
    state: headline.state,
  };
}

/** The slot's whole state: the scope, the chosen option key, and the reader's open / could-not-open flags. */
interface RunSlotState {
  scope: string;
  key: string | null;
  open: boolean;
  unavailable: boolean;
}
const freshRunSlot = (scope: string): RunSlotState => ({ scope, key: null, open: false, unavailable: false });

/**
 * The row's second item: holds the chosen run line for `scope` and draws the
 * card (with its "Open full card" entry) only while `totals` exists, plus the
 * full-size reader while open. Stays mounted when it draws nothing, so a
 * same-scope absence keeps the key (B1) and an open reader stays open (I2, see
 * header). State = scope + key + open + unavailable; no model is held.
 */
function MlbRunTotalsSlot({
  totals,
  scope,
  colors,
  context,
  anchor,
}: {
  totals: MlbRunTotalsInput | null;
  scope: string;
  colors: MlbRunTotalsColors;
  context: MlbRunReaderContext;
  /** The page's persistent, programmatically focusable local anchor (the history row). */
  anchor: RefObject<HTMLElement>;
}) {
  const [slot, setSlot] = useState<RunSlotState>(() => freshRunSlot(scope));
  const entry = useRef<HTMLButtonElement>(null);
  // A new event or phase clears the choice and closes the reader while rendering, whether or not a card is drawn.
  if (slot.scope !== scope) setSlot(freshRunSlot(scope));
  const now = slot.scope === scope ? slot : freshRunSlot(scope);
  // ONE selection for both views: the page card and the reader read and move the same key.
  const selection: MlbRunTotalsSelection = {
    held: now.key,
    onSelect: (key) => setSlot((s) => (s.scope === scope ? { ...s, key } : s)),
  };
  // R-F3: the entry while connected and enabled, else the page's own anchor; null only once the page is gone.
  const returnTo = (): HTMLElement | null => {
    const own = entry.current;
    if (own?.isConnected && !own.disabled) return own;
    const local = anchor.current;
    return local?.isConnected ? local : null;
  };
  return (
    <>
      {totals && (
        <div data-mlb-row-item="runTotals" className="min-w-0 grow basis-[22.5rem]">
          <MlbRunTotalsCard totals={totals} scope={scope} colors={colors} selection={selection} />
          <div className="mt-3">
            <button
              ref={entry}
              type="button"
              disabled={now.open}
              aria-label={`${SOCCER_READER_WORDS.openCard}: ${MLB_RUN_READER_WORDS.title}`}
              onClick={() => setSlot((s) => ({ ...s, open: true, unavailable: false }))}
              data-mlb-run-reader-entry=""
              className="min-h-11 w-full rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand sm:w-auto"
            >
              {SOCCER_READER_WORDS.openCard}
            </button>
            {/* A live region that is always present, so the words are announced when they appear. */}
            <p role="status" className={now.unavailable ? "mt-2 text-sm text-text-secondary" : undefined} data-mlb-run-reader-status="">
              {now.unavailable ? SOCCER_READER_WORDS.fullSizeUnavailable : null}
            </p>
          </div>
        </div>
      )}
      {/* While open, even through a same-scope pass with no input: the reader then says only its absence words. */}
      {now.open && (
        <MlbRunTotalsReader
          totals={totals}
          scope={scope}
          colors={colors}
          selection={selection}
          context={context}
          onClose={() => setSlot((s) => ({ ...s, open: false }))}
          onUnavailable={() => setSlot((s) => ({ ...s, open: false, unavailable: true }))}
          returnTo={returnTo}
        />
      )}
    </>
  );
}

export default function MlbGamePage({ model }: { model: MlbGameModel }) {
  // Before any return: the history row is the run-total reader's persistent local focus anchor (R-F3).
  const historyRow = useRef<HTMLDivElement>(null);
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
  // The run-total card only for an input that agrees with this page's phase (the builder already agrees).
  const runTotals = runTotalsForPhase(model.phase, model.runTotals);

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

      {/* D4: the history, then this phase's run-total card; side by side while both bases fit (see header).
          The row is also the reader's named local focus anchor (tabIndex -1: focusable by script, never a Tab stop). */}
      <div
        ref={historyRow}
        tabIndex={-1}
        role="group"
        aria-label={MLB_HISTORY_ROW_LABEL}
        data-mlb-history-row=""
        className="flex flex-wrap gap-6 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
      >
        <div data-mlb-row-item="history" className="min-w-0 grow basis-[28.75rem]">
          <HockeyJourneyHistoryChart key={model.scope} history={history} colors={lineColors} />
        </div>
        <MlbRunTotalsSlot
          totals={runTotals}
          scope={model.scope}
          colors={lineColors}
          context={runReaderContext(model.phase, headline)}
          anchor={historyRow}
        />
      </div>

      <HockeyJourneyAllProps key={model.originals.scope} originals={model.originals} entryLabel={model.allPropsLabel} />
    </section>
  );
}
