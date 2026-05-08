"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import Link from "next/link";
import { Check, Heart, Share2 } from "lucide-react";
import { formatProbability } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import { getDiscoverItemAnalytics, recordDiscoverInteraction } from "@/lib/discoverInteractions";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";
import type { ShareContentType } from "@/lib/share";

// ── Session ID for prediction tracking ──

function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("bainluck_session_id");
  if (!id) {
    id = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("bainluck_session_id", id);
  }
  return id;
}

// ── Animated Counter ──

function AnimatedProbability({ value, className }: { value: number; className?: string }) {
  const [displayed, setDisplayed] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const animated = useRef(false);

  useEffect(() => {
    if (animated.current) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !animated.current) {
        animated.current = true;
        const duration = 800;
        const start = performance.now();
        const animate = (now: number) => {
          const elapsed = now - start;
          const progress = Math.min(elapsed / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          setDisplayed(Math.round(value * eased));
          if (progress < 1) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
      }
    }, { threshold: 0.5 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [value]);

  return <span ref={ref} className={className}>{displayed}<span className="text-3xl">%</span></span>;
}

// ── Types ──

export interface DiscoverGroupedItem {
  type: "single" | "group";
  item?: FeedItem;
  items?: FeedItem[];
  groupTitle?: string;
}

interface DiscoverCardProps {
  groupedItem: DiscoverGroupedItem;
  onDismiss?: () => void;
  positionIndex?: number;
}

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

function getCat(cat: string | null | undefined) {
  if (!cat) return { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
  return CATEGORY_COLORS[cat.toLowerCase()] ?? { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };
}

// ── Helpers ──

function resolvesLabel(d: string | null | undefined): string {
  if (!d) return "";
  const date = new Date(d);
  const diffH = (date.getTime() - Date.now()) / 36e5;
  if (diffH < 0) return "Resolved";
  if (diffH < 3) return `Resolves in ${Math.round(diffH * 60)}m`;
  if (diffH < 24) return `Resolves in ${Math.round(diffH)}h`;
  if (diffH < 48) return "Resolves tomorrow";
  if (diffH < 168) return `Resolves in ${Math.round(diffH / 24)} days`;
  return `Resolves ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

function isTrending(item: FeedItem): boolean {
  if (item.type === "futures") {
    const m = (item.data as FeedFuturesData).top_outcomes?.[0]?.movement;
    return !!m && Math.abs(m) >= 0.05;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    return ed.status === "live" || (ed.ei?.score ?? 0) >= 70;
  }
  return false;
}

function MovementBadge({ m }: { m: number | null | undefined }) {
  if (!m || Math.abs(m) < 0.02) return null;
  const up = m > 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full ${up ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600"}`}>
      <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor">{up ? <path d="M4 1L7 5H1z" /> : <path d="M4 7L1 3h6z" />}</svg>
      {Math.abs(Math.round(m * 100))}%
    </span>
  );
}

// ── Swipe Hook ──

function useSwipe(onSwipeLeft?: () => void, onSwipeRight?: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  const startX = useRef(0);
  const currentX = useRef(0);
  const swiping = useRef(false);
  const [offset, setOffset] = useState(0);
  const [swipeAction, setSwipeAction] = useState<"like" | "dismiss" | null>(null);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    startX.current = e.touches[0].clientX;
    swiping.current = true;
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!swiping.current) return;
    currentX.current = e.touches[0].clientX;
    const dx = currentX.current - startX.current;
    setOffset(dx * 0.5);
    setSwipeAction(dx > 60 ? "like" : dx < -60 ? "dismiss" : null);
  }, []);

  const onTouchEnd = useCallback(() => {
    swiping.current = false;
    const dx = currentX.current - startX.current;
    if (dx > 80 && onSwipeRight) onSwipeRight();
    else if (dx < -80 && onSwipeLeft) onSwipeLeft();
    setOffset(0);
    setSwipeAction(null);
  }, [onSwipeLeft, onSwipeRight]);

  return { ref, offset, swipeAction, handlers: { onTouchStart, onTouchMove, onTouchEnd } };
}

