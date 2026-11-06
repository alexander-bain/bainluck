/**
 * #11974 Step E6d — Tennis story cards for the web event page (`?atlas=1`):
 * - Set-by-set path (`tennis-sets`, `id: "tennis:sets"`): "The match, set by set"
 *   (finished) / "Set-by-set path" (before/during play), reading `Set N Winner`
 *   questions in numeric set order without inventing unquoted sets.
 * - Exact match score in sets (`tennis-exact-score`, `id: "tennis:exactScore"`):
 *   "<Winner> in <two/three/four/five> sets" (finished) / "Exact match score in sets"
 *   (before/during play), preserving supplied set-score outcomes (`2-0`, `2-1`,
 *   `3-0`, `3-1`, `3-2`) with their recorded quotes or settlement grades.
 * - Total games ladder (`ladder`, `id: "total"`, `family: "total"`, `unit: "games"`):
 *   "Total games" from `Match O/U` total-games questions, with `actual: null`
 *   always enforced (`COMPONENT-CONTRACT.md` §7: "Missing actual/projection stays
 *   absent; tennis sets cannot supply games actual").
 */

import { isFinishedStatus } from "./eventState";
import {
  decodeQuestionMatrix,
  type LadderCard,
  type LadderPhase,
  type LadderPoint,
  type MatrixOption,
  type MatrixQuestion,
} from "./nbaEventCards";

export interface TennisGameMarketsLike {
  totals?: unknown[];
  other?: unknown[];
  game_question_matrix?: unknown;
}

export type EventStage = "before" | "during" | "after";

function resolveTennisStage(
  status: string | null | undefined,
  commenceTime: string | null | undefined,
  nowMs: number,
): EventStage {
  if (isFinishedStatus(status)) return "after";
  const commenceMs =
    typeof commenceTime === "string" ? Date.parse(commenceTime) : Number.NaN;
  if (
    status === "live" ||
    status === "in_progress" ||
    (!Number.isNaN(commenceMs) && commenceMs <= nowMs)
  ) {
    return "during";
  }
  return "before";
}

export function tennisCardsApply(
  sportKey: string | null | undefined,
  atlasMode = false,
): boolean {
  return Boolean(
    atlasMode && typeof sportKey === "string" && sportKey.startsWith("tennis_"),
  );
}

export type TennisOutcomeResultState =
  | "won"
  | "lost"
  | "closed_no_winner"
  | null;

export interface TennisSetPlayerOutcome {
  optionKey: string;
  playerName: string;
  shortName: string;
  side: "home" | "away";
  pregameProbability: number | null;
  liveProbability: number | null;
  result: TennisOutcomeResultState;
  observedAt: string | null;
  pregameObservedAt: string | null;
  source: string | null;
  marketId: number | string | null;
  outcomeId: number | string | null;
}

export interface TennisSetStepRow {
  setNumber: number;
  label: string;
  marketName: string;
  source: string | null;
  marketId: number | string | null;
  home: TennisSetPlayerOutcome;
  away: TennisSetPlayerOutcome;
  winnerSide: "home" | "away" | null;
  winnerName: string | null;
}

export interface TennisSetsCard {
  kind: "tennis-sets";
  id: "tennis:sets";
  stage: EventStage;
  title: string;
  subtitle: string;
  homePlayer: string;
  awayPlayer: string;
  homeShort: string;
  awayShort: string;
  sets: TennisSetStepRow[];
}

export interface TennisExactScoreOutcome {
  optionKey: string;
  outcomeName: string;
  winnerSide: "home" | "away";
  winnerName: string;
  winnerShort: string;
  winnerSets: number;
  loserSets: number;
  scoreLabel: string;
  pregameProbability: number | null;
  liveProbability: number | null;
  result: TennisOutcomeResultState;
  observedAt: string | null;
  pregameObservedAt: string | null;
  source: string | null;
  marketName: string;
  marketId: number | string | null;
  outcomeId: number | string | null;
}

export interface TennisExactScoreCard {
  kind: "tennis-exact-score";
  id: "tennis:exactScore";
  stage: EventStage;
  title: string;
  subtitle: string;
  marketName: string;
  source: string | null;
  homePlayer: string;
  awayPlayer: string;
  homeShort: string;
  awayShort: string;
  outcomes: TennisExactScoreOutcome[];
  winningOutcome: TennisExactScoreOutcome | null;
}

