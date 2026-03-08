'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, ComposedChart } from 'recharts';
import { useState } from 'react';
import { motion } from 'framer-motion';

// ============================================================================
// DATA GENERATORS
// ============================================================================

function generateTwoTeamData() {
  return [
    // Q1
    { time: 0, minute: '0:00', period: 'Q1', espn: 55, kalshi: 57, polymarket: 54, aggregate: 55.3 },
    { time: 2, minute: '2:00', period: 'Q1', espn: 58, kalshi: 59, polymarket: 57, aggregate: 58 },
    { time: 6, minute: '6:00', period: 'Q1', espn: 62, kalshi: 63, polymarket: 60, aggregate: 61.7 },
    { time: 12, minute: '12:00', period: 'Q1', espn: 60, kalshi: 61, polymarket: 59, aggregate: 60 },
    // Q2
    { time: 14, minute: '2:00', period: 'Q2', espn: 56, kalshi: 55, polymarket: 57, aggregate: 56 },
    { time: 18, minute: '6:00', period: 'Q2', espn: 52, kalshi: 50, polymarket: 53, aggregate: 51.7 },
    { time: 24, minute: '12:00', period: 'Q2', espn: 48, kalshi: 47, polymarket: 49, aggregate: 48 },
    // Halftime
    { time: 25, minute: 'HT', period: 'Halftime', espn: 48, kalshi: 47, polymarket: 49, aggregate: 48 },
    // Q3
    { time: 30, minute: '6:00', period: 'Q3', espn: 52, kalshi: 54, polymarket: 51, aggregate: 52.3 },
    { time: 36, minute: '12:00', period: 'Q3', espn: 55, kalshi: 57, polymarket: 54, aggregate: 55.3 },
    // Q4
    { time: 40, minute: '4:00', period: 'Q4', espn: 52, kalshi: 51, polymarket: 53, aggregate: 52 },
    { time: 44, minute: '8:00', period: 'Q4', espn: 50, kalshi: 49, polymarket: 51, aggregate: 50 },
    { time: 48, minute: 'Final', period: 'Q4', espn: 48, kalshi: 47, polymarket: 49, aggregate: 48 },
  ];
}

function generateMultiParticipantData() {
  return [
    { round: 'R1', rory: 32, jon: 28, scottie: 45, collin: 25, other: 10 },
    { round: 'R1 EOD', rory: 22, jon: 30, scottie: 34, collin: 16, other: 20 },
    { round: 'R2', rory: 24, jon: 32, scottie: 31, collin: 17, other: 19 },
    { round: 'R2 EOD', rory: 32, jon: 40, scottie: 20, collin: 21, other: 23 },
  ];
}

// ============================================================================
// COMPONENT: TWO-TEAM CHART
// ============================================================================

function TwoTeamChart() {
  const data = generateTwoTeamData();
  const homeTeam = 'Boston Celtics';
  const awayTeam = 'Miami Heat';
  
  const halftimeIndex = data.findIndex(d => d.period === 'Halftime');

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">{homeTeam} vs {awayTeam}</h3>
        <p className="text-sm text-text-muted">NBA Playoffs - Live Game</p>
      </div>

      <div className="flex flex-wrap gap-3 px-4 py-2 bg-surface-elevated rounded-lg">
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-blue-500 rounded"></div>
          <span className="text-xs font-medium text-text-muted">ESPN</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-green-500 rounded"></div>
          <span className="text-xs font-medium text-text-muted">Kalshi</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-purple-500 rounded"></div>
          <span className="text-xs font-medium text-text-muted">Polymarket</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-white"></div>
          <span className="text-xs font-semibold text-white">Aggregated</span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={data} margin={{ top: 20, right: 30, left: 60, bottom: 60 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          
          {halftimeIndex >= 0 && (
            <ReferenceLine x={halftimeIndex} stroke="rgba(255,255,255,0.2)" strokeDasharray="5 5" />
          )}
          
          <ReferenceLine
            y={50}
            stroke="rgba(255,255,255,0.15)"
            strokeWidth={1}
            label={{ value: '50%', position: 'right', fill: 'rgba(255,255,255,0.5)', fontSize: 12 }}
          />
          
          <XAxis
            dataKey="minute"
            angle={-45}
            textAnchor="end"
            height={80}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.5)' }}
          />
          <YAxis
            domain={[0, 100]}
            label={{ value: `${homeTeam} Win %`, angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.5)', offset: 10 }}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.5)' }}
            ticks={[0, 25, 50, 75, 100]}
          />
          
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(0,0,0,0.8)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '8px',
            }}
            formatter={(value: any) => `${value.toFixed(1)}%`}
            labelStyle={{ color: 'white' }}
          />
          
          <Line type="monotone" dataKey="espn" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
          <Line type="monotone" dataKey="kalshi" stroke="#10b981" strokeWidth={1.5} dot={false} />
          <Line type="monotone" dataKey="polymarket" stroke="#a855f7" strokeWidth={1.5} dot={false} />
          <Line type="monotone" dataKey="aggregate" stroke="white" strokeWidth={3} dot={{ r: 4 }} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-5 gap-2 text-center text-xs font-semibold text-text-muted">
        <div>Q1</div>
        <div>Q2</div>
        <div>Halftime</div>
        <div>Q3</div>
        <div>Q4</div>
      </div>
    </div>
  );
}

// ============================================================================
// COMPONENT: MULTI-PARTICIPANT CHART
// ============================================================================

