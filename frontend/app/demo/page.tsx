"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Event, FuturesMarket } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import SkeletonCard from "@/components/SkeletonCard";
import FeedFilterChips from "@/components/FeedFilterChips";
import PlayerStatCard from "@/components/PlayerStatCard";
import ProgressionLadder from "@/components/ProgressionLadder";
import TeamPlayoffCard from "@/components/TeamPlayoffCard";
import { MOCK_TEAMS } from "@/lib/playoff-mock-data";
import { staggerContainer, staggerItem } from "@/lib/animations";

// =============================================================================
// MOCK DATA - Matches the real Event and FuturesMarket types
// =============================================================================

const now = new Date();
const later = new Date(now.getTime() + 3 * 60 * 60 * 1000); // 3 hours from now
const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

const MOCK_EVENTS: Event[] = [
  // SCHEDULED - upcoming game with projected scores
  {
    id: 1,
    external_id: "demo-1",
    sport: "basketball_nba",
    home_team: "Boston Celtics",
    away_team: "Miami Heat",
    commence_time: later.toISOString(),
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: now.toISOString(),
      home_probability: 0.62,
      away_probability: 0.38,
      spread: -5.5,
      over_under: 215.5,
      projected_home_score: 108,
      projected_away_score: 102,
    },
    home_team_data: {
      primary_color: "#007A33",
      secondary_color: "#BA9653",
      logo_small: null,
      logo_large: null,
      record: "42-18",
    },
    away_team_data: {
      primary_color: "#98002E",
      secondary_color: "#F9A01B",
      logo_small: null,
      logo_large: null,
      record: "34-26",
    },
    espn: {
      broadcast: "ESPN",
    },
  },
  // LIVE - exciting mid-game with high EI
  {
    id: 2,
    external_id: "demo-2",
    sport: "basketball_nba",
    home_team: "Golden State Warriors",
    away_team: "Los Angeles Lakers",
    commence_time: new Date(now.getTime() - 90 * 60 * 1000).toISOString(),
    status: "live",
    home_score: 78,
    away_score: 82,
    current_odds: {
      captured_at: now.toISOString(),
      home_probability: 0.42,
      away_probability: 0.58,
      spread: 2.5,
      over_under: 220.5,
      projected_home_score: null,
      projected_away_score: null,
    },
    opening_odds: {
      home_probability: 0.65,
      away_probability: 0.35,
      spread: -6.5,
      over_under: 218.5,
      favorite: "home",
    },
    ei: {
      score: 82,
      raw_score: 78,
      status: "exciting",
      label: "Exciting",
      emoji: "⚡",
    },
    highlight: {
      score: 85,
      reasons: ["favorite_switched", "close_game"],
      label: "Upset brewing",
      should_feature: true,
      flags: {
        is_live: true,
        is_close_matchup: true,
        is_blowout: false,
        favorite_switched: true,
        probability_swing: "major",
        score_swing: "minor",
        is_starting_soon: false,
        is_recently_finished: false,
        is_upset: true,
        league_tier: 1,
      },
    },
    home_team_data: {
      primary_color: "#1D428A",
      secondary_color: "#FFC72C",
      logo_small: null,
      logo_large: null,
      record: "38-22",
    },
    away_team_data: {
      primary_color: "#552583",
      secondary_color: "#FDB927",
      logo_small: null,
      logo_large: null,
      record: "36-24",
    },
    espn: {
      broadcast: "TNT",
      game_clock: "4:32",
      period: "3rd",
    },
  },
  // LIVE - NFL with very high EI (wild finish)
  {
    id: 3,
    external_id: "demo-3",
    sport: "americanfootball_nfl",
    home_team: "Kansas City Chiefs",
    away_team: "Buffalo Bills",
    commence_time: new Date(now.getTime() - 150 * 60 * 1000).toISOString(),
    status: "live",
    home_score: 24,
    away_score: 27,
    current_odds: {
      captured_at: now.toISOString(),
      home_probability: 0.38,
      away_probability: 0.62,
      spread: 3.5,
      over_under: 52.5,
      projected_home_score: null,
      projected_away_score: null,
    },
    opening_odds: {
      home_probability: 0.58,
      away_probability: 0.42,
      spread: -3.5,
      over_under: 48.5,
      favorite: "home",
    },
    ei: {
      score: 91,
      raw_score: 88,
      status: "incredible",
      label: "Must-Watch",
      emoji: "🔥",
    },
    highlight: {
      score: 92,
      reasons: ["wild_finish", "favorite_switched"],
      label: "Wild finish",
      should_feature: true,
      flags: {
        is_live: true,
        is_close_matchup: true,
        is_blowout: false,
        favorite_switched: true,
        probability_swing: "major",
        score_swing: "major",
        is_starting_soon: false,
        is_recently_finished: false,
        is_upset: true,
        league_tier: 1,
      },
    },
    home_team_data: {
      primary_color: "#E31837",
      secondary_color: "#FFB81C",
      logo_small: null,
      logo_large: null,
      record: "12-3",
    },
    away_team_data: {
      primary_color: "#00338D",
      secondary_color: "#C60C30",
      logo_small: null,
      logo_large: null,
      record: "11-4",
    },
    espn: {
      broadcast: "CBS",
      game_clock: "2:14",
      period: "4th",
    },
  },
  // COMPLETED - underdog won
  {
    id: 4,
    external_id: "demo-4",
    sport: "basketball_nba",
    home_team: "Miami Heat",
    away_team: "Boston Celtics",
    commence_time: yesterday.toISOString(),
    status: "completed",
    home_score: 102,
    away_score: 98,
    current_odds: {
      captured_at: yesterday.toISOString(),
      home_probability: 0.38,
      away_probability: 0.62,
      spread: 6.5,
      over_under: 210.5,
      projected_home_score: null,
      projected_away_score: null,
    },
    opening_odds: {
      home_probability: 0.35,
      away_probability: 0.65,
      spread: 7.5,
      over_under: 212.5,
      favorite: "away",
    },
    ei: {
      score: 78,
      status: "exciting",
      label: "Exciting",
      emoji: "⚡",
    },
    highlight: {
      score: 82,
      reasons: ["upset", "close_finish"],
      label: "Won as 35% underdog",
      should_feature: true,
      flags: {
        is_live: false,
        is_close_matchup: true,
        is_blowout: false,
        favorite_switched: false,
        probability_swing: "stable",
        score_swing: "stable",
        is_starting_soon: false,
        is_recently_finished: true,
        is_upset: true,
        league_tier: 1,
      },
    },
    home_team_data: {
      primary_color: "#98002E",
      secondary_color: "#F9A01B",
      logo_small: null,
      logo_large: null,
      record: "35-26",
    },
    away_team_data: {
      primary_color: "#007A33",
      secondary_color: "#BA9653",
      logo_small: null,
      logo_large: null,
      record: "42-19",
    },
  },
  // SCHEDULED - Soccer
  {
    id: 5,
    external_id: "demo-5",
    sport: "soccer_epl",
    home_team: "Manchester City",
    away_team: "Arsenal",
    commence_time: new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString(),
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      captured_at: now.toISOString(),
      home_probability: 0.52,
      away_probability: 0.28,
      spread: null,
      over_under: 2.5,
      projected_home_score: 2,
      projected_away_score: 1,
    },
    home_team_data: {
      primary_color: "#6CABDD",
      secondary_color: "#1C2C5B",
      logo_small: null,
      logo_large: null,
      record: null,
    },
    away_team_data: {
      primary_color: "#EF0107",
      secondary_color: "#063672",
      logo_small: null,
      logo_large: null,
      record: null,
    },
    espn: {
      broadcast: "NBC",
    },
  },
  // LIVE - MLB
  {
    id: 6,
    external_id: "demo-6",
    sport: "baseball_mlb",
    home_team: "New York Yankees",
    away_team: "Boston Red Sox",
    commence_time: new Date(now.getTime() - 120 * 60 * 1000).toISOString(),
    status: "live",
    home_score: 5,
    away_score: 3,
    current_odds: {
      captured_at: now.toISOString(),
      home_probability: 0.72,
      away_probability: 0.28,
      spread: null,
      over_under: 9.5,
      projected_home_score: null,
      projected_away_score: null,
    },
    opening_odds: {
      home_probability: 0.58,
      away_probability: 0.42,
      spread: null,
      over_under: 8.5,
      favorite: "home",
    },
    ei: {
      score: 45,
      status: "competitive",
      label: "Competitive",
      emoji: "💪",
    },
    home_team_data: {
      primary_color: "#003087",
      secondary_color: "#E4002C",
      logo_small: null,
      logo_large: null,
      record: "58-42",
    },
    away_team_data: {
      primary_color: "#BD3039",
      secondary_color: "#0C2340",
      logo_small: null,
      logo_large: null,
      record: "52-48",
    },
    espn: {
      broadcast: "YES",
      period: "7th",
    },
  },
];