// ── Main Export ──

export default function DiscoverCard({ groupedItem, onDismiss, positionIndex }: DiscoverCardProps) {
  if (groupedItem.type === "group" && groupedItem.items) {
    return <GroupCard items={groupedItem.items} title={groupedItem.groupTitle || ""} positionIndex={positionIndex} />;
  }
  const item = groupedItem.item!;
  return <SingleCard item={item} onDismiss={onDismiss} positionIndex={positionIndex} />;
}

function SingleCard({ item, onDismiss, positionIndex }: { item: FeedItem; onDismiss?: () => void; positionIndex?: number }) {
  const [liked, setLiked] = useState(false);
  const trending = isTrending(item);
  const analytics = getDiscoverItemAnalytics(item);

  const trackAction = useCallback((action: "detail_click" | "like" | "unlike" | "share") => {
    trackEvent("feed_card_action", {
      action,
      ...analytics,
      position: positionIndex,
      surface: "discover",
    });
    recordDiscoverInteraction(analytics.category, action);
  }, [analytics, positionIndex]);

  const setLikedWithTracking = useCallback((next: boolean) => {
    setLiked(next);
    trackAction(next ? "like" : "unlike");
  }, [trackAction]);

  const handleLike = useCallback(() => setLikedWithTracking(true), [setLikedWithTracking]);
  const swipe = useSwipe(onDismiss, handleLike);

  const cardStyle = {
    transform: `translateX(${swipe.offset}px) rotate(${swipe.offset * 0.02}deg)`,
    transition: swipe.offset === 0 ? "transform 0.3s ease" : "none",
  };

  return (
    <div className="relative" {...swipe.handlers}>
      {/* Swipe hint overlays */}
      {swipe.swipeAction === "like" && (
        <div className="absolute inset-0 z-20 flex items-center justify-start pl-6 pointer-events-none">
          <span className="text-4xl">❤️</span>
        </div>
      )}
      {swipe.swipeAction === "dismiss" && (
        <div className="absolute inset-0 z-20 flex items-center justify-end pr-6 pointer-events-none">
          <span className="text-4xl">✕</span>
        </div>
      )}

      <div style={cardStyle}>
        {item.type === "event" && <EventCard item={item} data={item.data as FeedEventData} liked={liked} setLiked={setLikedWithTracking} onDismiss={onDismiss} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
        {item.type === "futures" && <FuturesCard item={item} data={item.data as FeedFuturesData} liked={liked} setLiked={setLikedWithTracking} onDismiss={onDismiss} trending={trending} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
        {item.type === "tournament" && <TournamentCard data={item.data as FeedTournamentData} liked={liked} setLiked={setLikedWithTracking} onDismiss={onDismiss} onDetailClick={() => trackAction("detail_click")} onShare={() => trackAction("share")} />}
      </div>
    </div>
  );
}

// ── Group Card ──

function GroupCard({ items, title, positionIndex }: { items: FeedItem[]; title: string; positionIndex?: number }) {
  const [expanded, setExpanded] = useState(false);
  const primary = items[0];
  const rest = items.slice(1);
  const cat = primary.type === "futures" ? (primary.data as FeedFuturesData).llm_sport_category : null;
  const catStyle = getCat(cat);
  const analytics = getDiscoverItemAnalytics(primary);

  const setExpandedWithTracking = (next: boolean) => {
    setExpanded(next);
    if (next) {
      trackEvent("feed_card_action", {
        action: "group_expand",
        ...analytics,
        position: positionIndex,
        surface: "discover",
      });
      recordDiscoverInteraction(analytics.category, "group_expand");
    }
  };

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card shadow-lg overflow-hidden">
      {/* Group header */}
      <button
        onClick={() => setExpandedWithTracking(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-surface-elevated/50 hover:bg-surface-elevated transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full`}>
            {catStyle.emoji} {title}
          </span>
          <span className="text-xs text-text-muted">{items.length} markets</span>
        </div>
        <svg className={`w-4 h-4 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Primary item always visible */}
      <div className="px-4 py-3 border-b border-surface-border">
        <FuturesCompactRow data={primary.data as FeedFuturesData} />
      </div>

      {/* Rest shown on expand */}
      {expanded && rest.map((item, i) => (
        <div key={i} className="px-4 py-3 border-b border-surface-border last:border-0">
          <FuturesCompactRow data={item.data as FeedFuturesData} />
        </div>
      ))}

      {!expanded && rest.length > 0 && (
        <button
          onClick={() => setExpandedWithTracking(true)}
          className="w-full text-center py-2 text-xs text-blue-600 hover:text-blue-700 font-medium"
        >
          Show {rest.length} more
        </button>
      )}
    </div>
  );
}

function FuturesCompactRow({ data }: { data: FeedFuturesData }) {
  const leader = data.top_outcomes?.[0];
  return (
    <Link href={`/futures/${data.id}`} className="flex items-center gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold line-clamp-2 group-hover:text-accent-brand transition-colors">{data.name}</div>
        {data.hook_description && <div className="text-xs text-text-muted mt-0.5 line-clamp-2">{data.hook_description}</div>}
      </div>
      {leader && (
        <div className="flex items-center gap-2 shrink-0">
          <MovementBadge m={leader.movement} />
          <span className="font-mono tabular-nums text-sm font-bold">{Math.round((leader.probability ?? 0) * 100)}%</span>
        </div>
      )}
    </Link>
  );
}

// ── Shared Components ──

function DismissBtn({ onDismiss }: { onDismiss?: () => void }) {
  if (!onDismiss) return null;
  return (
    <button onClick={onDismiss} className="absolute top-3 right-3 z-10 w-7 h-7 rounded-full bg-black/30 backdrop-blur-sm flex items-center justify-center text-white/80 hover:text-white hover:bg-black/50 transition-colors">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M2 2l8 8M10 2l-8 8" /></svg>
    </button>
  );
}

function TrendBadge() {
  return (
    <div className="absolute top-3 right-12 z-10 flex items-center gap-1 bg-orange-500/90 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full">
      🔥 Trending
    </div>
  );
}

function ActionBar({ liked, setLiked, shareUrl, shareTitle, shareText, contentType, itemId, onShare }: {
  liked: boolean;
  setLiked: (v: boolean) => void;
  shareUrl: string;
  shareTitle: string;
  shareText?: string;
  contentType: ShareContentType;
  itemId: number | string;
  onShare?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const trackShare = (method: string) => {
    trackEvent("share", {
      content_type: contentType,
      item_id: itemId,
      method,
      item_name: shareTitle,
      source_section: "discover",
      url: shareUrl,
    }, { immediate: true });
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: shareTitle, text: shareText, url: shareUrl });
        trackShare("native");
        onShare?.();
        return;
      } catch {
        return;
      }
    }

    if (navigator.clipboard?.writeText) {
      const text = shareText ? `${shareText}\n${shareUrl}` : shareUrl;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
      trackShare("clipboard");
      onShare?.();
    }
  };

  return (
    <div className="flex items-center gap-1 mt-3 pt-3 border-t border-surface-border">
      <button onClick={() => setLiked(!liked)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-colors text-sm ${liked ? "bg-red-500/10 text-red-500" : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated"}`}>
        <Heart size={16} fill={liked ? "currentColor" : "none"} strokeWidth={2} />
        {liked ? "Liked" : "Like"}
      </button>
      <div className="flex-1" />
      <button
        onClick={handleShare}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-surface-elevated transition-colors text-sm"
        title={copied ? "Copied" : "Share"}
        aria-label={copied ? "Copied share link" : "Share this card"}
      >
        {copied ? <Check size={14} strokeWidth={2.4} /> : <Share2 size={14} strokeWidth={2} />}
        {copied ? "Copied" : "Share"}
      </button>
    </div>
  );
}

// ── Event Card ──

function EventCard({ item, data, liked, setLiked, onDismiss, trending, onDetailClick, onShare }: {
  item: FeedItem; data: FeedEventData; liked: boolean; setLiked: (v: boolean) => void; onDismiss?: () => void; trending: boolean; onDetailClick?: () => void; onShare?: () => void;
}) {
  const [showContext, setShowContext] = useState(false);
  const homeColor = data.home_team_data?.primary_color || "#374151";
  const awayColor = data.away_team_data?.primary_color || "#6b7280";
  const isLive = data.status === "live";
  const isDone = data.status === "completed" || data.status === "closed";
  const homeProb = data.current_odds?.home_probability;
  const awayProb = data.current_odds?.away_probability;
  const catStyle = getCat(data.sport?.split("_")[0]);
  const sportCat = data.sport?.split("_")[0] || "sports";

  const headline = item.headline || (isLive ? "Live now" : isDone ? "Final" : data.highlight?.label || "");
  const timeLabel = isLive ? (data.espn?.period || "Live") : isDone ? "Final" : (() => {
    const d = new Date(data.commence_time);
    const diffH = (d.getTime() - Date.now()) / 36e5;
    if (diffH < 1) return `${Math.round(diffH * 60)}m`;
    if (diffH < 24) return `${Math.round(diffH)}h`;
    if (diffH < 48) return "Tomorrow";
    return d.toLocaleDateString("en-US", { weekday: "short" });
  })();

  // Build context blurb from tags
  const contextLines: string[] = [];
  if (data.event_tags) {
    const tags = data.event_tags;
    if (tags.some(t => t.includes("elimination"))) contextLines.push("Elimination game — loser goes home");
    if (tags.some(t => t.includes("clinch"))) contextLines.push("Winner clinches a playoff spot");
    if (tags.some(t => t.includes("rivalry"))) contextLines.push("Historic rivalry matchup");
    if (tags.some(t => t.includes("upset"))) contextLines.push("Upset alert — underdog has a real chance");
    if (tags.some(t => t.includes("playoff"))) contextLines.push("Playoff implications on the line");
  }
  if (data.ei && data.ei.score >= 60) contextLines.push(`Excitement Index: ${data.ei.score}/100 — ${data.ei.label}`);
  const shareUrl = buildDiscoverShareUrl(`/events/${data.id}`, "event", data.id);
  const homeProbability = formatShareProbability(homeProb);
  const awayProbability = formatShareProbability(awayProb);
  const shareText = homeProbability && awayProbability
    ? `${data.home_team} ${homeProbability}, ${data.away_team} ${awayProbability} on Bain Luck.`
    : `Track ${data.away_team} vs ${data.home_team} on Bain Luck.`;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className="relative h-44 flex items-center justify-center gap-6" style={{ background: CATEGORY_GRADIENTS[sportCat] || `linear-gradient(135deg, ${awayColor}33, ${homeColor}33)` }}>
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>{catStyle.emoji} {data.sport_name || "Sports"}</div>
        {isLive && <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-red-500/90 text-white text-[10px] font-bold uppercase px-2.5 py-1 rounded-full"><span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />LIVE</div>}

        <div className="flex flex-col items-center gap-2">
          {data.away_team_data?.logo_small ? <img src={data.away_team_data.logo_small} alt="" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: awayColor }}>{(data.away_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone) && data.away_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.away_score}</span>}
        </div>
        <span className="text-white/70 text-sm font-semibold">{timeLabel}</span>
        <div className="flex flex-col items-center gap-2">
          {data.home_team_data?.logo_small ? <img src={data.home_team_data.logo_small} alt="" className="w-16 h-16 object-contain drop-shadow-lg" /> : <div className="w-16 h-16 rounded-xl grid place-items-center text-white font-black text-lg" style={{ background: homeColor }}>{(data.home_team.split(" ").pop() || "").slice(0, 3).toUpperCase()}</div>}
          {(isLive || isDone) && data.home_score != null && <span className="text-2xl font-black tabular-nums text-white drop-shadow">{data.home_score}</span>}
        </div>
      </div>

      <div className="p-4">
        <Link href={`/events/${data.id}`} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.away_team} {isDone ? "" : "@"} {data.home_team}</h3>
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

        {/* Expandable context */}
        {contextLines.length > 0 && (
          <button onClick={() => setShowContext(!showContext)} className="text-xs text-blue-600 hover:text-blue-700 mt-1 font-medium">
            {showContext ? "Less context" : "Why this matters"}
          </button>
        )}
        {showContext && (
          <div className="mt-2 space-y-1 text-xs text-text-secondary bg-surface-elevated/50 rounded-lg p-2.5">
            {contextLines.map((line, i) => <p key={i}>• {line}</p>)}
          </div>
        )}

        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={shareUrl}
          shareTitle={`${data.away_team} vs ${data.home_team}`}
          shareText={shareText}
          contentType="event"
          itemId={data.id}
          onShare={onShare}
        />
      </div>
    </div>
  );
}

