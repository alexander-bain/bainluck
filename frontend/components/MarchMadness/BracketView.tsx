'use client';

import React, { useMemo, useRef } from 'react';
import Link from 'next/link';
import { BracketGame, MarchMadnessBracket } from '@/lib/types';
import { ROUND_ORDER } from '@/lib/marchMadnessData';

interface BracketProps {
  bracket: MarchMadnessBracket;
}

// Standard NCAA bracket seed order for Round of 64
const R64_SEED_PAIRS: [number, number][] = [
  [1, 16], [8, 9], [5, 12], [4, 13],
  [6, 11], [3, 14], [7, 10], [2, 15],
];

const SEED_TO_R64_SLOT: Record<number, number> = {};
R64_SEED_PAIRS.forEach(([a, b], i) => {
  SEED_TO_R64_SLOT[a] = i;
  SEED_TO_R64_SLOT[b] = i;
});

function getBracketSlot(game: BracketGame, round: string): number {
  const seed = Math.min(game.seed_home || 99, game.seed_away || 99);
  const r64 = SEED_TO_R64_SLOT[seed] ?? 0;
  switch (round) {
    case 'Round of 64': return r64;
    case 'Round of 32': return Math.floor(r64 / 2);
    case 'Sweet 16': return Math.floor(r64 / 4);
    case 'Elite Eight': return 0;
    default: return 0;
  }
}

const REGION_ROUNDS = ['Round of 64', 'Round of 32', 'Sweet 16', 'Elite Eight'] as const;
const CONNECTOR_COLOR = 'rgba(205, 133, 63, 0.35)';

const ROUND_SHORT_LABELS: Record<string, string> = {
  'First Four': 'FF',
  'Round of 64': 'R64',
  'Round of 32': 'R32',
  'Sweet 16': 'S16',
  'Elite Eight': 'E8',
  'Final Four': 'F4',
  Championship: 'NC',
};