function MultiParticipantChart() {
  const data = generateMultiParticipantData();
  const [highlighted, setHighlighted] = useState<string | null>(null);

  const players = [
    { key: 'rory', name: 'Rory McIlroy', color: '#3b82f6' },
    { key: 'jon', name: 'Jon Rahm', color: '#10b981' },
    { key: 'scottie', name: 'Scottie Scheffler', color: '#f59e0b' },
    { key: 'collin', name: 'Collin Morikawa', color: '#ef4444' },
  ];

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">Masters Tournament</h3>
        <p className="text-sm text-text-muted">Multi-Participant Evolution - 72 Holes</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {players.map((player) => (
          <button
            key={player.key}
            onClick={() => setHighlighted(highlighted === player.key ? null : player.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition`}
            style={{
              backgroundColor: player.color,
              opacity: highlighted === player.key ? 1 : (highlighted ? 0.3 : 0.7),
            }}
          >
            {player.name}
          </button>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data} margin={{ top: 20, right: 30, left: 60, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
          <XAxis dataKey="round" tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.5)' }} />
          <YAxis
            label={{ value: 'Win Probability %', angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.5)', offset: 10 }}
            tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.5)' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'rgba(0,0,0,0.8)',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '8px',
            }}
            formatter={(value: any) => `${value?.toFixed(1)}%`}
          />

          {players.map((player) => (
            <Line
              key={player.key}
              type="monotone"
              dataKey={player.key}
              stroke={player.color}
              strokeWidth={highlighted === player.key ? 3 : 1.5}
              dot={false}
              opacity={highlighted === null || highlighted === player.key ? 1 : 0.2}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-2 gap-2 text-xs">
        {players.map((player) => (
          <div key={player.key} className="flex items-center gap-2">
            <div className="w-3 h-0.5 rounded" style={{ backgroundColor: player.color }}></div>
            <span className="text-text-muted">{player.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// COMPONENT: TOURNAMENT BRACKET
// ============================================================================

function TournamentChart() {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-text-primary mb-1">March Madness - Elite Eight</h3>
        <p className="text-sm text-text-muted">Tournament Progression</p>
      </div>

      <div className="bg-surface-elevated/50 rounded-lg p-6 space-y-6 overflow-x-auto">
        {/* Round 1 */}
        <div className="space-y-3 min-w-max">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide">Round 1</h4>
          <div className="space-y-2">
            {[
              { seed: '1', prob: 95 },
              { seed: '8', prob: 5 },
              { seed: '4', prob: 10 },
              { seed: '5', prob: 90 },
              { seed: '6', prob: 15 },
              { seed: '3', prob: 85 },
              { seed: '7', prob: 20 },
              { seed: '2', prob: 80 },
            ].map((match, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <div className="w-24 text-xs font-medium text-text-muted">Seed {match.seed}</div>
                <div className="w-40">
                  <div className="relative h-6 bg-surface rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-blue-500 to-blue-500/60"
                      initial={{ width: 0 }}
                      animate={{ width: `${match.prob}%` }}
                      transition={{ duration: 0.8, delay: idx * 0.1 }}
                    />
                  </div>
                </div>
                <div className="w-12 text-right text-xs font-semibold text-blue-400">{match.prob}%</div>
              </div>
            ))}
          </div>
        </div>

        {/* Round 2 */}
        <div className="space-y-3 min-w-max">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide">Round 2</h4>
          <div className="space-y-2">
            {[
              { seed: '1', prob: 92 },
              { seed: '4', prob: 8 },
              { seed: '3', prob: 88 },
              { seed: '6', prob: 12 },
            ].map((match, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <div className="w-24 text-xs font-medium text-text-muted">Seed {match.seed}</div>
                <div className="w-40">
                  <div className="relative h-6 bg-surface rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-green-500 to-green-500/60"
                      initial={{ width: 0 }}
                      animate={{ width: `${match.prob}%` }}
                      transition={{ duration: 0.8, delay: idx * 0.1 }}
                    />
                  </div>
                </div>
                <div className="w-12 text-right text-xs font-semibold text-green-400">{match.prob}%</div>
              </div>
            ))}
          </div>
        </div>

        {/* Final Four */}
        <div className="space-y-3 min-w-max">
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wide">Final</h4>
          <div className="space-y-2">
            {[
              { seed: '1', prob: 90 },
              { seed: '3', prob: 10 },
            ].map((match, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <div className="w-24 text-xs font-medium text-text-muted">Seed {match.seed}</div>
                <div className="w-40">
                  <div className="relative h-6 bg-surface rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-purple-500 to-purple-500/60"
                      initial={{ width: 0 }}
                      animate={{ width: `${match.prob}%` }}
                      transition={{ duration: 0.8, delay: idx * 0.1 }}
                    />
                  </div>
                </div>
                <div className="w-12 text-right text-xs font-semibold text-purple-400">{match.prob}%</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// MAIN PAGE
// ============================================================================

export default function WinProbabilityDemo() {
  return (
    <main className="min-h-screen bg-background text-text-primary">
      <div className="max-w-6xl mx-auto px-4 py-12 space-y-12">
        <div className="space-y-2">
          <h1 className="text-4xl font-bold">Win Probability Charts</h1>
          <p className="text-text-muted">Three visualizations for different competition types with multiple probability sources</p>
        </div>

        <motion.section
          className="bg-surface rounded-lg p-6 space-y-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <TwoTeamChart />
        </motion.section>

        <motion.section
          className="bg-surface rounded-lg p-6 space-y-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <MultiParticipantChart />
        </motion.section>

        <motion.section
          className="bg-surface rounded-lg p-6 space-y-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <TournamentChart />
        </motion.section>
      </div>
    </main>
  );
}
