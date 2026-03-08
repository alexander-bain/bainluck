"use client";

/**
 * Win Probability Demo
 * 
 * Two views:
 * 1. Two-Team (NBA/NFL/MLB) — OddsChart with period markers integrated
 * 2. Tournament (DataGolf-inspired) — Evolution plot + sortable grid
 */

import { useState } from "react";
import OddsChart from "@/components/OddsChart";
import type { OddsHistoryPoint, WinProbHistoryPoint, WinProbSourceMeta } from "@/lib/types";
import type { PeriodBoundary } from "@/lib/periodMarkers";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
} from "recharts";

// =============================================================================
// TWO-TEAM MOCK DATA (NBA)
// =============================================================================

const NBA_COMMENCE_TIME = "2024-03-15T19:30:00Z";

function generateNBAOddsHistory(): OddsHistoryPoint[] {
  const points: OddsHistoryPoint[] = [];
  const baseTime = new Date(NBA_COMMENCE_TIME);
  
  const probCurve = [
    { minute: -60, prob: 0.58 }, { minute: -30, prob: 0.57 }, { minute: 0, prob: 0.56 },
    { minute: 3, prob: 0.62 }, { minute: 6, prob: 0.65 }, { minute: 9, prob: 0.63 }, { minute: 12, prob: 0.60 },
    { minute: 15, prob: 0.55 }, { minute: 18, prob: 0.48 }, { minute: 21, prob: 0.42 }, { minute: 24, prob: 0.38 },
    { minute: 27, prob: 0.35 }, { minute: 30, prob: 0.32 }, { minute: 33, prob: 0.28 }, { minute: 36, prob: 0.25 },
    { minute: 39, prob: 0.30 }, { minute: 42, prob: 0.38 }, { minute: 44, prob: 0.45 }, { minute: 46, prob: 0.55 },
    { minute: 47, prob: 0.65 }, { minute: 48, prob: 0.78 },
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

function generateNBAWinProbHistory(): Record<string, WinProbHistoryPoint[]> {
  const baseTime = new Date(NBA_COMMENCE_TIME);
  const sources: Record<string, WinProbHistoryPoint[]> = { espn: [], kalshi: [], polymarket: [] };
  const baseProbCurve = [0.56, 0.62, 0.65, 0.63, 0.60, 0.55, 0.48, 0.42, 0.38, 0.35, 0.32, 0.28, 0.25, 0.30, 0.38, 0.45, 0.55, 0.65, 0.78];
  const minutes = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 44, 46, 47, 48];
  
  minutes.forEach((minute, i) => {
    const timestamp = new Date(baseTime.getTime() + minute * 60 * 1000).toISOString();
    const baseProb = baseProbCurve[i];
    sources.espn.push({ timestamp, home_probability: Math.min(1, Math.max(0, baseProb + (Math.random() - 0.5) * 0.04)) });
    sources.kalshi.push({ timestamp, home_probability: Math.min(1, Math.max(0, baseProb + (Math.random() - 0.5) * 0.04)) });
    sources.polymarket.push({ timestamp, home_probability: Math.min(1, Math.max(0, baseProb + (Math.random() - 0.5) * 0.04)) });
  });
  return sources;
}

const NBA_WIN_PROB_SOURCES: WinProbSourceMeta[] = [
  { key: "espn", label: "ESPN", color: "#f97316" },
  { key: "kalshi", label: "Kalshi", color: "#22c55e" },
  { key: "polymarket", label: "Polymarket", color: "#3b82f6" },
];

const NBA_PERIOD_BOUNDARIES: PeriodBoundary[] = [
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 12 * 60 * 1000).toISOString(), label: "Q1" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 24 * 60 * 1000).toISOString(), label: "Q2" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 36 * 60 * 1000).toISOString(), label: "Q3" },
  { timestamp: new Date(new Date(NBA_COMMENCE_TIME).getTime() + 48 * 60 * 1000).toISOString(), label: "Q4" },
];

