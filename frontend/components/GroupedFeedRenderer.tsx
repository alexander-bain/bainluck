"use client";

/**
 * GroupedFeedRenderer — Renders items from the grouped futures feed API.
 *
 * Automatically selects the appropriate component based on item type:
 * - stat_prop → PlayerStatCard
 * - playoff_progression → ProgressionLadder
 * - threshold → QuantityGroup (the shared Quantity kernel — one question, many
 *   rungs; Queue L2-119 retired the #958-era pooled ThresholdSparkline strip so
 *   the card system and detail-page system draw the SAME primitive)
 * - market → FuturesCard (fallback for ungrouped markets)
 */

import { motion } from "@/components/motion";
import { staggerContainer, staggerItem } from "@/lib/animations";
import { admittedPropStripRows } from "@/lib/sports/propStripAdmission";
import type {
  GroupedFeedItem,
  StatPropFeedItem,
  PlayoffProgressionFeedItem,
  ThresholdFeedItem,
  UngroupedMarketFeedItem,
} from "@/lib/types";

import PlayerStatCard from "./PlayerStatCard";
import ProgressionLadder from "./ProgressionLadder";
import QuantityGroup, { buildThresholdRungs } from "./QuantityGroup";
import FuturesCard from "./FuturesCard";

interface GroupedFeedRendererProps {
  /** Feed items from the grouped-feed API */
  items: GroupedFeedItem[];
  /** Compact mode for denser display */
  compact?: boolean;
  /** Click handler for individual items */
  onItemClick?: (item: GroupedFeedItem) => void;
}

function StatPropItem({
  item,
  compact,
  onClick,
}: {
  item: StatPropFeedItem;
  compact?: boolean;
  onClick?: () => void;
}) {
  return (
    <PlayerStatCard
      playerName={item.player_name}
      statCategory={item.stat_category}
      lines={item.lines}
      compact={compact}
      espnPlayerId={item.espn_player_id}
      sportKey={item.sport_key}
      eventMatchup={item.event_matchup}
      eventTime={item.event_time}
      onLineClick={() => onClick?.()}
    />
  );
}

function PlayoffProgressionItem({
  item,
  onClick,
}: {
  item: PlayoffProgressionFeedItem;
  onClick?: () => void;
}) {
  return (
    <ProgressionLadder
      entityName={item.entity_name}
      stages={item.stages}
      horizontal
      onStageClick={() => onClick?.()}
    />
  );
}

/**
 * Prettify a threshold stem into a question-context title. The backend stem is
 * lowercased with the numeric threshold stripped (e.g. "will bitcoin exceed $"),
 * so we collapse whitespace, trim dangling stem artifacts, and sentence-case it.
 * The kernel discipline (Queue L2-119): a Quantity ladder NEVER renders without
 * its question context, so we always resolve to a non-empty title.
 */
/**
 * Stable per-entity React key for a grouped-feed row (L2-178 / L2-199).
 *
 * NOT the array index: an index key made React recycle a card instance (and its
 * resolved player headshot / team logo) for a DIFFERENT entity when the list
 * reordered or updated — the "wrong-face" bug. Keying by entity identity forces
 * a fresh component instance (fresh image state) whenever the entity at a
 * position changes, so a replaced row can never retain the previous entity's
 * image or failure state. `group_key` is the grouping identity for grouped
 * items; ungrouped markets key by their market id.
 */
export function groupedFeedItemKey(item: GroupedFeedItem): string {
  return item.type === "market"
    ? `market-${item.market.id}`
    : `${item.type}-${item.group_key}`;
}

