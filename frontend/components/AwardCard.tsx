"use client";

import Link from "next/link";
import { formatProbability } from "@/lib/api";
import type { LeagueMarket } from "@/lib/api";
import EntityImage from "./EntityImage";

interface AwardCardProps {
  market: LeagueMarket;
}

function cleanAwardName(name: string): string {
  return name
    .replace(/^(NBA|NHL|MLB|NFL|WNBA|MLS)\s+/i, "")
    .replace(/\s*(2025|2026|2024)(-\d+)?\s*$/i, "")
    .replace(/\s*winner$/i, "")
    .trim();
}

export default function AwardCard({ market }: AwardCardProps) {
  const candidates = market.top_outcomes.slice(0, 5);
  if (candidates.length === 0) return null;

  const leader = candidates[0];
  const leaderProb = leader.probability ?? 0;

  return (
    <Link href={`/futures/${market.id}`}>
      <div className="rounded-2xl border border-surface-border bg-surface-card p-4 hover:shadow-md transition-all cursor-pointer h-full">
        <div className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-3">
          {cleanAwardName(market.name)}
        </div>

        {/* Leader highlight */}
        <div className="flex items-center gap-3 mb-3">
          <EntityImage type="wikipedia" name={leader.name} size={36} className="flex-shrink-0 rounded-full" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold text-text-primary truncate">{leader.name}</div>
            <div className="text-xs text-text-muted">
              {leader.probability !== null ? formatProbability(leader.probability) : "—"}
              {leader.movement_24h !== null && leader.movement_24h !== 0 && (
                <span className={`ml-1.5 font-semibold ${leader.movement_24h > 0 ? "text-accent-live" : "text-accent-danger"}`}>
                  {leader.movement_24h > 0 ? "+" : ""}{(leader.movement_24h * 100).toFixed(1)}
                </span>
              )}
            </div>
          </div>
          <span className="text-xl font-black font-mono text-text-primary tabular-nums">
            {Math.round(leaderProb * 100)}%
          </span>
        </div>

        {/* Contenders */}
        <div className="space-y-1.5">
          {candidates.slice(1).map((o, i) => (
            <div key={o.id} className="flex items-center gap-2">
              <span className="text-[10px] text-text-muted/60 w-3 flex-shrink-0 text-right">{i + 2}</span>
              <EntityImage type="wikipedia" name={o.name} size={18} className="flex-shrink-0 rounded-full" />
              <span className="text-xs text-text-secondary truncate flex-1">{o.name}</span>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <div className="w-16 h-1.5 rounded-full overflow-hidden bg-surface-elevated">
                  <div
                    className="h-full rounded-full bg-accent-brand/40 transition-all"
                    style={{ width: `${Math.max(2, Math.round((o.probability ?? 0) * 100))}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono font-semibold text-text-muted w-8 text-right">
                  {o.probability !== null ? formatProbability(o.probability) : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>

        {market.outcome_count > 5 && (
          <div className="text-[10px] text-text-muted mt-2 text-right">
            +{market.outcome_count - 5} more
          </div>
        )}
      </div>
    </Link>
  );
}