// =============================================================================
// TOURNAMENT MOCK DATA (Golf - DataGolf inspired)
// =============================================================================

interface Player {
  id: string;
  name: string;
  firstName: string;
  lastName: string;
  country: string;
  color: string;
  score: number;
  thru: string;
  today: number;
  probabilities: { top20: number; top10: number; top5: number; win: number };
  trend: number; // change in win% over last update
  history: { time: string; prob: number }[];
}

const TOURNAMENT_PLAYERS: Player[] = [
  {
    id: "berger", name: "Daniel Berger", firstName: "Daniel", lastName: "BERGER", country: "USA", color: "#e74c3c",
    score: -13, thru: "15", today: 0,
    probabilities: { top20: 99.7, top10: 97.8, top5: 91.6, win: 50.5 },
    trend: 2.5,
    history: [
      { time: "Thu-AM", prob: 3 }, { time: "Thu-PM", prob: 8 }, { time: "Fri-AM", prob: 12 }, { time: "Fri-PM", prob: 18 },
      { time: "Sat-AM", prob: 28 }, { time: "Sat-PM", prob: 42 }, { time: "Sun-AM", prob: 48 }, { time: "Sun-Now", prob: 50.5 },
    ],
  },
  {
    id: "bhatia", name: "Akshay Bhatia", firstName: "Akshay", lastName: "BHATIA", country: "USA", color: "#3498db",
    score: -11, thru: "16", today: -3,
    probabilities: { top20: 98.5, top10: 90.4, top5: 72.0, win: 14.8 },
    trend: 26.2,
    history: [
      { time: "Thu-AM", prob: 1 }, { time: "Thu-PM", prob: 2 }, { time: "Fri-AM", prob: 4 }, { time: "Fri-PM", prob: 6 },
      { time: "Sat-AM", prob: 8 }, { time: "Sat-PM", prob: 10 }, { time: "Sun-AM", prob: 12 }, { time: "Sun-Now", prob: 14.8 },
    ],
  },
  {
    id: "young", name: "Cameron Young", firstName: "Cameron", lastName: "YOUNG", country: "USA", color: "#27ae60",
    score: -9, thru: "F", today: -5,
    probabilities: { top20: 97.8, top10: 87.1, top5: 63.6, win: 9.1 },
    trend: 44.0,
    history: [
      { time: "Thu-AM", prob: 2 }, { time: "Thu-PM", prob: 3 }, { time: "Fri-AM", prob: 4 }, { time: "Fri-PM", prob: 5 },
      { time: "Sat-AM", prob: 5 }, { time: "Sat-PM", prob: 6 }, { time: "Sun-AM", prob: 7 }, { time: "Sun-Now", prob: 9.1 },
    ],
  },
  {
    id: "morikawa", name: "Collin Morikawa", firstName: "Collin", lastName: "MORIKAWA", country: "USA", color: "#9b59b6",
    score: -9, thru: "F", today: -2,
    probabilities: { top20: 97.9, top10: 86.6, top5: 62.2, win: 8.1 },
    trend: 15.9,
    history: [
      { time: "Thu-AM", prob: 5 }, { time: "Thu-PM", prob: 6 }, { time: "Fri-AM", prob: 6 }, { time: "Fri-PM", prob: 7 },
      { time: "Sat-AM", prob: 7 }, { time: "Sat-PM", prob: 7 }, { time: "Sun-AM", prob: 8 }, { time: "Sun-Now", prob: 8.1 },
    ],
  },
  {
    id: "straka", name: "Sepp Straka", firstName: "Sepp", lastName: "STRAKA", country: "AUT", color: "#e67e22",
    score: -9, thru: "F", today: -6,
    probabilities: { top20: 97.0, top10: 83.0, top5: 55.9, win: 6.0 },
    trend: 58.6,
    history: [
      { time: "Thu-AM", prob: 1 }, { time: "Thu-PM", prob: 2 }, { time: "Fri-AM", prob: 2 }, { time: "Fri-PM", prob: 3 },
      { time: "Sat-AM", prob: 3 }, { time: "Sat-PM", prob: 4 }, { time: "Sun-AM", prob: 5 }, { time: "Sun-Now", prob: 6.0 },
    ],
  },
  {
    id: "lee", name: "Min Woo Lee", firstName: "Min Woo", lastName: "LEE", country: "AUS", color: "#1abc9c",
    score: -8, thru: "F", today: -4,
    probabilities: { top20: 95.9, top10: 78.9, top5: 49.4, win: 4.6 },
    trend: 37.4,
    history: [
      { time: "Thu-AM", prob: 2 }, { time: "Thu-PM", prob: 3 }, { time: "Fri-AM", prob: 3 }, { time: "Fri-PM", prob: 4 },
      { time: "Sat-AM", prob: 4 }, { time: "Sat-PM", prob: 4 }, { time: "Sun-AM", prob: 4 }, { time: "Sun-Now", prob: 4.6 },
    ],
  },
  {
    id: "gotterup", name: "Chris Gotterup", firstName: "Chris", lastName: "GOTTERUP", country: "USA", color: "#34495e",
    score: -7, thru: "F", today: -3,
    probabilities: { top20: 90.6, top10: 63.1, top5: 30.6, win: 1.7 },
    trend: 27.7,
    history: [
      { time: "Thu-AM", prob: 0.5 }, { time: "Thu-PM", prob: 0.8 }, { time: "Fri-AM", prob: 1 }, { time: "Fri-PM", prob: 1.2 },
      { time: "Sat-AM", prob: 1.3 }, { time: "Sat-PM", prob: 1.5 }, { time: "Sun-AM", prob: 1.6 }, { time: "Sun-Now", prob: 1.7 },
    ],
  },
  {
    id: "aberg", name: "Ludvig Aberg", firstName: "Ludvig", lastName: "ABERG", country: "SWE", color: "#f39c12",
    score: -7, thru: "16", today: 0,
    probabilities: { top20: 88.9, top10: 60.1, top5: 28.9, win: 1.8 },
    trend: -7.5,
    history: [
      { time: "Thu-AM", prob: 4 }, { time: "Thu-PM", prob: 5 }, { time: "Fri-AM", prob: 4 }, { time: "Fri-PM", prob: 3 },
      { time: "Sat-AM", prob: 3 }, { time: "Sat-PM", prob: 2.5 }, { time: "Sun-AM", prob: 2 }, { time: "Sun-Now", prob: 1.8 },
    ],
  },
  {
    id: "fowler", name: "Rickie Fowler", firstName: "Rickie", lastName: "FOWLER", country: "USA", color: "#e91e63",
    score: -6, thru: "F", today: 0,
    probabilities: { top20: 85.9, top10: 51.0, top5: 19.2, win: 0.7 },
    trend: -8.3,
    history: [
      { time: "Thu-AM", prob: 3 }, { time: "Thu-PM", prob: 2.5 }, { time: "Fri-AM", prob: 2 }, { time: "Fri-PM", prob: 1.5 },
      { time: "Sat-AM", prob: 1.2 }, { time: "Sat-PM", prob: 1 }, { time: "Sun-AM", prob: 0.8 }, { time: "Sun-Now", prob: 0.7 },
    ],
  },
  {
    id: "henley", name: "Russell Henley", firstName: "Russell", lastName: "HENLEY", country: "USA", color: "#607d8b",
    score: -6, thru: "F", today: -1,
    probabilities: { top20: 87.2, top10: 52.5, top5: 19.8, win: 0.6 },
    trend: 3.5,
    history: [
      { time: "Thu-AM", prob: 0.4 }, { time: "Thu-PM", prob: 0.5 }, { time: "Fri-AM", prob: 0.5 }, { time: "Fri-PM", prob: 0.5 },
      { time: "Sat-AM", prob: 0.5 }, { time: "Sat-PM", prob: 0.6 }, { time: "Sun-AM", prob: 0.6 }, { time: "Sun-Now", prob: 0.6 },
    ],
  },
];

