/**
 * #11974 Step E6b — NHL game-story cards on web (`icehockey_nhl`), behind `?atlas=1`.
 *
 * Mirrors the event-page atlas hockey specification (`docs/designs/event-page-atlas-2026-10/src/HockeyStories.tsx`,
 * `HockeyScoringCard.tsx`, `HockeyGoalsCard.tsx`):
 *   1. Goalscorers (`nhl-scoring`): "Who found the net?" (finished with scorers)
 *      or "Likely goalscorers" (before/during play), plotting each player's
 *      saved pregame 1+ goal chance on a shared probability rail alongside
 *      actual goals scored and settlement mark (`✓ Won` / `✗ Lost`).
 *   2. Goal expectations (`ladder`, `family: "total"`, `unit: "goals"`): full-game
 *      goal total lines from `game_question_matrix` (`10238.v1`, `quantity.key === "goals"`).
 *   3. Puck-line margin (`ladder`, `family: "margin"`, `unit: "goals"`): full-game
 *      signed goal handicap lines from `game_question_matrix` (`10238.v1`).
 *   4. Player points / assists milestones (`milestone`): skater points/assists
 *      milestone ladder when ≥ 3 priced thresholds exist.
 */

import { isFinishedStatus } from "./eventState";
import {
  decodeQuestionMatrix,
  MIN_LADDER_LINES,
  type LadderCard,
  type LadderPhase,
  type LadderPoint,
  type MatrixOption,
} from "./nbaEventCards";
import {
  isRecentQuote,
  isTeamSubject,
  milestoneProfile,
  propRowId,
  type MilestoneBasis,
  type MilestoneCard,
  type MilestoneRung,
  type NflPropRow,
  type PropSide,
} from "./nflEventCardDeck";
import { parseMlbPropShape } from "./mlbEventCards";
import { propOutcomeSide } from "./propOutcomeSide";

export const NHL_SPORT_KEY = "icehockey_nhl";
export const MAX_NHL_SCORERS = 4;

