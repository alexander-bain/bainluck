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
  CurrentOdds,
  ScoringPlay,
} from "@/lib/types";
import {
  categoryLabelFormat,
  CATEGORY_LABEL_FORMAT,
} from "@/lib/chartTimeline";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { renderedDuelPercents } from "@/lib/renderedPercent";

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

/**
 * How close to its start an event has to be before the header's poll countdown
 * is worth showing. Reuses the window `sportCategories.ts` already ships as
 * "starting soon" (`hoursUntil <= 3`) rather than inventing a second one, so
 * the two surfaces cannot drift into disagreeing about what "soon" means.
 */
export const REFRESH_COUNTDOWN_WINDOW_MS = 3 * 60 * 60 * 1000;

/**
 * Should the event header draw its "Next update: NN" ring? (#3802)
 *
 * The ring counts down the page's own poll, and the page polls every two
 * minutes whether the match is in ten minutes or in three days. Gated only on
 * `!isFinished && !streamConnected`, it therefore promised "next update in 109
 * seconds" over a US Open quarter-final **34 hours away** — a true sentence
 * about our poll that reads as a false one about the match, on the page a
 * reader opens precisely to find out when something will happen. It is also
 * the third element in a `justify-between` row that only has space for two at
 * 390px, so the same countdown wrapped the header into three ragged lines.
 *
 * A countdown earns its place when an update could plausibly land while the
 * reader is looking: the event is live, it is past its start with no reported
 * result, or it starts within the window above. A pregame match days out is
 * told when it starts by the hero ("Starts in 1d 10h") — the poll clock adds
 * nothing there and costs the header its layout.
 *
 * Pure and exported because a Next.js page may not carry named exports, so
 * this is the only seam a guard can hold.
 */
export function shouldShowRefreshCountdown(args: {
  isFinished: boolean;
  streamConnected: boolean;
  isLive: boolean;
  isSuspended: boolean;
  commenceTime: string | null | undefined;
  now?: Date;
}): boolean {
  const { isFinished, streamConnected, isLive, isSuspended, commenceTime } = args;

  // Unchanged: a finished event has nothing to refresh, and a pushed event
  // shows its age stamp instead (live/034 S2).
  if (isFinished || streamConnected) return false;

  // An event that is live, or past its start with no result reported, is
  // exactly the case the ring was written for.
  if (isLive || isSuspended) return true;

  // No start time is not a licence to promise an update — an event we cannot
  // place in time is the last one that should carry a confident clock.
  if (!commenceTime) return false;

  const startMs = new Date(commenceTime).getTime();
  if (isNaN(startMs)) return false;

  const nowMs = (args.now ?? new Date()).getTime();
  return startMs - nowMs <= REFRESH_COUNTDOWN_WINDOW_MS;
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
  // #2085 — the WHOLE PERCENTS the hero prints for the pair above, decided
  // together. Every pair this function can return is an exact complement by
  // construction on the backend (`1 - home`, at four separate sites), so
  // rounding the two sides independently prints 101 whenever `home * 100` lands
  // on a half-percent — 34 of 414 scheduled/live events, measured 2026-08-21.
  // It can print 101; it can never print 99.
  //
  // These are the numbers to PRINT. `homeProb`/`awayProb` are unchanged and
  // remain the numbers to reason with — the chart's right edge, the trend
  // delta and `data-probability` all still read them.
  homePct: number | null;
  awayPct: number | null;
  // The same decision for the "Opened away – home" line, which draws
  // `opening_odds` and derives its away side the same way (routes/events.py's
  // `opening_away_probability or round(1 - home, 4)`).
  openingHomePct: number | null;
  openingAwayPct: number | null;
}

/**
 * The most recent valid home-win probability from the backend blend line
 * (aggregate_line — the weighted-median "Bain Luck" line the chart draws).
 * Returns null when there is no usable blend point yet. Walks backwards so a
 * trailing null/undefined doesn't hide a good earlier value.
 */
export function latestBlendPoint(
  aggregateLine: Array<{ timestamp: string; home_probability: number }> | null | undefined,
): number | null {
  if (!aggregateLine || aggregateLine.length === 0) return null;
  for (let i = aggregateLine.length - 1; i >= 0; i--) {
    const p = aggregateLine[i]?.home_probability;
    if (typeof p === "number" && !isNaN(p)) return p;
  }
  return null;
}

