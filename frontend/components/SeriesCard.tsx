"use client";

import Link from "next/link";
import { formatProbability } from "@/lib/api";
import type { LeagueMarket, LeagueMarketOutcome } from "@/lib/api";

interface SeriesCardProps {
  market: LeagueMarket;
}

function parseSeriesTeams(market: LeagueMarket): { teamA: string; teamB: string; probA: number | null; probB: number | null } | null {
  if (market.top_outcomes.length < 2) return null;
  const a = market.top_outcomes[0];
  const b = market.top_outcomes[1];
  return { teamA: a.name, teamB: b.name, probA: a.probability, probB: b.probability };
}

function ProbBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={`h-2 rounded-full overflow-hidden bg-surface-elevated ${className || ""}`}>
      <div
        className="h-full rounded-full bg-accent-brand transition-all"
        style={{ width: `${Math.max(2, Math.round(value * 100))}%` }}
      />
    </div>
  );
}

function MovementBadge({ value }: { value: number | null }) {
  if (!value || Math.abs(value) < 0.005) return null;
  const pct = (value * 100).toFixed(1);
  return (
    <span className={`text-[10px] font-semibold ${value > 0 ? "text-accent-live" : "text-accent-danger"}`}>
      {value > 0 ? "+" : ""}{pct}
    </span>
  );
}

export default function SeriesCard({ market }: SeriesCardProps) {
  const teams = parseSeriesTeams(market);
  if (!teams) return null;

  const resDate = market.resolution_date ? new Date(market.resolution_date) : null;
  const now = new Date();
  const daysUntil = resDate ? Math.ceil((resDate.getTime() - now.getTime()) / 86400000) : null;

  return (
    <Link href={`/futures/${market.id}`}>
      <div className="rounded-2xl border border-surface-border bg-surface-card p-4 hover:shadow-md transition-all cursor-pointer h-full">
        <div className="text-[10px] font-bold uppercase tracking-widest text-text-muted mb-3">
          {market.name.replace(/^(NBA|NHL|MLB|NFL)\s*/i, "").replace(/:\s*Series Winner$/i, "")}
        </div>

        {/* Team A */}
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm font-semibold text-text-primary truncate flex-1">{teams.teamA}</span>
          <span className="text-sm font-mono font-bold text-text-primary ml-2">
            {teams.probA !== null ? formatProbability(teams.probA) : "—"}
          </span>
        </div>
        {teams.probA !== null && <ProbBar value={teams.probA} className="mb-3" />}

        {/* Team B */}
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm font-semibold text-text-primary truncate flex-1">{teams.teamB}</span>
          <span className="text-sm font-mono font-bold text-text-primary ml-2">
            {teams.probB !== null ? formatProbability(teams.probB) : "—"}
          </span>
        </div>
        {teams.probB !== null && <ProbBar value={teams.probB} className="mb-2" />}

        {/* Footer: resolution + movements */}
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-surface-border">
          {daysUntil !== null && daysUntil > 0 ? (
            <span className="text-[10px] text-text-muted">
              Resolves in {daysUntil}d
            </span>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <MovementBadge value={market.top_outcomes[0]?.movement_24h} />
            <MovementBadge value={market.top_outcomes[1]?.movement_24h} />
          </div>
        </div>
      </div>
    </Link>
  );
}
