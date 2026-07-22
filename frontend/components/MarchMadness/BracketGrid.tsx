'use client';

import React, { useMemo, useState } from 'react';
import Link from 'next/link';
import { BracketGame, MarchMadnessBracket } from '@/lib/types';
import { ROUND_ORDER, ROUND_SHORT } from '@/lib/marchMadnessData';

interface BracketProps {
  bracket: MarchMadnessBracket;
}

type SortKey = 'round' | 'region' | 'seed';

/**
 * BracketGrid: Compact grid/table view for bracket games
 * Better for mobile - shows games in table format with filtering/sorting
 * - Sortable by round (default), region, seed
 * - Completed games show score, upcoming show probability
 * - Highlights upsets (lower seed won)
 * - Uses CSS variables from march-madness theme
 */
export default function BracketGrid({ bracket }: BracketProps) {
  const [sortKey, setSortKey] = useState<SortKey>('round');

  // Sort and organize games
  const sortedGames = useMemo(() => {
    const games = [...bracket.games];

    switch (sortKey) {
      case 'round':
        return games.sort(
          (a, b) =>
            (ROUND_ORDER as readonly string[]).indexOf(a.round || '') - (ROUND_ORDER as readonly string[]).indexOf(b.round || '')
        );
      case 'region':
        return games.sort((a, b) => {
          const regionOrder = (r: string | null) => {
            const order: Record<string, number> = {
              East: 0,
              West: 1,
              South: 2,
              Midwest: 3,
            };
            return order[r || ''] ?? 999;
          };
          const diff = regionOrder(a.region) - regionOrder(b.region);
          return diff !== 0 ? diff : (ROUND_ORDER as readonly string[]).indexOf(a.round || '') - (ROUND_ORDER as readonly string[]).indexOf(b.round || '');
        });
      case 'seed':
        return games.sort((a, b) => {
          const seedA = Math.min(a.seed_home || 999, a.seed_away || 999);
          const seedB = Math.min(b.seed_home || 999, b.seed_away || 999);
          return seedA - seedB;
        });
      default:
        return games;
    }
  }, [bracket.games, sortKey]);

  // Detect upsets (lower seed beat higher seed)
  const isUpset = (game: BracketGame): boolean => {
    if (game.status === 'completed' || game.status === 'closed') {
      if (
        game.score_home !== null &&
        game.score_away !== null &&
        game.seed_home !== null &&
        game.seed_away !== null
      ) {
        const homeWon = game.score_home > game.score_away;
        const seedDiff = game.seed_away - game.seed_home;

        // Upset if lower seed (higher number) won
        return homeWon && seedDiff > 0;
      }
    }
    return false;
  };

  const renderGameRow = (game: BracketGame) => {
    const isCompleted = game.status === 'completed' || game.status === 'closed';
    const isLive = game.status === 'live';
    const hasLink = game.event_id !== null && game.event_id !== undefined;

    // Determine winner
    let homeWon = false;
    let awayWon = false;
    if (isCompleted && game.score_home !== null && game.score_away !== null) {
      homeWon = game.score_home > game.score_away;
      awayWon = game.score_away > game.score_home;
    }

    const upset = isUpset(game);
    const homeProb = game.prob_home ?? 0;
    const awayProb = game.prob_away ?? 0;

    const rowStyle: React.CSSProperties = {
      display: 'grid',
      gridTemplateColumns: '80px 60px 1fr 80px 60px',
      gap: '12px',
      alignItems: 'center',
      padding: '12px 16px',
      borderRadius: '8px',
      background: `var(--mm-card-bg)`,
      border: `1px solid var(--mm-card-border)`,
      marginBottom: '8px',
      cursor: hasLink ? 'pointer' : 'default',
      transition: 'all 0.2s',
      opacity: upset ? 1 : 0.85,
    };

    const hoverStyle: React.CSSProperties = {
      borderColor: hasLink ? `var(--mm-gold)` : `var(--mm-card-border)`,
      transform: hasLink ? 'translateX(4px)' : 'none',
    };

    const rowContent = (
      <div
        style={rowStyle}
        onMouseEnter={(e) => {
          if (hasLink) {
            Object.assign(e.currentTarget.style, hoverStyle);
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = `var(--mm-card-border)`;
          e.currentTarget.style.transform = 'none';
        }}
      >
        {/* Round */}
        <div
          style={{
            fontSize: '12px',
            fontWeight: '600',
            color: `var(--mm-wood-accent)`,
          }}
        >
          {ROUND_SHORT[game.round || '']}
        </div>

        {/* Region */}
        <div
          style={{
            fontSize: '11px',
            color: `var(--mm-text-dim)`,
            textAlign: 'center',
          }}
        >
          {game.region?.[0] || '–'}
        </div>

        {/* Teams */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0 }}>
          {/* Home team */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', minWidth: 0 }}>
            {game.seed_home && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '3px',
                  background: `rgba(139, 69, 19, 0.4)`,
                  color: `var(--mm-wood-pale)`,
                  fontSize: '9px',
                  fontWeight: 'bold',
                  flexShrink: 0,
                }}
              >
                {game.seed_home}
              </span>
            )}
            <span
              style={{
                fontSize: '13px',
                fontWeight: homeWon ? 'bold' : '500',
                color: homeWon ? `var(--mm-gold)` : `var(--mm-text)`,
                opacity: awayWon ? 0.4 : 1,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {game.home_team}
            </span>
          </div>

          {/* Away team */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', minWidth: 0 }}>
            {game.seed_away && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '20px',
                  height: '20px',
                  borderRadius: '3px',
                  background: `rgba(139, 69, 19, 0.4)`,
                  color: `var(--mm-wood-pale)`,
                  fontSize: '9px',
                  fontWeight: 'bold',
                  flexShrink: 0,
                }}
              >
                {game.seed_away}
              </span>
            )}
            <span
              style={{
                fontSize: '13px',
                fontWeight: awayWon ? 'bold' : '500',
                color: awayWon ? `var(--mm-gold)` : `var(--mm-text)`,
                opacity: homeWon ? 0.4 : 1,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {game.away_team}
            </span>
          </div>
        </div>

        {/* Score/Probability */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            textAlign: 'right',
            fontSize: '11px',
          }}
        >
          {isCompleted && game.score_home !== null ? (
            <>
              <span
                style={{
                  fontWeight: homeWon ? 'bold' : '500',
                  color: homeWon ? `var(--mm-gold)` : `var(--mm-text-dim)`,
                }}
              >
                {game.score_home}
              </span>
              <span
                style={{
                  fontWeight: awayWon ? 'bold' : '500',
                  color: awayWon ? `var(--mm-gold)` : `var(--mm-text-dim)`,
                }}
              >
                {game.score_away}
              </span>
            </>
          ) : (
            <>
              <span style={{ color: `var(--mm-text-dim)` }}>{(homeProb * 100).toFixed(0)}%</span>
              <span style={{ color: `var(--mm-text-dim)` }}>{(awayProb * 100).toFixed(0)}%</span>
            </>
          )}
        </div>

        {/* EI / Status */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            alignItems: 'center',
            fontSize: '10px',
          }}
        >
          {/* Excitement Index display removed pending overhaul — L2-156 */}

          {upset && (
            <span
              style={{
                fontWeight: '700',
                color: `var(--mm-upset-red)`,
                padding: '2px 6px',
                borderRadius: '4px',
                background: `rgba(239, 68, 68, 0.1)`,
              }}
            >
              UPSET
            </span>
          )}

          {isLive && (
            <span
              style={{
                fontWeight: '600',
                color: `var(--mm-orange)`,
                fontSize: '9px',
              }}
            >
              LIVE
            </span>
          )}
        </div>
      </div>
    );

    return hasLink ? (
      <Link key={`game-grid-${game.event_id}`} href={`/events/${game.event_id}`}>
        {rowContent}
      </Link>
    ) : (
      <div key={`game-grid-${game.home_team}-${game.away_team}`}>{rowContent}</div>
    );
  };

  return (
    <div
      style={{
        width: '100%',
        padding: '16px',
      }}
    >
      {/* Sort controls */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '16px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: '12px',
            color: `var(--mm-text-dim)`,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          Sort by:
        </span>
        {(['round', 'region', 'seed'] as const).map((key) => (
          <button
            key={key}
            onClick={() => setSortKey(key)}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: `1px solid ${sortKey === key ? `var(--mm-gold)` : `var(--mm-card-border)`}`,
              background: sortKey === key ? `rgba(255, 215, 0, 0.1)` : `var(--mm-card-bg)`,
              color: sortKey === key ? `var(--mm-gold)` : `var(--mm-text)`,
              fontSize: '12px',
              fontWeight: sortKey === key ? '700' : '500',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = `var(--mm-wood-accent)`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor =
                sortKey === key ? `var(--mm-gold)` : `var(--mm-card-border)`;
            }}
          >
            {key.charAt(0).toUpperCase() + key.slice(1)}
          </button>
        ))}
      </div>

      {/* Header row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '80px 60px 1fr 80px 60px',
          gap: '12px',
          padding: '12px 16px',
          marginBottom: '8px',
          borderBottom: `2px solid var(--mm-card-border)`,
          fontSize: '11px',
          fontWeight: '700',
          color: `var(--mm-wood-accent)`,
          textTransform: 'uppercase',
        }}
      >
        <div>Round</div>
        <div style={{ textAlign: 'center' }}>Region</div>
        <div>Teams</div>
        <div style={{ textAlign: 'right' }}>Score/Prob</div>
        <div style={{ textAlign: 'center' }}>Status</div>
      </div>

      {/* Game rows */}
      <div>
        {sortedGames.length > 0 ? (
          sortedGames.map((game) => renderGameRow(game))
        ) : (
          <div
            style={{
              padding: '24px',
              textAlign: 'center',
              color: `var(--mm-text-dim)`,
            }}
          >
            No games available
          </div>
        )}
      </div>

      {/* Stats footer */}
      <div
        style={{
          marginTop: '24px',
          padding: '12px 16px',
          borderTop: `1px solid var(--mm-card-border)`,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: '12px',
          fontSize: '12px',
          color: `var(--mm-text-dim)`,
        }}
      >
        <div>
          <span style={{ fontWeight: '600' }}>Total Games:</span> {bracket.games.length}
        </div>
        <div>
          <span style={{ fontWeight: '600' }}>Completed:</span>{' '}
          {bracket.games.filter((g) => g.status === 'completed' || g.status === 'closed').length}
        </div>
        <div>
          <span style={{ fontWeight: '600' }}>Live:</span> {bracket.games.filter((g) => g.status === 'live').length}
        </div>
        <div>
          <span style={{ fontWeight: '600' }}>Upsets:</span>{' '}
          {bracket.games.filter((g) => isUpset(g)).length}
        </div>
      </div>
    </div>
  );
}
