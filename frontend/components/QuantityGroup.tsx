"use client";

/**
 * QuantityGroup — the Quantity kernel: one question, many lines, heat-strip.
 *
 * Queue L2-118 Phase 1, from the Claude Design "Props Reorg / Futures Detail"
 * spec (§03 Grouped markets — "A threshold ladder … the Discover heat-strip,
 * expanded with per-rung history").
 *
 * A "≥ N" market is really ONE continuous question. The legacy behavior stacked
 * it as N separate yes/no cards (a grid) and hid the shape. The ladder restores
 * it: every rung is cumulative, the heat reads top-down, and an optional
 * distribution strip shows where the value actually lands. Each rung carries a
 * chevron — a lens, never a buy button; tapping it re-scopes the history chart
 * (wired in Phase 2 via `onRungSelect`).
 *
 * This is the SHARED Quantity component — the same primitive covers MLB hit
 * props, RT scores, CPI ladders, and temperature buckets, at both detail-page
 * zoom (default) and Discover glance zoom (`compact`). It renders on the shape
 * field (`market_type === "quantity"`); see `lib/marketShape.ts`.
 *
 * Heat: uses the tokenized `probabilityHeat()` scale L2-117 cleaned — accent
 * tokens only, no raw Tailwind palette (CLAUDE.md light-mode rule).
 */

import { probabilityHeat } from "@/lib/probabilityColors";

export interface QuantityRung {
  /** Stable key (outcome id or the threshold string). */
  key: string | number;
  /** Row label, e.g. "≥ 80" or "$90K+". Pre-formatted by the caller. */
  label: string;
  /** Cumulative probability for this rung (0–1), or null when unknown. */
  probability: number | null;
  /** The reference line (e.g. the Certified Fresh ≥ 80 rung) — tinted + accented. */
  highlighted?: boolean;
  /** Numeric value used for ascending sort when `sort` is on. */
  value?: number;
}

/** A single bar in the "where it lands" distribution heat-strip. */
export interface QuantityDistributionBin {
  label: string;
  /** Probability mass in this bin (0–1). Bars are scaled to the max mass. */
  mass: number;
  /** Whether this is the modal / highlighted bin. */
  highlighted?: boolean;
}

interface QuantityGroupProps {
  /** Group title (e.g. the market stem). Omitted → no title row. */
  title?: string;
  /** The ladder rungs. */
  rungs: QuantityRung[];
  /** Header hint on the right (default depends on interactivity). */
  hint?: string;
  /** Footer legend describing the highlighted line, e.g. "≥ 80 is Certified Fresh". */
  lineLabel?: string;
  /** Optional distribution strip — "where it lands · probability mass". */
  distribution?: QuantityDistributionBin[];
  /** Phase-2 seam: tap a rung to re-scope history. Renders a chevron when set. */
  onRungSelect?: (rung: QuantityRung) => void;
  /** Sort rungs ascending by `value` (design shows ≥60 → ≥95 top-to-bottom). */
  sort?: boolean;
  /** Glance zoom for Discover cards: fewer rungs, tighter spacing, no distribution. */
  compact?: boolean;
  /**
   * Embed mode: drop the outer card chrome (border/shadow/padding) so the ladder
   * can render INSIDE an existing card that already owns the question context
   * (e.g. the Discover FuturesCard's title). Queue L2-119.
   */
  bare?: boolean;
  /**
   * Cap the number of rungs shown. Defaults to 4 in `compact`, unbounded
   * otherwise. Date-bucket cards use a slightly higher cap to keep the full
   * timeline legible without wrapping columns.
   */
  maxRungs?: number;
  /**
   * Wide-label mode for date/time buckets ("2029 or later") that don't fit the
   * fixed numeric-threshold label column. The "by WHEN" variant of the kernel —
   * same ladder, roomier label track. Queue L2-119.
   */
  wideLabels?: boolean;
}

function pct(p: number | null): string {
  return p == null ? "—" : `${Math.round(p * 100)}%`;
}

