/**
 * #10868 — the MLB full-size readers' shared COMPACT CONTEXT (web): the type
 * and the stateless view both readers draw at the top of their body — the run
 * totals reader (`MlbRunTotalsReader`, I1) and the history reader
 * (`MlbHistoryReader`, Full chart). Moved here verbatim from
 * `MlbRunTotalsReader.tsx` (markup, words and the `data-mlb-run-reader-*`
 * hooks unchanged; the run-named hooks are an accepted wart), so the history
 * reader can share it without importing the run reader.
 *
 * Native `compactHeader`: only the caller's strings, away first — the two
 * names, with the two score strings between them only when BOTH are present,
 * then the state words. It derives no score, parses no scope, is not a heading
 * and has no id; every part wraps.
 *
 * VERDICT-FREE ON PURPOSE: this module imports nothing, holds no state and no
 * hook, and prints only the strings it is given, so it stays outside the
 * settled-vocabulary census's `lib/propGrade` closure.
 */

/** The compact context, as the caller already holds it: display strings only. */
export interface MlbRunReaderContext {
  away: string;
  home: string;
  /** Both runs figures exactly as the page prints them; null when the page shows no pair. */
  score: { away: string; home: string } | null;
  state: string;
}

/** Away first: the names (and the score only when both strings exist) on one wrapping line, then the state. */
export function RunReaderContext({ context }: { context: MlbRunReaderContext }) {
  const score = context.score && context.score.away !== "" && context.score.home !== "" ? context.score : null;
  return (
    <div className="space-y-1" data-mlb-run-reader-context="">
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-base font-semibold">
        <span className="min-w-0 break-words" data-mlb-run-reader-team="away">
          {context.away}
        </span>
        {score ? (
          <span className="whitespace-nowrap tabular-nums" data-mlb-run-reader-score="">
            {`${score.away} – ${score.home}`}
          </span>
        ) : (
          <span className="text-text-secondary">
            <span aria-hidden="true">·</span>
            <span className="sr-only">,</span>
          </span>
        )}
        <span className="min-w-0 break-words" data-mlb-run-reader-team="home">
          {context.home}
        </span>
      </p>
      {context.state && (
        <p className="break-words text-sm text-text-secondary" data-mlb-run-reader-state="">
          {context.state}
        </p>
      )}
    </div>
  );
}
