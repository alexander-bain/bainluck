/**
 * ContainerKernel — a bundle (headliner market + bundle count + date).
 *
 * Design source: "Discover Card System" handoff (2026-07-15), card `1h`
 * ("headliner + count"), finalized in the `2f` mixed-feed chrome. The shape is
 * the roll-up of `container_member` markets into one card (see
 * lib/marketShape.ts): a tournament / card / ceremony surfaced as ONE inset
 * headliner market plus a "N markets" bundle-count pill — never a stacked list.
 *
 * Wears the unified KernelCard chrome (header = state + ONE angle, footer =
 * league + timestamp) with the Container-specific bundle-count pill in the
 * footer via `footerAccessory`. The title runs one step larger (16px) than the
 * other kernels — a container names an event, not a single question.
 *
 * Settled state resolves the headliner ("Scheffler won ✓") and the header grade
 * chip carries the user's bundle record ("3 of 4 calls right").
 */

import { KernelCard, type KernelState, type KernelGrade } from "./KernelCard";
import type { AngleValue } from "./AngleBadge";

export interface ContainerKernelProps {
  state: KernelState;
  /** The container / event name ("The Open Championship"). */
  title: string;
  /** Second line: venue+dates, or the live storyline ("Scheffler leads by 2 · −8 thru 54"). */
  subtitle?: string;
  categorySlug: string;
  categoryLabel: string;
  categoryEmoji: string;
  /** The inset headliner market's question ("Scheffler wins?"). */
  headlinerLabel: string;
  /** 0–1 probability of the headliner (upcoming/live). */
  headlinerProbability?: number | null;
  /** Headliner 24h/period movement in POINTS. */
  headlinerDeltaPoints?: number | null;
  /** Settled: the resolved headliner ("Scheffler won"). Replaces the probability. */
  headlinerResult?: string;
  /** Settled: whether the headliner resolved Yes/for-the-favorite (drives ✓/✗). */
  headlinerCorrect?: boolean;
  /** Bundle size ("12 markets"). */
  marketCount: number;
  /** Suffix on the count pill ("4 live", "settled"). */
  marketCountSuffix?: string;
  /** Header-left state copy ("Starts Thursday", "Ended"). */
  stateLabel?: string;
  liveLabel?: string;
  timestamp?: string;
  angle?: AngleValue | null;
  grade?: KernelGrade | null;
}

function fmtPct(p: number | null | undefined): string | null {
  if (p == null) return null;
  return `${Math.round(p * 100)}%`;
}

function fmtDelta(pts: number | null | undefined): { text: string; up: boolean } | null {
  if (pts == null || Math.abs(pts) < 0.1) return null;
  const up = pts >= 0;
  return { text: `${up ? "↑" : "↓"} ${Math.abs(pts).toFixed(1)}`, up };
}

export function ContainerKernel(props: ContainerKernelProps) {
  const {
    state, title, subtitle, headlinerLabel, headlinerProbability, headlinerDeltaPoints,
    headlinerResult, headlinerCorrect, marketCount, marketCountSuffix,
  } = props;
  const settled = state === "settled";
  const pct = fmtPct(headlinerProbability);
  const delta = fmtDelta(headlinerDeltaPoints);

  const countLabel = `${marketCount} market${marketCount === 1 ? "" : "s"}${marketCountSuffix ? ` · ${marketCountSuffix}` : ""}`;
  const countPill = (
    <span className="inline-flex items-center rounded-full bg-surface-elevated px-2 py-0.5 text-[11px] font-medium text-text-secondary whitespace-nowrap">
      {countLabel}
    </span>
  );

  return (
    <KernelCard
      state={state}
      stateLabel={settled ? props.stateLabel ?? "Ended" : props.stateLabel}
      liveLabel={props.liveLabel}
      angle={props.angle}
      grade={props.grade}
      categoryEmoji={props.categoryEmoji}
      categoryLabel={props.categoryLabel}
      timestamp={props.timestamp}
      footerAccessory={countPill}
      ariaLabel={title}
    >
      <div className="flex flex-col gap-0.5">
        <div className={`text-[16px] font-semibold leading-tight ${settled ? "text-text-secondary" : "text-text-primary"}`}>
          {title}
        </div>
        {subtitle && <div className="text-[12px] text-text-secondary">{subtitle}</div>}
      </div>

      {/* Inset headliner market */}
      <div className="flex items-center gap-2 rounded-lg bg-surface-elevated px-2.5 py-2">
        {settled ? (
          <>
            <span className="flex-1 text-[13px] font-semibold text-text-primary">{headlinerResult ?? headlinerLabel}</span>
            <span className={`text-[12px] font-bold ${headlinerCorrect === false ? "text-accent-danger" : "text-accent-brand"}`}>
              {headlinerCorrect === false ? "✗" : "✓"}
            </span>
          </>
        ) : (
          <>
            <span className="flex-1 text-[13px] font-medium text-text-primary">{headlinerLabel}</span>
            {pct && <span className="font-mono text-[14px] font-bold tabular-nums text-text-primary">{pct}</span>}
            {delta && (
              <span className={`font-mono text-[10px] font-medium ${delta.up ? "text-accent-live" : "text-accent-danger"}`}>
                {delta.text}
              </span>
            )}
          </>
        )}
      </div>
    </KernelCard>
  );
}
