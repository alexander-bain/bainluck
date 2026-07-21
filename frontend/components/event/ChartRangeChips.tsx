"use client";

// Time-range chips for the probability-path charts (#L2-137 chart-excellence
// Phase 0). Presentational + pure so the chart-integrity guard test can render
// it without SWR/jsdom. The parent owns the selected state and the windowing.

import type { ChartRange, ChartRangeKey } from "@/lib/chartWindow";

interface ChartRangeChipsProps {
  ranges: ChartRange[];
  selected: ChartRangeKey;
  onSelect: (key: ChartRangeKey) => void;
  className?: string;
}

export default function ChartRangeChips({
  ranges,
  selected,
  onSelect,
  className,
}: ChartRangeChipsProps) {
  if (ranges.length <= 1) return null;
  return (
    <div
      className={`flex flex-wrap gap-1.5 ${className ?? ""}`}
      role="group"
      aria-label="Chart time range"
    >
      {ranges.map((r) => {
        const active = r.key === selected;
        return (
          <button
            key={r.key}
            type="button"
            onClick={() => onSelect(r.key)}
            aria-pressed={active}
            className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
              active
                ? "bg-accent-brand text-white"
                : "bg-surface-elevated text-text-secondary hover:text-text-primary hover:bg-surface-border"
            }`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}