/**
 * The ONE conversion between a 0–1 home win-probability — the scale of every
 * payload field (current_odds, opening_odds, history[], win_prob_history,
 * aggregate_line) and every non-chart surface (hero, discover card, readout) —
 * and the chart's internal 0–100 axis.
 *
 * #1003 was a stray `/100` at exactly this boundary: OddsChart multiplies
 * `home_probability` by 100 to plot and to feed its tooltip, then divides the
 * axis value by 100 when it hands a scrubbed point back to the hero/readout.
 * When those two conversions drift (an added/removed `*100` or `/100`) the
 * tooltip and the headline show different numbers for the same game. Routing
 * BOTH directions through these named helpers makes the boundary one tested
 * contract (probabilityInvariant.test.ts) — a regression fails a unit test
 * instead of only surfacing as a live visual mismatch. The arithmetic is
 * unchanged; this is a guard, not a behavior change.
 */
export function homeProbToChartAxis(homeProb: number): number {
  return homeProb * 100;
}

export function chartAxisToHomeProb(axisValue: number): number {
  return axisValue / 100;
}

/**
 * #2085 — fold the printed percents onto a resolved pair, at the ONE place that
 * knows which source the pair actually came from.
 *
 * 🔴 THE SERVED PERCENTS DESCRIBE `current_odds` AND NOTHING ELSE, AND ON THIS
 * PAGE THAT IS USUALLY NOT THE PAIR ON SCREEN. `FeedCard` may read
 * `current_odds.{home,away}_rendered_percent` unconditionally, and says so in a
 * comment, because the feed card renders `current_odds` whenever it renders a
 * pair at all. The event page does not: a LIVE game's hero is
 * `hero_probability` / `hero_probability_away`, a settled one is `opening_odds`,
 * and a blend-less live game falls through to `history[]`. Copying the feed's
 * one-liner here would print `current_odds`' rounding beside the BLEND's
 * probability — a mismatched pair, served confidently. So the served values are
 * taken only on the branches that read `odds`, and `fromCurrentOdds` records
 * that at the branch rather than being inferred afterwards.
 *
 * BOTH SERVED VALUES OR NEITHER. They are one decision; taking a served away
 * beside a locally-derived home re-opens the 101 from the other direction. An
 * older deploy that carries one and not the other therefore falls back whole.
 */
