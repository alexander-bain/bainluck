/**
 * Direction 199 & Rulings 200-B, 197, 194-A — Single unified value model and
 * resolver for every sport and state on the website game page (`/events/[id]`),
 * matching iOS `EventSportHeadlines12472` + `HeadlineStyleTable199` (`#12771`).
 *
 * Invariants:
 * 1. One structure across every sport and state (`before`, `during`, `after`):
 *    - `before`: `Proj. · Chance` + segmented bar (no tick), records under names.
 *    - `during`: `<Score / Set columns> · Proj. · Now` + segmented bar with
 *      pregame tick + one single-line grey pregame summary (`"Pregame  Lions 58% · projected 27–23"`,
 *      strictly from `prematch_odds` + `pregame_projection`, never `opening_odds`).
 *      No `Pregame` column during a game; no team records during a game.
 *    - `after`: `[Set columns] · Pregame · Final`, winner ticked (`✓`), loser
 *      dimmed, **no bar**, `Pregame` strictly from `prematch_odds`.
 * 2. Empty columns suppress their header text (`header = ""`) while keeping
 *    column spacing; when every column in the table is empty, `hasAnyColumnValue`
 *    is `false` so no blank header strip renders.
 * 3. Never prints `"opening"`, `"opened"`, `"stale"`, `"Settled"`, `"by venue"`,
 *    `"Current win chance"`, or `"Projection before"`, and never repeats an
 *    alphabetic label twice inside one headline.
 */

import { formatProbability } from "@/lib/api";
import { printableAway, sportPricesADraw, awayIsTheComplement } from "@/lib/drawPricedWinner";
import {
  formatLivePregameSummary,
  formatLiveTenthsPair,
  formatSingleLiveTenths,
} from "@/components/EventCard183A";
import {
  PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL,
  PREGAME_KIND_LAST_BEFORE_SCHEDULED_START,
} from "@/lib/finalForecastComparison";
import { formatEventStartLabel } from "@/lib/eventKeyStats";
import { sportVocab } from "@/lib/marketMapUtils";
import { projectedFinalFormat } from "@/lib/projectedFinalPair";
import {
  ABOVE_NINETY_NINE_PERCENT,
  BELOW_ONE_PERCENT,
} from "@/lib/probabilityDisplay";
import { probabilityBarPair } from "@/lib/probabilityBarPair";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import {
  buildSoccerThreeWayCard,
  type SoccerRawOtherRow,
} from "@/lib/soccerEventCards";
import { getLeagueDisplay } from "@/lib/sportCategories";
import {
  effectiveAwaySecondaryColor,
  lookupTeamColors,
  resolveMatchupTeamColors,
  teamTextColor,
} from "@/lib/teamColors";
import { teamShortNames } from "@/lib/teamShortName";
import type { EventDetailResponse } from "@/lib/types";
import {
  HEADLINE_STYLE_199,
  type HeadlineBottomBar199,
  type HeadlineColumnRole199,
  type HeadlineColumnSpec199,
  type HeadlineCompetitorRow199,
  type HeadlineLivePregameSummary199,
  type HeadlineModel199,
  type HeadlinePhase199,
  type HeadlineRowRole199,
} from "@/lib/headlineModel199";

export {
  HEADLINE_STYLE_199,
  type HeadlineBottomBar199,
  type HeadlineColumnRole199,
  type HeadlineColumnSpec199,
  type HeadlineCompetitorRow199,
  type HeadlineLivePregameSummary199,
  type HeadlineModel199,
  type HeadlinePhase199,
  type HeadlineRowRole199,
};

export function isSoccerSport199(sport: string | null | undefined): boolean {
  const s = (sport ?? "").trim().toLowerCase();
  return s === "soccer" || s.startsWith("soccer_");
}

export function isTennisSport199(sport: string | null | undefined): boolean {
  const s = (sport ?? "").trim().toLowerCase();
  return s === "tennis" || s.startsWith("tennis_");
}

export function isMMASport199(sport: string | null | undefined): boolean {
  const s = (sport ?? "").trim().toLowerCase();
  return s === "mma" || s.startsWith("mma_");
}

export function isBoxingSport199(sport: string | null | undefined): boolean {
  const s = (sport ?? "").trim().toLowerCase();
  return s === "boxing" || s.startsWith("boxing_");
}

export function carriesProjectedScoreColumn199(sport: string | null | undefined): boolean {
  if (isTennisSport199(sport) || isMMASport199(sport) || isBoxingSport199(sport)) {
    return false;
  }
  const vocab = sportVocab(sport ?? undefined);
  return Boolean(vocab.scoreboardCountsTheUnit && vocab.unit);
}

const SOCCER_FRIENDLY_NAMES: Record<string, string> = {
  soccer_epl: "Premier League",
  soccer_uefa_champs_league: "Champions League",
  soccer_uefa_europa_league: "Europa League",
  soccer_uefa_europa_conference_league: "Conference League",
  soccer_mexico_ligamx: "Liga MX",
  soccer_spain_la_liga: "La Liga",
  soccer_germany_bundesliga: "Bundesliga",
  soccer_italy_serie_a: "Serie A",
  soccer_france_ligue_one: "Ligue 1",
  soccer_usa_mls: "MLS",
  soccer_brazil_campeonato: "Brasileirão",
  soccer_netherlands_eredivisie: "Eredivisie",
  soccer_portugal_primeira_liga: "Primeira Liga",
  soccer_fifa_world_cup: "World Cup",
};

export function resolveHeadlineLeagueLabel199(
  event: Pick<EventDetailResponse, "sport" | "sport_key" | "sport_name">,
): string {
  const sportRaw = event.sport ?? event.sport_key ?? null;
  const lower = (sportRaw ?? "").trim().toLowerCase();
  if (lower === "americanfootball_nfl") return "NFL";
  if (lower === "basketball_nba") return "NBA";
  if (lower === "americanfootball_ncaaf") return "NCAAF";
  if (lower === "americanfootball_ncaaf_fcs") return "NCAAF FCS";
  if (lower === "basketball_ncaab") return "NCAAB";
  if (lower === "basketball_wncaab") return "WNCAAB";
  if (lower === "baseball_mlb") return "MLB";
  if (lower === "icehockey_nhl") return "NHL";
  if (isSoccerSport199(lower)) {
    if (SOCCER_FRIENDLY_NAMES[lower]) return SOCCER_FRIENDLY_NAMES[lower];
    const served = event.sport_name?.trim();
    if (served) {
      if (served.toLowerCase() === "uefa champions league") return "Champions League";
      if (served.toLowerCase() === "english premier league") return "Premier League";
      return served;
    }
    return sportRaw ? getLeagueDisplay(sportRaw) : "Soccer";
  }
  if (isTennisSport199(lower)) {
    if (lower.startsWith("tennis_atp")) return "ATP";
    if (lower.startsWith("tennis_wta")) return "WTA";
    const served = event.sport_name?.trim();
    if (served) {
      const u = served.toUpperCase();
      if (u.includes("ATP")) return "ATP";
      if (u.includes("WTA")) return "WTA";
      return served;
    }
    return "Tennis";
  }
  if (isMMASport199(lower)) {
    if (lower.includes("ufc")) return "UFC";
    const served = event.sport_name?.trim();
    return served || "MMA";
  }
  if (isBoxingSport199(lower)) return "Boxing";
  const served = event.sport_name?.trim();
  if (served) return served;
  return sportRaw ? getLeagueDisplay(sportRaw) : "Matchup";
}

/**
 * Resolves readable, distinct competitor colours for `away` and `home` rows
 * and the segmented probability bar (Ruling 197 + contrast floor + partner defaults).
 */
