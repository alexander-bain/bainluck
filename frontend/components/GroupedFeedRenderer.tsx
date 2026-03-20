"use client";

/**
 * GroupedFeedRenderer — Renders items from the grouped futures feed API.
 *
 * Automatically selects the appropriate component based on item type:
 * - stat_prop → PlayerStatCard
 * - playoff_progression → ProgressionLadder
 * - threshold → ThresholdSparkline (wrapped in a card)
 * - market → FuturesCard (fallback for ungrouped markets)
 */

import { motion } from "framer-motion";
import { staggerContainer, staggerItem } from "@/lib/animations";
import type {
  GroupedFeedItem,
  StatPropFeedItem,
  PlayoffProgressionFeedItem,
  ThresholdFeedItem,
  UngroupedMarketFeedItem,
} from "@/lib/types";

import PlayerStatCard from "./PlayerStatCard";
import ProgressionLadder from "./ProgressionLadder";
import ThresholdSparkline from "./ThresholdSparkline";
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

function ThresholdItem({
  item,
  onClick,
}: {
  item: ThresholdFeedItem;
  onClick?: () => void;
}) {
  return (
    <motion.div
      className="bg-[var(--surface-card)] border border-[var(--surface-border)] rounded-xl p-4"
      variants={staggerItem}
    >
      {/* Title */}
      <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-3">
        {item.title}
      </h3>

      {/* Sparkline */}
      <ThresholdSparkline
        points={item.points}
        height={48}
        showLabels
        onPointClick={() => onClick?.()}
      />

      {/* Count badge */}
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-[var(--text-muted)]">
          {item.outcome_count} thresholds
        </span>
      </div>
    </motion.div>
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
  if (!items || items.length === 0) {
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
      {items.map((item, idx) => {
        const key = `${item.type}-${idx}`;

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
              <ThresholdItem
                key={key}
                item={item}
                onClick={() => onItemClick?.(item)}
              />
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
