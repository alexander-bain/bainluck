"use client";

/**
 * Win Probability Charts Demo
 * 
 * 4 distinct chart styles inspired by:
 * 1. 538 - Stepped area chart with 50% baseline, dramatic color fills
 * 2. Kalshi - Clean line with gradient fill and confidence bands
 * 3. MoneyPuck - Team-branded with period markers and scoring annotations
 * 4. DataGolf - Multi-participant evolution plot for tournaments
 */

import { useState } from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  Legend,
  ComposedChart,
} from "recharts";
import { motion } from "framer-motion";

// =============================================================================
// MOCK DATA
// =============================================================================

// NBA game: Celtics vs Heat (dramatic comeback)
const nbaGameData = generateNBAGameData();

function generateNBAGameData() {
  const data: Array<{
    time: number;
    minute: string;
    period: string;
    homeProb: number;
    awayProb: number;
    homeScore: number;
    awayScore: number;
    event?: string;
  }> = [];
  
  let homeProb = 0.52;
  let homeScore = 0;
  let awayScore = 0;
  
  // Generate 48 minutes of game data
  for (let i = 0; i <= 48; i++) {
    const period = i <= 12 ? "Q1" : i <= 24 ? "Q2" : i <= 36 ? "Q3" : "Q4";
    const periodMinute = i % 12;
    
    // Simulate game flow with momentum swings
    const swing = Math.sin(i * 0.3) * 0.15 + (Math.random() - 0.5) * 0.08;
    homeProb = Math.max(0.05, Math.min(0.95, homeProb + swing));
    
    // Dramatic moments
    if (i === 24) { homeProb = 0.35; } // Halftime deficit
    if (i === 36) { homeProb = 0.28; } // End of Q3 down big
    if (i === 42) { homeProb = 0.45; } // Comeback starts
    if (i === 46) { homeProb = 0.72; } // Lead change
    if (i === 48) { homeProb = 0.88; } // Final stretch
    
    // Simulate scores
    if (i > 0 && Math.random() > 0.4) {
      if (Math.random() > 0.5) {
        homeScore += Math.random() > 0.7 ? 3 : 2;
      } else {
        awayScore += Math.random() > 0.7 ? 3 : 2;
      }
    }
    
    data.push({
      time: i,
      minute: `${period} ${12 - periodMinute}:00`,
      period,
      homeProb: Math.round(homeProb * 100),
      awayProb: Math.round((1 - homeProb) * 100),
      homeScore,
      awayScore,
      event: i === 42 ? "Tatum 3-pointer" : i === 46 ? "Brown steal & dunk" : undefined,
    });
  }
  
  return data;
}

// Golf tournament: 8 players over 4 rounds
const golfTournamentData = generateGolfData();

function generateGolfData() {
  const players = [
    { name: "Scottie Scheffler", color: "#e63946" },
    { name: "Rory McIlroy", color: "#457b9d" },
    { name: "Jon Rahm", color: "#2a9d8f" },
    { name: "Viktor Hovland", color: "#f4a261" },
    { name: "Xander Schauffele", color: "#9b5de5" },
    { name: "Collin Morikawa", color: "#00b4d8" },
    { name: "Patrick Cantlay", color: "#90be6d" },
    { name: "Brooks Koepka", color: "#ff006e" },
  ];
  
  const data: Array<Record<string, number | string>> = [];
  
  // 72 holes (4 rounds of 18)
  for (let hole = 0; hole <= 72; hole += 4) {
    const round = Math.floor(hole / 18) + 1;
    const holeInRound = hole % 18;
    
    const point: Record<string, number | string> = {
      hole,
      label: hole === 0 ? "Start" : `R${round} H${holeInRound || 18}`,
    };
    
    players.forEach((player, idx) => {
      // Start with roughly equal probabilities
      let baseProb = 12.5;
      
      // Add some variation based on "performance"
      const performance = Math.sin(hole * 0.1 + idx) * 5 + (Math.random() - 0.5) * 3;
      
      // Leader emerges
      if (idx === 0 && hole > 36) {
        baseProb = 25 + (hole - 36) * 0.5;
      }
      
      // Late surge
      if (idx === 1 && hole > 54) {
        baseProb = 20 + (hole - 54) * 0.8;
      }
      
      point[player.name] = Math.max(1, Math.min(50, baseProb + performance));
    });
    
    data.push(point);
  }
  
  return { data, players };
}

// NHL game with period markers
const nhlGameData = generateNHLData();

