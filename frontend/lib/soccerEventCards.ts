/**
 * #11974 Step E6c — Soccer game-story cards on web (`soccer_*`), behind `?atlas=1`.
 *
 * Mirrors the event-page atlas soccer specification (`artifacts/discovery-containers-release-plan/event-page-design-20261011/atlas-v6/COMPONENT-CONTRACT.md`
 * and `prototype/src/Atlas.tsx`):
 *   1. Three-way match outcome (`soccer-three-way`): Home / Draw / Away on a
 *      shared 0–100% probability scale ("A draw is a real third outcome" before
 *      full-time; "Full-time three-way result" after). Refuses any market that
 *      does not explicitly supply all three legs — never invents a draw from
 *      `1 - home - away`, and never normalizes the three quotes to 100%.
 *   2. Exact-score landscape (`soccer-exact-score`): 2D discrete score grid
 *      (`homeGoals` across × `awayGoals` down) built from supplied Exact Score /
 *      Correct Score outcomes without inventing missing cells as 0% or normalizing
 *      cells into a synthetic distribution.
 *   3. Goal expectations (`ladder`, `family: "total"`, `unit: "goals"`): full-game
 *      goal thresholds from `game_question_matrix` / `gameMarkets.totals`.
 */

import { labelNamesSide } from "./eventOwnMoneyline";
import { isFinishedStatus } from "./eventState";
import {
  decodeQuestionMatrix,
  MIN_LADDER_LINES,
  type LadderCard,
  type LadderPhase,
  type LadderPoint,
  type MatrixOption,
} from "./nbaEventCards";
import { isRecentQuote, type NflEventCard } from "./nflEventCardDeck";

export function soccerCardsApply(sportKey: string | null | undefined, atlasMode = false): boolean {
  return Boolean(atlasMode && typeof sportKey === "string" && sportKey.startsWith("soccer_"));
}

function openChance(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value > 0 && value < 1 ? value : null;
}

function parseMs(value: string | null | undefined): number | null {
  if (typeof value !== "string") return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

function phaseOf(
  status: string | null | undefined,
  commenceTime: string | null | undefined,
  nowMs: number,
): LadderPhase {
  if (isFinishedStatus(status)) return "after";
  const c = parseMs(commenceTime);
  if (status === "live" || c === null || c <= nowMs) return "during";
  return "before";
}

export interface SoccerRawOtherRow {
  market_name?: string | null;
  outcome_name?: string | null;
  probability?: number | null;
  opening_probability?: number | null;
  pregame_mark?: number | null;
  observed_at?: string | null;
  source?: string | null;
  is_winner?: boolean | null;
  resolution_source?: string | null;
  _market_id?: number | string | null;
}

export interface SoccerRawTotalRow {
  threshold?: number | null;
  over_probability?: number | null;
  opening_probability?: number | null;
  pregame_mark?: number | null;
  observed_at?: string | null;
  source?: string | null;
  market_type?: string | null;
  market_name?: string | null;
  outcome_name?: string | null;
  is_winner?: boolean | null;
  period?: string | null;
  _market_id?: number | string | null;
}

// ─── 1. Three-way match outcome ("A draw is a real third outcome") ─────────

export type SoccerThreeWayRole = "home" | "draw" | "away";

export interface SoccerThreeWayLeg {
  role: SoccerThreeWayRole;
  label: string;
  rawOutcomeLabel: string;
  quotedChance: number | null;
  pregameChance: number | null;
  observedAt: string | null;
  pregameObservedAt: string | null;
  result: "won" | "lost" | null;
  source: string | null;
}

export interface SoccerThreeWayCard {
  kind: "soccer-three-way";
  id: "soccer:threeWay";
  phase: LadderPhase;
  legs: [SoccerThreeWayLeg, SoccerThreeWayLeg, SoccerThreeWayLeg];
  marketTitle: string;
  source: string | null;
  quotedSum: number | null;
}

export function soccerThreeWayHeadline(card: SoccerThreeWayCard): string {
  if (card.phase === "after") {
    const drawLeg = card.legs.find((l) => l.role === "draw");
    if (drawLeg?.result === "won") return "Finished level — a draw was the third outcome";
    return "Full-time three-way result";
  }
  return "A draw is a real third outcome";
}

export function soccerThreeWayReason(card: SoccerThreeWayCard): string {
  if (card.phase === "after") {
    return "90-minute Home, Draw, and Away outcomes graded independently";
  }
  if (card.quotedSum !== null) {
    const pct = Math.round(card.quotedSum * 1000) / 10;
    return `Recorded three-way quotes total ${pct}% · no normalization or invented draw`;
  }
  return "Three supplied 90-minute outcomes · no normalization or invented draw";
}

function isDisqualifiedThreeWayMarketName(name: string): boolean {
  const lower = name.toLowerCase();
  return (
    /\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|halftime|half-time|half\s+time)\b/.test(lower) ||
    /\b(?:corner|corners|card|cards|shot|shots|goalscorer|first\s+team\s+to\s+score|last\s+team\s+to\s+score|both\s+teams\s+to\s+score|btts|exact\s+score|correct\s+score|advance|qualify|tiebreaker|over\/under|o\/u|spread|handicap)\b/.test(
      lower,
    )
  );
}