export function nhlCardsApply(sportKey: string | null | undefined, atlasMode = false): boolean {
  return atlasMode && sportKey === NHL_SPORT_KEY;
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

function phaseOf(status: string | null | undefined, commenceTime: string | null | undefined, nowMs: number): LadderPhase {
  if (isFinishedStatus(status)) return "after";
  const c = parseMs(commenceTime);
  if (status === "live" || c === null || c <= nowMs) return "during";
  return "before";
}

// ─── 1. Goalscorers card ("Who found the net?") ────────────────────────────

export interface NhlScorerEntry {
  id: string;
  rowId: string;
  player: string;
  pregameChance: number | null;
  observedAt: string | null;
  actualGoals: number | null;
  hit: boolean | null;
  side: PropSide;
  sourceCount: number;
  marketTitle: string;
}

export interface NhlScoringCard {
  kind: "nhl-scoring";
  id: "nhl:scoring";
  story: "scored" | "likeliest";
  phase: LadderPhase;
  entries: NhlScorerEntry[];
  scaleCeiling: number;
}

export function nhlScoringHeadline(card: NhlScoringCard): string {
  return card.story === "scored" ? "Who found the net?" : "Likely goalscorers";
}

export function nhlScoringReason(card: NhlScoringCard): string {
  if (card.story === "scored") {
    return "Players who scored, alongside their pregame 1+ goal chance";
  }
  return "Highest pregame chances of scoring 1+ goals";
}

export function computeNhlScoringScaleCeiling(entries: Pick<NhlScorerEntry, "pregameChance">[]): number {
  const top = entries.reduce((max, e) => Math.max(max, e.pregameChance ?? 0), 0);
  return Math.min(1, Math.max(0.35, Math.ceil(top * 20) / 20));
}

export function buildNhlScoringCard(opts: {
  playerProps?: NflPropRow[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  nowMs: number;
}): NhlScoringCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const finished = phase === "after";
  const props = opts.playerProps ?? [];
  const groupsByPlayer = new Map<
    string,
    {
      rowId: string;
      player: string;
      chances: number[];
      sources: Set<string>;
      latestObservedAt: string | null;
      latestObservedMs: number;
      actualGoals: number | null;
      hit: boolean | null;
      side: PropSide;
    }
  >();

  for (const row of props) {
    if (row._inverted) continue;
    const shape = parseMlbPropShape(row);
    if (!shape || !/^goals$/i.test(shape.stat.trim())) continue;
    if (isTeamSubject(shape.player, [opts.homeTeam, opts.awayTeam])) continue;
    if (row.threshold !== 1 && row.threshold !== 0.5) continue;
    const side = propOutcomeSide(row.outcome_name);
    if (side === "under" || (side === "unreadable" && /\bunder\b/i.test(row.outcome_name))) continue;

    const rawChance =
      phase === "before"
        ? isRecentQuote(row.observed_at, opts.nowMs)
          ? row.over_probability
          : null
        : (row.pregame_mark ?? null);
    const pregameChance = openChance(rawChance);
    const actualGoals =
      finished && typeof row.actual === "number" && Number.isFinite(row.actual) && row.actual >= 0
        ? Math.round(row.actual)
        : null;
    const hit = finished && typeof row.hit === "boolean" ? row.hit : null;

    if (pregameChance === null && (actualGoals === null || actualGoals === 0)) continue;

    const rId = propRowId(row);
    const group = groupsByPlayer.get(shape.player) ?? {
      rowId: rId,
      player: shape.player,
      chances: [],
      sources: new Set<string>(),
      latestObservedAt: null,
      latestObservedMs: -Infinity,
      actualGoals: null,
      hit: null,
      side: "unknown",
    };
    if (pregameChance !== null) group.chances.push(pregameChance);
    if (row.source) group.sources.add(row.source);
    const obsMs = parseMs(row.observed_at);
    if (obsMs !== null && obsMs > group.latestObservedMs) {
      group.latestObservedMs = obsMs;
      group.latestObservedAt = row.observed_at ?? null;
    } else if (group.latestObservedAt === null && row.observed_at) {
      group.latestObservedAt = row.observed_at;
    }
    if (actualGoals !== null) group.actualGoals = actualGoals;
    if (hit !== null) group.hit = hit;
    if (group.side === "unknown" && (row.player_team === "home" || row.player_team === "away")) {
      group.side = row.player_team;
    }
    groupsByPlayer.set(shape.player, group);
  }

  const all: NhlScorerEntry[] = [...groupsByPlayer.values()].map((g) => ({
    id: `nhl-scorer:${g.rowId}`,
    rowId: g.rowId,
    player: g.player,
    pregameChance:
      g.chances.length > 0 ? g.chances.reduce((s, c) => s + c, 0) / g.chances.length : null,
    observedAt: g.latestObservedAt,
    actualGoals: g.actualGoals,
    hit: g.hit,
    side: g.side,
    sourceCount: Math.max(1, g.sources.size),
    marketTitle: `${g.player} · 1+ goals`,
  }));
  if (all.length === 0) return null;

  const scorers = all
    .filter((e) => (e.actualGoals ?? 0) >= 1)
    .sort((a, b) => {
      const ga = a.actualGoals ?? 0;
      const gb = b.actualGoals ?? 0;
      if (gb !== ga) return gb - ga;
      const pa = a.pregameChance ?? 1;
      const pb = b.pregameChance ?? 1;
      if (pa !== pb) return pa - pb;
      return a.player.localeCompare(b.player);
    });

  if (finished && scorers.length > 0) {
    const chosen = scorers.slice(0, MAX_NHL_SCORERS);
    return {
      kind: "nhl-scoring",
      id: "nhl:scoring",
      story: "scored",
      phase,
      entries: chosen,
      scaleCeiling: computeNhlScoringScaleCeiling(chosen),
    };
  }

  const likeliest = all
    .filter((e) => e.pregameChance !== null)
    .sort((a, b) => {
      const diff = (b.pregameChance ?? 0) - (a.pregameChance ?? 0);
      return diff !== 0 ? diff : a.player.localeCompare(b.player);
    })
    .slice(0, MAX_NHL_SCORERS);

  if (likeliest.length === 0) return null;
  return {
    kind: "nhl-scoring",
    id: "nhl:scoring",
    story: "likeliest",
    phase,
    entries: likeliest,
    scaleCeiling: computeNhlScoringScaleCeiling(likeliest),
  };
}

// ─── 2 & 3. Goal totals & Puck-line margin ladders ─────────────────────────

function pointChanceForNhl(
  o: MatrixOption,
  phase: LadderPhase,
  nowMs: number,
): { chance: number | null; observedAt: string | null; now: number | null } {
  if (phase === "before") {
    const recent = o.quoted !== null && isRecentQuote(o.observedAt, nowMs);
    return { chance: recent ? o.quoted : null, observedAt: o.observedAt, now: null };
  }
  if (phase === "after") {
    return { chance: o.reading ?? o.baseline, observedAt: null, now: null };
  }
  const now = o.quoted !== null && isRecentQuote(o.observedAt, nowMs) ? o.quoted : null;
  return { chance: o.baseline, observedAt: null, now };
}

export function buildNhlGoalTotalsCard(opts: {
  gameQuestionMatrix?: unknown;
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  homeShort: string;
  awayShort: string;
  nowMs: number;
}): LadderCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const questions = decodeQuestionMatrix(opts.gameQuestionMatrix);
  const points: LadderPoint[] = [];

  for (const q of questions) {
    if (!q.typed || q.kind !== "count_threshold" || q.quantityKey !== "goals" || q.subjectSide !== "game") continue;
    if (q.periodKey !== "full_game" || q.relation !== "ge") continue;
    const line = q.line ?? (q.bound !== null ? q.bound - 0.5 : null);
    if (line === null || !Number.isFinite(line)) continue;
    const own = q.options.filter((o) => o.side === "over");
    if (own.length !== 1) continue;
    const o = own[0];
    const settled = phase === "after";
    points.push({
      optionKey: o.optionKey,
      x: line,
      label: `Over ${line} goals`,
      side: "game",
      ...pointChanceForNhl(o, phase, opts.nowMs),
      result: settled ? o.result : null,
      detail: {
        detail: "option",
        label: o.label || `Over ${line} goals`,
        marketName: q.marketName || q.label,
        source: o.source,
        quoted: o.quoted,
        observedAt: o.observedAt,
        baseline: settled ? (o.reading ?? o.baseline) : o.baseline,
        baselineObservedAt: settled ? (o.readingObservedAt ?? o.baselineObservedAt) : o.baselineObservedAt,
        result: o.result,
      },
    });
  }

  const counts = new Map<number, number>();
  for (const p of points) counts.set(p.x, (counts.get(p.x) ?? 0) + 1);
  const kept = points.filter((p) => counts.get(p.x) === 1).sort((a, b) => a.x - b.x);
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

export function buildNhlPuckLineMarginCard(opts: {
  gameQuestionMatrix?: unknown;
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  homeShort: string;
  awayShort: string;
  nowMs: number;
}): LadderCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const questions = decodeQuestionMatrix(opts.gameQuestionMatrix);
  const points: LadderPoint[] = [];

  for (const q of questions) {
    if (!q.typed || q.kind !== "signed_handicap" || q.quantityKey !== "goals" || q.periodKey !== "full_game") continue;
    if (q.relation !== "handicap" || q.line === null || !(q.line < 0)) continue;
    const side = q.subjectSide;
    if (side !== "home" && side !== "away") continue;
    const own = q.options.filter((o) => o.side === side);
    if (own.length !== 1) continue;
    const o = own[0];
    const by = -q.line;
    const team = side === "home" ? opts.homeShort : opts.awayShort;
    const settled = phase === "after";
    points.push({
      optionKey: o.optionKey,
      x: side === "home" ? by : -by,
      label: `${team} by ${Math.floor(by) + 1}+`,
      side,
      ...pointChanceForNhl(o, phase, opts.nowMs),
      result: settled ? o.result : null,
      detail: {
        detail: "option",
        label: o.label || `${team} by ${Math.floor(by) + 1}+`,
        marketName: q.marketName || q.label,
        source: o.source,
        quoted: o.quoted,
        observedAt: o.observedAt,
        baseline: settled ? (o.reading ?? o.baseline) : o.baseline,
        baselineObservedAt: settled ? (o.readingObservedAt ?? o.baselineObservedAt) : o.baselineObservedAt,
        result: o.result,
      },
    });
  }

  const counts = new Map<number, number>();
  for (const p of points) counts.set(p.x, (counts.get(p.x) ?? 0) + 1);
  const kept = points.filter((p) => counts.get(p.x) === 1).sort((a, b) => a.x - b.x);
  if (kept.length < MIN_LADDER_LINES) return null;

  const actual =
    phase !== "before" && typeof opts.homeScore === "number" && typeof opts.awayScore === "number"
      ? opts.homeScore - opts.awayScore
      : null;

  return {
    kind: "ladder",
    id: "margin",
    family: "margin",
    unit: "goals",
    phase,
    points: kept,
    actual,
    forecast: null,
    awayShort: opts.awayShort,
    homeShort: opts.homeShort,
  };
}