export function formatThresholdTitle(title: string): string {
  const cleaned = (title ?? "")
    .replace(/\s+/g, " ")
    .replace(/[\s#$·,:;–-]+$/g, "")
    .trim();
  if (!cleaned) return "Threshold market";
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function ThresholdItem({
  item,
  compact,
  onClick,
}: {
  item: ThresholdFeedItem;
  compact?: boolean;
  onClick?: () => void;
}) {
  // One question, many rungs — the shared Quantity kernel. Every rung is a
  // cumulative threshold; the ladder reads top-down and never wraps its columns
  // (the old pooled sparkline hid the shape). Always title it: the kernel
  // discipline forbids a naked ladder without its question context.
  //
  // UX-1052 item 2 — an EXACT SCORE row is the same kernel asking a different
  // question. It is a discrete distribution, so it reads most-likely-first, its
  // rungs are labelled with the scoreline the market actually offers, and a
  // capped ladder says how many scorelines it left off instead of just ending.
  const isExactScore = item.kind === "exact_score";
  const rungs = buildThresholdRungs(
    item.points.map((p) => ({
      outcome_id: p.id,
      name: p.name,
      probability: p.probability,
      threshold_value: p.threshold_value,
      threshold_unit: p.threshold_unit,
      threshold_direction: p.threshold_direction,
      label: p.label,
    })),
  );
  if (rungs.length === 0) return null;
  const cap = compact ? 4 : undefined;
  const hidden = cap == null ? 0 : Math.max(0, rungs.length - cap);
  return (
    <QuantityGroup
      title={formatThresholdTitle(item.title)}
      rungs={rungs}
      compact={compact}
      sortBy={isExactScore ? "probability" : "value"}
      footnote={
        isExactScore && hidden > 0
          ? `${hidden} more scoreline${hidden === 1 ? "" : "s"}`
          : undefined
      }
      onRungSelect={onClick ? () => onClick() : undefined}
    />
  );
}

function UngroupedMarketItem({
  item,
  onClick,
}: {
  item: UngroupedMarketFeedItem;
  onClick?: () => void;
}) {
  // Convert to FuturesCard format
  const market = item.market;
  return (
    <FuturesCard
      market={{
        id: market.id,
        name: market.name,
        description: null,
        source: market.source,
        category: market.category || null,
        sport: market.sport || null,
        sport_name: null,
        llm_sport_category: null,
        external_id: null,
        mutually_exclusive: true,
        commence_time: null,
        resolution_date: null,
        outcome_count: market.outcomes.length,
        created_at: null,
        updated_at: null,
        status: "open",
        outcomes: market.outcomes.map((o) => ({
          id: o.id,
          name: o.name,
          probability: o.probability,
          american_odds: o.american_odds || null,
          rank: null,
          rank_change_24h: null,
          probability_change_24h: null,
          movement: null,
          opening_probability: null,
          opening_american_odds: null,
          is_winner: null,
          last_updated: null,
        })),
      }}
    />
  );
}

export default function GroupedFeedRenderer({
  items,
  compact = false,
  onItemClick,
}: GroupedFeedRendererProps) {
  // UX-P276 (#2710) — "a card with no number is not shown" (Alex). A row that
  // carries no printable probability rendered a full card whose body was the
  // words "No outcomes available", or a column of dashes. The strip had no
  // admission of any kind; it renders whatever the endpoint returns.
  // Fail-closed, and shared with the section heading's count so the two cannot
  // disagree — see `lib/sports/propStripAdmission.ts` for why this is NOT the
  // Discover card-admission contract.
  const admitted = admittedPropStripRows(items);

  if (admitted.length === 0) {
    return (
      <div className="text-center py-12 text-[var(--text-muted)]">
        No grouped markets found
      </div>
    );
  }

  return (
    <motion.div
      className="grid gap-3"
      style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      {admitted.map((item) => {
        // Key by a STABLE entity id, not the array index (see groupedFeedItemKey).
        const key = groupedFeedItemKey(item);

        switch (item.type) {
          case "stat_prop":
            return (
              <motion.div key={key} variants={staggerItem}>
                <StatPropItem
                  item={item}
                  compact={compact}
                  onClick={() => onItemClick?.(item)}
                />
              </motion.div>
            );

          case "playoff_progression":
            return (
              <motion.div key={key} variants={staggerItem}>
                <PlayoffProgressionItem
                  item={item}
                  onClick={() => onItemClick?.(item)}
                />
              </motion.div>
            );

          case "threshold":
            return (
              <motion.div key={key} variants={staggerItem}>
                <ThresholdItem
                  item={item}
                  compact={compact}
                  onClick={() => onItemClick?.(item)}
                />
              </motion.div>
            );

          case "market":
            return (
              <motion.div key={key} variants={staggerItem}>
                <UngroupedMarketItem
                  item={item}
                  onClick={() => onItemClick?.(item)}
                />
              </motion.div>
            );

          default:
            return null;
        }
      })}
    </motion.div>
  );
}