// ── Futures Card ──

function FuturesCard({ item, data, liked, setLiked, onDismiss, trending, onDetailClick, onShare }: {
  item: FeedItem; data: FeedFuturesData; liked: boolean; setLiked: (v: boolean) => void; onDismiss?: () => void; trending: boolean; onDetailClick?: () => void; onShare?: () => void;
}) {
  const [showContext, setShowContext] = useState(false);
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const leader = data.top_outcomes?.[0];
  const prob = leader?.probability ?? 0;
  const headline = data.hook_description || item.headline || "";
  const resolveText = resolvesLabel(data.resolution_date);
  const hasImage = !!data.image_url;
  const outcomesAreDate = data.top_outcomes?.some((o) => /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}/i.test(o.name));
  const shareUrl = buildDiscoverShareUrl(`/futures/${data.id}`, "futures", data.id);
  const leaderProbability = formatShareProbability(prob);
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;

  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className={`relative ${hasImage ? "h-44" : "h-32"} flex flex-col items-center justify-center bg-cover bg-center`} style={{
        background: hasImage
          ? `linear-gradient(to bottom, rgba(0,0,0,0.25), rgba(0,0,0,0.75)), url(${data.image_url}) center/cover`
          : CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
      }}>
        <div className={`absolute top-3 left-3 ${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full backdrop-blur-sm`}>{catStyle.emoji} {category}</div>
        {!hasImage && <span className="absolute inset-0 flex items-center justify-center text-[80px] opacity-[0.08] select-none pointer-events-none">{catStyle.emoji}</span>}
        {leader && (
          <>
            <AnimatedProbability value={Math.round(prob * 100)} className="text-5xl font-black text-white tabular-nums tracking-tight drop-shadow-lg" />
            <div className="text-white/70 text-sm mt-1 font-medium max-w-[85%] text-center line-clamp-2">{leader.name}</div>
            <div className="mt-2 flex items-center gap-2">
              <MovementBadge m={leader.movement} />
              {resolveText && !outcomesAreDate && <span className="text-white/50 text-[10px] font-medium">{resolveText}</span>}
            </div>
          </>
        )}
      </div>

      <div className="p-4">
        <Link href={`/futures/${data.id}`} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.name}</h3>
        </Link>

        {headline && <p className="text-sm text-text-secondary mt-1 leading-relaxed">{headline}</p>}

        {data.top_outcomes.length > 1 && (
          <>
            <div className="mt-3 space-y-1.5">
              {data.top_outcomes.slice(0, showContext ? undefined : 3).map((o, i) => (
                <div key={o.id} className="flex items-center gap-2">
                  <span className={`text-xs w-32 truncate shrink-0 ${i === 0 ? "font-semibold" : "text-text-secondary"}`} title={o.name}>{o.name}</span>
                  <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
                    <div className={`h-full rounded-full transition-all duration-500 ${i === 0 ? "bg-accent-brand" : "bg-text-muted/30"}`} style={{ width: `${(o.probability ?? 0) * 100}%` }} />
                  </div>
                  <span className="font-mono tabular-nums text-xs font-semibold w-9 text-right">{Math.round((o.probability ?? 0) * 100)}%</span>
                  {i === 0 && <MovementBadge m={o.movement} />}
                </div>
              ))}
            </div>
            {data.outcome_count > 3 && (
              <button onClick={() => setShowContext(!showContext)} className="text-xs text-blue-600 hover:text-blue-700 mt-2 font-medium">
                {showContext ? "Show less" : data.outcome_count > 10 ? "Show more" : `Show all ${data.outcome_count} outcomes`}
              </button>
            )}
          </>
        )}

        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={shareUrl}
          shareTitle={data.name}
          shareText={shareText}
          contentType="futures"
          itemId={data.id}
          onShare={onShare}
        />
      </div>
    </div>
  );
}

