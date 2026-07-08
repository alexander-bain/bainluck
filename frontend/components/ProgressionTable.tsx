"use client";

/**
 * ProgressionTable — displays a table of outcomes progressing through
 * a sequence (tournament stages, election rounds, etc.).
 *
 * Shows outcomes sorted by threshold value or group position, with
 * probability, source, and optional status indicators.
 */

import { motion } from "framer-motion";
import { fadeIn } from "@/lib/animations";

interface ProgressionOutcome {
  id: number;
  name: string;
  probability: number | null;
  american_odds?: number | null;
  source: string;
  market_id: number;
}

interface ProgressionMarket {
  id: number;
  name: string;
  source: string;
  group_position: number | null;
  status: string;
  outcomes: ProgressionOutcome[];
}

interface ProgressionTableProps {
  /** Markets in the group, ordered by group_position */
  markets: ProgressionMarket[];
  /** Group title */
  title?: string;
}

// L2-52: source-name formatter + badge color removed — blend-only, no source
// attribution on progression rows.

export default function ProgressionTable({
  markets,
  title,
}: ProgressionTableProps) {
  if (!markets || markets.length === 0) return null;

  return (
    <motion.div
      variants={fadeIn}
      initial="hidden"
      animate="visible"
      className="space-y-3"
    >
      {title && (
        <h3 className="text-sm font-medium text-[var(--text-secondary)]">
          {title}
        </h3>
      )}

      <div className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-2 text-xs text-[var(--text-muted)] border-b border-[var(--surface-border)]">
          <div>Market</div>
          <div className="text-right">Top Outcome</div>
          {/* L2-52: Source column removed (blend-only). */}
        </div>

        {/* Rows */}
        {markets.map((market, idx) => {
          const topOutcome = market.outcomes[0];
          const prob = topOutcome?.probability ?? 0;
          const pct = (prob * 100).toFixed(0);

          return (
            <div
              key={market.id}
              className={`
                grid grid-cols-[1fr_auto_auto] gap-3 px-4 py-3
                ${idx < markets.length - 1 ? "border-b border-[var(--surface-border)]/50" : ""}
                hover:bg-[var(--surface-elevated)]/50
                transition-colors duration-150
              `}
            >
              {/* Market name */}
              <div>
                <div className="text-sm text-[var(--text-primary)] line-clamp-1">
                  {market.name}
                </div>
                {topOutcome && market.outcomes.length > 1 && (
                  <div className="text-xs text-[var(--text-muted)] mt-0.5">
                    {market.outcomes.length} outcomes
                  </div>
                )}
              </div>

              {/* Top outcome probability */}
              <div className="text-right">
                {topOutcome ? (
                  <div>
                    <div className="text-sm font-mono font-semibold text-[var(--text-primary)]">
                      {topOutcome.name}
                    </div>
                    <div className="text-xs font-mono text-[var(--text-secondary)]">
                      {pct}%
                    </div>
                  </div>
                ) : (
                  <span className="text-xs text-[var(--text-muted)]">—</span>
                )}
              </div>

              {/* L2-52: source badge removed (blend-only). */}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
