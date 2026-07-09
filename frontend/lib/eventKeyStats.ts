/**
 * Extracted helpers for the event detail page (events/[id]/page.tsx).
 *
 * Pure functions and constants that were previously inlined in the
 * EventPage component.  Keeping them here makes the page component a
 * thin orchestrator and each helper independently testable.
 */

import { format as fmtDate } from "date-fns";
import type {
  EventHistoryResponse,
  EventDetailResponse,
  ActiveChartPoint,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maps Odds API sport keys to sport hierarchy paths */
export const SPORT_KEY_TO_LEAGUE_PATH: Record<
  string,
  { path: string; label: string }
> = {
  basketball_nba: { path: "/sport/basketball/nba", label: "NBA" },
  americanfootball_nfl: { path: "/sport/football/nfl", label: "NFL" },
  baseball_mlb: { path: "/sport/baseball/mlb", label: "MLB" },
  icehockey_nhl: { path: "/sport/hockey/nhl", label: "NHL" },
  basketball_ncaab: {
    path: "/sport/basketball/ncaab",
    label: "NCAA Basketball",
  },
  americanfootball_ncaaf: {
    path: "/sport/football/ncaaf",
    label: "NCAA Football",
  },
  basketball_wnba: { path: "/sport/basketball/wnba", label: "WNBA" },
  soccer_usa_mls: { path: "/sport/soccer/mls", label: "MLS" },
  soccer_epl: { path: "/sport/soccer/epl", label: "EPL" },
  soccer_spain_la_liga: { path: "/sport/soccer/laliga", label: "La Liga" },
  soccer_uefa_champs_league: {
    path: "/sport/soccer/ucl",
    label: "Champions League",
  },
  soccer_germany_bundesliga: {
    path: "/sport/soccer/bundesliga",
    label: "Bundesliga",
  },
  basketball_wncaab: {
    path: "/sport/basketball/wncaab",
    label: "NCAA Basketball",
  },
};

/** Human-readable labels for event tags (namespace:value → display) */
export const TAG_LABELS: Record<string, string> = {
  "importance:championship": "Championship",
  "importance:playoff": "Playoff",
  "importance:exhibition": "Exhibition",
  "signal:close_matchup": "Close Game",
  "signal:upset": "Upset",
  "signal:line_moving": "Line Moving",
  "signal:blowout": "Blowout",
  "timing:primetime": "Primetime",
  "timing:national_tv": "National TV",
  "timing:weekend": "Weekend",
  "tier:1": "Major",
  "tier:2": "Tier 2",
  "ei:must_watch": "Must-Watch",
  "ei:incredible": "Incredible",
  "ei:exciting": "Exciting",
  "stakes:elimination": "Elimination",
  "stakes:clinch": "Clinch Scenario",
  "stakes:playoff_race": "Playoff Race",
  "stakes:title_defense": "Title Defense",
  "stakes:must_win": "Must-Win",
  "stakes:record_chase": "Record Chase",
  "stakes:seeding": "Seeding",
  "stakes:streak": "Streak",
  "narrative:rivalry": "Rivalry",
  "narrative:historic_rivalry": "Historic Rivalry",
  "narrative:revenge_game": "Revenge Game",
  "narrative:cinderella": "Cinderella",
  "narrative:upset_alert": "Upset Alert",
  "narrative:comeback": "Comeback",
  "narrative:rematch": "Rematch",
  "narrative:david_vs_goliath": "David vs. Goliath",
  "narrative:farewell_tour": "Farewell Tour",
  "narrative:winning_streak": "Winning Streak",
  "narrative:losing_streak": "Losing Streak",
  "narrative:debut": "Debut",
  "narrative:return_from_injury": "Return from Injury",
  "audience:national_interest": "National Interest",
  "audience:crossover_appeal": "Crossover Appeal",
  "audience:viral_potential": "Viral Potential",
  "audience:casual_friendly": "Casual-Friendly",
  "competitive_structure:knockout": "Knockout",
  "competitive_structure:single_elimination": "Single Elimination",
  "competitive_structure:bracket": "Bracket",
  "competitive_structure:series": "Series",
  "competitive_structure:best_of_7": "Best of 7",
  "competitive_structure:group_stage": "Group Stage",
};

/** CSS classes per tag namespace */
export const TAG_COLORS: Record<string, string> = {
  importance: "bg-purple-50 text-purple-600",
  signal: "bg-orange-50 text-orange-600",
  timing: "bg-yellow-50 text-yellow-700",
  tier: "bg-blue-50 text-blue-600",
  ei: "bg-emerald-50 text-emerald-600",
  stakes: "bg-red-50 text-red-600",
  narrative: "bg-amber-50 text-amber-600",
  audience: "bg-cyan-50 text-cyan-600",
  competitive_structure: "bg-indigo-50 text-indigo-600",
};

/** Tag namespace allowlist for the hero section */
const DISPLAY_TAG_NAMESPACES = new Set([
  "importance",
  "signal",
  "timing",
  "tier",
  "ei",
  "stakes",
  "narrative",
  "audience",
  "competitive_structure",
]);

/** Tags suppressed from display even when their namespace qualifies */
const SUPPRESSED_TAGS = new Set([
  "competitive_structure:head_to_head",
  "audience:local_interest",
  "stakes:meaningless",
]);

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

/** Pick key season stats to display based on sport */
export function getKeyStats(
  stats: Record<string, number | string> | null | undefined,
  sportKey: string | undefined,
): Array<{ label: string; value: string | number }> {
  if (!stats) return [];
  const result: Array<{ label: string; value: string | number }> = [];
  const s = sportKey?.toLowerCase() || "";

  if (s.includes("basketball")) {
    if (stats.ppg != null) result.push({ label: "PPG", value: stats.ppg });
    if (stats.rpg != null) result.push({ label: "RPG", value: stats.rpg });
    if (stats.apg != null) result.push({ label: "APG", value: stats.apg });
    if (stats.opp_ppg != null)
      result.push({ label: "Opp PPG", value: stats.opp_ppg });
  } else if (s.includes("football")) {
    if (stats.points_per_game != null)
      result.push({ label: "PTS/G", value: stats.points_per_game });
    if (stats.yards_per_game != null)
      result.push({ label: "YDS/G", value: stats.yards_per_game });
    if (stats.opp_points_per_game != null)
      result.push({ label: "Opp PTS/G", value: stats.opp_points_per_game });
  } else if (s.includes("baseball")) {
    if (stats.batting_avg != null)
      result.push({ label: "AVG", value: stats.batting_avg });
    if (stats.era != null) result.push({ label: "ERA", value: stats.era });
    if (stats.runs_per_game != null)
      result.push({ label: "R/G", value: stats.runs_per_game });
  } else if (s.includes("hockey")) {
    if (stats.goals_for_per_game != null)
      result.push({ label: "GF/G", value: stats.goals_for_per_game });
    if (stats.goals_against_per_game != null)
      result.push({ label: "GA/G", value: stats.goals_against_per_game });
    if (stats.power_play_pct != null)
      result.push({ label: "PP%", value: stats.power_play_pct });
  } else if (s.includes("soccer")) {
    if (stats.goals_per_game != null)
      result.push({ label: "G/G", value: stats.goals_per_game });
    if (stats.clean_sheets != null)
      result.push({ label: "CS", value: stats.clean_sheets });
    if (stats.goals_against_per_game != null)
      result.push({ label: "GA/G", value: stats.goals_against_per_game });
  } else {
    // Generic: show first 3 numeric stats
    for (const [key, val] of Object.entries(stats)) {
      if (result.length >= 3) break;
      if (
        typeof val === "number" ||
        (typeof val === "string" && !isNaN(Number(val)))
      ) {
        result.push({
          label: key
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase()),
          value: val,
        });
      }
    }
  }
  return result.slice(0, 4);
}

