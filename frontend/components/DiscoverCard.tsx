"use client";

import { useState } from "react";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";

const CATEGORY_GRADIENTS: Record<string, string> = {
  basketball: "linear-gradient(135deg, #7c2d12, #c2410c)",
  football: "linear-gradient(135deg, #14532d, #15803d)",
  baseball: "linear-gradient(135deg, #7f1d1d, #b91c1c)",
  hockey: "linear-gradient(135deg, #1e3a5f, #2563eb)",
  soccer: "linear-gradient(135deg, #064e3b, #059669)",
  golf: "linear-gradient(135deg, #14532d, #166534)",
  mma: "linear-gradient(135deg, #450a0a, #991b1b)",
  boxing: "linear-gradient(135deg, #450a0a, #991b1b)",
  motorsports: "linear-gradient(135deg, #1c1917, #44403c)",
  economics: "linear-gradient(135deg, #2e1065, #7c3aed)",
  culture: "linear-gradient(135deg, #831843, #db2777)",
  tech: "linear-gradient(135deg, #083344, #0891b2)",
  politics: "linear-gradient(135deg, #1e1b4b, #4338ca)",
  olympics: "linear-gradient(135deg, #78350f, #d97706)",
  cricket: "linear-gradient(135deg, #134e4a, #14b8a6)",
};

const CATEGORY_COLORS: Record<string, { bg: string; text: string; emoji: string }> = {
  basketball: { bg: "bg-orange-500/15", text: "text-orange-600", emoji: "🏀" },
  football: { bg: "bg-green-700/15", text: "text-green-700", emoji: "🏈" },
  baseball: { bg: "bg-red-500/15", text: "text-red-600", emoji: "⚾" },
  hockey: { bg: "bg-blue-500/15", text: "text-blue-600", emoji: "🏒" },
  soccer: { bg: "bg-emerald-500/15", text: "text-emerald-600", emoji: "⚽" },
  golf: { bg: "bg-lime-600/15", text: "text-lime-700", emoji: "⛳" },
  mma: { bg: "bg-red-700/15", text: "text-red-700", emoji: "🥊" },
  boxing: { bg: "bg-red-600/15", text: "text-red-600", emoji: "🥊" },
  motorsports: { bg: "bg-gray-600/15", text: "text-gray-600", emoji: "🏎" },
  economics: { bg: "bg-violet-500/15", text: "text-violet-600", emoji: "📈" },
  culture: { bg: "bg-pink-500/15", text: "text-pink-600", emoji: "🎭" },
  tech: { bg: "bg-cyan-500/15", text: "text-cyan-600", emoji: "💻" },
  politics: { bg: "bg-indigo-500/15", text: "text-indigo-600", emoji: "🏛" },
  olympics: { bg: "bg-amber-500/15", text: "text-amber-600", emoji: "🏅" },
  cricket: { bg: "bg-teal-500/15", text: "text-teal-600", emoji: "🏏" },
};