export type TennisStoryCard =
  | TennisSetsCard
  | TennisExactScoreCard
  | LadderCard;

export interface TennisCardInputs {
  sportKey: string | null | undefined;
  atlasMode?: boolean;
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  homeShort: string;
  awayShort: string;
  /** Event scores on tennis are sets won, NEVER total games. */
  homeScore: number | null | undefined;
  awayScore: number | null | undefined;
  pregameProjection?: { home: number; away: number } | null;
  gameMarkets: TennisGameMarketsLike | null | undefined;
  questionMatrix?: unknown;
  nowMs?: number;
}

type RawRecord = Record<string, unknown>;

function asRecord(v: unknown): RawRecord | null {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as RawRecord)
    : null;
}

function asProb(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1
    ? v
    : null;
}

function asIso(v: unknown): string | null {
  return typeof v === "string" && !Number.isNaN(Date.parse(v)) ? v : null;
}

function normalizePlayerTokens(value: string): string[] {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((tok) => tok.length >= 2);
}

export function tennisPlayerShortName(fullName: string): string {
  const cleaned = fullName.trim();
  if (!cleaned) return "";
  const parts = cleaned.split(/\s+/);
  return parts[parts.length - 1] || cleaned;
}

export function tennisNameMatchesSide(
  candidate: string,
  playerName: string,
  shortName: string,
): boolean {
  const candNorm = candidate
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
  const fullNorm = playerName
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
  if (!candNorm || !fullNorm) return false;
  if (candNorm === fullNorm) return true;
  if (candNorm.includes(fullNorm) || fullNorm.includes(candNorm)) return true;

  const candTokens = normalizePlayerTokens(candidate);
  const playerTokens = normalizePlayerTokens(playerName);
  const shortTokens = normalizePlayerTokens(shortName);
  const surname = playerTokens[playerTokens.length - 1];
  if (surname && surname.length >= 3 && candTokens.includes(surname)) {
    return true;
  }
  if (
    shortTokens.length > 0 &&
    shortTokens.every((t) => candTokens.includes(t))
  ) {
    return true;
  }
  return false;
}

function parseSetWinnerNumber(marketName: string): number | null {
  const m =
    marketName.match(/\bSet\s+([1-5])\s+Winner\b/i) ??
    marketName.match(/\b([1-5])(?:st|nd|rd|th)\s+Set\s+Winner\b/i);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isInteger(n) && n >= 1 && n <= 5 ? n : null;
}

function isExactMatchScoreMarketName(marketName: string): boolean {
  return /\b(?:Exact\s+Match\s+Score|Exact\s+Set\s+Score|Correct\s+Set\s+Score|Set\s+Betting)\b/i.test(
    marketName,
  );
}

const VALID_TENNIS_SET_SCORES = new Set([
  "2-0",
  "2-1",
  "3-0",
  "3-1",
  "3-2",
]);

function parseExactSetScoreOutcome(
  outcomeLabel: string,
  homeTeam: string,
  awayTeam: string,
  homeShort: string,
  awayShort: string,
): {
  winnerSide: "home" | "away";
  winnerSets: number;
  loserSets: number;
} | null {
  const cleaned = outcomeLabel.trim();
  // Match "<Player> wins A-B" or "<Player> A-B" or "<Player> (A-B)"
  const scoreMatch = cleaned.match(/(\d+)\s*[-–:]\s*(\d+)/);
  if (!scoreMatch) return null;
  const a = Number(scoreMatch[1]);
  const b = Number(scoreMatch[2]);
  if (!Number.isInteger(a) || !Number.isInteger(b)) return null;

  const prefix = cleaned
    .slice(0, scoreMatch.index ?? 0)
    .replace(/\bwins?\b/gi, "")
    .replace(/[-–:()]/g, " ")
    .trim();
  const suffix = cleaned
    .slice((scoreMatch.index ?? 0) + scoreMatch[0].length)
    .replace(/\bwins?\b/gi, "")
    .replace(/[-–:()]/g, " ")
    .trim();
  const playerText = prefix || suffix;
  if (!playerText) return null;

  const isHome = tennisNameMatchesSide(playerText, homeTeam, homeShort);
  const isAway = tennisNameMatchesSide(playerText, awayTeam, awayShort);
  if (isHome === isAway) return null;

  const winnerSets = a;
  const loserSets = b;
  if (!VALID_TENNIS_SET_SCORES.has(`${winnerSets}-${loserSets}`)) {
    return null;
  }

  return {
    winnerSide: isHome ? "home" : "away",
    winnerSets,
    loserSets,
  };
}

