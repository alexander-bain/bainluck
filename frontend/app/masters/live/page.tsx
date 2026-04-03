"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchGolfLeaderboard } from "@/lib/api";
import type { GolfLeaderboardResponse, GolfLeaderboardPlayer } from "@/lib/types";
import { usePageTracking } from "@/hooks/usePageTracking";
import { useScrollDepth } from "@/hooks/useScrollDepth";
import { useEngagementTime } from "@/hooks/useEngagementTime";

// ============================================================================
// Ultra-low-data Masters Leaderboard
// No charts, no images, no heavy JS. Loads fast on any connection.
// Auto-refreshes every 60s.
// ============================================================================

const ROUND_LABELS: Record<number, string> = {
  1: "Round 1 — Thursday",
  2: "Round 2 — Friday",
  3: "Round 3 — Saturday",
  4: "Round 4 — Sunday",
};

export default function MastersLivePage() {
  usePageTracking({ pageType: "masters_live", pageTitle: "Masters Live Leaderboard" });
  useScrollDepth({ pageType: "masters_live" });
  useEngagementTime({ pageType: "masters_live" });

  const [data, setData] = useState<GolfLeaderboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await fetchGolfLeaderboard("pga");
      setData(result);
      setError(null);
      setLastRefresh(new Date());
    } catch {
      setError("Failed to load leaderboard");
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000); // Auto-refresh every 60s
    return () => clearInterval(interval);
  }, [load]);

  if (error && !data) {
    return (
      <div className="max-w-2xl mx-auto p-4 pt-8">
        <h1 className="text-lg font-bold mb-2">Masters Leaderboard</h1>
        <p className="text-sm text-text-secondary">{error}</p>
        <button onClick={load} className="mt-2 text-sm text-blue-600 font-medium">
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-2xl mx-auto p-4 pt-8">
        <h1 className="text-lg font-bold mb-2">Loading leaderboard…</h1>
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-7 bg-gray-100 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  // Check if the returned event is actually the Masters
  const isMasters = data.status === "live" && data.event_name
    ? /masters/i.test(data.event_name)
    : false;

  if (data.status === "no_event" || (data.status === "live" && !isMasters)) {
    return (
      <div className="max-w-2xl mx-auto p-4 pt-8">
        <h1 className="text-lg font-bold mb-2">Masters Tournament</h1>
        <p className="text-sm text-text-secondary">
          The Masters hasn&apos;t started yet. The tournament runs April 9–12, 2026 at Augusta National.
        </p>
        <p className="text-sm text-text-tertiary mt-2">
          Check back during the tournament for live leaderboard with win probabilities and position changes.
        </p>
      </div>
    );
  }

  const roundLabel = data.current_round ? ROUND_LABELS[data.current_round] || `Round ${data.current_round}` : "";
  const updatedTime = data.last_updated ? formatTime(data.last_updated) : "";

  return (
    <div className="max-w-2xl mx-auto p-4 pt-6 pb-20">
      {/* Header */}
      <div className="flex justify-between items-baseline mb-3">
        <div>
          <h1 className="text-[15px] font-bold">
            {data.event_name} — {roundLabel.split(" — ")[0]}
          </h1>
          <p className="text-xs text-text-tertiary">
            {roundLabel.includes("—") ? roundLabel.split(" — ")[1] : ""}
            {updatedTime && <> · Updated {updatedTime}</>}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-red-500 uppercase tracking-wide shrink-0">
          <span className="w-[7px] h-[7px] rounded-full bg-red-500 animate-pulse" />
          Live
        </span>
      </div>

      {/* Leaderboard table */}
      <div className="bg-white border border-border rounded-[10px] overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b-2 border-border">
              <th className="text-left text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">Pos</th>
              <th className="text-left text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">Player</th>
              <th className="text-right text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">Score</th>
              <th className="text-right text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">Thru</th>
              <th className="text-right text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">Win%</th>
              <th className="text-right text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">
                Pos <span className="font-normal text-text-quaternary">(today)</span>
              </th>
              <th className="text-right text-[10px] font-semibold uppercase tracking-wide text-text-tertiary px-2 py-1.5">
                Win <span className="font-normal text-text-quaternary">(today)</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.players.slice(0, 30).map((player, i) => (
              <LeaderboardRow key={`${player.name}-${i}`} player={player} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <p className="text-center text-[11px] text-text-quaternary mt-2">
        {data.has_snapshot
          ? <>Position and probability changes are since the start of {roundLabel.split(" — ")[0] || "today\u2019s round"} play today.</>
          : <>Deltas will appear once today&apos;s round begins (snapshot taken at ~6am ET).</>
        }
        <br />
        Auto-refreshes every 60 seconds.
        {lastRefresh && <> Last: {lastRefresh.toLocaleTimeString()}</>}
      </p>
    </div>
  );
}

// ============================================================================
// Leaderboard Row
// ============================================================================

function LeaderboardRow({ player }: { player: GolfLeaderboardPlayer }) {
  const scoreColor = player.total_score_raw != null && player.total_score_raw < 0
    ? "text-red-600 font-semibold"
    : player.total_score_raw != null && player.total_score_raw > 0
    ? "text-text-primary font-semibold"
    : "";

  // Position change: positive = climbed (green ▲), negative = dropped (red ▼)
  const posChange = player.position_change;
  let posDisplay: string;
  let posColor: string;
  if (posChange == null || posChange === 0) {
    posDisplay = posChange === 0 ? "—" : "—";
    posColor = "text-text-quaternary";
  } else if (posChange > 0) {
    posDisplay = `▲${posChange}`;
    posColor = "text-green-600 font-semibold";
  } else {
    posDisplay = `▼${Math.abs(posChange)}`;
    posColor = "text-red-500 font-semibold";
  }

  // Win probability change: positive = gained (green), negative = lost (red)
  const wpChange = player.win_prob_change;
  let wpDisplay: string;
  let wpColor: string;
  if (wpChange == null || Math.abs(wpChange) < 0.1) {
    wpDisplay = wpChange != null && Math.abs(wpChange) < 0.1 ? "—" : "—";
    wpColor = "text-text-quaternary";
  } else if (wpChange > 0) {
    wpDisplay = `+${wpChange.toFixed(1)}`;
    wpColor = "text-green-600 font-semibold";
  } else {
    wpDisplay = wpChange.toFixed(1);
    wpColor = "text-red-500 font-semibold";
  }

  return (
    <tr className="border-b border-border-light hover:bg-gray-50">
      <td className="px-2 py-1.5 font-semibold text-text-tertiary tabular-nums">{player.position}</td>
      <td className="px-2 py-1.5 font-medium">{player.name}</td>
      <td className={`px-2 py-1.5 text-right tabular-nums ${scoreColor}`}>{player.score}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-text-tertiary">{player.thru}</td>
      <td className="px-2 py-1.5 text-right tabular-nums font-bold">{player.win_prob.toFixed(1)}%</td>
      <td className={`px-2 py-1.5 text-right tabular-nums ${posColor}`}>{posDisplay}</td>
      <td className={`px-2 py-1.5 text-right tabular-nums ${wpColor}`}>{wpDisplay}</td>
    </tr>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function formatTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return "";
  }
}
