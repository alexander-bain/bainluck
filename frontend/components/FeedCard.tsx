"use client";

import Link from "next/link";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague, getCategoryForFutures } from "@/lib/sportCategories";

interface FeedCardProps {
  item: FeedItem;
}

export default function FeedCard({ item }: FeedCardProps) {
  if (item.type === "event") {
    return <EventFeedCard item={item} data={item.data as FeedEventData} />;
  }
  return <FuturesFeedCard item={item} data={item.data as FeedFuturesData} />;
}

/**
 * Personalization badge — shown on boosted items
 */
function PersonalizedBadge({ item }: { item: FeedItem }) {
  if (!item.personalized) return null;

  const label = getPersonalizationLabel(item.personalization_reasons);

  return (
    <span
      className="inline-flex items-center gap-1 bg-accent-brand/15 text-accent-brand px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0"
      title={`Boosted ${item.multiplier}x because: ${item.personalization_reasons?.join(", ")}`}
    >
      <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
      </svg>
      {label}
    </span>
  );
}

function getPersonalizationLabel(reasons?: string[]): string {
  if (!reasons || reasons.length === 0) return "For you";

  for (const r of reasons) {
    if (r.startsWith("your_team")) return "Your team";
    if (r.startsWith("rival_losing")) return "Rival losing";
    if (r.startsWith("rival")) return "Rival watch";
    if (r.startsWith("local_team")) return "Local";
    if (r.startsWith("alma_mater")) return "Alma mater";
    if (r.startsWith("pinned")) return "Pinned";
    if (r.startsWith("sport_boost")) return "For you";
  }

  return "For you";
}

// ============================================================================
// Event Feed Card
// ============================================================================

function EventFeedCard({ item, data }: { item: FeedItem; data: FeedEventData }) {
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
            <PersonalizedBadge item={item} />
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
      </div>
    </Link>
  );
}

// ============================================================================
// Futures Feed Card
// ============================================================================

function FuturesFeedCard({ item, data }: { item: FeedItem; data: FeedFuturesData }) {
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
            <PersonalizedBadge item={item} />
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
      </div>
    </Link>
  );
}
