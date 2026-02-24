"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { fetchRelatedFutures, formatProbability } from "@/lib/api";
import EntityImage from "./EntityImage";

interface RelatedFuturesProps {
  eventId: number;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  homeTeamLogo?: string;
  awayTeamLogo?: string;
  sportKey?: string;
}

/** Tier display config */
const TIER_CONFIG: Record<number, { label: string; icon: string }> = {
  1: { label: "Championship", icon: "🏆" },
  2: { label: "Conference", icon: "🏅" },
  3: { label: "Award", icon: "⭐" },
  4: { label: "Division", icon: "📊" },
  5: { label: "Market", icon: "📈" },
};

const DEFAULT_COLOR = "#6B7280";

/** Stat prop market patterns — "Team at Team: Stat Category" from Kalshi */
const STAT_PROP_PATTERNS = [
  /:\s*(points|assists|rebounds|steals|blocks|three\s*pointers?|3-?pointers?|turnovers|strikeouts|hits|runs|home\s*runs|goals|saves|sacks|passing\s*yards|rushing\s*yards|receiving\s*yards|touchdowns|completions|interceptions|aces|double\s*faults|kills)/i,
  /\bat\b.*:\s*\w/i,       // "Team at Team: Something" (Kalshi game stat format)
];

/** Stat category config — emoji + display name */
const STAT_CATEGORIES: Record<string, { emoji: string; label: string }> = {
  points: { emoji: "🏀", label: "Points" },
  assists: { emoji: "🤝", label: "Assists" },
  rebounds: { emoji: "💪", label: "Rebounds" },
  steals: { emoji: "🖐️", label: "Steals" },
  blocks: { emoji: "🚫", label: "Blocks" },
  "three pointers": { emoji: "🎯", label: "3-Pointers" },
  "3-pointers": { emoji: "🎯", label: "3-Pointers" },
  threepointers: { emoji: "🎯", label: "3-Pointers" },
  turnovers: { emoji: "🔄", label: "Turnovers" },
  strikeouts: { emoji: "⚾", label: "Strikeouts" },
  hits: { emoji: "🏏", label: "Hits" },
  runs: { emoji: "🏃", label: "Runs" },
  "home runs": { emoji: "💣", label: "Home Runs" },
  goals: { emoji: "⚽", label: "Goals" },
  saves: { emoji: "🧤", label: "Saves" },
  sacks: { emoji: "🏈", label: "Sacks" },
  "passing yards": { emoji: "🎯", label: "Pass Yds" },
  "rushing yards": { emoji: "🏃", label: "Rush Yds" },
  "receiving yards": { emoji: "📡", label: "Rec Yds" },
  touchdowns: { emoji: "🏈", label: "TDs" },
  completions: { emoji: "✅", label: "Comp" },
  interceptions: { emoji: "🔴", label: "INTs" },
  aces: { emoji: "🎾", label: "Aces" },
  kills: { emoji: "⚡", label: "Kills" },
};

/** Game-level market name patterns — these are individual matchup markets, not futures */
const GAME_MARKET_PATTERNS = [
  /\bvs\.?\s/i,           // "Team A vs. Team B" or "Team A vs Team B"
  /\s–\s/,                // "Team A – Team B" (en-dash)
  /more\s+markets$/i,     // "... - More Markets" (Polymarket suffix)
  /moneyline$/i,          // "Game X Moneyline"
  /\bgame\s+\d/i,         // "Game 1", "Game 7"
];

/** Award market name patterns */
const AWARD_PATTERNS = [
  /\bmvp\b/i,
  /\bgolden\s+boot\b/i,
  /\bgolden\s+glove\b/i,
  /\bcyoung\b|cy\s+young/i,
  /\bnewcomer\b|\brookie\b/i,
  /player\s+of\s+(the\s+)?year/i,
  /\bballon\b/i,
  /\bbest\s+(actor|actress|picture|director|supporting)\b/i,
];

/**
 * Determine the effective display tier for a future, using name-based detection
 * as a fallback when market_tier from the backend may be wrong or null.
 *
 * Returns 1-5 for standard tiers, 6 for stat props (special display).
 */
