"use client";

/**
 * Win Probability Charts Demo
 * 
 * Three chart variants using the existing OddsChart component:
 * 1. Two-Team (NBA, NFL, NHL, MLB) — multiple sources aggregated, period markers
 * 2. Multi-Participant (Golf, NASCAR) — evolution plot for 8+ competitors
 * 3. Tournament Bracket (March Madness, Playoffs) — progression through rounds
 */

import { useState } from "react";
import OddsChart from "@/components/OddsChart";
import type { 
  OddsHistoryPoint, 
  ESPNHistoryPoint, 
  WinProbHistoryPoint,
  WinProbSourceMeta,
} from "@/lib/types";
import type { PeriodBoundary } from "@/lib/periodMarkers";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
  Area,
} from "recharts";

// =============================================================================
// MOCK DATA: Two-Team NBA Game (Celtics vs Heat comeback)
// =============================================================================

const NBA_COMMENCE_TIME = "2024-03-15T19:30:00Z";

// Generate minute-by-minute data for a 48-minute NBA game
function generateNBAOddsHistory(): OddsHistoryPoint[] {
  const points: OddsHistoryPoint[] = [];
  const baseTime = new Date(NBA_COMMENCE_TIME);
  
  // Probability curve: Home starts favored, loses lead, comes back to win
  const probCurve = [
    // Pre-game
    { minute: -60, prob: 0.58 },
    { minute: -30, prob: 0.57 },
    { minute: 0, prob: 0.56 },
    // Q1: Home strong start
    { minute: 3, prob: 0.62 },
    { minute: 6, prob: 0.65 },
    { minute: 9, prob: 0.63 },
    { minute: 12, prob: 0.60 },
    // Q2: Away comeback begins
    { minute: 15, prob: 0.55 },
    { minute: 18, prob: 0.48 },
    { minute: 21, prob: 0.42 },
    { minute: 24, prob: 0.38 },
    // Q3: Away extends lead
    { minute: 27, prob: 0.35 },
    { minute: 30, prob: 0.32 },
    { minute: 33, prob: 0.28 },
    { minute: 36, prob: 0.25 },
    // Q4: Home dramatic comeback
    { minute: 39, prob: 0.30 },
    { minute: 42, prob: 0.38 },
    { minute: 44, prob: 0.45 },
    { minute: 46, prob: 0.55 },
    { minute: 47, prob: 0.65 },
    { minute: 48, prob: 0.78 },
  ];
  
  for (const { minute, prob } of probCurve) {
    const timestamp = new Date(baseTime.getTime() + minute * 60 * 1000);
    points.push({
      timestamp: timestamp.toISOString(),
      home_probability: prob,
      away_probability: 1 - prob,
      valid_until: new Date(timestamp.getTime() + 3 * 60 * 1000).toISOString(),
    });
  }
  
  return points;
}

// Generate multi-source win probability history
function generateNBAWinProbHistory(): Record<string, WinProbHistoryPoint[]> {
  const baseTime = new Date(NBA_COMMENCE_TIME);
  const sources: Record<string, WinProbHistoryPoint[]> = {
    espn: [],
    kalshi: [],
    polymarket: [],
  };
  
  // ESPN updates every ~2 minutes during game with slight variance from betting odds
  const espnVariance = [0.02, -0.01, 0.03, -0.02, 0.01, -0.03, 0.02, -0.01, 0.03, -0.02, 0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.02, -0.01];
  const kalshiVariance = [-0.01, 0.02, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, -0.02, 0.03, -0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, 0.02];
  const polymarketVariance = [0.01, -0.02, 0.01, -0.01, 0.02, -0.01, 0.01, -0.02, 0.01, -0.01, 0.02, 0.01, -0.02, 0.01, -0.01, 0.02, -0.01, 0.01];
  
  const baseProbCurve = [0.56, 0.62, 0.65, 0.63, 0.60, 0.55, 0.48, 0.42, 0.38, 0.35, 0.32, 0.28, 0.25, 0.30, 0.38, 0.45, 0.55, 0.65, 0.78];
  const periods = ["1st Quarter", "1st Quarter", "1st Quarter", "1st Quarter", "1st Quarter", "2nd Quarter", "2nd Quarter", "2nd Quarter", "2nd Quarter", "3rd Quarter", "3rd Quarter", "3rd Quarter", "3rd Quarter", "4th Quarter", "4th Quarter", "4th Quarter", "4th Quarter", "4th Quarter", "Final"];
  const clocks = ["12:00", "9:00", "6:00", "3:00", "0:00", "9:00", "6:00", "3:00", "0:00", "9:00", "6:00", "3:00", "0:00", "9:00", "6:00", "4:00", "2:00", "0:30", "0:00"];
  const homeScores = [0, 8, 18, 24, 28, 34, 38, 42, 45, 52, 58, 62, 68, 72, 78, 85, 92, 98, 105];
  const awayScores = [0, 5, 12, 20, 26, 32, 40, 48, 52, 60, 68, 76, 82, 86, 90, 94, 98, 100, 102];
  
  for (let i = 0; i < baseProbCurve.length; i++) {
    const minute = i * 2.5;
    const timestamp = new Date(baseTime.getTime() + minute * 60 * 1000).toISOString();
    
    sources.espn.push({
      timestamp,
      home_probability: Math.max(0.05, Math.min(0.95, baseProbCurve[i] + (espnVariance[i] || 0))),
      game_state: {
        period: periods[i],
        clock: clocks[i],
        home_score: homeScores[i],
        away_score: awayScores[i],
      },
    });
    
    sources.kalshi.push({
      timestamp,
      home_probability: Math.max(0.05, Math.min(0.95, baseProbCurve[i] + (kalshiVariance[i] || 0))),
    });
    
    sources.polymarket.push({
      timestamp,
      home_probability: Math.max(0.05, Math.min(0.95, baseProbCurve[i] + (polymarketVariance[i] || 0))),
    });
  }
  
  return sources;
}