/** Check if history response has ANY win probability data beyond sportsbook odds. */
export function hasAnyWinProbData(data: EventHistoryResponse | null | undefined): boolean {
  if (!data) return false;
  if (data.espn_history && data.espn_history.length > 0) return true;
  if (data.win_prob_history) {
    for (const points of Object.values(data.win_prob_history)) {
      if (Array.isArray(points) && points.length > 0) return true;
    }
  }
  return false;
}

/** Format a future timestamp as a human-readable countdown (e.g. "2d 5h"). */
export function formatCountdown(targetTime: string): string {
  const target = new Date(targetTime);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "";

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/** Format a start time as a relative label (Today/Tomorrow) or short date. */
export function formatStartTime(commenceTime: string): string {
  const date = new Date(commenceTime);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  if (date.toDateString() === today.toDateString()) {
    return `Today at ${timeStr}`;
  } else if (date.toDateString() === tomorrow.toDateString()) {
    return `Tomorrow at ${timeStr}`;
  } else {
    const dateStr = date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    return `${dateStr} at ${timeStr}`;
  }
}

/** Filter event tags to the displayable subset for the hero section. */
export function filterDisplayTags(
  tags: string[] | undefined,
): string[] | null {
  if (!tags || tags.length === 0) return null;
  const display = tags.filter((t) => {
    const ns = t.split(":")[0];
    return DISPLAY_TAG_NAMESPACES.has(ns);
  });
  const filtered = display.filter((t) => !SUPPRESSED_TAGS.has(t));
  return filtered.length > 0 ? filtered : null;
}

// ---------------------------------------------------------------------------
// Probability resolution
// ---------------------------------------------------------------------------

export interface ResolvedProbability {
  homeProb: number | null;
  awayProb: number | null;
  probSourceLabel: string | null;
  openingHomeProb: number | null;
  openingAwayProb: number | null;
}

/**
 * Determine the probability to display based on game status.
 *
 *   - Scheduled: current betting consensus
 *   - Live: current live odds (history cross-check for reliability) + opening
 *   - Completed/Closed: opening odds ("what was expected before the game")
 */
export function resolveProbability(
  event: EventDetailResponse,
  historyData: EventHistoryResponse | undefined,
  lastChartPoint: ActiveChartPoint | null,
  isLive: boolean,
  isFinished: boolean,
): ResolvedProbability {
  const odds = event.current_odds;
  const opening = event.opening_odds;

  let homeProb: number | null = null;
  let awayProb: number | null = null;
  let probSourceLabel: string | null = null;
  const openingHomeProb = opening?.home_probability ?? null;
  const openingAwayProb = opening?.away_probability ?? null;

  if (isFinished) {
    // Completed/closed: show opening odds
    homeProb = openingHomeProb;
    awayProb = openingAwayProb;
    if (homeProb !== null) {
      probSourceLabel = "Pre-game odds";
    } else {
      homeProb = odds?.home_probability ?? null;
      awayProb = odds?.away_probability ?? null;
    }
  } else if (isLive) {
    // Live: show current odds, cross-checked against history
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;

    if (historyData?.history && historyData.history.length > 0) {
      let latestValidHistory: (typeof historyData.history)[0] | null = null;
      for (let i = historyData.history.length - 1; i >= 0; i--) {
        if (
          historyData.history[i].home_probability !== null &&
          historyData.history[i].home_probability !== undefined
        ) {
          latestValidHistory = historyData.history[i];
          break;
        }
      }
      if (latestValidHistory) {
        const historyHome = latestValidHistory.home_probability!;
        const historyBookmakers = latestValidHistory.bookmaker_count ?? 0;
        if (homeProb === null || Math.abs(historyHome - homeProb) > 0.05) {
          homeProb = historyHome;
          awayProb =
            latestValidHistory.away_probability ?? 1 - historyHome;
          if (historyBookmakers > 0) {
            probSourceLabel = `Live · ${historyBookmakers} sportsbook${historyBookmakers !== 1 ? "s" : ""}`;
          }
        }
      }
    }
    if (!probSourceLabel && count > 0) {
      probSourceLabel = `Live · ${count} sportsbook${count !== 1 ? "s" : ""}`;
    }
    if (!probSourceLabel && homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Live · Aggregate";
    }
  } else {
    // Scheduled: current betting consensus
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {
      probSourceLabel = `${count} sportsbook${count !== 1 ? "s" : ""}`;
    } else if (homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Aggregate";
    }
  }

  // Fallback: use win_prob_history (ESPN/stat_model/Kalshi)
  if (
    homeProb === null &&
    lastChartPoint &&
    lastChartPoint.homeProb !== 0.5 &&
    !(
      isFinished &&
      (lastChartPoint.homeProb > 0.95 || lastChartPoint.homeProb < 0.05)
    )
  ) {
    homeProb = lastChartPoint.homeProb;
    awayProb = lastChartPoint.awayProb;
    const wpSources = historyData?.win_prob_sources;
    if (wpSources && Object.keys(wpSources).length > 0) {
      const sourceNames = Object.keys(wpSources).map((s) =>
        s === "stat_model"
          ? "Model"
          : s === "espn"
            ? "ESPN"
            : s.charAt(0).toUpperCase() + s.slice(1),
      );
      probSourceLabel = isLive
        ? `Live · ${sourceNames.join(", ")}`
        : sourceNames.join(", ");
    }
  }

  return { homeProb, awayProb, probSourceLabel, openingHomeProb, openingAwayProb };
}

// ---------------------------------------------------------------------------
// Chart domain computation
// ---------------------------------------------------------------------------

export interface SharedChartDomain {
  start: string;
  end: string;
  ticks: string[];
}

/**
 * Compute the shared x-axis domain for OddsChart and ScoreDifferentialChart.
 *
 * Collects all timestamps from every history source, computes start/end
 * based on `timeRange`, and generates evenly-spaced tick labels so both
 * charts render identical axes.
 */
export function computeSharedChartDomain(
  historyData: EventHistoryResponse | null | undefined,
  chartTimeRange: "all" | "live",
  eventStatus: string | undefined,
  commenceTime: string | undefined,
  sport: string | undefined,
): SharedChartDomain | null {
  if (!historyData) return null;

  const timestamps: number[] = [];
  for (const pt of historyData.history ?? []) {
    const t = new Date(pt.timestamp).getTime();
    if (!isNaN(t)) timestamps.push(t);
  }
  for (const pts of Object.values(historyData.win_prob_history ?? {})) {
    for (const pt of pts) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
  }
  for (const pt of historyData.espn_history ?? []) {
    const t = new Date(pt.timestamp).getTime();
    if (!isNaN(t)) timestamps.push(t);
  }
  for (const pts of Object.values(historyData.bookmaker_history ?? {})) {
    for (const pt of pts) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) timestamps.push(t);
    }
  }
  if (timestamps.length === 0) return null;

  const allStart = new Date(Math.min(...timestamps));
  let end = new Date(Math.max(...timestamps));

  // For completed games, derive end from game-end sources only.
  // If sportsbook data extends slightly beyond (within 10 min), include it
  // to avoid premature chart cutoff when ESPN data is sparse.
  const isCompleted = eventStatus === "completed" || eventStatus === "closed";
  if (isCompleted) {
    const GAME_END_SOURCES = new Set([
      "espn",
      "stat_model",
      "fangraphs",
      "mlb",
    ]);
    const gameEndTs: number[] = [];

    for (const pt of historyData.espn_history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t)) gameEndTs.push(t);
    }
    for (const [source, pts] of Object.entries(
      historyData.win_prob_history ?? {},
    )) {
      if (!GAME_END_SOURCES.has(source)) continue;
      for (const pt of pts) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) gameEndTs.push(t);
      }
    }

    if (gameEndTs.length > 0) {
      const lastGameEnd = Math.max(...gameEndTs);

      // Check if sportsbook data extends slightly beyond game-end sources.
      // This prevents premature cutoff when ESPN data is sparse (e.g.,
      // baseball chart cutting off at 8th inning).
      let endMs = lastGameEnd;
      const MAX_EXTENSION_MS = 10 * 60 * 1000; // 10 min max extension
      const bettingTs: number[] = [];
      for (const pt of historyData.history ?? []) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) bettingTs.push(t);
      }
      if (bettingTs.length > 0) {
        const lastBetting = Math.max(...bettingTs);
        if (lastBetting > lastGameEnd && lastBetting - lastGameEnd <= MAX_EXTENSION_MS) {
          endMs = lastBetting;
        }
      }

      const lastData = new Date(endMs);
      lastData.setMinutes(lastData.getMinutes() + 5);
      end = lastData;
    } else if (historyData.history && historyData.history.length > 0) {
      // No game-end sources — use sportsbook data with buffer
      const bettingTs: number[] = [];
      for (const pt of historyData.history) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) bettingTs.push(t);
      }
      if (bettingTs.length > 0) {
        const lastBetting = new Date(Math.max(...bettingTs));
        lastBetting.setMinutes(lastBetting.getMinutes() + 5);
        end = lastBetting;
      }
    } else if (commenceTime) {
      const ct = new Date(commenceTime);
      if (!isNaN(ct.getTime())) {
        const sportStr = sport || "";
        const isSoccer = sportStr.startsWith("soccer");
        const isTennis = sportStr.startsWith("tennis");
        const isCricket = sportStr.startsWith("cricket");
        const durationMin = isSoccer
          ? 110
          : isTennis
            ? 180
            : isCricket
              ? 240
              : 150;
        const estimated = new Date(ct.getTime() + durationMin * 60_000);
        end = estimated < end ? estimated : end;
      }
    } else if (historyData.completed_at) {
      const ca = new Date(historyData.completed_at);
      if (!isNaN(ca.getTime())) {
        end = ca;
      }
    }
  }

  // "Since Start" mode: start from commenceTime
  const gameStart = commenceTime ? new Date(commenceTime) : null;
  const liveStart =
    gameStart && !isNaN(gameStart.getTime()) ? gameStart : allStart;

  // "All" mode: cap the start to at most 2 hours before commenceTime for
  // completed/closed games. Prevents charts from showing many hours of
  // flat pre-game odds data that makes the in-game chart unreadable.
  let allModeStart = allStart;
  if (isCompleted && gameStart && !isNaN(gameStart.getTime())) {
    const twoHoursBefore = new Date(gameStart.getTime() - 2 * 60 * 60 * 1000);
    if (allModeStart < twoHoursBefore) {
      allModeStart = twoHoursBefore;
    }
  }

  const start = chartTimeRange === "live" ? liveStart : allModeStart;
  start.setSeconds(0, 0);
  end.setSeconds(0, 0);

  // Compute explicit X-axis ticks at clean time boundaries
  const durationMs = end.getTime() - start.getTime();
  const durationMin = durationMs / 60000;
  let intervalMin = durationMin < 180 ? 30 : 60;
  while (durationMin / intervalMin > 10) intervalMin *= 2;

  const ticks: string[] = [];
  ticks.push(fmtDate(start, "h:mm a"));

  const cursor = new Date(start);
  const curMins = cursor.getMinutes();
  const nextBoundary = Math.ceil((curMins + 1) / intervalMin) * intervalMin;
  cursor.setMinutes(nextBoundary, 0, 0);
  while (cursor < end) {
    ticks.push(fmtDate(cursor, "h:mm a"));
    cursor.setMinutes(cursor.getMinutes() + intervalMin);
  }

  const endLabel = fmtDate(end, "h:mm a");
  if (ticks[ticks.length - 1] !== endLabel) {
    ticks.push(endLabel);
  }

  return { start: start.toISOString(), end: end.toISOString(), ticks };
}