function effectiveTier(f: RelatedFuture): number {
  if (!f.market_name) return 5;

  // Stat props get their own tier (6) for special display treatment
  if (STAT_PROP_PATTERNS.some((p) => p.test(f.market_name))) {
    return 6;
  }
  // If the name looks like a game-level market, always treat as tier 5
  if (GAME_MARKET_PATTERNS.some((p) => p.test(f.market_name))) {
    return 5;
  }
  // If the name looks like an award, treat as tier 3
  if (AWARD_PATTERNS.some((p) => p.test(f.market_name))) {
    return 3;
  }
  // Trust the backend tier if it's set
  if (f.market_tier && f.market_tier >= 1 && f.market_tier <= 5) {
    return f.market_tier;
  }
  // Default: generic market
  return 5;
}

/**
 * Extract stat category from a stat prop market name.
 * e.g. "Boston at Golden State: Three Pointers" → "three pointers"
 */
function extractStatCategory(marketName: string): string {
  const colonMatch = marketName.match(/:\s*(.+?)$/i);
  if (colonMatch) return colonMatch[1].trim().toLowerCase();
  return "other";
}

/**
 * Look up emoji + display name for a stat category.
 */
function getStatConfig(category: string): { emoji: string; label: string } {
  // Try exact match first
  if (STAT_CATEGORIES[category]) return STAT_CATEGORIES[category];
  // Try partial match
  for (const [key, config] of Object.entries(STAT_CATEGORIES)) {
    if (category.includes(key) || key.includes(category)) return config;
  }
  return { emoji: "📊", label: category.charAt(0).toUpperCase() + category.slice(1) };
}

/**
 * Clean up market name for display — strip redundant suffixes and prefixes.
 */
function cleanMarketName(name: string): string {
  return name
    .replace(/\s*-\s*More Markets$/i, "")
    .replace(/\s*-\s*Moneyline$/i, "")
    .trim();
}

/** Format American odds */
function formatOdds(odds: number | null | undefined): string {
  if (odds === null || odds === undefined) return "";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

/** Movement pill — colored badge with arrow */
function MovementPill({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined || !Number.isFinite(change)) return null;
  if (Math.abs(change) < 0.001) return null;

  const isUp = change > 0;
  const abs = Math.abs(change * 100);

  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${
        isUp
          ? "bg-emerald-500/15 text-emerald-500"
          : "bg-red-500/15 text-red-500"
      }`}
    >
      {isUp ? "↑" : "↓"} {abs.toFixed(1)}%
    </span>
  );
}

/** Source badge */
function SourceBadge({ source }: { source: string | null | undefined }) {
  if (!source) return null;
  const label: Record<string, string> = {
    polymarket: "Polymarket",
    kalshi: "Kalshi",
    odds_api: "Sportsbooks",
  };
  const colors: Record<string, string> = {
    polymarket: "bg-blue-500/15 text-blue-400",
    kalshi: "bg-emerald-500/15 text-emerald-400",
    odds_api: "bg-amber-500/15 text-amber-400",
  };
  return (
    <span
      className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${
        colors[source] || "bg-surface-elevated text-text-muted"
      }`}
    >
      {label[source] || source}
    </span>
  );
}

// ─── HERO CARD: Championship / Conference / Division futures ───
function HeroFutureCard({
  future,
  teamColor,
}: {
  future: RelatedFuture;
  teamColor: string;
}) {
  const tierNum = effectiveTier(future);
  const tier = TIER_CONFIG[tierNum] || null;

  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="block group rounded-xl p-4 transition-all duration-200 hover:scale-[1.01]"
      style={{
        background: `linear-gradient(135deg, ${teamColor}18, ${teamColor}08)`,
        border: `1px solid ${teamColor}30`,
      }}
    >
      {/* Header: tier + market name + source */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            {tier && <span className="text-[10px]">{tier.icon}</span>}
            <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
              {tier?.label || "Market"}
            </span>
          </div>
          <div className="text-xs text-text-secondary leading-snug">
            {cleanMarketName(future.market_name)}
          </div>
        </div>
        <SourceBadge source={future.source} />
      </div>

      {/* Big probability + movement + odds */}
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="flex items-baseline gap-2">
            <span
              className="text-2xl font-bold tabular-nums tracking-tight"
              style={{ color: teamColor }}
            >
              {formatProbability(future.probability)}
            </span>
            <MovementPill change={future.probability_change_24h} />
          </div>
          <div className="text-[11px] text-text-muted font-mono mt-0.5">
            {formatOdds(future.american_odds)}
          </div>
        </div>
        {future.rank && (
          <div className="text-right">
            <div className="text-[10px] text-text-muted uppercase">Rank</div>
            <div className="text-lg font-bold text-text-secondary">
              #{future.rank}
            </div>
          </div>
        )}
      </div>

      {/* Subtle probability bar */}
      <div className="mt-3 h-1 rounded-full bg-surface-elevated overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.max(2, Math.min(100, (future.probability || 0) / 0.5 * 100))}%`,
            backgroundColor: teamColor,
            opacity: 0.7,
          }}
        />
      </div>
    </Link>
  );
}

