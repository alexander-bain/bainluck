"use client";

import { useState } from "react";
import Link from "next/link";
import { BarChart3 } from "lucide-react";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import { marketEventKey, eventPath } from "@/lib/eventKey";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { AnimatedProbability, DismissBtn, TrendBadge, TemporalBadge, ActionBar, MovementBadge, ExpandableContextText, SignalBars } from "./shared";
import QuantityGroup from "../QuantityGroup";
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
  const [showHeatmapContext, setShowHeatmapContext] = useState(false);
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  const leader = data.top_outcomes?.[0];
  const prob = leader?.probability ?? null;
  const contextSnippet = feedContextSnippet(item);
  const expandedContext = feedExpandedContext(item);
  const resolveText = resolvesLabel(data.resolution_date);
  const hasImage = !!data.image_url;
  const outcomesAreDate = data.top_outcomes?.some((o) => /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}/i.test(o.name));
  // L2-65: a winner-field market that IS an event concept (e.g. a tennis
  // tournament winner) links into the richer /event/[key] surface; everything
  // else stays on the futures market page.
  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;
  const shareUrl = buildDiscoverShareUrl(detailHref, "futures", data.id);
  const leaderProbability = prob != null ? formatShareProbability(prob) : null;
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;
  const heatmapRows = buildHeatmapRows(data);
  const volumeStr = data.volume_24h != null && data.volume_24h > 0
    ? data.volume_24h >= 1_000_000 ? `$${(data.volume_24h / 1_000_000).toFixed(1)}M vol`
    : data.volume_24h >= 1_000 ? `$${(data.volume_24h / 1_000).toFixed(0)}K vol`
    : `$${data.volume_24h} vol`
    : null;

  if (data.discover_card?.suggested_format === "threshold_heatmap" && heatmapRows.length >= 2) {
    const shownCells = heatmapRows.slice(0, 8);
    const above50 = shownCells.filter((r) => (r.probability ?? 0) >= 0.5);
    const lastAbove50Label = above50.length > 0 ? above50[above50.length - 1].label : null;

    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-format="heatmap">
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{catStyle.emoji} {category}</span>
            <span className="ml-auto text-[11px] text-text-muted">{resolveText}</span>
          </div>
          <Link href={detailHref} onClick={onDetailClick} className="block group">
            <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-4">{data.name}</h3>
          </Link>

          {/* #1102/L2-119: the "by WHEN" Quantity kernel. The old horizontal
              cell grid used equal flex-1 columns, so long date labels ("2029 or
              later") wrapped and broke alignment against the fixed-height cells.
              The vertical ladder (QuantityGroup, wide-label variant) never wraps
              its columns — one component covers "how MANY" and "by WHEN".
              L2-120: maxRungs is pinned to the sliced set so the `compact`
              default (4) doesn't silently crop the timeline. Date buckets tell
              their story in the TAIL (the modal/latest bucket is usually the
              highest-probability rung); with every bucket often below 50% there
              is no footer summary to carry a cropped rung, so a 5-bucket card
              must show all 5 — not just the first 4. */}
          <QuantityGroup
            bare
            compact
            wideLabels
            sort={false}
            maxRungs={shownCells.length}
            rungs={shownCells.map((row) => ({
              key: row.key,
              label: row.label,
              probability: row.probability,
              value: row.sortValue,
            }))}
          />

          {/* Summary footer — orphan-free: "All below 50%" is dropped (it read as
              a context-less phrase); when nothing clears 50% we show only volume.
              L2-183: the confidence glyph joins the right cluster so this
              multi-candidate kernel matches its ComparisonCard sibling. */}
          {(lastAbove50Label || volumeStr || data.confidence_tier) && (
            <div className="flex items-center gap-1.5 mt-3.5 pt-3 border-t border-surface-border">
              {lastAbove50Label && (
                <>
                  <span className="text-[12px] text-text-secondary">Above 50% through</span>
                  <span className="font-mono font-bold text-[13px] text-accent-brand">{lastAbove50Label}</span>
                </>
              )}
              <span className="ml-auto flex items-center gap-1.5 text-[11px] text-text-muted">
                {volumeStr && <span>{volumeStr}</span>}
                {volumeStr && data.confidence_tier && <span>·</span>}
                <SignalBars tier={data.confidence_tier} />
              </span>
            </div>
          )}

          <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} />
        </div>
      </article>
    );
  }

  const distributionRows = data.discover_card?.distribution_outcomes ?? [];
  if (data.discover_card?.suggested_format === "outcome_distribution" && distributionRows.length >= 4) {
    const maxProb = Math.max(...distributionRows.map((row) => row.probability ?? 0), 0.01);
    const shownRows = distributionRows.slice(0, 4);
    const remainingCount = data.discover_card.remaining_outcome_count + Math.max(0, distributionRows.length - shownRows.length);

    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={`${data.name}`}>
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-3 pb-2">
          {/* L2-160 — muted category header (no internal-taxonomy "Distribution"
              pill; ruling: no internal taxonomy pills). Matches the handoff's
              leaderboard header + the sibling ComparisonCard treatment. */}
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{catStyle.emoji} {category}</span>
            <TemporalBadge badge={data.temporal_badge} />
            <span className="ml-auto flex items-center gap-1.5 text-[11px] text-text-muted">
              {resolveText && <span>{resolveText}</span>}
              {data.confidence_tier && resolveText && <span>·</span>}
              <SignalBars tier={data.confidence_tier} />
            </span>
          </div>
          <h3 className="text-base font-bold leading-tight text-text-primary line-clamp-2">{data.name}</h3>

          {contextSnippet && (
            <ExpandableContextText
              text={contextSnippet}
              expandedText={expandedContext}
              className="mt-2 text-xs leading-relaxed text-text-secondary"
              onExpand={onContextExpand}
              onCollapse={onContextCollapse}
            />
          )}
        </div>

        <div className="px-3 pb-3">
          <div className="space-y-1.5 border-y border-surface-border py-2">
              {shownRows.map((row, index) => {
                const probability = row.probability ?? 0;
                const pct = Math.round(probability * 100);
                const width = Math.max(5, Math.round((probability / maxProb) * 100));
                const displayName = compactOutcomeName(row.label);
                return (
                  <div
                    key={`${row.label}-${index}`}
                    className="grid min-h-8 grid-cols-[1.25rem_minmax(0,1fr)_2.75rem] items-center gap-2 rounded-md px-1.5 py-1"
                  >
                    <span className="font-mono text-xs font-semibold tabular-nums text-text-muted" title={`Rank ${index + 1} by probability`} aria-label={`Rank ${index + 1}`}>{index + 1}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`min-w-0 text-xs leading-tight text-text-primary ${index === 0 ? "font-bold" : "font-semibold"}`} title={row.label}>{displayName}</span>
                        <MovementBadge m={row.movement} prob={row.probability} />
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-border">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${index === 0 ? "bg-accent-brand" : "bg-text-muted/35"}`}
                          style={{ width: `${width}%` }}
                        />
                      </div>
                    </div>
                    <span className="text-right font-mono text-xs font-bold tabular-nums text-text-primary">{probability > 0 ? `${pct}%` : "—"}</span>
                  </div>
                );
              })}
              {remainingCount > 0 && (
                <div
                  className="grid min-h-7 grid-cols-[1.25rem_minmax(0,1fr)_2.75rem] items-center gap-2 rounded-md px-1.5 py-1 text-text-muted"
                >
                  <span className="font-mono text-xs font-semibold tabular-nums">{shownRows.length + 1}</span>
                  <span className="truncate text-xs font-medium">Field and remaining outcomes</span>
                  <span className="text-right text-xs font-semibold">+{remainingCount}</span>
                </div>
              )}
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

  // A/B variant: exposure-level assignment — hash(session + market) so each
  // market serves both variants across sessions and each session sees both.
  const _abSeed = `${typeof window !== "undefined" ? (localStorage.getItem("bainluck_session_id") || "anon") : "ssr"}_${data.id}`;
  const _abHash = Array.from(_abSeed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
  const variantB = (Math.abs(_abHash) % 2 === 0);
  const pctDisplay = prob != null ? `${Math.round(prob * 100)}%` : null;
  const movementVal = leader?.movement;
  const movementUp = movementVal != null && movementVal > 0;
  // L2-160 — respect the 5% placeholder floor: suppress the hero movement delta
  // when the leader probability is a placeholder (illiquid ~5% floor), where the
  // "movement" is noise rather than a real 24h shift.
  const probIsPlaceholder = prob != null && prob <= 0.05;
  const movementStr = movementVal != null && Math.abs(movementVal) >= 0.1 && !probIsPlaceholder
    ? `${movementUp ? "↑" : "↓"} ${Math.abs(movementVal).toFixed(1)}`
    : null;
  // L2-156 Item 3 — explain the arrow: it's a 24h probability move, not a rank change.
  const movementTitle = movementVal != null
    ? `${movementUp ? "Up" : "Down"} ${Math.abs(movementVal).toFixed(1)} points in the last 24h`
    : undefined;
  if (variantB) {
    // ── Variant B: data-pure (no image) ──
    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-variant="B">
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-4">
          <div className="flex items-center gap-2.5 mb-3.5">
            <div className="w-[38px] h-[38px] rounded-lg bg-surface-elevated flex items-center justify-center text-lg shrink-0">
              {catStyle.emoji}
            </div>
            <div className="leading-tight min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{category}</div>
              {resolveText && <div className="text-[11px] text-text-muted mt-0.5">{resolveText}</div>}
            </div>
          </div>

          {pctDisplay && (
            <div className="flex items-end gap-3 mb-3">
              <span className="font-mono font-bold text-4xl tracking-tight leading-none text-text-primary tabular-nums">{pctDisplay}</span>
              {movementStr && (
                <div className="pb-1">
                  <div className={`font-mono font-bold text-[15px] whitespace-nowrap ${movementUp ? "text-accent-live" : "text-accent-danger"}`} title={movementTitle}>{movementStr}</div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted mt-0.5">24h</div>
                </div>
              )}
            </div>
          )}

          {prob != null && (
            <div className="flex h-[7px] gap-0.5 mb-3.5">
              <div className="rounded-full bg-accent-brand shadow-inner" style={{ width: `${Math.round(prob * 100)}%` }} />
              <div className="rounded-full bg-text-muted/30 flex-1" />
            </div>
          )}

          <Link href={detailHref} onClick={onDetailClick} className="block group">
            <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-1.5">{data.name}</h3>
          </Link>

          {contextSnippet && (
            <ExpandableContextText
              text={contextSnippet}
              expandedText={expandedContext}
              className="text-[13px] leading-relaxed text-text-secondary mb-2.5"
              onExpand={onContextExpand}
              onCollapse={onContextCollapse}
            />
          )}

          {volumeStr && <div className="text-[11px] text-text-muted">{volumeStr}{resolveText ? ` · ${resolveText}` : ""}</div>}

          <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} />
        </div>
      </article>
    );
  }

  // ── Variant A: image-led (refined current treatment) ──
  return (
    <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-variant="A">
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className={`relative ${hasImage ? "aspect-[16/10]" : "h-32"} flex flex-col justify-end overflow-hidden`} style={{
        background: hasImage
          ? `url(${data.image_url}) center/cover`
          : CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
      }}>
        {/* Scrim gradient */}
        <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.04) 55%, rgba(0,0,0,0.22))" }} />

        {/* Category pill */}
        <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.04em] text-white bg-white/[0.18] backdrop-blur-sm px-2.5 py-1 rounded-full">
          {catStyle.emoji} {category}
        </div>

        {!hasImage && <span className="absolute inset-0 flex items-center justify-center text-[80px] opacity-[0.08] select-none pointer-events-none">{catStyle.emoji}</span>}

        {/* Probability hero bottom-left */}
        {leader && (
          <div className="relative z-10 px-3.5 pb-2.5">
            <div className="flex items-end gap-2">
              <span className="font-mono font-bold text-[38px] tracking-tight leading-none text-white tabular-nums">{pctDisplay}</span>
              {movementStr && (
                <span className={`font-mono font-bold text-[13px] pb-1 whitespace-nowrap ${movementUp ? "text-emerald-400" : "text-red-400"}`} title={movementTitle} aria-label={movementTitle}>{movementStr}</span>
              )}
            </div>
            <div className="text-[12px] font-medium text-white/85 mt-0.5 line-clamp-1">{leader.name}</div>
          </div>
        )}
      </div>

      <div className="px-3.5 py-3">
        <Link href={detailHref} onClick={onDetailClick} className="block group">
          <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-1.5">{data.name}</h3>
        </Link>

        {contextSnippet && (
          <ExpandableContextText
            text={contextSnippet}
            expandedText={expandedContext}
            className="text-[13px] leading-relaxed text-text-secondary mb-3"
            onExpand={onContextExpand}
            onCollapse={onContextCollapse}
          />
        )}

        <div className="flex items-center gap-2 text-[11px] text-text-muted">
          {volumeStr && <span className="whitespace-nowrap">{volumeStr}</span>}
          {volumeStr && resolveText && <span>·</span>}
          {resolveText && <span className="whitespace-nowrap">{resolveText}</span>}
          {data.confidence_tier && (volumeStr || resolveText) && <span>·</span>}
          <SignalBars tier={data.confidence_tier} />
        </div>

        <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} />
      </div>
    </article>
  );
}

