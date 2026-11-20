import React from "react";

export type QuietFillTone = "emerald" | "slate";

export interface QuietFillPercentBoxProps {
  /** Whole-point or fractional percentage in [0, 100]. Null, <= 0, or non-finite renders no fill. */
  percent: number | null | undefined;
  /** Visual tone: `"emerald"` (`bg-accent-brand/15`) for primary/win chances, `"slate"` (`bg-text-muted/20`) for stage-1/nomination chances. */
  tone?: QuietFillTone;
  /** Stretch across the full width of the parent slot (e.g. podium cards). */
  fullWidth?: boolean;
  /** Minimum/fixed width utility class (defaults to `"min-w-[3.5rem]"`). */
  widthClass?: string;
  /** Horizontal alignment inside the box (defaults to `"justify-end"`). */
  alignClass?: string;
  /** Extra classes on the outer pill box. */
  className?: string;
  /** Optional custom test id on the outer box. */
  testId?: string;
  children: React.ReactNode;
}

/**
 * #12714 — Quiet proportional fill behind grouped-card percentage boxes, matching iOS.
 *
 * A `94%` box is almost full (`94%`), a `36%` box is filled just past a third (`36%`),
 * and settled or unpriced labels never call this box with a positive percentage.
 * Uses light-mode design tokens only (`border-surface-border`, `bg-surface-elevated`,
 * `bg-accent-brand`, `bg-text-muted`).
 */
export function QuietFillPercentBox({
  percent,
  tone = "emerald",
  fullWidth = false,
  widthClass = "min-w-[3.5rem]",
  alignClass = "justify-end",
  className = "",
  testId = "quiet-fill-percent-box",
  children,
}: QuietFillPercentBoxProps) {
  const valid =
    typeof percent === "number" && Number.isFinite(percent) && percent > 0;
  const clamped = valid ? Math.min(100, Math.max(2, Math.round(percent))) : 0;
  const fillToneClass =
    tone === "slate" ? "bg-text-muted/20" : "bg-accent-brand/15";

  return (
    <span
      data-testid={testId}
      data-quiet-fill-pct={valid ? String(Math.round(percent)) : "0"}
      data-quiet-fill-tone={tone}
      className={`relative inline-flex items-center overflow-hidden rounded-md border border-surface-border/80 bg-surface-elevated/40 px-2 py-0.5 ${
        fullWidth ? "w-full" : widthClass
      } ${alignClass} ${className}`.trim()}
    >
      {valid && (
        <span
          aria-hidden="true"
          data-testid="quiet-fill-bar"
          className={`pointer-events-none absolute inset-y-0 left-0 ${fillToneClass}`}
          style={{ width: `${clamped}%` }}
        />
      )}
      <span className="relative z-10 inline-flex items-baseline gap-1">
        {children}
      </span>
    </span>
  );
}