export default function QuantityGroup({
  title,
  rungs,
  hint,
  lineLabel,
  distribution,
  onRungSelect,
  sort = true,
  compact = false,
  bare = false,
  maxRungs,
  wideLabels = false,
}: QuantityGroupProps) {
  if (!rungs || rungs.length === 0) return null;

  let ordered = rungs;
  if (sort) {
    ordered = [...rungs].sort((a, b) => {
      const av = a.value ?? Number.NEGATIVE_INFINITY;
      const bv = b.value ?? Number.NEGATIVE_INFINITY;
      return av - bv;
    });
  }
  const cap = maxRungs ?? (compact ? 4 : undefined);
  if (cap != null) ordered = ordered.slice(0, cap);

  const interactive = typeof onRungSelect === "function";
  const headerHint = hint ?? (interactive ? "tap a rung for its history" : undefined);

  const inner = (
    <>
      {(title || headerHint) && (
        <div className="flex items-center gap-2 pb-2.5 mb-1.5 border-b border-surface-elevated">
          {title && (
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {title}
            </span>
          )}
          {headerHint && (
            <span className="ml-auto text-[11px] text-text-muted">{headerHint}</span>
          )}
        </div>
      )}

      <div className="flex flex-col gap-0.5">
        {ordered.map((rung) => {
          const heat = probabilityHeat(rung.probability);
          const width = Math.max(2, Math.round((rung.probability ?? 0) * 100));
          const RowTag = interactive ? "button" : "div";
          return (
            <RowTag
              key={rung.key}
              type={interactive ? "button" : undefined}
              onClick={interactive ? () => onRungSelect!(rung) : undefined}
              className={[
                "flex items-center gap-3 w-full text-left",
                compact ? "py-1" : "py-1.5",
                rung.highlighted
                  ? "px-2 -mx-2 rounded-lg bg-accent-brand/[0.06]"
                  : "",
                interactive ? "transition-colors hover:bg-surface-elevated/60 rounded-lg" : "",
              ].join(" ")}
              aria-label={`${rung.label}: ${pct(rung.probability)}`}
            >
              <span
                className={[
                  wideLabels
                    ? "shrink-0 max-w-[45%] text-[12px] font-semibold leading-tight"
                    : "w-11 shrink-0 font-mono text-[13px] font-bold tabular-nums",
                  rung.highlighted ? "text-accent-brand" : "text-text-primary",
                ].join(" ")}
              >
                {rung.label}
              </span>
              <span className="flex-1 h-[18px] rounded-md bg-surface-elevated overflow-hidden">
                <span
                  className={`block h-full rounded-md ${heat.bar}`}
                  style={{ width: `${width}%` }}
                />
              </span>
              <span
                className={[
                  "w-10 shrink-0 text-right font-mono text-[13px] font-bold tabular-nums",
                  rung.highlighted ? "text-accent-brand" : "text-text-primary",
                ].join(" ")}
              >
                {pct(rung.probability)}
              </span>
              {interactive && (
                <span className="shrink-0 text-text-muted text-[15px] leading-none">›</span>
              )}
            </RowTag>
          );
        })}
      </div>

      {lineLabel && (
        <div className="flex items-center gap-1.5 pt-2 mt-1.5 border-t border-surface-elevated">
          <span className="w-2 h-2 rounded-[2px] bg-accent-brand shrink-0" />
          <span className="text-[11px] text-text-muted">{lineLabel}</span>
        </div>
      )}

      {!compact && distribution && distribution.length > 0 && (
        <div className="mt-3 pt-3 border-t border-surface-elevated">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-2.5">
            Where it lands · probability mass
          </div>
          <QuantityDistribution bins={distribution} />
        </div>
      )}
    </>
  );

  if (bare) return inner;

  return (
    <div className="bg-surface-card rounded-card shadow-card border border-surface-border p-4">
      {inner}
    </div>
  );
}

function QuantityDistribution({ bins }: { bins: QuantityDistributionBin[] }) {
  const maxMass = Math.max(...bins.map((b) => b.mass), 0.0001);
  return (
    <>
      <div className="flex gap-[3px] items-end h-16">
        {bins.map((b, i) => {
          const h = Math.max(4, Math.round((b.mass / maxMass) * 100));
          return (
            <div key={`${b.label}-${i}`} className="flex-1 flex items-end h-full">
              <div
                className={[
                  "w-full rounded-t",
                  b.highlighted ? "bg-accent-brand" : "bg-accent-brand/40",
                ].join(" ")}
                style={{ height: `${h}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-[3px] mt-1.5 font-mono text-[9px] text-text-muted text-center">
        {bins.map((b, i) => (
          <span
            key={`lbl-${b.label}-${i}`}
            className={`flex-1 ${b.highlighted ? "text-accent-brand font-bold" : ""}`}
          >
            {b.label}
          </span>
        ))}
      </div>
    </>
  );
}

/**
 * Build ladder rungs from futures threshold-group outcomes (the futures-detail
 * `threshold_groups` payload shape). Formats "≥ N unit" labels, sorts ascending,
 * and marks the top rung by probability as the reference line when none is
 * explicitly flagged.
 */
export function buildThresholdRungs(
  outcomes: {
    outcome_id: number;
    name: string;
    probability: number | null;
    threshold_value: number;
    threshold_unit?: string;
    threshold_direction?: string;
  }[],
): QuantityRung[] {
  return outcomes.map((o) => ({
    key: o.outcome_id,
    label: formatThresholdLabel(o.threshold_value, o.threshold_unit, o.threshold_direction),
    probability: o.probability,
    value: o.threshold_value,
  }));
}

function formatThresholdLabel(
  value: number,
  unit?: string,
  direction?: string,
): string {
  const u = unit ?? "";
  const arrow = direction === "under" || direction === "below" ? "≤" : "≥";
  let num: string;
  if (u.includes("$")) {
    if (value >= 1_000_000) num = `$${(value / 1_000_000).toFixed(1)}M`;
    else if (value >= 1_000) num = `$${(value / 1_000).toFixed(0)}K`;
    else num = `$${value}`;
  } else {
    num = `${value}${u && !u.includes("$") ? u : ""}`;
  }
  return `${arrow} ${num}`;
}
