"use client";

import Link from "next/link";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { DismissBtn, TrendBadge, ExpandableContextText, ActionBar, SignalBars, ForYouChip } from "./shared";
import { forYouCue } from "@/lib/discover/forYouCue";
import type { ActionBarProps, CardActionCallbacks } from "./types";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";

interface ComparisonCardProps extends CardActionCallbacks {
  item: FeedItem;
  data: FeedFuturesData;
  /**
   * UX-P234 (board item 16), added by the CERT-606 repair.
   *
   * 🔴 THIS CARD WAS THE MISSED RENDERING. `DiscoverCard` routes a FUTURES item
   * here — not to `FuturesCard` — when its `suggested_format` is
   * `outcome_distribution` and it has >=4 outcomes. The first version of this ship
   * threaded the pin through all four of `FuturesCard`'s ActionBars and its guard
   * counted them, so it looked exhaustive; it was exhaustive within ONE component
   * and blind to the fact that a futures item has TWO possible components.
   *
   * The same market therefore showed a pin or not depending on how the feed chose
   * to format it. Optional, like the ActionBar prop it feeds.
   */
  pin?: ActionBarProps["pin"];
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  trending: boolean;
}

export function ComparisonCard({
  item, data, liked, setLiked, onDismiss, trending, pin,
  onDetailClick, onShare, onContextExpand, onContextCollapse,
}: ComparisonCardProps) {
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const contextSnippet = feedContextSnippet(item);
  const expandedContext = feedExpandedContext(item);
  const resolveText = resolvesLabel(data.resolution_date);
  const shareUrl = buildDiscoverShareUrl(`/futures/${data.id}`, "futures", data.id);
  const shareText = `Compare: ${data.name} on Bain Luck.`;

  // UX-P248 / CERT-678 repair. This is the SECOND time this card has been the
  // missed rendering (see the `pin` prop's comment above, CERT-606). A futures
  // item has two possible components and `DiscoverCard` picks THIS one whenever
  // the format is `outcome_distribution` with >=4 outcomes — a shape that is
  // common, not exotic. Exhaustive-within-one-component is the recurring error;
  // `forYouCueRenderPaths.test.tsx` now enumerates the components instead.
  const cue = forYouCue(item);
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

        {/* Why this card is in front of THIS reader — same placement as every
            other card: under the question, in the flow, never a floating badge. */}
        <ForYouChip cue={cue} />

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
            // UX-P046: a nonzero probability must never print as "0%".
            const pct = formatProbabilityPercent(prob);
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
                  {prob > 0 ? pct : "—"}
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
          {/* Queue 309 Item 4 — the trailing " · $N.NM vol" clause is gone
              (docs/design-system.md: dollar volume as social proof is banned).
              The market count stays; SignalBars stays. */}
          <span className="ml-auto flex items-center gap-2 text-[11px] text-text-muted">
            <span>{data.outcome_count} markets</span>
            {data.confidence_tier && <span>·</span>}
            <SignalBars tier={data.confidence_tier} />
          </span>
        </div>

        <ActionBar
          pin={pin}
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