/**
 * Extract a short award label from a market name.
 * e.g., "NBA Most Valuable Player" → "MVP"
 * e.g., "NBA Rookie of the Year" → "Rookie of the Year"
 */
function shortAwardLabel(marketName: string): string {
  const cleaned = cleanMarketName(marketName);
  // Common abbreviations
  if (/\bmvp\b|most\s+valuable/i.test(cleaned)) return "MVP";
  if (/\brookie\s+of\s+the\s+year\b/i.test(cleaned)) return "Rookie of the Year";
  if (/\bdefensive\s+player/i.test(cleaned)) return "DPOY";
  if (/\bmost\s+improved/i.test(cleaned)) return "Most Improved";
  if (/\bsixth\s+man/i.test(cleaned)) return "6th Man";
  if (/\bcy\s*young/i.test(cleaned)) return "Cy Young";
  if (/\bgolden\s+boot/i.test(cleaned)) return "Golden Boot";
  if (/\bgolden\s+glove/i.test(cleaned)) return "Golden Glove";
  if (/\bballon/i.test(cleaned)) return "Ballon d'Or";
  if (/\bheisman/i.test(cleaned)) return "Heisman";
  if (/\bcoach\s+of\s+the\s+year/i.test(cleaned)) return "Coach of the Year";
  // Fallback: strip league prefix (e.g., "NBA" from "NBA MVP")
  return cleaned.replace(/^(NBA|NFL|NHL|MLB|MLS|WNBA|NCAAB|NCAAF)\s+/i, "");
}

// ─── AWARD CARD: MVP / individual awards ───
function AwardCard({
  future,
  teamColor,
  sportKey,
}: {
  future: RelatedFuture;
  teamColor: string;
  sportKey?: string;
}) {
  const awardLabel = shortAwardLabel(future.market_name);

  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="flex items-center gap-3 rounded-xl p-3 group transition-all duration-200 hover:scale-[1.005]"
      style={{
        background: `linear-gradient(135deg, ${teamColor}10, transparent)`,
        border: `1px solid ${teamColor}20`,
      }}
    >
      {/* Player headshot — 48px for prominence */}
      {future.matched_player?.espn_id ? (
        <EntityImage
          type="player"
          name={future.outcome_name}
          espnId={future.matched_player.espn_id}
          sport={sportKey}
          size={48}
          fallbackColor={teamColor}
        />
      ) : (
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
          style={{ backgroundColor: `${teamColor}20`, color: teamColor }}
        >
          {future.outcome_name
            ?.split(" ")
            .map((w: string) => w[0])
            .join("")
            .slice(0, 2)}
        </div>
      )}

      <div className="min-w-0 flex-1">
        {/* Player name — primary, large */}
        <div className="text-[15px] font-bold text-text-primary truncate leading-tight">
          {future.outcome_name}
        </div>
        {/* Award label — secondary */}
        <div className="flex items-center gap-1 mt-0.5">
          <span className="text-[10px]">⭐</span>
          <span className="text-[11px] text-text-muted truncate font-medium">
            {awardLabel}
          </span>
        </div>
      </div>

      <div className="text-right shrink-0">
        <div className="flex items-center gap-1.5 justify-end">
          <span
            className="text-xl font-bold tabular-nums"
            style={{ color: teamColor }}
          >
            {formatProbability(future.probability)}
          </span>
          <MovementPill change={future.probability_change_24h} />
        </div>
        <div className="text-[10px] text-text-muted font-mono">
          {formatOdds(future.american_odds)}
        </div>
      </div>
    </Link>
  );
}

/**
 * Extract opponent name from a game-level market name by stripping
 * the current team's name and common suffixes.
 */