// ── Tournament Card ──

function TournamentCard({ data, liked, setLiked, onDismiss, onDetailClick, onShare }: {
  data: FeedTournamentData; liked: boolean; setLiked: (v: boolean) => void; onDismiss?: () => void; onDetailClick?: () => void; onShare?: () => void;
}) {
  const leader = data.golfers?.[0];
  const leaderProbability = formatShareProbability(leader?.probability);
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;
  return (
    <div className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow">
      <DismissBtn onDismiss={onDismiss} />
      <div className="relative h-44 flex flex-col items-center justify-center" style={{ background: "linear-gradient(135deg, #14532d, #166534)" }}>
        <div className="absolute top-3 left-3 bg-lime-600/15 text-lime-700 text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full">⛳ Golf</div>
        {leader && (
          <>
            <AnimatedProbability value={Math.round(leader.probability * 100)} className="text-5xl font-black text-white tabular-nums drop-shadow-lg" />
            <div className="text-white/70 text-sm mt-1">{leader.name}</div>
            <MovementBadge m={leader.movement_24h} />
          </>
        )}
      </div>
      <div className="p-4">
        <Link href="/sport/golf" onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.name}</h3>
        </Link>
        {data.venue && <p className="text-sm text-text-secondary">{data.venue}</p>}
        <ActionBar
          liked={liked}
          setLiked={setLiked}
          shareUrl={buildDiscoverShareUrl("/sport/golf", "grid", data.name)}
          shareTitle={data.name}
          shareText={shareText}
          contentType="grid"
          itemId={data.name}
          onShare={onShare}
        />
      </div>
    </div>
  );
}