// ---------------------------------------------------------------------------
// Real start time computation
// ---------------------------------------------------------------------------

/**
 * Compute the real game start time from livescores data.
 *
 * Priority: StatPal score_history > ESPN > win_prob_history.
 * If the earliest live data point is >3 min later than nominal commence_time,
 * use the livescores timestamp instead.
 */
export function computeRealStartTime(
  commenceTime: string | undefined,
  historyData: EventHistoryResponse | null | undefined,
): string | undefined {
  if (!commenceTime) return undefined;
  const nominalMs = new Date(commenceTime).getTime();

  let earliestLive = Infinity;

  if (historyData?.score_history?.length) {
    const first = new Date(historyData.score_history[0].timestamp).getTime();
    if (first < earliestLive) earliestLive = first;
  }
  if (historyData?.espn_history?.length) {
    const first = new Date(historyData.espn_history[0].timestamp).getTime();
    if (first < earliestLive) earliestLive = first;
  }
  if (historyData?.win_prob_history) {
    for (const points of Object.values(historyData.win_prob_history)) {
      if (points.length > 0) {
        const first = new Date(points[0].timestamp).getTime();
        if (first < earliestLive) earliestLive = first;
      }
    }
  }

  if (earliestLive !== Infinity && earliestLive > nominalMs + 3 * 60 * 1000) {
    return new Date(earliestLive).toISOString();
  }
  return commenceTime;
}

