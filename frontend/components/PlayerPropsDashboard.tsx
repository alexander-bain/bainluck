"use client";

import { useMemo, useState } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface PlayerPropsDashboardProps {
  data: GameMarketsResponse;
  eventStatus?: string;
  homeTeam?: string;
  awayTeam?: string;
  homeColor?: string;
  awayColor?: string;
  boxScore?: { players?: Array<{ name: string; team: string; stats: Record<string, number> }> } | null;
}

interface StatRung {
  threshold: number;
  overProb: number;
  sources: number;
  movement: number | null;
}

interface PlayerStat {
  type: string;
  shape: "ladder" | "line";
  rungs?: StatRung[];
  threshold?: number;
  overProb?: number;
  sources: number;
  movement: number | null;
  actual?: number | null;
}

interface PlayerData {
  name: string;
  team: "home" | "away" | "unknown";
  initials: string;
  color: string;
  headshot?: string;
  stats: PlayerStat[];
}

function SourceDot({ count }: { count: number }) {
  if (count <= 1) return null;
  return (
    <span
      className="text-[10px] font-semibold text-blue-600 bg-blue-500/10 rounded-full w-4 h-4 grid place-items-center"
      title={`${count} sources`}
    >
      {count}
    </span>
  );
}

const STAT_TYPES = [
  "Points", "Assists", "Rebounds", "Steals", "Blocks",
  "Three Pointers", "3-Pointers", "3PM", "Turnovers",
  "Strikeouts", "Hits", "Runs", "Home Runs", "RBIs",
  "Hits + Runs + RBIs", "Total Bases", "Stolen Bases",
  "Goals", "Saves", "Shots",
  "Passing Yards", "Pass Yds", "Rushing Yards", "Rush Yds",
  "Receiving Yards", "Rec Yds", "Touchdowns", "TDs",
  "Receptions", "Interceptions", "Sacks",
  "Double Doubles", "Triple Doubles",
  "Points Leader", "Assists Leader",
];

const STAT_TO_BOX_SCORE: Record<string, string> = {
  "points": "points",
  "rebounds": "rebounds",
  "assists": "assists",
  "steals": "steals",
  "blocks": "blocks",
  "three pointers": "three_pointers_made",
  "3-pointers": "three_pointers_made",
  "3pm": "three_pointers_made",
  "hits": "hits",
  "home runs": "home_runs",
  "rbis": "rbis",
  "strikeouts": "strikeouts",
  "goals": "goals",
  "passing yards": "passing_yards",
  "pass yds": "passing_yards",
  "rushing yards": "rushing_yards",
  "rush yds": "rushing_yards",
  "receiving yards": "receiving_yards",
  "rec yds": "receiving_yards",
  "receptions": "receptions",
  "interceptions": "interceptions",
  "touchdowns": "touchdowns",
  "tds": "touchdowns",
};

function parsePlayerName(marketName: string, outcomeName: string): { player: string; stat: string; team: string } | null {
  const colonIdx = marketName.indexOf(":");
  const afterColon = colonIdx >= 0 ? marketName.slice(colonIdx + 1).trim() : marketName;
  const beforeColon = colonIdx >= 0 ? marketName.slice(0, colonIdx) : "";

  let player = "";
  let stat = "";

  const exactStatMatch = STAT_TYPES.find(
    (st) => afterColon.toLowerCase() === st.toLowerCase(),
  );
  if (exactStatMatch) {
    stat = exactStatMatch;
    const outcomeColon = (outcomeName || "").indexOf(":");
    if (outcomeColon > 0) {
      player = outcomeName.slice(0, outcomeColon).trim();
    }
  } else {
    player = afterColon;
    for (const st of STAT_TYPES) {
      if (afterColon.toLowerCase().endsWith(st.toLowerCase())) {
        player = afterColon.slice(0, -st.length).trim();
        stat = st;
        break;
      }
    }
  }

  if (!player) return null;
  return { player, stat, team: beforeColon };
}

