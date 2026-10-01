"use client";

// L2-135 — Bubble Watch (cut-line tracker) for the event-concept page. Ported
// from the legacy golf tournament page's BubbleWatch, reading the concept
// envelope's competitors instead of a separate leaderboard fetch: each golfer
// carries `make_cut_prob` (0–100 POINTS) fused by the golf aggregation, so no
// extra request. Alex's ruling (L2-135 Item 2): the leaderboard is the page's
// spine, so this section renders BELOW it — same content, better placement.
//
// Rounds 1–2 only (a cut is only live before it's made); suppressed otherwise by
// the parent's mount gate. Probability-only, light tokens.
//
// #10109: the rows split on make_cut_prob (≥ 50 above the line), so the line
// is a PROBABILITY line, and its labels say "projected", never "safe". A cut
// SCORE is printed only when the field's posted scores agree with that split
// (see projectedCutScore) — in round 1 half the field hasn't teed off, and a
// median-row score put 51% golfers at E above a "-2" cut and 49% golfers at -1.

import type { EventConceptCompetitor } from "@/lib/types";
import EntityImage from "@/components/EntityImage";

interface BubbleWatchProps {
  competitors: EventConceptCompetitor[];
  /** Current round (1 or 2) — shown as an "in progress" chip when known. */
  currentRound?: number | null;
  /** "golf" → person avatars on the rows (the leaderboard's language). */
  domain?: string | null;
}

/** make_cut_prob as a 0–100 point number, or null. */
function makeCutPct(c: EventConceptCompetitor): number | null {
  const v = (c as Record<string, unknown>).make_cut_prob;
  return typeof v === "number" ? v : null;
}

/** True when the golfer's score_to_par is a posted score: they hold a
 *  leaderboard position or have played a hole. A round-1 golfer who hasn't teed
 *  off reads "E" with position "--" — that E is not a score. */
function hasPostedScore(c: EventConceptCompetitor): boolean {
  if (typeof c.score_to_par !== "number") return false;
  if (/\d/.test(c.position ?? "")) return true;
  const thru = String(c.thru ?? "").trim();
  return thru.toUpperCase() === "F" || Number(thru) > 0;
}

/** The cut score S ("S or better makes it") that agrees with the probability
 *  split, or null. S is the worst posted score among golfers projected to make
 *  the cut (≥ 50%); it is printed only when every golfer projected to miss has
 *  a strictly worse posted score. Otherwise the scores and the probabilities
 *  disagree, and no single score is the cut — so none is shown. Exported for
 *  the guard test. */
export function projectedCutScore(competitors: EventConceptCompetitor[]): number | null {
  let worstMaker: number | null = null;
  let bestMisser: number | null = null;
  for (const c of competitors) {
    const mc = makeCutPct(c);
    if (mc == null || !hasPostedScore(c)) continue;
    const score = c.score_to_par as number;
    if (projectedToMake(mc)) worstMaker = worstMaker == null ? score : Math.max(worstMaker, score);
    else bestMisser = bestMisser == null ? score : Math.min(bestMisser, score);
  }
  if (worstMaker == null || bestMisser == null) return null;
  return bestMisser > worstMaker ? worstMaker : null;
}

/** Above the line = the row's PRINTED percent is ≥ 50. The split reads the
 *  same rounded number the row shows, so a golfer printed at "50%" is never
 *  listed as projected to miss (raw 49.6). */
function projectedToMake(mc: number): boolean {
  return Math.round(mc) >= 50;
}

/** Score-to-par display: E / -N / +N. */
function fmtToPar(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n === 0) return "E";
  return n > 0 ? `+${n}` : `${n}`;
}