// ---------------------------------------------------------------------------
// Last chart point computation
// ---------------------------------------------------------------------------

/**
 * Compute the most recent chart point for GamePlayCard default display.
 */
export function computeLastChartPoint(
  historyData: EventHistoryResponse | null | undefined,
  homeScore: number | null | undefined,
  awayScore: number | null | undefined,
): ActiveChartPoint | null {
  if (!historyData) return null;

  const espn = historyData.espn_history;
  const lastEspn = espn?.length ? espn[espn.length - 1] : null;

  const wpHistory = historyData.win_prob_history;
  let lastWp: { home_probability: number | null; timestamp: string } | null =
    null;
  if (wpHistory) {
    for (const pts of Object.values(wpHistory)) {
      if (pts.length) {
        const last = pts[pts.length - 1];
        if (!lastWp || last.timestamp > lastWp.timestamp) {
          lastWp = last;
        }
      }
    }
  }

  const hist = historyData.history;
  const lastHist = hist?.length ? hist[hist.length - 1] : null;

  // #1003: `history[].home_probability` is a 0–1 FRACTION (API-verified — same as
  // win_prob_history, current_odds, bookmaker_odds), NOT 0–100. The old `/ 100`
  // here made the headline fallback show ~1% while the chart tooltip (OddsChart
  // multiplies the same field by 100) correctly showed ~81% — the reported
  // tooltip-vs-headline mismatch. It fired whenever win_prob_history was empty
  // (any live sport without an ESPN/stat win-prob source, e.g. cricket/soccer).
  const homeProb =
    lastWp?.home_probability ??
    lastHist?.home_probability ??
    0.5;

  return {
    timestamp:
      lastEspn?.timestamp ||
      lastWp?.timestamp ||
      lastHist?.timestamp ||
      "",
    homeProb,
    awayProb: 1 - homeProb,
    homeScore: lastEspn?.home_score ?? homeScore ?? null,
    awayScore: lastEspn?.away_score ?? awayScore ?? null,
    period: lastEspn?.period?.toString() ?? null,
    clock: lastEspn?.game_clock ?? null,
  };
}