function StatBox({
  stat,
  gameState,
  teamColor,
}: {
  stat: PlayerStat;
  gameState: "pre" | "live" | "done";
  teamColor: string;
}) {
  const accent = teamColor;
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  if (stat.shape === "ladder" && stat.rungs) {
    const actual = stat.actual ?? 0;
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        {gameState !== "pre" ? (
          <div className="flex items-baseline gap-2 mb-1.5">
            <div className="font-mono tabular-nums text-2xl font-bold">{actual}</div>
            <div className="text-xs text-text-muted">so far</div>
          </div>
        ) : (
          <div className="text-[10px] text-text-muted mb-1.5">chance of hitting</div>
        )}
        <div className="space-y-1 mt-0.5">
          {stat.rungs.map((r) => {
            const hit = gameState !== "pre" && actual >= r.threshold;
            const prob = gameState === "done" ? (hit ? 1 : 0) : r.overProb;
            const fillStyle = gameState === "done" && !hit ? "rgba(156,163,175,0.3)" : `${accent}${hit ? "" : "AA"}`;
            return (
              <div key={r.threshold} className="flex items-center gap-2">
                <div
                  className={`font-mono tabular-nums text-xs w-8 ${hit ? "font-semibold" : "text-text-secondary"}`}
                  style={hit ? { color: accent } : undefined}
                >
                  {r.threshold}+
                </div>
                <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${prob * 100}%`, background: fillStyle }}
                  />
                </div>
                <div
                  className={`font-mono tabular-nums text-xs w-10 text-right ${hit ? "font-semibold" : "text-text-primary"}`}
                  style={hit ? { color: accent } : undefined}
                >
                  {gameState === "done" ? (hit ? "\u2713" : "\u2014") : pct(prob)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Line shape (single threshold O/U)
  const overThreshold = stat.actual != null && stat.threshold != null && stat.actual > stat.threshold;

  if (gameState === "pre") {
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <div className="font-mono tabular-nums text-2xl font-bold text-text-primary">{stat.threshold}+</div>
          <div className="text-xs text-text-muted">threshold</div>
        </div>
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] text-text-muted">Pre-game odds</div>
          {stat.movement != null && Math.abs(stat.movement) >= 0.01 && (
            <div className={`text-[10px] font-mono tabular-nums ${stat.movement > 0 ? "text-accent-brand" : "text-accent-danger"}`}>
              {stat.movement >= 0 ? "\u2191" : "\u2193"}{Math.round(Math.abs(stat.movement) * 100)}% 24h
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${(stat.overProb ?? 0) * 100}%`, background: accent }} />
          </div>
          <div className="font-mono tabular-nums text-xs font-semibold w-10 text-right">{pct(stat.overProb ?? 0)}</div>
        </div>
      </div>
    );
  }

  if (gameState === "live") {
    return (
      <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
        <div className="flex items-center justify-between mb-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
          <SourceDot count={stat.sources} />
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <div className="font-mono tabular-nums text-2xl font-bold">{stat.actual ?? 0}</div>
          <div className="text-xs text-text-muted">of {stat.threshold} so far</div>
        </div>
        <div className="space-y-1.5">
          <div className="grid grid-cols-[44px_1fr_36px] items-center gap-2">
            <div className="text-[10px] text-text-muted">Pre</div>
            <div className="h-1.5 rounded-full bg-surface-border overflow-hidden">
              <div className="h-full bg-text-muted/60 transition-all duration-500" style={{ width: `${(stat.overProb ?? 0) * 100}%` }} />
            </div>
            <div className="font-mono tabular-nums text-[11px] text-right">{pct(stat.overProb ?? 0)}</div>
          </div>
        </div>
      </div>
    );
  }

  // Done
  const hit = overThreshold;
  return (
    <div className="border border-surface-border rounded-lg p-2.5 bg-surface-card">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-text-secondary">{stat.type}</div>
        <SourceDot count={stat.sources} />
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <div className="font-mono tabular-nums text-2xl font-bold" style={{ color: hit ? accent : "#EF4444" }}>
          {stat.actual ?? 0}
        </div>
        <div className="font-mono tabular-nums text-xs text-text-muted">of {stat.threshold}</div>
      </div>
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded"
          style={hit ? { background: `${accent}22`, color: accent } : { background: "rgba(239,68,68,0.15)", color: "#EF4444" }}
        >
          {hit ? "HIGHER" : "LOWER"}
        </span>
        <span className="text-xs text-text-muted font-mono tabular-nums">
          by {Math.abs((stat.actual ?? 0) - (stat.threshold ?? 0)).toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function PlayerCard({ player, gameState }: { player: PlayerData; gameState: "pre" | "live" | "done" }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-4 flex flex-col">
      <div className="flex items-center gap-3 mb-3">
        {player.headshot ? (
          <img
            src={player.headshot}
            alt={player.name}
            className="w-11 h-11 rounded-full object-cover shrink-0"
            style={{ backgroundColor: player.color }}
          />
        ) : (
          <div
            className="w-11 h-11 rounded-full grid place-items-center font-mono font-bold text-white shrink-0"
            style={{ background: player.color }}
          >
            {player.initials}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-semibold truncate">{player.name}</div>
          <div className="text-xs text-text-muted font-mono">{player.team === "home" ? "Home" : player.team === "away" ? "Away" : ""}</div>
        </div>
        {gameState === "live" && (
          <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-live/15 text-accent-live flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-accent-live animate-pulse" />
            LIVE
          </span>
        )}
      </div>
      <div className={`grid gap-2 ${player.stats.length >= 3 ? "grid-cols-2" : "grid-cols-1"}`}>
        {player.stats.map((s) => (
          <StatBox key={s.type} stat={s} gameState={gameState} teamColor={player.color} />
        ))}
      </div>
    </div>
  );
}

export default function PlayerPropsDashboard({
  data,
  eventStatus,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  boxScore,
}: PlayerPropsDashboardProps) {
  const [teamFilter, setTeamFilter] = useState<"all" | "home" | "away">("all");

  const hasBoxScore = boxScore?.players != null && boxScore.players.length > 0;
  const gameState: "pre" | "live" | "done" =
    eventStatus === "live" ? "live" :
    (eventStatus === "completed" || eventStatus === "closed") && hasBoxScore ? "done" : "pre";

  const players = useMemo(() => {
    if (!data.player_props || data.player_props.length === 0) return [];

    // Group props by player → stat type
    const playerMap = new Map<string, {
      name: string;
      team: "home" | "away" | "unknown";
      headshot?: string;
      stats: Map<string, { rungs: StatRung[]; sources: Set<string>; movement: number | null }>;
    }>();

    const homeLower = homeTeam?.toLowerCase() ?? "";
    const awayLower = awayTeam?.toLowerCase() ?? "";
    const homeWords = homeLower.split(/\s+/).filter((w) => w.length >= 3);
    const awayWords = awayLower.split(/\s+/).filter((w) => w.length >= 3);

    function detectTeam(marketContext: string): "home" | "away" | "unknown" {
      const ctx = marketContext.toLowerCase();
      const homeMatch = homeWords.some((w) => ctx.includes(w)) || ctx.includes(homeLower);
      const awayMatch = awayWords.some((w) => ctx.includes(w)) || ctx.includes(awayLower);
      if (homeMatch && !awayMatch) return "home";
      if (awayMatch && !homeMatch) return "away";
      // Both match (e.g., "NYY vs BOS") — check ordering: first team mentioned is typically away (visitor)
      if (homeMatch && awayMatch) {
        const homeIdx = homeWords.reduce((min, w) => { const i = ctx.indexOf(w); return i >= 0 && i < min ? i : min; }, 999);
        const awayIdx = awayWords.reduce((min, w) => { const i = ctx.indexOf(w); return i >= 0 && i < min ? i : min; }, 999);
        return homeIdx < awayIdx ? "home" : "away";
      }
      return "unknown";
    }

    for (const p of data.player_props) {
      const parsed = parsePlayerName(p.market_name || "", p.outcome_name || "");
      if (!parsed || !parsed.player) continue;
      if (p.threshold == null) continue;

      const playerKey = parsed.player.toLowerCase();
      if (!playerMap.has(playerKey)) {
        const team: "home" | "away" | "unknown" = p.player_team ?? detectTeam(parsed.team || p.market_name || "");

        playerMap.set(playerKey, {
          name: parsed.player,
          team,
          headshot: p.player_headshot,
          stats: new Map(),
        });
      }

      const playerEntry = playerMap.get(playerKey)!;
      if (p.player_headshot && !playerEntry.headshot) {
        playerEntry.headshot = p.player_headshot;
      }

      const statKey = (parsed.stat || "prop").toLowerCase();
      if (!playerEntry.stats.has(statKey)) {
        playerEntry.stats.set(statKey, { rungs: [], sources: new Set(), movement: null });
      }

      const statEntry = playerEntry.stats.get(statKey)!;
      const existingRung = statEntry.rungs.find((r) => r.threshold === p.threshold);
      if (existingRung) {
        if (p.over_probability != null && (existingRung.overProb == null || p.over_probability > existingRung.overProb)) {
          existingRung.overProb = p.over_probability;
        }
      } else {
        statEntry.rungs.push({
          threshold: p.threshold,
          overProb: p.over_probability,
          sources: 1,
          movement: p.movement,
        });
      }
      statEntry.sources.add(p.source);
      if (p.movement != null && (statEntry.movement == null || Math.abs(p.movement) > Math.abs(statEntry.movement))) {
        statEntry.movement = p.movement;
      }
    }

    // Build player data with box score actuals
    const boxPlayers = boxScore?.players ?? [];
    const result: PlayerData[] = [];

    for (const [, entry] of playerMap) {
      const stats: PlayerStat[] = [];

      for (const [statKey, statData] of entry.stats) {
        const sortedRungs = statData.rungs.sort((a, b) => a.threshold - b.threshold);
        const shape: "ladder" | "line" = sortedRungs.length >= 3 ? "ladder" : "line";

        // Find actual from box score
        let actual: number | null = null;
        const boxKey = STAT_TO_BOX_SCORE[statKey];
        if (boxKey && boxPlayers.length > 0) {
          const match = boxPlayers.find(
            (bp) => bp.name.toLowerCase().includes(entry.name.split(" ").pop()!.toLowerCase()),
          );
          if (match?.stats?.[boxKey] != null) {
            actual = match.stats[boxKey];
          }
        }

        if (shape === "ladder") {
          stats.push({
            type: statKey.replace(/\b\w/g, (c) => c.toUpperCase()),
            shape: "ladder",
            rungs: sortedRungs,
            sources: statData.sources.size,
            movement: statData.movement,
            actual,
          });
        } else {
          const best = sortedRungs[0];
          stats.push({
            type: statKey.replace(/\b\w/g, (c) => c.toUpperCase()),
            shape: "line",
            threshold: best.threshold,
            overProb: best.overProb,
            sources: statData.sources.size,
            movement: statData.movement,
            actual,
          });
        }
      }

      if (stats.length === 0) continue;

      const initials = entry.name
        .split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();

      const color = entry.team === "home" ? (homeColor || "#3B82F6") :
                    entry.team === "away" ? (awayColor || "#EF4444") :
                    (homeColor || awayColor || "#3B82F6");

      result.push({
        name: entry.name,
        team: entry.team,
        initials,
        color,
        headshot: entry.headshot,
        stats,
      });
    }

    // Sort by most props (interesting players first)
    result.sort((a, b) => b.stats.length - a.stats.length);
    return result;
  }, [data.player_props, homeTeam, awayTeam, homeColor, awayColor, boxScore]);

  if (players.length === 0) return null;

  const filtered = teamFilter === "all" ? players : players.filter((p) => p.team === teamFilter || p.team === "unknown");
  const totalProps = players.reduce((a, p) => a + p.stats.length, 0);
  const allSources = new Set<string>();
  data.player_props?.forEach((p) => allSources.add(p.source));
  const sourceLabel = [...allSources].map((s) => s === "kalshi" ? "Kalshi" : s === "polymarket" ? "Polymarket" : s).join(" + ");

  const homeShortCode = homeTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "HOME";
  const awayShortCode = awayTeam?.split(" ").pop()?.slice(0, 3).toUpperCase() ?? "AWAY";

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Player Props</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded bg-blue-500/10 text-blue-600">
            {sourceLabel}
          </span>
          <div className="flex bg-surface-card rounded-lg border border-surface-border p-0.5">
            {(["all", "home", "away"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setTeamFilter(f)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  teamFilter === f ? "bg-[#111827] text-white" : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {f === "all" ? "All" : f === "home" ? homeShortCode : awayShortCode}
              </button>
            ))}
          </div>
        </div>
      </div>


      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        {filtered.map((p) => (
          <PlayerCard key={p.name} player={p} gameState={gameState} />
        ))}
      </div>
    </div>
  );
}