function numberToWord(n: number): string {
  switch (n) {
    case 0:
      return "zero";
    case 1:
      return "one";
    case 2:
      return "two";
    case 3:
      return "three";
    case 4:
      return "four";
    case 5:
      return "five";
    default:
      return String(n);
  }
}

function capitalizeWord(w: string): string {
  return w ? w[0].toUpperCase() + w.slice(1) : w;
}

function extractRawResultState(rawOpt: RawRecord): TennisOutcomeResultState {
  const res = asRecord(rawOpt.result);
  const state = typeof res?.state === "string" ? res.state : null;
  const evidenceKind =
    typeof res?.evidence_kind === "string" ? res.evidence_kind : null;
  if (evidenceKind === "ungradeable_result") return null;
  if (state === "closed_no_winner" || rawOpt.settlement_kind === "fair_value") {
    return "closed_no_winner";
  }
  if (state === "won") return "won";
  if (state === "lost") return "lost";
  if (
    rawOpt.resolution_source &&
    rawOpt.resolution_source !== "ungradeable_result" &&
    typeof rawOpt.is_winner === "boolean"
  ) {
    return rawOpt.is_winner ? "won" : "lost";
  }
  return null;
}

function extractRawOptionProbabilities(
  rawOpt: RawRecord,
  stage: EventStage,
): {
  pregameProbability: number | null;
  liveProbability: number | null;
  observedAt: string | null;
  pregameObservedAt: string | null;
  source: string | null;
  marketId: number | string | null;
  outcomeId: number | string | null;
} {
  const published = asRecord(rawOpt.published);
  const comparison = asRecord(rawOpt.comparison);
  const pregameReading = asRecord(rawOpt.pregame_reading);
  const baselineObj = asRecord(comparison?.baseline);
  const sourceEvidence = Array.isArray(rawOpt.source_evidence)
    ? asRecord(rawOpt.source_evidence[0])
    : null;

  const publishedValue =
    published?.value_state === "quoted" ? asProb(published.value) : null;
  const publishedObservedAt = asIso(published?.observed_at);

  const readingProb =
    pregameReading?.state === "available" &&
    pregameReading?.basis === "pregame_pin"
      ? asProb(pregameReading.probability)
      : null;
  const readingObservedAt = asIso(pregameReading?.observed_at);

  const baselineProb =
    comparison?.state === "comparable" && baselineObj?.basis === "pregame_pin"
      ? asProb(baselineObj.value ?? baselineObj.probability)
      : null;
  const baselineObservedAt = asIso(baselineObj?.observed_at);

  const directOpening = asProb(
    rawOpt.pregame_mark ?? rawOpt.opening_probability,
  );
  const directProb = asProb(rawOpt.probability);
  const isSettledRow =
    Boolean(rawOpt.resolution_source) || typeof rawOpt.is_winner === "boolean";

  let pregameProbability: number | null = null;
  let pregameObservedAt: string | null = null;
  let liveProbability: number | null = null;
  let observedAt: string | null =
    publishedObservedAt ??
    asIso(rawOpt.observed_at) ??
    asIso(sourceEvidence?.observed_at);

  if (stage === "before") {
    pregameProbability =
      publishedValue ??
      readingProb ??
      baselineProb ??
      directOpening ??
      (!isSettledRow ? directProb : null);
    pregameObservedAt =
      publishedObservedAt ?? readingObservedAt ?? baselineObservedAt ?? observedAt;
  } else if (stage === "during") {
    pregameProbability = readingProb ?? baselineProb ?? directOpening;
    pregameObservedAt = readingObservedAt ?? baselineObservedAt;
    liveProbability =
      publishedValue ?? (!isSettledRow ? directProb : null);
  } else {
    pregameProbability = readingProb ?? baselineProb ?? directOpening;
    pregameObservedAt = readingObservedAt ?? baselineObservedAt;
    liveProbability = null;
  }

  const source =
    (typeof published?.source === "string" ? published.source : null) ??
    (typeof rawOpt.source === "string" ? rawOpt.source : null) ??
    (typeof sourceEvidence?.source === "string" ? sourceEvidence.source : null);

  const marketIds = Array.isArray(rawOpt.market_ids) ? rawOpt.market_ids : [];
  const marketId =
    (typeof rawOpt._market_id === "number" ||
    typeof rawOpt._market_id === "string"
      ? rawOpt._market_id
      : null) ??
    (typeof marketIds[0] === "number" || typeof marketIds[0] === "string"
      ? marketIds[0]
      : null) ??
    (typeof sourceEvidence?.market_id === "number" ||
    typeof sourceEvidence?.market_id === "string"
      ? sourceEvidence.market_id
      : null);

  const contributorIds = Array.isArray(rawOpt.contributor_outcome_ids)
    ? rawOpt.contributor_outcome_ids
    : [];
  const outcomeId =
    (typeof contributorIds[0] === "number" ||
    typeof contributorIds[0] === "string"
      ? contributorIds[0]
      : null) ??
    (typeof sourceEvidence?.outcome_id === "number" ||
    typeof sourceEvidence?.outcome_id === "string"
      ? sourceEvidence.outcome_id
      : null);

  return {
    pregameProbability,
    liveProbability,
    observedAt,
    pregameObservedAt,
    source,
    marketId,
    outcomeId,
  };
}