export function resolveHeadlineTeamHexes199(opts: {
  homePrimary?: string | null;
  awayPrimary?: string | null;
  awaySecondary?: string | null;
}): { away: string; home: string } {
  const pair = resolveMatchupTeamColors({
    homePrimary: opts.homePrimary,
    awayPrimary: opts.awayPrimary,
    awaySecondary: opts.awaySecondary,
  });

  const safeHome = teamTextColor(pair.home) ?? null;
  const safeAway = teamTextColor(pair.away) ?? null;

  if (safeHome && safeAway) {
    return { away: safeAway, home: safeHome };
  }
  if (safeHome && !safeAway) {
    const fallbackPair = probabilityBarPair(null, safeHome);
    return {
      away: teamTextColor(fallbackPair.away) ?? HEADLINE_STYLE_199.defaultAwayHex,
      home: safeHome,
    };
  }
  if (!safeHome && safeAway) {
    const fallbackPair = probabilityBarPair(safeAway, null);
    return {
      away: safeAway,
      home: teamTextColor(fallbackPair.home) ?? HEADLINE_STYLE_199.defaultHomeHex,
    };
  }
  return {
    away: HEADLINE_STYLE_199.defaultAwayHex,
    home: HEADLINE_STYLE_199.defaultHomeHex,
  };
}

function cleanRecordString(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  // Keep compact W-L / W-D-L records ("6-3", "7-2-1", "34-10 (1st)") without multi-clause prose
  const firstClause = trimmed.split(",")[0]?.trim() ?? "";
  return firstClause || null;
}

function isUsableProb(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v > 0 && v < 1;
}

interface StrictPrematchPair {
  awayProb: number | null;
  homeProb: number;
  awayPct: number | null;
  homePct: number;
}

/**
 * Strict pregame reading (`event.prematch_odds` ONLY — NEVER `opening_odds`).
 */
function resolveStrictPrematch199(
  event: Pick<EventDetailResponse, "prematch_odds" | "sport">,
): StrictPrematchPair | null {
  const pre = event.prematch_odds;
  if (!pre || !isUsableProb(pre.home_probability)) return null;
  const rawAway = isUsableProb(pre.away_probability)
    ? pre.away_probability
    : 1 - pre.home_probability;
  const awayWithheld = awayIsTheComplement(
    pre.away_probability ?? null,
    pre.home_probability,
    event.sport,
  );
  if (awayWithheld) {
    const homePct =
      pre.home_rendered_percent != null && Number.isFinite(pre.home_rendered_percent)
        ? Math.round(pre.home_rendered_percent)
        : Math.round(pre.home_probability * 100);
    return {
      awayProb: null,
      homeProb: pre.home_probability,
      awayPct: null,
      homePct,
    };
  }
  const [awayPct, homePct] = servedDuelPercents(
    rawAway,
    pre.home_probability,
    pre.away_rendered_percent,
    pre.home_rendered_percent,
  );
  if (homePct == null) return null;
  return {
    awayProb: rawAway,
    homeProb: pre.home_probability,
    awayPct,
    homePct,
  };
}

/**
 * Matches iOS `EventSportHeadlines12472.formatLiveProjectedColumnNumber`:
 * football and basketball print whole numbers (`24`, `28`); baseball, hockey,
 * and soccer keep one decimal (`4.5`, `3.2`, `1.8`).
 */
export function formatHeadlineProjectedNumber199(
  value: number | null | undefined,
  sportKey: string | null | undefined,
): string {
  if (value == null || !Number.isFinite(value)) return "";
  const lower = (sportKey ?? "").trim().toLowerCase();
  if (lower.startsWith("americanfootball") || lower.startsWith("basketball")) {
    return String(Math.round(value));
  }
  return value.toFixed(1);
}

/**
 * Matches iOS `EventSportHeadlines12472.qualifiedLivePregameProjectionPair`:
 * admits the pregame projection into the single grey pregame line (`200-B`)
 * only when `kind`, `boundary`, `source`, `basis`, `unit`, `period`,
 * `bookmaker_count`, capture window, `commence_time` match, margin-spread
 * support, and possible-result tie check all pass.
 */
function qualifiedLivePregameProjectionPair199(
  event: Pick<EventDetailResponse, "pregame_projection" | "sport" | "commence_time">,
): { away: string; home: string } | null {
  const p = event.pregame_projection;
  if (!p || typeof p !== "object") return null;
  if (isTennisSport199(event.sport)) return null;
  if (p.kind !== PREGAME_KIND_LAST_BEFORE_SCHEDULED_START) return null;
  if (p.boundary !== "scheduled_start") return null;
  if (p.source !== "sportsbooks") return null;
  if (p.basis !== PREGAME_BASIS_CONSENSUS_SPREAD_TOTAL) return null;
  const format = projectedFinalFormat(event.sport);
  if (!format || p.unit !== format.unit) return null;
  const expectedPeriod = format.unit === "goals" ? "regulation" : "full_game";
  if (p.period !== expectedPeriod) return null;
  if (!Number.isInteger(p.bookmaker_count) || p.bookmaker_count < 1) return null;
  const earliest = typeof p.earliest_captured_at === "string" ? Date.parse(p.earliest_captured_at) : NaN;
  const latest = typeof p.latest_captured_at === "string" ? Date.parse(p.latest_captured_at) : NaN;
  const boundary = typeof p.boundary_at === "string" ? Date.parse(p.boundary_at) : NaN;
  if (!Number.isFinite(earliest) || !Number.isFinite(latest) || !Number.isFinite(boundary)) {
    return null;
  }
  if (earliest > latest || latest >= boundary) return null;
  if (typeof event.commence_time === "string" && event.commence_time !== "") {
    const rowStart = Date.parse(event.commence_time);
    if (Number.isFinite(rowStart) && boundary !== rowStart) return null;
  }
  if (
    typeof p.projected_home_score !== "number" ||
    !Number.isFinite(p.projected_home_score) ||
    p.projected_home_score <= 0 ||
    typeof p.projected_away_score !== "number" ||
    !Number.isFinite(p.projected_away_score) ||
    p.projected_away_score <= 0
  ) {
    return null;
  }
  const vocab = sportVocab(event.sport ?? undefined);
  const roundedHome = Math.round(p.projected_home_score);
  const roundedAway = Math.round(p.projected_away_score);
  if (!vocab.canEndInATie && roundedHome === roundedAway) return null;
  return {
    away: String(roundedAway),
    home: String(roundedHome),
  };
}

function largestRemainderUnits(shares: number[], targetTotal: number): number[] {
  const scaled = shares.map((s) => Math.max(0, s) * targetTotal);
  const floors = scaled.map((s) => Math.floor(s));
  const remNeeded = Math.max(0, targetTotal - floors.reduce((a, b) => a + b, 0));
  if (remNeeded > 0) {
    const order = shares
      .map((_, i) => i)
      .sort((i, j) => {
        const ri = scaled[i] - floors[i];
        const rj = scaled[j] - floors[j];
        if (Math.abs(ri - rj) > 1e-9) return rj - ri;
        return i - j;
      });
    for (let k = 0; k < remNeeded && k < order.length; k++) {
      floors[order[k]] += 1;
    }
  }
  return floors;
}

