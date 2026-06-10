"use client";

import Link from "next/link";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { DismissBtn, TrendBadge, ExpandableContextText, ActionBar } from "./shared";
import type { CardActionCallbacks } from "./types";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";

interface ComparisonCardProps extends CardActionCallbacks {
  item: FeedItem;
  data: FeedFuturesData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  trending: boolean;
}

export function ComparisonCard({
  item, data, liked, setLiked, onDismiss, trending,
  onDetailClick, onShare, onContextExpand, onContextCollapse,
}: ComparisonCardProps) {
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const contextSnippet = feedContextSnippet(item);
  const expandedContext = feedExpandedContext(item);
  const resolveText = resolvesLabel(data.resolution_date);
  const shareUrl = buildDiscoverShareUrl(`/futures/${data.id}`, "futures", data.id);
  const shareText = `Compare: ${data.name} on Bain Luck.`;

  const outcomes = data.top_outcomes || [];
  const maxProb = Math.max(...outcomes.map((o) => o.probability ?? 0), 0.01);

  return (
    <article
      className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow"
      aria-label={data.name}
      data-card-format="comparison"
    >
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-1.5 mb-1">
          <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">
            {catStyle.emoji} {category}
          </span>
          <span className="ml-auto text-[11px] text-text-muted">{resolveText}</span>
        </div>

        <Link href={`/futures/${data.id}`} onClick={onDetailClick} className="block group">
          <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-1.5">
            {data.name}
          </h3>
        </Link>

        {contextSnippet && (
          <ExpandableContextText
            text={contextSnippet}
            expandedText={expandedContext}
            className="text-[13px] leading-relaxed text-text-secondary mb-3.5"
            onExpand={onContextExpand}
            onCollapse={onContextCollapse}
          />
        )}

        {/* Leaderboard rows */}
        <div>
          {outcomes.slice(0, 4).map((o, i) => {
            const prob = o.probability ?? 0;
            const pct = Math.round(prob * 100);
            const barWidth = Math.max(5, Math.round((prob / maxProb) * 100));
            const isLeader = i === 0;

            return (
              <div
                key={o.id}
                className="flex items-center gap-2.5 py-2 border-t border-surface-border"
              >
                <span
                  className={`flex-1 text-[13px] leading-tight truncate ${
                    isLeader ? "font-semibold text-text-primary" : "font-medium text-text-secondary"
                  }`}
                  title={o.name}
                >
                  {o.name}
                </span>
                <div className="w-[120px] h-[7px] bg-surface-elevated rounded-full overflow-hidden shrink-0">
                  <div
                    className="h-full rounded-full bg-accent-brand transition-all duration-500"
                    style={{
                      width: `${barWidth}%`,
                      opacity: prob >= 0.4 ? 1 : 0.55,
                    }}
                  />
                </div>
                <span className="font-mono font-bold text-sm tabular-nums w-9 text-right shrink-0">
                  {prob > 0 ? `${pct}%` : "—"}
                </span>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center pt-2.5 border-t border-surface-border">
          {data.outcome_count > 4 && (
            <Link
              href={`/futures/${data.id}`}
              onClick={onDetailClick}
              className="text-[12px] font-semibold text-accent-brand hover:underline"
            >
              Show more
            </Link>
          )}
          <span className="ml-auto text-[11px] text-text-muted">
            {data.outcome_count} markets
            {data.volume_24h != null && data.volume_24h > 0
              ? ` · $${data.volume_24h >= 1_000_000
                  ? `${(data.volume_24h / 1_000_000).toFixed(1)}M`
                  : data.volume_24h >= 1_000
                  ? `${(data.volume_24h / 1_000).toFixed(0)}K`
                  : data.volume_24h} vol`
              : ""}
          </span>
        </div>

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
