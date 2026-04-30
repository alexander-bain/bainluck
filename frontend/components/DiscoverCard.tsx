"use client";

import { useState } from "react";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";

// ── Category Styling ──

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
  geopolitics: "linear-gradient(135deg, #1e1b4b, #3730a3)",
  olympics: "linear-gradient(135deg, #78350f, #d97706)",
  cricket: "linear-gradient(135deg, #134e4a, #14b8a6)",
  weather: "linear-gradient(135deg, #0c4a6e, #0284c7)",
  entertainment: "linear-gradient(135deg, #701a75, #c026d3)",
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
  geopolitics: { bg: "bg-indigo-500/15", text: "text-indigo-600", emoji: "🌍" },
  olympics: { bg: "bg-amber-500/15", text: "text-amber-600", emoji: "🏅" },
  cricket: { bg: "bg-teal-500/15", text: "text-teal-600", emoji: "🏏" },
  weather: { bg: "bg-sky-500/15", text: "text-sky-600", emoji: "🌤" },
  entertainment: { bg: "bg-fuchsia-500/15", text: "text-fuchsia-600", emoji: "🎬" },
};

function getCategoryStyle(cat: string | null | undefined) {
  if (!cat) return { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
  return CATEGORY_COLORS[cat.toLowerCase()] ?? { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
}

// ── Time Helpers ──

function relativeTimeLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffH = diffMs / (1000 * 60 * 60);

  if (diffMs < 0) {
    const ago = Math.abs(diffH);
    if (ago < 1) return "Just ended";
    if (ago < 24) return `${Math.round(ago)}h ago`;
    return `${Math.round(ago / 24)}d ago`;
  }
  if (diffH < 1) return `${Math.round(diffMs / 60000)}m`;
  if (diffH < 24) return `${Math.round(diffH)}h`;
  if (diffH < 48) return "Tomorrow";
  if (diffH < 168) return `${Math.round(diffH / 24)}d`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function resolvesLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffH = (date.getTime() - now.getTime()) / (1000 * 60 * 60);
  if (diffH < 0) return "Resolved";
  if (diffH < 3) return `Resolves in ${Math.round(diffH * 60)}m`;
  if (diffH < 24) return `Resolves in ${Math.round(diffH)}h`;
  if (diffH < 48) return "Resolves tomorrow";
  if (diffH < 168) return `Resolves in ${Math.round(diffH / 24)} days`;
  return `Resolves ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

// ── Trending Detection ──

function isTrending(item: FeedItem): boolean {
  if (item.type === "futures") {
    const fd = item.data as FeedFuturesData;
    const leader = fd.top_outcomes?.[0];
    if (leader?.movement && Math.abs(leader.movement) >= 0.05) return true;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    if (ed.status === "live") return true;
    if (ed.ei && ed.ei.score >= 70) return true;
  }
  return false;
}

// ── Movement Sparkline ──

function MovementIndicator({ movement }: { movement: number | null | undefined }) {
  if (!movement || Math.abs(movement) < 0.01) return null;
  const up = movement > 0;
  const pct = Math.abs(Math.round(movement * 100));
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
      up ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600"
    }`}>
      <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">
        {up ? <path d="M4 1L7 5H1z" /> : <path d="M4 7L1 3h6z" />}
      </svg>
      {pct}%
    </span>
  );
}

// ── Main Component ──

interface DiscoverCardProps {
  item: FeedItem;
  onDismiss?: () => void;
}

export default function DiscoverCard({ item, onDismiss }: DiscoverCardProps) {
  const [liked, setLiked] = useState(false);
  const trending = isTrending(item);

  if (item.type === "event") {
    return <EventCard item={item} data={item.data as FeedEventData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} trending={trending} />;
  }
  if (item.type === "futures") {
    return <FuturesCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} trending={trending} />;
  }
  if (item.type === "tournament") {
    return <TournamentCard item={item} data={item.data as FeedTournamentData} liked={liked} setLiked={setLiked} onDismiss={onDismiss} />;
  }
  return null;
}