function withRenderedPercents(
  resolved: Omit<
    ResolvedProbability,
    "homePct" | "awayPct" | "openingHomePct" | "openingAwayPct"
  >,
  odds: CurrentOdds | undefined,
  fromCurrentOdds: boolean,
): ResolvedProbability {
  const [localAwayPct, localHomePct] = renderedDuelPercents(
    resolved.awayProb,
    resolved.homeProb,
  );
  const servedAway = fromCurrentOdds ? odds?.away_rendered_percent : null;
  const servedHome = fromCurrentOdds ? odds?.home_rendered_percent : null;
  const bothServed = servedAway != null && servedHome != null;

  // The opening line has no served pair at any deploy — `opening_odds` carries
  // only the two probabilities — so it is always decided locally.
  const [openingAwayPct, openingHomePct] = renderedDuelPercents(
    resolved.openingAwayProb,
    resolved.openingHomeProb,
  );

  return {
    ...resolved,
    awayPct: bothServed ? servedAway : localAwayPct,
    homePct: bothServed ? servedHome : localHomePct,
    openingAwayPct,
    openingHomePct,
  };
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
  // #2085 — set by the branch that reads `odds`, so `withRenderedPercents` can
  // tell whether the served pair describes the pair being returned. A later
  // branch that OVERRIDES the pair must clear it; that is the whole reason this
  // is a mutable flag beside the values rather than a test on the values.
  let fromCurrentOdds = false;

  // UX-P042 (#1640). Decided ONCE, up front, so the win_prob_history fallback below
  // cannot quietly re-introduce the number this branch declined to assert.
  const withheld = shouldWithholdProbability(event);

  if (isFinished) {
    // Completed/closed: show opening odds
    homeProb = openingHomeProb;
    awayProb = openingAwayProb;
    if (homeProb !== null) {
      probSourceLabel = "Pre-game odds";
    } else {
      homeProb = odds?.home_probability ?? null;
      awayProb = odds?.away_probability ?? null;
      fromCurrentOdds = true;
    }
  } else if (isLive) {
    // Live: THE BLEND IS THE HERO (L2-163 Item 2b, Alex ruling). The chart draws
    // the aggregated Bain Luck line (historyData.aggregate_line); the hero must
    // read the SAME number so a lagged sportsbook consensus never contradicts the
    // chart on screen (the 57%-hero vs 20%-chart bug).
    //
    // UX-P003 — read `hero_probability` FIRST. This branch used to lead with
    // `latestBlendPoint(aggregate_line)`, which bound the hero to a DIFFERENT
    // blend than the Discover card: the card renders
    // `compute_aggregate_probability(event)` (the point-in-time weighted median
    // over win_probability_sources), while `aggregate_line` is the time-series
    // blend — different inputs, per-bucket staleness decay, and formerly an
    // α=0.3 EMA on top. So the card and the hero it links to disagreed on the
    // same live game. Measured on production 2026-08-05:
    //
    //     Giants @ Rangers    card 60%  hero/chart 78%
    //     Dodgers @ Cubs      card 89%  hero/chart 99%
    //     Blue Jays @ Astros  card 99%  hero/chart 100%
    //
    // `hero_probability` IS `compute_aggregate_probability(event)` — literally
    // the same backend call the card uses — so binding here makes card == hero
    // by construction rather than by two paths happening to agree. The backend
    // now also pins the live edge of `aggregate_line` to that same value
    // (`_pin_live_blend_edge`), which brings the chart to the same number; the
    // aggregate_line read stays as the fallback for a cached/older payload that
    // predates the `hero_probability` field.
    // Gate on the source: `hero_probability` degrades to the OPENING line when
    // no blend exists, and an opening line is not a live blend — labelling it
    // "Bain Luck blend" would be a lie and would pre-empt the sportsbook
    // cross-check below. Only "blend" is the one number.
    const heroBlend =
      event.hero_probability_source === "blend" &&
      typeof event.hero_probability === "number"
        ? event.hero_probability
        : null;
    const blendPoint =
      heroBlend ?? latestBlendPoint(historyData?.aggregate_line);
    if (blendPoint !== null) {
      homeProb = blendPoint;
      awayProb =
        heroBlend !== null && typeof event.hero_probability_away === "number"
          ? event.hero_probability_away
          : 1 - blendPoint;
      probSourceLabel = "Live · Bain Luck blend";
      // 🔴 #2085 — `fromCurrentOdds` stays FALSE here on purpose. This pair is
      // the BLEND (`hero_probability` / `hero_probability_away`), which the
      // backend derives as `round(1 - agg, 6)` and serves with no rendered
      // percents of its own. `current_odds` is a different, lagging pair.
      return withRenderedPercents(
        {
          homeProb,
          awayProb,
          probSourceLabel,
          openingHomeProb,
          openingAwayProb,
        },
        odds,
        false,
      );
    }

    // No blend yet — show current odds, cross-checked against history
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    fromCurrentOdds = true;
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
          // #2085 — the pair has been REPLACED by a history row. The served
          // percents describe the `current_odds` pair this branch just
          // overrode, and the override only fires when the two differ by more
          // than 5 points, so keeping them would print a number off by five.
          fromCurrentOdds = false;
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
  } else if (withheld) {
    // UX-P042 (#1640) — scheduled, but there is no probability to show. The event's
    // entire evidence base is an untraded Polymarket book at its default midpoint, and
    // `current_odds` still presents that as a confident 0.5/0.5 "aggregate" with
    // bookmaker_count 0. Assert nothing rather than invent a coin flip; the callers
    // already render a no-probability state.
    homeProb = null;
    awayProb = null;
  } else {
    // Scheduled: current betting consensus
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
    fromCurrentOdds = true;
    const count = odds?.bookmaker_count ?? 0;
    if (count > 0) {
      probSourceLabel = `${count} sportsbook${count !== 1 ? "s" : ""}`;
    } else if (homeProb !== null && odds?.source === "aggregate") {
      probSourceLabel = "Aggregate";
    }
  }

  // Fallback: use win_prob_history (ESPN/stat_model/Kalshi)
  // `!withheld` (UX-P042): when the only source is an untraded placeholder, its
  // history is that same placeholder.
  //
  // #3459: this used to read `lastChartPoint.homeProb !== 0.5`, testing the VALUE
  // to infer whether there was a value at all. That was the right judgment made
  // on the wrong evidence — it also refused every market that is genuinely
  // pick-'em, so a real dead-even game lost its hero for looking like an absence.
  // `probKnown` is the same judgment made on the fact itself, and it is
  // absent-means-true, so a scrub point (which always carries a real reading)
  // behaves exactly as before.
  if (
    !withheld &&
    homeProb === null &&
    lastChartPoint &&
    lastChartPoint.probKnown !== false &&
    !(
      isFinished &&
      (lastChartPoint.homeProb > 0.95 || lastChartPoint.homeProb < 0.05)
    )
  ) {
    homeProb = lastChartPoint.homeProb;
    awayProb = lastChartPoint.awayProb;
    // #2085 — a chart point, not `current_odds`. Same override rule as the
    // history branch above.
    fromCurrentOdds = false;
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

  return withRenderedPercents(
    { homeProb, awayProb, probSourceLabel, openingHomeProb, openingAwayProb },
    odds,
    fromCurrentOdds,
  );
}

// ---------------------------------------------------------------------------
// Chart domain computation
// ---------------------------------------------------------------------------

export interface SharedChartDomain {
  start: string;
  end: string;
  ticks: string[];
  /**
   * The date-fns format the `ticks` were built with (#3419). The charts MUST
   * format their minute categories and period-marker keys with this exact
   * string: the XAxis is categorical, so a tick only lands on a real column
   * when the two spellings match character for character.
   */
  labelFormat: string;
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
  const allEnd = new Date(Math.max(...timestamps));
  let end = new Date(allEnd);

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
    // A completed game's end cannot precede its start. Drop game-end timestamps
    // that fall before commence_time (minus a small pregame margin): a
    // mis-attributed earlier game's snapshots (gotcha #32 / inverted completed_at)
    // otherwise drag `end` to before `start`, inverting the domain and rendering
    // an EMPTY settled chart (Queue #189). With them gone we fall through to the
    // commence-based window and the real journey renders.
    const ctMs = commenceTime ? new Date(commenceTime).getTime() : NaN;
    const endFloorMs = !isNaN(ctMs) ? ctMs - 60 * 60 * 1000 : -Infinity;
    const gameEndTs: number[] = [];

    for (const pt of historyData.espn_history ?? []) {
      const t = new Date(pt.timestamp).getTime();
      if (!isNaN(t) && t >= endFloorMs) gameEndTs.push(t);
    }
    for (const [source, pts] of Object.entries(
      historyData.win_prob_history ?? {},
    )) {
      if (!GAME_END_SOURCES.has(source)) continue;
      for (const pt of pts) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t) && t >= endFloorMs) gameEndTs.push(t);
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

      // End AT the final snapshot — no trailing buffer (L2-131 / gotcha #22).
      // The old +5 min pad left a flat forward-filled tail that read as if the
      // game continued after it ended.
      end = new Date(endMs);
    } else if (historyData.history && historyData.history.length > 0) {
      // No game-end sources — end at the last sportsbook snapshot.
      const bettingTs: number[] = [];
      for (const pt of historyData.history) {
        const t = new Date(pt.timestamp).getTime();
        if (!isNaN(t)) bettingTs.push(t);
      }
      if (bettingTs.length > 0) {
        end = new Date(Math.max(...bettingTs));
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

    // FLOOR (#3419): a completed game's window may not end before its own data
    // begins. Every branch above derives `end` from a field that can be wrong
    // in a way `end` cannot absorb — a ticker-derived midnight `commence_time`
    // plus a flat duration estimate, an inverted `completed_at`, a game-end
    // source belonging to a different game. When the derived end lands before
    // the FIRST point we are drawing, it is not trimming a trailing tail (what
    // this block is for), it is deleting the whole series: "Since Start" cuts
    // to a window the match was not played in, and "All" comes out INVERTED,
    // where fillMinuteGaps no-ops and the chart renders empty.
    //
    // Measured on /events/15300276 (Jodar v Bu, US Open, FINAL, Kalshi-only):
    // commence_time 2026-09-01T00:00Z + 180 tennis minutes = an end of 03:00Z,
    // 12h56m BEFORE the first of its 559 points. Discard a derived end that
    // fails this test and keep the honest maximum — a visible journey beats a
    // precisely-trimmed empty one.
    if (end.getTime() < allStart.getTime()) {
      end = new Date(allEnd);
    }
  }

  // "Since Start" mode: start from commenceTime
  const gameStart = commenceTime ? new Date(commenceTime) : null;
  const liveStart =
    gameStart && !isNaN(gameStart.getTime()) ? gameStart : allStart;

  // "All" mode: cap the start to at most 2 hours before commenceTime once a game
  // is in-game (live) or finished. Prevents charts from showing many hours of
  // flat pre-game odds data that makes the in-game chart unreadable — AND keeps
  // the rendered window under 12h so the "h:mm a" categorical inning markers
  // can't collide across a day boundary and render out of order (L2-163 Item 2c;
  // the "T9 left of T1" collision). Scheduled/pregame is left uncapped — there
  // the multi-hour odds-drift IS the story.
  //
  // The cap is anchored on commence_time, which is exactly the field that is
  // untrustworthy when a start was never reported. Applying it blind can move
  // the window PAST every point the event has and leave "All" as empty as
  // "Since Start" was. Only cap when something survives the cap.
  const isInGame = isCompleted || eventStatus === "live";
  let allModeStart = allStart;
  if (isInGame && gameStart && !isNaN(gameStart.getTime())) {
    const twoHoursBefore = new Date(gameStart.getTime() - 2 * 60 * 60 * 1000);
    if (
      allModeStart < twoHoursBefore &&
      timestamps.some((t) => t >= twoHoursBefore.getTime())
    ) {
      allModeStart = twoHoursBefore;
    }
  }

  const start = chartTimeRange === "live" ? liveStart : allModeStart;
  start.setSeconds(0, 0);
  end.setSeconds(0, 0);

  // Compute explicit X-axis ticks at clean time boundaries.
  //
  // UX-P022: the interval used to FLOOR at 30 minutes
  // (`durationMin < 180 ? 30 : 60`, then doubled while it produced >10 ticks).
  // That only ever coarsened, never refined, so a chart shorter than ~an hour
  // got no interior tick at all. A live game 21 minutes old rendered exactly
  // "1:10 PM" and "1:31 PM" across a full-width chart — the reader cannot tell
  // whether a move happened two minutes ago or twenty.
  //
  // The ladder below refines as well as coarsens: it picks the smallest clean
  // interval that keeps the tick count at or under the target. A 21-minute
  // window now steps by 5 minutes.
  const durationMs = end.getTime() - start.getTime();
  const durationMin = durationMs / 60000;
  // #3419: a window at or beyond a day needs its labels date-qualified to stay
  // unique, and a date-qualified label is ~40% wider ("Tue 6:00 AM" vs
  // "6:00 AM"), so it has to buy that width from the tick budget. Same total
  // ink, fewer and more informative labels.
  const labelFormat = categoryLabelFormat(start.getTime(), end.getTime());
  const MAX_TICKS = labelFormat === CATEGORY_LABEL_FORMAT ? 8 : 5;
  const INTERVAL_LADDER_MIN = [1, 2, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440];
  let intervalMin =
    INTERVAL_LADDER_MIN.find((step) => durationMin / step <= MAX_TICKS) ??
    INTERVAL_LADDER_MIN[INTERVAL_LADDER_MIN.length - 1];
  // Degenerate window (everything inside one step): keep the endpoints only.
  while (durationMin / intervalMin > MAX_TICKS) intervalMin *= 2;

  const ticks: string[] = [];
  ticks.push(fmtDate(start, labelFormat));

  // A boundary tick landing right next to the end label collides with it and
  // Recharts silently drops one of the pair — which is how a 3-tick axis
  // rendered as 2. Reserve a slice of the window for the end label instead.
  const endMs = end.getTime();
  const minGapMs = Math.max(durationMs * 0.06, 30_000);

  const cursor = new Date(start);
  const curMins = cursor.getMinutes();
  const nextBoundary = Math.ceil((curMins + 1) / intervalMin) * intervalMin;
  cursor.setMinutes(nextBoundary, 0, 0);
  while (cursor.getTime() < endMs) {
    if (endMs - cursor.getTime() >= minGapMs) {
      ticks.push(fmtDate(cursor, labelFormat));
    }
    cursor.setMinutes(cursor.getMinutes() + intervalMin);
  }

  const endLabel = fmtDate(end, labelFormat);
  if (ticks[ticks.length - 1] !== endLabel) {
    ticks.push(endLabel);
  }

  return {
    start: start.toISOString(),
    end: end.toISOString(),
    ticks,
    labelFormat,
  };
}