function extractOpponent(marketName: string, teamName: string): string {
  const teamWords = teamName.split(" ");
  const shortName = teamWords[teamWords.length - 1] || teamName;

  // Escape regex special chars in team names
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  return marketName
    .replace(/ - More Markets$/i, "")
    .replace(/\s*-\s*Moneyline$/i, "")
    .replace(new RegExp(`^${esc(teamName)}\\s+vs\\.?\\s+`, "i"), "")
    .replace(new RegExp(`\\s+vs\\.?\\s+${esc(teamName)}$`, "i"), "")
    .replace(new RegExp(`^${esc(shortName)}\\s+vs\\.?\\s+`, "i"), "")
    .replace(new RegExp(`\\s+vs\\.?\\s+${esc(shortName)}$`, "i"), "")
    // Also handle en-dash separator
    .replace(new RegExp(`^${esc(teamName)}\\s+–\\s+`, "i"), "")
    .replace(new RegExp(`\\s+–\\s+${esc(teamName)}$`, "i"), "")
    .replace(new RegExp(`^${esc(shortName)}\\s+–\\s+`, "i"), "")
    .replace(new RegExp(`\\s+–\\s+${esc(shortName)}$`, "i"), "")
    .trim();
}

// ─── GAME GRID: Dense 2-col cells for matchup markets ───
function GameMarketsGrid({
  futures,
  teamColor,
  teamName,
}: {
  futures: RelatedFuture[];
  teamColor: string;
  teamName: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (futures.length === 0) return null;

  // --- Filter and deduplicate ---
  // 1. Remove resolved/illiquid markets (0% or 100%)
  const meaningful = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return false;
    if (p <= 0.02 || p >= 0.98) return false; // effectively 0% or 100%
    return true;
  });

  // 2. Deduplicate by opponent name — keep the one with highest relevance_score
  const opponentMap = new Map<string, RelatedFuture>();
  for (const f of meaningful) {
    const opponent = extractOpponent(f.market_name, teamName).toLowerCase();
    const existing = opponentMap.get(opponent);
    if (
      !existing ||
      (f.relevance_score || 0) > (existing.relevance_score || 0)
    ) {
      opponentMap.set(opponent, f);
    }
  }
  const deduped = Array.from(opponentMap.values());

  // Sort: favored games first
  const sorted = deduped.sort(
    (a, b) => (b.probability || 0) - (a.probability || 0)
  );

  if (sorted.length === 0) return null;

  const COLLAPSED_COUNT = 6;
  const visible = expanded ? sorted : sorted.slice(0, COLLAPSED_COUNT);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px]">📈</span>
        <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
          Game-by-game odds
        </span>
        <span className="text-[10px] text-text-muted/50">
          ({sorted.length})
        </span>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {visible.map((f) => {
          const opponent = extractOpponent(f.market_name, teamName);
          const prob = f.probability || 0;
          const favored = prob > 0.5;
          const barPct = Math.min(100, prob * 100);

          return (
            <Link
              key={f.outcome_id}
              href={`/futures/${f.market_id}`}
              className="relative rounded-lg px-2.5 py-2 group transition-colors overflow-hidden bg-surface-elevated/30 border border-surface-elevated/50 hover:bg-surface-elevated/60"
            >
              {/* Background probability fill */}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  width: `${barPct}%`,
                  backgroundColor: teamColor,
                  opacity: favored ? 0.08 : 0.03,
                }}
              />

              {/* Content */}
              <div className="relative flex items-center justify-between gap-1">
                <span className="text-xs text-text-secondary truncate">
                  {opponent}
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <span
                    className="text-[13px] font-bold tabular-nums"
                    style={{
                      color: favored ? teamColor : "var(--text-muted)",
                    }}
                  >
                    {Math.round(prob * 100)}%
                  </span>
                  {f.probability_change_24h &&
                    Math.abs(f.probability_change_24h) >= 0.005 && (
                      <span
                        className={`text-[9px] font-semibold ${
                          f.probability_change_24h > 0
                            ? "text-emerald-500"
                            : "text-red-500"
                        }`}
                      >
                        {f.probability_change_24h > 0 ? "↑" : "↓"}
                      </span>
                    )}
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      {sorted.length > COLLAPSED_COUNT && (
        <button
          onClick={(e) => {
            e.preventDefault();
            setExpanded(!expanded);
          }}
          className="text-[11px] text-blue-500 hover:text-blue-400 font-medium mt-2 transition-colors"
        >
          {expanded
            ? "Show less"
            : `+${sorted.length - COLLAPSED_COUNT} more games`}
        </button>
      )}
    </div>
  );
}

