"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import type { RelatedFuture, RelatedFuturesResponse, TeamProgressionResponse } from "@/lib/types";
import { fetchRelatedFutures, formatProbability } from "@/lib/api";
import EntityImage from "./EntityImage";

interface TeamStandings {
  wins?: number;
  losses?: number;
  draws?: number;
  ties?: number;
  conf_rank?: number;
  conference?: string;
  div_rank?: number;
  division?: string;
}

interface RelatedFuturesProps {
  eventId: number;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  homeTeamLogo?: string;
  awayTeamLogo?: string;
  sportKey?: string;
  eventStatus?: string;
  homeStandings?: TeamStandings;
  awayStandings?: TeamStandings;
  /** When true, game-level stat props are already shown by TotalPointsSpectrum/PlayerPropsGrid above — suppress duplicate display here */
  hasGameMarkets?: boolean;
  /** Grid-based team progression data — always available for both teams in team sports */
  teamProgression?: TeamProgressionResponse;
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
  "double doubles": { emoji: "✌️", label: "Double-Doubles" },
  "double double": { emoji: "✌️", label: "Double-Doubles" },
  doubledoubles: { emoji: "✌️", label: "Double-Doubles" },
  "triple doubles": { emoji: "🔥", label: "Triple-Doubles" },
  "triple double": { emoji: "🔥", label: "Triple-Doubles" },
  tripledoubles: { emoji: "🔥", label: "Triple-Doubles" },
};

/** Map backend display_category to tier number for rendering */
const CATEGORY_TO_TIER: Record<string, number> = {
  playoff_path: 1,
  conference: 2,
  award: 3,
  season_stat: 4,
  game_prop: 6,      // stat props get special display
  trade: 4,
  novelty: 4,
  other: 5,
};

/**
 * Determine the effective display tier for a future.
 * Uses backend display_category (always provided by the API).
 * Falls back to market_tier for any edge cases.
 *
 * Returns 1-5 for standard tiers, 6 for stat props (special display).
 */