export function formatSoccerThreeWayTexts199(
  home: number,
  draw: number,
  away: number,
  tenths: boolean,
): { home: string; draw: string; away: string } {
  const total = home + draw + away;
  if (!Number.isFinite(total) || total <= 0) {
    return { home: "", draw: "", away: "" };
  }
  const shares = [home / total, draw / total, away / total];
  if (tenths) {
    if (shares.some((p) => p < 0.0095 || p > 0.9905)) {
      const fmt = shares.map((p) => {
        if (p < 0.0095) return BELOW_ONE_PERCENT;
        if (p > 0.9905) return ABOVE_NINETY_NINE_PERCENT;
        return `${(p * 100).toFixed(1)}%`;
      });
      return { home: fmt[0], draw: fmt[1], away: fmt[2] };
    }
    const units = largestRemainderUnits(shares, 1000);
    return {
      home: `${(units[0] / 10).toFixed(1)}%`,
      draw: `${(units[1] / 10).toFixed(1)}%`,
      away: `${(units[2] / 10).toFixed(1)}%`,
    };
  }
  if (shares.some((p) => p < 0.005 || p > 0.995)) {
    const fmt = shares.map((p) => {
      if (p < 0.005) return BELOW_ONE_PERCENT;
      if (p > 0.995) return ABOVE_NINETY_NINE_PERCENT;
      return `${Math.round(p * 100)}%`;
    });
    return { home: fmt[0], draw: fmt[1], away: fmt[2] };
  }
  const units = largestRemainderUnits(shares, 100);
  return {
    home: `${units[0]}%`,
    draw: `${units[1]}%`,
    away: `${units[2]}%`,
  };
}

interface SoccerThreeWayShares {
  home: number;
  draw: number;
  away: number;
}

function scaleThreeWayShares(
  home: unknown,
  draw: unknown,
  away: unknown,
): SoccerThreeWayShares | null {
  if (!isUsableProb(home) || !isUsableProb(draw) || !isUsableProb(away)) return null;
  const sum = home + draw + away;
  if (sum <= 0.8 || sum >= 1.25) return null;
  return { home: home / sum, draw: draw / sum, away: away / sum };
}

function extractSoccerThreeWaySnapshot199(opts: {
  event: EventDetailResponse;
  shortNames: { home: string; away: string };
  gameMarkets?: {
    game_question_matrix?: unknown;
    other?: SoccerRawOtherRow[];
  } | null;
  finished: boolean;
  nowMs: number;
}): {
  openShares: SoccerThreeWayShares | null;
  pregameShares: SoccerThreeWayShares | null;
  confirmedWinner: "home" | "draw" | "away" | null;
} {
  const oddsDraw = (
    opts.event.current_odds as { draw_probability?: number | null } | undefined
  )?.draw_probability;
  const directOpen = !opts.finished
    ? scaleThreeWayShares(
        opts.event.current_odds?.home_probability,
        oddsDraw,
        opts.event.current_odds?.away_probability,
      )
    : null;

  const preDraw = (
    opts.event.prematch_odds as { draw_probability?: number | null } | undefined
  )?.draw_probability;
  const directPregame = scaleThreeWayShares(
    opts.event.prematch_odds?.home_probability,
    preDraw,
    opts.event.prematch_odds?.away_probability,
  );

  const card = opts.gameMarkets
    ? buildSoccerThreeWayCard({
        gameQuestionMatrix: opts.gameMarkets.game_question_matrix,
        otherMarkets: opts.gameMarkets.other,
        status: opts.event.status,
        commenceTime: opts.event.commence_time,
        homeTeam: opts.event.home_team,
        awayTeam: opts.event.away_team,
        homeShort: opts.shortNames.home,
        awayShort: opts.shortNames.away,
        homeScore: opts.event.home_score,
        awayScore: opts.event.away_score,
        nowMs: opts.nowMs,
      })
    : null;

  const marketOpen = card
    ? scaleThreeWayShares(
        card.legs.find((l) => l.role === "home")?.quotedChance,
        card.legs.find((l) => l.role === "draw")?.quotedChance,
        card.legs.find((l) => l.role === "away")?.quotedChance,
      )
    : null;

  const marketPregame = card
    ? scaleThreeWayShares(
        card.legs.find((l) => l.role === "home")?.pregameChance,
        card.legs.find((l) => l.role === "draw")?.pregameChance,
        card.legs.find((l) => l.role === "away")?.pregameChance,
      )
    : null;

  let confirmedWinner: "home" | "draw" | "away" | null = null;
  if (opts.finished && card) {
    const winners = card.legs.filter((l) => l.result === "won");
    if (winners.length === 1) {
      confirmedWinner = winners[0].role;
    }
  }

  return {
    openShares: directOpen ?? marketOpen,
    pregameShares: directPregame ?? marketPregame,
    confirmedWinner,
  };
}

function sanitizeBannedWords199(raw: string): string {
  return raw
    .replace(/settled\s+by\s+venue/gi, "Ended · no result reported")
    .replace(/ended\s+by\s+venue/gi, "Ended · no result reported")
    .replace(/\bsettled\b/gi, "Ended")
    .replace(/\bopening\b/gi, "initial")
    .replace(/\bopened\b/gi, "started")
    .replace(/\bstale\b/gi, "paused");
}

function formatPregameStart199(
  commenceTime: string | null | undefined,
  startIsTbd: boolean | null | undefined,
  startClock: "clock" | "tbd" | "pending",
  pregameStateLabel: string | null | undefined,
  nowMs: number,
): string | null {
  if (
    pregameStateLabel &&
    (pregameStateLabel === "Started" || pregameStateLabel.startsWith("Resumes"))
  ) {
    return pregameStateLabel;
  }
  if (!commenceTime) return null;
  if (startIsTbd === true || startClock !== "clock") {
    const label = formatEventStartLabel(commenceTime, startClock);
    return label || null;
  }
  const ms = Date.parse(commenceTime);
  if (!Number.isFinite(ms)) return null;
  const deltaSec = (ms - nowMs) / 1000;
  if (deltaSec > 0 && deltaSec <= 3600) {
    const mins = Math.max(1, Math.ceil(deltaSec / 60));
    return `In ${mins}m`;
  }
  const target = new Date(ms);
  const now = new Date(nowMs);
  const sameLocalDay =
    target.getFullYear() === now.getFullYear() &&
    target.getMonth() === now.getMonth() &&
    target.getDate() === now.getDate();
  const timePart = target.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  if (sameLocalDay && deltaSec > 0) {
    return `Today ${timePart}`;
  }
  if (deltaSec > 0 && deltaSec < 6 * 86400) {
    const weekday = target.toLocaleDateString("en-US", { weekday: "short" });
    return `${weekday} ${timePart}`;
  }
  const monthDay = target.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  return `${monthDay}, ${timePart}`;
}

function formatAfterMeta199(
  league: string,
  event: EventDetailResponse,
  extraOutcome?: string | null,
): string {
  const lower = (event.sport ?? "").trim().toLowerCase();
  if (lower === "baseball_mlb" && event.box_score_data) {
    const awayInn = Array.isArray(event.box_score_data.away_period_scores)
      ? event.box_score_data.away_period_scores.filter((x) => x != null).length
      : 0;
    const homeInn = Array.isArray(event.box_score_data.home_period_scores)
      ? event.box_score_data.home_period_scores.filter((x) => x != null).length
      : 0;
    const played = Math.max(awayInn, homeInn);
    if (played >= 5) {
      return `MLB · Final · ${played} Innings`;
    }
  }

  let finalWord = "Final";
  const fp = (event.final_score_period as string | null | undefined)?.trim().toLowerCase();
  if (fp === "aet" || fp === "extra_time") finalWord = "Final (AET)";
  else if (fp === "pen" || fp === "penalties") finalWord = "Final (Pen.)";
  else if (fp === "ot" || fp === "so" || fp === "shootout") finalWord = "Final/OT";

  const parts = [league, finalWord];
  const rawDate = event.completed_at ?? event.commence_time;
  if (rawDate) {
    const ms = Date.parse(rawDate);
    if (Number.isFinite(ms)) {
      parts.push(
        new Date(ms).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
      );
    }
  }
  if (extraOutcome) parts.push(extraOutcome);
  return parts.join(" · ");
}

const TENNIS_POINTS_PAIR_RE = /^\s*(0|15|30|40|Ad|AD)\s*[-–:]\s*(0|15|30|40|Ad|AD)\s*$/;