// Transform player histories for chart
function getChartData() {
  const times = ["Thu-AM", "Thu-PM", "Fri-AM", "Fri-PM", "Sat-AM", "Sat-PM", "Sun-AM", "Sun-Now"];
  return times.map((time) => {
    const point: Record<string, string | number> = { time };
    TOURNAMENT_PLAYERS.forEach((player) => {
      const historyPoint = player.history.find((h) => h.time === time);
      point[player.id] = historyPoint?.prob ?? 0;
    });
    return point;
  });
}

const COUNTRY_FLAGS: Record<string, string> = {
  USA: "🇺🇸", AUS: "🇦🇺", AUT: "🇦🇹", SWE: "🇸🇪", ENG: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", CAN: "🇨🇦", JPN: "🇯🇵", KOR: "🇰🇷",
};

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function WinProbabilityDemo() {
  const [activeView, setActiveView] = useState<"two-team" | "tournament">("two-team");

  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <h1 className="text-xl font-semibold text-foreground">Win Probability Charts</h1>
          <p className="text-sm text-muted-foreground mt-1">Demo page with two-team and tournament views</p>
        </div>
      </div>

      {/* View Toggle */}
      <div className="border-b border-border bg-card">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex gap-1">
            <button
              onClick={() => setActiveView("two-team")}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeView === "two-team"
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Two-Team (NBA)
            </button>
            <button
              onClick={() => setActiveView("tournament")}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeView === "tournament"
                  ? "border-foreground text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              Tournament (Golf)
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        {activeView === "two-team" ? <TwoTeamView /> : <TournamentView />}
      </div>
    </main>
  );
}