// ─── Round Progress Indicator ─────────────────────────────────
function RoundProgress({ games }: { games: BracketGame[] }) {
  const roundStatus = useMemo(() => {
    const status: Record<string, 'completed' | 'active' | 'upcoming'> = {};
    for (const round of ROUND_ORDER) {
      const roundGames = games.filter((g) => g.round === round);
      if (roundGames.length === 0) {
        status[round] = 'upcoming';
      } else if (roundGames.some((g) => g.status === 'live')) {
        status[round] = 'active';
      } else if (roundGames.every((g) => g.status === 'completed' || g.status === 'closed')) {
        status[round] = 'completed';
      } else {
        // Mix of scheduled and completed — treat as active
        const hasCompleted = roundGames.some((g) => g.status === 'completed' || g.status === 'closed');
        status[round] = hasCompleted ? 'active' : 'upcoming';
      }
    }
    return status;
  }, [games]);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 0,
        marginBottom: 20,
        padding: '10px 16px',
        background: 'rgba(139, 69, 19, 0.08)',
        borderRadius: 12,
        overflowX: 'auto',
      }}
    >
      {ROUND_ORDER.map((round, i) => {
        const status = roundStatus[round];
        const isActive = status === 'active';
        const isCompleted = status === 'completed';

        return (
          <React.Fragment key={round}>
            {i > 0 && (
              <div
                style={{
                  width: 16,
                  height: 2,
                  background:
                    isCompleted || isActive
                      ? 'var(--mm-wood-accent)'
                      : 'rgba(139, 69, 19, 0.15)',
                  flexShrink: 0,
                }}
              />
            )}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 3,
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  width: isActive ? 34 : 26,
                  height: isActive ? 34 : 26,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: isActive ? 10 : 9,
                  fontWeight: 700,
                  background: isActive
                    ? 'var(--mm-gold)'
                    : isCompleted
                      ? 'var(--mm-wood-accent)'
                      : 'rgba(139, 69, 19, 0.2)',
                  color:
                    isActive || isCompleted ? '#1a0e08' : 'var(--mm-text-dim)',
                  transition: 'all 0.3s',
                  boxShadow: isActive
                    ? '0 0 12px rgba(255, 215, 0, 0.3)'
                    : 'none',
                }}
              >
                {ROUND_SHORT_LABELS[round]}
              </div>
              {isActive && (
                <div
                  style={{
                    fontSize: 8,
                    color: 'var(--mm-gold)',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                  }}
                >
                  LIVE
                </div>
              )}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Compact Matchup Card ─────────────────────────────────────
function MatchupCard({
  game,
  compact = false,
}: {
  game: BracketGame;
  compact?: boolean;
}) {
  const isCompleted =
    game.status === 'completed' || game.status === 'closed';
  const isLive = game.status === 'live';
  const homeWon =
    isCompleted &&
    game.score_home != null &&
    game.score_away != null &&
    game.score_home > game.score_away;
  const awayWon =
    isCompleted &&
    game.score_home != null &&
    game.score_away != null &&
    game.score_away > game.score_home;

  const isUpset =
    isCompleted &&
    game.seed_home != null &&
    game.seed_away != null &&
    ((homeWon && game.seed_home > game.seed_away) ||
      (awayWon && game.seed_away > game.seed_home));

  const hasLink = game.event_id != null;
  const cardWidth = compact ? 130 : 148;

  const borderColor = isLive
    ? 'var(--mm-orange)'
    : isUpset
      ? 'var(--mm-upset-red)'
      : 'var(--mm-card-border)';

  const content = (
    <div
      className="mm-bracket-card"
      style={{
        width: cardWidth,
        borderRadius: 6,
        background: 'var(--mm-card-bg)',
        border: `1.5px solid ${borderColor}`,
        overflow: 'hidden',
        fontSize: 11,
        cursor: hasLink ? 'pointer' : 'default',
        position: 'relative',
      }}
    >
      {isLive && (
        <div
          className="mm-live-dot"
          style={{
            position: 'absolute',
            top: 3,
            right: 3,
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--mm-orange)',
            boxShadow: '0 0 6px var(--mm-orange)',
          }}
        />
      )}

      {/* Home team */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '4px 6px',
          borderBottom: '1px solid rgba(139, 69, 19, 0.15)',
          opacity: awayWon ? 0.35 : 1,
          background: homeWon ? 'rgba(255, 215, 0, 0.04)' : 'transparent',
        }}
      >
        {game.seed_home != null && (
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: 3,
              background: 'rgba(139, 69, 19, 0.35)',
              color: 'var(--mm-wood-pale)',
              fontSize: 8,
              fontWeight: 700,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {game.seed_home}
          </span>
        )}
        <span
          style={{
            flex: 1,
            fontWeight: homeWon ? 700 : 500,
            color: homeWon ? 'var(--mm-gold)' : 'var(--mm-text)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontSize: compact ? 10 : 11,
          }}
        >
          {game.home_team}
        </span>
        <span
          style={{
            fontWeight: homeWon ? 700 : 400,
            color: homeWon ? 'var(--mm-gold)' : 'var(--mm-text-dim)',
            fontSize: 10,
            minWidth: 20,
            textAlign: 'right',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {isCompleted && game.score_home != null
            ? game.score_home
            : `${((game.prob_home ?? 0) * 100).toFixed(0)}%`}
        </span>
      </div>

      {/* Away team */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '4px 6px',
          opacity: homeWon ? 0.35 : 1,
          background: awayWon ? 'rgba(255, 215, 0, 0.04)' : 'transparent',
        }}
      >
        {game.seed_away != null && (
          <span
            style={{
              width: 16,
              height: 16,
              borderRadius: 3,
              background: 'rgba(139, 69, 19, 0.35)',
              color: 'var(--mm-wood-pale)',
              fontSize: 8,
              fontWeight: 700,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {game.seed_away}
          </span>
        )}
        <span
          style={{
            flex: 1,
            fontWeight: awayWon ? 700 : 500,
            color: awayWon ? 'var(--mm-gold)' : 'var(--mm-text)',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontSize: compact ? 10 : 11,
          }}
        >
          {game.away_team}
        </span>
        <span
          style={{
            fontWeight: awayWon ? 700 : 400,
            color: awayWon ? 'var(--mm-gold)' : 'var(--mm-text-dim)',
            fontSize: 10,
            minWidth: 20,
            textAlign: 'right',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {isCompleted && game.score_away != null
            ? game.score_away
            : `${((game.prob_away ?? 0) * 100).toFixed(0)}%`}
        </span>
      </div>

      {/* Upset flag for exciting games (Excitement Index display removed pending overhaul — L2-156) */}
      {isUpset && (
        <div
          style={{
            padding: '2px 0',
            fontSize: 8,
            fontWeight: 700,
            color: 'var(--mm-gold)',
            background: 'rgba(255, 215, 0, 0.06)',
            textAlign: 'center',
            borderTop: '1px solid rgba(139, 69, 19, 0.15)',
          }}
        >
          UPSET
        </div>
      )}
    </div>
  );

  if (hasLink) {
    return (
      <Link
        href={`/events/${game.event_id}`}
        style={{ textDecoration: 'none' }}
      >
        {content}
      </Link>
    );
  }
  return content;
}

// ─── Bracket Connector Lines ──────────────────────────────────
function BracketConnector({
  numPairs,
  direction = 'ltr',
}: {
  numPairs: number;
  direction?: 'ltr' | 'rtl';
}) {
  if (numPairs <= 0) return null;

  const isLTR = direction === 'ltr';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: 20,
        flexShrink: 0,
        alignSelf: 'stretch',
      }}
    >
      {Array.from({ length: numPairs }, (_, i) => (
        <div key={i} style={{ flex: 1, position: 'relative', minHeight: 40 }}>
          {/* Horizontal line from first game (at 25%) */}
          <div
            style={{
              position: 'absolute',
              top: '25%',
              [isLTR ? 'left' : 'right']: 0,
              width: '50%',
              borderTop: `2px solid ${CONNECTOR_COLOR}`,
            }}
          />
          {/* Horizontal line from second game (at 75%) */}
          <div
            style={{
              position: 'absolute',
              top: '75%',
              [isLTR ? 'left' : 'right']: 0,
              width: '50%',
              borderTop: `2px solid ${CONNECTOR_COLOR}`,
            }}
          />
          {/* Vertical connector between them */}
          <div
            style={{
              position: 'absolute',
              top: '25%',
              bottom: '25%',
              [isLTR ? 'left' : 'right']: '50%',
              borderLeft: `2px solid ${CONNECTOR_COLOR}`,
            }}
          />
          {/* Horizontal line to next round (at 50%) */}
          <div
            style={{
              position: 'absolute',
              top: '50%',
              [isLTR ? 'left' : 'right']: '50%',
              width: '50%',
              borderTop: `2px solid ${CONNECTOR_COLOR}`,
            }}
          />
        </div>
      ))}
    </div>
  );
}

// ─── Region Bracket ───────────────────────────────────────────
function RegionBracket({
  games,
  region,
  direction = 'ltr',
}: {
  games: BracketGame[];
  region: string;
  direction?: 'ltr' | 'rtl';
}) {
  const gamesByRound = useMemo(() => {
    const result: Record<string, BracketGame[]> = {};
    for (const round of REGION_ROUNDS) {
      result[round] = games
        .filter((g) => g.round === round && g.region === region)
        .sort((a, b) => getBracketSlot(a, round) - getBracketSlot(b, round));
    }
    return result;
  }, [games, region]);

  // Determine bracket height based on R64 game count
  const maxGames = Math.max(
    ...REGION_ROUNDS.map((r) => (gamesByRound[r] || []).length),
    1
  );

  return (
    <div>
      {/* Region label */}
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: 'var(--mm-wood-accent)',
          textTransform: 'uppercase',
          letterSpacing: '1px',
          marginBottom: 8,
          textAlign: direction === 'rtl' ? 'right' : 'left',
          paddingLeft: direction === 'ltr' ? 4 : 0,
          paddingRight: direction === 'rtl' ? 4 : 0,
        }}
      >
        {region}
      </div>

      {/* Bracket tree */}
      <div
        style={{
          display: 'flex',
          flexDirection: direction === 'ltr' ? 'row' : 'row-reverse',
          alignItems: 'stretch',
          minHeight: maxGames * 58,
        }}
      >
        {REGION_ROUNDS.map((round, roundIdx) => {
          const roundGames = gamesByRound[round] || [];
          const isFirstRound = roundIdx === 0;
          const isLastRound = roundIdx === REGION_ROUNDS.length - 1;
          const numPairs = Math.floor(roundGames.length / 2);

          return (
            <React.Fragment key={round}>
              {/* Round column */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent:
                    roundGames.length > 0 ? 'space-around' : 'center',
                  flexShrink: 0,
                  gap: 0,
                }}
              >
                {/* Round label (only for first round to save space) */}
                {roundGames.length === 0 && (
                  <div
                    style={{
                      width: isFirstRound ? 130 : 148,
                      height: 44,
                      borderRadius: 6,
                      border: '1.5px dashed rgba(139, 69, 19, 0.15)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 10,
                      color: 'var(--mm-text-dim)',
                      opacity: 0.5,
                    }}
                  >
                    {ROUND_SHORT_LABELS[round] || round}
                  </div>
                )}
                {roundGames.map((game, gi) => (
                  <div key={`${round}-${gi}`} style={{ padding: '3px 0' }}>
                    <MatchupCard game={game} compact={isFirstRound} />
                  </div>
                ))}
              </div>

              {/* Connector lines to next round */}
              {!isLastRound && numPairs > 0 && (
                <BracketConnector
                  numPairs={numPairs}
                  direction={direction}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// ─── Center Column (Final Four + Championship) ────────────────
function CenterBracket({ games }: { games: BracketGame[] }) {
  const f4Games = games.filter((g) => g.round === 'Final Four');
  const champGames = games.filter((g) => g.round === 'Championship');

  if (f4Games.length === 0 && champGames.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          padding: '0 16px',
          minWidth: 180,
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--mm-wood-accent)',
            textTransform: 'uppercase',
            letterSpacing: '1px',
          }}
        >
          Final Four
        </div>
        <div
          style={{
            width: 148,
            height: 44,
            borderRadius: 6,
            border: '1.5px dashed rgba(139, 69, 19, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
            color: 'var(--mm-text-dim)',
            opacity: 0.5,
          }}
        >
          TBD
        </div>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: 'var(--mm-gold)',
          }}
        >
          Championship
        </div>
        <div
          style={{
            width: 148,
            height: 44,
            borderRadius: 6,
            border: '1.5px dashed rgba(255, 215, 0, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
            color: 'var(--mm-text-dim)',
            opacity: 0.5,
          }}
        >
          TBD
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: '0 12px',
        minWidth: 180,
      }}
    >
      {/* Final Four label */}
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: 'var(--mm-wood-accent)',
          textTransform: 'uppercase',
          letterSpacing: '1px',
          marginBottom: 4,
        }}
      >
        Final Four
      </div>

      {/* F4 games */}
      {f4Games.map((game, i) => (
        <div key={`f4-${i}`}>
          <MatchupCard game={game} />
        </div>
      ))}

      {/* Connector between F4 and Championship */}
      {f4Games.length >= 2 && champGames.length > 0 && (
        <div style={{ width: 2, height: 12, background: CONNECTOR_COLOR }} />
      )}

      {/* Championship label */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 12,
          fontWeight: 700,
          color: 'var(--mm-gold)',
        }}
      >
        Championship
      </div>

      {/* Championship game */}
      {champGames.map((game, i) => (
        <div
          key={`champ-${i}`}
          style={{
            padding: 3,
            borderRadius: 10,
            background: 'rgba(255, 215, 0, 0.06)',
            border: '1px solid rgba(255, 215, 0, 0.15)',
          }}
        >
          <MatchupCard game={game} />
        </div>
      ))}

      {champGames.length === 0 && (
        <div
          style={{
            width: 148,
            height: 44,
            borderRadius: 6,
            border: '1.5px dashed rgba(255, 215, 0, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
            color: 'var(--mm-text-dim)',
            opacity: 0.5,
          }}
        >
          TBD
        </div>
      )}
    </div>
  );
}

