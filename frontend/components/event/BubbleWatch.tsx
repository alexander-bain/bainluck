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

  // Projected cut ≈ the median bubble player's score.
  const midIdx = Math.floor(bubblePlayers.length / 2);
  const projectedCut = fmtToPar(bubblePlayers[midIdx]?.c.score_to_par);

  const safe = bubblePlayers.filter((x) => x.mc >= 50).slice(-3);
  const bubble = bubblePlayers.filter((x) => x.mc < 50).slice(0, 3);

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
        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-accent-brand/10 text-accent-brand">
          Projected cut: {projectedCut}
        </span>
        {currentRound != null && (
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-surface-elevated text-text-secondary">
            Round {currentRound} in progress
          </span>
        )}
      </div>

      <div className="px-6 py-4 space-y-1">
        <div className="text-[10px] uppercase tracking-wide font-semibold text-text-muted px-1 mb-0.5">
          Safe — will make cut
        </div>
        {safe.map(({ c, mc }) => (
          <BubbleRow key={`safe-${c.name}`} c={c} mc={mc} avatar={avatar} />
        ))}

        {/* Cut line */}
        <div className="relative my-3">
          <div className="border-t-2 border-dashed border-accent-brand/50" />
          <div className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-3 py-0.5 bg-surface-card border border-accent-brand/40 rounded-full">
            <span className="text-[10px] font-bold text-accent-brand">
              ✂️ CUT LINE · {projectedCut}
            </span>
          </div>
        </div>

        <div className="text-[10px] uppercase tracking-wide font-semibold text-text-muted px-1 mb-0.5">
          On the bubble
        </div>
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