function getCategoryStyle(cat: string | null | undefined) {
  if (!cat) return { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
  return CATEGORY_COLORS[cat.toLowerCase()] ?? { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
}

interface DiscoverCardProps {
  item: FeedItem;
  onDismiss?: () => void;
}

export default function DiscoverCard({ item, onDismiss }: DiscoverCardProps) {
  const [liked, setLiked] = useState(false);

  if (item.type === "event") {
    return <EventCard item={item} data={item.data as FeedEventData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} />;
  }
  if (item.type === "futures") {
    return <FuturesCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} />;
  }
  if (item.type === "tournament") {
    return <TournamentCard item={item} data={item.data as FeedTournamentData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} />;
  }
  return null;
}

// ── Event Card ──

function EventCard({
  item, data, liked, setLiked, onDismiss,
}: {
  item: FeedItem; data: FeedEventData;
  liked: boolean; setLiked: (v: boolean) => void;
  onDismiss?: () => void;
}) {
  const homeColor = data.home_team_data?.primary_color || "#374151";
  const awayColor = data.away_team_data?.primary_color || "#6b7280";
  const homeLogo = data.home_team_data?.logo_small;
  const awayLogo = data.away_team_data?.logo_small;
  const isLive = data.status === "live";
  const isDone = data.status === "completed" || data.status === "closed";
  const homeProb = data.current_odds?.home_probability;
  const awayProb = data.current_odds?.away_probability;

  const category = data.sport_name || "Sports";
  const catStyle = getCategoryStyle(data.sport?.split("_")[0]);

  const headline = item.headline || (isLive ? "Live now" : isDone ? "Final" : data.highlight?.label || "Upcoming");

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg">
      {/* Dismiss button */}
      {onDismiss && (
        <button onClick={onDismiss} className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
        </button>
      )}

      {/* Hero visual — team logos on gradient */}
      <div
        className="relative h-44 flex items-center justify-center gap-6"
        style={{
          background: `linear-gradient(135deg, ${awayColor}22, ${homeColor}22)`,
        }}
      >
        {/* Category pill */}
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full`}>
          {catStyle.emoji} {category}
        </div>

        {isLive && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            LIVE
          </div>
        )}

        {/* Away team */}
        <div className="flex flex-col items-center gap-2">
          {awayLogo ? (
            <img src={awayLogo} alt="" className="w-16 h-16 object-contain drop-shadow-md" />
          ) : (
            <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: awayColor }}>
              {(data.away_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}
            </div>
          )}
          {isDone && data.away_score != null && (
            <span className="text-2xl font-black tabular-nums">{data.away_score}</span>
          )}
        </div>

        <span className="text-text-muted text-sm font-medium">
          {isDone ? "Final" : isLive ? (data.espn?.period || "Live") : "vs"}
        </span>

        {/* Home team */}
        <div className="flex flex-col items-center gap-2">
          {homeLogo ? (
            <img src={homeLogo} alt="" className="w-16 h-16 object-contain drop-shadow-md" />
          ) : (
            <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: homeColor }}>
              {(data.home_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}
            </div>
          )}
          {isDone && data.home_score != null && (
            <span className="text-2xl font-black tabular-nums">{data.home_score}</span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <Link href={`/events/${data.id}`} className="block">
          <h3 className="font-bold text-lg leading-tight mb-1">
            {data.away_team} {isDone ? "" : "@"} {data.home_team}
          </h3>
        </Link>

        {/* Probability */}
        {homeProb != null && awayProb != null && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-sm mb-1.5">
              <span className="font-bold" style={{ color: awayColor }}>{formatProbability(awayProb)}</span>
              <span className="text-text-muted text-xs">Win Probability</span>
              <span className="font-bold" style={{ color: homeColor }}>{formatProbability(homeProb)}</span>
            </div>
            <div className="h-3 rounded-full overflow-hidden flex">
              <div className="transition-all duration-500" style={{ width: `${awayProb * 100}%`, backgroundColor: awayColor }} />
              <div className="transition-all duration-500" style={{ width: `${homeProb * 100}%`, backgroundColor: homeColor }} />
            </div>
          </div>
        )}

        {/* Headline / hook */}
        <p className="text-sm text-text-secondary mt-3">{headline}</p>

        {/* Action bar */}
        <ActionBar liked={liked} setLiked={setLiked} shareUrl={`https://bainluck.com/events/${data.id}`} shareTitle={`${data.away_team} vs ${data.home_team}`} />
      </div>
    </div>
  );
}

// ── Futures Card ──