function generateNHLData() {
  const data: Array<{
    time: number;
    minute: string;
    period: number;
    homeProb: number;
    awayProb: number;
    homeScore: number;
    awayScore: number;
    goal?: { team: "home" | "away"; scorer: string };
  }> = [];
  
  let homeProb = 0.48;
  let homeScore = 0;
  let awayScore = 0;
  
  const goals = [
    { time: 8, team: "away" as const, scorer: "Matthews" },
    { time: 23, team: "home" as const, scorer: "Pastrnak" },
    { time: 31, team: "home" as const, scorer: "Marchand" },
    { time: 45, team: "away" as const, scorer: "Marner" },
    { time: 58, team: "home" as const, scorer: "Bergeron" },
  ];
  
  for (let i = 0; i <= 60; i++) {
    const period = i <= 20 ? 1 : i <= 40 ? 2 : 3;
    const periodMinute = i % 20;
    
    // Check for goals
    const goal = goals.find(g => g.time === i);
    if (goal) {
      if (goal.team === "home") {
        homeScore++;
        homeProb = Math.min(0.95, homeProb + 0.15);
      } else {
        awayScore++;
        homeProb = Math.max(0.05, homeProb - 0.15);
      }
    }
    
    // Natural drift
    homeProb += (Math.random() - 0.5) * 0.02;
    homeProb = Math.max(0.05, Math.min(0.95, homeProb));
    
    data.push({
      time: i,
      minute: `${period}P ${periodMinute}:00`,
      period,
      homeProb: Math.round(homeProb * 100),
      awayProb: Math.round((1 - homeProb) * 100),
      homeScore,
      awayScore,
      goal,
    });
  }
  
  return data;
}

// =============================================================================
// CHART VARIANTS
// =============================================================================

// Variant 1: 538-Style Stepped Area Chart
function FiveThirtyEightChart({ data }: { data: typeof nbaGameData }) {
  return (
    <div className="bg-surface-card rounded-lg p-4 border border-surface-border">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">538-Style</h3>
          <p className="text-sm text-text-muted">Stepped area with 50% baseline</p>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#17A34A]" />
            <span className="text-text-secondary">Celtics</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#EF4444]" />
            <span className="text-text-secondary">Heat</span>
          </div>
        </div>
      </div>
      
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="homeGradient538" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#17A34A" stopOpacity={0.8} />
                <stop offset="100%" stopColor="#17A34A" stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="awayGradient538" x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor="#EF4444" stopOpacity={0.8} />
                <stop offset="100%" stopColor="#EF4444" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis 
              dataKey="minute" 
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              interval={11}
            />
            <YAxis 
              domain={[0, 100]}
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
              ticks={[0, 25, 50, 75, 100]}
            />
            <ReferenceLine y={50} stroke="rgba(255,255,255,0.3)" strokeDasharray="4 4" />
            
            {/* Period separators */}
            <ReferenceLine x="Q2 12:00" stroke="rgba(255,255,255,0.2)" />
            <ReferenceLine x="Q3 12:00" stroke="rgba(255,255,255,0.2)" />
            <ReferenceLine x="Q4 12:00" stroke="rgba(255,255,255,0.2)" />
            
            <Area
              type="stepAfter"
              dataKey="homeProb"
              stroke="#17A34A"
              strokeWidth={2}
              fill="url(#homeGradient538)"
              isAnimationActive={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgb(var(--surface-elevated))",
                border: "1px solid rgb(var(--surface-border))",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number, name: string) => [
                `${value}%`,
                name === "homeProb" ? "Celtics" : "Heat"
              ]}
              labelFormatter={(label) => label}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      
      {/* Score display */}
      <div className="flex justify-center gap-8 mt-4 pt-4 border-t border-surface-border">
        <div className="text-center">
          <div className="text-2xl font-bold text-[#17A34A]">
            {data[data.length - 1].homeScore}
          </div>
          <div className="text-xs text-text-muted">BOS</div>
        </div>
        <div className="text-sm text-text-muted self-center">FINAL</div>
        <div className="text-center">
          <div className="text-2xl font-bold text-[#EF4444]">
            {data[data.length - 1].awayScore}
          </div>
          <div className="text-xs text-text-muted">MIA</div>
        </div>
      </div>
    </div>
  );
}