// =============================================================================
// TWO-TEAM VIEW
// =============================================================================

function TwoTeamView() {
  const history = generateNBAOddsHistory();
  const winProbHistory = generateNBAWinProbHistory();

  return (
    <div className="bg-card rounded-lg border border-border overflow-hidden">
      {/* Game Header */}
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-8">
          {/* Home Team */}
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-lg bg-[#007a33] flex items-center justify-center">
              <span className="text-white text-sm font-bold">BOS</span>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Boston</div>
              <div className="text-2xl font-bold text-foreground">105</div>
            </div>
          </div>
          
          <div className="text-sm text-muted-foreground font-medium">FINAL</div>
          
          {/* Away Team */}
          <div className="flex items-center gap-3">
            <div>
              <div className="text-sm text-muted-foreground text-right">Miami</div>
              <div className="text-2xl font-bold text-foreground text-right">102</div>
            </div>
            <div className="w-12 h-12 rounded-lg bg-[#98002e] flex items-center justify-center">
              <span className="text-white text-sm font-bold">MIA</span>
            </div>
          </div>
        </div>
        
        <div className="text-right text-sm text-muted-foreground">
          <div>March 15, 2024</div>
          <div>TD Garden, Boston</div>
        </div>
      </div>
      
      {/* Source Legend */}
      <div className="px-6 py-2 border-b border-border flex items-center gap-6 text-xs">
        <span className="text-muted-foreground">Sources:</span>
        {NBA_WIN_PROB_SOURCES.map((source) => (
          <span key={source.key} className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 rounded" style={{ backgroundColor: source.color }} />
            <span className="text-muted-foreground">{source.label}</span>
          </span>
        ))}
        <span className="flex items-center gap-1.5 ml-2">
          <span className="w-4 h-0.5 bg-foreground rounded-full" />
          <span className="text-foreground font-medium">Aggregate</span>
        </span>
      </div>
      
      {/* Chart */}
      <div className="p-4 h-96">
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
// TOURNAMENT VIEW (DataGolf-inspired)
// =============================================================================

function TournamentView() {
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>(["berger", "bhatia", "young"]);
  const [timeRange, setTimeRange] = useState<"full" | "current">("full");
  const [probColumn, setProbColumn] = useState<"win" | "top5" | "top10" | "top20">("win");
  const chartData = getChartData();

  const togglePlayer = (playerId: string) => {
    setSelectedPlayers((prev) =>
      prev.includes(playerId) ? prev.filter((id) => id !== playerId) : [...prev, playerId]
    );
  };

  // Sort players by selected probability column
  const sortedPlayers = [...TOURNAMENT_PLAYERS].sort(
    (a, b) => b.probabilities[probColumn] - a.probabilities[probColumn]
  );

  return (
    <div className="bg-card rounded-lg border border-border overflow-hidden">
      {/* Tournament Header */}
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <div>
            <div className="text-lg font-semibold text-foreground">Arnold Palmer Invitational</div>
            <div className="text-sm text-muted-foreground">Bay Hill Club &amp; Lodge - Round 4</div>
          </div>
        </div>
        <div className="text-right text-sm text-muted-foreground">
          <div>Updated 2 hours ago</div>
        </div>
      </div>

      {/* Controls Row */}
      <div className="px-6 py-3 border-b border-border flex items-center justify-between bg-muted/30">
        {/* Time Range */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wider mr-2">Time Range</span>
          <div className="flex rounded-md overflow-hidden border border-border">
            <button
              onClick={() => setTimeRange("full")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                timeRange === "full" ? "bg-foreground text-background" : "bg-card text-muted-foreground hover:bg-muted"
              }`}
            >
              Full Event
            </button>
            <button
              onClick={() => setTimeRange("current")}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                timeRange === "current" ? "bg-foreground text-background" : "bg-card text-muted-foreground hover:bg-muted"
              }`}
            >
              Current Round
            </button>
          </div>
        </div>

        {/* Finish Position */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wider mr-2">Finish Position</span>
          <div className="flex rounded-md overflow-hidden border border-border">
            {(["top20", "top10", "top5", "win"] as const).map((col) => (
              <button
                key={col}
                onClick={() => setProbColumn(col)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  probColumn === col ? "bg-foreground text-background" : "bg-card text-muted-foreground hover:bg-muted"
                }`}
              >
                {col === "win" ? "Win" : col.toUpperCase().replace("TOP", "Top ")}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Evolution Plot */}
      <div className="px-6 py-4 border-b border-border">
        <div className="flex gap-6">
          {/* Chart */}
          <div className="flex-1 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 10, bottom: 5, left: 0 }}>
                {/* Day backgrounds */}
                <ReferenceArea x1="Thu-AM" x2="Thu-PM" fill="hsl(var(--muted))" fillOpacity={0.15} />
                <ReferenceArea x1="Fri-AM" x2="Fri-PM" fill="hsl(var(--muted))" fillOpacity={0.3} />
                <ReferenceArea x1="Sat-AM" x2="Sat-PM" fill="hsl(var(--muted))" fillOpacity={0.15} />
                <ReferenceArea x1="Sun-AM" x2="Sun-Now" fill="hsl(var(--muted))" fillOpacity={0.3} />

                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} vertical={false} />
                
                <XAxis
                  dataKey="time"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={{ stroke: "hsl(var(--border))" }}
                  tickLine={false}
                  tickFormatter={(value) => {
                    if (value.includes("AM")) return value.replace("-AM", "");
                    return "";
                  }}
                />
                <YAxis
                  domain={[0, "auto"]}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value) => `${value}%`}
                  width={40}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                  }}
                  labelFormatter={(label) => {
                    const day = label.split("-")[0];
                    const half = label.includes("AM") ? "Morning" : label.includes("PM") ? "Afternoon" : "Now";
                    return `${day} ${half}`;
                  }}
                  formatter={(value: number, name: string) => {
                    const player = TOURNAMENT_PLAYERS.find((p) => p.id === name);
                    return [`${value.toFixed(1)}%`, player?.name || name];
                  }}
                />

                {TOURNAMENT_PLAYERS.map((player) => (
                  <Line
                    key={player.id}
                    type="monotone"
                    dataKey={player.id}
                    stroke={player.color}
                    strokeWidth={selectedPlayers.includes(player.id) ? 2.5 : 1}
                    dot={false}
                    opacity={selectedPlayers.length === 0 || selectedPlayers.includes(player.id) ? 1 : 0.15}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Add Players Panel */}
          <div className="w-48 border-l border-border pl-4">
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-3">Add Players to Plot</div>
            <div className="space-y-1 max-h-56 overflow-y-auto">
              {TOURNAMENT_PLAYERS.slice(0, 8).map((player) => (
                <button
                  key={player.id}
                  onClick={() => togglePlayer(player.id)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left hover:bg-muted/50 transition-colors"
                >
                  <div
                    className={`w-2 h-2 rounded-full ${selectedPlayers.includes(player.id) ? "" : "opacity-30"}`}
                    style={{ backgroundColor: player.color }}
                  />
                  <span className={`text-xs ${selectedPlayers.includes(player.id) ? "text-foreground" : "text-muted-foreground"}`}>
                    {player.lastName}, {player.firstName.charAt(0)}.
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-12">Pos</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Player</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-16">Score</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-14">Thru</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-14">Today</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20">Top 20</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20">Top 10</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20">Top 5</th>
              <th className={`px-4 py-3 text-center text-xs font-medium uppercase tracking-wider w-20 ${probColumn === "win" ? "bg-green-500/10 text-green-600" : "text-muted-foreground"}`}>Win</th>
              <th className="px-4 py-3 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20">Trend</th>
            </tr>
          </thead>
          <tbody>
            {sortedPlayers.map((player, index) => {
              const position = index + 1;
              const isTied = index > 0 && sortedPlayers[index - 1].probabilities[probColumn] === player.probabilities[probColumn];
              const posDisplay = isTied ? `T${position}` : position;

              return (
                <tr
                  key={player.id}
                  className="border-b border-border hover:bg-muted/30 transition-colors"
                >
                  <td className="px-4 py-3 text-muted-foreground">{posDisplay}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-base">{COUNTRY_FLAGS[player.country] || "🏳️"}</span>
                      <span className="font-medium text-foreground">{player.lastName}</span>
                      <span className="text-muted-foreground">{player.firstName}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-flex items-center justify-center px-2 py-0.5 rounded text-xs font-semibold ${
                      player.score < 0 ? "bg-red-500 text-white" : player.score === 0 ? "bg-gray-400 text-white" : "bg-blue-500 text-white"
                    }`}>
                      {player.score > 0 ? `+${player.score}` : player.score === 0 ? "E" : player.score}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-muted-foreground">{player.thru}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={player.today < 0 ? "text-red-500" : player.today > 0 ? "text-blue-500" : "text-muted-foreground"}>
                      {player.today > 0 ? `+${player.today}` : player.today === 0 ? "E" : player.today}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-muted-foreground">{player.probabilities.top20.toFixed(1)}%</td>
                  <td className="px-4 py-3 text-center text-muted-foreground">{player.probabilities.top10.toFixed(1)}%</td>
                  <td className="px-4 py-3 text-center text-muted-foreground">{player.probabilities.top5.toFixed(1)}%</td>
                  <td className={`px-4 py-3 text-center font-semibold ${probColumn === "win" ? "bg-green-500/10 text-green-600" : "text-foreground"}`}>
                    {player.probabilities.win.toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`flex items-center justify-center gap-0.5 text-xs font-medium ${
                      player.trend > 0 ? "text-green-600" : player.trend < 0 ? "text-red-500" : "text-muted-foreground"
                    }`}>
                      {player.trend > 0 ? "▲" : player.trend < 0 ? "▼" : "—"}
                      {player.trend !== 0 && `${Math.abs(player.trend).toFixed(1)}%`}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