export default function BubbleWatch({
  competitors,
  currentRound,
  domain,
}: BubbleWatchProps) {
  const avatar = domain === "golf";

  const bubblePlayers = competitors
    .map((c) => ({ c, mc: makeCutPct(c) }))
    .filter((x): x is { c: EventConceptCompetitor; mc: number } =>
      x.mc != null && x.mc >= 15 && x.mc <= 85,
    )
    .sort((a, b) => b.mc - a.mc);

  if (bubblePlayers.length === 0) return null;

  const cutScore = projectedCutScore(competitors);
  const projectedCut = cutScore == null ? null : fmtToPar(cutScore);

  const safe = bubblePlayers.filter((x) => projectedToMake(x.mc)).slice(-3);
  const bubble = bubblePlayers.filter((x) => !projectedToMake(x.mc)).slice(0, 3);

  return (
    <section
      id="bubble-watch"
      className="bg-surface-card rounded-card shadow-card overflow-hidden"
    >
      <div className="px-6 py-4 flex items-center gap-2 flex-wrap border-b border-surface-border/60">
        <span aria-hidden className="text-base">
          ✂️
        </span>
        <h2 className="text-title-3 font-semibold text-text-primary">Bubble Watch</h2>
        {projectedCut != null && (
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand">
            Projected cut: {projectedCut}
          </span>
        )}
        {currentRound != null && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-secondary">
            Round {currentRound} in progress
          </span>
        )}
      </div>

      <div className="px-6 py-4 space-y-1">
        {safe.length > 0 && (
          <div className="text-[10px] uppercase tracking-wide font-semibold text-text-muted px-1 mb-0.5">
            Projected to make the cut
          </div>
        )}
        {safe.map(({ c, mc }) => (
          <BubbleRow key={`safe-${c.name}`} c={c} mc={mc} avatar={avatar} />
        ))}

        {/* Cut line — the pill hangs half its height below the dash, so the
            heading under it needs clearance. Padding, not margin: the parent's
            space-y-1 zeroes a child's bottom margin. */}
        <div className="relative pt-3 pb-4">
          <div className="border-t-2 border-dashed border-accent-brand/50" />
          <div className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 bg-surface-card border border-accent-brand/40 rounded-full">
            <span className="text-[10px] font-bold text-accent-brand">
              ✂️ CUT LINE{projectedCut != null ? ` · ${projectedCut}` : ""}
            </span>
          </div>
        </div>

        {bubble.length > 0 && (
          <div className="text-[10px] uppercase tracking-wide font-semibold text-text-muted px-1 mb-0.5">
            Projected to miss the cut
          </div>
        )}
        {bubble.map(({ c, mc }) => (
          <BubbleRow key={`bubble-${c.name}`} c={c} mc={mc} bubble avatar={avatar} />
        ))}

        <p className="text-[11px] text-text-muted text-center pt-2">
          {safe.length + bubble.length} golfers near the cut
        </p>
      </div>
    </section>
  );
}

function BubbleRow({
  c,
  mc,
  bubble = false,
  avatar = false,
}: {
  c: EventConceptCompetitor;
  mc: number;
  bubble?: boolean;
  avatar?: boolean;
}) {
  const probColor =
    mc >= 70 ? "text-accent-brand" : mc >= 40 ? "text-text-primary" : "text-accent-danger";
  const barColor = mc >= 70 ? "bg-accent-brand" : mc >= 40 ? "bg-accent-brand/60" : "bg-accent-danger";

  return (
    <div
      className={`flex items-center justify-between rounded-lg px-3 py-2 ${
        bubble ? "bg-accent-danger/[0.04] border border-accent-danger/15" : ""
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-xs font-bold text-text-muted w-7 shrink-0 tabular-nums">
          {c.position || "—"}
        </span>
        {avatar && <EntityImage type="wikipedia" name={c.name} size={20} className="shrink-0" />}
        <span className="text-sm font-medium text-text-primary truncate">{c.name}</span>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        <span className="font-mono text-sm tabular-nums text-text-secondary">
          {fmtToPar(c.score_to_par)}
        </span>
        <div className="w-24">
          <div className="flex items-center justify-between text-xs mb-0.5">
            <span className={`font-semibold tabular-nums ${probColor}`}>{Math.round(mc)}%</span>
            <span className="text-[9px] text-text-muted">make cut</span>
          </div>
          <div className="h-1.5 bg-surface-elevated rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${barColor}`} style={{ width: `${mc}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}
