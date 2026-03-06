'use client';

import React, { useMemo, useRef, useEffect, useState } from 'react';
import Link from 'next/link';
import { BracketGame, MarchMadnessBracket } from '@/lib/types';
import { ROUND_ORDER, ROUND_SHORT, REGIONS } from '@/lib/marchMadnessData';

interface BracketProps {
  bracket: MarchMadnessBracket;
}

/**
 * BracketView: Interactive SVG bracket visualization
 * Shows the 64-team March Madness bracket flowing left→center←right
 * - Left side: regions 1 & 2 (R64→R32→S16→E8)
 * - Right side: regions 3 & 4 (R64→R32→S16→E8)
 * - Center: Final Four + Championship
 */
export default function BracketView({ bracket }: BracketProps) {
  const [scrollPosition, setScrollPosition] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Organize games by round and region
  const gamesByRound = useMemo(() => {
    const result: Record<string, BracketGame[]> = {};
    ROUND_ORDER.forEach((round) => {
      result[round] = bracket.games.filter((g) => g.round === round);
    });
    return result;
  }, [bracket.games]);

  // Handle horizontal scroll tracking
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      setScrollPosition(container.scrollLeft);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  const renderMatchupBox = (game: BracketGame, isLeft: boolean) => {
    const isScheduled = game.status === 'scheduled';
    const isLive = game.status === 'live';
    const isCompleted = game.status === 'completed' || game.status === 'closed';

    // Determine winner/loser for completed games
    let homeWon = false;
    let awayWon = false;
    if (isCompleted && game.score_home !== null && game.score_away !== null) {
      homeWon = game.score_home > game.score_away;
      awayWon = game.score_away > game.score_home;
    }

    const homeProb = game.prob_home ?? 0;
    const awayProb = game.prob_away ?? 0;

    const hasLink = game.event_id !== null && game.event_id !== undefined;

    const boxContent = (
      <div
        style={{
          borderRadius: '8px',
          background: `var(--mm-card-bg)`,
          border: `1px solid var(--mm-card-border)`,
          padding: '8px',
          minWidth: '160px',
          fontSize: '12px',
          cursor: hasLink ? 'pointer' : 'default',
          transition: 'all 0.2s',
          opacity: homeWon || awayWon ? 1 : 0.7,
        }}
        onMouseEnter={(e) => {
          if (hasLink) {
            e.currentTarget.style.borderColor = `var(--mm-gold)`;
            e.currentTarget.style.transform = 'scale(1.05)';
          }
        }}
        onMouseLeave={(e) => {
          if (hasLink) {
            e.currentTarget.style.borderColor = `var(--mm-card-border)`;
            e.currentTarget.style.transform = 'scale(1)';
          }
        }}
      >
        {/* Matchup header */}
        <div style={{ marginBottom: '6px', borderBottom: '1px solid var(--mm-card-border)', paddingBottom: '4px' }}>
          {game.seed_home && (
            <span
              style={{
                display: 'inline-block',
                width: '20px',
                height: '20px',
                borderRadius: '3px',
                background: `rgba(139, 69, 19, 0.4)`,
                color: `var(--mm-wood-pale)`,
                fontSize: '10px',
                fontWeight: 'bold',
                marginRight: '4px',
                textAlign: 'center',
                lineHeight: '20px',
              }}
            >
              {game.seed_home}
            </span>
          )}
          <span style={{ opacity: awayWon ? 0.4 : 1, fontWeight: homeWon ? 'bold' : 'normal' }}>
            {game.home_team}
          </span>
        </div>

        {/* Home team score/prob */}
        <div style={{ marginBottom: '4px', paddingBottom: '4px', borderBottom: '1px solid var(--mm-card-border)' }}>
          {isCompleted && game.score_home !== null ? (
            <span
              style={{
                fontWeight: homeWon ? 'bold' : 'normal',
                color: homeWon ? `var(--mm-gold)` : `var(--mm-text-dim)`,
              }}
            >
              {game.score_home}
            </span>
          ) : (
            <span style={{ color: `var(--mm-text-dim)` }}>{(homeProb * 100).toFixed(0)}%</span>
          )}
        </div>

        {/* Away team */}
        <div style={{ marginBottom: '4px' }}>
          {game.seed_away && (
            <span
              style={{
                display: 'inline-block',
                width: '20px',
                height: '20px',
                borderRadius: '3px',
                background: `rgba(139, 69, 19, 0.4)`,
                color: `var(--mm-wood-pale)`,
                fontSize: '10px',
                fontWeight: 'bold',
                marginRight: '4px',
                textAlign: 'center',
                lineHeight: '20px',
              }}
            >
              {game.seed_away}
            </span>
          )}
          <span style={{ opacity: homeWon ? 0.4 : 1, fontWeight: awayWon ? 'bold' : 'normal' }}>
            {game.away_team}
          </span>
        </div>

        {/* Away team score/prob */}
        <div style={{ marginBottom: '4px' }}>
          {isCompleted && game.score_away !== null ? (
            <span
              style={{
                fontWeight: awayWon ? 'bold' : 'normal',
                color: awayWon ? `var(--mm-gold)` : `var(--mm-text-dim)`,
              }}
            >
              {game.score_away}
            </span>
          ) : (
            <span style={{ color: `var(--mm-text-dim)` }}>{(awayProb * 100).toFixed(0)}%</span>
          )}
        </div>

        {/* EI badge if available */}
        {game.ei !== null && (
          <div
            style={{
              marginTop: '4px',
              paddingTop: '4px',
              borderTop: '1px solid var(--mm-card-border)',
              fontSize: '10px',
              color: `var(--mm-wood-accent)`,
              fontWeight: 'bold',
            }}
          >
            EI: {game.ei}
          </div>
        )}
      </div>
    );

    return hasLink ? (
      <Link key={`game-${game.event_id}`} href={`/events/${game.event_id}`}>
        {boxContent}
      </Link>
    ) : (
      <div key={`game-${game.event_id ?? game.home_team}-${game.away_team}`}>{boxContent}</div>
    );
  };

  // Group left bracket (East, West)
  const leftRegionGames = bracket.games.filter((g) => g.region === 'East' || g.region === 'West');

  // Group right bracket (South, Midwest)
  const rightRegionGames = bracket.games.filter((g) => g.region === 'South' || g.region === 'Midwest');

  // Group center bracket (Final Four, Championship)
  const centerGames = bracket.games.filter((g) => g.round === 'Final Four' || g.round === 'Championship');

  return (
    <div
      style={{
        width: '100%',
        overflowX: 'auto',
        overflowY: 'hidden',
        paddingBottom: '16px',
      }}
      ref={containerRef}
    >
      <div
        style={{
          minWidth: '1600px',
          display: 'grid',
          gridTemplateColumns: 'auto 1fr auto',
          gap: '32px',
          padding: '16px 24px',
        }}
      >
        {/* LEFT BRACKET (East & West) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div>
            <h3 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 'bold', color: `var(--mm-wood-pale)` }}>
              EAST & WEST
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              {['East', 'West'].map((region) => (
                <div key={region}>
                  <h4
                    style={{
                      marginBottom: '8px',
                      fontSize: '12px',
                      color: `var(--mm-text-dim)`,
                      textAlign: 'center',
                    }}
                  >
                    {region}
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {leftRegionGames
                      .filter((g) => g.region === region)
                      .sort((a, b) => (ROUND_ORDER as readonly string[]).indexOf(a.round || '') - (ROUND_ORDER as readonly string[]).indexOf(b.round || ''))
                      .map((game) => renderMatchupBox(game, true))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* CENTER BRACKET (Final Four & Championship) */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '32px' }}>
          {/* Final Four */}
          <div style={{ textAlign: 'center' }}>
            <h3 style={{ marginBottom: '16px', fontSize: '14px', fontWeight: 'bold', color: `var(--mm-wood-pale)` }}>
              FINAL FOUR
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {gamesByRound['Final Four']?.map((game) => renderMatchupBox(game, false))}
            </div>
          </div>

          {/* Championship */}
          <div style={{ textAlign: 'center' }}>
            <h3 style={{ marginBottom: '16px', fontSize: '14px', fontWeight: 'bold', color: `var(--mm-gold)` }}>
              CHAMPIONSHIP 🏆
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {gamesByRound['Championship']?.map((game) => renderMatchupBox(game, false))}
            </div>
          </div>
        </div>

        {/* RIGHT BRACKET (South & Midwest) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div>
            <h3 style={{ marginBottom: '12px', fontSize: '14px', fontWeight: 'bold', color: `var(--mm-wood-pale)` }}>
              SOUTH & MIDWEST
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              {['South', 'Midwest'].map((region) => (
                <div key={region}>
                  <h4
                    style={{
                      marginBottom: '8px',
                      fontSize: '12px',
                      color: `var(--mm-text-dim)`,
                      textAlign: 'center',
                    }}
                  >
                    {region}
                  </h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {rightRegionGames
                      .filter((g) => g.region === region)
                      .sort((a, b) => (ROUND_ORDER as readonly string[]).indexOf(a.round || '') - (ROUND_ORDER as readonly string[]).indexOf(b.round || ''))
                      .map((game) => renderMatchupBox(game, false))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
