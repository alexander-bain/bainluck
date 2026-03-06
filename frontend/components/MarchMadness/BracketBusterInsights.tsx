'use client';

import React from 'react';
import { BracketBusterInsight } from '@/lib/types';

interface BracketBusterInsightsProps {
  insights: BracketBusterInsight[];
}

export default function BracketBusterInsights({
  insights,
}: BracketBusterInsightsProps) {
  // Return null if no insights
  if (!insights || insights.length === 0) {
    return null;
  }

  // Sort by absolute delta (biggest impact first)
  const sortedInsights = [...insights].sort((a, b) =>
    Math.abs(b.title_odds_delta) - Math.abs(a.title_odds_delta)
  );

  return (
    <div
      style={{
        marginTop: '2rem',
        padding: '1.5rem',
        backgroundColor: 'var(--mm-card-bg)',
        border: '1px solid var(--mm-card-border)',
        borderRadius: '8px',
      }}
    >
      <h3
        style={{
          fontSize: '1.25rem',
          fontWeight: '600',
          color: 'var(--mm-text)',
          marginBottom: '1rem',
          marginTop: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <span style={{ fontSize: '1.5rem' }}>🏀</span>
        Bracket Buster Insights
      </h3>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: '1rem',
        }}
      >
        {sortedInsights.map((insight, index) => {
          const isPositive = insight.title_odds_delta >= 0;
          const deltaPercent =
            insight.title_odds_before > 0
              ? ((insight.title_odds_delta / insight.title_odds_before) * 100).toFixed(0)
              : 0;
          const arrowColor = isPositive
            ? 'var(--mm-gold)'
            : 'var(--mm-upset-red)';
          const arrowText = isPositive ? '↑' : '↓';

          return (
            <div
              key={index}
              style={{
                padding: '1rem',
                backgroundColor: 'var(--mm-wood-accent)',
                border: '1px solid var(--mm-wood-pale)',
                borderRadius: '6px',
              }}
            >
              {/* Winner/Loser Section */}
              <div style={{ marginBottom: '0.75rem' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    marginBottom: '0.25rem',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.875rem',
                      fontWeight: '600',
                      color: 'var(--mm-gold)',
                    }}
                  >
                    {insight.seed_winner && `#${insight.seed_winner}`}
                  </span>
                  <span style={{ color: 'var(--mm-text)', fontWeight: '600' }}>
                    {insight.winner}
                  </span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    marginBottom: '0.5rem',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.875rem',
                      fontWeight: '600',
                      color: 'var(--mm-upset-red)',
                    }}
                  >
                    {insight.seed_loser && `#${insight.seed_loser}`}
                  </span>
                  <span style={{ color: 'var(--mm-text-dim)' }}>
                    {insight.loser}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: '0.875rem',
                    color: 'var(--mm-text-dim)',
                    fontWeight: '500',
                  }}
                >
                  {insight.score}
                </div>
              </div>

              {/* Round Badge */}
              {insight.round && (
                <div
                  style={{
                    display: 'inline-block',
                    fontSize: '0.75rem',
                    fontWeight: '600',
                    color: 'var(--mm-text)',
                    backgroundColor: 'var(--mm-wood-pale)',
                    padding: '0.25rem 0.5rem',
                    borderRadius: '4px',
                    marginBottom: '0.75rem',
                  }}
                >
                  {insight.round}
                </div>
              )}

              {/* Title Odds Section */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.75rem',
                  backgroundColor: 'rgba(0, 0, 0, 0.2)',
                  borderRadius: '4px',
                  marginBottom: '0.75rem',
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: '0.75rem',
                      color: 'var(--mm-text-dim)',
                      marginBottom: '0.25rem',
                    }}
                  >
                    Before
                  </div>
                  <div
                    style={{
                      fontSize: '1rem',
                      fontWeight: '600',
                      color: 'var(--mm-text)',
                    }}
                  >
                    {(insight.title_odds_before * 100).toFixed(1)}%
                  </div>
                </div>

                <div
                  style={{
                    fontSize: '1.5rem',
                    color: arrowColor,
                    fontWeight: '600',
                  }}
                >
                  {arrowText}
                </div>

                <div>
                  <div
                    style={{
                      fontSize: '0.75rem',
                      color: 'var(--mm-text-dim)',
                      marginBottom: '0.25rem',
                    }}
                  >
                    After
                  </div>
                  <div
                    style={{
                      fontSize: '1rem',
                      fontWeight: '600',
                      color: 'var(--mm-text)',
                    }}
                  >
                    {(insight.title_odds_after * 100).toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Delta Percentage */}
              <div
                style={{
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  color: arrowColor,
                  textAlign: 'center',
                  marginBottom: insight.narrative ? '0.75rem' : 0,
                }}
              >
                {isPositive ? '+' : ''}{deltaPercent}%
              </div>

              {/* Narrative Text */}
              {insight.narrative && (
                <div
                  style={{
                    fontSize: '0.875rem',
                    color: 'var(--mm-text-dim)',
                    lineHeight: '1.5',
                    fontStyle: 'italic',
                    borderTop: '1px solid var(--mm-wood-pale)',
                    paddingTop: '0.75rem',
                  }}
                >
                  &ldquo;{insight.narrative}&rdquo;
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
