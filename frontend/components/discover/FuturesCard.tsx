"use client";

import { useState } from "react";
import Link from "next/link";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { AnimatedProbability, DismissBtn, TrendBadge, TemporalBadge, ActionBar, MovementBadge, ExpandableContextText } from "./shared";
import type { CardActionCallbacks } from "./types";

interface FuturesCardProps extends CardActionCallbacks {
  item: FeedItem;
  data: FeedFuturesData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  trending: boolean;
}

export function FuturesCard({ item, data, liked, setLiked, onDismiss, trending, onDetailClick, onShare, onContextExpand, onContextCollapse }: FuturesCardProps) {
  const [showContext, setShowContext] = useState(false);
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const leader = data.top_outcomes?.[0];
  const prob = leader?.probability ?? null;
  const contextSnippet = feedContextSnippet(item);
  const expandedContext = feedExpandedContext(item);
  const resolveText = resolvesLabel(data.resolution_date);
  const hasImage = !!data.image_url;
  const outcomesAreDate = data.top_outcomes?.some((o) => /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}/i.test(o.name));
  const shareUrl = buildDiscoverShareUrl(`/futures/${data.id}`, "futures", data.id);
  const leaderProbability = prob != null ? formatShareProbability(prob) : null;
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;

  return (
    <article className="relative rounded-2xl overflow-hidden border border-surface-border bg-surface-card shadow-lg hover:shadow-xl transition-shadow" aria-label={`${data.name}`}>
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
            <AnimatedProbability value={Math.round((prob ?? 0) * 100)} className="text-5xl font-black text-white tabular-nums tracking-tight drop-shadow-lg" />
            <div className="text-white/70 text-sm mt-1 font-medium max-w-[85%] text-center line-clamp-2">{leader.name}</div>
            <div className="mt-2 flex items-center gap-2">
              <MovementBadge m={leader.movement} />
              <TemporalBadge badge={data.temporal_badge} />
              {resolveText && !outcomesAreDate && !data.temporal_badge && <span className="text-white/50 text-[10px] font-medium">{resolveText}</span>}
            </div>
          </>
        )}
      </div>

      <div className="p-4">
        <Link href={`/futures/${data.id}`} onClick={onDetailClick} className="block group">
          <h3 className="font-bold text-lg leading-tight mb-1 group-hover:text-accent-brand transition-colors">{data.name}</h3>
        </Link>

        {contextSnippet && (
          <ExpandableContextText
            text={contextSnippet}
            expandedText={expandedContext}
            className="text-sm text-text-secondary mt-1 leading-relaxed"
            onExpand={onContextExpand}
            onCollapse={onContextCollapse}
          />
        )}

        {data.top_outcomes.length > 1 && (
          <>
            <div className="mt-3 space-y-1.5">
              {data.top_outcomes.slice(0, showContext ? undefined : 3).map((o, i) => (
                <div key={o.id} className="flex items-center gap-2">
                  <span className={`text-xs w-32 truncate shrink-0 ${i === 0 ? "font-semibold" : "text-text-secondary"}`} title={o.name}>{o.name}</span>
                  <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden" role="progressbar" aria-valuenow={Math.round((o.probability ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={`${o.name} probability`}>
                    <div className={`h-full rounded-full transition-all duration-500 ${i === 0 ? "bg-accent-brand" : "bg-text-muted/30"}`} style={{ width: `${(o.probability ?? 0) * 100}%` }} />
                  </div>
                  <span className="font-mono tabular-nums text-xs font-semibold w-9 text-right">{o.probability != null && o.probability > 0 ? `${Math.round(o.probability * 100)}%` : "—"}</span>
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
    </article>
  );
}

// ── Compact row used by GroupCard ──

export function FuturesCompactRow({ item, data }: { item: FeedItem; data: FeedFuturesData }) {
  const leader = data.top_outcomes?.[0];
  const context = feedContextSnippet(item);
  return (
    <Link href={`/futures/${data.id}`} className="flex items-center gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold line-clamp-2 group-hover:text-accent-brand transition-colors">{data.name}</div>
        {context && <div className="text-xs text-text-muted mt-0.5 line-clamp-2">{context}</div>}
      </div>
      {leader && (
        <div className="flex items-center gap-2 shrink-0">
          <MovementBadge m={leader.movement} />
          <span className="font-mono tabular-nums text-sm font-bold">{leader.probability != null && leader.probability > 0 ? `${Math.round(leader.probability * 100)}%` : "—"}</span>
        </div>
      )}
    </Link>
  );
}