// ─── Main Bracket View ────────────────────────────────────────
export default function BracketView({ bracket }: BracketProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Determine region pairs for left/right sides
  // Standard NCAA: East+West on left, South+Midwest on right
  const regions = bracket.regions.length >= 4
    ? bracket.regions
    : ['East', 'West', 'South', 'Midwest'];

  const leftRegions = [regions[0], regions[1]];
  const rightRegions = [regions[2], regions[3]];

  return (
    <div style={{ width: '100%' }}>
      {/* Round progress indicator */}
      <RoundProgress games={bracket.games} />

      {/* Bracket tree */}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          overflowX: 'auto',
          overflowY: 'hidden',
          paddingBottom: 16,
        }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'row',
            alignItems: 'stretch',
            gap: 0,
            minWidth: 1400,
            padding: '8px 12px',
          }}
        >
          {/* Left regions (flow left → right) */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 32,
              flex: 1,
            }}
          >
            {leftRegions.map((region) => (
              <RegionBracket
                key={region}
                games={bracket.games}
                region={region}
                direction="ltr"
              />
            ))}
          </div>

          {/* Center: Final Four + Championship */}
          <CenterBracket games={bracket.games} />

          {/* Right regions (flow right → left, mirrored) */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 32,
              flex: 1,
            }}
          >
            {rightRegions.map((region) => (
              <RegionBracket
                key={region}
                games={bracket.games}
                region={region}
                direction="rtl"
              />
            ))}
          </div>
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 16,
          justifyContent: 'center',
          padding: '12px 16px',
          fontSize: 10,
          color: 'var(--mm-text-dim)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              border: '1.5px solid var(--mm-orange)',
              background: 'rgba(255, 107, 53, 0.15)',
            }}
          />
          Live
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              border: '1.5px solid var(--mm-upset-red)',
              background: 'rgba(239, 68, 68, 0.15)',
            }}
          />
          Upset
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background: 'rgba(255, 215, 0, 0.15)',
              border: '1px solid rgba(255, 215, 0, 0.3)',
            }}
          />
          Winner
        </div>
      </div>
    </div>
  );
}
