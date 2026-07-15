/**
 * ClaimKernel — the workhorse "number + delta" card.
 *
 * Design source: "Discover Card System" handoff (2026-07-15), card `2a`.
 * The shape is `claim` (one yes/no question) → kernel `number+delta`
 * (see lib/marketShape.ts). Glance-form: the question + hook on the left, the
 * big probability + 24h delta on the right, one progress bar beneath.
 *
 * Settled state drops the bar and shows the resolved answer big-and-plain, with
 * the settled grade chip in the header (KernelCard handles the chrome).
 */

import { KernelCard, type KernelState, type KernelGrade } from "./KernelCard";
import type { AngleValue } from "./AngleBadge";

export interface ClaimKernelProps {
  state: KernelState;
  title: string;
  hook?: string | null;
  /** Category slug for the footer emoji ("politics", "golf"…). */
  categorySlug: string;
  /** Category display label for the footer ("Politics", "Golf"). */
  categoryLabel: string;
  categoryEmoji: string;
  /** 0–1. The Yes probability. Shown on upcoming/live. */
  probability?: number | null;
  /** 24h/period movement in POINTS (+up / −down). */
  deltaPoints?: number | null;
  /** Live pill suffix ("R3"). */
  liveLabel?: string;
  /** Header-left state copy ("Resolves Sep 17"). */
  stateLabel?: string;
  /** Footer-right timestamp ("5m ago", "Live", "Final · Jul 29"). */
  timestamp?: string;
  angle?: AngleValue | null;
  /** Settled: the resolved answer ("No"/"Yes"). */
  result?: string;
  /** Settled: one-line result context ("Held at 4.25% on Jul 29"). */
  resultSubtitle?: string;
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

export function ClaimKernel(props: ClaimKernelProps) {
  const {
    state, title, hook, probability, deltaPoints, result, resultSubtitle,
  } = props;
  const pct = fmtPct(probability);
  const delta = fmtDelta(deltaPoints);
  const settled = state === "settled";

  return (
    <KernelCard
      state={state}
      stateLabel={props.stateLabel}
      liveLabel={props.liveLabel}
      angle={props.angle}
      grade={props.grade}
      categoryEmoji={props.categoryEmoji}
      categoryLabel={props.categoryLabel}
      timestamp={props.timestamp}
      ariaLabel={title}
    >
      {settled ? (
        <div className="flex items-start gap-3">
          <div className="flex flex-1 flex-col gap-1">
            <div className="text-[15px] font-semibold leading-snug text-text-secondary">{title}</div>
            {resultSubtitle && <div className="text-[12px] leading-normal text-text-muted">{resultSubtitle}</div>}
          </div>
          {result && <div className="text-[20px] font-bold tracking-tight text-text-primary">{result}</div>}
        </div>
      ) : (
        <>
          <div className="flex items-start gap-3">
            <div className="flex flex-1 flex-col gap-1">
              <div className="text-[15px] font-semibold leading-snug text-text-primary">{title}</div>
              {hook && <div className="text-[12px] leading-normal text-text-secondary">{hook}</div>}
            </div>
            {pct && (
              <div className="flex flex-col items-end gap-1">
                <div className="prob-lg font-mono text-text-primary">{pct}</div>
                {delta && (
                  <div className={`font-mono text-[11px] font-semibold ${delta.up ? "text-accent-live" : "text-accent-danger"}`}>
                    {delta.text}
                  </div>
                )}
              </div>
            )}
          </div>
          {probability != null && (
            <div className="h-[5px] overflow-hidden rounded-full bg-surface-border">
              <div
                className="h-full rounded-full bg-accent-brand transition-all duration-500"
                style={{ width: `${Math.round(probability * 100)}%` }}
              />
            </div>
          )}
        </>
      )}
    </KernelCard>
  );
}
