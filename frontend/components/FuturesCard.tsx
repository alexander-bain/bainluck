"use client";

import Link from "next/link";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";
import { formatProbability, formatAmericanOdds } from "@/lib/api";
import { getEmojiForCategory, getEmojiForLeague } from "@/lib/sportCategories";
import PersonalizedBadge from "./PersonalizedBadge";

interface FuturesCardProps {
  market: FuturesMarket;
  showSport?: boolean;
  isPinned?: boolean;
  onPinToggle?: (futuresId: number) => void;
  pinDisabled?: boolean;
  /** Whether this item was personalized by the feed */
  personalized?: boolean;
  /** Personalization multiplier */
  multiplier?: number;
  /** Personalization reason strings */
  personalizationReasons?: string[];
}

function formatSportName(sportKey: string | null, sportName: string | null): string {
  if (sportName) return sportName;
  if (!sportKey) return "Sports";
  return sportKey
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function MovementIndicator({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined || change === 0 || !Number.isFinite(change)) return null;

  const isPositive = change > 0;
  const absChange = Math.abs(change * 100);

  return (
    <span className={`text-[11px] font-medium ${isPositive ? "text-accent-live" : "text-accent-danger"}`}>
      {isPositive ? "↑" : "↓"} {absChange.toFixed(1)}%
    </span>
  );
}

export default function FuturesCard({
  market,
  showSport = true,
  isPinned = false,
  onPinToggle,
  pinDisabled = false,
  personalized,
  multiplier,
  personalizationReasons,
}: FuturesCardProps) {
  const outcomes = market.top_outcomes || market.outcomes || [];
  const topOutcomes = outcomes.slice(0, 5);
  const isResolved = market.status === "resolved";

  const handlePinClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onPinToggle) {
      onPinToggle(market.id);
    }
  };

  return (
    <Link href={`/futures/${market.id}`} className="h-full">
      <div className={`
        h-full flex flex-col rounded-card p-3 sm:p-4 transition-all cursor-pointer group/card
        bg-surface-card border border-surface-border
        hover:bg-surface-elevated hover:shadow-card-hover
        ${isResolved ? "opacity-70 hover:opacity-100" : ""}
      `}>
        {/* Header */}
        <div className="flex justify-between items-start gap-2 mb-2">
          <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
            {showSport && (
              <span className="text-micro-xs text-text-muted uppercase tracking-widest truncate">
                {market.llm_sport_category || formatSportName(market.sport, market.sport_name)}
              </span>
            )}
            {market.category && (
              <span className="text-[10px] bg-accent-futures/15 text-accent-futures px-1.5 py-0.5 rounded">
                {market.category}
              </span>
            )}
            <PersonalizedBadge
              personalized={personalized}
              multiplier={multiplier}
              personalizationReasons={personalizationReasons}
            />
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {isResolved && (
              <span className="text-micro-xs text-text-muted uppercase">Resolved</span>
            )}
            {market.outcome_count > 0 && (
              <span className="text-micro text-text-muted">
                {market.outcome_count}
              </span>
            )}
            {onPinToggle && (
              <button
                onClick={handlePinClick}
                disabled={pinDisabled && !isPinned}
                className={`
                  p-1 rounded transition-all
                  ${isPinned
                    ? 'text-accent-warning'
                    : 'text-text-muted/30 hover:text-text-muted group-hover/card:text-text-muted/50'
                  }
                  ${pinDisabled && !isPinned ? 'cursor-not-allowed opacity-30' : ''}
                `}
                title={isPinned ? 'Unpin' : pinDisabled ? 'Max 6 pins' : 'Pin'}
                aria-label={isPinned ? 'Unpin market' : 'Pin market'}
              >
                <PinIcon filled={isPinned} className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Market Name */}
        <h3 className="text-sm font-medium text-text-primary mb-3 line-clamp-2 leading-snug">
          {market.name}
        </h3>

        {/* Top Outcomes */}
        <div className="space-y-2 flex-grow">
          {topOutcomes.map((outcome, index) => (
            <OutcomeRow
              key={outcome.id}
              outcome={outcome}
              rank={index + 1}
              isLeader={index === 0}
              isResolved={isResolved}
            />
          ))}

          {outcomes.length === 0 && (
            <div className="text-sm text-text-muted text-center py-4">
              No outcomes available
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex justify-between items-center">
          <div className="text-micro text-text-muted">
            {market.source && <span>{market.source}</span>}
          </div>
          {market.updated_at && (
            <span className="text-micro text-text-muted">
              {formatRelativeTime(market.updated_at)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

function OutcomeRow({
  outcome,
  rank,
  isLeader,
  isResolved,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isResolved: boolean;
}) {
  const movement = outcome.movement ?? outcome.probability_change_24h;
  const prob = outcome.probability ?? 0;

  return (
    <div className="flex items-center gap-2">
      {/* Rank */}
      <span className={`w-5 h-5 flex items-center justify-center text-[10px] rounded flex-shrink-0 ${
        isLeader
          ? "bg-accent-warning/15 text-accent-warning font-bold"
          : "text-text-muted"
      }`}>
        {rank}
      </span>

      {/* Name + mini bar */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm truncate ${
            isLeader ? "font-medium text-text-primary" : "text-text-secondary"
          }`}>
            {outcome.name}
          </span>
          {outcome.is_winner && (
            <span className="text-[10px] bg-accent-live/15 text-accent-live px-1 py-0.5 rounded flex-shrink-0">
              ✓
            </span>
          )}
        </div>
        {/* Mini probability bar */}
        <div className="h-1 rounded-full bg-surface-border mt-1 overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.min(prob * 100, 100)}%`,
              backgroundColor: isLeader ? "var(--accent-futures)" : "var(--text-muted)",
              opacity: isLeader ? 0.7 : 0.3,
            }}
          />
        </div>
      </div>

      {/* Probability + movement */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <MovementIndicator change={movement} />
        <span className={`font-mono text-sm tabular-nums ${
          isLeader ? "font-bold text-text-primary" : "text-text-muted"
        }`}>
          {formatProbability(outcome.probability)}
        </span>
      </div>
    </div>
  );
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z"/>
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
    </svg>
  );
}