function buildTennisSetsCard(
  inputs: TennisCardInputs,
  stage: EventStage,
  rawMatrixQuestions: RawRecord[],
): TennisSetsCard | null {
  const bySet = new Map<number, TennisSetStepRow>();

  const tryRegisterSetMarket = (
    marketName: string,
    rawOptions: RawRecord[],
  ) => {
    const setNumber = parseSetWinnerNumber(marketName);
    if (setNumber === null || bySet.has(setNumber)) return;

    let homeOpt: TennisSetPlayerOutcome | null = null;
    let awayOpt: TennisSetPlayerOutcome | null = null;

    for (const rawOpt of rawOptions) {
      const label = String(
        rawOpt.label ?? rawOpt.outcome_name ?? rawOpt.name ?? "",
      ).trim();
      if (!label) continue;
      const explicitSide =
        rawOpt.side === "home" || rawOpt.side === "away" ? rawOpt.side : null;
      const matchesHome =
        explicitSide === "home" ||
        (explicitSide === null &&
          tennisNameMatchesSide(label, inputs.homeTeam, inputs.homeShort));
      const matchesAway =
        explicitSide === "away" ||
        (explicitSide === null &&
          tennisNameMatchesSide(label, inputs.awayTeam, inputs.awayShort));

      if (matchesHome === matchesAway) continue;
      const side: "home" | "away" = matchesHome ? "home" : "away";
      const probs = extractRawOptionProbabilities(rawOpt, stage);
      const result = extractRawResultState(rawOpt);
      const optionKey =
        typeof rawOpt.option_key === "string"
          ? rawOpt.option_key
          : `tennis:set:${setNumber}:${side}`;

      const entry: TennisSetPlayerOutcome = {
        optionKey,
        playerName: side === "home" ? inputs.homeTeam : inputs.awayTeam,
        shortName: side === "home" ? inputs.homeShort : inputs.awayShort,
        side,
        pregameProbability: probs.pregameProbability,
        liveProbability: probs.liveProbability,
        result,
        observedAt: probs.observedAt,
        pregameObservedAt: probs.pregameObservedAt,
        source: probs.source,
        marketId: probs.marketId,
        outcomeId: probs.outcomeId,
      };

      if (side === "home" && !homeOpt) homeOpt = entry;
      if (side === "away" && !awayOpt) awayOpt = entry;
    }

    if (!homeOpt || !awayOpt) return;

    const winnerSide: "home" | "away" | null =
      homeOpt.result === "won"
        ? "home"
        : awayOpt.result === "won"
          ? "away"
          : null;
    const winnerName =
      winnerSide === "home"
        ? inputs.homeTeam
        : winnerSide === "away"
          ? inputs.awayTeam
          : null;

    bySet.set(setNumber, {
      setNumber,
      label: `Set ${setNumber} Winner`,
      marketName,
      source: homeOpt.source ?? awayOpt.source,
      marketId: homeOpt.marketId ?? awayOpt.marketId,
      home: homeOpt,
      away: awayOpt,
      winnerSide,
      winnerName,
    });
  };

  for (const q of rawMatrixQuestions) {
    const marketName = String(q.market_name ?? q.label ?? "").trim();
    const opts = Array.isArray(q.options)
      ? (q.options.map(asRecord).filter(Boolean) as RawRecord[])
      : [];
    if (marketName && opts.length >= 2) {
      tryRegisterSetMarket(marketName, opts);
    }
  }

  const otherRows = Array.isArray(inputs.gameMarkets?.other)
    ? inputs.gameMarkets!.other
    : [];
  if (otherRows.length > 0) {
    const grouped = new Map<string, RawRecord[]>();
    for (const row of otherRows) {
      const r = asRecord(row);
      if (!r) continue;
      const mName = String(r.market_name ?? r.question ?? "").trim();
      if (!mName || parseSetWinnerNumber(mName) === null) continue;
      const list = grouped.get(mName) ?? [];
      list.push(r);
      grouped.set(mName, list);
    }
    for (const [mName, list] of grouped.entries()) {
      tryRegisterSetMarket(mName, list);
    }
  }

  const sets = [...bySet.values()].sort((a, b) => a.setNumber - b.setNumber);
  if (sets.length === 0) return null;

  const allResolved = sets.every((s) => s.winnerSide !== null);
  const title =
    stage === "after" || allResolved
      ? "The match, set by set"
      : "Set-by-set path";
  const subtitle =
    stage === "after" || allResolved
      ? "Resolved set outcomes in match order. Unsupplied sets are never invented."
      : "Set winner markets in numeric order. Each set is graded independently.";

  return {
    kind: "tennis-sets",
    id: "tennis:sets",
    stage,
    title,
    subtitle,
    homePlayer: inputs.homeTeam,
    awayPlayer: inputs.awayTeam,
    homeShort: inputs.homeShort,
    awayShort: inputs.awayShort,
    sets,
  };
}

