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
  /\bleader\b/i,            // "NBA Rebounds Per Game Leader"
  /\bper\s+game\b/i,        // "Points Per Game"
  /\bclutch\b/i,            // "Clutch Player of the Year"
  /\bfinals\s+mvp\b/i,      // "Finals MVP"
  /\b[ew]cf\s+mvp\b/i,      // "WCF MVP", "ECF MVP"
  /\bmost\s+improved\b/i,   // "Most Improved Player"
  /\bsixth\s+man\b/i,       // "Sixth Man"
  /\b6th\s+man\b/i,         // "6th Man"
  /\ball[- ]?star\s+mvp\b/i, // "All-Star MVP"
  /\bscoring\s+(leader|title|champion)/i, // "Scoring Leader"
  /\bhome\s+run\s+(leader|king)/i,        // "Home Run Leader"
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

/**
 * Player headshot component — uses direct headshot URL, ESPN ID, or Wikipedia fallback.
 * Priority: 1. Direct headshot URL  2. ESPN via espn_id  3. Wikipedia  4. Initials
 */
function PlayerHeadshot({
  name,
  matchedPlayer,
  sportKey,
  teamColor,
  size = 48,
}: {
  name: string;
  matchedPlayer?: RelatedFuture["matched_player"];
  sportKey?: string;
  teamColor: string;
  size?: number;
}) {
  // 1. Direct headshot URL from roster data (most reliable)
  if (matchedPlayer?.headshot) {
    return (
      <img
        src={matchedPlayer.headshot}
        alt={name}
        width={size}
        height={size}
        loading="lazy"
        className="rounded-full object-cover flex-shrink-0"
        style={{ width: size, height: size }}
        onError={(e) => {
          // On error, hide the image and show initials
          (e.target as HTMLImageElement).style.display = "none";
          const fallback = (e.target as HTMLImageElement).nextElementSibling;
          if (fallback) (fallback as HTMLElement).style.display = "flex";
        }}
      />
    );
  }

  // 2. ESPN headshot via espn_id
  if (matchedPlayer?.espn_id) {
    return (
      <EntityImage
        type="player"
        name={name}
        espnId={matchedPlayer.espn_id}
        sport={sportKey}
        size={size}
        fallbackColor={teamColor}
      />
    );
  }

  // 3. Wikipedia fallback
  return (
    <EntityImage
      type="wikipedia"
      name={name}
      size={size}
      fallbackColor={teamColor}
    />
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
        <div className="min-w-0 flex-1">
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
  if (/\bsixth\s+man\b|\b6th\s+man\b/i.test(cleaned)) return "6th Man";
  if (/\bcy\s*young/i.test(cleaned)) return "Cy Young";
  if (/\bgolden\s+boot/i.test(cleaned)) return "Golden Boot";
  if (/\bgolden\s+glove/i.test(cleaned)) return "Golden Glove";
  if (/\bballon/i.test(cleaned)) return "Ballon d'Or";
  if (/\bheisman/i.test(cleaned)) return "Heisman";
  if (/\bcoach\s+of\s+the\s+year/i.test(cleaned)) return "Coach of the Year";
  if (/rebounds?\s*per\s*game\s*leader/i.test(cleaned)) return "Rebounds Leader";
  if (/assists?\s*per\s*game\s*leader/i.test(cleaned)) return "Assists Leader";
  if (/points?\s*per\s*game\s*leader/i.test(cleaned)) return "Scoring Leader";
  if (/\bscoring\s+(leader|title|champion)/i.test(cleaned)) return "Scoring Leader";
  if (/\bhome\s+run\s+(leader|king)/i.test(cleaned)) return "HR Leader";
  if (/\bper\s+game\s+leader/i.test(cleaned)) {
    // Extract the stat name: "NBA Rebounds Per Game Leader" → "Rebounds Leader"
    const statMatch = cleaned.match(/(\w+)\s+per\s+game\s+leader/i);
    if (statMatch) return `${statMatch[1]} Leader`;
    return "Per Game Leader";
  }
  if (/\bleader\b/i.test(cleaned)) {
    // "NBA Steals Leader" → "Steals Leader"
    const statMatch = cleaned.match(/(\w+)\s+leader/i);
    if (statMatch && !/nba|nfl|nhl|mlb|mls/i.test(statMatch[1])) {
      return `${statMatch[1]} Leader`;
    }
  }
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
      {/* Player headshot — 48px, tries headshot URL → ESPN → Wikipedia → initials */}
      <PlayerHeadshot
        name={future.outcome_name}
        matchedPlayer={future.matched_player}
        sportKey={sportKey}
        teamColor={teamColor}
        size={48}
      />

      <div className="min-w-0 flex-1">
        {/* Player name — primary, large */}
        <div className="text-[15px] font-bold text-text-primary leading-tight">
          {future.outcome_name}
        </div>
        {/* Award label — secondary, NO truncation */}
        <div className="flex items-center gap-1 mt-0.5">
          <span className="text-[10px]">⭐</span>
          <span className="text-[11px] text-text-muted font-medium leading-snug">
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

/**
 * Check if a resolution_date is in the past.
 */
function isPastDate(dateStr: string | null): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  // Set to start of today for day-level comparison
  now.setHours(0, 0, 0, 0);
  return d < now;
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
  // 1. Remove resolved/illiquid markets (0% or 100%) AND past games
  const meaningful = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return false;
    if (p <= 0.02 || p >= 0.98) return false; // effectively 0% or 100%
    // Filter out past games
    if (f.resolution_date && isPastDate(f.resolution_date)) return false;
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

  // Sort: soonest games first (by resolution_date), then by probability
  const sorted = deduped.sort((a, b) => {
    // Games with dates come first, sorted chronologically
    if (a.resolution_date && b.resolution_date) {
      return new Date(a.resolution_date).getTime() - new Date(b.resolution_date).getTime();
    }
    if (a.resolution_date && !b.resolution_date) return -1;
    if (!a.resolution_date && b.resolution_date) return 1;
    return (b.probability || 0) - (a.probability || 0);
  });

  if (sorted.length === 0) return null;

  const COLLAPSED_COUNT = 6;
  const visible = expanded ? sorted : sorted.slice(0, COLLAPSED_COUNT);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px]">📈</span>
        <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
          Upcoming games
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
              <div className="relative">
                {/* Date first — context for the matchup */}
                {f.resolution_date && (
                  <div className="text-[9px] text-text-muted/70 font-medium mb-0.5">
                    {new Date(f.resolution_date).toLocaleDateString("en-US", {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    })}
                  </div>
                )}
                <div className="flex items-center justify-between gap-1">
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
 * Parse a player stat outcome like "Derrick White: 12+" into parts.
 * Also handles "Over 218.5" / "Under 48.5" for team-level totals.
 */
function parseStatOutcome(outcomeName: string): {
  playerName: string | null;
  line: string | null;
  isTeamTotal: boolean;
} {
  // Team-level: "Over 218.5" or "Under 48.5"
  if (/^(over|under)\b/i.test(outcomeName.trim())) {
    const lineMatch = outcomeName.match(/([\d.]+\+?)/);
    return {
      playerName: null,
      line: lineMatch ? lineMatch[1] : outcomeName.replace(/^(over|under)\s*/i, "").trim(),
      isTeamTotal: true,
    };
  }
  // Player-level: "Derrick White: 12+" or "Jaylen Brown: 4+"
  const colonIdx = outcomeName.indexOf(":");
  if (colonIdx > 0) {
    return {
      playerName: outcomeName.slice(0, colonIdx).trim(),
      line: outcomeName.slice(colonIdx + 1).trim(),
      isTeamTotal: false,
    };
  }
  // Fallback: just a name or unknown
  return { playerName: outcomeName, line: null, isTeamTotal: false };
}

/** Parsed stat row for display */
interface StatRow {
  playerName: string | null;
  line: string | null;
  probability: number;
  marketId: number;
  outcomeName: string;
  isTeamTotal: boolean;
  matchedPlayer?: RelatedFuture["matched_player"];
}

/**
 * Semi-circular gauge for stat prop probability.
 * Shows a colored arc from 0-100% with the percentage in the center.
 */
function StatGauge({
  probability,
  teamColor,
  size = 52,
}: {
  probability: number;
  teamColor: string;
  size?: number;
}) {
  const pct = Math.round(probability * 100);
  const radius = (size - 6) / 2;
  const circumference = Math.PI * radius; // half circle
  const offset = circumference * (1 - probability);

  return (
    <div className="flex flex-col items-center" style={{ width: size, height: size * 0.65 }}>
      <svg
        width={size}
        height={size * 0.55}
        viewBox={`0 0 ${size} ${size * 0.55}`}
        className="overflow-visible"
      >
        {/* Background arc */}
        <path
          d={`M 3 ${size * 0.52} A ${radius} ${radius} 0 0 1 ${size - 3} ${size * 0.52}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          className="text-surface-elevated"
          strokeLinecap="round"
        />
        {/* Colored arc */}
        <path
          d={`M 3 ${size * 0.52} A ${radius} ${radius} 0 0 1 ${size - 3} ${size * 0.52}`}
          fill="none"
          stroke={teamColor}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={`${offset}`}
          style={{ opacity: pct >= 50 ? 0.85 : 0.5, transition: "stroke-dashoffset 0.5s ease" }}
        />
      </svg>
      <span
        className="text-[13px] font-bold tabular-nums -mt-1.5"
        style={{ color: pct >= 50 ? teamColor : "var(--text-muted)" }}
      >
        {pct}%
      </span>
    </div>
  );
}

// ─── STAT PROPS: Player stat cards with gauges ───
function StatPropsSection({
  futures,
  teamColor,
  sportKey,
}: {
  futures: RelatedFuture[];
  teamColor: string;
  sportKey?: string;
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

  // Group by stat category, then build display rows
  const groups = new Map<string, StatRow[]>();
  for (const f of meaningful) {
    const cat = extractStatCategory(f.market_name);
    const parsed = parseStatOutcome(f.outcome_name);
    const row: StatRow = {
      playerName: parsed.playerName,
      line: parsed.line,
      probability: f.probability || 0,
      marketId: f.market_id,
      outcomeName: f.outcome_name,
      isTeamTotal: parsed.isTeamTotal,
      matchedPlayer: f.matched_player,
    };
    const existing = groups.get(cat) || [];
    existing.push(row);
    groups.set(cat, existing);
  }

  // Sort groups by size, rows within by probability descending
  const sortedGroups: Array<{
    category: string;
    config: { emoji: string; label: string };
    rows: StatRow[];
  }> = [];
  groups.forEach((rows, cat) => {
    sortedGroups.push({
      category: cat,
      config: getStatConfig(cat),
      rows: rows.sort((a, b) => b.probability - a.probability),
    });
  });
  sortedGroups.sort((a, b) => b.rows.length - a.rows.length);

  const COLLAPSED_GROUPS = 3;
  const ROWS_PER_GROUP = 4;
  const visibleGroups = expanded
    ? sortedGroups
    : sortedGroups.slice(0, COLLAPSED_GROUPS);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px]">📊</span>
        <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">
          Player stats
        </span>
      </div>

      <div className="space-y-4">
        {visibleGroups.map(({ category, config, rows }) => (
          <div key={category}>
            {/* Category header */}
            <div className="flex items-center gap-1.5 mb-2">
              <span className="text-sm">{config.emoji}</span>
              <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
                {config.label}
              </span>
              <span className="text-[10px] text-text-muted/50">
                ({rows.length})
              </span>
            </div>

            {/* Player stat cards — horizontal scroll on mobile */}
            <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-hide">
              {rows.slice(0, ROWS_PER_GROUP).map((row) => (
                <Link
                  key={`${row.marketId}-${row.outcomeName}`}
                  href={`/futures/${row.marketId}`}
                  className="flex-shrink-0 rounded-xl p-2.5 group transition-all duration-200 hover:scale-[1.02] text-center"
                  style={{
                    background: `linear-gradient(135deg, ${teamColor}08, transparent)`,
                    border: `1px solid ${teamColor}15`,
                    width: 110,
                  }}
                >
                  {/* Player headshot — small */}
                  {row.playerName && (
                    <div className="flex justify-center mb-1.5">
                      <PlayerHeadshot
                        name={row.playerName}
                        matchedPlayer={row.matchedPlayer}
                        sportKey={sportKey}
                        teamColor={teamColor}
                        size={36}
                      />
                    </div>
                  )}

                  {/* Player name */}
                  <div className="text-[11px] font-semibold text-text-primary truncate leading-tight">
                    {row.playerName || (row.isTeamTotal ? "Team" : "—")}
                  </div>

                  {/* Stat line — hero element */}
                  {row.line && (
                    <div
                      className="text-lg font-black tabular-nums mt-0.5 leading-none"
                      style={{ color: teamColor }}
                    >
                      {row.line}
                    </div>
                  )}

                  {/* Gauge */}
                  <div className="flex justify-center mt-1">
                    <StatGauge
                      probability={row.probability}
                      teamColor={teamColor}
                      size={48}
                    />
                  </div>
                </Link>
              ))}
            </div>
            {rows.length > ROWS_PER_GROUP && (
              <span className="text-[10px] text-text-muted/50 mt-1 inline-block">
                +{rows.length - ROWS_PER_GROUP} more
              </span>
            )}
          </div>
        ))}
      </div>

      {sortedGroups.length > COLLAPSED_GROUPS && (
        <button
          onClick={(e) => {
            e.preventDefault();
            setExpanded(!expanded);
          }}
          className="text-[11px] text-blue-500 hover:text-blue-400 font-medium mt-2 transition-colors"
        >
          {expanded
            ? "Show less"
            : `+${sortedGroups.length - COLLAPSED_GROUPS} more stats`}
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

/**
 * Deduplicate award futures by player name.
 * When a player appears in multiple award markets (e.g., MVP on Polymarket AND Kalshi),
 * keep only the one with the highest probability to avoid cluttering the UI.
 */
function deduplicateAwards(futures: RelatedFuture[]): RelatedFuture[] {
  const playerMap = new Map<string, RelatedFuture>();
  for (const f of futures) {
    const key = f.outcome_name.toLowerCase();
    const existing = playerMap.get(key);
    if (
      !existing ||
      (f.probability || 0) > (existing.probability || 0)
    ) {
      playerMap.set(key, f);
    }
  }
  return Array.from(playerMap.values());
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
  const rawAwards = futures.filter((f) => effectiveTier(f) === 3);
  const awards = deduplicateAwards(rawAwards);
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

        {/* Awards — player-centric rows with headshots (deduplicated) */}
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

        {/* Stat props — player stat cards with gauges */}
        <StatPropsSection futures={statProps} teamColor={teamColor} sportKey={sportKey} />
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
 * - Award futures as player-centric rows with headshots (deduplicated)
 * - Game markets as dense 2-column grid cells (past games filtered out)
 * - Stat props as player cards with semi-circular gauges
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
