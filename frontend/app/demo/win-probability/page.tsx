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
    <div className="flex flex-col h-full">
      {/* Game Header - MoneyPuck inspired */}
      <div className="bg-[#1a1d24] px-5 py-4 border-b border-border/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            {/* Home Team */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#007a33] flex items-center justify-center">
                <span className="text-white text-sm font-bold">BOS</span>
              </div>
              <div>
                <div className="font-semibold text-foreground">Boston Celtics</div>
                <div className="text-2xl font-bold text-foreground">105</div>
              </div>
            </div>
            
            {/* VS / Final */}
            <div className="flex flex-col items-center">
              <span className="text-xs text-muted-foreground uppercase tracking-wider">Final</span>
            </div>
            
            {/* Away Team */}
            <div className="flex items-center gap-3">
              <div>
                <div className="font-semibold text-foreground text-right">Miami Heat</div>
                <div className="text-2xl font-bold text-foreground text-right">102</div>
              </div>
              <div className="w-10 h-10 rounded-lg bg-[#98002e] flex items-center justify-center">
                <span className="text-white text-sm font-bold">MIA</span>
              </div>
            </div>
          </div>
          
          <div className="text-right">
            <div className="text-xs text-muted-foreground">March 15, 2024</div>
            <div className="text-xs text-muted-foreground">TD Garden, Boston</div>
          </div>
        </div>
      </div>
      
      {/* Period markers legend */}
      <div className="px-5 py-2 bg-[#1a1d24]/50 border-b border-border/30 flex items-center gap-4 text-[10px] text-muted-foreground">
        <span>Q1</span>
        <div className="flex-1 h-px bg-border/30" />
        <span>Q2</span>
        <div className="flex-1 h-px bg-border/30" />
        <span>Halftime</span>
        <div className="flex-1 h-px bg-border/30" />
        <span>Q3</span>
        <div className="flex-1 h-px bg-border/30" />
        <span>Q4</span>
      </div>
      
      {/* Chart */}
      <div className="flex-1 p-4">
        <div className="h-72">
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
      
      {/* Source legend */}
      <div className="px-5 py-3 bg-[#1a1d24]/50 border-t border-border/30 flex items-center gap-4 text-[10px]">
        <span className="text-muted-foreground">Sources:</span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-[#f97316]" style={{ opacity: 0.8 }} />
          <span className="text-muted-foreground">ESPN</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-[#22c55e]" style={{ opacity: 0.8 }} />
          <span className="text-muted-foreground">Kalshi</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-[#3b82f6]" style={{ opacity: 0.8 }} />
          <span className="text-muted-foreground">Polymarket</span>
        </span>
        <span className="flex items-center gap-1.5 ml-2">
          <span className="w-4 h-0.5 bg-white rounded-full" />
          <span className="text-foreground font-medium">Aggregate</span>
        </span>
      </div>
    </div>
  );
}

// =============================================================================
// GOLF CHART (DataGolf-Inspired Multi-Participant Evolution)
// =============================================================================

interface GolfChartProps {
  highlightedPlayer: string | null;
  setHighlightedPlayer: (player: string | null) => void;
}

// More granular data: hole-by-hole for final round to show DataGolf-style detail
const GOLF_DETAILED_DATA = [
  // Pre-tournament through R3
  { hole: "Pre", label: "Pre", Scheffler: 18, McIlroy: 12, Rahm: 14, Koepka: 8, Hovland: 6, Morikawa: 5, Thomas: 4, Field: 33 },
  { hole: "R1", label: "R1", Scheffler: 22, McIlroy: 15, Rahm: 12, Koepka: 10, Hovland: 8, Morikawa: 4, Thomas: 3, Field: 26 },
  { hole: "R2", label: "R2", Scheffler: 28, McIlroy: 18, Rahm: 10, Koepka: 12, Hovland: 6, Morikawa: 3, Thomas: 2, Field: 21 },
  { hole: "R3", label: "R3", Scheffler: 35, McIlroy: 14, Rahm: 8, Koepka: 15, Hovland: 5, Morikawa: 2, Thomas: 1, Field: 20 },
  // Final round - hole by hole (every 3 holes for clarity)
  { hole: "F-3", label: "H3", Scheffler: 38, McIlroy: 12, Rahm: 7, Koepka: 18, Hovland: 4, Morikawa: 2, Thomas: 1, Field: 18 },
  { hole: "F-6", label: "H6", Scheffler: 42, McIlroy: 10, Rahm: 6, Koepka: 20, Hovland: 3, Morikawa: 1, Thomas: 1, Field: 17 },
  { hole: "F-9", label: "Turn", Scheffler: 45, McIlroy: 8, Rahm: 5, Koepka: 22, Hovland: 3, Morikawa: 1, Thomas: 1, Field: 15 },
  { hole: "F-12", label: "H12", Scheffler: 52, McIlroy: 6, Rahm: 4, Koepka: 20, Hovland: 2, Morikawa: 1, Thomas: 1, Field: 14 },
  { hole: "F-15", label: "H15", Scheffler: 58, McIlroy: 5, Rahm: 3, Koepka: 18, Hovland: 2, Morikawa: 1, Thomas: 0, Field: 13 },
  { hole: "F-18", label: "Final", Scheffler: 100, McIlroy: 0, Rahm: 0, Koepka: 0, Hovland: 0, Morikawa: 0, Thomas: 0, Field: 0 },
];

function GolfChart({ highlightedPlayer, setHighlightedPlayer }: GolfChartProps) {
  // Current leaderboard (from final data point)
  const leaderboard = GOLF_PLAYERS
    .map(p => ({ name: p.name, color: p.color, prob: GOLF_DETAILED_DATA[GOLF_DETAILED_DATA.length - 2][p.name as keyof typeof GOLF_DETAILED_DATA[0]] as number }))
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 6);

  return (
    <div className="flex flex-col h-full">
      {/* Tournament Header - DataGolf style with dark bg */}
      <div className="bg-[#1a1d24] px-5 py-4 border-b border-border/50">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold text-foreground">The Masters 2024</div>
            <div className="text-xs text-muted-foreground mt-0.5">Augusta National Golf Club - Final Round</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-muted-foreground">Live Model</div>
            <div className="text-sm font-medium text-foreground">Win Probability</div>
          </div>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Main Chart Area */}
        <div className="flex-1 p-4">
          {/* Clickable Player Legend - horizontal above chart */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
            {GOLF_PLAYERS.slice(0, 6).map((player) => (
              <button
                key={player.name}
                onClick={() => setHighlightedPlayer(
                  highlightedPlayer === player.name ? null : player.name
                )}
                className={`flex items-center gap-1.5 text-xs transition-all ${
                  highlightedPlayer && highlightedPlayer !== player.name
                    ? "opacity-25"
                    : "opacity-100"
                }`}
              >
                <div
                  className="w-3 h-0.5"
                  style={{ backgroundColor: player.color }}
                />
                <span className="text-muted-foreground hover:text-foreground">{player.name}</span>
              </button>
            ))}
          </div>

          {/* Chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={GOLF_DETAILED_DATA} margin={{ top: 10, right: 10, bottom: 5, left: 0 }}>
                {/* Subtle grid */}
                <CartesianGrid 
                  strokeDasharray="1 4" 
                  stroke="hsl(var(--border))" 
                  opacity={0.3}
                  horizontal={true}
                  vertical={false}
                />
                
                {/* Round separators as reference lines */}
                <ReferenceLine x="R1" stroke="hsl(var(--border))" strokeDasharray="2 2" opacity={0.5} />
                <ReferenceLine x="R2" stroke="hsl(var(--border))" strokeDasharray="2 2" opacity={0.5} />
                <ReferenceLine x="R3" stroke="hsl(var(--border))" strokeDasharray="2 2" opacity={0.5} />
                <ReferenceLine x="F-3" stroke="hsl(var(--border))" strokeDasharray="2 2" opacity={0.5} label={{ value: "Final Round", position: "top", fill: "hsl(var(--muted-foreground))", fontSize: 9 }} />
                
                <XAxis
                  dataKey="label"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={{ stroke: "hsl(var(--border))", opacity: 0.5 }}
                  tickLine={false}
                  interval={0}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `${value}%`}
                  width={35}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                    padding: "8px 12px",
                  }}
                  labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600, marginBottom: 4 }}
                  formatter={(value: number, name: string) => {
                    const player = GOLF_PLAYERS.find(p => p.name === name);
                    return [
                      <span key={name} style={{ color: player?.color }}>{value}%</span>,
                      name
                    ];
                  }}
                />
                
                {/* Lines - DataGolf uses thinner lines with dots at data points */}
                {GOLF_PLAYERS.map((player) => (
                  <Line
                    key={player.name}
                    type="monotone"
                    dataKey={player.name}
                    stroke={player.color}
                    strokeWidth={highlightedPlayer === player.name ? 2.5 : 1.5}
                    dot={false}
                    activeDot={{ 
                      r: 4, 
                      fill: player.color,
                      stroke: "hsl(var(--background))",
                      strokeWidth: 2
                    }}
                    opacity={
                      highlightedPlayer && highlightedPlayer !== player.name
                        ? 0.1
                        : 1
                    }
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Sidebar - Live Leaderboard (DataGolf style) */}
        <div className="w-44 border-l border-border/50 bg-[#1a1d24] p-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 font-medium">
            Win Probability
          </div>
          <div className="space-y-1.5">
            {leaderboard.map((player, i) => (
              <button
                key={player.name}
                onClick={() => setHighlightedPlayer(
                  highlightedPlayer === player.name ? null : player.name
                )}
                className={`w-full flex items-center justify-between py-1.5 px-2 rounded transition-all ${
                  highlightedPlayer === player.name ? "bg-white/5" : "hover:bg-white/5"
                } ${highlightedPlayer && highlightedPlayer !== player.name ? "opacity-30" : ""}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-muted-foreground w-3">{i + 1}</span>
                  <div
                    className="w-1 h-4 rounded-full"
                    style={{ backgroundColor: player.color }}
                  />
                  <span className="text-xs text-foreground">{player.name}</span>
                </div>
                <span 
                  className="text-sm font-mono font-medium"
                  style={{ color: player.color }}
                >
                  {player.prob}%
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// BRACKET CHART (Tournament Progression - Chart + Grid)
// =============================================================================

// More detailed bracket data with 8 teams
const BRACKET_DETAILED_TEAMS: BracketTeam[] = [
  { name: "UConn", seed: 1, color: "#0e1a36", probabilities: [
    { round: "Pre", prob: 0.15 }, { round: "R64", prob: 0.98 }, { round: "R32", prob: 0.88 }, 
    { round: "S16", prob: 0.65 }, { round: "E8", prob: 0.45 }, { round: "F4", prob: 0.28 }, { round: "Champ", prob: 0.18 }
  ]},
  { name: "Houston", seed: 1, color: "#c8102e", probabilities: [
    { round: "Pre", prob: 0.12 }, { round: "R64", prob: 0.97 }, { round: "R32", prob: 0.85 }, 
    { round: "S16", prob: 0.58 }, { round: "E8", prob: 0.38 }, { round: "F4", prob: 0.22 }, { round: "Champ", prob: 0.14 }
  ]},
  { name: "Purdue", seed: 1, color: "#ceb888", probabilities: [
    { round: "Pre", prob: 0.11 }, { round: "R64", prob: 0.96 }, { round: "R32", prob: 0.82 }, 
    { round: "S16", prob: 0.52 }, { round: "E8", prob: 0.32 }, { round: "F4", prob: 0.18 }, { round: "Champ", prob: 0.10 }
  ]},
  { name: "N. Carolina", seed: 1, color: "#7bafd4", probabilities: [
    { round: "Pre", prob: 0.10 }, { round: "R64", prob: 0.95 }, { round: "R32", prob: 0.78 }, 
    { round: "S16", prob: 0.48 }, { round: "E8", prob: 0.28 }, { round: "F4", prob: 0.15 }, { round: "Champ", prob: 0.08 }
  ]},
  { name: "Duke", seed: 4, color: "#003087", probabilities: [
    { round: "Pre", prob: 0.06 }, { round: "R64", prob: 0.78 }, { round: "R32", prob: 0.55 }, 
    { round: "S16", prob: 0.32 }, { round: "E8", prob: 0.18 }, { round: "F4", prob: 0.08 }, { round: "Champ", prob: 0.04 }
  ]},
  { name: "Tennessee", seed: 2, color: "#ff8200", probabilities: [
    { round: "Pre", prob: 0.07 }, { round: "R64", prob: 0.92 }, { round: "R32", prob: 0.72 }, 
    { round: "S16", prob: 0.42 }, { round: "E8", prob: 0.22 }, { round: "F4", prob: 0.10 }, { round: "Champ", prob: 0.05 }
  ]},
  { name: "Arizona", seed: 2, color: "#cc0033", probabilities: [
    { round: "Pre", prob: 0.08 }, { round: "R64", prob: 0.93 }, { round: "R32", prob: 0.74 }, 
    { round: "S16", prob: 0.44 }, { round: "E8", prob: 0.24 }, { round: "F4", prob: 0.12 }, { round: "Champ", prob: 0.06 }
  ]},
  { name: "Marquette", seed: 2, color: "#003366", probabilities: [
    { round: "Pre", prob: 0.05 }, { round: "R64", prob: 0.90 }, { round: "R32", prob: 0.68 }, 
    { round: "S16", prob: 0.38 }, { round: "E8", prob: 0.20 }, { round: "F4", prob: 0.09 }, { round: "Champ", prob: 0.04 }
  ]},
];

const BRACKET_ROUND_LABELS: Record<string, string> = {
  "Pre": "Pre-Tournament",
  "R64": "Round of 64",
  "R32": "Round of 32",
  "S16": "Sweet 16",
  "E8": "Elite 8",
  "F4": "Final Four",
  "Champ": "Champion",
};

function generateDetailedBracketData() {
  const rounds = ["Pre", "R64", "R32", "S16", "E8", "F4", "Champ"];
  return rounds.map((round) => {
    const dataPoint: Record<string, string | number> = { round };
    for (const team of BRACKET_DETAILED_TEAMS) {
      const roundData = team.probabilities.find(p => p.round === round);
      dataPoint[team.name] = roundData ? Math.round(roundData.prob * 100) : 0;
    }
    return dataPoint;
  });
}

function BracketChart() {
  const data = generateDetailedBracketData();
  const [highlightedTeam, setHighlightedTeam] = useState<string | null>(null);
  
  // Get current probabilities (Sweet 16 stage for demo)
  const currentRound = "S16";
  const currentProbs = BRACKET_DETAILED_TEAMS
    .map(team => ({
      ...team,
      currentProb: team.probabilities.find(p => p.round === currentRound)?.prob || 0
    }))
    .sort((a, b) => b.currentProb - a.currentProb);

  return (
    <div className="flex flex-col h-full">
      {/* Tournament Header */}
      <div className="bg-[#1a1d24] px-5 py-4 border-b border-border/50">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-semibold text-foreground">NCAA Tournament 2024</div>
            <div className="text-xs text-muted-foreground mt-0.5">Championship Probability Evolution</div>
          </div>
          <div className="px-3 py-1 bg-amber-500/20 text-amber-400 text-xs font-medium rounded">
            Sweet 16
          </div>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Main Chart */}
        <div className="flex-1 p-4">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 5, left: 0 }}>
                <CartesianGrid 
                  strokeDasharray="1 4" 
                  stroke="hsl(var(--border))" 
                  opacity={0.3}
                  horizontal={true}
                  vertical={false}
                />
                
                <XAxis
                  dataKey="round"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={{ stroke: "hsl(var(--border))", opacity: 0.5 }}
                  tickLine={false}
                  tickFormatter={(value) => BRACKET_ROUND_LABELS[value]?.split(" ")[0] || value}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 25, 50, 75, 100]}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `${value}%`}
                  width={35}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                    padding: "8px 12px",
                  }}
                  labelStyle={{ color: "hsl(var(--foreground))", fontWeight: 600, marginBottom: 4 }}
                  labelFormatter={(label) => BRACKET_ROUND_LABELS[label] || label}
                  formatter={(value: number, name: string) => {
                    const team = BRACKET_DETAILED_TEAMS.find(t => t.name === name);
                    return [
                      <span key={name} style={{ color: team?.color }}>{value}%</span>,
                      `(${team?.seed}) ${name}`
                    ];
                  }}
                />
                
                {/* Current round indicator */}
                <ReferenceLine 
                  x={currentRound} 
                  stroke="hsl(var(--muted-foreground))" 
                  strokeDasharray="4 4" 
                  opacity={0.5}
                />
                
                {BRACKET_DETAILED_TEAMS.map((team) => (
                  <Line
                    key={team.name}
                    type="monotone"
                    dataKey={team.name}
                    stroke={team.color}
                    strokeWidth={highlightedTeam === team.name ? 2.5 : 1.5}
                    dot={false}
                    activeDot={{ 
                      r: 4, 
                      fill: team.color,
                      stroke: "hsl(var(--background))",
                      strokeWidth: 2
                    }}
                    opacity={
                      highlightedTeam && highlightedTeam !== team.name
                        ? 0.1
                        : 1
                    }
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Sidebar - Championship Odds Grid */}
        <div className="w-52 border-l border-border/50 bg-[#1a1d24] p-3 overflow-y-auto">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-3 font-medium">
            Championship Odds
          </div>
          
          {/* Grid header */}
          <div className="grid grid-cols-[1fr_auto_auto] gap-1 text-[9px] text-muted-foreground mb-1 px-1">
            <span>Team</span>
            <span className="text-center w-10">Now</span>
            <span className="text-center w-10">Pre</span>
          </div>
          
          {/* Teams */}
          <div className="space-y-0.5">
            {currentProbs.map((team, i) => {
              const preProb = team.probabilities.find(p => p.round === "Pre")?.prob || 0;
              const change = team.currentProb - preProb;
              
              return (
                <button
                  key={team.name}
                  onClick={() => setHighlightedTeam(
                    highlightedTeam === team.name ? null : team.name
                  )}
                  className={`w-full grid grid-cols-[1fr_auto_auto] gap-1 items-center py-1.5 px-1 rounded transition-all text-left ${
                    highlightedTeam === team.name ? "bg-white/10" : "hover:bg-white/5"
                  } ${highlightedTeam && highlightedTeam !== team.name ? "opacity-30" : ""}`}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <div
                      className="w-1 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: team.color }}
                    />
                    <span className="text-[10px] text-muted-foreground w-3 flex-shrink-0">{team.seed}</span>
                    <span className="text-xs text-foreground truncate">{team.name}</span>
                  </div>
                  <span 
                    className="text-xs font-mono font-medium text-center w-10"
                    style={{ color: team.color }}
                  >
                    {Math.round(team.currentProb * 100)}%
                  </span>
                  <span className={`text-[10px] font-mono text-center w-10 ${
                    change > 0 ? "text-green-400" : change < 0 ? "text-red-400" : "text-muted-foreground"
                  }`}>
                    {change > 0 ? "+" : ""}{Math.round(change * 100)}
                  </span>
                </button>
              );
            })}
          </div>
          
          {/* Source attribution */}
          <div className="mt-4 pt-3 border-t border-border/30">
            <div className="text-[9px] text-muted-foreground">
              Data: ESPN, Kalshi, FiveThirtyEight
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
