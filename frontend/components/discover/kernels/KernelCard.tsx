/**
 * KernelCard — the shared chrome every Discover kernel wears.
 *
 * Design source: "Discover Card System" handoff (2026-07-15), finalized "Turn 2"
 * family. One unified chrome so all kernels read as one family:
 *   • header  = STATE (upcoming/live/settled) + ONE angle badge
 *               (a settled grade chip REPLACES the angle — design intro `1k`)
 *   • body    = the kernel-specific glance-form (children)
 *   • footer  = league (emoji + label) + timestamp
 *   • an optional hero band sits above the padded content (the Duel kernel keeps
 *     its logo/gradient crest — Alex's ruling 2026-07-15: harmonize, keep hero).
 *
 * Light-mode tokens only. The live state adds a green 1px ring (design shadow
 * `0 0 0 1px rgba(34,197,94,0.25)`); other states use the standard card ring.
 */

import type { ReactNode } from "react";
import { AngleBadge, type AngleValue } from "./AngleBadge";

export type KernelState = "upcoming" | "live" | "settled";

export interface KernelGrade {
  /** Was the user's call correct? Drives the ✓/✗ + color. */
  correct: boolean;
  /** e.g. "You said Yes", "3 of 4 calls right". */
  label: string;
}

const RING_BASE = "0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)";
const RING_LIVE = "0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(34,197,94,0.25)";

interface KernelCardProps {
  state: KernelState;
  /** Optional crest/hero band rendered above the padded content (Duel). */
  hero?: ReactNode;
  /** Left-of-header state copy: "Resolves Sep 17", "Tomorrow 7:05 PM", "Final". */
  stateLabel?: string;
  /** Live pill suffix: "R3", "Bot 6". */
  liveLabel?: string;
  /** Score shown next to the state (live/settled duels): "4 - 3". */
  score?: string;
  /** Header-right angle badge (upcoming/live). Ignored when a grade is set. */
  angle?: AngleValue | null;
  /** Header-right grade chip (settled) — REPLACES the angle. */
  grade?: KernelGrade | null;
  categoryEmoji: string;
  categoryLabel: string;
  /** Footer-right: "5m ago", "Live", "Final · Jul 29". */
  timestamp?: string;
  children: ReactNode;
  ariaLabel?: string;
}

function StateBadge({ state, stateLabel, liveLabel, score }: Pick<KernelCardProps, "state" | "stateLabel" | "liveLabel" | "score">) {
  if (state === "live") {
    return (
      <span className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-accent-live/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] text-accent-live">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-live animate-pulse" aria-hidden="true" />
          LIVE{liveLabel ? ` · ${liveLabel}` : ""}
        </span>
        {score && <span className="font-mono text-[13px] font-bold tabular-nums text-accent-live">{score}</span>}
      </span>
    );
  }
  if (state === "settled") {
    return (
      <span className="inline-flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{stateLabel ?? "Resolved"}</span>
        {score && <span className="font-mono text-[13px] font-bold tabular-nums text-text-primary">{score}</span>}
      </span>
    );
  }
  // upcoming
  return <span className="text-[11px] tracking-[0.02em] text-text-muted">{stateLabel}</span>;
}

function GradeChip({ grade }: { grade: KernelGrade }) {
  const cls = grade.correct
    ? "text-accent-brand bg-accent-brand/15"
    : "text-accent-danger bg-accent-danger/10";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`} data-grade={grade.correct ? "hit" : "miss"}>
      <span aria-hidden="true">{grade.correct ? "✓" : "✗"}</span>
      {grade.label}
    </span>
  );
}

export function KernelCard({
  state,
  hero,
  stateLabel,
  liveLabel,
  score,
  angle,
  grade,
  categoryEmoji,
  categoryLabel,
  timestamp,
  children,
  ariaLabel,
}: KernelCardProps) {
  return (
    <article
      className="relative flex flex-col overflow-hidden rounded-[10px] border border-surface-border bg-surface-card transition-shadow hover:shadow-lg"
      style={{ boxShadow: state === "live" ? RING_LIVE : RING_BASE }}
      data-kernel-state={state}
      aria-label={ariaLabel}
    >
      {hero}
      <div className="flex flex-col gap-2 px-[14px] py-[12px]">
        {/* Header: state + ONE angle (grade replaces angle when settled) */}
        <div className="flex items-center gap-1.5">
          <StateBadge state={state} stateLabel={stateLabel} liveLabel={liveLabel} score={score} />
          <span className="ml-auto">
            {state === "settled" && grade ? <GradeChip grade={grade} /> : <AngleBadge angle={angle ?? null} />}
          </span>
        </div>

        {/* Body: the kernel-specific glance-form */}
        {children}

        {/* Footer: league + timestamp */}
        <div className="mt-0.5 flex items-center justify-between">
          <span className="text-[11px] tracking-[0.02em] text-text-muted">
            {categoryEmoji} {categoryLabel}
          </span>
          {timestamp && <span className="text-[11px] text-text-muted">{timestamp}</span>}
        </div>
      </div>
    </article>
  );
}
