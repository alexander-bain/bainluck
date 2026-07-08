"use client";

// #999 L2-64 Event Concept Page — winner-field leaderboard. One row per
// competitor: rank, optional seed, a live-state chip, a probability bar, an
// optional sparkline (real history only), the big probability %, and 24h
// movement. Probability-only, no source names, light tokens.

import { formatProbability } from "@/lib/api";
import {
  fieldOrder,
  competitorMovement,
  formatMovement,
  seriesForName,
} from "@/lib/eventConceptDisplay";
import type { EventConceptCompetitor, FuturesOutcomeHistory } from "@/lib/types";
import Sparkline from "./Sparkline";

interface EventLeaderboardProps {
  competitors: EventConceptCompetitor[];
  label: string;
  /** Shared history from the evolution market — powers per-row sparklines. */
  historyOutcomes?: FuturesOutcomeHistory[];
  /** Tweak: hide sparklines even when history is present. */
  showSparkline?: boolean;
  limit?: number;
  /** Rank 1 gets a "Leader" chip when the event is live. */
  live?: boolean;
}

export default function EventLeaderboard({
  competitors,
  label,
  historyOutcomes,
  showSparkline = true,
  limit = 20,
  live = false,
}: EventLeaderboardProps) {
  const ranked = fieldOrder(competitors).slice(0, limit);
  if (ranked.length === 0) return null;

  return (
    <section id="leaderboard" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">{label || "Winner"}</h2>
      <div className="space-y-0.5">
        {ranked.map((c, i) => {
          const seed = (c as Record<string, unknown>).seed;
          const mv = formatMovement(competitorMovement(c));
          const series = showSparkline ? seriesForName(historyOutcomes, c.name) : [];
          const pct = c.probability != null ? Math.round(c.probability * 100) : null;
          return (
            <div
              key={`${c.name}-${i}`}
              className="flex items-center gap-3 py-2 border-b border-surface-border/40 last:border-0"
            >
              {/* Rank */}
              <span className="text-text-muted font-mono text-xs w-5 text-right tabular-nums shrink-0">
                {i + 1}
              </span>

              {/* Name + chips + bar */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-primary truncate">{c.name}</span>
                  {typeof seed === "number" && (
                    <span className="text-[10px] text-text-muted font-mono shrink-0">
                      #{seed}
                    </span>
                  )}
                  {live && i === 0 && (
                    <span className="text-[10px] font-semibold uppercase tracking-wide px-1 py-0.5 rounded bg-accent-live/15 text-accent-live shrink-0">
                      Leader
                    </span>
                  )}
                </div>
                {pct != null && (
                  <div className="mt-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
                    <div
                      className="h-full rounded-full bg-accent-brand"
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  </div>
                )}
              </div>

              {/* Sparkline (real history only) */}
              {series.length >= 2 && (
                <div className="hidden sm:block shrink-0">
                  <Sparkline series={series} />
                </div>
              )}

              {/* 24h movement */}
              {mv && (
                <span
                  className={`font-mono text-[11px] tabular-nums shrink-0 w-12 text-right ${
                    mv.dir === "up" ? "text-accent-brand" : "text-accent-danger"
                  }`}
                >
                  {mv.dir === "up" ? "▲" : "▼"}
                  {mv.text}
                </span>
              )}

              {/* Big probability */}
              <span className="font-mono text-base font-semibold text-text-primary tabular-nums shrink-0 w-14 text-right">
                {formatProbability(c.probability)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