function FuturesCard({
  item, data, liked, setLiked, onDismiss,
}: {
  item: FeedItem; data: FeedFuturesData;
  liked: boolean; setLiked: (v: boolean) => void;
  onDismiss?: () => void;
}) {
  const catStyle = getCategoryStyle(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const leader = data.top_outcomes?.[0];
  const runnerUp = data.top_outcomes?.[1];
  const movement = leader?.movement;
  const prob = leader?.probability ?? 0;

  const headline = item.headline || (
    movement && Math.abs(movement) >= 0.02
      ? `${movement > 0 ? "↑" : "↓"} ${Math.abs(Math.round(movement * 100))}% this week`
      : data.source_count > 1 ? `${data.source_count} sources` : ""
  );

  const resolveLabel = data.resolution_date
    ? `resolves ${new Date(data.resolution_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}`
    : "";

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg">
      {onDismiss && (
        <button onClick={onDismiss} className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
        </button>
      )}

      {/* Hero — gradient with giant probability */}
      <div
        className="relative h-44 flex flex-col items-center justify-center"
        style={{
          background: CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
        }}
      >
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>
          {catStyle.emoji} {category}
        </div>

        {leader && (
          <>
            <div className="text-5xl font-black text-white tabular-nums tracking-tight">
              {Math.round(prob * 100)}<span className="text-3xl">%</span>
            </div>
            <div className="text-white/60 text-sm mt-1 font-medium max-w-[80%] text-center truncate">{leader.name}</div>
            {movement != null && Math.abs(movement) >= 0.01 && (
              <div className={`mt-2 text-xs font-bold px-2 py-0.5 rounded-full ${movement > 0 ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"}`}>
                {movement > 0 ? "↑" : "↓"} {Math.abs(Math.round(movement * 100))}% 24h
              </div>
            )}
          </>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        <Link href={`/futures/${data.id}`} className="block">
          <h3 className="font-bold text-lg leading-tight mb-1">{data.name}</h3>
        </Link>

        {/* Runner-up */}
        {runnerUp && (
          <div className="mt-2 flex items-center gap-2">
            <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
              <div className="h-full rounded-full bg-text-muted/40 transition-all" style={{ width: `${(runnerUp.probability ?? 0) * 100}%` }} />
            </div>
            <span className="text-xs text-text-secondary shrink-0">
              {runnerUp.name} {Math.round((runnerUp.probability ?? 0) * 100)}%
            </span>
          </div>
        )}

        {headline && <p className="text-sm text-text-secondary mt-3">{headline}</p>}

        {/* Source + resolution */}
        <div className="flex items-center gap-2 mt-2 text-[10px] text-text-muted">
          {data.source && (
            <span className="font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-surface-elevated">{data.source}</span>
          )}
          {resolveLabel && <span>{resolveLabel}</span>}
        </div>

        <ActionBar liked={liked} setLiked={setLiked} shareUrl={`https://bainluck.com/futures/${data.id}`} shareTitle={data.name} />
      </div>
    </div>
  );
}

// ── Tournament Card ──

function TournamentCard({
  item, data, liked, setLiked, onDismiss,
}: {
  item: FeedItem; data: FeedTournamentData;
  liked: boolean; setLiked: (v: boolean) => void;
  onDismiss?: () => void;
}) {
  const catStyle = getCategoryStyle("golf");
  const leader = data.golfers?.[0];

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg">
      {onDismiss && (
        <button onClick={onDismiss} className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
        </button>
      )}

      <div className="relative h-44 flex flex-col items-center justify-center" style={{ background: "linear-gradient(135deg, #14532d, #166534)" }}>
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full`}>
          ⛳ Golf
        </div>
        {leader && (
          <>
            <div className="text-5xl font-black text-white tabular-nums">{Math.round(leader.probability * 100)}%</div>
            <div className="text-white/60 text-sm mt-1">{leader.name}</div>
          </>
        )}
      </div>

      <div className="p-4">
        <h3 className="font-bold text-lg leading-tight mb-1">{data.name}</h3>
        {data.venue && <p className="text-sm text-text-secondary">{data.venue}</p>}
        <ActionBar liked={liked} setLiked={setLiked} shareUrl={`https://bainluck.com/sport/golf`} shareTitle={data.name} />
      </div>
    </div>
  );
}

// ── Action Bar ──

function ActionBar({
  liked, setLiked, shareUrl, shareTitle,
}: {
  liked: boolean; setLiked: (v: boolean) => void;
  shareUrl: string; shareTitle: string;
}) {
  const handleShare = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: shareTitle, url: shareUrl }); } catch {}
    } else {
      await navigator.clipboard.writeText(shareUrl);
    }
  };

  return (
    <div className="flex items-center gap-1 mt-4 pt-3 border-t border-surface-border">
      <button
        onClick={() => setLiked(!liked)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm ${liked ? "bg-red-500/10 text-red-500" : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"}`}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
        </svg>
        {liked ? "Liked" : "Like"}
      </button>

      <div className="flex-1" />

      <button
        onClick={handleShare}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-elevated transition-colors text-sm"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
        Share
      </button>
    </div>
  );
}
