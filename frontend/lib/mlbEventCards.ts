/**
 * #11974 Step E6a — MLB game-story cards on web (`baseball_mlb`), behind `?atlas=1`.
 *
 * Mirrors the shipped native MLB reader (`MLBFinalReader11284.swift`,
 * `MLBFinalCards11284.swift`, design ref #10868 / `event-page-atlas-2026-10`):
 *   1. Home runs (`mlb-home-runs`): players' saved pregame chances of 1+ HR
 *      beside their official final counts on one shared probability scale.
 *   2. Strikeout milestones (`milestone`): pitcher strikeout ladder with
 *      saved pregame chance to reach each count and official final when typed.
 *   3. Run totals (`ladder`, `unit: "runs"`): full-game run lines from the
 *      served question matrix (`10238.v1`, `quantity.key === "runs"`), with
 *      each line's pregame chance, settled result, and actual total runs.
 *   4. Extra innings (`mlb-extra-innings`): the extra-innings market
 *      for this game when served in `other`.
 *   5. The series (`mlb-series`): separate associated series markets from
 *      `relatedFutures.series_question_matrix` (`10238.v1`, `display_scope === "series"`).
 *
 * Every number is one the existing payload already serves, named for what it is.
 */

import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import { isFinishedStatus } from "./eventState";
import { decodeQuestionMatrix, MIN_LADDER_LINES, type LadderCard, type LadderPhase, type LadderPoint, type MatrixOption } from "./nbaEventCards";
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
import { propSubjectDisplay } from "./playerPropsGrouping";
import { propOutcomeSide } from "./propOutcomeSide";

export const MLB_SPORT_KEY = "baseball_mlb";
export const AFTER_PROPS_CONTRACT = "10237.v1";
export const MAX_MLB_HOME_RUN_ENTRIES = 3;

export function mlbCardsApply(sportKey: string | null | undefined, atlasMode = false): boolean {
  return atlasMode && sportKey === MLB_SPORT_KEY;
}

export type MlbVenueResult = "won" | "lost" | "open" | "pending";

export function mlbVenueResultLabel(result: MlbVenueResult): string {
  switch (result) {
    case "won":
      return "Won";
    case "lost":
      return "Lost";
    case "open":
      return "Open";
    case "pending":
      return "Pending";
  }
}

/**
 * Resolves a row's settled/open status through the single settled-state rule
 * (`outcomeRowVerdict`, #4788) so ungraded or retracted rows never invent a result.
 */
export function resolveMlbRowVenueResult(
  isWinner: boolean | null | undefined,
  resolutionSource?: string | null | undefined,
  phase: LadderPhase = "after",
): MlbVenueResult {
  const verdict = outcomeRowVerdict(
    { is_winner: isWinner, resolution_source: resolutionSource },
    phase === "after",
  );
  if (verdict === "won") return "won";
  if (verdict === "lost") return "lost";
  return phase === "after" ? "pending" : "open";
}

export function resolveMlbProducerResult(state: string | null | undefined): MlbVenueResult {
  if (!state) return "pending";
  if (state === "won") return "won";
  if (state === "lost") return "lost";
  if (state === "open") return "open";
  return "pending";
}

function openChance(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value > 0 && value < 1 ? value : null;
}

// ─── 1. Home runs card ─────────────────────────────────────────────────────

export interface MlbHomeRunEntry {
  id: string;
  questionKey: string;
  player: string;
  saved: number;
  observedAt: string | null;
  finalCount: number | null;
  finalState: "final" | "pending" | "unknown";
  finalSourceLabel: string | null;
  side: PropSide;
  sourceCount: number;
  venueResult: MlbVenueResult;
  marketTitle: string;
}

export interface MlbHomeRunCard {
  kind: "mlb-home-runs";
  id: "mlb:homeRuns";
  story: "homered" | "likeliest";
  phase: LadderPhase;
  entries: MlbHomeRunEntry[];
  scaleCeiling: number;
}

