import { PriceAgeMark } from "@/components/event/PriceAgeMark";
import type { RoundupRowModel } from "@/lib/discover/roundupCard";

/**
 * #10357 — one round-up row: the number on the left with a small percent sign,
 * the label on the right, and a blue bar under every label. A NEW part, built
 * to Fable's R4 reference; not the grouped-card rows.
 *
 * R4 measurements: a 3.1rem number column, 12 gap, label column. Number mono
 * 20px/1.15/700/−0.03em right-aligned; % at 0.6em/500 in ink3, 1 right of the
 * digits. Label 15px/1.3 in ink, wraps, never truncated. Bar 7 below the label,
 * 6 tall, radius 3, on the track; fill = probability share, never under 3px,
 * in --series-1 (blue: green stays for a contest's leader and for "Won").
 *
 * `nowMs` is the card's one clock, passed down so the row's age mark cannot
 * disagree with the model that decided the row was old.
 */
export function RoundupRow({ row, nowMs }: { row: RoundupRowModel; nowMs: number }) {
  return (
    <div
      className="grid grid-cols-[3.1rem_minmax(0,1fr)] items-start gap-x-[12px]"
      data-testid="roundup-row"
      data-market-id={row.marketId}
    >
      <span className="text-right font-mono text-[20px] font-bold leading-[1.15] tracking-[-0.03em] text-text-primary tabular-nums">
        {row.marker}
        {row.digits}
        <small className="ml-px text-[0.6em] font-medium tracking-normal text-text-secondary">%</small>
      </span>
      <span className="flex min-w-0 items-baseline justify-between gap-2">
        <span className="min-w-0 break-words text-[15px] leading-[1.3] text-text-primary" data-testid="roundup-row-label">
          {row.label}
        </span>
        {row.rowMark ? <PriceAgeMark observedAt={row.observedAt} nowMs={nowMs} cadence={row.cadence} scope="row" /> : null}
      </span>
      <span
        className="col-start-2 mt-[7px] block h-[6px] overflow-hidden rounded-[3px] bg-surface-elevated"
        aria-hidden="true"
      >
        <i
          className="block h-full min-w-[3px] rounded-r-[3px] bg-[var(--series-1)]"
          style={{ width: `${Math.max(0, Math.min(1, row.fill)) * 100}%` }}
          data-testid="roundup-row-bar"
        />
      </span>
      {row.secondary ? (
        <div
          className="col-start-2 mt-1.5 space-y-1 text-[12px] leading-none text-text-secondary"
          data-testid="roundup-row-secondary"
        >
          <span
            className="block h-[5px] w-full overflow-hidden rounded-[3px] bg-surface-elevated"
            aria-hidden="true"
          >
            <i
              className="block h-full min-w-[3px] rounded-r-[3px] bg-text-muted"
              style={{ width: `${Math.max(0, Math.min(1, row.secondary.fill)) * 100}%` }}
              data-testid="roundup-row-secondary-bar"
            />
          </span>
          <span className="block font-mono tabular-nums" data-testid="roundup-row-secondary-value">
            {row.secondary.secondaryLabel} {row.secondary.marker}
            {row.secondary.digits}% · {row.secondary.primaryLabel} {row.marker}
            {row.digits}%
          </span>
        </div>
      ) : null}
    </div>
  );
}
