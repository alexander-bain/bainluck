/**
 * FieldKernel — many entrants, one prize (the top-3 leaderboard card).
 *
 * Design source: "Discover Card System" handoff (2026-07-15), card `1f`
 * ("equal rows" — the owner's pick over the `1g` podium), finalized in the
 * `2f` mixed-feed chrome. The shape is `field` → kernel `top-3` (see
 * lib/marketShape.ts): a themed set of entrants ranked, showing the top three
 * plus a "+N more · residual%" line so the whole field is accounted for.
 *
 * The kernel wears the unified KernelCard chrome (header = state + ONE angle,
 * footer = league + timestamp) with the Field-specific 2px accent-futures top
 * border (`topAccent`) as the "many entrants" cue.
 *
 * Settled state drops the leaderboard and names the winner big-and-plain with
 * its pre-resolution context ("Entered playoffs at 18%"), the grade chip in the
 * header (KernelCard handles the chrome).
 */

import { KernelCard, type KernelState, type KernelGrade } from "./KernelCard";
import type { AngleValue } from "./AngleBadge";

export interface FieldEntrant {
  /** Entrant name ("Buffalo Bills", "Scottie Scheffler"). */
  name: string;
  /** 0–1 probability of winning the prize. */
  probability: number | null;
  /** Optional 24h/period movement in POINTS (shown on the leader row). */
  deltaPoints?: number | null;
}

export interface FieldKernelProps {
  state: KernelState;
  /** The prize question ("Super Bowl LXI winner"). */
  title: string;
  categorySlug: string;
  categoryLabel: string;
  categoryEmoji: string;
  /** Ranked entrants, highest probability first. The top 3 are shown. */
  entrants: FieldEntrant[];
  /** Count of entrants beyond the shown top 3 ("+N more"). */
  moreCount?: number | null;
  /** Combined probability of all not-shown entrants (0–1) for the "more" line. */
  moreProbability?: number | null;
  /** Header-left state copy ("31 entrants · Resolves Feb '27"). */
  stateLabel?: string;
  liveLabel?: string;
  timestamp?: string;
  angle?: AngleValue | null;
  grade?: KernelGrade | null;
  /** Settled: the winning entrant's name. */
  winner?: string;
  /** Settled: one-line pre-resolution context ("Entered playoffs at 18%"). */
  winnerContext?: string;
}

function fmtPct(p: number | null | undefined): string {
  if (p == null) return "—";
  return `${Math.round(p * 100)}%`;
}

function fmtDelta(pts: number | null | undefined): { text: string; up: boolean } | null {
  if (pts == null || Math.abs(pts) < 0.1) return null;
  const up = pts >= 0;
  return { text: `${up ? "↑" : "↓"}${Math.abs(pts).toFixed(1)}%`, up };
}

function EntrantRow({ entrant, rank }: { entrant: FieldEntrant; rank: number }) {
  const isLeader = rank === 1;
  const width = Math.max(2, Math.round((entrant.probability ?? 0) * 100));
  const delta = isLeader ? fmtDelta(entrant.deltaPoints) : null;
  return (
    <div className="flex items-center gap-2 text-[13px]">
      <span
        className={[
          "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded text-[10px] font-bold",
          isLeader ? "bg-accent-warning/15 text-accent-warning" : "font-medium text-text-muted",
        ].join(" ")}
        aria-hidden="true"
      >
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className={`truncate ${isLeader ? "font-medium text-text-primary" : "text-text-secondary"}`}>
          {entrant.name}
        </div>
        <div className="mt-[3px] h-[3px] overflow-hidden rounded-[3px] bg-surface-border">
          <div
            className={`h-full ${isLeader ? "bg-accent-futures/70" : "bg-text-muted/30"}`}
            style={{ width: `${width}%` }}
          />
        </div>
      </div>
      {delta && (
        <span className={`shrink-0 font-mono text-[10px] font-medium ${delta.up ? "text-accent-live" : "text-accent-danger"}`}>
          {delta.text}
        </span>
      )}
      <span
        className={`shrink-0 font-mono text-[13px] tabular-nums ${isLeader ? "font-bold text-text-primary" : "font-medium text-text-muted"}`}
      >
        {fmtPct(entrant.probability)}
      </span>
    </div>
  );
}

export function FieldKernel(props: FieldKernelProps) {
  const { state, title, entrants, moreCount, moreProbability, winner, winnerContext } = props;
  const settled = state === "settled";
  const top = entrants.slice(0, 3);

  return (
    <KernelCard
      state={state}
      topAccent
      stateLabel={settled ? props.stateLabel ?? "Resolved" : props.stateLabel}
      liveLabel={props.liveLabel}
      angle={props.angle}
      grade={props.grade}
      categoryEmoji={props.categoryEmoji}
      categoryLabel={props.categoryLabel}
      timestamp={props.timestamp}
      ariaLabel={title}
    >
      {settled ? (
        <>
          <div className="text-[15px] font-semibold leading-snug text-text-secondary">{title}</div>
          <div className="flex items-center gap-2">
            {winner && <span className="text-[13px] font-semibold text-text-primary">{winner}</span>}
            <span className="text-[12px] font-bold text-accent-brand">✓ Won</span>
            {winnerContext && <span className="ml-auto text-[12px] text-text-muted">{winnerContext}</span>}
          </div>
        </>
      ) : (
        <>
          <div className="text-[15px] font-semibold leading-snug text-text-primary">{title}</div>
          <div className="flex flex-col gap-1.5">
            {top.map((entrant, i) => (
              <EntrantRow key={`${entrant.name}-${i}`} entrant={entrant} rank={i + 1} />
            ))}
            {moreCount != null && moreCount > 0 && (
              <div className="pl-[26px] text-[12px] text-text-muted">
                +{moreCount} more
                {moreProbability != null && (
                  <> · <span className="font-mono font-medium">{fmtPct(moreProbability)}</span></>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </KernelCard>
  );
}