// ─── 4. Skater points / assists milestone card ─────────────────────────────

export function buildNhlContributionMilestoneCard(opts: {
  playerProps?: NflPropRow[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  nowMs: number;
}): MilestoneCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const finished = phase === "after";
  const basis: MilestoneBasis = phase === "before" ? "pregamePrice" : "pregameMark";
  const props = opts.playerProps ?? [];

  const ladders = new Map<string, { player: string; stat: string; rows: NflPropRow[] }>();
  for (const row of props) {
    if (row._inverted) continue;
    const shape = parseMlbPropShape(row);
    if (!shape || !/^(?:points|assists)$/i.test(shape.stat.trim())) continue;
    if (isTeamSubject(shape.player, [opts.homeTeam, opts.awayTeam])) continue;
    const key = `${shape.player}|${shape.stat}|${row.source ?? ""}`;
    const entry = ladders.get(key) ?? { player: shape.player, stat: shape.stat, rows: [] };
    entry.rows.push(row);
    ladders.set(key, entry);
  }

  const candidates: { key: string; card: MilestoneCard; pricedCount: number }[] = [];
  for (const [key, ladder] of ladders) {
    const rungs: MilestoneRung[] = [];
    for (const row of ladder.rows) {
      if (typeof row.threshold !== "number" || !Number.isFinite(row.threshold)) continue;
      const side = propOutcomeSide(row.outcome_name);
      if (side === "under" || (side === "unreadable" && /\bunder\b/i.test(row.outcome_name))) continue;
      const observedAt = basis === "pregamePrice" ? (row.observed_at ?? null) : null;
      let chance = openChance(basis === "pregamePrice" ? row.over_probability : row.pregame_mark);
      if (basis === "pregamePrice" && !isRecentQuote(observedAt, opts.nowMs)) chance = null;
      rungs.push({
        threshold: row.threshold,
        chance,
        observedAt,
        rowId: propRowId(row),
        hit: finished ? (row.hit ?? null) : null,
      });
    }
    rungs.sort((a, b) => a.threshold - b.threshold);
    const servedSide = ladder.rows.find((r) => r.player_team)?.player_team;
    const actualRow = finished
      ? ladder.rows.find((r) => typeof r.actual === "number" && Number.isFinite(r.actual))
      : undefined;
    const card: MilestoneCard = {
      kind: "milestone",
      id: "nhl:contributions",
      player: ladder.player,
      stat: ladder.stat,
      side: servedSide === "home" || servedSide === "away" ? servedSide : "unknown",
      basis,
      rungs,
      actual: actualRow ? (actualRow.actual as number) : null,
    };
    if (!milestoneProfile(card)) continue;
    candidates.push({
      key,
      card,
      pricedCount: rungs.filter((r) => r.chance !== null).length,
    });
  }

  candidates.sort((a, b) => {
    if (a.pricedCount !== b.pricedCount) return b.pricedCount - a.pricedCount;
    return a.key.localeCompare(b.key);
  });

  return candidates[0]?.card ?? null;
}

