import { PARTIAL_HISTORY_CAPTION } from "@/lib/historyRange";

/** #683 — the one caption a partial full read earns (`servedPartialHistory`).
 *  One component so the plot, the too-little-to-draw state and each caller's
 *  own empty state print the same words with the same probe id. */
export function PartialHistoryCaption() {
  return (
    <p className="text-xs text-text-muted" data-testid="futures-chart-history-partial">
      {PARTIAL_HISTORY_CAPTION}
    </p>
  );
}