/**
 * Extract the line number from an outcome name.
 * e.g., "Over 218.5" → 218.5, "Under 48.5" → 48.5, "Yes" → null
 */
function extractLine(outcomeName: string): number | null {
  const match = outcomeName.match(/(\d+\.?\d*)/);
  return match ? parseFloat(match[1]) : null;
}

/**
 * Check if outcome is "Over" side.
 */
function isOver(outcomeName: string): boolean {
  return /^over\b/i.test(outcomeName.trim());
}

/** A paired stat prop: Over + Under for the same market */
interface StatPair {
  category: string;
  config: { emoji: string; label: string };
  line: number | null;
  overProb: number | null;
  underProb: number | null;
  overFuture: RelatedFuture;
  underFuture: RelatedFuture | null;
  marketId: number;
}

// ─── STAT PROPS: Over/Under gauge visualization ───
function StatPropsSection({
  futures,
  teamColor,
}: {
  futures: RelatedFuture[];
  teamColor: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (futures.length === 0) return null;

  // Filter out resolved/illiquid
  const meaningful = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return false;
    if (p <= 0.02 || p >= 0.98) return false;
    return true;
  });

  if (meaningful.length === 0) return null;

  // Group by market_id to pair Over/Under outcomes
  const marketMap = new Map<number, RelatedFuture[]>();
  for (const f of meaningful) {
    const existing = marketMap.get(f.market_id) || [];
    existing.push(f);
    marketMap.set(f.market_id, existing);
  }

  // Build stat pairs
  const pairs: StatPair[] = [];
  marketMap.forEach((outcomes, marketId) => {
    const cat = extractStatCategory(outcomes[0].market_name);
    const config = getStatConfig(cat);

    const overOutcome = outcomes.find((o: RelatedFuture) => isOver(o.outcome_name));
    const underOutcome = outcomes.find(
      (o: RelatedFuture) => /^under\b/i.test(o.outcome_name.trim())
    );
    // Use whichever we have as primary
    const primary = overOutcome || outcomes[0];
    const line = extractLine(primary.outcome_name);

    pairs.push({
      category: cat,
      config,
      line,
      overProb: overOutcome?.probability ?? null,
      underProb: underOutcome?.probability ?? null,
      overFuture: primary,
      underFuture: underOutcome || null,
      marketId,
    });
  });

  // Sort: by category name for grouping, then by line
  pairs.sort((a, b) => {
    if (a.category !== b.category) return a.category.localeCompare(b.category);
    return (a.line || 0) - (b.line || 0);
  });

  const COLLAPSED_COUNT = 4;
  const visible = expanded ? pairs : pairs.slice(0, COLLAPSED_COUNT);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px]">📊</span>
        <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
          Player & team stats
        </span>
        <span className="text-[10px] text-text-muted/50">
          ({pairs.length})
        </span>
      </div>

      <div className="space-y-1.5">
        {visible.map((pair) => {
          const overPct = pair.overProb !== null ? pair.overProb * 100 : 50;
          const leansOver = overPct >= 50;

          return (
            <Link
              key={pair.marketId}
              href={`/futures/${pair.marketId}`}
              className="block rounded-lg p-2.5 group transition-colors bg-surface-elevated/30 border border-surface-elevated/50 hover:bg-surface-elevated/60"
            >
              {/* Top row: emoji + stat label + line number */}
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">{pair.config.emoji}</span>
                  <span className="text-xs font-semibold text-text-secondary">
                    {pair.config.label}
                  </span>
                </div>
                {pair.line !== null && (
                  <span className="text-xs font-bold text-text-primary tabular-nums">
                    {pair.line}
                  </span>
                )}
              </div>

              {/* Over/Under gauge bar */}
              <div className="relative h-5 rounded-full overflow-hidden bg-surface-elevated flex">
                {/* Over side */}
                <div
                  className="h-full flex items-center justify-start pl-1.5 transition-all duration-500"
                  style={{
                    width: `${overPct}%`,
                    backgroundColor: leansOver
                      ? `${teamColor}30`
                      : `${teamColor}12`,
                  }}
                >
                  <span
                    className="text-[10px] font-bold tabular-nums whitespace-nowrap"
                    style={{
                      color: leansOver ? teamColor : "var(--text-muted)",
                    }}
                  >
                    O {Math.round(overPct)}%
                  </span>
                </div>
                {/* Under side */}
                <div
                  className="h-full flex-1 flex items-center justify-end pr-1.5"
                  style={{
                    backgroundColor: !leansOver
                      ? "rgba(156,163,175,0.2)"
                      : "rgba(156,163,175,0.08)",
                  }}
                >
                  <span
                    className="text-[10px] font-bold tabular-nums whitespace-nowrap"
                    style={{
                      color: !leansOver
                        ? "var(--text-secondary)"
                        : "var(--text-muted)",
                    }}
                  >
                    U {Math.round(100 - overPct)}%
                  </span>
                </div>
                {/* Center line marker */}
                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-surface-card/60" />
              </div>
            </Link>
          );
        })}
      </div>

      {pairs.length > COLLAPSED_COUNT && (
        <button
          onClick={(e) => {
            e.preventDefault();
            setExpanded(!expanded);
          }}
          className="text-[11px] text-blue-500 hover:text-blue-400 font-medium mt-2 transition-colors"
        >
          {expanded
            ? "Show less"
            : `+${pairs.length - COLLAPSED_COUNT} more stats`}
        </button>
      )}
    </div>
  );
}

