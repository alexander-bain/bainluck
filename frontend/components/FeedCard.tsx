"use client";

import Link from "next/link";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague, getCategoryForFutures } from "@/lib/sportCategories";
import PersonalizedBadge from "./PersonalizedBadge";

interface FeedCardProps {
  item: FeedItem;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}

export default function FeedCard({ item, onThumbsUp, onThumbsDown, category }: FeedCardProps) {
  if (item.type === "event") {
    return (
      <EventFeedCard
        item={item}
        data={item.data as FeedEventData}
        onThumbsUp={onThumbsUp}
        onThumbsDown={onThumbsDown}
        category={category}
      />
    );
  }
  return (
    <FuturesFeedCard
      item={item}
      data={item.data as FeedFuturesData}
      onThumbsUp={onThumbsUp}
      onThumbsDown={onThumbsDown}
      category={category}
    />
  );
}

// ============================================================================
// Thumbs buttons — shared by both card types
// ============================================================================

function ThumbButtons({
  category,
  onThumbsUp,
  onThumbsDown,
}: {
  category?: string;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
}) {
  if (!category || (!onThumbsUp && !onThumbsDown)) return null;

  return (
    <div className="flex items-center gap-0.5 ml-auto flex-shrink-0">
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onThumbsUp?.(category);
        }}
        className="p-1 text-text-muted/40 hover:text-accent-live transition-colors rounded"
        title="More like this"
        aria-label="More like this"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 10v12" />
          <path d="M15 5.88L14 10h5.83a2 2 0 011.92 2.56l-2.33 8A2 2 0 0117.5 22H4a2 2 0 01-2-2v-8a2 2 0 012-2h2.76a2 2 0 001.79-1.11L12 2a3.13 3.13 0 013 3.88z" />
        </svg>
      </button>
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onThumbsDown?.(category);
        }}
        className="p-1 text-text-muted/40 hover:text-accent-danger transition-colors rounded"
        title="Less like this"
        aria-label="Less like this"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 14V2" />
          <path d="M9 18.12L10 14H4.17a2 2 0 01-1.92-2.56l2.33-8A2 2 0 016.5 2H20a2 2 0 012 2v8a2 2 0 01-2 2h-2.76a2 2 0 00-1.79 1.11L12 22a3.13 3.13 0 01-3-3.88z" />
        </svg>
      </button>
    </div>
  );
}

// ============================================================================
// Event Feed Card
// ============================================================================

