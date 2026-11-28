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
 *
 * Number & settlement rules (shared with E6a–E6c):
 * 1. Print only a served number: a server-combined row (`source === "blended" | "blend"`),
 *    or exactly one source. Several sources with no combined row print no number.
 *    Never average on the client.
 * 2. Before the game, a recent quote. During the game, the pregame pin. After the
 *    final, only the producer's `pregame_reading` (or `pregame_mark` on fallback rows;
 *    never `opening_probability`).
 * 3. Settlement goes through `outcomeRowVerdict`; venues that disagree show Pending.
 * 4. A card with nothing to show is not drawn.
 */

import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
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

/** Quotes older than 6 hours before the match are treated as stale. */
const RECENT_QUOTE_MAX_AGE_MS = 6 * 3600 * 1000;

function isRecentQuote(observedAt: string | null | undefined, nowMs: number): boolean {
  if (!observedAt) return true;
  const parsed = Date.parse(observedAt);
  if (Number.isNaN(parsed)) return true;
  return nowMs - parsed <= RECENT_QUOTE_MAX_AGE_MS;
}

function isServerBlendedSource(source: string | null | undefined): boolean {
  return source === "blended" || source === "blend";
}

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
  | "pending"
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
  sourceCount: number;
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
  sourceCount: number;
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