// ---------------------------------------------------------------------------
// Shared chart time range
// ---------------------------------------------------------------------------

/**
 * The largest number of post-`commenceTime` points held by any ONE chart
 * series (sportsbook history, score history, ESPN history, or a single
 * win-prob source).
 *
 * Per-series, not pooled: the charts draw one `<Line>` per series and a line
 * needs two points of its OWN. Pooling would let four series with one point
 * each read as four points and re-select a range that draws nothing.
 *
 * Why the page needs this at all. Both charts already compute a
 * `hasPostStartData` and refuse "Since Start" when it would be empty —
 * OddsChart even disables the toggle. But the event page passes
 * `externalTimeRange`, and `timeRange = externalTimeRange ?? internalTimeRange`
 * means the parent's value wins outright, so each child's own fallback is dead
 * code on this page. Pinned to "live" by the parent, an event whose
 * `commence_time` is a stand-in rather than a reported first serve renders BOTH
 * charts as an empty grid.
 *
 * The exhibit — US Open Jodar v Kokkinakis (15293847), measured live on
 * production 2026-09-01 22:18Z: `commence_time` 16:00:00Z, an exact top of the
 * hour written by the Odds API's session-start default, while the last
 * sportsbook quote is 15:44Z — sixteen minutes BEFORE the "start". Zero
 * post-start odds points, one post-start score point, one post-start Kalshi
 * point. Win Probability rendered a bare grid with a single dot at the right
 * edge; Score Differential rendered nothing at all; and "Since Start" showed as
 * the selected pill on a button OddsChart had itself disabled.
 *
 * Note the counting rule is what makes that exhibit come out right. A
 * has-any test passes on it — one score point IS post-start — and the chart is
 * still blank, because one point with `dot={false}` draws no segment.
 */