export function parseTennisGamePoints199(
  rawClock: string | null | undefined,
): { away: string; home: string } | null {
  if (!rawClock) return null;
  const m = rawClock.trim().match(TENNIS_POINTS_PAIR_RE);
  if (!m) return null;
  const fmt = (s: string) => (s.toUpperCase() === "AD" ? "Ad" : s);
  return { away: fmt(m[1]), home: fmt(m[2]) };
}

function normalizeTennisSetLabel(raw: string): string {
  const lower = raw.trim().toLowerCase();
  if (lower.startsWith("set ")) return raw.trim();
  if (lower === "1st" || lower === "1st set" || lower === "s1" || lower === "1") return "Set 1";
  if (lower === "2nd" || lower === "2nd set" || lower === "s2" || lower === "2") return "Set 2";
  if (lower === "3rd" || lower === "3rd set" || lower === "s3" || lower === "3") return "Set 3";
  if (lower === "4th" || lower === "4th set" || lower === "s4" || lower === "4") return "Set 4";
  if (lower === "5th" || lower === "5th set" || lower === "s5" || lower === "5") return "Set 5";
  return raw.trim();
}

function buildTennisScoreSlot199(opts: {
  event: EventDetailResponse;
  awaySetScore: number | null;
  homeSetScore: number | null;
  hasScore: boolean;
  includePoints: boolean;
}): {
  columns: HeadlineColumnSpec199[];
  awayCells: string[];
  homeCells: string[];
  awayEmph: number[];
  homeEmph: number[];
} {
  const box = opts.event.box_score_data as
    | { away_period_scores?: Array<number | null>; home_period_scores?: Array<number | null> }
    | undefined;
  const pairs: Array<{ index: number; away: number; home: number }> = [];

  if (
    box &&
    (Array.isArray(box.away_period_scores) || Array.isArray(box.home_period_scores))
  ) {
    const aArr = box.away_period_scores ?? [];
    const hArr = box.home_period_scores ?? [];
    const maxLen = Math.max(aArr.length, hArr.length);
    for (let i = 0; i < maxLen; i++) {
      const a = aArr[i];
      const h = hArr[i];
      if (typeof a === "number" && typeof h === "number") {
        pairs.push({ index: i + 1, away: a, home: h });
      }
    }
  } else if (Array.isArray(opts.event.linescore?.sets)) {
    // `linescore.sets` is `[homeGames, awayGames]` per set on the backend wire.
    opts.event.linescore.sets.forEach((tuple, idx) => {
      if (Array.isArray(tuple) && tuple.length >= 2) {
        const [h, a] = tuple;
        if (typeof a === "number" && typeof h === "number") {
          pairs.push({ index: idx + 1, away: a, home: h });
        }
      }
    });
  }

  const columns: HeadlineColumnSpec199[] = [];
  const awayCells: string[] = [];
  const homeCells: string[] = [];
  const awayEmph: number[] = [];
  const homeEmph: number[] = [];

  if (pairs.length > 0) {
    pairs.forEach((entry, offset) => {
      const isCurrentSet = opts.includePoints && offset === pairs.length - 1;
      columns.push({ role: "setScore", header: `S${entry.index}`, setIndex: entry.index });
      awayCells.push(String(entry.away));
      homeCells.push(String(entry.home));
      if (isCurrentSet || entry.away > entry.home) awayEmph.push(offset);
      if (isCurrentSet || entry.home > entry.away) homeEmph.push(offset);
    });
  } else if (opts.includePoints) {
    columns.push({ role: "setScore", header: "Sets", setIndex: 0 });
    if (opts.hasScore && opts.awaySetScore != null && opts.homeSetScore != null) {
      awayCells.push(String(opts.awaySetScore));
      homeCells.push(String(opts.homeSetScore));
      awayEmph.push(0);
      homeEmph.push(0);
    } else {
      awayCells.push("");
      homeCells.push("");
    }
  }

  if (opts.includePoints) {
    const pts = parseTennisGamePoints199(opts.event.espn?.game_clock);
    if (pts) {
      columns.push({ role: "gamePoints", header: "Pts" });
      awayCells.push(pts.away);
      homeCells.push(pts.home);
    }
  }

  return { columns, awayCells, homeCells, awayEmph, homeEmph };
}

function normalizeLiveBadgeClock199(opts: {
  event: EventDetailResponse;
  liveClockLabel: string | null | undefined;
}): string {
  const sport = opts.event.sport;
  if (isTennisSport199(sport)) {
    const rawPeriod = opts.event.espn?.period?.trim();
    if (rawPeriod) return `LIVE · ${normalizeTennisSetLabel(rawPeriod)}`;
    const box = opts.event.box_score_data as
      | { away_period_scores?: unknown[]; home_period_scores?: unknown[] }
      | undefined;
    const setCount = Math.max(
      box?.away_period_scores?.filter((x) => x != null).length ?? 0,
      box?.home_period_scores?.filter((x) => x != null).length ?? 0,
      opts.event.linescore?.sets?.length ?? 0,
    );
    if (setCount >= 1) return `LIVE · Set ${setCount}`;
    const trimmed = opts.liveClockLabel?.trim();
    if (trimmed && !parseTennisGamePoints199(trimmed)) {
      return `LIVE · ${trimmed}`;
    }
    return "LIVE";
  }

  if (isSoccerSport199(sport)) {
    const rawClock = opts.event.espn?.game_clock?.trim();
    if (rawClock && rawClock.includes("'")) return `LIVE · ${rawClock}`;
    const label = opts.liveClockLabel?.trim();
    if (label) {
      const cleaned = label.replace(/^(?:1st|2nd)\s*(?:Half)?\s*·\s*/i, "");
      return `LIVE · ${cleaned}`;
    }
    return "LIVE";
  }

  const rawLabel = opts.liveClockLabel?.trim();
  if (!rawLabel) return "LIVE";
  const compact = rawLabel
    .replace(/\b1st Quarter\b/gi, "Q1")
    .replace(/\b2nd Quarter\b/gi, "Q2")
    .replace(/\b3rd Quarter\b/gi, "Q3")
    .replace(/\b4th Quarter\b/gi, "Q4")
    .replace(/\b1st Period\b/gi, "P1")
    .replace(/\b2nd Period\b/gi, "P2")
    .replace(/\b3rd Period\b/gi, "P3")
    .replace(/\b1st Half\b/gi, "1H")
    .replace(/\b2nd Half\b/gi, "2H")
    .replace(/\s*·\s*/g, " ");
  return `LIVE · ${compact}`;
}

function suppressEmptyColumnHeaders(
  columns: HeadlineColumnSpec199[],
  rows: HeadlineCompetitorRow199[],
): { columns: HeadlineColumnSpec199[]; hasAnyColumnValue: boolean } {
  let hasAny = false;
  const resolved = columns.map((col, idx) => {
    const colHasValue = rows.some((row) => {
      const hasText = idx < row.cells.length && row.cells[idx] !== "";
      const hasTick = col.role === "finalResult" && row.won === true;
      return hasText || hasTick;
    });
    if (colHasValue) hasAny = true;
    return colHasValue ? col : { ...col, header: "" };
  });
  return { columns: resolved, hasAnyColumnValue: hasAny };
}