function normalizePlayerPlain(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function tennisNameMatchesSide(
  candidate: string,
  playerName: string,
  shortName: string,
): boolean {
  const candNorm = normalizePlayerPlain(candidate);
  const fullNorm = normalizePlayerPlain(playerName);
  if (!candNorm || !fullNorm) return false;
  if (candNorm === fullNorm) return true;
  if (
    candNorm.length >= 3 &&
    (candNorm.includes(fullNorm) || fullNorm.includes(candNorm))
  ) {
    return true;
  }

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

export function matchTennisPlayerSide(
  candidate: string,
  homeTeam: string,
  awayTeam: string,
  homeShort: string,
  awayShort: string,
): "home" | "away" | null {
  const candNorm = normalizePlayerPlain(candidate);
  const homeNorm = normalizePlayerPlain(homeTeam);
  const awayNorm = normalizePlayerPlain(awayTeam);
  const homeShortNorm = normalizePlayerPlain(homeShort);
  const awayShortNorm = normalizePlayerPlain(awayShort);
  if (!candNorm) return null;

  // 1. Exact full-name match
  const exactHome = Boolean(homeNorm && candNorm === homeNorm);
  const exactAway = Boolean(awayNorm && candNorm === awayNorm);
  if (exactHome !== exactAway) return exactHome ? "home" : "away";
  if (exactHome && exactAway) return null;

  // 2. Exact short-name match
  const shortHome = Boolean(homeShortNorm && candNorm === homeShortNorm);
  const shortAway = Boolean(awayShortNorm && candNorm === awayShortNorm);
  if (shortHome !== shortAway) return shortHome ? "home" : "away";
  if (shortHome && shortAway) return null;

  // 3. Full-name substring match (candNorm >= 3 chars to avoid short-string false positives)
  const subHome = Boolean(
    candNorm.length >= 3 &&
      homeNorm &&
      (candNorm.includes(homeNorm) || homeNorm.includes(candNorm)),
  );
  const subAway = Boolean(
    candNorm.length >= 3 &&
      awayNorm &&
      (candNorm.includes(awayNorm) || awayNorm.includes(candNorm)),
  );
  if (subHome !== subAway) return subHome ? "home" : "away";
  if (subHome && subAway) return null;

  // 4. Token / surname match
  const tokHome = tennisNameMatchesSide(candidate, homeTeam, homeShort);
  const tokAway = tennisNameMatchesSide(candidate, awayTeam, awayShort);
  if (tokHome !== tokAway) return tokHome ? "home" : "away";
  return null;
}

function normalizeSourceKey(source: string | null | undefined): string {
  return typeof source === "string" ? source.trim().toLowerCase() : "";
}

export function dedupeCandidatesBySource<T>(
  candidates: T[],
  getSource: (item: T) => string | null | undefined,
): T[] {
  const seenNamedSources = new Set<string>();
  const deduped: T[] = [];
  for (const c of candidates) {
    const src = normalizeSourceKey(getSource(c));
    if (src) {
      if (seenNamedSources.has(src)) continue;
      seenNamedSources.add(src);
    }
    deduped.push(c);
  }
  return deduped;
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

  const matchedSide = matchTennisPlayerSide(
    playerText,
    homeTeam,
    awayTeam,
    homeShort,
    awayShort,
  );
  if (!matchedSide) return null;

  const winnerSets = a;
  const loserSets = b;
  if (!VALID_TENNIS_SET_SCORES.has(`${winnerSets}-${loserSets}`)) {
    return null;
  }

  return {
    winnerSide: matchedSide,
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

function singleEvidenceVerdict(
  ev: RawRecord,
  stage: EventStage,
): "won" | "lost" | "pending" | null {
  const res = asRecord(ev.result);
  const state = typeof res?.state === "string" ? res.state : null;
  const evidenceKind =
    typeof res?.evidence_kind === "string" ? res.evidence_kind : null;
  if (evidenceKind === "ungradeable_result" || state === "disputed" || state === "pending") {
    return "pending";
  }
  if (state === "won") return "won";
  if (state === "lost") return "lost";
  const verdict = outcomeRowVerdict(
    {
      is_winner: typeof ev.is_winner === "boolean" ? ev.is_winner : null,
      resolution_source:
        ev.resolution_source === null
          ? null
          : typeof ev.resolution_source === "string"
            ? ev.resolution_source
            : undefined,
    },
    stage === "after",
  );
  if (verdict === "won") return "won";
  if (verdict === "lost") return "lost";
  return null;
}

/**
 * Resolves an option's settled state through `outcomeRowVerdict` (#4788).
 * If contributing venues disagree (`won` vs `lost`), returns `"pending"`.
 */
function extractRawResultState(
  rawOpt: RawRecord,
  stage: EventStage,
): TennisOutcomeResultState {
  const evidenceList = Array.isArray(rawOpt.source_evidence)
    ? (rawOpt.source_evidence.map(asRecord).filter(Boolean) as RawRecord[])
    : [];
  if (evidenceList.length > 1) {
    let sawWon = false;
    let sawLost = false;
    let sawPending = false;
    for (const ev of evidenceList) {
      const v = singleEvidenceVerdict(ev, stage);
      if (v === "won") sawWon = true;
      else if (v === "lost") sawLost = true;
      else if (v === "pending") sawPending = true;
    }
    if ((sawWon && sawLost) || sawPending) return "pending";
  }

  const res = asRecord(rawOpt.result);
  const state = typeof res?.state === "string" ? res.state : null;
  const evidenceKind =
    typeof res?.evidence_kind === "string" ? res.evidence_kind : null;
  if (evidenceKind === "ungradeable_result" || state === "disputed" || state === "pending") {
    return stage === "after" ? "pending" : null;
  }
  if (state === "closed_no_winner" || rawOpt.settlement_kind === "fair_value") {
    return "closed_no_winner";
  }
  if (state === "won") return "won";
  if (state === "lost") return "lost";

  const verdict = outcomeRowVerdict(
    {
      is_winner: typeof rawOpt.is_winner === "boolean" ? rawOpt.is_winner : null,
      resolution_source:
        rawOpt.resolution_source === null
          ? null
          : typeof rawOpt.resolution_source === "string"
            ? rawOpt.resolution_source
            : undefined,
    },
    stage === "after",
  );
  if (verdict === "won") return "won";
  if (verdict === "lost") return "lost";
  if (
    stage === "after" &&
    (rawOpt.resolution_source === "ungradeable_result" ||
      rawOpt.resolution_source === null)
  ) {
    return "pending";
  }
  return null;
}

function combineCandidateResults(
  results: TennisOutcomeResultState[],
  stage: EventStage,
): TennisOutcomeResultState {
  const hasWon = results.includes("won");
  const hasLost = results.includes("lost");
  if (hasWon && hasLost) return "pending";
  if (results.includes("pending")) return "pending";
  if (hasWon) return "won";
  if (hasLost) return "lost";
  if (results.includes("closed_no_winner")) return "closed_no_winner";
  return stage === "after" && results.length > 1 ? "pending" : null;
}

function extractRawOptionProbabilities(
  rawOpt: RawRecord,
  stage: EventStage,
  nowMs: number,
): {
  pregameProbability: number | null;
  liveProbability: number | null;
  observedAt: string | null;
  pregameObservedAt: string | null;
  source: string | null;
  sourceCount: number;
  marketId: number | string | null;
  outcomeId: number | string | null;
} {
  const published = asRecord(rawOpt.published);
  const comparison = asRecord(rawOpt.comparison);
  const pregameReading = asRecord(rawOpt.pregame_reading);
  const baselineObj = asRecord(comparison?.baseline);
  const evidenceList = Array.isArray(rawOpt.source_evidence)
    ? (rawOpt.source_evidence.map(asRecord).filter(Boolean) as RawRecord[])
    : [];
  const sourceEvidence = evidenceList[0] ?? null;

  const isMatrixOption =
    published !== null || comparison !== null || pregameReading !== null;

  const dedupedEvidence = dedupeCandidatesBySource(evidenceList, (ev) =>
    typeof ev?.source === "string" ? (ev.source as string) : null,
  );
  const distinctEvidenceCount = Math.max(1, dedupedEvidence.length);

  const rawSource =
    (typeof published?.source === "string" ? published.source : null) ??
    (typeof rawOpt.source === "string" ? rawOpt.source : null) ??
    (distinctEvidenceCount === 1 && typeof sourceEvidence?.source === "string"
      ? (sourceEvidence.source as string)
      : null);

  const multiSourceEvidenceUnblended =
    !isServerBlendedSource(rawSource) && distinctEvidenceCount > 1;

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

  // #11125 single-contributor contract: never read `opening_probability` on fallback rows.
  const directPregameMark = asProb(rawOpt.pregame_mark);
  const directProb = asProb(rawOpt.probability);
  const isSettledRow =
    Boolean(rawOpt.resolution_source) || typeof rawOpt.is_winner === "boolean";

  const observedAt: string | null =
    publishedObservedAt ??
    asIso(rawOpt.observed_at) ??
    asIso(sourceEvidence?.observed_at);

  let pregameProbability: number | null = null;
  let pregameObservedAt: string | null = null;
  let liveProbability: number | null = null;

  if (!multiSourceEvidenceUnblended) {
    if (isMatrixOption) {
      if (stage === "before") {
        // Before the game: recent quote only.
        pregameProbability = isRecentQuote(publishedObservedAt, nowMs)
          ? publishedValue
          : null;
        pregameObservedAt =
          pregameProbability !== null ? publishedObservedAt : null;
      } else if (stage === "during") {
        // During the game: pregame pin (`comparison.baseline`) + live recent quote.
        pregameProbability = baselineProb;
        pregameObservedAt =
          pregameProbability !== null ? baselineObservedAt : null;
        liveProbability = isRecentQuote(publishedObservedAt, nowMs)
          ? publishedValue
          : null;
      } else {
        // After the final: only the producer's `pregame_reading` (#11125).
        pregameProbability = readingProb;
        pregameObservedAt =
          pregameProbability !== null ? readingObservedAt : null;
        liveProbability = null;
      }
    } else {
      // Fallback row (`gameMarkets.other`):
      if (stage === "before") {
        pregameProbability =
          !isSettledRow && isRecentQuote(observedAt, nowMs) ? directProb : null;
        pregameObservedAt = pregameProbability !== null ? observedAt : null;
      } else if (stage === "during") {
        pregameProbability = directPregameMark;
        pregameObservedAt = null;
        liveProbability =
          !isSettledRow && isRecentQuote(observedAt, nowMs) ? directProb : null;
      } else {
        pregameProbability = directPregameMark;
        pregameObservedAt = null;
        liveProbability = null;
      }
    }
  }

  const source = multiSourceEvidenceUnblended ? null : rawSource;
  const sourceCount = distinctEvidenceCount;

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
    sourceCount,
    marketId,
    outcomeId,
  };
}

function resolveCandidateSetOutcome(
  candidates: TennisSetPlayerOutcome[],
  stage: EventStage,
): TennisSetPlayerOutcome | null {
  if (candidates.length === 0) return null;
  const deduped = dedupeCandidatesBySource(candidates, (c) => c.source);
  const blended = deduped.find((c) => isServerBlendedSource(c.source));
  const multiUnblended = !blended && deduped.length > 1;
  const chosen = blended ?? deduped[0]!;
  const combinedResult =
    candidates.length > 1
      ? combineCandidateResults(
          candidates.map((c) => c.result),
          stage,
        )
      : chosen.result;

  return {
    ...chosen,
    pregameProbability: multiUnblended ? null : chosen.pregameProbability,
    liveProbability: multiUnblended ? null : chosen.liveProbability,
    source: multiUnblended ? null : chosen.source,
    sourceCount: Math.max(chosen.sourceCount, deduped.length),
    result: combinedResult,
  };
}

function buildTennisSetsCard(
  inputs: TennisCardInputs,
  stage: EventStage,
  rawMatrixQuestions: RawRecord[],
  nowMs: number,
): TennisSetsCard | null {
  const bySet = new Map<number, TennisSetStepRow>();

  const tryRegisterSetMarket = (
    setNumber: number,
    marketName: string,
    rawOptions: RawRecord[],
  ) => {
    if (bySet.has(setNumber)) return;

    const homeCandidates: TennisSetPlayerOutcome[] = [];
    const awayCandidates: TennisSetPlayerOutcome[] = [];

    for (const rawOpt of rawOptions) {
      const label = String(
        rawOpt.label ?? rawOpt.outcome_name ?? rawOpt.name ?? "",
      ).trim();
      if (!label) continue;
      const explicitSide =
        rawOpt.side === "home" || rawOpt.side === "away" ? rawOpt.side : null;
      const side =
        explicitSide ??
        matchTennisPlayerSide(
          label,
          inputs.homeTeam,
          inputs.awayTeam,
          inputs.homeShort,
          inputs.awayShort,
        );
      if (!side) continue;
      const probs = extractRawOptionProbabilities(rawOpt, stage, nowMs);
      const result = extractRawResultState(rawOpt, stage);
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
        sourceCount: probs.sourceCount,
        marketId: probs.marketId,
        outcomeId: probs.outcomeId,
      };

      if (side === "home") homeCandidates.push(entry);
      else awayCandidates.push(entry);
    }

    const homeOpt = resolveCandidateSetOutcome(homeCandidates, stage);
    const awayOpt = resolveCandidateSetOutcome(awayCandidates, stage);
    if (!homeOpt || !awayOpt) return;

    // If both sides claim "won", venues/legs disagree -> mark both pending and clear winnerSide.
    let winnerSide: "home" | "away" | null = null;
    if (homeOpt.result === "won" && awayOpt.result === "won") {
      homeOpt.result = "pending";
      awayOpt.result = "pending";
    } else if (homeOpt.result === "pending" || awayOpt.result === "pending") {
      winnerSide = null;
    } else if (homeOpt.result === "won") {
      winnerSide = "home";
    } else if (awayOpt.result === "won") {
      winnerSide = "away";
    }

    const winnerName =
      winnerSide === "home"
        ? inputs.homeTeam
        : winnerSide === "away"
          ? inputs.awayTeam
          : null;

    const hasAnythingToShow =
      homeOpt.pregameProbability !== null ||
      homeOpt.liveProbability !== null ||
      awayOpt.pregameProbability !== null ||
      awayOpt.liveProbability !== null ||
      homeOpt.result !== null ||
      awayOpt.result !== null;
    if (!hasAnythingToShow) return;

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

  const matrixBySet = new Map<
    number,
    { marketName: string; options: RawRecord[] }
  >();
  for (const q of rawMatrixQuestions) {
    const marketName = String(q.market_name ?? q.label ?? "").trim();
    const setNumber = parseSetWinnerNumber(marketName);
    if (setNumber === null) continue;
    const opts = Array.isArray(q.options)
      ? (q.options.map(asRecord).filter(Boolean) as RawRecord[])
      : [];
    if (opts.length === 0) continue;
    const existing = matrixBySet.get(setNumber);
    if (existing) {
      existing.options.push(...opts);
    } else {
      matrixBySet.set(setNumber, { marketName, options: [...opts] });
    }
  }
  for (const [setNumber, group] of matrixBySet.entries()) {
    tryRegisterSetMarket(setNumber, group.marketName, group.options);
  }

  const otherRows = Array.isArray(inputs.gameMarkets?.other)
    ? inputs.gameMarkets!.other
    : [];
  if (otherRows.length > 0) {
    const groupedBySet = new Map<
      number,
      { marketName: string; rows: RawRecord[] }
    >();
    for (const row of otherRows) {
      const r = asRecord(row);
      if (!r) continue;
      const mName = String(r.market_name ?? r.question ?? "").trim();
      const setNumber = mName ? parseSetWinnerNumber(mName) : null;
      if (setNumber === null || bySet.has(setNumber)) continue;
      const existing = groupedBySet.get(setNumber);
      if (existing) {
        existing.rows.push(r);
      } else {
        groupedBySet.set(setNumber, { marketName: mName, rows: [r] });
      }
    }
    for (const [setNumber, group] of groupedBySet.entries()) {
      tryRegisterSetMarket(setNumber, group.marketName, group.rows);
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
  nowMs: number,
): TennisExactScoreCard | null {
  let matchedMarketName: string | null = null;
  const matchedOptions: RawRecord[] = [];

  for (const q of rawMatrixQuestions) {
    const marketName = String(q.market_name ?? q.label ?? "").trim();
    if (!isExactMatchScoreMarketName(marketName)) continue;
    const opts = Array.isArray(q.options)
      ? (q.options.map(asRecord).filter(Boolean) as RawRecord[])
      : [];
    if (opts.length >= 2) {
      if (!matchedMarketName) matchedMarketName = marketName;
      matchedOptions.push(...opts);
    }
  }

  if (!matchedMarketName) {
    const otherRows = Array.isArray(inputs.gameMarkets?.other)
      ? inputs.gameMarkets!.other
      : [];
    for (const row of otherRows) {
      const r = asRecord(row);
      if (!r) continue;
      const mName = String(r.market_name ?? r.question ?? "").trim();
      if (!mName || !isExactMatchScoreMarketName(mName)) continue;
      if (!matchedMarketName) matchedMarketName = mName;
      matchedOptions.push(r);
    }
  }

  if (!matchedMarketName || matchedOptions.length === 0) return null;

  const candidatesByKey = new Map<string, TennisExactScoreOutcome[]>();

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
    const probs = extractRawOptionProbabilities(rawOpt, stage, nowMs);
    const result = extractRawResultState(rawOpt, stage);
    const winnerName =
      parsed.winnerSide === "home" ? inputs.homeTeam : inputs.awayTeam;
    const winnerShort =
      parsed.winnerSide === "home" ? inputs.homeShort : inputs.awayShort;
    const optionKey =
      typeof rawOpt.option_key === "string"
        ? rawOpt.option_key
        : `tennis:exact:${dedupeKey}`;

    const candidate: TennisExactScoreOutcome = {
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
      sourceCount: probs.sourceCount,
      marketName: matchedMarketName,
      marketId: probs.marketId,
      outcomeId: probs.outcomeId,
    };

    const list = candidatesByKey.get(dedupeKey) ?? [];
    list.push(candidate);
    candidatesByKey.set(dedupeKey, list);
  }

  const outcomes: TennisExactScoreOutcome[] = [];
  for (const candidates of candidatesByKey.values()) {
    const deduped = dedupeCandidatesBySource(candidates, (c) => c.source);
    const blended = deduped.find((c) => isServerBlendedSource(c.source));
    const multiUnblended = !blended && deduped.length > 1;
    const chosen = blended ?? deduped[0]!;
    const combinedResult =
      candidates.length > 1
        ? combineCandidateResults(
            candidates.map((c) => c.result),
            stage,
          )
        : chosen.result;

    outcomes.push({
      ...chosen,
      pregameProbability: multiUnblended ? null : chosen.pregameProbability,
      liveProbability: multiUnblended ? null : chosen.liveProbability,
      source: multiUnblended ? null : chosen.source,
      sourceCount: Math.max(chosen.sourceCount, deduped.length),
      result: combinedResult,
    });
  }

  if (outcomes.length < 2) return null;

  // If multiple distinct exact-score outcomes claim "won", venues disagree -> mark conflicting outcomes Pending.
  const wonOutcomes = outcomes.filter((o) => o.result === "won");
  if (wonOutcomes.length > 1) {
    for (const o of wonOutcomes) {
      o.result = "pending";
    }
  }

  const hasVisibleContent = outcomes.some(
    (o) =>
      o.pregameProbability !== null ||
      o.liveProbability !== null ||
      o.result !== null,
  );
  if (!hasVisibleContent) return null;

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
    source: outcomes.find((o) => o.source !== null)?.source ?? null,
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
  nowMs: number,
): LadderCard | null {
  const phase: LadderPhase = stage;
  const byLine = new Map<number, LadderPoint>();

  // 1. Check typed count_threshold questions in game_question_matrix first
  const typedByLine = new Map<
    number,
    Array<{ q: MatrixQuestion; overOpt: MatrixOption }>
  >();
  for (const q of decodedQuestions) {
    if (
      q.typed &&
      q.kind === "count_threshold" &&
      q.subjectSide === "game" &&
      q.periodKey === "full_game" &&
      q.relation === "ge"
    ) {
      const line = q.line ?? (q.bound !== null ? q.bound - 0.5 : null);
      if (line === null) continue;
      const overOpt = q.options.find(
        (o: MatrixOption) =>
          o.side === "over" || /^over\b/i.test(o.label.trim()),
      );
      if (!overOpt) continue;
      const list = typedByLine.get(line) ?? [];
      list.push({ q, overOpt });
      typedByLine.set(line, list);
    }
  }
  for (const [line, candidates] of typedByLine.entries()) {
    const deduped = dedupeCandidatesBySource(
      candidates,
      (c) => c.overOpt.source,
    );
    const blended = deduped.find((c) =>
      isServerBlendedSource(c.overOpt.source),
    );
    const multiUnblended = !blended && deduped.length > 1;
    const chosen = blended ?? deduped[0]!;
    const { q, overOpt } = chosen;
    const rawChance =
      phase === "before"
        ? isRecentQuote(overOpt.observedAt, nowMs)
          ? overOpt.quoted
          : null
        : phase === "during"
          ? overOpt.baseline
          : overOpt.reading;
    const rawNow =
      phase === "during" && isRecentQuote(overOpt.observedAt, nowMs)
        ? overOpt.quoted
        : null;
    const chance = multiUnblended ? null : rawChance;
    const now = multiUnblended ? null : rawNow;
    const source = multiUnblended ? null : overOpt.source;

    const hasWon = candidates.some((c) => c.overOpt.result === true);
    const hasLost = candidates.some((c) => c.overOpt.result === false);
    const result =
      phase === "after" && !(hasWon && hasLost) ? overOpt.result : null;

    byLine.set(line, {
      optionKey: overOpt.optionKey,
      x: line,
      label: `Over ${line} games`,
      side: "game",
      chance,
      now,
      observedAt: overOpt.observedAt,
      result,
      detail: {
        detail: "option",
        label: overOpt.label || q.label,
        marketName: q.marketName,
        source,
        sourceCount: deduped.length,
        quoted: multiUnblended ? null : overOpt.quoted,
        observedAt: overOpt.observedAt,
        baseline:
          multiUnblended
            ? null
            : phase === "after"
              ? overOpt.reading
              : overOpt.baseline,
        baselineObservedAt:
          phase === "after"
            ? overOpt.readingObservedAt
            : overOpt.baselineObservedAt,
        result,
      },
    });
  }

  // 2. Check untyped `Match O/U X.5` questions in raw game_question_matrix (explicit Over only; never invert Under)
  const untypedByLine = new Map<
    number,
    Array<{ marketName: string; overRaw: RawRecord }>
  >();
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
    if (!overRaw) continue;
    const list = untypedByLine.get(line) ?? [];
    list.push({ marketName, overRaw });
    untypedByLine.set(line, list);
  }
  for (const [line, candidates] of untypedByLine.entries()) {
    const extracted = candidates.map((c) => ({
      ...c,
      probs: extractRawOptionProbabilities(c.overRaw, stage, nowMs),
      rawRes: extractRawResultState(c.overRaw, stage),
    }));
    const deduped = dedupeCandidatesBySource(extracted, (c) => c.probs.source);
    const blended = deduped.find((c) =>
      isServerBlendedSource(c.probs.source),
    );
    const multiUnblended = !blended && deduped.length > 1;
    const chosen = blended ?? deduped[0]!;
    const chance = multiUnblended ? null : chosen.probs.pregameProbability;
    const now = multiUnblended ? null : chosen.probs.liveProbability;
    const source = multiUnblended ? null : chosen.probs.source;

    const combinedRes =
      extracted.length > 1
        ? combineCandidateResults(
            extracted.map((c) => c.rawRes),
            stage,
          )
        : chosen.rawRes;
    const result =
      stage === "after" && (combinedRes === "won" || combinedRes === "lost")
        ? combinedRes === "won"
        : null;

    const optionKey =
      typeof chosen.overRaw.option_key === "string"
        ? chosen.overRaw.option_key
        : `tennis:total:${line}`;

    byLine.set(line, {
      optionKey,
      x: line,
      label: `Over ${line} games`,
      side: "game",
      chance,
      now,
      observedAt: chosen.probs.observedAt,
      result,
      detail: {
        detail: "option",
        label: `Over ${line} games`,
        marketName: chosen.marketName,
        source,
        sourceCount: Math.max(chosen.probs.sourceCount, deduped.length),
        quoted: now ?? (stage === "before" ? chance : null),
        observedAt: chosen.probs.observedAt,
        baseline: chance,
        baselineObservedAt: chosen.probs.pregameObservedAt,
        result,
      },
    });
  }

  // 3. Fallback to gameMarkets.totals for Match O/U rows
  const totalsRows = Array.isArray(inputs.gameMarkets?.totals)
    ? inputs.gameMarkets!.totals
    : [];
  const totalsByLine = new Map<number, RawRecord[]>();
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
    const outcomeName = String(r.outcome_name ?? "Over").trim();
    const isUnderRow = /^under\b/i.test(outcomeName);
    if (isUnderRow && r.over_probability === undefined) continue;
    const list = totalsByLine.get(threshold) ?? [];
    list.push(r);
    totalsByLine.set(threshold, list);
  }

  for (const [threshold, candidates] of totalsByLine.entries()) {
    const deduped = dedupeCandidatesBySource(candidates, (c) =>
      typeof c.source === "string" ? c.source : null,
    );
    const blended = deduped.find((c) =>
      isServerBlendedSource(typeof c.source === "string" ? c.source : null),
    );
    const multiUnblended = !blended && deduped.length > 1;
    const chosen = blended ?? deduped[0]!;
    const marketName = String(chosen.market_name ?? "").trim();
    const observedAt = asIso(chosen.observed_at);
    const overProb = asProb(chosen.over_probability ?? chosen.probability);
    const isSettled =
      Boolean(chosen.resolution_source) ||
      typeof chosen.is_winner === "boolean";

    const verdicts = candidates.map((c) => {
      const outcomeName = String(c.outcome_name ?? "Over").trim();
      const isUnderRow = /^under\b/i.test(outcomeName);
      const v = outcomeRowVerdict(
        {
          is_winner: typeof c.is_winner === "boolean" ? c.is_winner : null,
          resolution_source:
            c.resolution_source === null
              ? null
              : typeof c.resolution_source === "string"
                ? c.resolution_source
                : undefined,
        },
        stage === "after",
      );
      if (v === null) return null;
      return isUnderRow ? v === "lost" : v === "won";
    });
    const hasWon = verdicts.includes(true);
    const hasLost = verdicts.includes(false);
    const result =
      stage === "after" && !(hasWon && hasLost)
        ? hasWon
          ? true
          : hasLost
            ? false
            : null
        : null;

    // #11125 single-contributor contract: never read `opening_probability` on fallback rows.
    const rawChance =
      stage === "before"
        ? !isSettled && isRecentQuote(observedAt, nowMs)
          ? overProb
          : null
        : asProb(chosen.pregame_mark);
    const rawNow =
      stage === "during" && !isSettled && isRecentQuote(observedAt, nowMs)
        ? overProb
        : null;
    const chance = multiUnblended ? null : rawChance;
    const now = multiUnblended ? null : rawNow;
    const source = multiUnblended
      ? null
      : typeof chosen.source === "string"
        ? chosen.source
        : null;
    const optionKey = `tennis:total:${threshold}`;

    byLine.set(threshold, {
      optionKey,
      x: threshold,
      label: `Over ${threshold} games`,
      side: "game",
      chance,
      now,
      observedAt,
      result,
      detail: {
        detail: "option",
        label: `Over ${threshold} games`,
        marketName: marketName || `Match O/U ${threshold}`,
        source,
        sourceCount: deduped.length,
        quoted: now ?? (stage === "before" ? chance : null),
        observedAt,
        baseline: chance,
        baselineObservedAt: null,
        result,
      },
    });
  }

  const points = [...byLine.values()].sort((a, b) => a.x - b.x);
  if (points.length < 2) return null;

  const hasVisibleContent = points.some(
    (p) => p.chance !== null || p.now !== null || p.result !== null,
  );
  if (!hasVisibleContent) return null;

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

  const nowMs = inputs.nowMs ?? Date.now();
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
    nowMs,
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
    nowMs,
  );
  if (setsCard) cards.push(setsCard);

  const exactScoreCard = buildTennisExactScoreCard(
    normalizedInputs,
    stage,
    rawMatrixQuestions,
    nowMs,
  );
  if (exactScoreCard) cards.push(exactScoreCard);

  const totalGamesCard = buildTennisTotalGamesCard(
    normalizedInputs,
    stage,
    decodedQuestions,
    rawMatrixQuestions,
    nowMs,
  );
  if (totalGamesCard) cards.push(totalGamesCard);

  return cards;
}