function stripSoccerClubAffixes(value: string): string {
  return value
    .replace(/\b(?:fc|afc|cf|sc|ac|sv|bv|vfb|vfl|rb|tsg|fsv|bsc|ud|cd|rcd|rc|fk|sk|nk|if|bk|ik|\d{2,4})\b/gi, " ")
    .replace(/[.,]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function soccerNameMatchesSide(
  candidate: string,
  team: string,
  shortName: string,
): boolean {
  const c = candidate.trim();
  if (!c) return false;
  if (
    labelNamesSide(c, team) ||
    labelNamesSide(team, c) ||
    labelNamesSide(c, shortName) ||
    labelNamesSide(shortName, c) ||
    c.toLowerCase() === team.toLowerCase() ||
    c.toLowerCase() === shortName.toLowerCase()
  ) {
    return true;
  }
  const strippedCandidate = stripSoccerClubAffixes(c);
  const strippedTeam = stripSoccerClubAffixes(team);
  const strippedShort = stripSoccerClubAffixes(shortName);
  if (!strippedCandidate) return false;
  return (
    (Boolean(strippedTeam) &&
      (labelNamesSide(strippedCandidate, strippedTeam) ||
        labelNamesSide(strippedTeam, strippedCandidate) ||
        strippedCandidate.toLowerCase() === strippedTeam.toLowerCase())) ||
    (Boolean(strippedShort) &&
      (labelNamesSide(strippedCandidate, strippedShort) ||
        labelNamesSide(strippedShort, strippedCandidate) ||
        strippedCandidate.toLowerCase() === strippedShort.toLowerCase()))
  );
}

function classifyThreeWayRole(
  outcomeLabel: string,
  homeTeam: string,
  awayTeam: string,
  homeShort: string,
  awayShort: string,
): SoccerThreeWayRole | null {
  const trimmed = outcomeLabel.trim();
  if (!trimmed) return null;
  if (/^(?:draw|tie)(?:\b|\s*\()/i.test(trimmed)) return "draw";

  const cleaned = trimmed.replace(/\s+wins$/i, "").trim();
  if (soccerNameMatchesSide(cleaned, homeTeam, homeShort)) {
    return "home";
  }
  if (soccerNameMatchesSide(cleaned, awayTeam, awayShort)) {
    return "away";
  }
  return null;
}

export function buildSoccerThreeWayCard(opts: {
  gameQuestionMatrix?: unknown;
  otherMarkets?: SoccerRawOtherRow[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  homeShort: string;
  awayShort: string;
  homeScore?: number | null;
  awayScore?: number | null;
  nowMs: number;
}): SoccerThreeWayCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const finished = phase === "after";

  type CandidateMarket = {
    marketTitle: string;
    source: string | null;
    legsByRole: Map<SoccerThreeWayRole, SoccerThreeWayLeg>;
    score: number;
  };

  const candidates: CandidateMarket[] = [];

  // 1. Check game_question_matrix questions
  const questions = decodeQuestionMatrix(opts.gameQuestionMatrix);
  for (const q of questions) {
    const title = (q.marketName || q.label || "").trim();
    if (!title || isDisqualifiedThreeWayMarketName(title)) continue;
    if (q.periodKey && q.periodKey !== "full_game") continue;
    if (q.options.length !== 3) continue;

    const legsByRole = new Map<SoccerThreeWayRole, SoccerThreeWayLeg>();
    for (const o of q.options) {
      const role = classifyThreeWayRole(
        o.label,
        opts.homeTeam,
        opts.awayTeam,
        opts.homeShort,
        opts.awayShort,
      );
      if (!role || legsByRole.has(role)) break;
      const quotedChance =
        !finished && isRecentQuote(o.observedAt, opts.nowMs) ? openChance(o.quoted) : null;
      const pregameChance = openChance(o.reading ?? o.baseline);
      const pregameObservedAt = o.readingObservedAt ?? o.baselineObservedAt ?? null;
      const result: "won" | "lost" | null =
        finished && typeof o.result === "boolean" ? (o.result ? "won" : "lost") : null;
      legsByRole.set(role, {
        role,
        label: role === "home" ? opts.homeShort : role === "away" ? opts.awayShort : "Draw",
        rawOutcomeLabel: o.label,
        quotedChance,
        pregameChance,
        observedAt: o.observedAt,
        pregameObservedAt,
        result,
        source: o.source,
      });
    }

    if (legsByRole.size === 3) {
      const allLegs = Array.from(legsByRole.values());
      const pricedCount = allLegs.filter(
        (l) => l.quotedChance !== null || l.pregameChance !== null,
      ).length;
      const settledCount = allLegs.filter((l) => l.result !== null).length;
      const score = pricedCount * 10 + settledCount * 5 + (allLegs[0]?.pregameChance !== null ? 3 : 0);
      candidates.push({
        marketTitle: title,
        source: allLegs.find((l) => l.source)?.source ?? null,
        legsByRole,
        score,
      });
    }
  }

  // 2. Also check gameMarkets.other grouped by market_name
  const byMarketName = new Map<string, SoccerRawOtherRow[]>();
  for (const row of opts.otherMarkets ?? []) {
    const mname = (row.market_name ?? "").trim();
    if (!mname || isDisqualifiedThreeWayMarketName(mname)) continue;
    const list = byMarketName.get(mname) ?? [];
    list.push(row);
    byMarketName.set(mname, list);
  }

  for (const [title, rows] of byMarketName) {
    if (rows.length !== 3) continue;
    const legsByRole = new Map<SoccerThreeWayRole, SoccerThreeWayLeg>();
    for (const row of rows) {
      const outLabel = (row.outcome_name ?? "").trim();
      const role = classifyThreeWayRole(
        outLabel,
        opts.homeTeam,
        opts.awayTeam,
        opts.homeShort,
        opts.awayShort,
      );
      if (!role || legsByRole.has(role)) break;
      const observedAt = row.observed_at ?? null;
      const quotedChance =
        !finished && isRecentQuote(observedAt, opts.nowMs) ? openChance(row.probability) : null;
      const pregameChance = openChance(
        row.pregame_mark ?? row.opening_probability ?? (phase === "before" ? row.probability : null),
      );
      const result: "won" | "lost" | null =
        finished && typeof row.is_winner === "boolean"
          ? row.is_winner
            ? "won"
            : "lost"
          : null;
      legsByRole.set(role, {
        role,
        label: role === "home" ? opts.homeShort : role === "away" ? opts.awayShort : "Draw",
        rawOutcomeLabel: outLabel,
        quotedChance,
        pregameChance,
        observedAt,
        pregameObservedAt: null,
        result,
        source: row.source ?? null,
      });
    }

    if (legsByRole.size === 3) {
      const allLegs = Array.from(legsByRole.values());
      const pricedCount = allLegs.filter(
        (l) => l.quotedChance !== null || l.pregameChance !== null,
      ).length;
      const settledCount = allLegs.filter((l) => l.result !== null).length;
      const score = pricedCount * 10 + settledCount * 5;
      candidates.push({
        marketTitle: title,
        source: allLegs.find((l) => l.source)?.source ?? null,
        legsByRole,
        score,
      });
    }
  }

  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  const best = candidates[0];

  const homeLeg = best.legsByRole.get("home")!;
  const drawLeg = best.legsByRole.get("draw")!;
  const awayLeg = best.legsByRole.get("away")!;
  const legs: [SoccerThreeWayLeg, SoccerThreeWayLeg, SoccerThreeWayLeg] = [
    homeLeg,
    drawLeg,
    awayLeg,
  ];

  // Refuse if no leg has either a valid probability (before/during) or a settled result (after)
  const hasAnySignal = finished
    ? legs.some((l) => l.result !== null || l.pregameChance !== null)
    : legs.every((l) => (l.quotedChance ?? l.pregameChance) !== null);
  if (!hasAnySignal) return null;

  const activeQuotes = legs.map((l) => l.quotedChance ?? l.pregameChance);
  const quotedSum = activeQuotes.every((v): v is number => typeof v === "number")
    ? activeQuotes.reduce((acc, v) => acc + v, 0)
    : null;

  return {
    kind: "soccer-three-way",
    id: "soccer:threeWay",
    phase,
    legs,
    marketTitle: best.marketTitle,
    source: best.source,
    quotedSum,
  };
}

// ─── 2. Exact-score landscape ("The exact-score landscape") ────────────────

export interface SoccerExactScoreCell {
  key: string;
  homeGoals: number;
  awayGoals: number;
  outcomeLabel: string;
  chance: number | null;
  pregameChance: number | null;
  observedAt: string | null;
  result: "won" | "lost" | null;
  source: string | null;
  marketTitle: string;
}

export interface SoccerExactScoreCard {
  kind: "soccer-exact-score";
  id: "soccer:exactScore";
  phase: LadderPhase;
  homeTeam: string;
  awayTeam: string;
  homeShort: string;
  awayShort: string;
  maxGoals: number;
  maxChance: number;
  cells: SoccerExactScoreCell[];
  otherCell: {
    outcomeLabel: string;
    chance: number | null;
    pregameChance: number | null;
    observedAt: string | null;
    result: "won" | "lost" | null;
    source: string | null;
    marketTitle: string;
  } | null;
  defaultSelectedKey: string;
  marketTitle: string;
  source: string | null;
}

export function parseSoccerExactScoreOutcome(
  outcomeLabel: string,
  homeTeam: string,
  awayTeam: string,
  homeShort: string,
  awayShort: string,
): { homeGoals: number; awayGoals: number } | "other" | null {
  const trimmed = outcomeLabel.trim();
  if (!trimmed) return null;
  if (/^(?:any\s+other(?:\s+score)?|other)$/i.test(trimmed)) return "other";

  // 1. "Draw 0-0" or "Tie 1 - 1"
  const drawMatch = trimmed.match(/^(?:draw|tie)\s+(\d+)\s*[-–:]\s*(\d+)$/i);
  if (drawMatch) {
    const a = Number(drawMatch[1]);
    const b = Number(drawMatch[2]);
    if (Number.isInteger(a) && Number.isInteger(b) && a === b) {
      return { homeGoals: a, awayGoals: b };
    }
  }

  // 2. "<Team> wins 3-2"
  const winsMatch = trimmed.match(/^(.+?)\s+wins\s+(\d+)\s*[-–:]\s*(\d+)$/i);
  if (winsMatch) {
    const teamPart = winsMatch[1].trim();
    const g1 = Number(winsMatch[2]);
    const g2 = Number(winsMatch[3]);
    if (soccerNameMatchesSide(teamPart, homeTeam, homeShort)) {
      return { homeGoals: g1, awayGoals: g2 };
    }
    if (soccerNameMatchesSide(teamPart, awayTeam, awayShort)) {
      return { homeGoals: g2, awayGoals: g1 };
    }
  }

  // 3. "<TeamA> 3 - 2 <TeamB>"
  const teamPairMatch = trimmed.match(/^(.+?)\s+(\d+)\s*[-–:]\s*(\d+)\s+(.+)$/);
  if (teamPairMatch) {
    const leftTeam = teamPairMatch[1].trim();
    const gLeft = Number(teamPairMatch[2]);
    const gRight = Number(teamPairMatch[3]);
    const rightTeam = teamPairMatch[4].trim();

    const leftIsHome = soccerNameMatchesSide(leftTeam, homeTeam, homeShort);
    const rightIsAway = soccerNameMatchesSide(rightTeam, awayTeam, awayShort);
    if (leftIsHome && rightIsAway) {
      return { homeGoals: gLeft, awayGoals: gRight };
    }

    const leftIsAway = soccerNameMatchesSide(leftTeam, awayTeam, awayShort);
    const rightIsHome = soccerNameMatchesSide(rightTeam, homeTeam, homeShort);
    if (leftIsAway && rightIsHome) {
      return { homeGoals: gRight, awayGoals: gLeft };
    }
  }

  // 4. Bare "1 - 1" / "2-0"
  const bareMatch = trimmed.match(/^(\d+)\s*[-–:]\s*(\d+)$/);
  if (bareMatch) {
    return { homeGoals: Number(bareMatch[1]), awayGoals: Number(bareMatch[2]) };
  }

  return null;
}

function isExactScoreMarketTitle(title: string): boolean {
  const lower = title.toLowerCase();
  if (/\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|halftime)\b/.test(lower)) {
    return false;
  }
  return /\b(?:exact\s+score|correct\s+score)\b/.test(lower);
}

export function buildSoccerExactScoreCard(opts: {
  gameQuestionMatrix?: unknown;
  otherMarkets?: SoccerRawOtherRow[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  homeShort: string;
  awayShort: string;
  nowMs: number;
}): SoccerExactScoreCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const finished = phase === "after";

  type CandidateGrid = {
    marketTitle: string;
    source: string | null;
    cellsByKey: Map<string, SoccerExactScoreCell>;
    otherCell: SoccerExactScoreCard["otherCell"];
    score: number;
  };

  const candidates: CandidateGrid[] = [];

  // 1. Check game_question_matrix questions
  const questions = decodeQuestionMatrix(opts.gameQuestionMatrix);
  for (const q of questions) {
    const title = (q.marketName || q.label || "").trim();
    if (!isExactScoreMarketTitle(title)) continue;
    const cellsByKey = new Map<string, SoccerExactScoreCell>();
    let otherCell: SoccerExactScoreCard["otherCell"] = null;

    for (const o of q.options) {
      const parsed = parseSoccerExactScoreOutcome(
        o.label,
        opts.homeTeam,
        opts.awayTeam,
        opts.homeShort,
        opts.awayShort,
      );
      if (!parsed) continue;
      const quoted =
        !finished && isRecentQuote(o.observedAt, opts.nowMs) ? openChance(o.quoted) : null;
      const pregame = openChance(o.reading ?? o.baseline);
      const chance = finished ? pregame : (quoted ?? pregame);
      const result: "won" | "lost" | null =
        finished && typeof o.result === "boolean" ? (o.result ? "won" : "lost") : null;

      if (parsed === "other") {
        otherCell = {
          outcomeLabel: o.label,
          chance,
          pregameChance: pregame,
          observedAt: o.observedAt ?? o.readingObservedAt ?? o.baselineObservedAt ?? null,
          result,
          source: o.source,
          marketTitle: title,
        };
        continue;
      }

      if (parsed.homeGoals > 6 || parsed.awayGoals > 6) continue;
      const key = `${parsed.homeGoals}-${parsed.awayGoals}`;
      if (cellsByKey.has(key)) continue;
      cellsByKey.set(key, {
        key,
        homeGoals: parsed.homeGoals,
        awayGoals: parsed.awayGoals,
        outcomeLabel: o.label,
        chance,
        pregameChance: pregame,
        observedAt: o.observedAt ?? o.readingObservedAt ?? o.baselineObservedAt ?? null,
        result,
        source: o.source,
        marketTitle: title,
      });
    }

    if (cellsByKey.size >= 4) {
      const cells = Array.from(cellsByKey.values());
      const pricedCount = cells.filter((c) => c.chance !== null).length;
      const wonCount = cells.filter((c) => c.result === "won").length;
      candidates.push({
        marketTitle: title,
        source: cells.find((c) => c.source)?.source ?? null,
        cellsByKey,
        otherCell,
        score: pricedCount * 10 + wonCount * 20 + cells.length,
      });
    }
  }

  // 2. Also check gameMarkets.other grouped by market_name
  const byMarketName = new Map<string, SoccerRawOtherRow[]>();
  for (const row of opts.otherMarkets ?? []) {
    const mname = (row.market_name ?? "").trim();
    if (!isExactScoreMarketTitle(mname)) continue;
    const list = byMarketName.get(mname) ?? [];
    list.push(row);
    byMarketName.set(mname, list);
  }

  for (const [title, rows] of byMarketName) {
    const cellsByKey = new Map<string, SoccerExactScoreCell>();
    let otherCell: SoccerExactScoreCard["otherCell"] = null;

    for (const row of rows) {
      const outLabel = (row.outcome_name ?? "").trim();
      const parsed = parseSoccerExactScoreOutcome(
        outLabel,
        opts.homeTeam,
        opts.awayTeam,
        opts.homeShort,
        opts.awayShort,
      );
      if (!parsed) continue;
      const observedAt = row.observed_at ?? null;
      const quoted =
        !finished && isRecentQuote(observedAt, opts.nowMs) ? openChance(row.probability) : null;
      const pregame = openChance(
        row.pregame_mark ?? row.opening_probability ?? (phase === "before" ? row.probability : null),
      );
      const chance = finished ? pregame : (quoted ?? pregame);
      const result: "won" | "lost" | null =
        finished && typeof row.is_winner === "boolean"
          ? row.is_winner
            ? "won"
            : "lost"
          : null;

      if (parsed === "other") {
        otherCell = {
          outcomeLabel: outLabel,
          chance,
          pregameChance: pregame,
          observedAt,
          result,
          source: row.source ?? null,
          marketTitle: title,
        };
        continue;
      }

      if (parsed.homeGoals > 6 || parsed.awayGoals > 6) continue;
      const key = `${parsed.homeGoals}-${parsed.awayGoals}`;
      if (cellsByKey.has(key)) continue;
      cellsByKey.set(key, {
        key,
        homeGoals: parsed.homeGoals,
        awayGoals: parsed.awayGoals,
        outcomeLabel: outLabel,
        chance,
        pregameChance: pregame,
        observedAt,
        result,
        source: row.source ?? null,
        marketTitle: title,
      });
    }

    if (cellsByKey.size >= 4) {
      const cells = Array.from(cellsByKey.values());
      const pricedCount = cells.filter((c) => c.chance !== null).length;
      const wonCount = cells.filter((c) => c.result === "won").length;
      candidates.push({
        marketTitle: title,
        source: cells.find((c) => c.source)?.source ?? null,
        cellsByKey,
        otherCell,
        score: pricedCount * 10 + wonCount * 20 + cells.length,
      });
    }
  }

  if (candidates.length === 0) return null;
  candidates.sort((a, b) => b.score - a.score);
  const best = candidates[0];
  const cells = Array.from(best.cellsByKey.values()).sort(
    (a, b) => a.awayGoals - b.awayGoals || a.homeGoals - b.homeGoals,
  );

  const hasSignal = cells.some((c) => c.chance !== null || c.result !== null);
  if (!hasSignal) return null;

  const maxCoord = cells.reduce(
    (max, c) => Math.max(max, c.homeGoals, c.awayGoals),
    3,
  );
  const maxGoals = Math.min(5, Math.max(3, maxCoord));
  const maxChance = cells.reduce((max, c) => Math.max(max, c.chance ?? 0), 0.05);

  const winnerCell = finished ? cells.find((c) => c.result === "won") : undefined;
  const highestPricedCell = [...cells]
    .filter((c) => c.chance !== null)
    .sort((a, b) => (b.chance ?? 0) - (a.chance ?? 0))[0];
  const defaultSelectedKey =
    winnerCell?.key ?? highestPricedCell?.key ?? cells[0].key;

  return {
    kind: "soccer-exact-score",
    id: "soccer:exactScore",
    phase,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    maxGoals,
    maxChance,
    cells,
    otherCell: best.otherCell,
    defaultSelectedKey,
    marketTitle: best.marketTitle,
    source: best.source,
  };
}

// ─── 3. Goal expectations ladder (`unit: "goals"`) ─────────────────────────

function pointChanceForSoccer(
  o: MatrixOption,
  phase: LadderPhase,
  nowMs: number,
): { chance: number | null; observedAt: string | null; now: number | null } {
  if (phase === "before") {
    const recent = o.quoted !== null && isRecentQuote(o.observedAt, nowMs);
    return { chance: recent ? o.quoted : o.reading, observedAt: o.observedAt, now: null };
  }
  if (phase === "after") {
    return { chance: o.reading ?? o.baseline, observedAt: null, now: null };
  }
  const now = o.quoted !== null && isRecentQuote(o.observedAt, nowMs) ? o.quoted : null;
  return { chance: o.baseline ?? o.reading, observedAt: null, now };
}

function parseSoccerGoalThresholdFromLabel(label: string): number | null {
  const trimmed = label.trim();
  // Avoid team-total questions like "Arsenal FC vs. Hull City AFC: Arsenal FC O/U 3.5"
  if (/:\s+.+\bO\/U\s+\d+(?:\.\d+)?$/i.test(trimmed)) return null;

  // "1+ goal" / "2+ goals" → threshold 0.5 / 1.5 (so Math.floor(line) + 1 === N+)
  const plusMatch = trimmed.match(/^(\d+)\+\s+goals?$/i);
  if (plusMatch) {
    const count = Number(plusMatch[1]);
    if (Number.isInteger(count) && count >= 1) return count - 0.5;
  }

  // "...: O/U 2.5" or "Over 2.5 goals"
  const ouMatch = trimmed.match(/\bO\/U\s+(\d+(?:\.\d+)?)$/i);
  if (ouMatch) {
    const line = Number(ouMatch[1]);
    if (Number.isFinite(line) && line >= 0.5) return line;
  }

  return null;
}

export function buildSoccerGoalTotalCard(opts: {
  gameQuestionMatrix?: unknown;
  totalsMarkets?: SoccerRawTotalRow[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  homeShort: string;
  awayShort: string;
  nowMs: number;
}): LadderCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const settled = phase === "after";
  const questions = decodeQuestionMatrix(opts.gameQuestionMatrix);
  const points: LadderPoint[] = [];

  for (const q of questions) {
    if (q.periodKey && q.periodKey !== "full_game") continue;
    if (q.subjectSide === "home" || q.subjectSide === "away") continue;

    const line =
      q.typed && q.quantityKey === "goals" && q.line !== null
        ? q.line
        : parseSoccerGoalThresholdFromLabel(q.label || q.marketName);
    if (line === null || !Number.isFinite(line)) continue;

    const overOpt =
      q.options.find((o) => o.side === "over") ??
      q.options.find((o) => /^over\b/i.test(o.label));
    if (!overOpt) continue;

    points.push({
      optionKey: overOpt.optionKey,
      x: line,
      label: `Over ${line} goals`,
      side: "game",
      ...pointChanceForSoccer(overOpt, phase, opts.nowMs),
      result: settled ? overOpt.result : null,
      detail: {
        detail: "option",
        label: overOpt.label || `Over ${line} goals`,
        marketName: q.marketName || q.label,
        source: overOpt.source,
        quoted: overOpt.quoted,
        observedAt: overOpt.observedAt,
        baseline: settled ? (overOpt.reading ?? overOpt.baseline) : overOpt.baseline,
        baselineObservedAt: settled
          ? (overOpt.readingObservedAt ?? overOpt.baselineObservedAt)
          : overOpt.baselineObservedAt,
        result: overOpt.result,
      },
    });
  }

  // Fallback to gameMarkets.totals when GQM has < 3 lines
  if (points.length < MIN_LADDER_LINES && opts.totalsMarkets) {
    for (const row of opts.totalsMarkets) {
      if (row.period && row.period !== "full_game") continue;
      if (row.market_type && row.market_type !== "game_total") continue;
      if (typeof row.threshold !== "number" || !Number.isFinite(row.threshold)) continue;
      if (row.outcome_name && /^under\b/i.test(row.outcome_name)) continue;

      const line = row.threshold;
      const observedAt = row.observed_at ?? null;
      const freshQuote =
        !settled && isRecentQuote(observedAt, opts.nowMs)
          ? openChance(row.over_probability)
          : null;
      const pregame = openChance(
        row.pregame_mark ??
          row.opening_probability ??
          (phase === "before" ? row.over_probability : null),
      );
      const result: boolean | null =
        settled && typeof row.is_winner === "boolean" ? row.is_winner : null;

      points.push({
        optionKey: `total:${row._market_id ?? line}`,
        x: line,
        label: `Over ${line} goals`,
        side: "game",
        chance: phase === "before" ? (freshQuote ?? pregame) : pregame,
        observedAt: phase === "before" ? observedAt : null,
        now: phase === "during" ? freshQuote : null,
        result,
        detail: {
          detail: "option",
          label: `Over ${line} goals`,
          marketName: row.market_name || `Over ${line} goals`,
          source: row.source ?? null,
          quoted: openChance(row.over_probability),
          observedAt,
          baseline: pregame,
          baselineObservedAt: null,
          result,
        },
      });
    }
  }

  const byLine = new Map<number, LadderPoint>();
  for (const p of points) {
    const prev = byLine.get(p.x);
    if (!prev || (p.chance !== null && prev.chance === null)) {
      byLine.set(p.x, p);
    }
  }
  const kept = Array.from(byLine.values()).sort((a, b) => a.x - b.x);
  if (kept.length < MIN_LADDER_LINES) return null;

  const actual =
    phase !== "before" && typeof opts.homeScore === "number" && typeof opts.awayScore === "number"
      ? opts.homeScore + opts.awayScore
      : null;

  return {
    kind: "ladder",
    id: "total",
    family: "total",
    unit: "goals",
    phase,
    points: kept,
    actual,
    forecast: null,
    awayShort: opts.awayShort,
    homeShort: opts.homeShort,
  };
}

// ─── Deck builder ──────────────────────────────────────────────────────────

export function buildSoccerEventCards(opts: {
  sportKey: string | null | undefined;
  atlasMode?: boolean;
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  homeShort: string;
  awayShort: string;
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  gameMarkets?: {
    game_question_matrix?: unknown;
    other?: SoccerRawOtherRow[];
    totals?: SoccerRawTotalRow[];
  } | null;
  nowMs?: number;
}): NflEventCard[] {
  if (!soccerCardsApply(opts.sportKey, opts.atlasMode)) return [];
  if (!opts.gameMarkets) return [];
  const nowMs = opts.nowMs ?? Date.now();
  const cards: NflEventCard[] = [];

  const threeWayCard = buildSoccerThreeWayCard({
    gameQuestionMatrix: opts.gameMarkets.game_question_matrix,
    otherMarkets: opts.gameMarkets.other,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    homeScore: opts.homeScore,
    awayScore: opts.awayScore,
    nowMs,
  });
  if (threeWayCard) cards.push(threeWayCard);

  const exactScoreCard = buildSoccerExactScoreCard({
    gameQuestionMatrix: opts.gameMarkets.game_question_matrix,
    otherMarkets: opts.gameMarkets.other,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    nowMs,
  });
  if (exactScoreCard) cards.push(exactScoreCard);

  const totalCard = buildSoccerGoalTotalCard({
    gameQuestionMatrix: opts.gameMarkets.game_question_matrix,
    totalsMarkets: opts.gameMarkets.totals,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeScore: opts.homeScore,
    awayScore: opts.awayScore,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    nowMs,
  });
  if (totalCard) cards.push(totalCard);

  return cards;
}