export function maxPostStartSeriesPoints(
  historyData: EventHistoryResponse | null | undefined,
  commenceTime: string | undefined,
): number {
  if (!historyData || !commenceTime) return 0;
  const cutoff = new Date(commenceTime).getTime();
  if (isNaN(cutoff)) return 0;

  const countAtOrAfter = (
    points: { timestamp?: string }[] | null | undefined,
  ): number => {
    let n = 0;
    for (const p of points ?? []) {
      if (!p?.timestamp) continue;
      const t = new Date(p.timestamp).getTime();
      if (!isNaN(t) && t >= cutoff) n += 1;
    }
    return n;
  };

  let most = 0;
  most = Math.max(most, countAtOrAfter(historyData.history));
  most = Math.max(most, countAtOrAfter(historyData.score_history));
  most = Math.max(most, countAtOrAfter(historyData.espn_history));
  for (const pts of Object.values(historyData.win_prob_history ?? {})) {
    most = Math.max(most, countAtOrAfter(pts));
  }
  return most;
}

/** Two points make a line; one point with `dot={false}` makes an empty grid. */
export const MIN_POINTS_TO_DRAW_A_LINE = 2;

/**
 * The shared "All" / "Since Start" range the page should hold before the
 * reader has picked one. "Since Start" only when some series can actually
 * draw inside it — otherwise "All", which is what each chart would have
 * chosen on its own.
 */