// Variant 2: Kalshi-Style Clean Line with Confidence Band
function KalshiChart({ data }: { data: typeof nbaGameData }) {
  // Add confidence bands
  const dataWithBands = data.map(d => ({
    ...d,
    upper: Math.min(100, d.homeProb + 8),
    lower: Math.max(0, d.homeProb - 8),
  }));
  
  return (
    <div className="bg-surface-card rounded-lg p-4 border border-surface-border">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Kalshi-Style</h3>
          <p className="text-sm text-text-muted">Clean line with confidence bands</p>
        </div>
        <div className="flex items-center gap-2 bg-surface-elevated px-3 py-1.5 rounded-full">
          <span className="text-2xl font-bold text-text-primary">
            {data[data.length - 1].homeProb}%
          </span>
          <span className="text-sm text-text-muted">win prob</span>
        </div>
      </div>
      
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={dataWithBands} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="kalshiGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#3B82F6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="kalshiBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3B82F6" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#3B82F6" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
            <XAxis 
              dataKey="time" 
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickFormatter={(v) => v === 0 ? "Start" : v === 24 ? "Half" : v === 48 ? "End" : ""}
            />
            <YAxis 
              domain={[0, 100]}
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <ReferenceLine y={50} stroke="rgba(255,255,255,0.15)" strokeDasharray="2 2" />
            
            {/* Confidence band */}
            <Area
              type="monotone"
              dataKey="upper"
              stroke="none"
              fill="url(#kalshiBand)"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="lower"
              stroke="none"
              fill="rgb(var(--surface-card))"
              isAnimationActive={false}
            />
            
            {/* Main line */}
            <Area
              type="monotone"
              dataKey="homeProb"
              stroke="#3B82F6"
              strokeWidth={2.5}
              fill="url(#kalshiGradient)"
              isAnimationActive={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgb(var(--surface-elevated))",
                border: "1px solid rgb(var(--surface-border))",
                borderRadius: "8px",
              }}
              formatter={(value: number) => [`${value}%`, "Win Probability"]}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      
      {/* Minimal footer */}
      <div className="flex justify-between items-center mt-4 pt-4 border-t border-surface-border text-xs text-text-muted">
        <span>Boston Celtics vs Miami Heat</span>
        <span>Final: 112-104</span>
      </div>
    </div>
  );
}

// Variant 3: MoneyPuck-Style with Team Branding and Annotations
function MoneyPuckChart({ data }: { data: typeof nhlGameData }) {
  const homeColor = "#FFB81C"; // Bruins gold
  const awayColor = "#00205B"; // Leafs blue
  
  return (
    <div className="bg-surface-card rounded-lg p-4 border border-surface-border">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">MoneyPuck-Style</h3>
          <p className="text-sm text-text-muted">Team colors, period markers, goal annotations</p>
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ backgroundColor: homeColor, color: "#000" }}>
              BOS
            </div>
            <span className="text-xl font-bold text-text-primary">{data[data.length - 1].homeScore}</span>
          </div>
          <span className="text-text-muted">-</span>
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-text-primary">{data[data.length - 1].awayScore}</span>
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ backgroundColor: awayColor, color: "#fff" }}>
              TOR
            </div>
          </div>
        </div>
      </div>
      
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 20, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="mpHomeGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={homeColor} stopOpacity={0.6} />
                <stop offset="50%" stopColor={homeColor} stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="mpAwayGradient" x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor={awayColor} stopOpacity={0.6} />
                <stop offset="50%" stopColor={awayColor} stopOpacity={0.1} />
              </linearGradient>
            </defs>
            
            {/* Period backgrounds */}
            <ReferenceArea x1={0} x2={20} fill="rgba(255,255,255,0.02)" />
            <ReferenceArea x1={20} x2={40} fill="rgba(255,255,255,0.04)" />
            <ReferenceArea x1={40} x2={60} fill="rgba(255,255,255,0.02)" />
            
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis 
              dataKey="time" 
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              ticks={[0, 10, 20, 30, 40, 50, 60]}
              tickFormatter={(v) => `${v}'`}
            />
            <YAxis 
              domain={[0, 100]}
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            <ReferenceLine y={50} stroke="rgba(255,255,255,0.2)" />
            
            {/* Period labels */}
            <ReferenceLine x={20} stroke="rgba(255,255,255,0.3)" label={{ value: "1ST", fill: "rgb(var(--text-muted))", fontSize: 10, position: "top" }} />
            <ReferenceLine x={40} stroke="rgba(255,255,255,0.3)" label={{ value: "2ND", fill: "rgb(var(--text-muted))", fontSize: 10, position: "top" }} />
            
            {/* Goal markers */}
            {data.filter(d => d.goal).map((d, i) => (
              <ReferenceLine 
                key={i} 
                x={d.time} 
                stroke={d.goal?.team === "home" ? homeColor : awayColor} 
                strokeWidth={2}
                strokeDasharray="4 2"
              />
            ))}
            
            <Area
              type="monotone"
              dataKey="homeProb"
              stroke={homeColor}
              strokeWidth={2}
              fill="url(#mpHomeGradient)"
              isAnimationActive={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgb(var(--surface-elevated))",
                border: "1px solid rgb(var(--surface-border))",
                borderRadius: "8px",
              }}
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null;
                const d = payload[0].payload;
                return (
                  <div className="bg-surface-elevated border border-surface-border rounded-lg p-3 text-sm">
                    <div className="font-medium text-text-primary">{d.minute}</div>
                    <div className="text-text-secondary">BOS: {d.homeProb}% | TOR: {d.awayProb}%</div>
                    {d.goal && (
                      <div className="mt-1 text-xs" style={{ color: d.goal.team === "home" ? homeColor : awayColor }}>
                        GOAL: {d.goal.scorer}
                      </div>
                    )}
                  </div>
                );
              }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      
      {/* Period summary */}
      <div className="flex justify-around mt-4 pt-4 border-t border-surface-border text-xs">
        <div className="text-center">
          <div className="text-text-muted mb-1">1ST PERIOD</div>
          <div className="text-text-secondary">0-1</div>
        </div>
        <div className="text-center">
          <div className="text-text-muted mb-1">2ND PERIOD</div>
          <div className="text-text-secondary">2-0</div>
        </div>
        <div className="text-center">
          <div className="text-text-muted mb-1">3RD PERIOD</div>
          <div className="text-text-secondary">1-1</div>
        </div>
      </div>
    </div>
  );
}

