"use client";

/**
 * #10868 — THE MLB FULL CHART (web): the baseball page's win-probability
 * history at full size, an independent presentation. Nothing mounts it yet;
 * the page binding ("Full chart" entry) is a later, separately admitted
 * increment.
 *
 * PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a baseball fan can read the
 * probability journey at full size, with the same game context and honest
 * missing-history treatment.
 *
 * NATIVE: the #10868 baseball host's one reader sheet showing
 * `BaseballEventPagePresentation10868.reader(.history)`: the compact heading,
 * the matrix while the headline shows (its phase is the page's), then the
 * SAME history drawn with `layout: .expanded` and no expand control. Native's
 * reader keeps its owner's 230 pt plot; web's expanded plot is 360 px (the
 * accepted web soccer convention) — no native pixel parity is claimed.
 *
 * THE SHELL is the EXISTING `SoccerMatchReader`, imported unchanged, with
 * `kind="history"` and `history.title` as its title: a true modal or nothing;
 * the page's scroll held while open; Close, Escape (the dialog's `cancel`) and
 * the browser's own close reach `onClose` once; an asked close restores the
 * page position and focuses `returnTo()` with `preventScroll`; an owner close
 * restores no scroll and moves focus only if it was lost; a missing or
 * throwing `showModal` shows nothing and calls `onUnavailable`. This file adds
 * no modal, focus, scroll or navigation code and does not use
 * `soccerReaderEntry`. No Previous / Next, no position.
 *
 * BODY, from what the caller already owns (the page's away-first presentation
 * copies):
 *   - the compact context (`RunReaderContext`, the run reader's shared view,
 *     from the verdict-free `MlbReaderContext`): only the caller's strings;
 *   - the SAME headline matrix (`HockeyJourneyMatrix`, the page's props) only
 *     while `headline.matrix.phase` is `phase` — a matrix from another phase
 *     is never drawn;
 *   - the SAME history through `HockeyJourneyHistoryChart layout="expanded"`:
 *     every recorded point, run, gap, guide, label, key, caption, note and
 *     source word is the chart owner's; only the plot is taller. A missing or
 *     foreign history is the chart's own absence, and the reader stays open.
 * Nothing is reconstructed, interpolated, complemented, re-timed or
 * formatted here; no request, subscription, scrub, inspection, recorded
 * moment or Details destination exists (no owner implements one on either
 * platform). The chart's Details disclosure is per instance: opening it here
 * never opens the page's, and the reverse.
 *
 * CENSUS: it states no prop verdict and imports nothing that does (the shell,
 * the matrix, the chart, the types and `MlbReaderContext` all sit outside the
 * settled-vocabulary census's `lib/propGrade` closure), so it is not a census
 * surface. It never imports `MlbRunTotalsReader`.
 *
 * THE CALLER OWNS open/closed and the scope (it renders this only while open
 * and closes it in the same render as a new event or phase) and `returnTo`:
 * its surviving opener, else a programmatically focusable local page anchor;
 * null only when the owning page is gone.
 */

import type { HockeyJourneyHeadline, HockeyJourneyHistory, HockeyJourneyPhase } from "@/lib/eventPage10868/hockeyJourneyTypes";
import SoccerMatchReader from "./SoccerMatchReader";
import HockeyJourneyMatrix from "./HockeyJourneyMatrix";
import HockeyJourneyHistoryChart, { type HockeyJourneyLineColors } from "./HockeyJourneyHistoryChart";
import { RunReaderContext, type MlbRunReaderContext } from "./MlbReaderContext";

export default function MlbHistoryReader({
  headline,
  phase,
  history,
  colors,
  context,
  onClose,
  onUnavailable,
  returnTo,
}: {
  /** The page's own built headline (its away-first presentation copy). */
  headline: HockeyJourneyHeadline;
  /** The page's phase: the matrix is drawn only when the headline's matrix is this phase's. */
  phase: HockeyJourneyPhase;
  /** The page's own history model (its away-first presentation copy), drawn unchanged. */
  history: HockeyJourneyHistory;
  /** The page's line colours, the same the inline chart is given. */
  colors: HockeyJourneyLineColors;
  /** The compact context strings, the same the run reader is given. */
  context: MlbRunReaderContext;
  /** The caller's controlled close: it stops rendering the reader. */
  onClose: () => void;
  /** The modal could not open: the caller stops rendering the reader and says so by its entry. */
  onUnavailable: () => void;
  /** Where focus returns, read after the caller's close has committed. */
  returnTo: () => HTMLElement | null;
}) {
  return (
    <SoccerMatchReader
      kind="history"
      title={history.title}
      context={<RunReaderContext context={context} />}
      onClose={onClose}
      onUnavailable={onUnavailable}
      returnTo={returnTo}
    >
      {headline.matrix.phase === phase && <HockeyJourneyMatrix headline={headline} inlineProvenance compactColumns />}
      <HockeyJourneyHistoryChart history={history} colors={colors} layout="expanded" />
    </SoccerMatchReader>
  );
}