export function defaultChartTimeRange(
  historyData: EventHistoryResponse | null | undefined,
  commenceTime: string | undefined,
): "all" | "live" {
  return maxPostStartSeriesPoints(historyData, commenceTime) >=
    MIN_POINTS_TO_DRAW_A_LINE
    ? "live"
    : "all";
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

  // L2-174 Item 1 — THE READOUT INVERSION. The resting readout must agree with
  // the hero. The hero (resolveProbability, live branch) and the scrub tooltip
  // (OddsChart `bainLuckDelta`) both read the aggregate_line BLEND — the weighted
  // "Bain Luck" line the chart draws. The at-rest readout was instead trusting a
  // SINGLE win_prob_history source's `home_probability`, whose orientation can be
  // opposite the blend (a source's home-field is actually the away side). That
  // rendered "Cardinals 99% — Diamondbacks 1%" under a hero that correctly showed
  // the inverse. Read the blend FIRST so the strip-at-rest, the scrub, and the
  // hero all speak one orientation-consistent number; the win_prob_history/history
  // fallbacks only fire when there is no blend point yet.
  //
  // #1003: `history[].home_probability` is a 0–1 FRACTION (API-verified — same as
  // win_prob_history, current_odds, bookmaker_odds), NOT 0–100. The old `/ 100`
  // here made the headline fallback show ~1% while the chart tooltip (OddsChart
  // multiplies the same field by 100) correctly showed ~81% — the reported
  // tooltip-vs-headline mismatch. It fired whenever win_prob_history was empty
  // (any live sport without an ESPN/stat win-prob source, e.g. cricket/soccer).
  // #3459 — SAY WHEN THERE IS NO READING, instead of inventing a pick-'em one.
  //
  // The `?? 0.5` on the end of this cascade was load-bearing for layout (the
  // point's prob fields are not nullable) and a lie for meaning: on production
  // event 15305801 — Ram/Salisbury v Arribage/Olivetti, US Open doubles, LIVE,
  // with **0 rows in `futures_markets` and 0 in `odds_snapshots`** — all three
  // sources were absent, this returned 0.5, and `GamePlayCard` printed
  // "Ram/Salisbury 50% — Arribage/Olivetti 50%" three inches under a chart
  // correctly reading "Tracking will begin when odds are available".
  //
  // The hero escaped only because `resolveProbability` sniffed for the literal
  // `lastChartPoint.homeProb !== 0.5` — which also threw away every market that
  // is honestly dead even. Absence and evenness cannot share a value domain;
  // `probKnown` gives absence its own, so no consumer has to guess again.
  const measuredHomeProb =
    latestBlendPoint(historyData.aggregate_line) ??
    lastWp?.home_probability ??
    lastHist?.home_probability ??
    null;
  const probKnown = measuredHomeProb !== null;
  const homeProb = measuredHomeProb ?? 0.5;

  // L2-163 Item 3 — moments readout scaffold. Surface the most recent scoring
  // play so the below-chart readout (GamePlayCard) shows the CURRENT moment at
  // rest, not just a static win-prob line: for a live game that is the play that
  // just happened; for a settled game it is "what hit" last. On-chart dots wait
  // for #1168 — this is the socket the moments engine plugs into. Scored by
  // timestamp so an out-of-order plays array can't surface a stale play.
  const plays = historyData.scoring_plays;
  let latestPlay: ScoringPlay | null = null;
  if (plays && plays.length > 0) {
    for (const play of plays) {
      if (!play?.timestamp) continue;
      if (!latestPlay || play.timestamp > latestPlay.timestamp) {
        latestPlay = play;
      }
    }
  }

  return {
    timestamp:
      lastEspn?.timestamp ||
      lastWp?.timestamp ||
      lastHist?.timestamp ||
      "",
    homeProb,
    awayProb: 1 - homeProb,
    probKnown,
    homeScore: lastEspn?.home_score ?? homeScore ?? null,
    awayScore: lastEspn?.away_score ?? awayScore ?? null,
    period: lastEspn?.period?.toString() ?? null,
    clock: lastEspn?.game_clock ?? null,
    scoringPlay: latestPlay,
  };
}
