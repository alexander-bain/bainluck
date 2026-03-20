"use client";

/**
 * ThresholdSparkline — A compact inline visualization for threshold groups.
 *
 * Displays a horizontal sparkline where each dot represents a threshold value,
 * with position and color indicating probability. Perfect for showing
 * distributions like "Bitcoin > $80K, $90K, $100K" or "Player: 20+, 25+, 30+ points"
 * in a single glanceable row.
 *
 * Visual design:
 * - Horizontal bar with dots positioned by threshold value
 * - Dot size proportional to probability (larger = more likely)
 * - Dot color indicates probability (green=high, amber=mid, red=low)
 * - Hoverable tooltip shows details
 */

import { motion, AnimatePresence } from "framer-motion";
import { useState, useMemo } from "react";
import { transitionFast } from "@/lib/animations";

interface ThresholdPoint {
  id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_unit?: string;
  threshold_direction?: string;
}

interface ThresholdSparklineProps {
  /** Array of threshold outcomes to display */
  points: ThresholdPoint[];
  /** Optional: Highlight a specific threshold value */
  highlightValue?: number;
  /** Height of the sparkline in pixels */
  height?: number;
  /** Show labels below key points */
  showLabels?: boolean;
  /** Callback when a point is clicked */
  onPointClick?: (point: ThresholdPoint) => void;
}

function formatThreshold(value: number, unit?: string): string {
  const u = unit || "";
  if (u.includes("$") || u === "") {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
    if (u.includes("$")) return `$${value.toFixed(0)}`;
  }
  if (Number.isInteger(value)) return `${value}${u}`;
  return `${value.toFixed(1)}${u}`;
}

function probabilityToColor(prob: number): string {
  if (prob >= 0.7) return "rgb(var(--color-status-live))"; // green
  if (prob >= 0.4) return "rgb(234, 179, 8)"; // amber
  if (prob >= 0.15) return "rgb(249, 115, 22)"; // orange
  return "rgb(239, 68, 68)"; // red
}

function probabilityToBgClass(prob: number): string {
  if (prob >= 0.7) return "bg-green-500";
  if (prob >= 0.4) return "bg-amber-500";
  if (prob >= 0.15) return "bg-orange-500";
  return "bg-red-500";
}

export default function ThresholdSparkline({
  points,
  highlightValue,
  height = 48,
  showLabels = true,
  onPointClick,
}: ThresholdSparklineProps) {
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  // Sort by threshold value
  const sortedPoints = useMemo(
    () => [...points].sort((a, b) => a.threshold_value - b.threshold_value),
    [points]
  );

  // Calculate min/max for positioning
  const { minVal, maxVal, range } = useMemo(() => {
    const values = sortedPoints.map((p) => p.threshold_value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { minVal: min, maxVal: max, range: max - min || 1 };
  }, [sortedPoints]);

  // Which points get labels (first, last, and optionally highlighted)
  const labeledIndices = useMemo(() => {
    const indices = new Set<number>([0, sortedPoints.length - 1]);
    if (highlightValue !== undefined) {
      const idx = sortedPoints.findIndex((p) => p.threshold_value === highlightValue);
      if (idx !== -1) indices.add(idx);
    }
    return indices;
  }, [sortedPoints, highlightValue]);

  if (points.length === 0) return null;

  return (
    <div className="relative" style={{ height: showLabels ? height + 24 : height }}>
      {/* Track */}
      <div
        className="absolute left-4 right-4 top-1/2 -translate-y-1/2 h-1 bg-[var(--surface-elevated)] rounded-full"
        style={{ top: height / 2 }}
      />

      {/* Probability fill gradient (from leftmost to rightmost) */}
      <div
        className="absolute left-4 right-4 top-1/2 -translate-y-1/2 h-1 rounded-full overflow-hidden"
        style={{ top: height / 2 }}
      >
        <div
          className="h-full bg-gradient-to-r from-green-500/30 via-amber-500/20 to-red-500/30"
          style={{ width: "100%" }}
        />
      </div>

      {/* Points */}
      {sortedPoints.map((point, idx) => {
        const prob = point.probability ?? 0;
        const xPercent = range > 0 ? ((point.threshold_value - minVal) / range) * 100 : 50;
        const isHighlighted = highlightValue === point.threshold_value;
        const isHovered = hoveredId === point.id;
        const dotSize = 8 + prob * 12; // 8px to 20px based on probability

        return (
          <div
            key={point.id}
            className="absolute"
            style={{
              left: `calc(${xPercent}% * 0.875 + 4%)`, // Scale to 87.5% width + 4% padding
              top: height / 2,
              transform: "translate(-50%, -50%)",
            }}
          >
            {/* Dot */}
            <motion.button
              className={`
                rounded-full cursor-pointer
                transition-shadow duration-150
                ${isHighlighted ? "ring-2 ring-[var(--accent-brand)] ring-offset-2 ring-offset-[var(--surface-base)]" : ""}
                ${probabilityToBgClass(prob)}
              `}
              style={{
                width: dotSize,
                height: dotSize,
              }}
              whileHover={{ scale: 1.3 }}
              whileTap={{ scale: 0.95 }}
              onMouseEnter={() => setHoveredId(point.id)}
              onMouseLeave={() => setHoveredId(null)}
              onClick={() => onPointClick?.(point)}
              aria-label={`${formatThreshold(point.threshold_value, point.threshold_unit)}: ${(prob * 100).toFixed(0)}%`}
            />

            {/* Tooltip on hover */}
            <AnimatePresence>
              {isHovered && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  transition={transitionFast}
                  className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-20"
                >
                  <div className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-lg px-2.5 py-1.5 shadow-lg whitespace-nowrap">
                    <div className="text-xs font-mono font-semibold text-[var(--text-primary)]">
                      {formatThreshold(point.threshold_value, point.threshold_unit)}
                    </div>
                    <div
                      className="text-sm font-mono font-bold"
                      style={{ color: probabilityToColor(prob) }}
                    >
                      {(prob * 100).toFixed(0)}%
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Label below */}
            {showLabels && labeledIndices.has(idx) && (
              <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 whitespace-nowrap">
                <span className="text-[10px] font-mono text-[var(--text-muted)]">
                  {formatThreshold(point.threshold_value, point.threshold_unit)}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