function buildTennisExactScoreCard(
  inputs: TennisCardInputs,
  stage: EventStage,
  rawMatrixQuestions: RawRecord[],
): TennisExactScoreCard | null {
  let matchedMarketName: string | null = null;
  let matchedOptions: RawRecord[] = [];

  for (const q of rawMatrixQuestions) {
    const marketName = String(q.market_name ?? q.label ?? "").trim();
    if (!isExactMatchScoreMarketName(marketName)) continue;
    const opts = Array.isArray(q.options)
      ? (q.options.map(asRecord).filter(Boolean) as RawRecord[])
      : [];
    if (opts.length >= 2) {
      matchedMarketName = marketName;
      matchedOptions = opts;
      break;
    }
  }

  if (!matchedMarketName) {
    const otherRows = Array.isArray(inputs.gameMarkets?.other)
      ? inputs.gameMarkets!.other
      : [];
    const grouped = new Map<string, RawRecord[]>();
    for (const row of otherRows) {
      const r = asRecord(row);
      if (!r) continue;
      const mName = String(r.market_name ?? r.question ?? "").trim();
      if (!mName || !isExactMatchScoreMarketName(mName)) continue;
      const list = grouped.get(mName) ?? [];
      list.push(r);
      grouped.set(mName, list);
    }
    for (const [mName, list] of grouped.entries()) {
      if (list.length >= 2) {
        matchedMarketName = mName;
        matchedOptions = list;
        break;
      }
    }
  }

  if (!matchedMarketName || matchedOptions.length === 0) return null;

  const outcomes: TennisExactScoreOutcome[] = [];
  const seenKeys = new Set<string>();

  for (const rawOpt of matchedOptions) {
    const outcomeName = String(
      rawOpt.label ?? rawOpt.outcome_name ?? rawOpt.name ?? "",
    ).trim();
    if (!outcomeName) continue;

    const parsed = parseExactSetScoreOutcome(
      outcomeName,
      inputs.homeTeam,
      inputs.awayTeam,
      inputs.homeShort,
      inputs.awayShort,
    );
    if (!parsed) continue;

    const dedupeKey = `${parsed.winnerSide}:${parsed.winnerSets}-${parsed.loserSets}`;
    if (seenKeys.has(dedupeKey)) continue;
    seenKeys.add(dedupeKey);

    const probs = extractRawOptionProbabilities(rawOpt, stage);
    const result = extractRawResultState(rawOpt);
    const winnerName =
      parsed.winnerSide === "home" ? inputs.homeTeam : inputs.awayTeam;
    const winnerShort =
      parsed.winnerSide === "home" ? inputs.homeShort : inputs.awayShort;
    const optionKey =
      typeof rawOpt.option_key === "string"
        ? rawOpt.option_key
        : `tennis:exact:${dedupeKey}`;

    outcomes.push({
      optionKey,
      outcomeName,
      winnerSide: parsed.winnerSide,
      winnerName,
      winnerShort,
      winnerSets: parsed.winnerSets,
      loserSets: parsed.loserSets,
      scoreLabel: `${winnerShort} ${parsed.winnerSets}–${parsed.loserSets}`,
      pregameProbability: probs.pregameProbability,
      liveProbability: probs.liveProbability,
      result,
      observedAt: probs.observedAt,
      pregameObservedAt: probs.pregameObservedAt,
      source: probs.source,
      marketName: matchedMarketName,
      marketId: probs.marketId,
      outcomeId: probs.outcomeId,
    });
  }

  if (outcomes.length < 2) return null;

  outcomes.sort((a, b) => {
    if (a.winnerSide !== b.winnerSide) {
      return a.winnerSide === "home" ? -1 : 1;
    }
    if (a.winnerSets !== b.winnerSets) return a.winnerSets - b.winnerSets;
    return a.loserSets - b.loserSets;
  });

  const winningOutcome = outcomes.find((o) => o.result === "won") ?? null;
  const totalSetsPlayed = winningOutcome
    ? winningOutcome.winnerSets + winningOutcome.loserSets
    : null;

  const title =
    stage === "after" && winningOutcome && totalSetsPlayed !== null
      ? `${winningOutcome.winnerShort} in ${numberToWord(totalSetsPlayed)} sets`
      : "Exact match score in sets";

  const subtitle =
    stage === "after" && winningOutcome
      ? `${capitalizeWord(numberToWord(winningOutcome.winnerSets))} sets to ${numberToWord(winningOutcome.loserSets)} is the match result. Games handicaps and games totals stay in a separate unit-specific group.`
      : "Exact set-score outcomes keep their recorded quotes without normalization. Games handicaps and games totals stay in a separate unit-specific group.";

  return {
    kind: "tennis-exact-score",
    id: "tennis:exactScore",
    stage,
    title,
    subtitle,
    marketName: matchedMarketName,
    source: outcomes[0]?.source ?? null,
    homePlayer: inputs.homeTeam,
    awayPlayer: inputs.awayTeam,
    homeShort: inputs.homeShort,
    awayShort: inputs.awayShort,
    outcomes,
    winningOutcome,
  };
}