// ── Dismiss Button ──

function DismissButton({ onDismiss }: { onDismiss?: () => void }) {
  if (!onDismiss) return null;
  return (
    <button onClick={onDismiss} className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
    </button>
  );
}

// ── Trending Badge ──

function TrendingBadge() {
  return (
    <div className="absolute top-3 right-12 z-10 flex items-center gap-1 bg-orange-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full">
      🔥 Trending
    </div>
  );
}

// ── Event Card ──

function EventCard({
  item, data, liked, setLiked, onDismiss, trending,
}: {
  item: FeedItem; data: FeedEventData;
  liked: boolean; setLiked: (v: boolean) => void;
  onDismiss?: () => void; trending: boolean;
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
  const sportCat = data.sport?.split("_")[0] || "sports";

  const headline = item.headline || (isLive ? "Live now" : isDone ? "Final" : data.highlight?.label || "");
  const timeLabel = isLive
    ? data.espn?.period || "Live"
    : isDone ? "Final" : relativeTimeLabel(data.commence_time);

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissButton onDismiss={onDismiss} />
      {trending && <TrendingBadge />}

      {/* Hero — sport-themed gradient with team logos */}
      <div
        className="relative h-44 flex items-center justify-center gap-6"
        style={{
          background: CATEGORY_GRADIENTS[sportCat] || `linear-gradient(135deg, ${awayColor}33, ${homeColor}33)`,
        }}
      >
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>
          {catStyle.emoji} {category}
        </div>

        {isLive && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            LIVE
          </div>
        )}

        <div className="flex flex-col items-center gap-2">
          {awayLogo ? (
            <img src={awayLogo} alt="" className="w-16 h-16 object-contain drop-shadow-lg" />
          ) : (
            <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: awayColor }}>
              {(data.away_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}
            </div>
          )}
          {(isLive || isDone) && data.away_score != null && (
            <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.away_score}</span>
          )}
        </div>

        <div className="flex flex-col items-center">
          <span className="text-white/70 text-sm font-semibold">{timeLabel}</span>
        </div>

        <div className="flex flex-col items-center gap-2">
          {homeLogo ? (
            <img src={homeLogo} alt="" className="w-16 h-16 object-contain drop-shadow-lg" />
          ) : (
            <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: homeColor }}>
              {(data.home_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}
            </div>
          )}
          {(isLive || isDone) && data.home_score != null && (
            <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.home_score}</span>
          )}
        </div>
      </div>

      <div className="p-4">
        <Link href={`/events/${data.id}`} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">
            {data.away_team} {isDone ? "" : "@"} {data.home_team}
          </h3>
        </Link>

        {homeProb != null && awayProb != null && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="font-bold" style={{ color: awayColor }}>{formatProbability(awayProb)}</span>
              <span className="text-text-muted text-[10px]">Win Probability</span>
              <span className="font-bold" style={{ color: homeColor }}>{formatProbability(homeProb)}</span>
            </div>
            <div className="h-2.5 rounded-full overflow-hidden flex">
              <div className="transition-all duration-500" style={{ width: `${awayProb * 100}%`, backgroundColor: awayColor }} />
              <div className="transition-all duration-500" style={{ width: `${homeProb * 100}%`, backgroundColor: homeColor }} />
            </div>
          </div>
        )}

        {headline && <p className="text-sm text-text-secondary mt-2">{headline}</p>}

        <ActionBar liked={liked} setLiked={setLiked} shareUrl={`https://bainluck.com/events/${data.id}`} shareTitle={`${data.away_team} vs ${data.home_team}`} />
      </div>
    </div>
  );
}

// ── Futures Card ──

