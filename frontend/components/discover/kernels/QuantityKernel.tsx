/**
 * QuantityKernel — one question, many thresholds (the ladder-strip crop).
 *
 * Design source: "Discover Card System" handoff (2026-07-15), card `1d`
 * ("compact ladder" — the owner's pick over the `1c` heat strip), finalized in
 * the `2f` mixed-feed chrome. The shape is `quantity` → kernel `ladder-strip`
 * (see lib/marketShape.ts). This is the CARD-SIZE CROP of the shared
 * `QuantityGroup` primitive (which owns the detail-page zoom): a thin 4px
 * row-per-threshold ladder that reads a value's distribution at a glance, plus
 * the date-bucket "by when?" variant (`wideLabels`) that the old grid rendered
 * broken (the "Putin out by…?" card).
 *
 * Rung data reuses `QuantityRung` from QuantityGroup so the card crop and the
 * detail-page ladder share one contract. Settled state trades the bars for a
 * Hit/Miss reading with the landed rung highlighted; the grade chip sits in the
 * header (KernelCard handles the chrome).
 */

import { KernelCard, type KernelState, type KernelGrade } from "./KernelCard";
import type { AngleValue } from "./AngleBadge";
import type { QuantityRung } from "../../QuantityGroup";

/** A settled rung: the threshold and whether it was Hit or Missed. */
export interface QuantitySettledRung {
  /** Row label ("5+", "Sep '26"). */
  label: string;
  /** True when the threshold was met. */
  hit: boolean;
  /** Optional detail on the landed rung ("6" — the actual value). */
  detail?: string;
  /** The rung the value actually landed on (bold/highlighted). */
  landed?: boolean;
}

export interface QuantityKernelProps {
  state: KernelState;
  /** The continuous question ("Aaron Judge home runs?"). */
  title: string;
  categorySlug: string;
  categoryLabel: string;
  categoryEmoji: string;
  /** Ladder rungs (upcoming/live). Sorted ascending by `value` when present. */
  rungs?: QuantityRung[];
  /** Header-left subtitle ("Season total", "By when · cumulative"). */
  stateLabel?: string;
  liveLabel?: string;
  timestamp?: string;
  angle?: AngleValue | null;
  grade?: KernelGrade | null;
  /** Cap the rungs shown (default 4 — the design's card crop). */
  maxRungs?: number;
  /** Date/time-bucket variant: a roomier label track for "Sep '26"-style labels. */
  wideLabels?: boolean;
  /** Settled: the Hit/Miss reading. */
  settledRungs?: QuantitySettledRung[];
}

function fmtPct(p: number | null): string {
  return p == null ? "—" : `${Math.round(p * 100)}%`;
}

/** Probability → prob-label emphasis (graphite / slate / silver by band). */
function probClass(p: number | null): string {
  if (p == null) return "font-semibold text-text-muted";
  if (p >= 0.5) return "font-bold text-text-primary";
  if (p >= 0.2) return "font-semibold text-text-secondary";
  return "font-semibold text-text-muted";
}

function LadderRow({ rung, wideLabels }: { rung: QuantityRung; wideLabels?: boolean }) {
  const p = rung.probability;
  const width = Math.max(2, Math.round((p ?? 0) * 100));
  // Fill opacity encodes probability (design: emerald fades with belief), floored
  // so a low rung is still visible.
  const opacity = Math.max(0.3, Math.min(1, p ?? 0));
  return (
    <div className="flex items-center gap-2">
      <span
        className={[
          "shrink-0 font-mono text-[11px] font-semibold text-text-secondary",
          wideLabels ? "w-[52px]" : "w-[34px]",
        ].join(" ")}
      >
        {rung.label}
      </span>
      <span className="h-[4px] flex-1 overflow-hidden rounded-full bg-surface-border">
        <span
          className="block h-full rounded-full bg-accent-brand"
          style={{ width: `${width}%`, opacity }}
        />
      </span>
      <span className={`w-9 shrink-0 text-right font-mono text-[13px] tabular-nums ${probClass(p)}`}>
        {fmtPct(p)}
      </span>
    </div>
  );
}

export function QuantityKernel(props: QuantityKernelProps) {
  const { state, title, rungs, settledRungs, wideLabels, maxRungs = 4 } = props;
  const settled = state === "settled";

  let ordered = rungs ?? [];
  ordered = [...ordered]
    .sort((a, b) => (a.value ?? Number.NEGATIVE_INFINITY) - (b.value ?? Number.NEGATIVE_INFINITY))
    .slice(0, maxRungs);

  return (
    <KernelCard
      state={state}
      stateLabel={settled ? props.stateLabel ?? "Resolved" : props.stateLabel}
      liveLabel={props.liveLabel}
      angle={props.angle}
      grade={props.grade}
      categoryEmoji={props.categoryEmoji}
      categoryLabel={props.categoryLabel}
      timestamp={props.timestamp}
      ariaLabel={title}
    >
      <div className={`text-[15px] font-semibold leading-snug ${settled ? "text-text-secondary" : "text-text-primary"}`}>
        {title}
      </div>

      {settled ? (
        <div className="flex flex-col gap-1">
          {(settledRungs ?? []).map((rung, i) => (
            <div
              key={`${rung.label}-${i}`}
              className={[
                "flex items-center gap-2 rounded-md px-2 py-1 -mx-2",
                rung.landed ? "bg-surface-elevated" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "shrink-0 font-mono text-[11px] font-semibold",
                  wideLabels ? "w-[52px]" : "w-[34px]",
                  rung.landed ? "text-text-primary" : "text-text-muted",
                ].join(" ")}
              >
                {rung.label}
              </span>
              <span
                className={`flex-1 text-[12px] font-semibold ${rung.hit ? "text-accent-brand" : "text-text-muted"}`}
              >
                {rung.hit ? "Hit" : "Miss"}
                {rung.detail && <span className="text-text-secondary"> · {rung.detail}</span>}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {ordered.map((rung) => (
            <LadderRow key={rung.key} rung={rung} wideLabels={wideLabels} />
          ))}
        </div>
      )}
    </KernelCard>
  );
}
