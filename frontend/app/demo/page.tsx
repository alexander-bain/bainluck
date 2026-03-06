"use client";

import { useEffect, useState } from "react";
import { motion, useSpring, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";
import { staggerContainer, staggerItem, eiBreathingTransition } from "@/lib/animations";

// =============================================================================
// TYPES
// =============================================================================

type EventStatus = "scheduled" | "live" | "completed";
type FuturesCategory = "basketball" | "politics" | "crypto" | "entertainment" | "economics";

interface TeamData {
  name: string;
  shortName: string;
  logo?: string;
  primaryColor: string;
}

interface EventData {
  id: string;
  sport: string;
  sportIcon: string;
  status: EventStatus;
  homeTeam: TeamData;
  awayTeam: TeamData;
  homeProb: number;
  awayProb: number;
  homeScore?: number;
  awayScore?: number;
  gameTime?: string;
  broadcast?: string;
  projectedScore?: { home: number; away: number };
  openingOdds?: { home: number; away: number };
  ei?: number;
  highlightLabel?: string;
}

interface FuturesOutcome {
  id: string;
  name: string;
  probability: number;
  movement?: number;
}

interface FuturesData {
  id: string;
  name: string;
  category: FuturesCategory;
  categoryLabel: string;
  outcomes: FuturesOutcome[];
  source: string;
  sourceCount: number;
  updatedAt: string;
}

// =============================================================================
// SAMPLE DATA
// =============================================================================

const SAMPLE_EVENTS: EventData[] = [
  // Scheduled
  {
    id: "1",
    sport: "NBA",
    sportIcon: "🏀",
    status: "scheduled",
    homeTeam: { name: "Boston Celtics", shortName: "CEL", primaryColor: "#007A33" },
    awayTeam: { name: "Miami Heat", shortName: "MIA", primaryColor: "#98002E" },
    homeProb: 0.62,
    awayProb: 0.38,
    gameTime: "Today 7:30 PM",
    broadcast: "ESPN · TNT",
    projectedScore: { home: 108, away: 102 },
  },
  // Live
  {
    id: "2",
    sport: "NBA",
    sportIcon: "🏀",
    status: "live",
    homeTeam: { name: "Boston Celtics", shortName: "CEL", primaryColor: "#007A33" },
    awayTeam: { name: "Miami Heat", shortName: "MIA", primaryColor: "#98002E" },
    homeProb: 0.71,
    awayProb: 0.29,
    homeScore: 78,
    awayScore: 72,
    broadcast: "TNT",
    openingOdds: { home: 0.62, away: 0.38 },
    ei: 78,
    highlightLabel: "Upset brewing",
  },
  // Live - high EI
  {
    id: "3",
    sport: "NFL",
    sportIcon: "🏈",
    status: "live",
    homeTeam: { name: "Kansas City Chiefs", shortName: "KC", primaryColor: "#E31837" },
    awayTeam: { name: "Buffalo Bills", shortName: "BUF", primaryColor: "#00338D" },
    homeProb: 0.52,
    awayProb: 0.48,
    homeScore: 24,
    awayScore: 21,
    broadcast: "CBS",
    openingOdds: { home: 0.58, away: 0.42 },
    ei: 84,
    highlightLabel: "Wild finish",
  },
  // Finished - underdog won
  {
    id: "4",
    sport: "NBA",
    sportIcon: "🏀",
    status: "completed",
    homeTeam: { name: "Miami Heat", shortName: "MIA", primaryColor: "#98002E" },
    awayTeam: { name: "Boston Celtics", shortName: "CEL", primaryColor: "#007A33" },
    homeProb: 0.38,
    awayProb: 0.62,
    homeScore: 102,
    awayScore: 98,
    gameTime: "Yesterday 7 PM",
    openingOdds: { home: 0.38, away: 0.62 },
    ei: 84,
    highlightLabel: "Won as 35% underdog",
  },
  // Soccer
  {
    id: "5",
    sport: "Soccer",
    sportIcon: "⚽",
    status: "scheduled",
    homeTeam: { name: "Manchester City", shortName: "MCI", primaryColor: "#6CABDD" },
    awayTeam: { name: "Arsenal", shortName: "ARS", primaryColor: "#EF0107" },
    homeProb: 0.55,
    awayProb: 0.45,
    gameTime: "Tomorrow 3:00 PM",
    broadcast: "NBC",
    projectedScore: { home: 2, away: 1 },
  },
  // MLB
  {
    id: "6",
    sport: "MLB",
    sportIcon: "⚾",
    status: "live",
    homeTeam: { name: "New York Yankees", shortName: "NYY", primaryColor: "#003087" },
    awayTeam: { name: "Boston Red Sox", shortName: "BOS", primaryColor: "#BD3039" },
    homeProb: 0.64,
    awayProb: 0.36,
    homeScore: 5,
    awayScore: 3,
    broadcast: "YES",
    openingOdds: { home: 0.58, away: 0.42 },
    ei: 52,
  },
];

const SAMPLE_FUTURES: FuturesData[] = [
  {
    id: "f1",
    name: "NBA Championship Winner 2025-26",
    category: "basketball",
    categoryLabel: "Championship",
    outcomes: [
      { id: "o1", name: "Boston Celtics", probability: 0.22, movement: 0.013 },
      { id: "o2", name: "Oklahoma City Thunder", probability: 0.18 },
      { id: "o3", name: "Cleveland Cavaliers", probability: 0.12, movement: -0.005 },
      { id: "o4", name: "Denver Nuggets", probability: 0.09 },
      { id: "o5", name: "Golden State Warriors", probability: 0.07 },
    ],
    source: "Sportsbooks",
    sourceCount: 3,
    updatedAt: "2h ago",
  },
  {
    id: "f2",
    name: "Will Bitcoin exceed $150,000 by end of 2026?",
    category: "crypto",
    categoryLabel: "Price Target",
    outcomes: [
      { id: "o6", name: "Yes", probability: 0.42, movement: 0.034 },
      { id: "o7", name: "No", probability: 0.58, movement: -0.034 },
    ],
    source: "Polymarket",
    sourceCount: 2,
    updatedAt: "15m ago",
  },
  {
    id: "f3",
    name: "2028 US Presidential Election Winner",
    category: "politics",
    categoryLabel: "Election",
    outcomes: [
      { id: "o8", name: "Democratic Nominee", probability: 0.48, movement: 0.02 },
      { id: "o9", name: "Republican Nominee", probability: 0.46, movement: -0.015 },
      { id: "o10", name: "Third Party", probability: 0.06 },
    ],
    source: "Kalshi",
    sourceCount: 1,
    updatedAt: "1h ago",
  },
];

const FILTER_CHIPS = [
  { label: "All", emoji: "🌐" },
  { label: "NBA", emoji: "🏀" },
  { label: "NFL", emoji: "🏈" },
  { label: "MLB", emoji: "⚾" },
  { label: "Soccer", emoji: "⚽" },
  { label: "Politics", emoji: "🗳️" },
  { label: "Crypto", emoji: "₿" },
];

const CATEGORY_COLORS: Record<FuturesCategory, string> = {
  basketball: "#8B5CF6",
  politics: "#3B82F6",
  crypto: "#F97316",
  entertainment: "#EAB308",
  economics: "#10B981",
};

// =============================================================================
// ANIMATED PROBABILITY NUMBER
// =============================================================================

function AnimatedProbability({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const springValue = useSpring(value * 100, {
    stiffness: 80,
    damping: 20,
    mass: 0.5,
  });
  const display = useTransform(springValue, (v: number) => `${Math.round(v)}%`);

  useEffect(() => {
    springValue.set(value * 100);
  }, [value, springValue]);

  return <motion.span className={className}>{display}</motion.span>;
}

// =============================================================================
// PROBABILITY BAR COMPONENT
// =============================================================================

function ProbabilityBar({
  homeProb,
  homeColor,
  awayColor,
  homeFavorite,
  height = 5,
}: {
  homeProb: number;
  homeColor: string;
  awayColor: string;
  homeFavorite: boolean;
  height?: number;
}) {
  const homeWidth = homeProb * 100;
  const awayWidth = 100 - homeWidth;

  return (
    <div className="flex w-full gap-[1.5px]" style={{ height: `${height}px` }}>
      <motion.div
        className="rounded-full"
        style={{
          backgroundColor: homeColor,
          opacity: homeFavorite ? 1 : 0.4,
        }}
        animate={{ width: `${homeWidth}%` }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
      />
      <motion.div
        className="rounded-full"
        style={{
          backgroundColor: awayColor,
          opacity: !homeFavorite ? 1 : 0.4,
        }}
        animate={{ width: `${awayWidth}%` }}
        transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
      />
    </div>
  );
}

// =============================================================================
// EI BADGE COMPONENT
// =============================================================================

function EIBadge({ score, isLive = false }: { score: number; isLive?: boolean }) {
  const getBgClass = () => {
    if (score >= 70) return "bg-accent-live/15 text-accent-live";
    if (score >= 50) return "bg-accent-warning/15 text-accent-warning";
    return "bg-surface-elevated text-text-muted";
  };

  const showBreathing = isLive && score >= 70;

  return (
    <motion.span
      className={cn(
        "flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold",
        getBgClass()
      )}
      {...(showBreathing
        ? {
            animate: { scale: [1, 1.03, 1] },
            transition: eiBreathingTransition(score),
          }
        : {})}
    >
      ⚡ EI {score}
    </motion.span>
  );
}

// =============================================================================
// EVENT CARD COMPONENT
// =============================================================================

function EventCard({ event }: { event: EventData }) {
  const isLive = event.status === "live";
  const isFinished = event.status === "completed";
  const isScheduled = event.status === "scheduled";
  const homeFavorite = event.homeProb >= event.awayProb;

  // For finished games, show opening odds
  const displayHomeProb = isFinished ? (event.openingOdds?.home ?? event.homeProb) : event.homeProb;
  const displayAwayProb = isFinished ? (event.openingOdds?.away ?? event.awayProb) : event.awayProb;

  // Determine winner for finished games
  const homeWon = isFinished && event.homeScore !== undefined && event.awayScore !== undefined && event.homeScore > event.awayScore;
  const awayWon = isFinished && event.homeScore !== undefined && event.awayScore !== undefined && event.awayScore > event.homeScore;

  return (
    <motion.div
      variants={staggerItem}
      className={cn(
        "relative bg-surface-card border border-surface-border rounded-[10px] p-4",
        "transition-all cursor-pointer hover:bg-surface-elevated hover:shadow-card-hover hover:scale-[1.005]",
        isLive && "border-l-[3px] border-l-accent-live ring-1 ring-accent-live/20",
        isFinished && "opacity-80 hover:opacity-100"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">{event.sportIcon}</span>
          <span className="text-[10px] text-text-muted uppercase tracking-widest font-semibold">
            {event.sport}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {isLive && (
            <>
              <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-2 py-0.5 rounded text-[10px] font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                LIVE
              </span>
              {event.highlightLabel && (
                <span className="text-[10px] text-text-secondary">{event.highlightLabel}</span>
              )}
              {event.ei && <EIBadge score={event.ei} isLive />}
            </>
          )}

          {isFinished && (
            <>
              <span className="text-[10px] text-text-muted uppercase font-semibold">FINAL</span>
              {event.highlightLabel && (
                <span className="text-[10px] text-accent-warning bg-accent-warning/10 px-1.5 py-0.5 rounded">
                  {event.highlightLabel}
                </span>
              )}
              {event.ei && <EIBadge score={event.ei} />}
            </>
          )}

          {isScheduled && (
            <span className="text-xs text-text-muted">{event.gameTime}</span>
          )}
        </div>
      </div>

      {/* Score display for live/finished */}
      {(isLive || isFinished) && event.homeScore !== undefined && event.awayScore !== undefined && (
        <div
          className={cn(
            "flex items-center justify-center gap-6 py-2 mb-3 rounded-lg",
            isLive ? "bg-accent-live/5" : "bg-surface-elevated/50"
          )}
        >
          <div className="text-center">
            <div
              className={cn(
                "font-mono text-2xl font-bold",
                isFinished
                  ? homeWon
                    ? "text-text-primary"
                    : "text-text-muted"
                  : "text-accent-live"
              )}
            >
              {event.homeScore}
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-wide">
              {event.homeTeam.shortName}
            </div>
          </div>
          <span className="text-text-muted font-light text-lg">—</span>
          <div className="text-center">
            <div
              className={cn(
                "font-mono text-2xl font-bold",
                isFinished
                  ? awayWon
                    ? "text-text-primary"
                    : "text-text-muted"
                  : "text-accent-live"
              )}
            >
              {event.awayScore}
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-wide">
              {event.awayTeam.shortName}
            </div>
          </div>
        </div>
      )}

      {/* Teams + Probabilities */}
      <div className="space-y-1.5">
        {/* Home team */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div
              className="w-5 h-5 rounded-sm flex items-center justify-center text-[9px] font-bold text-white"
              style={{ backgroundColor: event.homeTeam.primaryColor }}
            >
              {event.homeTeam.shortName.slice(0, 2)}
            </div>
            <span
              className={cn(
                "text-sm font-medium truncate",
                isFinished && homeWon && "flex items-center gap-1"
              )}
            >
              <span className={homeFavorite ? "text-text-primary" : "text-text-secondary"}>
                {event.homeTeam.name}
              </span>
              {isFinished && homeWon && (
                <span className="text-accent-live text-xs">✓</span>
              )}
            </span>
          </div>
          <AnimatedProbability
            value={displayHomeProb}
            className={cn(
              "font-mono tabular-nums",
              homeFavorite ? "text-[20px] font-bold text-text-primary" : "text-[16px] font-bold text-text-secondary"
            )}
          />
        </div>

        {/* Probability bar */}
        <ProbabilityBar
          homeProb={displayHomeProb}
          homeColor={event.homeTeam.primaryColor}
          awayColor={event.awayTeam.primaryColor}
          homeFavorite={homeFavorite}
        />

        {/* Away team */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div
              className="w-5 h-5 rounded-sm flex items-center justify-center text-[9px] font-bold text-white"
              style={{ backgroundColor: event.awayTeam.primaryColor }}
            >
              {event.awayTeam.shortName.slice(0, 2)}
            </div>
            <span
              className={cn(
                "text-sm font-medium truncate",
                isFinished && awayWon && "flex items-center gap-1"
              )}
            >
              <span className={!homeFavorite ? "text-text-primary" : "text-text-secondary"}>
                {event.awayTeam.name}
              </span>
              {isFinished && awayWon && (
                <span className="text-accent-live text-xs">✓</span>
              )}
            </span>
          </div>
          <AnimatedProbability
            value={displayAwayProb}
            className={cn(
              "font-mono tabular-nums",
              !homeFavorite ? "text-[20px] font-bold text-text-primary" : "text-[16px] font-bold text-text-secondary"
            )}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-surface-border/50 flex justify-between items-center text-xs text-text-muted">
        {isScheduled && event.projectedScore && (
          <span>
            Proj{" "}
            <span className="font-mono text-text-secondary">
              {event.projectedScore.home}-{event.projectedScore.away}
            </span>
          </span>
        )}
        {isLive && event.openingOdds && (
          <span>
            Opened{" "}
            <span className="font-mono text-text-secondary">
              {Math.round(event.openingOdds.home * 100)}/{Math.round(event.openingOdds.away * 100)}
            </span>
          </span>
        )}
        {isFinished && (
          <span>
            Pre-game:{" "}
            <span className="font-mono text-text-secondary">
              {Math.round(displayHomeProb * 100)}%/{Math.round(displayAwayProb * 100)}%
            </span>
          </span>
        )}
        {event.broadcast && <span className="truncate ml-auto">{event.broadcast}</span>}
        {isFinished && event.gameTime && !event.broadcast && (
          <span className="ml-auto">{event.gameTime}</span>
        )}
      </div>
    </motion.div>
  );
}

// =============================================================================
// COMPACT FEED CARD COMPONENT
// =============================================================================

function CompactFeedCard({ event }: { event: EventData }) {
  const isLive = event.status === "live";
  const homeFavorite = event.homeProb >= event.awayProb;

  return (
    <motion.div
      variants={staggerItem}
      className={cn(
        "bg-surface-card border border-surface-border rounded-[10px] p-3",
        "transition-all cursor-pointer hover:bg-surface-elevated hover:shadow-card-hover",
        isLive && "border-l-[3px] border-l-accent-live ring-1 ring-accent-live/20"
      )}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          {isLive && (
            <span className="flex items-center gap-1 text-accent-live text-[10px] font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
              LIVE
            </span>
          )}
          <span className="text-[10px] text-text-muted uppercase tracking-wide">{event.sport}</span>
        </div>
        {event.homeScore !== undefined && event.awayScore !== undefined && (
          <span className="font-mono text-sm font-bold text-text-primary">
            {event.homeScore} - {event.awayScore}
          </span>
        )}
      </div>

      {/* Teams row */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <div
            className="w-4 h-4 rounded-sm flex items-center justify-center text-[8px] font-bold text-white"
            style={{ backgroundColor: event.homeTeam.primaryColor }}
          >
            {event.homeTeam.shortName.slice(0, 2)}
          </div>
          <span className="text-xs text-text-secondary">{event.homeTeam.shortName}</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="w-4 h-4 rounded-sm flex items-center justify-center text-[8px] font-bold text-white"
            style={{ backgroundColor: event.awayTeam.primaryColor }}
          >
            {event.awayTeam.shortName.slice(0, 2)}
          </div>
          <span className="text-xs text-text-secondary">{event.awayTeam.shortName}</span>
        </div>
      </div>

      {/* Probability bar + percentages */}
      <div className="flex items-center gap-2">
        <ProbabilityBar
          homeProb={event.homeProb}
          homeColor={event.homeTeam.primaryColor}
          awayColor={event.awayTeam.primaryColor}
          homeFavorite={homeFavorite}
          height={4}
        />
        <span className="font-mono text-[11px] text-text-secondary whitespace-nowrap">
          {Math.round(event.homeProb * 100)}% &nbsp; {Math.round(event.awayProb * 100)}%
        </span>
      </div>

      {/* Footer */}
      {event.openingOdds && (
        <div className="mt-2 text-[10px] text-text-muted">
          Opened {Math.round(event.openingOdds.home * 100)}/{Math.round(event.openingOdds.away * 100)}
        </div>
      )}
    </motion.div>
  );
}

// =============================================================================
// FUTURES CARD COMPONENT
// =============================================================================

function FuturesCard({ market }: { market: FuturesData }) {
  const accentColor = CATEGORY_COLORS[market.category];

  return (
    <motion.div
      variants={staggerItem}
      className={cn(
        "bg-surface-card border border-surface-border rounded-[10px] p-4",
        "transition-all cursor-pointer hover:bg-surface-elevated hover:shadow-card-hover hover:scale-[1.005]"
      )}
      style={{ borderTopWidth: "2px", borderTopColor: accentColor }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-text-muted uppercase tracking-widest font-semibold">
            {market.category}
          </span>
          <span className="text-[10px] bg-accent-futures/15 text-accent-futures px-1.5 py-0.5 rounded">
            {market.categoryLabel}
          </span>
          {market.sourceCount > 1 && (
            <span className="text-[10px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded font-medium">
              {market.sourceCount} sources
            </span>
          )}
        </div>
      </div>

      {/* Market name */}
      <h3 className="text-sm font-medium text-text-primary mb-3 leading-snug">
        {market.name}
      </h3>

      {/* Outcomes */}
      <motion.div className="space-y-2" variants={staggerContainer} initial="hidden" animate="visible">
        {market.outcomes.map((outcome, index) => (
          <motion.div key={outcome.id} variants={staggerItem}>
            <OutcomeRow
              outcome={outcome}
              rank={index + 1}
              isLeader={index === 0}
              accentColor={accentColor}
            />
          </motion.div>
        ))}
      </motion.div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-surface-border/50 flex justify-between items-center text-xs text-text-muted">
        <span>{market.source}</span>
        <span>Updated {market.updatedAt}</span>
      </div>
    </motion.div>
  );
}

function OutcomeRow({
  outcome,
  rank,
  isLeader,
  accentColor,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  accentColor: string;
}) {
  const isSignificant = outcome.movement && Math.abs(outcome.movement) >= 0.02;

  return (
    <div className="flex items-center gap-2">
      {/* Rank */}
      <span
        className={cn(
          "w-5 h-5 flex items-center justify-center text-[10px] rounded flex-shrink-0",
          isLeader ? "bg-accent-warning/15 text-accent-warning font-bold" : "text-text-muted"
        )}
      >
        {rank}
      </span>

      {/* Name + progress bar */}
      <div className="flex-1 min-w-0">
        <span
          className={cn(
            "text-sm truncate block",
            isLeader ? "font-medium text-text-primary" : "text-text-secondary"
          )}
        >
          {outcome.name}
        </span>
        <div className="h-1 rounded-full bg-surface-border mt-1 overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{
              backgroundColor: isLeader ? accentColor : "#475569",
              opacity: isLeader ? 0.7 : 0.3,
            }}
            animate={{ width: `${Math.min(outcome.probability * 100, 100)}%` }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          />
        </div>
      </div>

      {/* Movement + probability */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {outcome.movement && (
          <motion.span
            className={cn(
              "text-[11px] font-medium",
              outcome.movement > 0 ? "text-accent-live" : "text-accent-danger"
            )}
            {...(isSignificant
              ? {
                  animate: { opacity: [1, 0.5, 1] },
                  transition: { duration: 2, repeat: Infinity, ease: "easeInOut" },
                }
              : {})}
          >
            {outcome.movement > 0 ? "↑" : "↓"} {Math.abs(outcome.movement * 100).toFixed(1)}%
          </motion.span>
        )}
        <span
          className={cn(
            "font-mono text-sm tabular-nums",
            isLeader ? "font-bold text-text-primary" : "text-text-muted"
          )}
        >
          {Math.round(outcome.probability * 100)}%
        </span>
      </div>
    </div>
  );
}

// =============================================================================
// SKELETON CARD COMPONENT
// =============================================================================

function SkeletonCard() {
  return (
    <div className="bg-surface-card border border-surface-border rounded-[10px] p-4 animate-pulse">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div className="h-4 w-16 bg-surface-elevated rounded" />
        <div className="h-4 w-14 bg-surface-elevated rounded" />
      </div>

      {/* Team rows */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <div className="h-4 w-28 bg-surface-elevated rounded" />
          <div className="h-6 w-12 bg-surface-elevated rounded" />
        </div>
        <div className="h-[5px] w-full rounded-full bg-surface-elevated" />
        <div className="flex items-center justify-between gap-2">
          <div className="h-4 w-24 bg-surface-elevated rounded" />
          <div className="h-6 w-12 bg-surface-elevated rounded" />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-surface-border/50">
        <div className="h-3 w-32 bg-surface-elevated rounded" />
      </div>
    </div>
  );
}

// =============================================================================
// FILTER CHIPS
// =============================================================================

function FilterChips({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (chip: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide -mx-1 px-1">
      {FILTER_CHIPS.map((chip) => (
        <button
          key={chip.label}
          onClick={() => onSelect(chip.label)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium",
            "whitespace-nowrap transition-colors shrink-0",
            active === chip.label
              ? "bg-text-primary text-surface-deep"
              : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
          )}
        >
          <span className="text-sm leading-none">{chip.emoji}</span>
          {chip.label}
        </button>
      ))}
    </div>
  );
}

// =============================================================================
// SECTION HEADER
// =============================================================================

function SectionHeader({
  icon,
  title,
  count,
  accent,
}: {
  icon: string;
  title: string;
  count: number;
  accent?: string;
}) {
  return (
    <motion.div
      className="flex items-center gap-2 mb-3"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <span className="text-sm">{icon}</span>
      <h2 className={cn("text-sm font-semibold", accent || "text-text-primary")}>{title}</h2>
      <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
        {count}
      </span>
    </motion.div>
  );
}

// =============================================================================
// MAIN PAGE
// =============================================================================

export default function DemoPage() {
  const [activeFilter, setActiveFilter] = useState("All");
  const [showLoading, setShowLoading] = useState(false);

  const liveEvents = SAMPLE_EVENTS.filter((e) => e.status === "live");
  const finishedEvents = SAMPLE_EVENTS.filter((e) => e.status === "completed");
  const upcomingEvents = SAMPLE_EVENTS.filter((e) => e.status === "scheduled");

  return (
    <div className="min-h-screen bg-surface-deep">
      <div className="max-w-[1200px] mx-auto px-3 md:px-6 py-6">
        {/* Page title */}
        <div className="mb-6">
          <h1 className="text-title-1 text-text-primary mb-1">Bain Luck Feed Demo</h1>
          <p className="text-sm text-text-secondary">
            Showcasing all card types, states, and animations
          </p>
        </div>

        {/* Filter Chips */}
        <div className="mb-6">
          <FilterChips active={activeFilter} onSelect={setActiveFilter} />
        </div>

        {/* Toggle loading state */}
        <div className="mb-6">
          <button
            onClick={() => setShowLoading(!showLoading)}
            className="text-xs px-3 py-1.5 bg-surface-elevated text-text-secondary rounded-full hover:bg-surface-border transition-colors"
          >
            {showLoading ? "Hide Loading State" : "Show Loading State"}
          </button>
        </div>

        {showLoading ? (
          /* Loading/Skeleton State */
          <div className="space-y-8">
            <section>
              <SectionHeader icon="🔴" title="Loading..." count={6} />
              <div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                }}
              >
                {Array.from({ length: 6 }).map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            </section>
          </div>
        ) : (
          /* Main Feed Content */
          <div className="space-y-8">
            {/* Live Now Section */}
            <section>
              <SectionHeader icon="🔴" title="Live Now" count={liveEvents.length} accent="text-accent-live" />
              <motion.div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                }}
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
              >
                {liveEvents.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </motion.div>
            </section>

            {/* Just Happened Section */}
            <section>
              <SectionHeader icon="✅" title="Just Happened" count={finishedEvents.length} />
              <motion.div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                }}
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
              >
                {finishedEvents.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </motion.div>
            </section>

            {/* Upcoming Section */}
            <section>
              <SectionHeader icon="📅" title="Upcoming" count={upcomingEvents.length} />
              <motion.div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                }}
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
              >
                {upcomingEvents.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </motion.div>
            </section>

            {/* Top Markets (Futures) Section */}
            <section>
              <SectionHeader icon="🎯" title="Top Markets" count={SAMPLE_FUTURES.length} accent="text-accent-futures" />
              <motion.div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                }}
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
              >
                {SAMPLE_FUTURES.map((market) => (
                  <FuturesCard key={market.id} market={market} />
                ))}
              </motion.div>
            </section>

            {/* Compact Feed Cards */}
            <section>
              <SectionHeader icon="📊" title="Compact View" count={3} />
              <motion.div
                className="grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 280px), 1fr))",
                }}
                variants={staggerContainer}
                initial="hidden"
                animate="visible"
              >
                {liveEvents.map((event) => (
                  <CompactFeedCard key={`compact-${event.id}`} event={event} />
                ))}
              </motion.div>
            </section>
          </div>
        )}

        {/* Footer stats */}
        <p className="text-center text-xs text-text-muted pt-8">
          {SAMPLE_EVENTS.length} events · {SAMPLE_FUTURES.length} futures markets · Demo data
        </p>
      </div>
    </div>
  );
}