export interface ResolveEventPageHeadline199Input {
  event: EventDetailResponse;
  effectivelyLive: boolean;
  isLive: boolean;
  isFinished: boolean;
  isSuspended: boolean;
  venueVoided: boolean;
  venueSettledSentence: string | null;
  stoppageLabel: string | null;
  startClock: "clock" | "tbd" | "pending";
  pregameStateLabel?: string | null;
  liveClockLabel: string | null;
  bestHomeScore: number | null;
  bestAwayScore: number | null;
  heroScorePairPresent: boolean;
  heroScoreIsStoppageFiller: boolean;
  projectedPairRaw: { home_score: number; away_score: number } | null;
  projectedPairAdmitted: boolean;
  homeProb: number | null;
  servedAwayProb: number | null;
  homePct: number | null;
  servedAwayPct: number | null;
  probSourceLabel: string | null;
  tenthsOptIn: boolean;
  settledWinnerSide: "home" | "away" | null;
  gameMarkets?: {
    game_question_matrix?: unknown;
    other?: SoccerRawOtherRow[];
  } | null;
  nowMs?: number;
}

export function resolveEventPageHeadline199(
  input: ResolveEventPageHeadline199Input,
): HeadlineModel199 {
  const effectiveSport = input.event.sport ?? input.event.sport_key ?? null;
  const event: EventDetailResponse =
    input.event.sport === effectiveSport
      ? input.event
      : { ...input.event, sport: effectiveSport };
  const nowMs = input.nowMs ?? Date.now();
  const sportKey = effectiveSport ?? "unknown";
  const leagueLabel = resolveHeadlineLeagueLabel199(event);
  const shortNames = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );
  const homeKnown = lookupTeamColors(event.home_team);
  const awayKnown = lookupTeamColors(event.away_team);
  const teamHexes = resolveHeadlineTeamHexes199({
    homePrimary: event.home_team_data?.primary_color ?? homeKnown?.primary,
    awayPrimary: event.away_team_data?.primary_color ?? awayKnown?.primary,
    awaySecondary: effectiveAwaySecondaryColor(
      event.away_team,
      event.away_team_data?.secondary_color,
    ),
  });
  const colors = {
    away: teamHexes.away,
    home: teamHexes.home,
    drawText: HEADLINE_STYLE_199.drawTextInk,
    drawBar: HEADLINE_STYLE_199.drawBarInk,
  };

  const awayAbbr = event.away_team_data?.abbreviation ?? null;
  const homeAbbr = event.home_team_data?.abbreviation ?? null;

  const isNoResultEnded =
    !input.isFinished &&
    (input.venueVoided ||
      input.venueSettledSentence !== null ||
      (input.isSuspended && event.status !== "suspended"));

  const phase: HeadlinePhase199 =
    input.isFinished || isNoResultEnded
      ? "after"
      : input.effectivelyLive || input.isLive || input.isSuspended
        ? "during"
        : "before";

  // ── PHASE 1: BEFORE (`Proj. · Chance`) ───────────────────────────────────
  if (phase === "before") {
    const isStoppedBeforePlay = input.stoppageLabel !== null;
    const isOpeningOnlyFallback =
      input.probSourceLabel === "Opening line" ||
      event.hero_probability_source === "opening" ||
      ((event.current_odds as { quote_kind?: string } | undefined)?.quote_kind === "opening" &&
        event.hero_probability_source !== "blend");
    const canGrade = !isStoppedBeforePlay && !isOpeningOnlyFallback;

    const startTimeText = isStoppedBeforePlay
      ? null
      : formatPregameStart199(
          event.commence_time,
          event.start_is_tbd,
          input.startClock,
          input.pregameStateLabel,
          nowMs,
        );
    const broadcastText =
      !isStoppedBeforePlay &&
      !input.isFinished &&
      !input.isSuspended &&
      event.espn?.broadcast?.trim()
        ? event.espn.broadcast.trim()
        : null;
    const plainMetaText = isStoppedBeforePlay
      ? `${leagueLabel} · ${sanitizeBannedWords199(input.stoppageLabel!)}`
      : startTimeText
        ? `${leagueLabel} · ${startTimeText}`
        : leagueLabel;

    const hasProjCol = carriesProjectedScoreColumn199(event.sport);
    const baseColumns: HeadlineColumnSpec199[] = hasProjCol
      ? [
          { role: "projected", header: "Proj." },
          { role: "chance", header: "Chance" },
        ]
      : [{ role: "chance", header: "Chance" }];

    const awayProjCell =
      canGrade && hasProjCol && input.projectedPairAdmitted && input.projectedPairRaw
        ? formatHeadlineProjectedNumber199(input.projectedPairRaw.away_score, event.sport)
        : "";
    const homeProjCell =
      canGrade && hasProjCol && input.projectedPairAdmitted && input.projectedPairRaw
        ? formatHeadlineProjectedNumber199(input.projectedPairRaw.home_score, event.sport)
        : "";

    const awayRecord = cleanRecordString(
      event.away_team_data?.record ?? event.standings_context?.away,
    );
    const homeRecord = cleanRecordString(
      event.home_team_data?.record ?? event.standings_context?.home,
    );

    if (canGrade && isSoccerSport199(event.sport)) {
      const snap = extractSoccerThreeWaySnapshot199({
        event,
        shortNames,
        gameMarkets: input.gameMarkets,
        finished: false,
        nowMs,
      });
      if (snap.openShares) {
        const texts = formatSoccerThreeWayTexts199(
          snap.openShares.home,
          snap.openShares.draw,
          snap.openShares.away,
          false,
        );
        const rows: HeadlineCompetitorRow199[] = [
          {
            role: "home",
            fullName: event.home_team,
            opponentFullName: event.away_team,
            shortName: shortNames.home,
            record: homeRecord,
            cells: hasProjCol ? [homeProjCell, texts.home] : [texts.home],
            rawProbability: snap.openShares.home,
            won: null,
            emphasizedColumns: [],
            abbreviation: homeAbbr,
            opponentAbbreviation: awayAbbr,
          },
          {
            role: "away",
            fullName: event.away_team,
            opponentFullName: event.home_team,
            shortName: shortNames.away,
            record: awayRecord,
            cells: hasProjCol ? [awayProjCell, texts.away] : [texts.away],
            rawProbability: snap.openShares.away,
            won: null,
            emphasizedColumns: [],
            abbreviation: awayAbbr,
            opponentAbbreviation: homeAbbr,
          },
          {
            role: "draw",
            fullName: "Draw",
            opponentFullName: "",
            shortName: "Draw",
            record: null,
            cells: hasProjCol ? ["", texts.draw] : [texts.draw],
            rawProbability: snap.openShares.draw,
            won: null,
            emphasizedColumns: [],
            abbreviation: null,
            opponentAbbreviation: null,
          },
        ];
        const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
        return {
          eventId: event.id,
          sportKey,
          phase,
          leagueLabel,
          plainMetaText,
          startTimeText,
          broadcastText,
          liveBadgeText: null,
          isStoppedOrNoResult: false,
          columns: suppressed.columns,
          hasAnyColumnValue: suppressed.hasAnyColumnValue,
          rows,
          bottomBar: {
            kind: "threeWay",
            homeShare: snap.openShares.home,
            drawShare: snap.openShares.draw,
            awayShare: snap.openShares.away,
          },
          livePregameSummary: null,
          colors,
        };
      }
    }

    let awayChance = "";
    let homeChance = "";
    let awayRaw: number | null = null;
    let homeRaw: number | null = null;
    let bottomBar: HeadlineBottomBar199 | null = null;

    if (canGrade && input.homeProb !== null && Number.isFinite(input.homeProb)) {
      const awayAllowed = printableAway(input.servedAwayProb, event.sport);
      const awayPctAllowed = printableAway(input.servedAwayPct, event.sport);
      homeRaw = input.homeProb;
      homeChance = formatProbability(input.homeProb, { rendered: input.homePct });
      if (!sportPricesADraw(event.sport) && awayAllowed !== null) {
        awayRaw = awayAllowed;
        awayChance = formatProbability(awayAllowed, { rendered: awayPctAllowed });
        bottomBar = {
          kind: "twoWay",
          awayShare: awayAllowed,
          homeShare: input.homeProb,
          pregameAwayMarker: null,
        };
      }
    }

    const rows: HeadlineCompetitorRow199[] = [
      {
        role: "away",
        fullName: event.away_team,
        opponentFullName: event.home_team,
        shortName: shortNames.away,
        record: awayRecord,
        cells: hasProjCol ? [awayProjCell, awayChance] : [awayChance],
        rawProbability: awayRaw,
        won: null,
        emphasizedColumns: [],
        abbreviation: awayAbbr,
        opponentAbbreviation: homeAbbr,
      },
      {
        role: "home",
        fullName: event.home_team,
        opponentFullName: event.away_team,
        shortName: shortNames.home,
        record: homeRecord,
        cells: hasProjCol ? [homeProjCell, homeChance] : [homeChance],
        rawProbability: homeRaw,
        won: null,
        emphasizedColumns: [],
        abbreviation: homeAbbr,
        opponentAbbreviation: awayAbbr,
      },
    ];
    const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
    return {
      eventId: event.id,
      sportKey,
      phase,
      leagueLabel,
      plainMetaText,
      startTimeText,
      broadcastText,
      liveBadgeText: null,
      isStoppedOrNoResult: isStoppedBeforePlay,
      columns: suppressed.columns,
      hasAnyColumnValue: suppressed.hasAnyColumnValue,
      rows,
      bottomBar,
      livePregameSummary: null,
      colors,
    };
  }

  // ── PHASE 2: DURING (`Score · Proj. · Now` + bar + single grey line) ─────
  if (phase === "during") {
    const isLiveActive = input.effectivelyLive;
    const liveBadgeText = isLiveActive
      ? normalizeLiveBadgeClock199({ event, liveClockLabel: input.liveClockLabel })
      : null;
    const plainMetaText = isLiveActive
      ? null
      : input.stoppageLabel
        ? `${leagueLabel} · ${sanitizeBannedWords199(input.stoppageLabel)}`
        : event.status === "suspended"
          ? `${leagueLabel} · Suspended`
          : `${leagueLabel} · Ended · no result reported`;

    const isTennis = isTennisSport199(event.sport);
    const isScoreless = isMMASport199(event.sport) || isBoxingSport199(event.sport);
    const hasProjCol = carriesProjectedScoreColumn199(event.sport);
    const hasValidScore =
      input.heroScorePairPresent && !input.heroScoreIsStoppageFiller;

    const awayProjCell =
      isLiveActive && hasProjCol && input.projectedPairAdmitted && input.projectedPairRaw
        ? formatHeadlineProjectedNumber199(
            Math.max(input.projectedPairRaw.away_score, input.bestAwayScore ?? 0),
            event.sport,
          )
        : "";
    const homeProjCell =
      isLiveActive && hasProjCol && input.projectedPairAdmitted && input.projectedPairRaw
        ? formatHeadlineProjectedNumber199(
            Math.max(input.projectedPairRaw.home_score, input.bestHomeScore ?? 0),
            event.sport,
          )
        : "";

    const tennisSlot = isTennis
      ? buildTennisScoreSlot199({
          event,
          awaySetScore: input.bestAwayScore,
          homeSetScore: input.bestHomeScore,
          hasScore: hasValidScore,
          includePoints: isLiveActive,
        })
      : null;

    const baseColumns: HeadlineColumnSpec199[] = tennisSlot
      ? [...tennisSlot.columns, { role: "now", header: "Now" }]
      : [
          ...(!isScoreless ? [{ role: "score" as const, header: "Score" }] : []),
          ...(hasProjCol ? [{ role: "projected" as const, header: "Proj." }] : []),
          { role: "now" as const, header: "Now" },
        ];

    const pregameProj = isLiveActive
      ? qualifiedLivePregameProjectionPair199(event)
      : null;

    if (isLiveActive && isSoccerSport199(event.sport)) {
      const snap = extractSoccerThreeWaySnapshot199({
        event,
        shortNames,
        gameMarkets: input.gameMarkets,
        finished: false,
        nowMs,
      });
      if (snap.openShares) {
        const texts = formatSoccerThreeWayTexts199(
          snap.openShares.home,
          snap.openShares.draw,
          snap.openShares.away,
          input.tenthsOptIn,
        );
        let liveSummary: HeadlineLivePregameSummary199 | null = null;
        if (snap.pregameShares) {
          const preTexts = formatSoccerThreeWayTexts199(
            snap.pregameShares.home,
            snap.pregameShares.draw,
            snap.pregameShares.away,
            false,
          );
          let favName = shortNames.home;
          let favText = preTexts.home;
          let favIsHome = true;
          let favSide: HeadlineRowRole199 = "home";
          if (
            snap.pregameShares.away > snap.pregameShares.home &&
            snap.pregameShares.away >= snap.pregameShares.draw
          ) {
            favName = shortNames.away;
            favText = preTexts.away;
            favIsHome = false;
            favSide = "away";
          } else if (
            snap.pregameShares.draw > snap.pregameShares.home &&
            snap.pregameShares.draw > snap.pregameShares.away
          ) {
            favName = "Draw";
            favText = preTexts.draw;
            favIsHome = true;
            favSide = "draw";
          }
          const namedText = `${favName} ${favText}`;
          const firstProjText = pregameProj
            ? favIsHome
              ? pregameProj.home
              : pregameProj.away
            : null;
          const secondProjText = pregameProj
            ? favIsHome
              ? pregameProj.away
              : pregameProj.home
            : null;
          const firstProjSide: "home" | "away" | null = pregameProj
            ? favIsHome
              ? "home"
              : "away"
            : null;
          const secondProjSide: "home" | "away" | null = pregameProj
            ? favIsHome
              ? "away"
              : "home"
            : null;
          const projHalf = pregameProj
            ? ` · projected ${firstProjText}–${secondProjText}`
            : "";
          const bodyText = `${namedText}${projHalf}`;
          liveSummary = {
            leadWord: "Pregame",
            bodyText,
            fullText: `Pregame  ${bodyText}`,
            namedText,
            namedSide: favSide,
            firstProjText,
            firstProjSide,
            secondProjText,
            secondProjSide,
          };
        }

        const homeScoreCell =
          hasValidScore && input.bestHomeScore != null ? String(input.bestHomeScore) : "";
        const awayScoreCell =
          hasValidScore && input.bestAwayScore != null ? String(input.bestAwayScore) : "";

        const rows: HeadlineCompetitorRow199[] = [
          {
            role: "home",
            fullName: event.home_team,
            opponentFullName: event.away_team,
            shortName: shortNames.home,
            record: null,
            cells: [homeScoreCell, homeProjCell, texts.home],
            rawProbability: snap.openShares.home,
            won: null,
            emphasizedColumns: [],
            abbreviation: homeAbbr,
            opponentAbbreviation: awayAbbr,
          },
          {
            role: "away",
            fullName: event.away_team,
            opponentFullName: event.home_team,
            shortName: shortNames.away,
            record: null,
            cells: [awayScoreCell, awayProjCell, texts.away],
            rawProbability: snap.openShares.away,
            won: null,
            emphasizedColumns: [],
            abbreviation: awayAbbr,
            opponentAbbreviation: homeAbbr,
          },
          {
            role: "draw",
            fullName: "Draw",
            opponentFullName: "",
            shortName: "Draw",
            record: null,
            cells: ["", "", texts.draw],
            rawProbability: snap.openShares.draw,
            won: null,
            emphasizedColumns: [],
            abbreviation: null,
            opponentAbbreviation: null,
          },
        ];
        const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
        return {
          eventId: event.id,
          sportKey,
          phase,
          leagueLabel,
          plainMetaText: null,
          startTimeText: null,
          broadcastText: null,
          liveBadgeText,
          isStoppedOrNoResult: false,
          columns: suppressed.columns,
          hasAnyColumnValue: suppressed.hasAnyColumnValue,
          rows,
          bottomBar: {
            kind: "threeWay",
            homeShare: snap.openShares.home,
            drawShare: snap.openShares.draw,
            awayShare: snap.openShares.away,
          },
          livePregameSummary: liveSummary,
          colors,
        };
      }
    }

    const strictPre = isLiveActive ? resolveStrictPrematch199(event) : null;
    const rawSummary = isLiveActive
      ? formatLivePregameSummary(
          {
            sport: isTennis ? event.sport : "americanfootball_nfl",
            pregame_home_pct: strictPre?.homePct ?? null,
            pregame_away_pct: strictPre?.awayPct ?? null,
            pregame_projected_home: pregameProj?.home ?? null,
            pregame_projected_away: pregameProj?.away ?? null,
          },
          shortNames.away,
          shortNames.home,
        )
      : null;
    const livePregameSummary: HeadlineLivePregameSummary199 | null = rawSummary
      ? {
          leadWord: "Pregame",
          bodyText: rawSummary.body,
          fullText: rawSummary.fullText,
          namedText: rawSummary.namedText,
          namedSide: rawSummary.namedSide,
          firstProjText: rawSummary.firstProjText,
          firstProjSide: rawSummary.firstProjSide,
          secondProjText: rawSummary.secondProjText,
          secondProjSide: rawSummary.secondProjSide,
        }
      : null;

    let awayNow = "";
    let homeNow = "";
    let awayRaw: number | null = null;
    let homeRaw: number | null = null;
    let bottomBar: HeadlineBottomBar199 | null = null;

    const isOpeningOnly =
      input.probSourceLabel === "Opening line" ||
      (event.hero_probability_source === "opening" && input.probSourceLabel === null);

    const canShowInPlayReading =
      (isLiveActive || event.status === "live") &&
      !input.venueVoided &&
      input.venueSettledSentence === null &&
      input.stoppageLabel === null;

    if (
      canShowInPlayReading &&
      !isOpeningOnly &&
      input.homeProb !== null &&
      Number.isFinite(input.homeProb)
    ) {
      const awayWithheld = sportPricesADraw(event.sport);
      const awayAllowed = printableAway(input.servedAwayProb, event.sport);
      homeRaw = input.homeProb;
      if (input.tenthsOptIn) {
        const tenths = formatLiveTenthsPair(awayAllowed, input.homeProb, awayWithheld);
        homeNow = tenths.home ?? "";
        awayNow = tenths.away ?? "";
      } else {
        homeNow = formatProbability(input.homeProb, { rendered: input.homePct });
        awayNow =
          !awayWithheld && awayAllowed !== null
            ? formatProbability(awayAllowed, {
                rendered: printableAway(input.servedAwayPct, event.sport),
              })
            : "";
      }
      if (!awayWithheld && awayAllowed !== null) {
        awayRaw = awayAllowed;
        bottomBar = {
          kind: "twoWay",
          awayShare: awayAllowed,
          homeShare: input.homeProb,
          pregameAwayMarker: strictPre?.awayProb ?? null,
        };
      } else if (awayWithheld && homeNow === "" && input.tenthsOptIn) {
        homeNow = formatSingleLiveTenths(input.homeProb) ?? "";
      }
    }

    const canShowScoreSlot =
      !isScoreless &&
      !input.heroScoreIsStoppageFiller &&
      (isLiveActive || event.status === "suspended");
    const awayScoreCell =
      canShowScoreSlot && input.bestAwayScore != null
        ? String(input.bestAwayScore)
        : "";
    const homeScoreCell =
      canShowScoreSlot && input.bestHomeScore != null
        ? String(input.bestHomeScore)
        : "";

    const awayCells = tennisSlot
      ? [...tennisSlot.awayCells, awayNow]
      : [
          ...(!isScoreless ? [awayScoreCell] : []),
          ...(hasProjCol ? [awayProjCell] : []),
          awayNow,
        ];
    const homeCells = tennisSlot
      ? [...tennisSlot.homeCells, homeNow]
      : [
          ...(!isScoreless ? [homeScoreCell] : []),
          ...(hasProjCol ? [homeProjCell] : []),
          homeNow,
        ];

    const rows: HeadlineCompetitorRow199[] = [
      {
        role: "away",
        fullName: event.away_team,
        opponentFullName: event.home_team,
        shortName: shortNames.away,
        record: null,
        cells: awayCells,
        rawProbability: awayRaw,
        won: null,
        emphasizedColumns: tennisSlot?.awayEmph ?? [],
        abbreviation: awayAbbr,
        opponentAbbreviation: homeAbbr,
      },
      {
        role: "home",
        fullName: event.home_team,
        opponentFullName: event.away_team,
        shortName: shortNames.home,
        record: null,
        cells: homeCells,
        rawProbability: homeRaw,
        won: null,
        emphasizedColumns: tennisSlot?.homeEmph ?? [],
        abbreviation: homeAbbr,
        opponentAbbreviation: awayAbbr,
      },
    ];
    const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
    return {
      eventId: event.id,
      sportKey,
      phase,
      leagueLabel,
      plainMetaText,
      startTimeText: null,
      broadcastText: null,
      liveBadgeText,
      isStoppedOrNoResult: !isLiveActive,
      columns: suppressed.columns,
      hasAnyColumnValue: suppressed.hasAnyColumnValue,
      rows,
      bottomBar,
      livePregameSummary,
      colors,
    };
  }

  // ── PHASE 3: AFTER (`[Sets] · Pregame · Final`, winner ticked, no bar) ───
  const strictPre = input.isFinished ? resolveStrictPrematch199(event) : null;

  if (input.isFinished && isSoccerSport199(event.sport)) {
    const snap = extractSoccerThreeWaySnapshot199({
      event,
      shortNames,
      gameMarkets: input.gameMarkets,
      finished: true,
      nowMs,
    });
    const fp = (event.final_score_period as string | null | undefined)?.trim().toLowerCase();
    const nonRegFinish = fp === "extra_time" || fp === "penalties" || fp === "aet" || fp === "pen";

    let winnerRole: "home" | "draw" | "away" | null = snap.confirmedWinner;
    if (!winnerRole && !(nonRegFinish && snap.pregameShares)) {
      if (event.hero_settled_result === "draw") winnerRole = "draw";
      else if (event.hero_settled_result === "home") winnerRole = "home";
      else if (event.hero_settled_result === "away") winnerRole = "away";
      else if (
        input.bestHomeScore != null &&
        input.bestAwayScore != null &&
        !input.heroScoreIsStoppageFiller
      ) {
        if (input.bestHomeScore > input.bestAwayScore) winnerRole = "home";
        else if (input.bestAwayScore > input.bestHomeScore) winnerRole = "away";
        else winnerRole = "draw";
      }
    }

    if (snap.pregameShares || winnerRole === "draw") {
      const preTexts = snap.pregameShares
        ? formatSoccerThreeWayTexts199(
            snap.pregameShares.home,
            snap.pregameShares.draw,
            snap.pregameShares.away,
            false,
          )
        : { home: "", draw: "", away: "" };

      const hasScores =
        input.bestHomeScore != null &&
        input.bestAwayScore != null &&
        !input.heroScoreIsStoppageFiller;
      const homeFinalText = hasScores
        ? String(input.bestHomeScore)
        : winnerRole === "home"
          ? "Won"
          : winnerRole === "away"
            ? "Lost"
            : "";
      const awayFinalText = hasScores
        ? String(input.bestAwayScore)
        : winnerRole === "away"
          ? "Won"
          : winnerRole === "home"
            ? "Lost"
            : "";
      const drawFinalText =
        winnerRole == null ? "" : winnerRole === "draw" ? "" : "—";

      const rows: HeadlineCompetitorRow199[] = [
        {
          role: "home",
          fullName: event.home_team,
          opponentFullName: event.away_team,
          shortName: shortNames.home,
          record: null,
          cells: [preTexts.home, homeFinalText],
          rawProbability: snap.pregameShares?.home ?? null,
          won: winnerRole == null ? null : winnerRole === "home" ? true : winnerRole === "away" ? false : null,
          emphasizedColumns: [],
          abbreviation: homeAbbr,
          opponentAbbreviation: awayAbbr,
        },
        {
          role: "away",
          fullName: event.away_team,
          opponentFullName: event.home_team,
          shortName: shortNames.away,
          record: null,
          cells: [preTexts.away, awayFinalText],
          rawProbability: snap.pregameShares?.away ?? null,
          won: winnerRole == null ? null : winnerRole === "away" ? true : winnerRole === "home" ? false : null,
          emphasizedColumns: [],
          abbreviation: awayAbbr,
          opponentAbbreviation: homeAbbr,
        },
        {
          role: "draw",
          fullName: "Draw",
          opponentFullName: "",
          shortName: "Draw",
          record: null,
          cells: [preTexts.draw, drawFinalText],
          rawProbability: snap.pregameShares?.draw ?? null,
          won: winnerRole == null ? null : winnerRole === "draw",
          emphasizedColumns: [],
          abbreviation: null,
          opponentAbbreviation: null,
        },
      ];
      const baseColumns: HeadlineColumnSpec199[] = [
        { role: "pregame", header: "Pregame" },
        { role: "finalResult", header: "Final" },
      ];
      const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
      return {
        eventId: event.id,
        sportKey,
        phase,
        leagueLabel,
        plainMetaText: formatAfterMeta199(leagueLabel, event),
        startTimeText: null,
        broadcastText: null,
        liveBadgeText: null,
        isStoppedOrNoResult: false,
        columns: suppressed.columns,
        hasAnyColumnValue: suppressed.hasAnyColumnValue,
        rows,
        bottomBar: null,
        livePregameSummary: null,
        colors,
      };
    }
  }

  let awayPre = "";
  let homePre = "";
  if (strictPre) {
    homePre = formatProbability(strictPre.homeProb, { rendered: strictPre.homePct });
    if (strictPre.awayProb != null) {
      awayPre = formatProbability(strictPre.awayProb, { rendered: strictPre.awayPct });
    }
  }

  const isScoreless = isMMASport199(event.sport) || isBoxingSport199(event.sport);
  const bothScoresPresent =
    input.isFinished &&
    !isScoreless &&
    input.heroScorePairPresent &&
    !input.heroScoreIsStoppageFiller &&
    input.bestAwayScore != null &&
    input.bestHomeScore != null;

  let resolvedWinner: "home" | "away" | "draw" | null = null;
  if (input.isFinished && !input.venueVoided) {
    if (input.settledWinnerSide) {
      resolvedWinner = input.settledWinnerSide;
    } else if (event.hero_settled_result === "home") {
      resolvedWinner = "home";
    } else if (event.hero_settled_result === "away") {
      resolvedWinner = "away";
    } else if (event.hero_settled_result === "draw") {
      resolvedWinner = "draw";
    } else if (bothScoresPresent && input.bestAwayScore === input.bestHomeScore) {
      resolvedWinner = "draw";
    }
  }

  let awayWon: boolean | null = null;
  let homeWon: boolean | null = null;
  let awayFinalText = "";
  let homeFinalText = "";
  let extraMetaOutcome: string | null = null;

  if (!input.isFinished || input.venueVoided) {
    awayWon = null;
    homeWon = null;
    awayFinalText = "";
    homeFinalText = "";
  } else if (bothScoresPresent) {
    awayFinalText = String(input.bestAwayScore);
    homeFinalText = String(input.bestHomeScore);
    if (resolvedWinner === "away") {
      awayWon = true;
      homeWon = false;
    } else if (resolvedWinner === "home") {
      awayWon = false;
      homeWon = true;
    } else if (resolvedWinner === "draw") {
      extraMetaOutcome = "Draw";
    }
  } else if (resolvedWinner === "away") {
    awayWon = true;
    homeWon = false;
    awayFinalText = "Won";
    homeFinalText = "Lost";
  } else if (resolvedWinner === "home") {
    awayWon = false;
    homeWon = true;
    awayFinalText = "Lost";
    homeFinalText = "Won";
  } else if (resolvedWinner === "draw") {
    extraMetaOutcome = "Draw";
  }

  let afterMetaText: string;
  if (input.venueVoided || event.venue_closed_no_winner === true) {
    afterMetaText = `${leagueLabel} · Ended · no winner`;
  } else if (!input.isFinished) {
    const rawVerdict = event.venue_settled_result?.trim();
    if (rawVerdict) {
      const lowerV = rawVerdict.toLowerCase();
      if (
        lowerV === "settled by venue" ||
        lowerV === "ended by venue" ||
        lowerV === "settled" ||
        lowerV === "no result reported"
      ) {
        afterMetaText = `${leagueLabel} · Ended · no result reported`;
      } else {
        afterMetaText = `${leagueLabel} · Ended · ${sanitizeBannedWords199(rawVerdict)}`;
      }
    } else {
      afterMetaText = `${leagueLabel} · Ended · no result reported`;
    }
  } else {
    afterMetaText = formatAfterMeta199(leagueLabel, event, extraMetaOutcome);
  }

  const tennisFinishedSlot =
    input.isFinished && isTennisSport199(event.sport)
      ? (() => {
          const slot = buildTennisScoreSlot199({
            event,
            awaySetScore: input.bestAwayScore,
            homeSetScore: input.bestHomeScore,
            hasScore: false,
            includePoints: false,
          });
          return slot.columns.length > 0 ? slot : null;
        })()
      : null;

  const baseColumns: HeadlineColumnSpec199[] = [
    ...(tennisFinishedSlot?.columns ?? []),
    { role: "pregame", header: "Pregame" },
    { role: "finalResult", header: "Final" },
  ];

  const rows: HeadlineCompetitorRow199[] = [
    {
      role: "away",
      fullName: event.away_team,
      opponentFullName: event.home_team,
      shortName: shortNames.away,
      record: null,
      cells: [...(tennisFinishedSlot?.awayCells ?? []), awayPre, awayFinalText],
      rawProbability: strictPre?.awayProb ?? null,
      won: awayWon,
      emphasizedColumns: tennisFinishedSlot?.awayEmph ?? [],
      abbreviation: awayAbbr,
      opponentAbbreviation: homeAbbr,
    },
    {
      role: "home",
      fullName: event.home_team,
      opponentFullName: event.away_team,
      shortName: shortNames.home,
      record: null,
      cells: [...(tennisFinishedSlot?.homeCells ?? []), homePre, homeFinalText],
      rawProbability: strictPre?.homeProb ?? null,
      won: homeWon,
      emphasizedColumns: tennisFinishedSlot?.homeEmph ?? [],
      abbreviation: homeAbbr,
      opponentAbbreviation: awayAbbr,
    },
  ];
  const suppressed = suppressEmptyColumnHeaders(baseColumns, rows);
  return {
    eventId: event.id,
    sportKey,
    phase,
    leagueLabel,
    plainMetaText: afterMetaText,
    startTimeText: null,
    broadcastText: null,
    liveBadgeText: null,
    isStoppedOrNoResult: !input.isFinished || input.venueVoided,
    columns: suppressed.columns,
    hasAnyColumnValue: suppressed.hasAnyColumnValue,
    rows,
    bottomBar: null,
    livePregameSummary: null,
    colors,
  };
}
