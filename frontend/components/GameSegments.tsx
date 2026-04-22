"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface GameSegmentsProps {
  data: GameMarketsResponse;
  eventStatus?: string;
  homeTeam?: string;
  awayTeam?: string;
  homeColor?: string;
  awayColor?: string;
}

interface HalfData {
  name: string;
  totalLine: number | null;
  overProb: number | null;
  leaderProbs: { home: number; away: number; tied?: number } | null;
  sources: number;
}

function SourceBadge({ count }: { count: number }) {
  if (count <= 1) return null;
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded bg-blue-500/10 text-blue-600">
      {count} sources
    </span>
  );
}

export default function GameSegments({
  data,
  eventStatus,
  homeTeam,
  awayTeam,
  homeColor = "#10B981",
  awayColor = "#6B7280",
}: GameSegmentsProps) {
  const periodMarkets = data.period_markets ?? [];

  const halves = useMemo(() => {
    if (periodMarkets.length === 0) return [];

    const halfNames = new Set<string>();
    const halfData = new Map<string, HalfData>();

    for (const m of periodMarkets) {
      const name = m.market_name || "";
      const lower = name.toLowerCase();

      let halfKey = "";
      let halfLabel = "";
      if (lower.includes("1st half") || lower.includes("1h") || lower.includes("first half")) {
        halfKey = "1st_half";
        halfLabel = "1st Half";
      } else if (lower.includes("2nd half") || lower.includes("2h") || lower.includes("second half")) {
        halfKey = "2nd_half";
        halfLabel = "2nd Half";
      } else if (lower.includes("1st quarter") || lower.includes("1q")) {
        halfKey = "q1";
        halfLabel = "1st Quarter";
      } else {
        continue;
      }

      if (!halfNames.has(halfKey)) {
        halfNames.add(halfKey);
        halfData.set(halfKey, {
          name: halfLabel,
          totalLine: null,
          overProb: null,
          leaderProbs: null,
          sources: 0,
        });
      }

      const entry = halfData.get(halfKey)!;
      const sources = new Set<string>();
      if (m.source) sources.add(m.source);

      if (m.market_type === "half_total" || m.market_type === "quarter_total") {
        if (m.threshold != null && m.over_probability != null) {
          if (entry.totalLine == null || Math.abs(m.over_probability - 0.5) < Math.abs((entry.overProb ?? 0) - 0.5)) {
            entry.totalLine = m.threshold;
            entry.overProb = m.over_probability;
          }
        }
      }

      if (m.market_type === "half_winner" || m.market_type === "quarter_winner") {
        const outLower = (m.outcome_name || "").toLowerCase();
        const homeShort = homeTeam?.split(" ").pop()?.toLowerCase() ?? "";
        const awayShort = awayTeam?.split(" ").pop()?.toLowerCase() ?? "";

        if (!entry.leaderProbs) {
          entry.leaderProbs = { home: 0.5, away: 0.5 };
        }

        if (homeShort && outLower.includes(homeShort)) {
          entry.leaderProbs.home = m.probability ?? m.over_probability ?? 0.5;
        } else if (awayShort && outLower.includes(awayShort)) {
          entry.leaderProbs.away = m.probability ?? m.over_probability ?? 0.5;
        } else if (outLower.includes("tie") || outLower.includes("draw")) {
          entry.leaderProbs.tied = m.probability ?? m.over_probability ?? 0;
        }
      }

      entry.sources = Math.max(entry.sources, sources.size);
    }

    return [...halfData.values()].filter((h) => h.totalLine != null || h.leaderProbs != null);
  }, [periodMarkets, homeTeam, awayTeam]);

  if (halves.length === 0) return null;

  const homeCode = homeTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "HOME";
  const awayCode = awayTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "AWAY";

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-5">
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Game segments</h3>
          <p className="text-sm text-text-secondary mt-0.5">Period totals and leader</p>
        </div>
        <SourceBadge count={Math.max(...halves.map((h) => h.sources))} />
      </div>

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        {halves.map((half) => {
          const overPct = half.overProb != null ? Math.round(half.overProb * 100) : null;
          const homePct = half.leaderProbs ? Math.round(half.leaderProbs.home * 100) : 50;
          const awayPct = half.leaderProbs ? Math.round(half.leaderProbs.away * 100) : 50;
          const tiedPct = half.leaderProbs?.tied ? Math.round(half.leaderProbs.tied * 100) : 0;

          return (
            <div key={half.name} className="border border-surface-border rounded-lg p-4 bg-surface-card">
              <div className="font-semibold mb-3">{half.name}</div>

              {/* Total points */}
              {half.totalLine != null && overPct != null && (
                <div className="mb-4">
                  <div className="flex items-baseline justify-between mb-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">TOTAL POINTS</div>
                    <div className="font-mono tabular-nums text-xs text-text-secondary">
                      line <b className="text-text-primary">{half.totalLine}</b>
                    </div>
                  </div>
                  <div className="grid grid-cols-[72px_1fr_44px] items-center gap-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Over</div>
                    <div className="h-2 rounded-full bg-surface-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-violet-400/50 transition-all duration-500"
                        style={{ width: `${overPct}%` }}
                      />
                    </div>
                    <div className="font-mono tabular-nums text-[11px] text-right">{overPct}%</div>
                  </div>
                </div>
              )}

              {/* Leader bar */}
              {half.leaderProbs && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-1">
                    LEADER AFTER {half.name.toUpperCase()}
                  </div>
                  <div className="flex h-7 rounded-lg overflow-hidden">
                    <div
                      className="flex items-center justify-between px-2 transition-all duration-500"
                      style={{ width: `${homePct}%`, background: homeColor }}
                    >
                      <span className="text-white font-mono tabular-nums text-xs font-bold">{homeCode}</span>
                      <span className="text-white font-mono tabular-nums text-xs font-bold">{homePct}%</span>
                    </div>
                    {tiedPct > 0 && (
                      <div
                        className="flex items-center justify-center bg-text-muted/40 px-1 transition-all duration-500"
                        style={{ width: `${tiedPct}%` }}
                      >
                        <span className="text-white font-mono tabular-nums text-[10px] font-bold">{tiedPct}%</span>
                      </div>
                    )}
                    <div
                      className="flex items-center justify-between px-2 transition-all duration-500"
                      style={{ width: `${awayPct}%`, background: awayColor }}
                    >
                      <span className="text-white font-mono tabular-nums text-xs font-bold">{awayPct}%</span>
                      <span className="text-white font-mono tabular-nums text-xs font-bold">{awayCode}</span>
                    </div>
                  </div>
                  {tiedPct > 0 && (
                    <div className="text-[10px] text-text-muted mt-1">includes {tiedPct}% chance of tied score</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
