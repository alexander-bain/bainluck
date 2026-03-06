'use client';

import { useParams, notFound } from 'next/navigation';
import { useEffect, useState, useCallback } from 'react';
import { usePageTracking, useScrollDepth, useEngagementTime } from '@/hooks';
import { fetchMarchMadness } from '@/lib/api';
import { useBracketPicks } from '@/hooks/useBracketPicks';
import { TOURNAMENT_TYPE_CONFIG, ROUND_ORDER, ROUND_SHORT } from '@/lib/marchMadnessData';
import type { MarchMadnessResponse, BracketGame } from '@/lib/types';
import '../../march-madness.css';

export default function BracketPicksPage() {
  const params = useParams();
  const type = params?.type as string;

  // Analytics (3 mandatory hooks — must be called before any conditional return)
  usePageTracking({ pageType: 'march_madness_picks', pageTitle: `Make Your Picks - ${type}` });
  useScrollDepth({ pageType: 'march_madness_picks' });
  useEngagementTime({ pageType: 'march_madness_picks' });

  const config = TOURNAMENT_TYPE_CONFIG[type as keyof typeof TOURNAMENT_TYPE_CONFIG];
  const bracketPicks = useBracketPicks(type);

  const [data, setData] = useState<MarchMadnessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRounds, setExpandedRounds] = useState<Record<string, boolean>>({});

  const loadData = useCallback(async () => {
    if (!config) return;
    try {
      const result = await fetchMarchMadness(config.apiType);
      setData(result);
      setError(null);
    } catch (err) {
      setError('Failed to load tournament data');
      console.error('March Madness fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [config]);

  // Load data on mount and set up auto-refresh
  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 60000); // Refresh every 60s
    return () => clearInterval(interval);
  }, [loadData]);

  // Update bracket picks results based on game data
  useEffect(() => {
    if (data?.bracket?.games) {
      bracketPicks.updateResults(data.bracket.games);
    }
  }, [data?.bracket?.games, bracketPicks]);

  if (!config) {
    notFound();
  }

  if (loading) {
    return (
      <div className="mm-page">
        <div className="mm-content">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[...Array(6)].map((_, i) => (
              <div key={i} className="mm-skeleton" style={{ height: 64 }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="mm-page">
        <div className="mm-content">
          <div
            style={{
              padding: 24,
              textAlign: 'center',
              color: 'var(--mm-text-dim)',
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
            }}
          >
            <p style={{ marginBottom: 12 }}>{error || 'Failed to load bracket'}</p>
            <button
              onClick={loadData}
              style={{
                padding: '8px 20px',
                borderRadius: 8,
                border: '1px solid var(--mm-wood-accent)',
                background: 'transparent',
                color: 'var(--mm-wood-pale)',
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Group games by round
  const gamesByRound: Record<string, BracketGame[]> = {};
  for (const game of data.bracket?.games ?? []) {
    const round = game.round || 'Unknown';
    if (!gamesByRound[round]) gamesByRound[round] = [];
    gamesByRound[round].push(game);
  }

  // Order rounds
  const orderedRounds = ROUND_ORDER.filter(r => gamesByRound[r]);

  const toggleRound = (round: string) => {
    setExpandedRounds(prev => ({
      ...prev,
      [round]: !prev[round],
    }));
  };

  return (
    <div className="mm-page">
      <div className="mm-content">
        {/* Hero Section */}
        <div className="mm-hero">
          <h1>Make Your Picks</h1>
          <p className="mm-hero-subtitle">Predict the winners and track your accuracy</p>
        </div>

        {/* Stats Bar */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: 12,
            marginBottom: 32,
          }}
        >
          <div
            style={{
              padding: 16,
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', marginBottom: 4 }}>
              Picks Made
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--mm-gold)' }}>
              {bracketPicks.totalPicks}
            </div>
          </div>

          <div
            style={{
              padding: 16,
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', marginBottom: 4 }}>
              Correct
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--mm-green)' }}>
              {bracketPicks.correctPicks}
            </div>
          </div>

          <div
            style={{
              padding: 16,
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', marginBottom: 4 }}>
              Decided
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--mm-text)' }}>
              {bracketPicks.decidedGames}
            </div>
          </div>

          <div
            style={{
              padding: 16,
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', marginBottom: 4 }}>
              Accuracy
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--mm-gold)' }}>
              {bracketPicks.accuracy > 0 ? `${Math.round(bracketPicks.accuracy)}%` : '—'}
            </div>
          </div>
        </div>

        {/* Games by Round */}
        {orderedRounds.length > 0 ? (
          orderedRounds.map(round => (
            <div key={round}>
              <button
                onClick={() => toggleRound(round)}
                style={{
                  width: '100%',
                  padding: '16px 20px',
                  marginBottom: 16,
                  borderRadius: 12,
                  background: 'var(--mm-card-bg)',
                  border: '1px solid var(--mm-card-border)',
                  color: 'var(--mm-text)',
                  fontSize: '1rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  transition: 'background-color 200ms',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.backgroundColor = 'var(--mm-card-bg)';
                  e.currentTarget.style.opacity = '0.8';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.backgroundColor = 'var(--mm-card-bg)';
                  e.currentTarget.style.opacity = '1';
                }}
              >
                <span>
                  {round} <span style={{ color: 'var(--mm-text-dim)', fontSize: '0.875rem', marginLeft: 8 }}>({gamesByRound[round]?.length ?? 0} games)</span>
                </span>
                <span style={{ color: 'var(--mm-gold)', fontSize: '1.25rem' }}>
                  {expandedRounds[round] ? '▼' : '▶'}
                </span>
              </button>

              {expandedRounds[round] && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
                  {gamesByRound[round]?.map(game => (
                    <GameCard
                      key={game.event_id}
                      game={game}
                      pick={bracketPicks.getPick(game.event_id)}
                      onPick={(teamName: string) => bracketPicks.makePick(game.event_id, teamName)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))
        ) : (
          <div
            style={{
              padding: 24,
              textAlign: 'center',
              color: 'var(--mm-text-dim)',
              borderRadius: 12,
              background: 'var(--mm-card-bg)',
              border: '1px solid var(--mm-card-border)',
            }}
          >
            <p>No games to pick yet. Check back soon!</p>
          </div>
        )}

        {/* Reset Button */}
        {bracketPicks.totalPicks > 0 && (
          <div style={{ marginTop: 32, display: 'flex', justifyContent: 'center' }}>
            <button
              onClick={() => {
                if (confirm('Reset all picks? This cannot be undone.')) {
                  bracketPicks.resetPicks();
                }
              }}
              style={{
                padding: '12px 24px',
                borderRadius: 8,
                border: '1px solid var(--mm-wood-accent)',
                background: 'transparent',
                color: 'var(--mm-text-dim)',
                cursor: 'pointer',
                fontSize: '0.875rem',
              }}
            >
              Reset All Picks
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * GameCard - Individual game card for picking a winner
 */
interface GameCardProps {
  game: BracketGame;
  pick: any; // BracketPick | null
  onPick: (teamName: string) => void;
}

function GameCard({ game, pick, onPick }: GameCardProps) {
  const isLocked = pick?.locked || ['live', 'in_progress', 'completed', 'closed'].includes(game.status);
  const isCompleted = ['completed', 'closed'].includes(game.status);

  let homeTeamColor = '#8B8B8B';
  let awayTeamColor = '#8B8B8B';

  if (isCompleted && game.score_home !== null && game.score_away !== null) {
    const homeWon = game.score_home > game.score_away;
    homeTeamColor = homeWon ? 'var(--mm-green)' : '#888';
    awayTeamColor = !homeWon ? 'var(--mm-green)' : '#888';
  }

  return (
    <div
      style={{
        padding: 16,
        borderRadius: 12,
        background: 'var(--mm-card-bg)',
        border: `1px solid ${pick ? 'var(--mm-gold)' : 'var(--mm-card-border)'}`,
        opacity: isLocked && !isCompleted ? 0.6 : 1,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', textTransform: 'uppercase', fontWeight: 600 }}>
          {game.round}
        </div>
        {isLocked && (
          <div style={{ fontSize: '0.75rem', color: 'var(--mm-text-dim)', display: 'flex', gap: 4, alignItems: 'center' }}>
            🔒 Locked
          </div>
        )}
        {isCompleted && pick && (
          <div
            style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              color: pick.result === 'correct' ? 'var(--mm-green)' : 'var(--mm-upset-red)',
            }}
          >
            {pick.result === 'correct' ? '✓ Correct' : '✗ Incorrect'}
          </div>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Home Team */}
        <button
          onClick={() => !isLocked && onPick(game.home_team)}
          disabled={isLocked}
          style={{
            padding: '12px 16px',
            borderRadius: 8,
            border: pick?.picked_team === game.home_team ? '2px solid var(--mm-gold)' : '1px solid var(--mm-card-border)',
            background: pick?.picked_team === game.home_team ? 'rgba(212, 175, 55, 0.08)' : 'transparent',
            color: homeTeamColor,
            fontSize: '0.9375rem',
            fontWeight: 700,
            cursor: isLocked ? 'not-allowed' : 'pointer',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            opacity: isLocked && pick?.picked_team !== game.home_team ? 0.5 : 1,
          }}
        >
          <span>
            {game.seed_home && <span style={{ marginRight: 8, color: 'var(--mm-text-dim)' }}>({game.seed_home})</span>}
            {game.home_team}
          </span>
          {game.prob_home !== null && (
            <span style={{ fontSize: '0.8125rem', color: 'var(--mm-text-dim)' }}>
              {Math.round(game.prob_home * 100)}%
            </span>
          )}
        </button>

        {/* VS divider */}
        <div style={{ textAlign: 'center', color: 'var(--mm-text-dim)', fontSize: '0.75rem', fontWeight: 600 }}>
          VS
        </div>

        {/* Away Team */}
        <button
          onClick={() => !isLocked && onPick(game.away_team)}
          disabled={isLocked}
          style={{
            padding: '12px 16px',
            borderRadius: 8,
            border: pick?.picked_team === game.away_team ? '2px solid var(--mm-gold)' : '1px solid var(--mm-card-border)',
            background: pick?.picked_team === game.away_team ? 'rgba(212, 175, 55, 0.08)' : 'transparent',
            color: awayTeamColor,
            fontSize: '0.9375rem',
            fontWeight: 700,
            cursor: isLocked ? 'not-allowed' : 'pointer',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            opacity: isLocked && pick?.picked_team !== game.away_team ? 0.5 : 1,
          }}
        >
          <span>
            {game.seed_away && <span style={{ marginRight: 8, color: 'var(--mm-text-dim)' }}>({game.seed_away})</span>}
            {game.away_team}
          </span>
          {game.prob_away !== null && (
            <span style={{ fontSize: '0.8125rem', color: 'var(--mm-text-dim)' }}>
              {Math.round(game.prob_away * 100)}%
            </span>
          )}
        </button>
      </div>

      {/* Score (for completed games) */}
      {isCompleted && game.score_home !== null && game.score_away !== null && (
        <div style={{ marginTop: 12, padding: '12px', borderRadius: 8, background: 'rgba(0,0,0,0.2)', textAlign: 'center', fontSize: '0.875rem', color: 'var(--mm-text-dim)' }}>
          Final: {game.home_team} {game.score_home} - {game.score_away} {game.away_team}
        </div>
      )}
    </div>
  );
}