function FuturesCard({
  item, data, liked, setLiked, onDismiss, trending,
}: {
  item: FeedItem; data: FeedFuturesData;
  liked: boolean; setLiked: (v: boolean) => void;
  onDismiss?: () => void; trending: boolean;
}) {
  const catStyle = getCategoryStyle(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const leader = data.top_outcomes?.[0];
  const movement = leader?.movement;
  const prob = leader?.probability ?? 0;

  const headline = data.hook_description || item.headline || "";
  const resolveText = resolvesLabel(data.resolution_date);

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissButton onDismiss={onDismiss} />
      {trending && <TrendingBadge />}

      <div
        className="relative h-44 flex flex-col items-center justify-center bg-cover bg-center"
        style={{
          background: data.image_url
            ? `linear-gradient(to bottom, rgba(0,0,0,0.25), rgba(0,0,0,0.75)), url(${data.image_url}) center/cover`
            : CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
        }}
      >
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>
          {catStyle.emoji} {category}
        </div>

        {leader && (
          <>
            <div className="text-5xl font-black text-white tabular-nums tracking-tight drop-shadow-lg">
              {Math.round(prob * 100)}<span className="text-3xl">%</span>
            </div>
            <div className="text-white/70 text-sm mt-1 font-medium max-w-[80%] text-center truncate">{leader.name}</div>
            <div className="mt-2 flex items-center gap-2">
              <MovementIndicator movement={movement} />
              {resolveText && (
                <span className="text-white/50 text-[10px] font-medium">{resolveText}</span>
              )}
            </div>
          </>
        )}
      </div>

      <div className="p-4">
        <Link href={`/futures/${data.id}`} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.name}</h3>
        </Link>

        {headline && <p className="text-sm text-text-secondary mt-1 leading-relaxed">{headline}</p>}

        {data.top_outcomes.length > 1 && (
          <div className="mt-3 space-y-1.5">
            {data.top_outcomes.slice(0, 3).map((o, i) => (
              <div key={o.id} className="flex items-center gap-2">
                <span className={`text-xs w-28 truncate shrink-0 ${i === 0 ? "font-semibold" : "text-text-secondary"}`}>{o.name}</span>
                <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-500 ${i === 0 ? "bg-accent-brand" : "bg-text-muted/30"}`} style={{ width: `${(o.probability ?? 0) * 100}%` }} />
                </div>
                <span className="font-mono tabular-nums text-xs font-semibold w-9 text-right">{Math.round((o.probability ?? 0) * 100)}%</span>
                {i === 0 && <MovementIndicator movement={o.movement} />}
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mt-2 text-[10px] text-text-muted">
          {data.source && (
            <span className="font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-surface-elevated">{data.source}</span>
          )}
          {data.outcome_count > 3 && <span>{data.outcome_count} outcomes</span>}
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
  const leader = data.golfers?.[0];
  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissButton onDismiss={onDismiss} />
      <div className="relative h-44 flex flex-col items-center justify-center" style={{ background: "linear-gradient(135deg, #14532d, #166534)" }}>
        <div className="absolute top-3 left-3 bg-lime-600/15 text-lime-700 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">⛳ Golf</div>
        {leader && (
          <>
            <div className="text-5xl font-black text-white tabular-nums drop-shadow-lg">{Math.round(leader.probability * 100)}%</div>
            <div className="text-white/70 text-sm mt-1">{leader.name}</div>
            <MovementIndicator movement={leader.movement_24h} />
          </>
        )}
      </div>
      <div className="p-4">
        <h3 className="font-bold text-lg leading-tight mb-1">{data.name}</h3>
        {data.venue && <p className="text-sm text-text-secondary">{data.venue}</p>}
        <ActionBar liked={liked} setLiked={setLiked} shareUrl="https://bainluck.com/sport/golf" shareTitle={data.name} />
      </div>
    </div>
  );
}

// ── Action Bar ──

function ActionBar({ liked, setLiked, shareUrl, shareTitle }: {
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
    <div className="flex items-center gap-1 mt-3 pt-3 border-t border-surface-border">
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