function EventFeedCard({
  item,
  data,
  onThumbsUp,
  onThumbsDown,
  category,
}: {
  item: FeedItem;
  data: FeedEventData;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}) {
  const isLive = data.status === "live";
  const isFinished = data.status === "completed" || data.status === "closed";
  const homeProb = data.current_odds?.home_probability ?? null;
  const awayProb = data.current_odds?.away_probability ?? null;

  return (
    <Link href={`/events/${data.id}`}>
      <div className={`
        rounded-card border border-surface-border bg-surface-card
        p-3 hover:bg-surface-elevated transition-all cursor-pointer
        ${isLive ? "ring-1 ring-accent-live/20" : ""}
        ${isFinished ? "opacity-70 hover:opacity-100" : ""}
      `}>
        {/* Top row: badges */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            {isLive && (
              <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-1.5 py-0.5 rounded text-[10px] font-semibold flex-shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                LIVE
              </span>
            )}
            {item.headline && !isLive && (
              <span className="bg-accent-warning/15 text-accent-warning px-1.5 py-0.5 rounded text-[10px] font-semibold flex-shrink-0">
                {item.headline}
              </span>
            )}
            <PersonalizedBadge
              personalized={item.personalized}
              multiplier={item.multiplier}
              personalizationReasons={item.personalization_reasons}
            />
            {data.sport && (
              <span className="text-[10px] text-text-muted uppercase tracking-wider truncate">
                {getLeagueDisplay(data.sport)}
              </span>
            )}
          </div>

          {(isLive || isFinished) && data.home_score !== null && data.away_score !== null && (
            <span className={`text-sm font-mono font-bold flex-shrink-0 ${
              isLive ? "text-accent-live" : "text-text-primary"
            }`}>
              {data.home_score} - {data.away_score}
            </span>
          )}
        </div>

        {/* Main row: teams + probability */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">
              {data.away_team} <span className="text-text-muted font-normal">at</span> {data.home_team}
            </div>
            <p className="text-[11px] text-text-muted mt-0.5 truncate">{item.reason}</p>
          </div>

          {homeProb !== null && awayProb !== null && (
            <div className="flex-shrink-0 text-right">
              <div className="flex items-center gap-1">
                <span className={`font-mono text-sm font-bold ${homeProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                  {formatProbability(homeProb)}
                </span>
                <span className="text-[10px] text-text-muted">-</span>
                <span className={`font-mono text-sm font-bold ${awayProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                  {formatProbability(awayProb)}
                </span>
              </div>
              {/* Mini probability bar */}
              <div className="w-16 h-1 rounded-full bg-surface-border mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent-brand transition-all"
                  style={{ width: `${Math.round((homeProb) * 100)}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Bottom row: thumbs */}
        <div className="flex items-center justify-end mt-1">
          <ThumbButtons
            category={category}
            onThumbsUp={onThumbsUp}
            onThumbsDown={onThumbsDown}
          />
        </div>
      </div>
    </Link>
  );
}

// ============================================================================
// Futures Feed Card
// ============================================================================

function FuturesFeedCard({
  item,
  data,
  onThumbsUp,
  onThumbsDown,
  category,
}: {
  item: FeedItem;
  data: FeedFuturesData;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}) {
  const leader = data.top_outcomes?.[0];
  const leaderProb = leader?.probability;

  return (
    <Link href={`/futures/${data.id}`}>
      <div className="rounded-card border border-surface-border bg-surface-card p-3 hover:bg-surface-elevated transition-all cursor-pointer">
        {/* Top row */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            {item.headline && (
              <span className="bg-accent-futures/15 text-accent-futures px-1.5 py-0.5 rounded text-[10px] font-semibold flex-shrink-0">
                {item.headline}
              </span>
            )}
            <PersonalizedBadge
              personalized={item.personalized}
              multiplier={item.multiplier}
              personalizationReasons={item.personalization_reasons}
            />
            <span className="text-[10px] text-text-muted uppercase tracking-wider truncate">
              {data.llm_sport_category
                ? `${data.llm_sport_category.charAt(0).toUpperCase()}${data.llm_sport_category.slice(1)}`
                : "Futures"}
            </span>
          </div>

          {data.source_count > 1 && (
            <span className="text-[10px] bg-accent-futures/10 text-accent-futures px-1.5 py-0.5 rounded font-medium flex-shrink-0">
              {data.source_count} sources
            </span>
          )}
        </div>

        {/* Main row */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">
              {data.name}
            </div>
            <p className="text-[11px] text-text-muted mt-0.5 truncate">{item.reason}</p>
          </div>

          {leader && leaderProb !== null && (
            <div className="flex-shrink-0 text-right">
              <div className="font-mono text-sm font-bold text-text-primary">
                {formatProbability(leaderProb)}
              </div>
              <div className="text-[11px] text-text-muted truncate max-w-[100px]">
                {leader.name}
              </div>
              {leader.movement !== null && leader.movement !== undefined && leader.movement !== 0 && (
                <div className={`text-[10px] font-medium ${
                  leader.movement > 0 ? "text-accent-live" : "text-accent-danger"
                }`}>
                  {leader.movement > 0 ? "+" : ""}{(leader.movement * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}
        </div>

        {/* Top outcomes mini-list */}
        {data.top_outcomes.length > 1 && (
          <div className="flex gap-3 mt-2 pt-2 border-t border-surface-border/50">
            {data.top_outcomes.slice(0, 3).map((outcome, i) => (
              <div key={outcome.id} className="text-[11px] text-text-muted">
                <span className="text-text-muted/50 mr-1">#{i + 1}</span>
                <span className="font-medium text-text-secondary">{outcome.name.split(" ").pop()}</span>
                {outcome.probability !== null && (
                  <span className="ml-1 font-mono font-bold text-text-primary">
                    {Math.round(outcome.probability * 100)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Bottom row: thumbs */}
        <div className="flex items-center justify-end mt-1">
          <ThumbButtons
            category={category}
            onThumbsUp={onThumbsUp}
            onThumbsDown={onThumbsDown}
          />
        </div>
      </div>
    </Link>
  );
}