function effectiveTier(f: RelatedFuture): number {
  if (f.display_category && CATEGORY_TO_TIER[f.display_category] !== undefined) {
    return CATEGORY_TO_TIER[f.display_category];
  }
  if (f.market_tier && f.market_tier >= 1 && f.market_tier <= 5) {
    return f.market_tier;
  }
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

/** Normalize a name for deduplication: lowercase, trim, collapse whitespace */
function normalizeName(name: string): string {
  return name.toLowerCase().trim().replace(/\s+/g, " ");
}

/**
 * Match a stat prop player name to an ESPN box score entry.
 * Tries exact normalized match first, then last-name match for abbreviated names.
 */
function matchPlayerToBoxScore(
  playerName: string,
  boxScore: Record<string, Record<string, number>>
): Record<string, number> | null {
  const norm = normalizeName(playerName);
  // Exact match
  for (const [name, stats] of Object.entries(boxScore)) {
    if (normalizeName(name) === norm) return stats;
  }
  // Last name match (handles "C. Johnson" vs "Cameron Johnson")
  const lastName = norm.split(" ").pop() || "";
  if (lastName.length >= 4) {
    const matches = Object.entries(boxScore).filter(
      ([name]) => normalizeName(name).endsWith(lastName)
    );
    if (matches.length === 1) return matches[0][1];
  }
  return null;
}

/** Extract numeric threshold from line string: "12+" → 12, "O/U 3.5" → 3.5 */
function parseThreshold(line: string | null): number | null {
  if (!line) return null;
  const m = line.match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
}

/** Map stat category from market name to box score key */
const CATEGORY_TO_STAT: Record<string, string> = {
  points: "points", rebounds: "rebounds", assists: "assists",
  steals: "steals", blocks: "blocks", turnovers: "turnovers",
  "three pointers": "three pointers", "3-pointers": "three pointers",
  threepointers: "three pointers",
  "double doubles": "double doubles", "double double": "double doubles",
  doubledoubles: "double doubles",
  "triple doubles": "triple doubles", "triple double": "triple doubles",
  tripledoubles: "triple doubles",
  strikeouts: "strikeouts", hits: "hits", "home runs": "home runs",
  "passing yards": "passing yards", "rushing yards": "rushing yards",
  "receiving yards": "receiving yards", touchdowns: "touchdowns",
  goals: "goals", saves: "saves", sacks: "sacks",
};

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

/** Multi-source badge — shows when multiple sources agree on a market */
function MultiSourceBadge({ sources }: { sources: string[] }) {
  if (sources.length <= 1) return null;
  return (
    <span className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
      {sources.length} sources
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
          // On error, hide the image — initials already render as sibling
          (e.target as HTMLImageElement).style.display = "none";
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
  const tier = TIER_CONFIG[tierNum] || TIER_CONFIG[4];

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
            {future.clean_label || cleanMarketName(future.market_name)}
          </div>
        </div>
        {future.all_sources && future.all_sources.length > 1 ? (
          <MultiSourceBadge sources={future.all_sources} />
        ) : (
          <SourceBadge source={future.source} />
        )}
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
 * Uses backend clean_label when available, falls back to regex extraction.
 * e.g., "NBA Most Valuable Player" → "MVP"
 * e.g., "NBA Rookie of the Year" → "Rookie of the Year"
 */
function shortAwardLabel(marketName: string, cleanLabel?: string): string {
  // Use backend clean_label if available — already normalized
  if (cleanLabel && cleanLabel !== marketName) {
    return cleanLabel;
  }
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
  if (/\bcover\s+of\b.*\b2k\b/i.test(cleaned)) return "NBA 2K Cover";
  if (/\b2k\b.*\bcover\b/i.test(cleaned)) return "NBA 2K Cover";
  if (/\bper\s+game\s+leader/i.test(cleaned)) {
    const statMatch = cleaned.match(/(\w+)\s+per\s+game\s+leader/i);
    if (statMatch) return `${statMatch[1]} Leader`;
    return "Per Game Leader";
  }
  if (/\bleader\b/i.test(cleaned)) {
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
  sourceCount,
}: {
  future: RelatedFuture;
  teamColor: string;
  sportKey?: string;
  sourceCount?: number;
}) {
  const awardLabel = shortAwardLabel(future.market_name, future.clean_label);

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
        {/* Award label + source info — secondary, NO truncation */}
        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span className="text-[10px]">⭐</span>
          <span className="text-[11px] text-text-muted font-medium leading-snug">
            {awardLabel}
          </span>
          {sourceCount && sourceCount > 1 && (
            <span className="text-[9px] text-purple-400/80 font-medium">
              ({sourceCount} sources)
            </span>
          )}
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
 * Handles: "Team A vs. Team B", "Team A – Team B", "Team A at Team B"
 */
function extractOpponent(marketName: string, teamName: string): string {
  const teamWords = teamName.split(" ");
  const shortName = teamWords[teamWords.length - 1] || teamName;

  // Escape regex special chars in team names
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  let result = marketName
    .replace(/ - More Markets$/i, "")
    .replace(/\s*-\s*Moneyline$/i, "");

  // Try all separator patterns: "vs.", "vs", "–", "at"
  for (const name of [teamName, shortName]) {
    const escaped = esc(name);
    // "Team vs. Opponent" or "Team vs Opponent"
    result = result.replace(new RegExp(`^${escaped}\\s+vs\\.?\\s+`, "i"), "");
    result = result.replace(new RegExp(`\\s+vs\\.?\\s+${escaped}$`, "i"), "");
    // "Team – Opponent" (en-dash)
    result = result.replace(new RegExp(`^${escaped}\\s+–\\s+`, "i"), "");
    result = result.replace(new RegExp(`\\s+–\\s+${escaped}$`, "i"), "");
    // "Team at Opponent"
    result = result.replace(new RegExp(`^${escaped}\\s+at\\s+`, "i"), "");
    result = result.replace(new RegExp(`\\s+at\\s+${escaped}$`, "i"), "");
  }

  return result.trim();
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
  const teamShort = teamName.split(" ").pop()?.toLowerCase() || "";
  const teamFull = teamName.toLowerCase();

  // 1. Remove resolved/illiquid, past games, and cross-sport false positives
  const meaningful = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return false;
    if (p <= 0.02 || p >= 0.98) return false; // effectively 0% or 100%
    // Filter out past games
    if (f.resolution_date && isPastDate(f.resolution_date)) return false;
    // Verify market name actually contains this team (catches cross-sport leaks)
    const mLower = (f.market_name || "").toLowerCase();
    if (teamShort.length >= 4 && !mLower.includes(teamShort) && !mLower.includes(teamFull)) {
      return false;
    }
    return true;
  });

  // 2. Deduplicate by opponent name — keep the one with highest relevance_score
  const opponentMap = new Map<string, RelatedFuture>();
  for (const f of meaningful) {
    const opponent = normalizeName(extractOpponent(f.market_name, teamName));
    // Skip entries where opponent extraction failed (opponent = full market name)
    if (opponent.length > 40) continue;
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

// ─── STAT PROPS: Player stat cards with gauges (live/scheduled) or settled results (completed) ───
function StatPropsSection({
  futures,
  teamColor,
  sportKey,
  isFinished,
  isLive,
  boxScore,
}: {
  futures: RelatedFuture[];
  teamColor: string;
  sportKey?: string;
  isFinished?: boolean;
  isLive?: boolean;
  boxScore?: Record<string, Record<string, number>> | null;
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

  // Deduplicate within each group: per player, keep highest line
  // (e.g., "Pritchard: 2+" and "Pritchard: 1+" → keep "Pritchard: 2+" since it's the more interesting bet)
  const dedupedGroups = new Map<string, StatRow[]>();
  groups.forEach((rows, cat) => {
    const playerBest = new Map<string, StatRow>();
    for (const row of rows) {
      const playerKey = normalizeName(row.playerName || row.outcomeName);
      const existing = playerBest.get(playerKey);
      if (!existing) {
        playerBest.set(playerKey, row);
      } else {
        // Keep the row with the more interesting (lower probability) line
        // or the higher line number if probabilities are similar
        const existingLine = parseFloat(existing.line || "0");
        const newLine = parseFloat(row.line || "0");
        if (newLine > existingLine) {
          playerBest.set(playerKey, row);
        }
      }
    }
    dedupedGroups.set(cat, Array.from(playerBest.values()));
  });

  // Sort groups by size, rows within by probability descending
  const sortedGroups: Array<{
    category: string;
    config: { emoji: string; label: string };
    rows: StatRow[];
  }> = [];
  dedupedGroups.forEach((rows, cat) => {
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
          {isFinished && boxScore ? "Game props — results" : isLive && boxScore ? "Game props — live" : "Game props"}
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
              {rows.slice(0, ROWS_PER_GROUP).map((row) => {
                // For completed events with box score: show settled card
                const statKey = CATEGORY_TO_STAT[category] || category;
                const playerStats = ((isFinished || isLive) && boxScore && row.playerName)
                  ? matchPlayerToBoxScore(row.playerName, boxScore)
                  : null;
                const actualValue = playerStats ? playerStats[statKey] : null;
                const threshold = parseThreshold(row.line);
                const hasSettledData = isFinished && actualValue !== null && threshold !== null;
                const hasLiveData = isLive && actualValue !== null && threshold !== null;

                // Determine OVER/UNDER/PUSH result
                let result: "over" | "under" | "push" | null = null;
                if (hasSettledData) {
                  if (actualValue! > threshold!) result = "over";
                  else if (actualValue! < threshold!) result = "under";
                  else result = "push";
                }

                // Live progress toward the line
                const liveProgress = hasLiveData ? Math.min(1, (actualValue as number) / (threshold as number)) : 0;
                const livePacing = hasLiveData && (actualValue as number) >= (threshold as number);

                return (
                  <Link
                    key={`${row.marketId}-${row.outcomeName}`}
                    href={`/futures/${row.marketId}`}
                    className="flex-shrink-0 rounded-xl p-2.5 group transition-all duration-200 hover:scale-[1.02] text-center"
                    style={{
                      background: hasSettledData
                        ? result === "over"
                          ? `linear-gradient(135deg, #22c55e08, transparent)`
                          : result === "under"
                          ? `linear-gradient(135deg, #ef444408, transparent)`
                          : `linear-gradient(135deg, ${teamColor}08, transparent)`
                        : hasLiveData
                          ? `linear-gradient(135deg, ${teamColor}0a, transparent)`
                          : `linear-gradient(135deg, ${teamColor}08, transparent)`,
                      border: hasSettledData
                        ? result === "over"
                          ? `1px solid #22c55e25`
                          : result === "under"
                          ? `1px solid #ef444425`
                          : `1px solid ${teamColor}15`
                        : hasLiveData
                          ? `1px solid ${teamColor}25`
                          : `1px solid ${teamColor}15`,
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

                    {hasSettledData ? (
                      <>
                        {/* Settled: line, actual value, result */}
                        <div className="text-[10px] text-text-muted mt-1">
                          Line: {row.line}
                        </div>
                        <div
                          className="text-xl font-black tabular-nums mt-0.5 leading-none"
                          style={{ color: teamColor }}
                        >
                          {actualValue}
                        </div>
                        <div className={`text-[10px] font-bold mt-1 ${
                          result === "over"
                            ? "text-emerald-500"
                            : result === "under"
                            ? "text-red-400"
                            : "text-text-muted"
                        }`}>
                          {result === "over" ? "OVER" : result === "under" ? "UNDER" : "PUSH"}
                        </div>
                      </>
                    ) : hasLiveData ? (
                      <>
                        {/* Live: line + actual value + progress bar */}
                        <div className="text-[10px] text-text-muted mt-1">
                          Line: {row.line}
                        </div>
                        <div
                          className="text-xl font-black tabular-nums mt-0.5 leading-none"
                          style={{ color: teamColor }}
                        >
                          {actualValue}
                        </div>
                        {/* Progress bar toward the line */}
                        <div className="mt-1.5 w-full h-1.5 rounded-full bg-graphite/10 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${Math.round(liveProgress * 100)}%`,
                              backgroundColor: livePacing ? "#22c55e" : teamColor,
                              opacity: livePacing ? 0.8 : 0.5,
                            }}
                          />
                        </div>
                        <div className="text-[9px] text-text-muted/50 mt-0.5">
                          {livePacing ? "On pace" : `${Math.round(liveProgress * 100)}%`}
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Scheduled: stat line + gauge */}
                        {row.line && (
                          <div
                            className="text-lg font-black tabular-nums mt-0.5 leading-none"
                            style={{ color: teamColor }}
                          >
                            {row.line}
                          </div>
                        )}
                        <div className="flex justify-center mt-1">
                          <StatGauge
                            probability={row.probability}
                            teamColor={teamColor}
                            size={48}
                          />
                        </div>
                      </>
                    )}
                  </Link>
                );
              })}
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
 * Deduplicate award futures by player name + award type combination.
 * Same player in the same award type from different sources → merged (keep highest probability).
 * Same player in different award types → kept separate.
 * Also filters out near-0% entries (< 1%) and near-100% entries.
 */
function deduplicateAwards(futures: RelatedFuture[]): { future: RelatedFuture; sourceCount: number }[] {
  // First filter out noise: very low or very high probability
  const filtered = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return false;
    if (p < 0.01 || p > 0.99) return false;
    return true;
  });

  // Deduplicate by normalized player name + award label combo
  const dedupMap = new Map<string, { future: RelatedFuture; sources: Set<string> }>();
  for (const f of filtered) {
    const playerKey = normalizeName(f.outcome_name);
    const awardKey = (f.merge_group || shortAwardLabel(f.market_name, f.clean_label)).toLowerCase();
    const key = `${playerKey}::${awardKey}`;
    const existing = dedupMap.get(key);
    if (!existing) {
      dedupMap.set(key, { future: f, sources: new Set([f.source || "unknown"]) });
    } else {
      existing.sources.add(f.source || "unknown");
      // Keep the one with higher probability
      if ((f.probability || 0) > (existing.future.probability || 0)) {
        existing.future = f;
      }
    }
  }

  return Array.from(dedupMap.values()).map(({ future, sources }) => ({
    future,
    sourceCount: sources.size,
  }));
}


// ─── V5 SECTION DIVIDER ───
function SectionDivider({ level, label, count }: { level: number; label: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 mt-5 mb-3">
      <span className="text-[9px] font-bold text-white bg-gray-400 px-1.5 py-0.5 rounded text-center min-w-[18px]">
        {level}
      </span>
      <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-text-muted">
        {label}
      </span>
      <div className="flex-1 h-px bg-surface-border" />
      {count !== undefined && count > 0 && (
        <span className="text-[10px] text-text-muted/50 font-medium">{count} items</span>
      )}
    </div>
  );
}

// ─── V5 PLAYOFF PATH (side-by-side progression cards) ───
// Playoff stage classification is now computed server-side in
// market_label_normalization.py:compute_playoff_stage() and returned
// as playoff_stage, playoff_stage_type, and stage_order fields.
// No client-side regex classification needed.

interface PlayoffStage {
  name: string;
  probability: number;
  order: number;
  marketId: number;
  isDone: boolean;
}

function buildPlayoffStages(futures: RelatedFuture[]): PlayoffStage[] {
  const stages: PlayoffStage[] = [];
  for (const f of futures) {
    if (f.probability === null || f.probability === undefined) continue;
    // Use server-computed playoff stage fields
    const name = f.playoff_stage || f.clean_label || cleanMarketName(f.market_name);
    const order = f.stage_order ?? 3;
    stages.push({
      name,
      probability: f.probability,
      order,
      marketId: f.market_id,
      isDone: f.probability >= 0.99,
    });
  }
  stages.sort((a, b) => a.order - b.order);
  const deduped = new Map<string, PlayoffStage>();
  for (const s of stages) {
    const existing = deduped.get(s.name);
    if (!existing || s.probability > existing.probability) {
      deduped.set(s.name, s);
    }
  }
  return Array.from(deduped.values()).sort((a, b) => a.order - b.order);
}

function PlayoffPathPair({
  homeFutures,
  awayFutures,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
}: {
  homeFutures: RelatedFuture[];
  awayFutures: RelatedFuture[];
  homeTeam: string;
  awayTeam: string;
  homeColor: string;
  awayColor: string;
  homeLogo?: string;
  awayLogo?: string;
}) {
  const homeStages = buildPlayoffStages(homeFutures);
  const awayStages = buildPlayoffStages(awayFutures);

  if (homeStages.length === 0 && awayStages.length === 0) return null;

  function renderCard(stages: PlayoffStage[], shortName: string, color: string, logo?: string) {
    if (stages.length === 0) return <div />;
    return (
      <div
        className="rounded-xl border overflow-hidden bg-surface-card"
        style={{ borderLeftWidth: 3, borderLeftColor: color }}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          {logo ? (
            <img src={logo} alt="" className="w-7 h-7 object-contain" />
          ) : (
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white font-extrabold text-[10px]"
              style={{ backgroundColor: color }}
            >
              {shortName.slice(0, 3).toUpperCase()}
            </div>
          )}
          <span className="text-[13px] font-bold flex-1">{shortName}</span>
          <span className="text-[9px] font-semibold text-text-muted tracking-wide">PLAYOFFS</span>
        </div>
        <div className="px-3 pb-2.5">
          {stages.map((stage) => {
            const pct = Math.round(stage.probability * 100);
            return (
              <Link
                key={stage.name}
                href={`/futures/${stage.marketId}`}
                className="flex items-center gap-1.5 py-1 group"
              >
                <div className={`w-[7px] h-[7px] rounded-full shrink-0 ${
                  stage.isDone ? "bg-emerald-500" : pct >= 30 ? "bg-amber-500" : "bg-gray-300"
                }`} />
                <span className="text-[11px] text-text-secondary flex-1">{stage.name}</span>
                <span
                  className={`text-[11px] font-bold font-mono ${
                    stage.isDone ? "text-emerald-500" : ""
                  }`}
                  style={stage.isDone ? undefined : { color: pct >= 30 ? undefined : "var(--text-muted)" }}
                >
                  {stage.isDone ? "done" : `${pct}%`}
                </span>
              </Link>
            );
          })}
        </div>
        {/* Source dots */}
        <div className="flex items-center gap-1 px-3 pb-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          <span className="text-[8px] text-text-muted ml-0.5">3 sources</span>
        </div>
      </div>
    );
  }

  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  return (
    <div className="grid grid-cols-2 gap-2">
      {renderCard(awayStages, awayShort, awayColor, awayLogo)}
      {renderCard(homeStages, homeShort, homeColor, homeLogo)}
    </div>
  );
}

/** Grid-based playoff path — always available for both teams from championship grid data */
function GridPlayoffPathPair({
  teamProgression,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
}: {
  teamProgression: TeamProgressionResponse;
  homeTeam: string;
  awayTeam: string;
  homeColor: string;
  awayColor: string;
  homeLogo?: string;
  awayLogo?: string;
}) {
  const { home_team, away_team, grid_url } = teamProgression;

  if (!home_team && !away_team) return null;

  function renderCard(
    team: NonNullable<TeamProgressionResponse["home_team"]>,
    color: string,
    logo?: string,
  ) {
    const stages = team.stages.filter((s) => s.probability !== null);
    if (stages.length === 0) return <div />;
    return (
      <div
        className="rounded-xl border overflow-hidden bg-surface-card"
        style={{ borderLeftWidth: 3, borderLeftColor: color }}
      >
        <div className="flex items-center gap-2 px-3 py-2.5">
          {(logo || team.logo_url) ? (
            <img src={logo || team.logo_url!} alt="" className="w-7 h-7 object-contain" />
          ) : (
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center text-white font-extrabold text-[10px]"
              style={{ backgroundColor: color }}
            >
              {team.short_name.slice(0, 3).toUpperCase()}
            </div>
          )}
          <span className="text-[13px] font-bold flex-1">{team.short_name}</span>
          {team.record && (
            <span className="text-[9px] font-medium text-text-muted">{team.record}</span>
          )}
        </div>
        <div className="px-3 pb-2.5">
          {stages.map((stage) => {
            const pct = Math.round(stage.probability! * 100);
            return (
              <div
                key={stage.key}
                className="flex items-center gap-1.5 py-1"
              >
                <div className={`w-[7px] h-[7px] rounded-full shrink-0 ${
                  pct >= 95 ? "bg-emerald-500" : pct >= 30 ? "bg-amber-500" : "bg-gray-300"
                }`} />
                <span className="text-[11px] text-text-secondary flex-1">{stage.label}</span>
                <span
                  className={`text-[11px] font-bold font-mono ${
                    pct >= 95 ? "text-emerald-500" : ""
                  }`}
                  style={pct >= 95 ? undefined : { color: pct >= 30 ? undefined : "var(--text-muted)" }}
                >
                  {pct >= 95 ? "done" : `${pct}%`}
                </span>
                {stage.trend_24h !== null && stage.trend_24h !== 0 && (
                  <span className={`text-[9px] font-mono ${
                    stage.trend_24h > 0 ? "text-emerald-500" : "text-red-400"
                  }`}>
                    {stage.trend_24h > 0 ? "+" : ""}{Math.round(stage.trend_24h * 100)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
        {/* Source indicators */}
        {stages[0]?.sources && stages[0].sources.length > 0 && (
          <div className="flex items-center gap-1 px-3 pb-2">
            {stages[0].sources.map((s, i) => (
              <div key={i} className={`w-1.5 h-1.5 rounded-full ${
                s.source === "odds_api" ? "bg-emerald-500" :
                s.source === "kalshi" ? "bg-blue-500" :
                s.source === "polymarket" ? "bg-amber-500" : "bg-gray-400"
              }`} />
            ))}
            <span className="text-[8px] text-text-muted ml-0.5">
              {stages[0].sources.length} source{stages[0].sources.length !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {away_team ? renderCard(away_team, awayColor, awayLogo) : <div />}
      {home_team ? renderCard(home_team, homeColor, homeLogo) : <div />}
    </div>
  );
}

// ─── V5 SEASON STATS (compact side-by-side list) ───
function SeasonStatRow({ future, teamColor }: { future: RelatedFuture; teamColor: string }) {
  const prob = future.probability || 0;
  const label = future.clean_label || cleanMarketName(future.market_name);
  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="flex items-center gap-2 py-1.5 border-b border-surface-border/10 last:border-0 hover:bg-surface-elevated/30 transition-colors px-2 group"
    >
      <span className="text-[10px] text-text-secondary flex-1 truncate">{label}</span>
      <span
        className="text-[11px] font-bold font-mono shrink-0"
        style={{ color: prob >= 0.10 ? teamColor : "var(--text-muted)" }}
      >
        {formatProbability(future.probability)}
      </span>
      {future.rank && (
        <span className="text-[8px] text-text-muted font-medium shrink-0">#{future.rank}</span>
      )}
    </Link>
  );
}

// ── Games per season by sport ──
const SEASON_GAMES: Record<string, number> = {
  basketball_nba: 82,
  basketball_wnba: 40,
  basketball_ncaab: 33,
  americanfootball_nfl: 18,
  americanfootball_ncaaf: 14,
  baseball_mlb: 162,
  icehockey_nhl: 82,
  soccer_epl: 38,
  soccer_usa_mls: 34,
};

/** Parse threshold number from an outcome name like "Over 55.5" */
function parseWinTotalThreshold(outcomeName: string): number | null {
  const m = outcomeName.match(/(\d+(?:\.\d+)?)/);
  return m ? parseFloat(m[1]) : null;
}

interface WinTotalThreshold {
  value: number;
  probability: number;
  change24h: number | null;
  marketId: number;
}

// ─── V5 WIN TOTALS GAUGE ───
function WinTotalsGauge({
  teamName,
  teamColor,
  standings,
  thresholds,
  sportKey,
  logo,
}: {
  teamName: string;
  teamColor: string;
  standings?: TeamStandings;
  thresholds: WinTotalThreshold[];
  sportKey?: string;
  logo?: string;
}) {
  if (thresholds.length === 0) return null;

  const shortName = teamName.split(" ").pop() || teamName;
  const wins = standings?.wins;
  const losses = standings?.losses;
  const totalGames = sportKey ? SEASON_GAMES[sportKey] || 82 : 82;
  const gamesPlayed = wins != null && losses != null ? wins + losses : null;
  const gamesRemaining = gamesPlayed != null ? Math.max(0, totalGames - gamesPlayed) : null;

  // Sort thresholds
  const sorted = [...thresholds].sort((a, b) => a.value - b.value);

  // Find the "interesting line" — threshold closest to 50% probability
  const interestingLine = sorted.reduce((best, t) =>
    Math.abs(t.probability - 0.5) < Math.abs(best.probability - 0.5) ? t : best
  );

  // Gauge range
  const minThresh = sorted[0].value;
  const maxThresh = sorted[sorted.length - 1].value;
  const gaugeMin = Math.min(minThresh - 3, wins != null ? wins - 2 : minThresh - 3);
  const gaugeMax = maxThresh + 3;
  const gaugeRange = gaugeMax - gaugeMin;

  // Position helpers (0-100%)
  const pos = (val: number) => Math.max(0, Math.min(100, ((val - gaugeMin) / gaugeRange) * 100));

  const winsPos = wins != null ? pos(wins) : null;
  const interestingPos = pos(interestingLine.value);
  const interestingProb = Math.round(interestingLine.probability * 100);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-3 text-center">
      {/* Team name */}
      <div className="flex items-center justify-center gap-1.5 mb-2">
        {logo ? (
          <img src={logo} alt="" className="w-4 h-4 object-contain" />
        ) : (
          <div
            className="w-4 h-4 rounded flex items-center justify-center text-white text-[6px] font-extrabold"
            style={{ backgroundColor: teamColor }}
          >
            {shortName.slice(0, 3).toUpperCase()}
          </div>
        )}
        <span className="text-[10px] font-bold" style={{ color: teamColor }}>
          {teamName}
        </span>
      </div>

      {/* Gauge */}
      <div className="relative h-11 mb-1">
        {/* Track */}
        <div className="absolute left-0 right-0 top-[18px] h-2 rounded bg-surface-elevated" />
        {/* Fill to current wins */}
        {winsPos !== null && (
          <div
            className="absolute top-[18px] left-0 h-2 rounded"
            style={{
              width: `${winsPos}%`,
              background: `linear-gradient(90deg, ${teamColor}, ${teamColor}40)`,
            }}
          />
        )}
        {/* Current wins marker */}
        {winsPos !== null && wins != null && (
          <div
            className="absolute top-[8px] w-0.5 h-7 rounded-full"
            style={{ left: `${winsPos}%`, backgroundColor: teamColor }}
          >
            <div
              className="absolute top-0 left-1/2 -translate-x-1/2 text-[8px] font-bold whitespace-nowrap"
              style={{ color: teamColor, top: "-12px" }}
            >
              {wins}W
            </div>
          </div>
        )}
        {/* Interesting line marker */}
        <div
          className="absolute top-[12px] w-px h-5"
          style={{ left: `${interestingPos}%`, backgroundColor: "#f97316" }}
        >
          <div className="absolute bottom-[-14px] left-1/2 -translate-x-1/2 text-[7px] font-medium text-text-muted whitespace-nowrap">
            {interestingLine.value}
          </div>
        </div>
      </div>

      {/* Interesting line callout */}
      <div className="text-[11px] font-extrabold mb-0.5" style={{ color: teamColor }}>
        {interestingLine.value}+ wins: {interestingProb}%
      </div>
      <div className="text-[9px] text-text-secondary">The interesting line</div>

      {/* Current record */}
      {wins != null && losses != null && (
        <div className="text-[8px] text-text-muted mt-0.5">
          Currently {wins}-{losses}
          {gamesRemaining != null && gamesRemaining > 0 && ` · ${gamesRemaining} games left`}
        </div>
      )}

      {/* Threshold pills */}
      <div className="flex flex-wrap gap-1 mt-2 justify-center">
        {sorted.map((t) => {
          const isHot = t === interestingLine;
          const prob = Math.round(t.probability * 100);
          return (
            <span
              key={t.value}
              className={`text-[7px] font-semibold font-mono px-1 py-0.5 rounded ${
                isHot
                  ? "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 font-bold"
                  : "bg-surface-elevated text-text-muted"
              }`}
            >
              {t.value}: {prob}%
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** Minimal standings card shown when no season stat futures exist for a team */
function StandingsCard({ name, color, logo, standings }: {
  name: string;
  color: string;
  logo?: string;
  standings: TeamStandings;
}) {
  const record = standings.wins != null && standings.losses != null
    ? `${standings.wins}-${standings.losses}${standings.ties ? `-${standings.ties}` : ""}`
    : null;
  return (
    <div className="rounded-xl border overflow-hidden bg-surface-card" style={{ borderLeftWidth: 3, borderLeftColor: color }}>
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-surface-border/30">
        {logo ? (
          <img src={logo} alt="" className="w-4 h-4 object-contain" />
        ) : (
          <div className="w-4 h-4 rounded flex items-center justify-center text-white text-[6px] font-extrabold" style={{ backgroundColor: color }}>
            {name.slice(0, 3).toUpperCase()}
          </div>
        )}
        <span className="text-[9px] font-bold">{name}</span>
      </div>
      <div className="px-3 py-2 space-y-1">
        {record && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-text-secondary">Record</span>
            <span className="text-[11px] font-bold font-mono">{record}</span>
          </div>
        )}
        {standings.conference && standings.conf_rank != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-text-secondary">{standings.conference}</span>
            <span className="text-[11px] font-bold font-mono">#{standings.conf_rank}</span>
          </div>
        )}
        {standings.division && standings.div_rank != null && (
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-text-secondary">{standings.division}</span>
            <span className="text-[11px] font-bold font-mono">#{standings.div_rank}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function WinTotalsPair({
  homeFutures,
  awayFutures,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
  homeStandings,
  awayStandings,
  sportKey,
}: {
  homeFutures: RelatedFuture[];
  awayFutures: RelatedFuture[];
  homeTeam: string;
  awayTeam: string;
  homeColor: string;
  awayColor: string;
  homeLogo?: string;
  awayLogo?: string;
  homeStandings?: TeamStandings;
  awayStandings?: TeamStandings;
  sportKey?: string;
}) {
  if (homeFutures.length === 0 && awayFutures.length === 0 && !homeStandings && !awayStandings) return null;

  const awayShort = awayTeam.split(" ").pop() || awayTeam;
  const homeShort = homeTeam.split(" ").pop() || homeTeam;

  // Separate win total futures from other season stats
  function extractWinTotals(futures: RelatedFuture[]): { winTotals: WinTotalThreshold[]; other: RelatedFuture[] } {
    const winTotals: WinTotalThreshold[] = [];
    const other: RelatedFuture[] = [];
    for (const f of futures) {
      if (f.merge_group === "win_total") {
        const threshold = parseWinTotalThreshold(f.outcome_name);
        if (threshold != null && f.probability != null) {
          winTotals.push({
            value: threshold,
            probability: f.probability,
            change24h: f.probability_change_24h,
            marketId: f.market_id,
          });
        }
      } else {
        other.push(f);
      }
    }
    return { winTotals, other };
  }

  const homeExtracted = extractWinTotals(homeFutures);
  const awayExtracted = extractWinTotals(awayFutures);
  const hasGauge = homeExtracted.winTotals.length >= 2 || awayExtracted.winTotals.length >= 2;

  function renderListCol(futures: RelatedFuture[], shortName: string, color: string, logo?: string) {
    if (futures.length === 0) return <div />;
    const sorted = [...futures].sort((a, b) => (b.probability || 0) - (a.probability || 0));
    return (
      <div className="rounded-xl border overflow-hidden bg-surface-card" style={{ borderLeftWidth: 3, borderLeftColor: color }}>
        <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-surface-border/30">
          {logo ? (
            <img src={logo} alt="" className="w-4 h-4 object-contain" />
          ) : (
            <div className="w-4 h-4 rounded flex items-center justify-center text-white text-[6px] font-extrabold" style={{ backgroundColor: color }}>
              {shortName.slice(0, 3).toUpperCase()}
            </div>
          )}
          <span className="text-[9px] font-bold">{shortName}</span>
        </div>
        <div>
          {sorted.slice(0, 5).map((f) => (
            <SeasonStatRow key={f.outcome_id} future={f} teamColor={color} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Win Totals — v5 gauge cards */}
      {hasGauge && (
        <div className="grid grid-cols-2 gap-2 mb-2">
          {awayExtracted.winTotals.length >= 2 ? (
            <WinTotalsGauge
              teamName={awayTeam}
              teamColor={awayColor}
              standings={awayStandings}
              thresholds={awayExtracted.winTotals}
              sportKey={sportKey}
              logo={awayLogo}
            />
          ) : <div />}
          {homeExtracted.winTotals.length >= 2 ? (
            <WinTotalsGauge
              teamName={homeTeam}
              teamColor={homeColor}
              standings={homeStandings}
              thresholds={homeExtracted.winTotals}
              sportKey={sportKey}
              logo={homeLogo}
            />
          ) : <div />}
        </div>
      )}
      {/* Other season stats — list view */}
      {(homeExtracted.other.length > 0 || awayExtracted.other.length > 0) && (
        <div className="grid grid-cols-2 gap-2">
          {renderListCol(awayExtracted.other, awayShort, awayColor, awayLogo)}
          {renderListCol(homeExtracted.other, homeShort, homeColor, homeLogo)}
        </div>
      )}
      {/* Standings-only fallback when no futures exist for either team */}
      {!hasGauge && homeExtracted.other.length === 0 && awayExtracted.other.length === 0 && (homeStandings || awayStandings) && (
        <div className="grid grid-cols-2 gap-2">
          {awayStandings ? (
            <StandingsCard name={awayShort} color={awayColor} logo={awayLogo} standings={awayStandings} />
          ) : <div />}
          {homeStandings ? (
            <StandingsCard name={homeShort} color={homeColor} logo={homeLogo} standings={homeStandings} />
          ) : <div />}
        </div>
      )}
    </>
  );
}

// ─── V5 MATCHUP GRID ───
/** Label lookup for matchup merge groups */
const MATCHUP_LABELS: Record<string, string> = {
  nba_finals_matchup: "NBA Finals Matchup",
  super_bowl_matchup: "Super Bowl Matchup",
  stanley_cup_matchup: "Stanley Cup Matchup",
  world_series_matchup: "World Series Matchup",
};

function MatchupGrid({
  futures,
  teamName,
  teamColor,
  logo,
}: {
  futures: RelatedFuture[];
  teamName: string;
  teamColor: string;
  logo?: string;
}) {
  if (futures.length === 0) return null;

  // Group by merge_group to separate finals vs conference matchups
  const groups: Record<string, RelatedFuture[]> = {};
  for (const f of futures) {
    const key = f.merge_group || "other";
    if (!groups[key]) groups[key] = [];
    groups[key].push(f);
  }

  const shortName = teamName.split(" ").pop() || teamName;
  const abbrev = teamName.split(" ").map(w => w[0]).join("").slice(0, 3).toUpperCase();

  return (
    <>
      {Object.entries(groups).map(([groupKey, items]) => {
        const sorted = [...items].sort((a, b) => (b.probability || 0) - (a.probability || 0));
        const maxProb = sorted[0]?.probability || 0;

        // Determine label
        let label = MATCHUP_LABELS[groupKey];
        if (!label) {
          // Try to extract from merge_group (e.g., "eastern_conf_finals_matchup" → "East Conf Finals")
          const confMatch = groupKey.match(/^(eastern|western)_conf_finals_matchup$/);
          if (confMatch) {
            label = `${confMatch[1] === "eastern" ? "East" : "West"} Conf Finals`;
          } else {
            label = (sorted[0]?.clean_label || sorted[0]?.market_name || groupKey).replace(/\s*Matchup\s*$/i, "");
          }
        }

        const sources = [...new Set(sorted.map(s => s.source).filter(Boolean))];
        const sourceLabel = sources.map(s => s === "kalshi" ? "Kalshi" : s === "polymarket" ? "Polymarket" : s).join(" · ");

        return (
          <div key={groupKey} className="rounded-xl border border-surface-border bg-surface-card overflow-hidden mb-2">
            <div className="flex items-center justify-between px-4 py-2 border-b border-surface-border/30">
              <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-text-secondary">
                {label}
              </span>
              <span className="text-[10px] text-text-muted">
                {sorted.length} matchups · {sourceLabel}
              </span>
            </div>
            <div className="px-3 py-1.5">
              {/* Header: team logo + "Team vs ..." */}
              <div className="flex items-center gap-1.5 pb-1.5 border-b border-surface-border/30 mb-1">
                {logo ? (
                  <img src={logo} alt="" className="w-5 h-5 object-contain" />
                ) : (
                  <div
                    className="w-5 h-5 rounded flex items-center justify-center text-white text-[7px] font-extrabold"
                    style={{ backgroundColor: teamColor }}
                  >
                    {abbrev}
                  </div>
                )}
                <span className="text-[10px] font-semibold text-text-secondary">
                  {shortName} vs ...
                </span>
              </div>

              {/* Ranked rows */}
              {sorted.slice(0, 8).map((f, i) => {
                const prob = f.probability || 0;
                const pct = Math.round(prob * 100);
                const barWidth = maxProb > 0 ? (prob / maxProb) * 100 : 0;
                const isTop = i === 0;
                const isFaded = prob < 0.05;

                return (
                  <Link
                    key={f.outcome_id}
                    href={`/futures/${f.market_id}`}
                    className={`flex items-center gap-1.5 py-1 group ${
                      isTop
                        ? "bg-amber-50 dark:bg-amber-900/10 rounded-md px-1 border border-amber-200 dark:border-amber-800/30 -mx-1"
                        : "border-b border-surface-border/10 last:border-0"
                    }`}
                    style={{ opacity: isFaded ? 0.5 : undefined }}
                  >
                    <span className="text-[8px] font-bold text-text-muted w-3 text-right shrink-0">
                      {i + 1}
                    </span>
                    <div
                      className="w-[18px] h-[18px] rounded flex items-center justify-center text-white text-[6px] font-extrabold shrink-0"
                      style={{ backgroundColor: "#6B7280" }}
                    >
                      {(f.outcome_name || "").split(" ").map(w => w[0]).join("").slice(0, 3).toUpperCase()}
                    </div>
                    <span className="text-[10px] font-semibold flex-1 truncate text-text-primary group-hover:text-text-primary/80">
                      {f.outcome_name}
                    </span>
                    <div className="w-[60px] h-[5px] rounded bg-surface-elevated overflow-hidden shrink-0">
                      <div
                        className="h-full rounded"
                        style={{
                          width: `${barWidth}%`,
                          background: isTop
                            ? `linear-gradient(90deg, #6B7280, ${teamColor})`
                            : prob >= 0.05 ? "#6B7280" : "#aaa",
                        }}
                      />
                    </div>
                    <span
                      className={`text-[10px] font-bold font-mono min-w-[28px] text-right shrink-0 ${
                        isTop ? "text-amber-600 dark:text-amber-400" : isFaded ? "text-text-muted" : ""
                      }`}
                    >
                      {pct < 1 && prob > 0 ? "<1" : pct}%
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </>
  );
}

// ─── V5 AWARD COMPACT ROW ───
function AwardCompactRow({
  future,
  teamColor,
  teamLabel,
  sportKey,
}: {
  future: RelatedFuture;
  teamColor: string;
  teamLabel: string;
  sportKey?: string;
}) {
  const awardLabel = shortAwardLabel(future.market_name, future.clean_label);
  const prob = future.probability || 0;
  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="flex items-center gap-2 py-1.5 border-b border-surface-border/20 last:border-0 group hover:bg-surface-elevated/30 transition-colors -mx-1 px-1 rounded"
    >
      <PlayerHeadshot
        name={future.outcome_name}
        matchedPlayer={future.matched_player}
        sportKey={sportKey}
        teamColor={teamColor}
        size={24}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-bold text-text-primary truncate leading-tight">
          {future.outcome_name}
        </div>
        <div className="text-[8px] text-text-muted font-medium">{awardLabel}</div>
      </div>
      <span
        className="text-[7px] font-bold px-1.5 py-0.5 rounded text-white shrink-0"
        style={{ backgroundColor: teamColor }}
      >
        {teamLabel}
      </span>
      <div className="flex items-center gap-1 shrink-0">
        <span
          className="text-[11px] font-extrabold font-mono"
          style={{ color: prob >= 0.10 ? undefined : "var(--text-muted)" }}
        >
          {formatProbability(future.probability)}
        </span>
        {future.probability_change_24h && Math.abs(future.probability_change_24h) >= 0.005 && (
          <span className={`text-[8px] font-bold ${future.probability_change_24h > 0 ? "text-emerald-500" : "text-red-500"}`}>
            {future.probability_change_24h > 0 ? "+" : ""}{Math.round(future.probability_change_24h * 100)}%
          </span>
        )}
      </div>
    </Link>
  );
}

// ─── V5 TRADE WATCH (2-col per team) ───
function TradeWatchPair({
  homeTrades,
  awayTrades,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
  homeLogo,
  awayLogo,
}: {
  homeTrades: RelatedFuture[];
  awayTrades: RelatedFuture[];
  homeTeam: string;
  awayTeam: string;
  homeColor: string;
  awayColor: string;
  homeLogo?: string;
  awayLogo?: string;
}) {
  if (homeTrades.length === 0 && awayTrades.length === 0) return null;

  function renderCol(trades: RelatedFuture[], shortName: string, color: string, logo?: string) {
    if (trades.length === 0) return <div />;
    const sorted = [...trades].sort((a, b) => (b.probability || 0) - (a.probability || 0));
    return (
      <div className="rounded-xl border overflow-hidden bg-surface-card" style={{ borderTop: `3px solid ${color}` }}>
        <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-surface-border/30">
          {logo ? (
            <img src={logo} alt="" className="w-4 h-4 object-contain" />
          ) : (
            <div className="w-4 h-4 rounded flex items-center justify-center text-white text-[6px] font-extrabold" style={{ backgroundColor: color }}>
              {shortName.slice(0, 3).toUpperCase()}
            </div>
          )}
          <span className="text-[9px] font-bold">Traded to {shortName}</span>
        </div>
        {sorted.slice(0, 5).map((f, i) => {
          const playerName = extractTradePlayer(f.market_name);
          return (
            <Link
              key={f.outcome_id}
              href={`/futures/${f.market_id}`}
              className="flex items-center gap-2 px-2 py-1.5 border-b border-surface-border/10 last:border-0 hover:bg-surface-elevated/30 transition-colors"
            >
              <PlayerHeadshot
                name={playerName}
                matchedPlayer={f.matched_player}
                teamColor={color}
                size={i === 0 ? 32 : 20}
              />
              <span className="text-[9px] font-semibold flex-1 truncate">{playerName}</span>
              <span className="text-[10px] font-bold font-mono" style={{ color: (f.probability || 0) >= 0.10 ? undefined : "var(--text-muted)" }}>
                {formatProbability(f.probability)}
              </span>
            </Link>
          );
        })}
      </div>
    );
  }

  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  return (
    <div className="grid grid-cols-2 gap-2">
      {renderCol(awayTrades, awayShort, awayColor, awayLogo)}
      {renderCol(homeTrades, homeShort, homeColor, homeLogo)}
    </div>
  );
}

// ─── V5 NOVELTY SCROLL (horizontal gradient cards) ───
const NOVELTY_GRADIENTS = [
  "from-purple-600 to-pink-500",
  "from-sky-700 to-cyan-500",
  "from-red-600 to-orange-500",
  "from-emerald-600 to-emerald-400",
  "from-violet-700 to-purple-400",
  "from-amber-600 to-yellow-400",
];

function NoveltyScroll({ futures }: { futures: RelatedFuture[] }) {
  if (futures.length === 0) return null;
  return (
    <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 scrollbar-hide">
      {futures.slice(0, 8).map((f, i) => {
        const gradient = NOVELTY_GRADIENTS[i % NOVELTY_GRADIENTS.length];
        const pct = Math.round((f.probability || 0) * 100);
        // Use clean_label for display, fall back to market_name
        const label = f.clean_label || f.market_name;
        return (
          <Link
            key={f.outcome_id}
            href={`/futures/${f.market_id}`}
            className={`flex-shrink-0 rounded-xl overflow-hidden bg-gradient-to-br ${gradient} w-[180px]`}
          >
            <div className="p-3 flex flex-col gap-1.5 min-h-[100px] relative">
              <div className="text-[11px] font-bold text-white leading-snug" style={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                {label}
              </div>
              <div className="text-white/70 text-[9px] truncate">
                {f.outcome_name}
              </div>
              <div className="flex items-end justify-between mt-auto">
                <div className="text-[15px] font-black font-mono text-white">
                  {pct}%
                </div>
                {f.source && (
                  <span className="text-[7px] font-semibold px-1.5 py-0.5 rounded bg-white/20 text-white">
                    {f.source === "kalshi" ? "Kalshi" : f.source === "polymarket" ? "Polymarket" : f.source}
                  </span>
                )}
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

// ─── V5 GAME MARKETS PAIR (upcoming games side-by-side) ───
function GameMarketsPair({
  homeFutures,
  awayFutures,
  homeTeam,
  awayTeam,
  homeColor,
  awayColor,
}: {
  homeFutures: RelatedFuture[];
  awayFutures: RelatedFuture[];
  homeTeam: string;
  awayTeam: string;
  homeColor: string;
  awayColor: string;
}) {
  if (homeFutures.length === 0 && awayFutures.length === 0) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-3">
      {awayFutures.length > 0 && (
        <GameMarketsGrid futures={awayFutures} teamColor={awayColor} teamName={awayTeam} />
      )}
      {homeFutures.length > 0 && (
        <GameMarketsGrid futures={homeFutures} teamColor={homeColor} teamName={homeTeam} />
      )}
    </div>
  );
}

/** Check if a game_prop market actually belongs to this event (filter out mismatches). */
function isRelevantGameProp(f: RelatedFuture, homeTeam: string, awayTeam: string): boolean {
  if (f.display_category !== "game_prop") return true;
  const name = f.market_name.toLowerCase();
  // Extract city/team tokens from both teams
  const homeTokens = homeTeam.toLowerCase().split(/\s+/);
  const awayTokens = awayTeam.toLowerCase().split(/\s+/);
  const allTokens = [...homeTokens, ...awayTokens];
  // If market name contains "at" or "vs" pattern, check the teams match
  const matchupMatch = name.match(/^(.+?)\s+(?:at|vs\.?)\s+(.+?)(?:\s*:|\s*$)/);
  if (matchupMatch) {
    const team1 = matchupMatch[1].trim();
    const team2 = matchupMatch[2].trim();
    const matchesTeam = (t: string) => allTokens.some((tok) => t.includes(tok) && tok.length > 2);
    // If neither team in the matchup matches our event teams, filter it out
    if (!matchesTeam(team1) && !matchesTeam(team2)) return false;
    // Specifically filter known college team false positives
    if (/miami\s*\(oh\)|smu\b|southern\s+methodist/i.test(name)) return false;
  }
  return true;
}

/** Extract player name from trade market (e.g. "Devin Booker's Next Team" → "Devin Booker") */
function extractTradePlayer(marketName: string): string {
  const m = marketName.match(/^(.+?)(?:'s?\s+Next\s+Team|'s?\s+next\s+destination)/i);
  return m ? m[1].trim() : marketName;
}

/** Categorize a list of related futures into display groups. */
function categorizeFutures(futures: RelatedFuture[], homeTeam: string = "", awayTeam: string = "") {
  const active = futures.filter((f) => {
    const p = f.probability;
    if (p === null || p === undefined) return true;
    if (p <= 0.01 || p >= 0.99) return false;
    // Filter mismatched game props
    if (!isRelevantGameProp(f, homeTeam, awayTeam)) return false;
    return true;
  });
  return {
    championship: active.filter((f) => {
      if (f.display_category === "playoff_path") return true;
      // Also pull division/playoff items from season_stat
      if (f.display_category === "season_stat") {
        const name = (f.clean_label || f.market_name).toLowerCase();
        if (/division|playoff|play-?in|#1 seed|best record/i.test(name)) return true;
      }
      return false;
    }),
    conference: active.filter((f) => {
      if (f.display_category !== "conference") return false;
      // Exclude matchup items — they get their own section
      if (f.merge_group && /_matchup$/.test(f.merge_group)) return false;
      return true;
    }),
    matchups: active.filter((f) => {
      if (f.display_category !== "conference") return false;
      return !!(f.merge_group && /_matchup$/.test(f.merge_group));
    }),
    awards: active.filter((f) => f.display_category === "award"),
    seasonStats: active.filter((f) => {
      if (f.display_category === "season_stat") {
        // Pull division/playoff/seed items into playoff path instead
        const name = (f.clean_label || f.market_name).toLowerCase();
        if (/division|playoff|play[- ]?in|#1\s+seed|best\s+record|worst\s+record/i.test(name)) return false;
        return true;
      }
      return false;
    }),
    trades: active.filter((f) => f.display_category === "trade"),
    novelty: active.filter((f) => f.display_category === "novelty"),
    games: active.filter((f) => f.display_category === "other"),
    statProps: active.filter((f) => f.display_category === "game_prop"),
  };
}

/**
 * Related Futures — "Bigger Picture" section on event detail page.
 * V5 layout: cross-team sections instead of per-team columns.
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
  homeStandings,
  awayStandings,
  hasGameMarkets = false,
  teamProgression,
}: RelatedFuturesProps) {
  const { data, error, isLoading } = useSWR<RelatedFuturesResponse>(
    ["related-futures", eventId],
    () => fetchRelatedFutures(eventId),
    {
      revalidateOnFocus: false,
      dedupingInterval: 300000,
    }
  );

  if (isLoading || error || !data || data.total_count === 0) {
    return null;
  }

  const { home_team_futures, away_team_futures, event_status, box_score } = data;
  const isFinished = event_status === "completed" || event_status === "closed";
  const isLive = event_status === "live";
  const boxScore = box_score ?? null;

  const hColor = homeTeamColor || DEFAULT_COLOR;
  const aColor = awayTeamColor || DEFAULT_COLOR;
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  // Categorize futures for each team (pass team names for mismatch filtering)
  const homeCats = categorizeFutures(home_team_futures, homeTeam, awayTeam);
  const awayCats = categorizeFutures(away_team_futures, homeTeam, awayTeam);

  // Find championship futures for title comparison
  const CHAMP_RE = /\bchampionship\b|\bwin\s+(the\s+)?title\b|\btitle\s+winner\b|\bwin\s+it\s+all\b/i;
  function findBestChampionship(futures: RelatedFuture[]): RelatedFuture | undefined {
    const tier1 = futures.filter((f) => effectiveTier(f) === 1);
    const byMerge = tier1.find((f) =>
      f.merge_group === "nba_champion" || f.merge_group === "nfl_champion" ||
      f.merge_group === "mlb_champion" || f.merge_group === "nhl_champion"
    );
    if (byMerge) return byMerge;
    return tier1.find((f) => CHAMP_RE.test(f.market_name)) || tier1[0];
  }
  const homeChamp = findBestChampionship(home_team_futures);
  const awayChamp = findBestChampionship(away_team_futures);
  const showTitleComparison = !!(homeChamp && awayChamp);

  // Merge awards across both teams
  const mergedAwards = [
    ...deduplicateAwards(homeCats.awards).map((a) => ({
      ...a,
      teamColor: hColor,
      teamLabel: homeShort,
    })),
    ...deduplicateAwards(awayCats.awards).map((a) => ({
      ...a,
      teamColor: aColor,
      teamLabel: awayShort,
    })),
  ].sort((a, b) => (b.future.probability || 0) - (a.future.probability || 0));

  // Merge novelty across teams
  const mergedNovelty = [...homeCats.novelty, ...awayCats.novelty].sort(
    (a, b) => (b.probability || 0) - (a.probability || 0),
  );

  // Playoff path (championship + conference combined)
  const homePlayoff = [...homeCats.championship, ...homeCats.conference];
  const awayPlayoff = [...awayCats.championship, ...awayCats.conference];

  // Section counts — suppress stat props when game-markets components already show them
  const effectiveStatProps = hasGameMarkets ? 0 : homeCats.statProps.length + awayCats.statProps.length;
  const gameMarketCount =
    effectiveStatProps +
    homeCats.games.length + awayCats.games.length;
  const hasStandings = !!(homeStandings || awayStandings);
  const seasonCount =
    homePlayoff.length + awayPlayoff.length +
    homeCats.matchups.length + awayCats.matchups.length +
    homeCats.seasonStats.length + awayCats.seasonStats.length +
    mergedAwards.length +
    homeCats.trades.length + awayCats.trades.length +
    mergedNovelty.length +
    (hasStandings && homeCats.seasonStats.length === 0 && awayCats.seasonStats.length === 0 ? 1 : 0);

  // Grid-based playoff path is available when team-progression data exists for at least one team
  const hasGridProgression = !!(teamProgression?.home_team || teamProgression?.away_team);

  if (gameMarketCount === 0 && seasonCount === 0 && !hasGridProgression) return null;

  return (
    <div className="bg-surface-card rounded-card shadow-card p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-text-secondary mb-3">
        Bigger Picture
      </h3>
      <div className="max-w-2xl mx-auto">

      {/* Title Odds comparison */}
      {showTitleComparison && (
        <TitleComparison
          homeChamp={homeChamp!}
          awayChamp={awayChamp!}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          homeTeamColor={hColor}
          awayTeamColor={aColor}
        />
      )}

      {/* === Level 3: Game Markets === */}
      {gameMarketCount > 0 && (
        <>
          <SectionDivider level={3} label="Game Markets" count={gameMarketCount} />

          {/* Stat props (player props) — per team; hidden when game-markets section shows them above */}
          {!hasGameMarkets && (homeCats.statProps.length > 0 || awayCats.statProps.length > 0) && (
            <div className="space-y-4 mb-3">
              {homeCats.statProps.length > 0 && (
                <StatPropsSection
                  futures={homeCats.statProps}
                  teamColor={hColor}
                  sportKey={sportKey}
                  isFinished={isFinished}
                  isLive={isLive}
                  boxScore={boxScore}
                />
              )}
              {awayCats.statProps.length > 0 && (
                <StatPropsSection
                  futures={awayCats.statProps}
                  teamColor={aColor}
                  sportKey={sportKey}
                  isFinished={isFinished}
                  isLive={isLive}
                  boxScore={boxScore}
                />
              )}
            </div>
          )}

          {/* Upcoming game markets */}
          <GameMarketsPair
            homeFutures={homeCats.games}
            awayFutures={awayCats.games}
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            homeColor={hColor}
            awayColor={aColor}
          />
        </>
      )}

      {/* === Level 4: Season Context === */}
      {(seasonCount > 0 || hasGridProgression) && (
        <>
          <SectionDivider level={4} label="Season Context" count={seasonCount + (hasGridProgression && homePlayoff.length === 0 && awayPlayoff.length === 0 ? 1 : 0)} />

          {/* Playoff Path — use grid data (guaranteed both teams) with futures fallback */}
          {hasGridProgression ? (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                  Playoff Path
                </span>
              </div>
              <GridPlayoffPathPair
                teamProgression={teamProgression!}
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                homeColor={hColor}
                awayColor={aColor}
                homeLogo={homeTeamLogo}
                awayLogo={awayTeamLogo}
              />
            </div>
          ) : (homePlayoff.length > 0 || awayPlayoff.length > 0) ? (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                  Playoff Path
                </span>
              </div>
              <PlayoffPathPair
                homeFutures={homePlayoff}
                awayFutures={awayPlayoff}
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                homeColor={hColor}
                awayColor={aColor}
                homeLogo={homeTeamLogo}
                awayLogo={awayTeamLogo}
              />
            </div>
          ) : null}

          {/* Matchup Grids — Finals, Conference Finals */}
          {(homeCats.matchups.length > 0 || awayCats.matchups.length > 0) && (
            <div className="mb-3">
              {homeCats.matchups.length > 0 && (
                <MatchupGrid
                  futures={homeCats.matchups}
                  teamName={homeTeam}
                  teamColor={hColor}
                  logo={homeTeamLogo}
                />
              )}
              {awayCats.matchups.length > 0 && (
                <MatchupGrid
                  futures={awayCats.matchups}
                  teamName={awayTeam}
                  teamColor={aColor}
                  logo={awayTeamLogo}
                />
              )}
            </div>
          )}

          {/* Season Stats — win totals, division, seeding */}
          {(homeCats.seasonStats.length > 0 || awayCats.seasonStats.length > 0 || homeStandings || awayStandings) && (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                  Season Stats
                </span>
              </div>
              <WinTotalsPair
                homeFutures={homeCats.seasonStats}
                awayFutures={awayCats.seasonStats}
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                homeColor={hColor}
                awayColor={aColor}
                homeLogo={homeTeamLogo}
                awayLogo={awayTeamLogo}
                homeStandings={homeStandings}
                awayStandings={awayStandings}
                sportKey={sportKey}
              />
            </div>
          )}

          {/* Awards — merged compact rows from both teams */}
          {mergedAwards.length > 0 && (
            <div className="rounded-xl border border-surface-border overflow-hidden mb-3">
              <div className="flex items-center justify-between px-4 py-2 border-b border-surface-border/30">
                <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-text-muted">
                  Awards & All-Team
                </span>
                <span className="text-[10px] text-text-muted/50">
                  {homeShort}/{awayShort} players
                </span>
              </div>
              <div className="px-3 py-1">
                {mergedAwards.slice(0, 10).map(({ future, teamColor, teamLabel }) => (
                  <AwardCompactRow
                    key={`${future.outcome_id}-${future.market_id}`}
                    future={future}
                    teamColor={teamColor}
                    teamLabel={teamLabel}
                    sportKey={sportKey}
                  />
                ))}
                {mergedAwards.length > 10 && (
                  <div className="text-center py-1">
                    <span className="text-[10px] text-text-muted/50">
                      +{mergedAwards.length - 10} more
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Trade Watch — 2-col per team */}
          {(homeCats.trades.length > 0 || awayCats.trades.length > 0) && (
            <div className="mb-3">
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                  Trade Watch
                </span>
              </div>
              <TradeWatchPair
                homeTrades={homeCats.trades}
                awayTrades={awayCats.trades}
                homeTeam={homeTeam}
                awayTeam={awayTeam}
                homeColor={hColor}
                awayColor={aColor}
                homeLogo={homeTeamLogo}
                awayLogo={awayTeamLogo}
              />
            </div>
          )}

          {/* Novelty & Fun — horizontal scroll gradient cards */}
          {mergedNovelty.length > 0 && (
            <div className="mb-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted">
                  Novelty & Fun
                </span>
                <span className="text-[10px] text-text-muted/50">
                  {mergedNovelty.length} items
                </span>
              </div>
              <NoveltyScroll futures={mergedNovelty} />
            </div>
          )}
        </>
      )}

      </div>

      {/* Footer count */}
      <div className="text-center pt-2 border-t border-surface-border/30 mt-3">
        <span className="text-[9px] text-text-muted">
          {data.total_count} related futures from multiple sources
        </span>
      </div>
    </div>
  );
}