// Variant 4: DataGolf-Style Multi-Participant Evolution
function DataGolfChart({ data, players }: { data: typeof golfTournamentData.data; players: typeof golfTournamentData.players }) {
  const [selectedPlayers, setSelectedPlayers] = useState<string[]>(
    players.slice(0, 4).map(p => p.name)
  );
  
  const togglePlayer = (name: string) => {
    setSelectedPlayers(prev => 
      prev.includes(name) 
        ? prev.filter(p => p !== name)
        : [...prev, name]
    );
  };
  
  return (
    <div className="bg-surface-card rounded-lg p-4 border border-surface-border">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">DataGolf-Style</h3>
          <p className="text-sm text-text-muted">Multi-participant evolution plot</p>
        </div>
        <div className="text-sm text-text-muted">
          The Masters - Round 4
        </div>
      </div>
      
      {/* Player toggles */}
      <div className="flex flex-wrap gap-2 mb-4">
        {players.map(player => (
          <button
            key={player.name}
            onClick={() => togglePlayer(player.name)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
              selectedPlayers.includes(player.name)
                ? "ring-2 ring-offset-1 ring-offset-surface-card"
                : "opacity-40 hover:opacity-70"
            }`}
            style={{ 
              backgroundColor: `${player.color}20`,
              color: player.color,
              ringColor: player.color,
            }}
          >
            {player.name.split(" ").pop()}
          </button>
        ))}
      </div>
      
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis 
              dataKey="label" 
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              interval={4}
            />
            <YAxis 
              domain={[0, 50]}
              tick={{ fill: "rgb(var(--text-muted))", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${v}%`}
            />
            
            {/* Round separators */}
            <ReferenceLine x="R2 H18" stroke="rgba(255,255,255,0.15)" label={{ value: "CUT", fill: "rgb(var(--text-muted))", fontSize: 9 }} />
            <ReferenceLine x="R3 H18" stroke="rgba(255,255,255,0.15)" />
            
            {players.map(player => (
              <Line
                key={player.name}
                type="monotone"
                dataKey={player.name}
                stroke={player.color}
                strokeWidth={selectedPlayers.includes(player.name) ? 2.5 : 1}
                strokeOpacity={selectedPlayers.includes(player.name) ? 1 : 0.2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
            
            <Tooltip
              contentStyle={{
                backgroundColor: "rgb(var(--surface-elevated))",
                border: "1px solid rgb(var(--surface-border))",
                borderRadius: "8px",
              }}
              content={({ active, payload, label }) => {
                if (!active || !payload) return null;
                const filtered = payload
                  .filter(p => selectedPlayers.includes(p.dataKey as string))
                  .sort((a, b) => (b.value as number) - (a.value as number));
                return (
                  <div className="bg-surface-elevated border border-surface-border rounded-lg p-3 text-sm min-w-[140px]">
                    <div className="font-medium text-text-primary mb-2">{label}</div>
                    {filtered.map(p => (
                      <div key={p.dataKey} className="flex justify-between items-center gap-4 text-xs">
                        <span style={{ color: p.color }}>{(p.dataKey as string).split(" ").pop()}</span>
                        <span className="font-mono text-text-secondary">{(p.value as number).toFixed(1)}%</span>
                      </div>
                    ))}
                  </div>
                );
              }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      
      {/* Leaderboard snippet */}
      <div className="mt-4 pt-4 border-t border-surface-border">
        <div className="text-xs text-text-muted mb-2">Current Win Probability</div>
        <div className="grid grid-cols-4 gap-2">
          {players.slice(0, 4).map((player, i) => {
            const lastPoint = data[data.length - 1];
            const prob = lastPoint[player.name] as number;
            return (
              <div key={player.name} className="text-center">
                <div className="text-lg font-bold" style={{ color: player.color }}>
                  {prob.toFixed(0)}%
                </div>
                <div className="text-[10px] text-text-muted truncate">
                  {player.name.split(" ").pop()}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function WinProbabilityDemo() {
  const [activeVariant, setActiveVariant] = useState<string>("all");
  
  const variants = [
    { id: "all", label: "All Variants" },
    { id: "538", label: "538" },
    { id: "kalshi", label: "Kalshi" },
    { id: "moneypuck", label: "MoneyPuck" },
    { id: "datagolf", label: "DataGolf" },
  ];
  
  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <motion.div 
          className="mb-8"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <h1 className="text-2xl font-bold text-text-primary mb-2">
            Win Probability Charts
          </h1>
          <p className="text-text-muted">
            4 design variants inspired by 538, Kalshi, MoneyPuck, and DataGolf
          </p>
        </motion.div>
        
        {/* Variant selector */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
          {variants.map(v => (
            <button
              key={v.id}
              onClick={() => setActiveVariant(v.id)}
              className={`px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                activeVariant === v.id
                  ? "bg-accent-brand text-white"
                  : "bg-surface-elevated text-text-secondary hover:text-text-primary"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
        
        {/* Charts grid */}
        <motion.div 
          className="grid gap-6"
          style={{ 
            gridTemplateColumns: activeVariant === "all" 
              ? "repeat(auto-fit, minmax(min(100%, 500px), 1fr))" 
              : "1fr" 
          }}
          layout
        >
          {(activeVariant === "all" || activeVariant === "538") && (
            <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <FiveThirtyEightChart data={nbaGameData} />
            </motion.div>
          )}
          
          {(activeVariant === "all" || activeVariant === "kalshi") && (
            <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <KalshiChart data={nbaGameData} />
            </motion.div>
          )}
          
          {(activeVariant === "all" || activeVariant === "moneypuck") && (
            <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <MoneyPuckChart data={nhlGameData} />
            </motion.div>
          )}
          
          {(activeVariant === "all" || activeVariant === "datagolf") && (
            <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <DataGolfChart data={golfTournamentData.data} players={golfTournamentData.players} />
            </motion.div>
          )}
        </motion.div>
        
        {/* Design notes */}
        <div className="mt-12 p-6 bg-surface-card rounded-lg border border-surface-border">
          <h2 className="text-lg font-semibold text-text-primary mb-4">Design Notes</h2>
          <div className="grid md:grid-cols-2 gap-6 text-sm text-text-secondary">
            <div>
              <h3 className="font-medium text-text-primary mb-2">538-Style</h3>
              <ul className="list-disc list-inside space-y-1">
                <li>Stepped area chart emphasizes discrete events</li>
                <li>50% baseline with team color fills above/below</li>
                <li>Period separators for game structure</li>
                <li>Best for: head-to-head sports (NBA, NFL, NHL)</li>
              </ul>
            </div>
            <div>
              <h3 className="font-medium text-text-primary mb-2">Kalshi-Style</h3>
              <ul className="list-disc list-inside space-y-1">
                <li>Clean monotone line with gradient fill</li>
                <li>Confidence band shows uncertainty range</li>
                <li>Minimalist, prediction-market aesthetic</li>
                <li>Best for: single outcome tracking, elections</li>
              </ul>
            </div>
            <div>
              <h3 className="font-medium text-text-primary mb-2">MoneyPuck-Style</h3>
              <ul className="list-disc list-inside space-y-1">
                <li>Strong team branding with colors and logos</li>
                <li>Goal/scoring annotations on the chart</li>
                <li>Period backgrounds for visual structure</li>
                <li>Best for: hockey, soccer, low-scoring sports</li>
              </ul>
            </div>
            <div>
              <h3 className="font-medium text-text-primary mb-2">DataGolf-Style</h3>
              <ul className="list-disc list-inside space-y-1">
                <li>Multi-line evolution plot for many participants</li>
                <li>Interactive player selection/highlighting</li>
                <li>Round separators and cut lines</li>
                <li>Best for: golf, NASCAR, tournaments with 10+ competitors</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