const NBA_WIN_PROB_SOURCES: Record<string, WinProbSourceMeta> = {
  espn: { display_name: "ESPN", color: "#f97316", dash_pattern: "6 3", type: "model" },
  kalshi: { display_name: "Kalshi", color: "#22c55e", dash_pattern: "8 4", type: "market" },
  polymarket: { display_name: "Polymarket", color: "#3b82f6", dash_pattern: "8 4", type: "market" },
};

const NBA_PERIOD_BOUNDARIES: PeriodBoundary[] = [
  { timestamp: NBA_COMMENCE_TIME, label: "Q1" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 12 * 60 * 1000).toISOString(), label: "Q2" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 24 * 60 * 1000).toISOString(), label: "HT" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 26 * 60 * 1000).toISOString(), label: "Q3" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 38 * 60 * 1000).toISOString(), label: "Q4" },
];

// =============================================================================
// MOCK DATA: Multi-Participant Golf Tournament (Masters)
// =============================================================================

interface GolfPlayerData {
  name: string;
  color: string;
  probabilities: number[];
}

const GOLF_PLAYERS: GolfPlayerData[] = [
  { name: "Scheffler", color: "#22c55e", probabilities: [0.18, 0.22, 0.28, 0.35, 0.42] },
  { name: "McIlroy", color: "#3b82f6", probabilities: [0.12, 0.15, 0.18, 0.14, 0.10] },
  { name: "Rahm", color: "#eab308", probabilities: [0.14, 0.12, 0.10, 0.08, 0.06] },
  { name: "Koepka", color: "#ef4444", probabilities: [0.08, 0.10, 0.12, 0.15, 0.18] },
  { name: "Hovland", color: "#8b5cf6", probabilities: [0.06, 0.08, 0.06, 0.05, 0.04] },
  { name: "Morikawa", color: "#06b6d4", probabilities: [0.05, 0.04, 0.03, 0.02, 0.02] },
  { name: "Thomas", color: "#f97316", probabilities: [0.04, 0.03, 0.02, 0.01, 0.01] },
  { name: "Field", color: "#6b7280", probabilities: [0.33, 0.26, 0.21, 0.20, 0.17] },
];

const GOLF_ROUNDS = ["Pre-Tournament", "After R1", "After R2", "After R3", "Final"];

function generateGolfData() {
  return GOLF_ROUNDS.map((round, i) => {
    const dataPoint: Record<string, string | number> = { round };
    for (const player of GOLF_PLAYERS) {
      dataPoint[player.name] = Math.round(player.probabilities[i] * 100);
    }
    return dataPoint;
  });
}

// =============================================================================
// MOCK DATA: Tournament Bracket (March Madness)
// =============================================================================

interface BracketTeam {
  name: string;
  seed: number;
  color: string;
  probabilities: { round: string; prob: number }[];
}