type HeatmapRow = {
  key: string;
  label: string;
  probability: number | null;
  movement: number | null;
  sortValue: number;
};

function buildHeatmapRows(data: FeedFuturesData): HeatmapRow[] {
  const byLabel = new Map<string, HeatmapRow>();
  const outcomesByName = new Map(
    data.top_outcomes.map((outcome) => [outcome.name.toLowerCase(), outcome])
  );

  for (const point of data.discover_card?.threshold_points ?? []) {
    const label = point.label.trim();
    if (!label) continue;
    const key = label.toLowerCase();
    const matchedOutcome = outcomesByName.get(key);
    const existing = byLabel.get(key);
    const probability = point.probability ?? matchedOutcome?.probability ?? null;
    const movement = matchedOutcome?.movement ?? null;
    const sortValue = existing
      ? Math.min(existing.sortValue, point.value)
      : point.value;

    byLabel.set(key, {
      key,
      label,
      probability: existing?.probability ?? probability,
      movement: existing?.movement ?? movement,
      sortValue,
    });
  }

  return Array.from(byLabel.values()).sort((a, b) => a.sortValue - b.sortValue);
}

function formatComparisonTheme(theme: string | null | undefined): string {
  switch (theme) {
    case "ipo_valuation":
      return "Valuation";
    case "commodity_ranges":
      return "Commodity";
    case "rotten_tomatoes_scores":
      return "Score";
    case "macro_ranges":
      return "Macro";
    case "weather_distributions":
      return "Weather";
    case "sports_paths":
      return "Path";
    default:
      return "";
  }
}