export function mlbHomeRunHeadline(card: MlbHomeRunCard): string {
  return card.story === "homered"
    ? "Who homered, against their pregame chances"
    : "The likeliest home-run hitters";
}

export function mlbHomeRunReason(card: MlbHomeRunCard): string {
  if (card.story === "homered") {
    return "Lowest pregame chances among players with an official home run";
  }
  if (card.phase !== "after") {
    return "Highest pregame chances of hitting at least one home run";
  }
  return card.entries.some((e) => e.finalCount !== null)
    ? "Highest pregame chances of a home run"
    : "Highest pregame chances of a home run · official finals unavailable";
}

export function computeMlbHomeRunScaleCeiling(entries: Pick<MlbHomeRunEntry, "saved">[]): number {
  const top = entries.reduce((max, e) => Math.max(max, e.saved), 0);
  return Math.min(1, Math.max(0.25, Math.ceil(top * 20) / 20));
}

type RawObj = Record<string, unknown>;
const asObj = (v: unknown): RawObj | null =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as RawObj) : null;
const asStr = (v: unknown): string | null => (typeof v === "string" ? v : null);

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

export function buildMlbHomeRunCard(opts: {
  afterPlayerProps?: unknown;
  playerProps?: (NflPropRow & {
    contributor_outcome_ids?: number[];
    is_winner?: boolean | null;
    resolution_source?: string | null;
  })[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  nowMs: number;
}): MlbHomeRunCard | null {
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const props = opts.playerProps ?? [];
  const after = asObj(opts.afterPlayerProps);

  if (after && after.contract === AFTER_PROPS_CONTRACT && Array.isArray(after.questions)) {
    const actualsByKey = new Map<string, RawObj>();
    if (Array.isArray(after.actuals)) {
      for (const rawActual of after.actuals) {
        const a = asObj(rawActual);
        const key = asStr(a?.actual_key);
        if (a && key) actualsByKey.set(key, a);
      }
    }

    const entries: MlbHomeRunEntry[] = [];
    for (const rq of after.questions) {
      const q = asObj(rq);
      if (!q || q.stat_key !== "home_runs" || q.period_key !== "full_game") continue;
      const subject = asObj(q.subject);
      const predicate = asObj(q.predicate);
      const expectation = asObj(q.expectation);
      if (
        !subject ||
        subject.kind === "team" ||
        !predicate ||
        predicate.kind !== "count_at_least" ||
        predicate.count !== 1 ||
        predicate.side !== "over" ||
        !expectation ||
        expectation.state !== "available"
      ) {
        continue;
      }
      const saved = openChance(expectation.probability);
      const questionKey = asStr(q.question_key);
      const player = asStr(subject.label);
      if (saved === null || !questionKey || !player) continue;

      const actualKey = asStr(q.actual_key);
      const actualObj = actualKey ? actualsByKey.get(actualKey) : undefined;
      const actualStateRaw = asStr(actualObj?.state);
      const finalState: "final" | "pending" | "unknown" =
        actualStateRaw === "final" ? "final" : actualStateRaw === "pending" ? "pending" : "unknown";
      const finalCount =
        finalState === "final" && typeof actualObj?.value === "number" && Number.isFinite(actualObj.value)
          ? actualObj.value
          : null;
      const finalSourceLabel = asStr(actualObj?.source_label);

      const contributorIds = Array.isArray(q.contributor_outcome_ids)
        ? q.contributor_outcome_ids.filter((id): id is number => typeof id === "number")
        : [];
      const matchedProp =
        contributorIds.length > 0
          ? props.find((p) =>
              (p.contributor_outcome_ids ?? []).some((id) => contributorIds.includes(id)),
            )
          : props.find((p) => p.outcome_name.toLowerCase().startsWith(player.toLowerCase()));
      const side: PropSide =
        matchedProp?.player_team === "home" || matchedProp?.player_team === "away"
          ? matchedProp.player_team
          : "unknown";

      const contributors = Array.isArray(expectation.contributors) ? expectation.contributors : [];
      const sourceCount = Math.max(1, contributors.length);
      const venueGrade = asObj(q.venue_grade);
      const venueResult: MlbVenueResult =
        finalCount !== null
          ? finalCount >= 1
            ? "won"
            : "lost"
          : resolveMlbRowVenueResult(
              typeof venueGrade?.is_winner === "boolean" ? venueGrade.is_winner : null,
              asStr(venueGrade?.resolution_source),
              phase,
            );

      entries.push({
        id: `mlb-hr:${questionKey}`,
        questionKey,
        player,
        saved,
        observedAt: asStr(expectation.observed_at),
        finalCount,
        finalState,
        finalSourceLabel,
        side,
        sourceCount,
        venueResult,
        marketTitle: `${player} · 1+ home runs`,
      });
    }

    if (entries.length > 0) {
      const homered = entries
        .filter((e) => (e.finalCount ?? 0) >= 1)
        .sort((a, b) => (a.saved !== b.saved ? a.saved - b.saved : a.questionKey.localeCompare(b.questionKey)));
      if (homered.length > 0) {
        const chosen = homered.slice(0, MAX_MLB_HOME_RUN_ENTRIES);
        return {
          kind: "mlb-home-runs",
          id: "mlb:homeRuns",
          story: "homered",
          phase,
          entries: chosen,
          scaleCeiling: computeMlbHomeRunScaleCeiling(chosen),
        };
      }
      const likeliest = [...entries]
        .sort((a, b) => (a.saved !== b.saved ? b.saved - a.saved : a.questionKey.localeCompare(b.questionKey)))
        .slice(0, MAX_MLB_HOME_RUN_ENTRIES);
      return {
        kind: "mlb-home-runs",
        id: "mlb:homeRuns",
        story: "likeliest",
        phase,
        entries: likeliest,
        scaleCeiling: computeMlbHomeRunScaleCeiling(likeliest),
      };
    }
  }

  // Fallback for pregame / live MLB games before `after_player_props` is built
  const seenPlayers = new Set<string>();
  const fallbackEntries: MlbHomeRunEntry[] = [];
  for (const row of props) {
    if (row._inverted) continue;
    const shape = parseMlbPropShape(row);
    if (!shape || !/home\s*runs?/i.test(shape.stat)) continue;
    if (isTeamSubject(shape.player, [opts.homeTeam, opts.awayTeam])) continue;
    const threshold = row.threshold;
    if (threshold !== 0.5 && threshold !== 1) continue;
    const side = propOutcomeSide(row.outcome_name);
    if (side === "under" || (side === "unreadable" && /\bunder\b/i.test(row.outcome_name))) continue;
    const rawChance =
      phase === "before"
        ? isRecentQuote(row.observed_at, opts.nowMs)
          ? row.over_probability
          : null
        : (row.pregame_mark ?? null);
    const saved = openChance(rawChance);
    if (saved === null || seenPlayers.has(shape.player)) continue;
    seenPlayers.add(shape.player);
    const qKey = propRowId(row);
    fallbackEntries.push({
      id: `mlb-hr:${qKey}`,
      questionKey: qKey,
      player: shape.player,
      saved,
      observedAt: row.observed_at ?? null,
      finalCount: null,
      finalState: "pending",
      finalSourceLabel: null,
      side: row.player_team === "home" || row.player_team === "away" ? row.player_team : "unknown",
      sourceCount: 1,
      venueResult: resolveMlbRowVenueResult(row.is_winner, row.resolution_source, phase),
      marketTitle: `${shape.player} · 1+ home runs`,
    });
  }

  if (fallbackEntries.length === 0) return null;
  const chosen = fallbackEntries
    .sort((a, b) => (a.saved !== b.saved ? b.saved - a.saved : a.questionKey.localeCompare(b.questionKey)))
    .slice(0, MAX_MLB_HOME_RUN_ENTRIES);
  return {
    kind: "mlb-home-runs",
    id: "mlb:homeRuns",
    story: "likeliest",
    phase,
    entries: chosen,
    scaleCeiling: computeMlbHomeRunScaleCeiling(chosen),
  };
}

// ─── 2. Strikeouts milestone card ──────────────────────────────────────────

export function parseMlbPropShape(row: Pick<NflPropRow, "market_name" | "outcome_name">): {
  player: string;
  stat: string;
} | null {
  const outcomeColon = row.outcome_name.indexOf(":");
  const marketColon = row.market_name.indexOf(":");
  if (outcomeColon >= 0 && marketColon >= 0) {
    const player = propSubjectDisplay(row.outcome_name.slice(0, outcomeColon).trim());
    const stat = row.market_name
      .slice(marketColon + 1)
      .trim()
      .replace(/^\d+(?:\.\d+)?\+\s+/, "")
      .replace(/\s+O\/U\s+\d+(?:\.\d+)?$/i, "")
      .trim();
    return player && stat ? { player, stat } : null;
  }
  if (outcomeColon < 0 && marketColon >= 0) {
    const player = propSubjectDisplay(row.market_name.slice(0, marketColon).trim());
    const stat = row.market_name
      .slice(marketColon + 1)
      .trim()
      .replace(/^(?:Player|Batter|Pitcher)\s+/i, "")
      .replace(/^\d+(?:\.\d+)?\+\s+/, "")
      .replace(/\s+O\/U\s+\d+(?:\.\d+)?$/i, "")
      .trim();
    return player && stat ? { player, stat } : null;
  }
  return null;
}

export function buildMlbStrikeoutMilestoneCard(opts: {
  playerProps?: (NflPropRow & { contributor_outcome_ids?: number[] })[];
  afterPlayerProps?: unknown;
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  nowMs: number;
}): MilestoneCard | null {
  const props = opts.playerProps ?? [];
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);
  const basis: MilestoneBasis = phase === "before" ? "pregamePrice" : "pregameMark";

  const ladders = new Map<
    string,
    {
      player: string;
      stat: string;
      source: string;
      rows: (NflPropRow & { contributor_outcome_ids?: number[] })[];
    }
  >();

  for (const row of props) {
    if (row._inverted) continue;
    const shape = parseMlbPropShape(row);
    if (!shape || !shape.stat.toLowerCase().includes("strikeout")) continue;
    if (isTeamSubject(shape.player, [opts.homeTeam, opts.awayTeam])) continue;
    const key = `${shape.player}|${shape.stat}|${row.source ?? ""}`;
    const entry = ladders.get(key) ?? {
      player: shape.player,
      stat: shape.stat,
      source: row.source ?? "",
      rows: [],
    };
    entry.rows.push(row);
    ladders.set(key, entry);
  }

  const after = asObj(opts.afterPlayerProps);
  const afterQuestions =
    after && after.contract === AFTER_PROPS_CONTRACT && Array.isArray(after.questions)
      ? after.questions.map(asObj).filter((q): q is RawObj => q !== null)
      : [];
  const afterActuals = new Map<string, RawObj>();
  if (after && after.contract === AFTER_PROPS_CONTRACT && Array.isArray(after.actuals)) {
    for (const rawActual of after.actuals) {
      const a = asObj(rawActual);
      const k = asStr(a?.actual_key);
      if (a && k) afterActuals.set(k, a);
    }
  }

  const candidates: { key: string; card: MilestoneCard; defaultThreshold: number; pricedCount: number }[] = [];

  for (const [key, ladder] of ladders) {
    const overs = ladder.rows.filter((row) => {
      if (typeof row.threshold !== "number" || !Number.isFinite(row.threshold)) return false;
      const side = propOutcomeSide(row.outcome_name);
      if (side !== "unreadable") return side === "over";
      if (/\bunder\b/i.test(row.outcome_name)) return false;
      return /\bover\b/i.test(row.outcome_name) || /\d+\+/.test(row.outcome_name);
    });

    const counts = new Map<number, number>();
    for (const r of overs) {
      const t = Math.round(r.threshold!) === r.threshold! ? r.threshold! : Math.floor(r.threshold!) + 1;
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    const kept = overs.filter((r) => {
      const t = Math.round(r.threshold!) === r.threshold! ? r.threshold! : Math.floor(r.threshold!) + 1;
      return counts.get(t) === 1;
    });

    // Typed official final via contributor_outcome_ids in `after_player_props`
    const contributorIds = new Set(kept.flatMap((r) => r.contributor_outcome_ids ?? []));
    let typedFinalCount: number | null = null;
    if (contributorIds.size > 0 && afterQuestions.length > 0) {
      const matchedQuestions = afterQuestions.filter((q) => {
        const qIds = Array.isArray(q.contributor_outcome_ids) ? q.contributor_outcome_ids : [];
        return qIds.some((id) => typeof id === "number" && contributorIds.has(id));
      });
      const actualKeys = new Set(matchedQuestions.map((q) => asStr(q.actual_key)).filter((k): k is string => k !== null));
      if (actualKeys.size === 1) {
        const [onlyKey] = [...actualKeys];
        const actualObj = afterActuals.get(onlyKey);
        if (actualObj?.state === "final" && typeof actualObj.value === "number" && Number.isFinite(actualObj.value)) {
          typedFinalCount = actualObj.value;
        }
      }
    }

    const rungs: MilestoneRung[] = kept
      .map((row) => {
        const milestone =
          Math.round(row.threshold!) === row.threshold! ? row.threshold! : Math.floor(row.threshold!) + 1;
        const observedAt = basis === "pregamePrice" ? (row.observed_at ?? null) : null;
        const rawChance = basis === "pregamePrice" ? row.over_probability : (row.pregame_mark ?? null);
        let chance = openChance(rawChance);
        if (basis === "pregamePrice" && !isRecentQuote(observedAt, opts.nowMs)) {
          chance = null;
        }
        const hit =
          phase === "after" && typedFinalCount !== null ? typedFinalCount >= milestone : null;
        return {
          threshold: milestone,
          chance,
          observedAt,
          rowId: propRowId(row),
          hit,
        };
      })
      .sort((a, b) => a.threshold - b.threshold);

    const servedSide = ladder.rows.find((r) => r.player_team)?.player_team;
    const card: MilestoneCard = {
      kind: "milestone",
      id: "mlb:strikeouts",
      player: ladder.player,
      stat: ladder.stat,
      side: servedSide === "home" || servedSide === "away" ? servedSide : "unknown",
      basis,
      rungs,
      actual: phase === "after" ? typedFinalCount : null,
    };

    if (!milestoneProfile(card)) continue;

    let bestDist = Infinity;
    let defaultThreshold = -Infinity;
    for (const r of rungs) {
      if (r.chance === null) continue;
      const d = Math.abs(r.chance - 0.5);
      if (d < bestDist) {
        bestDist = d;
        defaultThreshold = r.threshold;
      }
    }
    const pricedCount = rungs.filter((r) => r.chance !== null).length;
    candidates.push({ key, card, defaultThreshold, pricedCount });
  }

  // Prefer the starter with the highest 50/50 strikeout threshold line, then most priced rungs.
  candidates.sort((a, b) => {
    if (a.defaultThreshold !== b.defaultThreshold) return b.defaultThreshold - a.defaultThreshold;
    if (a.pricedCount !== b.pricedCount) return b.pricedCount - a.pricedCount;
    return a.key.localeCompare(b.key);
  });

  return candidates[0]?.card ?? null;
}

// ─── 3. Run totals ladder card ─────────────────────────────────────────────

function pointChanceForMlb(
  o: MatrixOption,
  phase: LadderPhase,
  nowMs: number,
): { chance: number | null; observedAt: string | null; now: number | null } {
  if (phase === "before") {
    const recent = o.quoted !== null && isRecentQuote(o.observedAt, nowMs);
    return { chance: recent ? o.quoted : null, observedAt: o.observedAt, now: null };
  }
  if (phase === "after") {
    return { chance: o.reading, observedAt: null, now: null };
  }
  const now = o.quoted !== null && isRecentQuote(o.observedAt, nowMs) ? o.quoted : null;
  return { chance: o.baseline, observedAt: null, now };
}

export function buildMlbRunTotalsCard(opts: {
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
    if (!q.typed || q.kind !== "count_threshold" || q.quantityKey !== "runs" || q.subjectSide !== "game") continue;
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
      label: `Over ${line} runs`,
      side: "game",
      ...pointChanceForMlb(o, phase, opts.nowMs),
      result: settled ? o.result : null,
      detail: {
        detail: "option",
        label: o.label || `Over ${line} runs`,
        marketName: q.marketName || q.label,
        source: o.source,
        quoted: o.quoted,
        observedAt: o.observedAt,
        baseline: settled ? o.reading : o.baseline,
        baselineObservedAt: settled ? o.readingObservedAt : o.baselineObservedAt,
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
    unit: "runs",
    phase,
    points: kept,
    actual,
    forecast: null,
    awayShort: opts.awayShort,
    homeShort: opts.homeShort,
  };
}

// ─── 4. Extra innings card ─────────────────────────────────────────────────

export interface MlbExtraInningsOutcome {
  id: string;
  label: string;
  sourceCount: number;
  pregameChance: number | null;
  observedAt: string | null;
  venueResult: MlbVenueResult;
  marketName: string;
}

export interface MlbExtraInningsCard {
  kind: "mlb-extra-innings";
  id: "mlb:extraInnings";
  phase: LadderPhase;
  outcomes: MlbExtraInningsOutcome[];
}

export function isMlbExtraInningsMarketName(marketName: string | null | undefined): boolean {
  if (!marketName) return false;
  const parts = marketName.split(":");
  const suffix = (parts[parts.length - 1] ?? "").trim().toLowerCase();
  return suffix === "extra innings";
}

function canonicalExtraInningsLabel(raw: string): string {
  const trimmed = raw.trim();
  const lower = trimmed.toLowerCase();
  if (lower === "yes" || lower.startsWith("yes ")) return "Yes";
  if (lower === "no" || lower.startsWith("no ")) return "No";
  return trimmed;
}

export function buildMlbExtraInningsCard(opts: {
  other?: {
    market_name: string;
    outcome_name: string;
    probability?: number | null;
    pregame_mark?: number | null;
    observed_at?: string | null;
    source?: string | null;
    is_winner?: boolean | null;
    resolution_source?: string | null;
    _market_id?: number | null;
  }[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  nowMs: number;
}): MlbExtraInningsCard | null {
  const rows = (opts.other ?? []).filter((r) => isMlbExtraInningsMarketName(r.market_name));
  if (rows.length === 0) return null;
  const phase = phaseOf(opts.status, opts.commenceTime, opts.nowMs);

  // Print only a served number:
  // - If `other` carries a server-blended row (`source === "blended" | "blend"`), use its pregame number.
  // - If exactly one source prices the outcome, use that single served pregame number.
  // - If more than one unblended source prices the outcome, set `pregameChance = null`
  //   rather than averaging on the client or silently picking one order-dependent source.
  // During or after the game, read `pregame_mark` only; never mislabel a closing `probability` as pregame.
  const rowPregameChance = (row: (typeof rows)[number]): number | null =>
    phase === "before"
      ? isRecentQuote(row.observed_at, opts.nowMs)
        ? openChance(row.probability)
        : null
      : openChance(row.pregame_mark);

  const byLabel = new Map<
    string,
    {
      label: string;
      rows: (typeof rows)[number][];
      sources: Set<string>;
      verdicts: Set<"won" | "lost">;
      marketName: string;
    }
  >();

  for (const row of rows) {
    const label = canonicalExtraInningsLabel(row.outcome_name);
    const existing = byLabel.get(label);
    const verdict = outcomeRowVerdict(
      { is_winner: row.is_winner, resolution_source: row.resolution_source },
      phase === "after",
    );
    if (!existing) {
      const sources = new Set<string>();
      if (row.source) sources.add(row.source);
      const verdicts = new Set<"won" | "lost">();
      if (verdict) verdicts.add(verdict);
      byLabel.set(label, {
        label,
        rows: [row],
        sources,
        verdicts,
        marketName: "Extra Innings",
      });
    } else {
      existing.rows.push(row);
      if (row.source) existing.sources.add(row.source);
      if (verdict) existing.verdicts.add(verdict);
    }
  }

  const outcomes: MlbExtraInningsOutcome[] = [...byLabel.values()].map((group) => {
    const blendedRow = group.rows.find((r) => r.source === "blended" || r.source === "blend");
    const pricedRows = group.rows.filter((r) => rowPregameChance(r) !== null);

    let pregameChance: number | null = null;
    let observedAt: string | null = group.rows[0]?.observed_at ?? null;
    if (blendedRow) {
      pregameChance = rowPregameChance(blendedRow);
      observedAt = blendedRow.observed_at ?? observedAt;
    } else if (group.sources.size <= 1 && pricedRows.length === 1) {
      const singleRow = pricedRows[0];
      if (singleRow) {
        pregameChance = rowPregameChance(singleRow);
        observedAt = singleRow.observed_at ?? observedAt;
      }
    }

    // When venues disagree (`won` and `lost` both present), print `pending`, never a result.
    let venueResult: MlbVenueResult;
    if (group.verdicts.has("won") && group.verdicts.has("lost")) {
      venueResult = "pending";
    } else if (group.verdicts.has("won")) {
      venueResult = "won";
    } else if (group.verdicts.has("lost")) {
      venueResult = "lost";
    } else {
      venueResult = phase === "after" ? "pending" : "open";
    }
    return {
      id: `mlb-extra:${group.label.toLowerCase()}`,
      label: group.label,
      sourceCount: Math.max(1, group.sources.size),
      pregameChance,
      observedAt,
      venueResult,
      marketName: group.marketName,
    };
  });

  // Before/during the game, omit the card when no outcome has a usable pregame number;
  // keep the card after the game so the settled result is shown.
  if (phase !== "after" && !outcomes.some((o) => o.pregameChance !== null)) {
    return null;
  }

  // Sort Yes before No when both are present
  outcomes.sort((a, b) => {
    const order = (l: string) => (l === "Yes" ? 0 : l === "No" ? 1 : 2);
    return order(a.label) - order(b.label) || a.label.localeCompare(b.label);
  });

  return {
    kind: "mlb-extra-innings",
    id: "mlb:extraInnings",
    phase,
    outcomes,
  };
}

// ─── 5. Associated series card ─────────────────────────────────────────────

export interface MlbSeriesOption {
  optionKey: string;
  label: string;
  pregame: number | null;
  observedAt: string | null;
  sourceCount: number;
  result: MlbVenueResult;
  marketName: string;
}

export interface MlbSeriesQuestion {
  questionKey: string;
  label: string;
  options: MlbSeriesOption[];
}

export interface MlbSeriesCard {
  kind: "mlb-series";
  id: "mlb:series";
  questions: MlbSeriesQuestion[];
}

export function buildMlbSeriesCard(
  seriesQuestionMatrix: unknown,
  opts?: {
    status?: string | null;
    commenceTime?: string | null;
    nowMs?: number;
  },
): MlbSeriesCard | null {
  const m = asObj(seriesQuestionMatrix);
  if (!m || m.contract !== "10238.v1" || m.display_scope !== "series") return null;
  const decoded = decodeQuestionMatrix(seriesQuestionMatrix);
  const explicitPhase =
    opts && opts.nowMs !== undefined ? phaseOf(opts.status, opts.commenceTime, opts.nowMs) : null;
  const questions: MlbSeriesQuestion[] = [];
  for (const q of decoded) {
    if (!q.typed || q.options.length === 0) continue;
    const inferredSettled = q.options.some((o) => o.result !== null || o.valueState === "not_quoted");
    const phase: LadderPhase = explicitPhase ?? (inferredSettled ? "after" : "during");
    const options: MlbSeriesOption[] = q.options.map((o) => {
      // Same rule as NBA's ladders:
      // - before the game: a recent `quoted`
      // - during: `baseline` (`comparison.baseline`, pregame_pin)
      // - after the final: `reading` (`pregame_reading`, single contributor)
      let pregame: number | null = null;
      let observedAt: string | null = null;
      if (phase === "before") {
        const recent =
          o.quoted !== null &&
          opts?.nowMs !== undefined &&
          isRecentQuote(o.observedAt, opts.nowMs);
        pregame = recent ? openChance(o.quoted) : null;
        observedAt = pregame !== null ? o.observedAt : null;
      } else if (phase === "during") {
        pregame = openChance(o.baseline);
        observedAt = o.baselineObservedAt;
      } else {
        pregame = openChance(o.reading);
        observedAt = o.readingObservedAt;
      }
      const result: MlbVenueResult =
        o.result === true ? "won" : o.result === false ? "lost" : o.valueState === "quoted" ? "open" : "pending";
      return {
        optionKey: o.optionKey,
        label: o.label || q.label,
        pregame,
        observedAt,
        sourceCount: 1,
        result,
        marketName: q.marketName || q.label,
      };
    });
    questions.push({
      questionKey: q.questionKey,
      label: q.label,
      options,
    });
  }
  if (questions.length === 0) return null;
  return {
    kind: "mlb-series",
    id: "mlb:series",
    questions,
  };
}

// ─── Complete MLB deck in fixed slot order ─────────────────────────────────

export type MlbStoryCard = MlbHomeRunCard | MilestoneCard | LadderCard | MlbExtraInningsCard | MlbSeriesCard;

export function buildMlbEventCards(opts: {
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
    player_props?: (NflPropRow & {
      contributor_outcome_ids?: number[];
      is_winner?: boolean | null;
      resolution_source?: string | null;
    })[];
    after_player_props?: unknown;
    game_question_matrix?: unknown;
    other?: {
      market_name: string;
      outcome_name: string;
      probability?: number | null;
      pregame_mark?: number | null;
      observed_at?: string | null;
      source?: string | null;
      is_winner?: boolean | null;
      resolution_source?: string | null;
      _market_id?: number | null;
    }[];
  } | null;
  relatedFutures?: {
    series_question_matrix?: unknown;
  } | null;
  nowMs: number;
}): MlbStoryCard[] {
  if (!mlbCardsApply(opts.sportKey, opts.atlasMode)) return [];
  const gm = opts.gameMarkets;
  if (!gm) return [];

  const homeRuns = buildMlbHomeRunCard({
    afterPlayerProps: gm.after_player_props,
    playerProps: gm.player_props,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    nowMs: opts.nowMs,
  });
  const strikeouts = buildMlbStrikeoutMilestoneCard({
    playerProps: gm.player_props,
    afterPlayerProps: gm.after_player_props,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeTeam: opts.homeTeam,
    awayTeam: opts.awayTeam,
    nowMs: opts.nowMs,
  });
  const totals = buildMlbRunTotalsCard({
    gameQuestionMatrix: gm.game_question_matrix,
    status: opts.status,
    commenceTime: opts.commenceTime,
    homeScore: opts.homeScore,
    awayScore: opts.awayScore,
    homeShort: opts.homeShort,
    awayShort: opts.awayShort,
    nowMs: opts.nowMs,
  });
  const extraInnings = buildMlbExtraInningsCard({
    other: gm.other,
    status: opts.status,
    commenceTime: opts.commenceTime,
    nowMs: opts.nowMs,
  });
  const series = buildMlbSeriesCard(opts.relatedFutures?.series_question_matrix, {
    status: opts.status,
    commenceTime: opts.commenceTime,
    nowMs: opts.nowMs,
  });

  return [homeRuns, strikeouts, totals, extraInnings, series].filter((c): c is MlbStoryCard => c !== null);
}