const BRACKET_TEAMS: BracketTeam[] = [
  { 
    name: "UConn", 
    seed: 1, 
    color: "#0e1a36",
    probabilities: [
      { round: "R64", prob: 0.98 },
      { round: "R32", prob: 0.88 },
      { round: "S16", prob: 0.65 },
      { round: "E8", prob: 0.45 },
      { round: "F4", prob: 0.28 },
      { round: "Final", prob: 0.18 },
    ]
  },
  { 
    name: "Houston", 
    seed: 1, 
    color: "#c8102e",
    probabilities: [
      { round: "R64", prob: 0.97 },
      { round: "R32", prob: 0.85 },
      { round: "S16", prob: 0.58 },
      { round: "E8", prob: 0.38 },
      { round: "F4", prob: 0.22 },
      { round: "Final", prob: 0.14 },
    ]
  },
  { 
    name: "Purdue", 
    seed: 1, 
    color: "#ceb888",
    probabilities: [
      { round: "R64", prob: 0.96 },
      { round: "R32", prob: 0.82 },
      { round: "S16", prob: 0.52 },
      { round: "E8", prob: 0.32 },
      { round: "F4", prob: 0.18 },
      { round: "Final", prob: 0.10 },
    ]
  },
  { 
    name: "Duke", 
    seed: 4, 
    color: "#003087",
    probabilities: [
      { round: "R64", prob: 0.78 },
      { round: "R32", prob: 0.55 },
      { round: "S16", prob: 0.32 },
      { round: "E8", prob: 0.18 },
      { round: "F4", prob: 0.08 },
      { round: "Final", prob: 0.04 },
    ]
  },
];

const BRACKET_ROUNDS = ["R64", "R32", "S16", "E8", "F4", "Final"];

function generateBracketData() {
  return BRACKET_ROUNDS.map((round) => {
    const dataPoint: Record<string, string | number> = { round };
    for (const team of BRACKET_TEAMS) {
      const roundData = team.probabilities.find(p => p.round === round);
      dataPoint[team.name] = roundData ? Math.round(roundData.prob * 100) : 0;
    }
    return dataPoint;
  });
}

// =============================================================================
// DEMO PAGE COMPONENT
// =============================================================================

type DemoView = "two-team" | "golf" | "bracket";