const MOCK_FUTURES: FuturesMarket[] = [
  // Basketball championship
  {
    id: 101,
    name: "NBA Championship Winner 2025-26",
    description: "Which team will win the 2025-26 NBA Championship?",
    sport: "basketball_nba",
    sport_name: "NBA",
    category: "Championship",
    llm_sport_category: "basketball",
    status: "open",
    source: "odds_api",
    external_id: "nba-champ-2026",
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: "2026-06-30",
    outcome_count: 30,
    source_count: 4,
    created_at: now.toISOString(),
    updated_at: now.toISOString(),
    top_outcomes: [
      { id: 1001, name: "Boston Celtics", probability: 0.22, american_odds: 350, rank: 1, rank_change_24h: 0, probability_change_24h: 0.013, movement: 0.013, opening_probability: 0.18, opening_american_odds: 450, is_winner: null, last_updated: now.toISOString() },
      { id: 1002, name: "Oklahoma City Thunder", probability: 0.18, american_odds: 450, rank: 2, rank_change_24h: 0, probability_change_24h: null, movement: null, opening_probability: 0.15, opening_american_odds: 550, is_winner: null, last_updated: now.toISOString() },
      { id: 1003, name: "Cleveland Cavaliers", probability: 0.12, american_odds: 700, rank: 3, rank_change_24h: 1, probability_change_24h: -0.008, movement: -0.008, opening_probability: 0.14, opening_american_odds: 600, is_winner: null, last_updated: now.toISOString() },
      { id: 1004, name: "Denver Nuggets", probability: 0.09, american_odds: 1000, rank: 4, rank_change_24h: -1, probability_change_24h: null, movement: null, opening_probability: 0.10, opening_american_odds: 900, is_winner: null, last_updated: now.toISOString() },
      { id: 1005, name: "Golden State Warriors", probability: 0.07, american_odds: 1300, rank: 5, rank_change_24h: 0, probability_change_24h: null, movement: null, opening_probability: 0.08, opening_american_odds: 1150, is_winner: null, last_updated: now.toISOString() },
    ],
  },
  // Crypto prediction
  {
    id: 102,
    name: "Will Bitcoin exceed $150,000 by end of 2026?",
    description: "Bitcoin price target prediction market",
    sport: null,
    sport_name: null,
    category: "Price Target",
    llm_sport_category: "crypto",
    status: "open",
    source: "polymarket",
    external_id: "btc-150k-2026",
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: "2026-12-31",
    outcome_count: 2,
    source_count: 2,
    created_at: now.toISOString(),
    updated_at: now.toISOString(),
    top_outcomes: [
      { id: 1006, name: "Yes", probability: 0.42, american_odds: 138, rank: 1, rank_change_24h: 0, probability_change_24h: 0.034, movement: 0.034, opening_probability: 0.35, opening_american_odds: 186, is_winner: null, last_updated: now.toISOString() },
      { id: 1007, name: "No", probability: 0.58, american_odds: -138, rank: 2, rank_change_24h: 0, probability_change_24h: -0.034, movement: -0.034, opening_probability: 0.65, opening_american_odds: -186, is_winner: null, last_updated: now.toISOString() },
    ],
  },
  // Politics
  {
    id: 103,
    name: "2028 US Presidential Election Winner",
    description: "Which party will win the 2028 US Presidential Election?",
    sport: null,
    sport_name: null,
    category: "Election",
    llm_sport_category: "politics",
    status: "open",
    source: "kalshi",
    external_id: "pres-2028",
    mutually_exclusive: true,
    commence_time: null,
    resolution_date: "2028-11-05",
    outcome_count: 3,
    source_count: 1,
    created_at: now.toISOString(),
    updated_at: now.toISOString(),
    top_outcomes: [
      { id: 1008, name: "Democratic Nominee", probability: 0.48, american_odds: 108, rank: 1, rank_change_24h: 0, probability_change_24h: 0.02, movement: 0.02, opening_probability: 0.45, opening_american_odds: 122, is_winner: null, last_updated: now.toISOString() },
      { id: 1009, name: "Republican Nominee", probability: 0.46, american_odds: 117, rank: 2, rank_change_24h: 0, probability_change_24h: -0.015, movement: -0.015, opening_probability: 0.48, opening_american_odds: 108, is_winner: null, last_updated: now.toISOString() },
      { id: 1010, name: "Third Party", probability: 0.06, american_odds: 1567, rank: 3, rank_change_24h: 0, probability_change_24h: null, movement: null, opening_probability: 0.07, opening_american_odds: 1329, is_winner: null, last_updated: now.toISOString() },
    ],
  },
];