// ── Higher/Lower Guess Card ──

function generateThreshold(actualProb: number): number {
  const minGap = 0.10;
  // Randomly go higher or lower, at least 10% away
  const goHigher = Math.random() > 0.5;
  const offset = minGap + Math.random() * 0.15; // 10-25% away
  let threshold = goHigher ? actualProb + offset : actualProb - offset;
  // Clamp to 5%-95% range
  threshold = Math.max(0.05, Math.min(0.95, threshold));
  // Ensure still at least 10% away after clamping
  if (Math.abs(threshold - actualProb) < minGap) {
    threshold = actualProb > 0.5 ? actualProb - offset : actualProb + offset;
    threshold = Math.max(0.05, Math.min(0.95, threshold));
  }
  return Math.round(threshold * 100);
}

export function GuessCard({ item, onGuessCompleted }: { item: FeedItem; onGuessCompleted?: () => void }) {
  const isEvent = item.type === "event";
  const futuresData = isEvent ? null : (item.data as FeedFuturesData);
  const eventData = isEvent ? (item.data as FeedEventData) : null;

  const leader = futuresData?.top_outcomes?.[0];
  const actualProb = isEvent
    ? (eventData!.current_odds?.home_probability ?? 0)
    : (leader?.probability ?? 0);
  const subjectName = isEvent
    ? `${eventData!.home_team} to win`
    : (leader?.name ?? "");
  const cardTitle = isEvent
    ? `${eventData!.away_team} vs ${eventData!.home_team}`
    : (futuresData!.name);
  const itemId = isEvent ? eventData!.id : futuresData!.id;
  const detailLink = isEvent ? `/events/${eventData!.id}` : `/futures/${futuresData!.id}`;
  const sportCat = isEvent ? (eventData!.sport ?? "") : (futuresData!.llm_sport_category ?? "");

  const [guess, setGuess] = useState<"higher" | "lower" | null>(null);
  const [threshold] = useState(() => generateThreshold(actualProb));
  const [streak, setStreak] = useState<number | null>(null);
  const actualPct = Math.round(actualProb * 100);
  const correct = guess === "higher" ? actualPct > threshold : actualPct < threshold;

  const catStyle = getCat(sportCat);
  const category = (isEvent ? eventData!.sport_name : futuresData!.sport_name) || sportCat || "Markets";
  const catGradient = CATEGORY_GRADIENTS[sportCat.toLowerCase()] || "linear-gradient(135deg, #0f172a, #1e293b)";

  const submitGuess = async (g: "higher" | "lower") => {
    setGuess(g);
    const isCorrect = g === "higher" ? actualPct > threshold : actualPct < threshold;
    onGuessCompleted?.();
    try {
      await fetch("/api/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-session-id": getSessionId() },
        body: JSON.stringify({ market_id: itemId, guess: g, threshold, actual_probability: actualProb, correct: isCorrect }),
      });
      const statsRes = await fetch("/api/predictions/stats", { headers: { "x-session-id": getSessionId() } });
      if (statsRes.ok) {
        const stats = await statsRes.json();
        setStreak(stats.current_streak);
      }
    } catch {}
  };

  const handleShare = async () => {
    const text = `${correct ? "I got it right!" : "So close!"} ${cardTitle} — actual odds: ${actualPct}%. Can you beat me?`;
    const shareUrl = buildDiscoverShareUrl("/discover", isEvent ? "event" : "futures", itemId);
    const trackGuessShare = (method: string) => {
      trackEvent("share", {
        content_type: isEvent ? "event" : "futures",
        item_id: itemId,
        method,
        item_name: cardTitle,
        source_section: "discover_guess",
        url: shareUrl,
      }, { immediate: true });
    };
    if (navigator.share) {
      try {
        await navigator.share({ title: text, text, url: shareUrl });
        trackGuessShare("native");
      } catch {}
    } else {
      await navigator.clipboard.writeText(`${text}\n${shareUrl}`);
      trackGuessShare("clipboard");
    }
  };

  if (!isEvent && !leader) return null;
  if (isEvent && eventData!.current_odds?.home_probability == null) return null;

  return (
    <div data-guess-card data-market-id={itemId} className="rounded-2xl overflow-hidden border-2 border-amber-400/50 bg-surface-card shadow-lg">
      <div className="px-4 py-2.5 flex items-center gap-2" style={{ background: catGradient }}>
        <span className="text-white text-sm">🎯</span>
        <span className="text-white/90 text-xs font-bold uppercase tracking-wider">What are the odds?</span>
        <span className={`${catStyle.bg} ${catStyle.text} text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ml-auto`}>
          {catStyle.emoji} {category}
        </span>
      </div>

      <div className="p-4">
        <h3 className="font-bold text-lg leading-tight mb-3">{cardTitle}</h3>

        {!guess ? (
          <>
            <p className="text-sm text-text-secondary mb-4">
              {subjectName} — are the odds <span className="font-bold">higher</span> or <span className="font-bold">lower</span> than <span className="text-lg font-black">{threshold}%</span>?
            </p>
            <div className="flex gap-3">
              <button onClick={() => submitGuess("higher")} className="flex-1 py-3 rounded-xl bg-green-500/10 text-green-700 font-bold text-sm hover:bg-green-500/20 transition-colors border border-green-500/20">
                ↑ Higher than {threshold}%
              </button>
              <button onClick={() => submitGuess("lower")} className="flex-1 py-3 rounded-xl bg-red-500/10 text-red-700 font-bold text-sm hover:bg-red-500/20 transition-colors border border-red-500/20">
                ↓ Lower than {threshold}%
              </button>
            </div>
          </>
        ) : (
          <div className="text-center">
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold mb-3 ${correct ? "bg-green-500/15 text-green-700" : "bg-red-500/15 text-red-700"}`}>
              {correct ? "✓ Correct!" : "✗ Not quite!"}
            </div>

            <div className="mb-3">
              <div className="text-4xl font-black tabular-nums">{actualPct}%</div>
              <div className="text-sm text-text-secondary mt-1">{subjectName}</div>
            </div>

            {streak != null && streak > 1 && (
              <div className="text-xs font-bold text-amber-600 mb-2">🔥 {streak} correct in a row!</div>
            )}

            <div className="text-xs text-text-muted mb-3">
              You guessed {guess} than {threshold}% — actual is {actualPct}%
            </div>

            <div className="flex items-center justify-center gap-3 mb-3">
              <Link href={detailLink} className="text-xs text-blue-600 hover:text-blue-700 font-medium">
                See details →
              </Link>
              <button onClick={handleShare} className="text-xs text-text-muted hover:text-text-secondary font-medium flex items-center gap-1">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                </svg>
                Share result
              </button>
            </div>
            <button
              onClick={() => {
                const allGuessCards = document.querySelectorAll("[data-guess-card]");
                const currentCard = document.querySelector(`[data-guess-card][data-market-id="${itemId}"]`);
                let nextCard: Element | null = null;
                let foundCurrent = false;
                for (const card of allGuessCards) {
                  if (card === currentCard) { foundCurrent = true; continue; }
                  if (foundCurrent) { nextCard = card; break; }
                }
                if (nextCard) nextCard.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className="w-full py-2.5 rounded-xl bg-amber-500/10 text-amber-700 font-bold text-sm hover:bg-amber-500/20 transition-colors border border-amber-500/20"
            >
              Next question →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Daily Challenge Card ──

const DAILY_GOAL = 5;

export function DailyChallengeCard({ guessesToday }: {
  guessesToday: number;
}) {
  const completed = guessesToday >= DAILY_GOAL;
  const progress = Math.min(guessesToday / DAILY_GOAL, 1);

  return (
    <div className={`rounded-2xl overflow-hidden border-2 ${completed ? "border-green-400/50" : "border-amber-400/30"} bg-surface-card shadow-md`}>
      <div className="px-4 py-3 flex items-center gap-3">
        <span className="text-2xl">{completed ? "🏆" : "🎯"}</span>
        <div className="flex-1">
          <div className="text-sm font-bold">
            {completed ? "Daily Challenge Complete!" : "Today’s Challenge"}
          </div>
          <div className="text-xs text-text-muted">
            {completed
              ? "Come back tomorrow for a new challenge"
              : `Make ${DAILY_GOAL} predictions today · ${guessesToday}/${DAILY_GOAL}`}
          </div>
        </div>
        {!completed && (
          <div className="w-12 h-12 relative">
            <svg className="w-12 h-12 -rotate-90" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#e5e7eb" strokeWidth="3" />
              <circle cx="18" cy="18" r="15" fill="none" stroke="#f59e0b" strokeWidth="3"
                strokeDasharray={`${progress * 94.25} 94.25`}
                strokeLinecap="round" className="transition-all duration-500" />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">{guessesToday}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Resolution Card ──

export function ResolutionCard({ marketName, guess, threshold, actual, correct }: {
  marketName: string; guess: string; threshold: number; actual: number; correct: boolean;
}) {
  return (
    <div className="rounded-2xl overflow-hidden border-2 border-purple-400/30 bg-surface-card shadow-md">
      <div className="px-4 py-2 bg-purple-500/10 flex items-center gap-2">
        <span className="text-sm">📋</span>
        <span className="text-xs font-bold uppercase tracking-wider text-purple-700">Market Resolved</span>
      </div>
      <div className="p-4 text-center">
        <h3 className="font-bold text-sm mb-2">{marketName}</h3>
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold mb-2 ${
          correct ? "bg-green-500/15 text-green-700" : "bg-red-500/15 text-red-700"
        }`}>
          {correct ? "✓ You got it right!" : "✗ Better luck next time"}
        </div>
        <div className="text-xs text-text-muted">
          You guessed {guess} than {threshold}% — final result: {actual}%
        </div>
      </div>
    </div>
  );
}