export default function WinProbabilityDemo() {
  const [activeView, setActiveView] = useState<DemoView>("two-team");
  const [highlightedPlayer, setHighlightedPlayer] = useState<string | null>(null);
  
  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground mb-2">
            Win Probability Charts
          </h1>
          <p className="text-muted-foreground text-sm">
            Three chart variants for different competition types. Data aggregated from ESPN, Kalshi, Polymarket, and betting markets.
          </p>
        </div>
        
        {/* View Selector */}
        <div className="flex gap-2 flex-wrap">
          {[
            { key: "two-team" as DemoView, label: "Two-Team (NBA)", desc: "Head-to-head with multi-source aggregation" },
            { key: "golf" as DemoView, label: "Multi-Participant (Golf)", desc: "Tournament with 8+ competitors" },
            { key: "bracket" as DemoView, label: "Tournament Bracket", desc: "March Madness / Playoffs progression" },
          ].map(({ key, label, desc }) => (
            <button
              key={key}
              onClick={() => setActiveView(key)}
              className={`px-4 py-3 rounded-lg text-left transition-colors ${
                activeView === key
                  ? "bg-foreground text-background"
                  : "bg-card hover:bg-muted text-foreground"
              }`}
            >
              <div className="font-medium text-sm">{label}</div>
              <div className={`text-xs mt-0.5 ${activeView === key ? "text-background/70" : "text-muted-foreground"}`}>
                {desc}
              </div>
            </button>
          ))}
        </div>
        
        {/* Chart Area */}
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          {activeView === "two-team" && (
            <TwoTeamChart />
          )}
          {activeView === "golf" && (
            <GolfChart 
              highlightedPlayer={highlightedPlayer} 
              setHighlightedPlayer={setHighlightedPlayer} 
            />
          )}
          {activeView === "bracket" && (
            <BracketChart />
          )}
        </div>
        
        {/* Legend / Source Attribution */}
        <div className="text-xs text-muted-foreground">
          Data sources: ESPN Win Probability, Kalshi, Polymarket, DraftKings, FanDuel, BetMGM. 
          Aggregated "Bain Luck" line uses weighted median with staleness decay.
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// TWO-TEAM CHART (uses existing OddsChart component)
// =============================================================================

function TwoTeamChart() {
  const history = generateNBAOddsHistory();
  const winProbHistory = generateNBAWinProbHistory();
  
  return (
    <div className="p-4">
      {/* Game Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[#007a33] flex items-center justify-center text-white text-xs font-bold">
              BOS
            </div>
            <div>
              <div className="font-semibold text-foreground">Boston Celtics</div>
              <div className="text-xs text-muted-foreground">105 - Final</div>
            </div>
          </div>
          <div className="text-muted-foreground text-sm">vs</div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[#98002e] flex items-center justify-center text-white text-xs font-bold">
              MIA
            </div>
            <div>
              <div className="font-semibold text-foreground">Miami Heat</div>
              <div className="text-xs text-muted-foreground">102</div>
            </div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          March 15, 2024
        </div>
      </div>
      
      {/* Chart using existing OddsChart component */}
      <div className="h-80">
        <OddsChart
          history={history}
          homeTeam="Boston Celtics"
          awayTeam="Miami Heat"
          commenceTime={NBA_COMMENCE_TIME}
          isLive={false}
          winProbHistory={winProbHistory}
          winProbSources={NBA_WIN_PROB_SOURCES}
          eventStatus="completed"
          periodBoundaries={NBA_PERIOD_BOUNDARIES}
          homeTeamColor="#007a33"
          awayTeamColor="#98002e"
          fillContainer
        />
      </div>
    </div>
  );
}

// =============================================================================
// GOLF CHART (Multi-Participant Evolution)
// =============================================================================

interface GolfChartProps {
  highlightedPlayer: string | null;
  setHighlightedPlayer: (player: string | null) => void;
}

function GolfChart({ highlightedPlayer, setHighlightedPlayer }: GolfChartProps) {
  const data = generateGolfData();
  
  return (
    <div className="p-4">
      {/* Tournament Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="font-semibold text-foreground">The Masters 2024</div>
          <div className="text-xs text-muted-foreground">Augusta National Golf Club</div>
        </div>
        <div className="text-xs text-muted-foreground">
          Win Probability Evolution
        </div>
      </div>
      
      {/* Player Legend (clickable) */}
      <div className="flex flex-wrap gap-2 mb-4">
        {GOLF_PLAYERS.map((player) => (
          <button
            key={player.name}
            onClick={() => setHighlightedPlayer(
              highlightedPlayer === player.name ? null : player.name
            )}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-opacity ${
              highlightedPlayer && highlightedPlayer !== player.name
                ? "opacity-30"
                : "opacity-100"
            } ${highlightedPlayer === player.name ? "bg-muted" : ""}`}
          >
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: player.color }}
            />
            <span className="text-foreground">{player.name}</span>
          </button>
        ))}
      </div>
      
      {/* Chart */}
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="round"
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              axisLine={{ stroke: "hsl(var(--border))" }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 50]}
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              axisLine={{ stroke: "hsl(var(--border))" }}
              tickLine={false}
              tickFormatter={(value) => `${value}%`}
              label={{
                value: "Win Probability",
                angle: -90,
                position: "insideLeft",
                fill: "hsl(var(--muted-foreground))",
                fontSize: 11,
                offset: 10,
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600 }}
              formatter={(value: number, name: string) => [`${value}%`, name]}
            />
            {GOLF_PLAYERS.map((player) => (
              <Line
                key={player.name}
                type="monotone"
                dataKey={player.name}
                stroke={player.color}
                strokeWidth={highlightedPlayer === player.name ? 3 : 2}
                dot={{ fill: player.color, r: highlightedPlayer === player.name ? 5 : 3 }}
                opacity={
                  highlightedPlayer && highlightedPlayer !== player.name
                    ? 0.15
                    : 1
                }
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =============================================================================
// BRACKET CHART (Tournament Progression)
// =============================================================================

function BracketChart() {
  const data = generateBracketData();
  
  return (
    <div className="p-4">
      {/* Tournament Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="font-semibold text-foreground">NCAA Tournament 2024</div>
          <div className="text-xs text-muted-foreground">Championship Probability by Round</div>
        </div>
      </div>
      
      {/* Team Legend */}
      <div className="flex flex-wrap gap-3 mb-4">
        {BRACKET_TEAMS.map((team) => (
          <div key={team.name} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded"
              style={{ backgroundColor: team.color }}
            />
            <span className="text-xs text-foreground">
              ({team.seed}) {team.name}
            </span>
          </div>
        ))}
      </div>
      
      {/* Chart */}
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
            <XAxis
              dataKey="round"
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              axisLine={{ stroke: "hsl(var(--border))" }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
              axisLine={{ stroke: "hsl(var(--border))" }}
              tickLine={false}
              tickFormatter={(value) => `${value}%`}
              label={{
                value: "Championship Probability",
                angle: -90,
                position: "insideLeft",
                fill: "hsl(var(--muted-foreground))",
                fontSize: 11,
                offset: 10,
              }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600 }}
              formatter={(value: number, name: string) => {
                const team = BRACKET_TEAMS.find(t => t.name === name);
                return [`${value}%`, team ? `(${team.seed}) ${name}` : name];
              }}
            />
            {BRACKET_TEAMS.map((team) => (
              <Area
                key={team.name}
                type="monotone"
                dataKey={team.name}
                stroke={team.color}
                fill={team.color}
                fillOpacity={0.1}
                strokeWidth={2}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      
      {/* Round Labels */}
      <div className="flex justify-between mt-2 px-5 text-xs text-muted-foreground">
        <span>Round of 64</span>
        <span>Round of 32</span>
        <span>Sweet 16</span>
        <span>Elite 8</span>
        <span>Final Four</span>
        <span>Championship</span>
      </div>
    </div>
  );
}