// =============================================================================
// DEMO PAGE COMPONENT
// =============================================================================

export default function DemoPage() {
  const [showLoading, setShowLoading] = useState(false);
  const [activeTags, setActiveTags] = useState<string[] | null>(null);

  const scheduledEvents = MOCK_EVENTS.filter(e => e.status === "scheduled");
  const liveEvents = MOCK_EVENTS.filter(e => e.status === "live");
  const finishedEvents = MOCK_EVENTS.filter(e => e.status === "completed" || e.status === "closed");

  return (
    <div className="min-h-screen bg-surface-bg">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-surface-bg/95 backdrop-blur-sm border-b border-surface-border">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-text-primary">Bain Luck</h1>
              <p className="text-sm text-text-muted">Component Demo Page</p>
            </div>
            <button
              onClick={() => setShowLoading(!showLoading)}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-medium transition-all",
                showLoading
                  ? "bg-accent-live/20 text-accent-live"
                  : "bg-surface-card text-text-secondary hover:bg-surface-elevated"
              )}
            >
              {showLoading ? "Hide Skeletons" : "Show Skeletons"}
            </button>
          </div>

          {/* Filter Chips */}
          <FeedFilterChips
            activeTags={activeTags}
            onTagChange={setActiveTags}
          />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-10">
        {/* Loading State Demo */}
        {showLoading && (
          <section>
            <SectionHeader
              title="Loading States"
              subtitle="Skeleton cards with pulse animation"
              count={3}
            />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          </section>
        )}

        {/* Live Events - Most prominent */}
        <section>
          <SectionHeader
            title="Live Now"
            subtitle="Games in progress with real-time EI scores"
            count={liveEvents.length}
            accent="live"
          />
          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            {liveEvents.map((event, index) => (
              <motion.div key={event.id} variants={staggerItem}>
                <EventCard
                  event={event}
                  showSport
                  sourceSection="featured"
                  positionIndex={index}
                  highlightLabel={event.highlight?.label}
                />
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* Scheduled Events */}
        <section>
          <SectionHeader
            title="Upcoming"
            subtitle="Games with projected scores and current odds"
            count={scheduledEvents.length}
          />
          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            {scheduledEvents.map((event, index) => (
              <motion.div key={event.id} variants={staggerItem}>
                <EventCard
                  event={event}
                  showSport
                  sourceSection="sport_category"
                  positionIndex={index}
                />
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* Finished Events */}
        <section>
          <SectionHeader
            title="Recently Finished"
            subtitle="Final scores with pre-game odds comparison"
            count={finishedEvents.length}
            accent="muted"
          />
          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            {finishedEvents.map((event, index) => (
              <motion.div key={event.id} variants={staggerItem}>
                <EventCard
                  event={event}
                  showSport
                  sourceSection="recently_finished"
                  positionIndex={index}
                  highlightLabel={event.highlight?.label}
                />
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* Futures Markets */}
        <section>
          <SectionHeader
            title="Futures Markets"
            subtitle="Long-term predictions with movement indicators"
            count={MOCK_FUTURES.length}
            accent="futures"
          />
          <motion.div
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            {MOCK_FUTURES.map((market) => (
              <motion.div key={market.id} variants={staggerItem}>
                <FuturesCard market={market} showSport />
              </motion.div>
            ))}
          </motion.div>
        </section>

        {/* Player Props & Progressions - mixed in with futures naturally */}
        <section className="border-t border-surface-border pt-10">
          <SectionHeader
            title="Player Props"
            subtitle="Tonight's games"
            accent="futures"
          />
          
          {/* Same grid as futures cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <PlayerStatCard
              playerName="Jayson Tatum"
              espnPlayerId="4065648"
              sportKey="basketball_nba"
              statCategory="points"
              eventMatchup="BOS @ MIA"
              eventTime={new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString()}
              lines={[
                { id: 1, name: "Tatum 20+ Points", probability: 0.92, threshold_value: 20, threshold_direction: "above", source: "kalshi" },
                { id: 2, name: "Tatum 25+ Points", probability: 0.78, threshold_value: 25, threshold_direction: "above", source: "kalshi" },
                { id: 3, name: "Tatum 30+ Points", probability: 0.52, threshold_value: 30, threshold_direction: "above", source: "kalshi" },
                { id: 4, name: "Tatum 35+ Points", probability: 0.28, threshold_value: 35, threshold_direction: "above", source: "kalshi" },
              ]}
            />
            <PlayerStatCard
              playerName="LeBron James"
              espnPlayerId="1966"
              sportKey="basketball_nba"
              statCategory="rebounds"
              eventMatchup="LAL @ DEN"
              eventTime={new Date(Date.now() + 5 * 60 * 60 * 1000).toISOString()}
              lines={[
                { id: 10, name: "LeBron 6+ Rebounds", probability: 0.88, threshold_value: 6, threshold_direction: "above", source: "polymarket" },
                { id: 11, name: "LeBron 8+ Rebounds", probability: 0.62, threshold_value: 8, threshold_direction: "above", source: "polymarket" },
                { id: 12, name: "LeBron 10+ Rebounds", probability: 0.35, threshold_value: 10, threshold_direction: "above", source: "polymarket" },
              ]}
            />
            <PlayerStatCard
              playerName="Stephen Curry"
              espnPlayerId="3975"
              sportKey="basketball_nba"
              statCategory="threes"
              eventMatchup="GSW @ PHX"
              eventTime={new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()}
              lines={[
                { id: 20, name: "Curry 3+ Threes", probability: 0.92, threshold_value: 3, threshold_direction: "above", source: "kalshi" },
                { id: 21, name: "Curry 5+ Threes", probability: 0.58, threshold_value: 5, threshold_direction: "above", source: "kalshi" },
                { id: 22, name: "Curry 7+ Threes", probability: 0.22, threshold_value: 7, threshold_direction: "above", source: "kalshi" },
              ]}
            />
            <ProgressionLadder
              entityName="Los Angeles Lakers"
              stages={[
                { id: 1, name: "Lakers Make Playoffs", stage_name: "Playoffs", stage_order: 1, probability: 0.85, status: "achieved" },
                { id: 2, name: "Lakers Make Round 2", stage_name: "Round 2", stage_order: 2, probability: 0.45 },
                { id: 3, name: "Lakers Make WCF", stage_name: "Conf Finals", stage_order: 3, probability: 0.22 },
                { id: 4, name: "Lakers Win Championship", stage_name: "Champion", stage_order: 4, probability: 0.06 },
              ]}
              teamColors={{ primary: "85, 37, 130", secondary: "253, 185, 39" }}
            />
            <ProgressionLadder
              entityName="Boston Celtics"
              stages={[
                { id: 40, name: "Celtics Make Playoffs", stage_name: "Playoffs", stage_order: 1, probability: 0.99, status: "achieved" },
                { id: 41, name: "Celtics Make R2", stage_name: "Round 2", stage_order: 2, probability: 0.82, status: "achieved" },
                { id: 42, name: "Celtics Make ECF", stage_name: "Conf Finals", stage_order: 3, probability: 0.65 },
                { id: 43, name: "Celtics Win Title", stage_name: "Champion", stage_order: 4, probability: 0.28 },
              ]}
              teamColors={{ primary: "0, 122, 51", secondary: "186, 150, 83" }}
            />
            <PlayerStatCard
              playerName="Nikola Jokic"
              espnPlayerId="3112335"
              sportKey="basketball_nba"
              statCategory="assists"
              eventMatchup="DEN vs LAL"
              eventTime={new Date(Date.now() + 5 * 60 * 60 * 1000).toISOString()}
              lines={[
                { id: 30, name: "Jokic 8+ Assists", probability: 0.75, threshold_value: 8, threshold_direction: "above", source: "odds_api" },
                { id: 31, name: "Jokic 10+ Assists", probability: 0.42, threshold_value: 10, threshold_direction: "above", source: "odds_api" },
                { id: 32, name: "Jokic 12+ Assists", probability: 0.18, threshold_value: 12, threshold_direction: "above", source: "odds_api" },
              ]}
            />
          </div>
        </section>

        {/* Playoff Components */}
        <section className="border-t border-surface-border pt-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <SectionHeader
                title="Championship Probability"
                subtitle="TeamPlayoffCard — horizontal probability funnel per team"
              />
            </div>
            <Link
              href="/demo/playoffs"
              className="text-xs px-3 py-1.5 rounded-full border transition-colors text-text-secondary hover:text-text-primary"
              style={{ borderColor: "var(--surface-border)" }}
            >
              Full grid demo →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl">
            <TeamPlayoffCard
              team={MOCK_TEAMS.find((t) => t.short === "OKC")!}
              gridHref="/demo/playoffs"
            />
            <TeamPlayoffCard
              team={MOCK_TEAMS.find((t) => t.short === "BOS")!}
              gridHref="/demo/playoffs"
            />
          </div>
        </section>

        {/* Visual Comparison Section */}
        <section className="border-t border-surface-border pt-10">
          <h2 className="text-xl font-bold text-text-primary mb-2">Visual Differences Guide</h2>
          <p className="text-text-muted mb-6">How to identify card states at a glance</p>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-surface-card border border-surface-border rounded-xl p-4">
              <h3 className="font-semibold text-text-primary mb-3">Scheduled Events</h3>
              <ul className="space-y-2 text-sm text-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>No left border accent</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Shows game time in header</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>No score display section</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Footer shows projected score</span>
                </li>
              </ul>
            </div>

            <div className="bg-surface-card border border-surface-border rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-4 bg-accent-live rounded-full" />
                <h3 className="font-semibold text-text-primary">Live Events</h3>
              </div>
              <ul className="space-y-2 text-sm text-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="text-accent-live">-</span>
                  <span>Green left border + ring glow</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-live">-</span>
                  <span>Pulsing LIVE badge with dot</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-live">-</span>
                  <span>Green-tinted score section</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-live">-</span>
                  <span>EI badge (breathing on high EI)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-live">-</span>
                  <span>Footer shows opening odds</span>
                </li>
              </ul>
            </div>

            <div className="bg-surface-card border border-surface-border rounded-xl p-4 opacity-80">
              <h3 className="font-semibold text-text-primary mb-3">Finished Events</h3>
              <ul className="space-y-2 text-sm text-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Reduced opacity (80%)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>FINAL label in header</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Muted score section background</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Winner score is brighter</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-text-muted">-</span>
                  <span>Footer shows pre-game odds</span>
                </li>
              </ul>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

// =============================================================================
// SECTION HEADER COMPONENT
// =============================================================================

function SectionHeader({
  title,
  subtitle,
  count,
  accent,
}: {
  title: string;
  subtitle?: string;
  count?: number;
  accent?: "live" | "futures" | "muted";
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <div className="flex items-center gap-2">
          <h2 className={cn(
            "text-lg font-semibold",
            accent === "live" ? "text-accent-live" : 
            accent === "futures" ? "text-accent-futures" :
            accent === "muted" ? "text-text-muted" : "text-text-primary"
          )}>
            {title}
          </h2>
          {count !== undefined && (
            <span className="text-xs bg-surface-elevated text-text-muted px-2 py-0.5 rounded-full">
              {count}
            </span>
          )}
        </div>
        {subtitle && (
          <p className="text-sm text-text-muted mt-0.5">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