// ─── Complete NHL deck in fixed slot order ─────────────────────────────────

export type NhlStoryCard = NhlScoringCard | LadderCard | MilestoneCard;

export function buildNhlEventCards(opts: {
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
    player_props?: NflPropRow[];
    game_question_matrix?: unknown;
  } | null;
  nowMs: number;
}): NhlStoryCard[] {
  if (!nhlCardsApply(opts.sportKey, opts.atlasMode)) return [];
  const gm = opts.gameMarkets;
  if (!gm) return [];

  const scoring = buildNhlScoringCard({
    playerProps: gm.player_props,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    nowMs: opts.nowMs,
  });
  const totals = buildNhlGoalTotalsCard({
    gameQuestionMatrix: gm.game_question_matrix,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeScore: opts.homeScore,
    awayScore: opts.awayScore,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    nowMs: opts.nowMs,
  });
  const margin = buildNhlPuckLineMarginCard({
    gameQuestionMatrix: gm.game_question_matrix,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeScore: opts.homeScore,
    awayScore: opts.awayScore,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    nowMs: opts.nowMs,
  });
  const contributions = buildNhlContributionMilestoneCard({
    playerProps: gm.player_props,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    nowMs: opts.nowMs,
  });

  return [scoring, totals, margin, contributions].filter((c): c is NhlStoryCard => c !== null);
}
