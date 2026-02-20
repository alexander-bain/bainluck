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

// ============================================================================
// Event Feed Card
// ============================================================================

function EventFeedCard({ item, data }: { item: FeedItem; data: FeedEventData }) {
  const isLive = data.status === "live";
  const isFinished = data.status === "completed" || data.status === "closed";
  const homeProb = data.current_odds?.home_probability ?? null;
  const awayProb = data.current_odds?.away_probability ?? null;

  // Card styling based on state
  const cardBorder = isLive
    ? "border-l-4 border-l-emerald-400 bg-gradient-to-r from-emerald-50/50 to-white"
    : isFinished
    ? "border-l-4 border-l-slate-300 bg-slate-50/50"
    : "border-l-4 border-l-amber-300 bg-white";

  return (
    <Link href={`/events/${data.id}`}>
      <div className={`rounded-lg border border-mist shadow-sm p-3 sm:p-4 hover:shadow-md transition-all cursor-pointer ${cardBorder}`}>
        {/* Top row: headline badge + sport + score */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2 min-w-0">
            {/* Status badge */}
            {isLive && (
              <span className="flex items-center gap-1 bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap flex-shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            )}
            {item.headline && !isLive && (
              <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap flex-shrink-0">
                {item.headline}
              </span>
            )}
            {/* Sport label */}
            {data.sport && (
              <span className="text-xs text-slate truncate">
                {getEmojiForLeague(data.sport)} {getLeagueDisplay(data.sport)}
              </span>
            )}
          </div>

          {/* Score for live/finished games */}
          {(isLive || isFinished) && data.home_score !== null && data.away_score !== null && (
            <span className={`text-sm font-mono font-bold flex-shrink-0 ${
              isLive ? "text-emerald-700" : "text-graphite"
            }`}>
              {data.home_score} - {data.away_score}
            </span>
          )}
        </div>

        {/* Main row: teams + probability bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Teams */}
            <div className="text-sm font-semibold text-graphite truncate">
              {data.away_team} <span className="text-slate font-normal">at</span> {data.home_team}
            </div>
            {/* Reason text */}
            <p className="text-xs text-slate mt-0.5 truncate">{item.reason}</p>
          </div>

          {/* Probability display */}
          {homeProb !== null && awayProb !== null && (
            <div className="flex-shrink-0 text-right">
              <div className="flex items-center gap-1.5">
                <span className={`text-sm font-bold ${homeProb >= 0.5 ? "text-graphite" : "text-slate"}`}>
                  {formatProbability(homeProb)}
                </span>
                <span className="text-xs text-silver">-</span>
                <span className={`text-sm font-bold ${awayProb >= 0.5 ? "text-graphite" : "text-slate"}`}>
                  {formatProbability(awayProb)}
                </span>
              </div>
              {/* Mini probability bar */}
              <div className="w-16 h-1 rounded-full bg-slate-200 mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full bg-graphite transition-all"
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
      <div className="rounded-lg border border-mist border-l-4 border-l-purple-300 bg-gradient-to-r from-purple-50/30 to-white shadow-sm p-3 sm:p-4 hover:shadow-md transition-all cursor-pointer">
        {/* Top row: headline badge + sport + source count */}
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2 min-w-0">
            {item.headline && (
              <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap flex-shrink-0">
                {item.headline}
              </span>
            )}
            <span className="text-xs text-slate truncate">
              {data.llm_sport_category
                ? `${data.llm_sport_category.charAt(0).toUpperCase()}${data.llm_sport_category.slice(1)}`
                : "Futures"}
            </span>
          </div>

          {/* Source count badge */}
          {data.source_count > 1 && (
            <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded font-medium flex-shrink-0">
              {data.source_count} sources
            </span>
          )}
        </div>

        {/* Main row: market name + leader + probability */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Market name */}
            <div className="text-sm font-semibold text-graphite truncate">
              {data.name}
            </div>
            {/* Reason text */}
            <p className="text-xs text-slate mt-0.5 truncate">{item.reason}</p>
          </div>

          {/* Leader display */}
          {leader && leaderProb !== null && (
            <div className="flex-shrink-0 text-right">
              <div className="text-sm font-bold text-graphite">
                {formatProbability(leaderProb)}
              </div>
              <div className="text-xs text-slate truncate max-w-[100px]">
                {leader.name}
              </div>
              {/* Movement arrow */}
              {leader.movement !== null && leader.movement !== undefined && leader.movement !== 0 && (
                <div className={`text-xs font-medium ${
                  leader.movement > 0 ? "text-emerald-600" : "text-red-500"
                }`}>
                  {leader.movement > 0 ? "+" : ""}{(leader.movement * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}
        </div>

        {/* Top outcomes mini-list (if more than leader) */}
        {data.top_outcomes.length > 1 && (
          <div className="flex gap-3 mt-2 pt-2 border-t border-mist/50">
            {data.top_outcomes.slice(0, 3).map((outcome, i) => (
              <div key={outcome.id} className="text-xs text-slate">
                <span className="text-silver mr-1">#{i + 1}</span>
                <span className="font-medium">{outcome.name.split(" ").pop()}</span>
                {outcome.probability !== null && (
                  <span className="ml-1 text-graphite font-bold">
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
