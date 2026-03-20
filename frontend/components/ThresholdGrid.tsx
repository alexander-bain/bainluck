"use client";

/**
 * ThresholdGrid — displays a grid of threshold variant outcomes.
 *
 * Used when a market group contains outcomes that differ only by a numeric
 * threshold (e.g., "Bitcoin > $80K", "Bitcoin > $90K", "Bitcoin > $100K").
 * Renders as a horizontal grid of cards sorted by threshold value, with
 * probability bars and color coding.
 */

import { motion } from "framer-motion";
import { staggerContainer, staggerItem } from "@/lib/animations";

interface ThresholdOutcome {
  outcome_id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_unit: string;
  threshold_direction: string;
  source: string;
}

interface ThresholdGridProps {
  /** Group of threshold variants sharing a common stem */
  outcomes: ThresholdOutcome[];
  /** Optional title for the group (e.g., "Bitcoin Price Targets") */
  title?: string;
  /** When set, the card matching this threshold_value gets a highlighted ring */
  highlightedValue?: number;
}

function formatThreshold(value: number, unit: string): string {
  if (unit.includes("$")) {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
    return `$${value.toFixed(0)}`;
  }
  if (Number.isInteger(value)) return `${value}${unit}`;
  return `${value}${unit}`;
}

function probabilityColor(prob: number): string {
  if (prob >= 0.7) return "text-green-400";
  if (prob >= 0.4) return "text-amber-400";
  if (prob >= 0.15) return "text-orange-400";
  return "text-red-400";
}

function probabilityBg(prob: number): string {
  if (prob >= 0.7) return "bg-green-500/15";
  if (prob >= 0.4) return "bg-amber-500/15";
  if (prob >= 0.15) return "bg-orange-500/15";
  return "bg-red-500/15";
}

export default function ThresholdGrid({ outcomes, title, highlightedValue }: ThresholdGridProps) {
  if (!outcomes || outcomes.length === 0) return null;

  return (
    <div className="space-y-3">
      {title && (
        <h3 className="text-sm font-medium text-[var(--text-secondary)]">
          {title}
        </h3>
      )}
      <motion.div
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {outcomes.map((o) => {
          const prob = o.probability ?? 0;
          const pct = (prob * 100).toFixed(0);
          const isHighlighted = highlightedValue !== undefined && o.threshold_value === highlightedValue;

          return (
            <motion.div
              key={o.outcome_id}
              variants={staggerItem}
              className={`
                rounded-lg border p-3
                hover:border-[var(--accent-brand)]/30
                transition-colors duration-150
                ${isHighlighted
                  ? "border-[var(--accent-brand)] ring-1 ring-[var(--accent-brand)]/30 bg-[var(--accent-brand)]/5"
                  : "border-[var(--surface-border)] bg-[var(--surface-card)]"
                }
              `}
            >
              {/* Threshold label */}
              <div className="text-xs text-[var(--text-muted)] mb-1">
                {o.threshold_direction === "below" ? "Under" : "Over"}
              </div>
              <div className="text-base font-mono font-semibold text-[var(--text-primary)] mb-2">
                {formatThreshold(o.threshold_value, o.threshold_unit)}
              </div>

              {/* Probability */}
              <div className={`text-lg font-mono font-bold ${probabilityColor(prob)}`}>
                {pct}%
              </div>

              {/* Mini bar */}
              <div className="mt-1.5 h-1 rounded-full bg-[var(--surface-elevated)] overflow-hidden">
                <div
                  className={`h-full rounded-full ${probabilityBg(prob)} transition-all duration-300`}
                  style={{ width: `${Math.max(2, prob * 100)}%` }}
                />
              </div>

              {/* Source */}
              <div className="mt-1.5 text-[10px] text-[var(--text-muted)]">
                {o.source === "polymarket" ? "Polymarket" : o.source === "kalshi" ? "Kalshi" : o.source}
              </div>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
}