function compactOutcomeName(name: string): string {
  const trimmed = name.trim().replace(/\s+/g, " ");
  if (trimmed.length <= 22) return trimmed;

  const parts = trimmed.split(" ");
  if (parts.length < 2) return trimmed;

  const suffixes = new Set(["Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV"]);
  const suffix = suffixes.has(parts[parts.length - 1]) ? ` ${parts.pop()}` : "";
  const last = parts.pop() || "";
  const initials = parts
    .filter(Boolean)
    .map((part) => `${part[0]}.`)
    .join(" ");

  return `${initials} ${last}${suffix}`.trim();
}

// ── Compact row used by GroupCard ──

export function FuturesCompactRow({ item, data }: { item: FeedItem; data: FeedFuturesData }) {
  const leader = data.top_outcomes?.[0];
  const context = feedContextSnippet(item);
  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;
  return (
    <Link href={detailHref} className="flex items-center gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold line-clamp-2 group-hover:text-accent-brand transition-colors">{data.name}</div>
        {context && <div className="text-xs text-text-muted mt-0.5 line-clamp-2">{context}</div>}
      </div>
      {leader && (
        <div className="flex items-center gap-2 shrink-0">
          <MovementBadge m={leader.movement} prob={leader.probability} />
          <span className="font-mono tabular-nums text-sm font-bold">{leader.probability != null && leader.probability > 0 ? `${Math.round(leader.probability * 100)}%` : "—"}</span>
        </div>
      )}
    </Link>
  );
}
