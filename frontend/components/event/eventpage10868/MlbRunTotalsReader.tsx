"use client";

/**
 * #10868 — THE MLB RUN-TOTAL CARD, FULL-SIZE READER (web), increment I1:
 * an independent presentation. Nothing mounts it yet; the page binding is a
 * later, separately admitted increment.
 *
 * PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a baseball fan can explore the
 * same run-total card at full size without losing the selected line or
 * milestone, then return to the same place.
 *
 * NATIVE: the #10868 baseball host's one reader sheet
 * (`BaseballEventPageHostAdapter10868`), rebuilt from live values on every
 * pass, showing `BaseballEventPagePresentation10868.reader(card)`: the compact
 * heading, then the same leaf with `expanded: true`, only while the card shows.
 * Not the held-snapshot `NFLCardReader9483`: nothing is held here.
 *
 * THE SHELL is the EXISTING `SoccerMatchReader`, imported unchanged: one local
 * native `<dialog>` opened with `showModal()` — a true modal or nothing; the
 * page's scroll held while open; Close, Escape (the dialog's `cancel`) and the
 * browser's own close each reach `onClose` exactly once; a close the reader
 * asked for restores the page position and focuses `returnTo()` with
 * `preventScroll`; a close the caller made (a new event or phase) restores no
 * scroll and focuses only if focus was lost; when `showModal` is missing or
 * throws, nothing is shown and `onUnavailable` is called. This file adds no
 * modal, focus or scroll code, and does not use `soccerReaderEntry`. Accepted
 * warts: the dialog carries the shell's soccer-named hooks
 * (`data-soccer-reader="story"`, `data-soccer-reader-body`) and says "Close"
 * where native says "Done".
 *
 * CONTENT: with an input, the SAME `MlbRunTotalsCard` the page draws, given
 * the caller's SAME controlled selection (B1: `held` key + one `onSelect` per
 * tap) and asking for `layout="expanded"` (only the final plot gains height;
 * the milestones leaf is unchanged). Nothing is decoded, formatted, graded,
 * snapshotted or cached here: every render draws exactly what the caller
 * passes now, so a same-scope refresh re-reads in place.
 *
 * SINGLE CARD: the title is native's "Run totals"; no Previous / Next and no
 * "1 of 1". No Details control (run-line and milestone Details stay owed), no
 * owner pass and no ids derived from the input.
 *
 * WHOLE INPUT LOST (Design R-F1): with `totals` null the dialog stays open
 * with only the title, Close and native baseball's `storyUnavailable` words:
 * no context, no card, no probability and no count. The caller keeps its key,
 * so when the exact input returns the card opens on it again.
 *
 * COMPACT CONTEXT (native `compactHeader`): only the caller's strings, away
 * first — the two names, with the two score strings between them only when
 * BOTH are present, then the state words. It derives no score, parses no
 * scope, is not a heading and has no id; every part wraps. The type and view
 * live in the verdict-free `MlbReaderContext` (shared with the history
 * reader); the type is re-exported from this path unchanged.
 *
 * THE CALLER OWNS open/closed and the scope. It renders this only while open,
 * and closes it in the same render as a new event or phase (so no frame shows
 * the reader for the old phase) while clearing its key. `returnTo` (Design
 * R-F3) is the caller's surviving opener, else a programmatically focusable
 * local page anchor; null only when the owning page is gone. No routing,
 * subscription or scope parsing here.
 */

import type { MlbRunTotalsInput } from "@/lib/eventPage10868/mlbRunTotals";
import SoccerMatchReader from "./SoccerMatchReader";
import MlbRunTotalsCard, { type MlbRunTotalsColors, type MlbRunTotalsSelection } from "./MlbRunTotalsCard";
import { RunReaderContext, type MlbRunReaderContext } from "./MlbReaderContext";

// The compact context's type, still public from this path (its definition moved to `MlbReaderContext`).
export type { MlbRunReaderContext } from "./MlbReaderContext";

/** Native `BaseballPageInputAdapter10868.Words`, verbatim. */
export const MLB_RUN_READER_WORDS = {
  title: "Run totals",
  storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
} as const;

export default function MlbRunTotalsReader({
  totals,
  scope,
  colors,
  selection,
  context,
  onClose,
  onUnavailable,
  returnTo,
}: {
  /** The SAME phase-agreed input the page card draws, or null when it is gone. */
  totals: MlbRunTotalsInput | null;
  /** `mlb:<event>:<phase>`, as the caller holds it; passed to the card, never parsed. */
  scope: string;
  colors: MlbRunTotalsColors;
  /** The caller's controlled B1 selection, the same object the page card is given. */
  selection: MlbRunTotalsSelection;
  context: MlbRunReaderContext;
  /** The caller's controlled close: it stops rendering the reader. */
  onClose: () => void;
  /** The modal could not open: the caller stops rendering the reader and says so by its entry. */
  onUnavailable: () => void;
  /** Where focus returns, read after the caller's close has committed (see R-F3). */
  returnTo: () => HTMLElement | null;
}) {
  return (
    <SoccerMatchReader
      kind="story"
      title={MLB_RUN_READER_WORDS.title}
      context={totals ? <RunReaderContext context={context} /> : null}
      onClose={onClose}
      onUnavailable={onUnavailable}
      returnTo={returnTo}
    >
      {totals ? (
        <MlbRunTotalsCard totals={totals} scope={scope} colors={colors} selection={selection} layout="expanded" />
      ) : (
        <p className="rounded-md bg-surface-deep p-2 text-sm font-semibold text-text-primary" data-mlb-run-reader-unavailable="">
          {MLB_RUN_READER_WORDS.storyUnavailable}
        </p>
      )}
    </SoccerMatchReader>
  );
}