function parseTennisTotalGamesThreshold(marketName: string): number | null {
  // Exclude set-specific or player-specific totals or spreads/handicaps
  if (
    /\b(?:Set\s+[1-5]|[1-5](?:st|nd|rd|th)\s+Set|Set\s+Handicap|Game\s+Spread|Tiebreak)\b/i.test(
      marketName,
    )
  ) {
    return null;
  }
  const m =
    marketName.match(/\bMatch\s+O\/U\s+(\d+(?:\.\d+)?)\b/i) ??
    marketName.match(/\bTotal\s+Games[:\s]+(?:O\/U\s+)?(\d+(?:\.\d+)?)\b/i) ??
    marketName.match(/\bO\/U\s+(\d+(?:\.\d+)?)\s+Games\b/i);
  if (!m) return null;
  const line = Number(m[1]);
  return Number.isFinite(line) && line >= 10 && line <= 65 ? line : null;
}

function buildTennisTotalGamesCard(
  inputs: TennisCardInputs,
  stage: EventStage,
  decodedQuestions: MatrixQuestion[],
  rawMatrixQuestions: RawRecord[],
): LadderCard | null {
  const phase: LadderPhase = stage;
  const byLine = new Map<number, LadderPoint>();

  // 1. Check typed count_threshold questions in game_question_matrix first
  for (const q of decodedQuestions) {
    if (
      q.typed &&
      q.kind === "count_threshold" &&
      q.subjectSide === "game" &&
      q.periodKey === "full_game" &&
      q.relation === "ge"
    ) {
      const line = q.line ?? (q.bound !== null ? q.bound - 0.5 : null);
      if (line === null || byLine.has(line)) continue;
      const overOpt = q.options.find(
        (o: MatrixOption) =>
          o.side === "over" || /^over\b/i.test(o.label.trim()),
      );
      if (!overOpt) continue;
      const chance =
        phase === "before"
          ? overOpt.quoted
          : phase === "during"
            ? overOpt.baseline
            : overOpt.reading;
      const now = phase === "during" ? overOpt.quoted : null;
      byLine.set(line, {
        optionKey: overOpt.optionKey,
        x: line,
        label: `Over ${line} games`,
        side: "game",
        chance,
        now,
        observedAt: overOpt.observedAt,
        result: phase === "after" ? overOpt.result : null,
        detail: {
          detail: "option",
          label: overOpt.label || q.label,
          marketName: q.marketName,
          source: overOpt.source,
          quoted: overOpt.quoted,
          observedAt: overOpt.observedAt,
          baseline: phase === "after" ? overOpt.reading : overOpt.baseline,
          baselineObservedAt:
            phase === "after"
              ? overOpt.readingObservedAt
              : overOpt.baselineObservedAt,
          result: overOpt.result,
        },
      });
    }
  }

  // 2. Check untyped `Match O/U X.5` questions in raw game_question_matrix
  for (const rawQ of rawMatrixQuestions) {
    const marketName = String(rawQ.market_name ?? rawQ.label ?? "").trim();
    const line = parseTennisTotalGamesThreshold(marketName);
    if (line === null || byLine.has(line)) continue;
    const opts = Array.isArray(rawQ.options)
      ? (rawQ.options.map(asRecord).filter(Boolean) as RawRecord[])
      : [];
    const overRaw = opts.find((o) => {
      const lbl = String(o.label ?? o.outcome_name ?? "").trim();
      const legSide = Array.isArray(o.source_evidence)
        ? asRecord(o.source_evidence[0])?.leg_side
        : null;
      return (
        /^over\b/i.test(lbl) ||
        o.side === "over" ||
        legSide === "over"
      );
    });
    const underRaw =
      !overRaw && opts.length === 1
        ? opts.find((o) => {
            const lbl = String(o.label ?? o.outcome_name ?? "").trim();
            return /^under\b/i.test(lbl);
          })
        : null;

    const chosenRaw = overRaw ?? underRaw;
    if (!chosenRaw) continue;
    const isInvertedUnder = Boolean(!overRaw && underRaw);
    const probs = extractRawOptionProbabilities(chosenRaw, stage);
    const rawRes = extractRawResultState(chosenRaw);

    const invertProb = (p: number | null) =>
      p === null ? null : isInvertedUnder ? Math.max(0, Math.min(1, 1 - p)) : p;

    const chance = invertProb(probs.pregameProbability);
    const now = invertProb(probs.liveProbability);
    const result =
      stage === "after" && (rawRes === "won" || rawRes === "lost")
        ? isInvertedUnder
          ? rawRes === "lost"
          : rawRes === "won"
        : null;

    const optionKey =
      typeof chosenRaw.option_key === "string"
        ? chosenRaw.option_key
        : `tennis:total:${line}`;

    byLine.set(line, {
      optionKey,
      x: line,
      label: `Over ${line} games`,
      side: "game",
      chance,
      now,
      observedAt: probs.observedAt,
      result,
      detail: {
        detail: "option",
        label: `Over ${line} games`,
        marketName,
        source: probs.source,
        quoted: now ?? (stage === "before" ? chance : null),
        observedAt: probs.observedAt,
        baseline: chance,
        baselineObservedAt: probs.pregameObservedAt,
        result,
      },
    });
  }

  // 3. Fallback to gameMarkets.totals for Match O/U rows
  const totalsRows = Array.isArray(inputs.gameMarkets?.totals)
    ? inputs.gameMarkets!.totals
    : [];
  for (const row of totalsRows) {
    const r = asRecord(row);
    if (!r) continue;
    const marketName = String(r.market_name ?? "").trim();
    const threshold =
      typeof r.threshold === "number" && Number.isFinite(r.threshold)
        ? r.threshold
        : parseTennisTotalGamesThreshold(marketName);
    if (threshold === null || byLine.has(threshold)) continue;
    if (
      marketName &&
      /\b(?:Set\s+[1-5]|[1-5](?:st|nd|rd|th)\s+Set|Set\s+Handicap)\b/i.test(
        marketName,
      )
    ) {
      continue;
    }

    const overProb = asProb(r.over_probability ?? r.probability);
    const isSettled =
      Boolean(r.resolution_source) || typeof r.is_winner === "boolean";
    const outcomeName = String(r.outcome_name ?? "Over").trim();
    const isUnderRow = /^under\b/i.test(outcomeName);
    const result =
      stage === "after" &&
      r.resolution_source &&
      r.resolution_source !== "ungradeable_result" &&
      typeof r.is_winner === "boolean"
        ? isUnderRow
          ? !r.is_winner
          : r.is_winner
        : null;

    const chance =
      stage === "before" && !isSettled
        ? overProb
        : asProb(r.pregame_mark ?? r.opening_probability);
    const now = stage === "during" && !isSettled ? overProb : null;
    const optionKey = `tennis:total:${threshold}`;

    byLine.set(threshold, {
      optionKey,
      x: threshold,
      label: `Over ${threshold} games`,
      side: "game",
      chance,
      now,
      observedAt: asIso(r.observed_at),
      result,
      detail: {
        detail: "option",
        label: `Over ${threshold} games`,
        marketName: marketName || `Match O/U ${threshold}`,
        source: typeof r.source === "string" ? r.source : null,
        quoted: now ?? (stage === "before" ? chance : null),
        observedAt: asIso(r.observed_at),
        baseline: chance,
        baselineObservedAt: null,
        result,
      },
    });
  }

  const points = [...byLine.values()].sort((a, b) => a.x - b.x);
  if (points.length < 2) return null;

  // CRITICAL TRUTH GUARD (COMPONENT-CONTRACT.md §7, line 117):
  // "Missing actual/projection stays absent; tennis sets cannot supply games actual."
  // Event homeScore/awayScore on tennis events are sets won (e.g. 2-1), NEVER total games.
  return {
    kind: "ladder",
    id: "total",
    family: "total",
    unit: "games",
    phase,
    points,
    actual: null,
    forecast: null,
    awayShort: inputs.awayShort,
    homeShort: inputs.homeShort,
  };
}