// ─── TITLE ODDS COMPARISON BAR ───
function TitleComparison({
  homeChamp,
  awayChamp,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
}: {
  homeChamp: RelatedFuture;
  awayChamp: RelatedFuture;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor: string;
  awayTeamColor: string;
}) {
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  return (
    <div className="rounded-xl p-4 bg-surface-elevated/40 border border-surface-elevated mb-4">
      <div className="text-[10px] text-text-muted uppercase tracking-wider mb-3 text-center">
        🏆 Title Odds
      </div>
      <div className="flex items-center gap-4">
        {/* Home */}
        <div className="flex-1 text-right">
          <div className="text-[11px] text-text-muted mb-0.5">
            {homeShort}
          </div>
          <div className="flex items-center justify-end gap-2">
            <MovementPill change={homeChamp.probability_change_24h} />
            <span
              className="text-2xl font-bold tabular-nums"
              style={{ color: homeTeamColor }}
            >
              {formatProbability(homeChamp.probability)}
            </span>
          </div>
          <div className="text-[10px] font-mono text-text-muted/50 mt-0.5">
            {formatOdds(homeChamp.american_odds)}
          </div>
        </div>

        {/* Divider */}
        <div className="w-px h-12 bg-surface-elevated" />

        {/* Away */}
        <div className="flex-1">
          <div className="text-[11px] text-text-muted mb-0.5">
            {awayShort}
          </div>
          <div className="flex items-center gap-2">
            <span
              className="text-2xl font-bold tabular-nums"
              style={{ color: awayTeamColor }}
            >
              {formatProbability(awayChamp.probability)}
            </span>
            <MovementPill change={awayChamp.probability_change_24h} />
          </div>
          <div className="text-[10px] font-mono text-text-muted/50 mt-0.5">
            {formatOdds(awayChamp.american_odds)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── TEAM COLUMN: Tier-grouped display ───
function TeamColumn({
  teamName,
  futures,
  teamColor,
  teamLogo,
  sportKey,
}: {
  teamName: string;
  futures: RelatedFuture[];
  teamColor: string;
  teamLogo?: string;
  sportKey?: string;
}) {
  const championship = futures.filter((f) => effectiveTier(f) === 1);
  const conference = futures.filter((f) => {
    const t = effectiveTier(f);
    return t === 2 || t === 4;
  });
  const awards = futures.filter((f) => effectiveTier(f) === 3);
  const games = futures.filter((f) => effectiveTier(f) === 5);
  const statProps = futures.filter((f) => effectiveTier(f) === 6);

  const shortName = teamName.split(" ").pop() || teamName;

  if (futures.length === 0) return null;

  return (
    <div className="flex-1 min-w-0">
      {/* Team header */}
      <div
        className="flex items-center gap-2 mb-4 pb-2"
        style={{ borderBottom: `2px solid ${teamColor}40` }}
      >
        {teamLogo && (
          <img
            src={teamLogo}
            alt=""
            width={20}
            height={20}
            loading="lazy"
            className="w-5 h-5 object-contain"
          />
        )}
        <h4 className="text-xs font-bold uppercase tracking-wider text-text-primary">
          {shortName}
        </h4>
        <span className="text-[10px] text-text-muted">
          {futures.length} market{futures.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-3">
        {/* Championship — hero cards */}
        {championship.map((f) => (
          <HeroFutureCard
            key={f.outcome_id}
            future={f}
            teamColor={teamColor}
          />
        ))}

        {/* Conference / Division — same hero treatment */}
        {conference.map((f) => (
          <HeroFutureCard
            key={f.outcome_id}
            future={f}
            teamColor={teamColor}
          />
        ))}

        {/* Awards — player-centric rows with headshots */}
        {awards.length > 0 && (
          <div className="space-y-1.5">
            {awards.map((f) => (
              <AwardCard
                key={f.outcome_id}
                future={f}
                teamColor={teamColor}
                sportKey={sportKey}
              />
            ))}
          </div>
        )}

        {/* Game markets — dense 2-col grid */}
        <GameMarketsGrid
          futures={games}
          teamColor={teamColor}
          teamName={teamName}
        />

        {/* Stat props — grouped by category with emoji */}
        <StatPropsSection futures={statProps} teamColor={teamColor} />
      </div>
    </div>
  );
}

/**
 * Related Futures — "Bigger Picture" section on event detail page.
 *
 * Tier-grouped display:
 * - Title Odds comparison bar (always visible when both teams have championship futures)
 * - Championship/Conference futures as hero cards with gradient tints
 * - Award futures as player-centric rows with headshots
 * - Game markets as dense 2-column grid cells
 *
 * When an LLM summary is available, shows summary-first with details collapsed.
 * Falls back to expanded team columns when no summary exists.
 */
export default function RelatedFutures({
  eventId,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  sportKey,
}: RelatedFuturesProps) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const { data, error, isLoading } = useSWR<RelatedFuturesResponse>(
    ["related-futures", eventId],
    () => fetchRelatedFutures(eventId),
    {
      revalidateOnFocus: false,
      dedupingInterval: 300000, // 5 min — futures update hourly
    }
  );

  if (isLoading || error || !data || data.total_count === 0) {
    return null;
  }

  const { home_team_futures, away_team_futures, summary } = data;
  const hasSummary = !!summary;

  // Find championship futures for the comparison bar
  const homeChamp = home_team_futures.find((f) => effectiveTier(f) === 1);
  const awayChamp = away_team_futures.find((f) => effectiveTier(f) === 1);
  const showTitleComparison = !!(homeChamp && awayChamp);

  const hColor = homeTeamColor || DEFAULT_COLOR;
  const aColor = awayTeamColor || DEFAULT_COLOR;

  const teamDetails = (
    <div className="flex flex-col sm:flex-row gap-6">
      <TeamColumn
        teamName={homeTeam}
        futures={home_team_futures}
        teamColor={hColor}
        teamLogo={homeTeamLogo}
        sportKey={sportKey}
      />
      <TeamColumn
        teamName={awayTeam}
        futures={away_team_futures}
        teamColor={aColor}
        teamLogo={awayTeamLogo}
        sportKey={sportKey}
      />
    </div>
  );

  return (
    <div className="bg-surface-card rounded-card shadow-card p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-text-secondary mb-3">
        Bigger Picture
      </h3>

      {/* LLM Summary */}
      {hasSummary && (
        <p className="text-sm text-text-primary leading-relaxed mb-3">
          {summary}
        </p>
      )}

      {/* Title Odds comparison — always visible when available */}
      {showTitleComparison && (
        <TitleComparison
          homeChamp={homeChamp}
          awayChamp={awayChamp}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          homeTeamColor={hColor}
          awayTeamColor={aColor}
        />
      )}

      {/* Team detail sections */}
      {hasSummary ? (
        <>
          <button
            onClick={() => setDetailsExpanded(!detailsExpanded)}
            className="flex items-center gap-1.5 text-xs text-blue-500 hover:text-blue-400 font-medium transition-colors mb-3"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              className={`transition-transform duration-200 ${
                detailsExpanded ? "rotate-90" : ""
              }`}
            >
              <path
                d="M4 2L8 6L4 10"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
                strokeLinecap="round"
              />
            </svg>
            {detailsExpanded
              ? "Hide details"
              : `See all ${data.total_count} futures`}
          </button>
          {detailsExpanded && teamDetails}
        </>
      ) : (
        teamDetails
      )}
    </div>
  );
}