export function tennisCards(inputs: TennisCardInputs): TennisStoryCard[] {
  if (!tennisCardsApply(inputs.sportKey, inputs.atlasMode)) return [];

  const normalizedInputs: TennisCardInputs = {
    ...inputs,
    homeShort:
      inputs.homeShort && inputs.homeShort !== inputs.homeTeam
        ? inputs.homeShort
        : tennisPlayerShortName(inputs.homeTeam),
    awayShort:
      inputs.awayShort && inputs.awayShort !== inputs.awayTeam
        ? inputs.awayShort
        : tennisPlayerShortName(inputs.awayTeam),
  };

  const stage = resolveTennisStage(
    normalizedInputs.status,
    normalizedInputs.commenceTime,
    normalizedInputs.nowMs ?? Date.now(),
  );

  const matrixSource =
    normalizedInputs.questionMatrix ??
    normalizedInputs.gameMarkets?.game_question_matrix;
  const decodedQuestions = decodeQuestionMatrix(matrixSource);
  const rawMatrixObj = asRecord(matrixSource);
  const rawMatrixQuestions = Array.isArray(rawMatrixObj?.questions)
    ? (rawMatrixObj!.questions.map(asRecord).filter(Boolean) as RawRecord[])
    : [];

  const cards: TennisStoryCard[] = [];

  const setsCard = buildTennisSetsCard(
    normalizedInputs,
    stage,
    rawMatrixQuestions,
  );
  if (setsCard) cards.push(setsCard);

  const exactScoreCard = buildTennisExactScoreCard(
    normalizedInputs,
    stage,
    rawMatrixQuestions,
  );
  if (exactScoreCard) cards.push(exactScoreCard);

  const totalGamesCard = buildTennisTotalGamesCard(
    normalizedInputs,
    stage,
    decodedQuestions,
    rawMatrixQuestions,
  );
  if (totalGamesCard) cards.push(totalGamesCard);

  return cards;
}
