/**
 * #9483 — the NBA page's game-story cards on web (design freeze v328,
 * `nfl-web-nba-adoption-v328/NBA-MAPPING.md`): the scoring-expectations card
 * (one dot per full-game total line) and the winning-margin card (one dot per
 * team "wins by over N" line on a signed axis), beside the projected finish
 * the NFL slice already draws.
 *
 * READ FROM THE SERVED QUESTION MATRIX (`game_question_matrix`, contract
 * `10238.v1`) — the producer's typing is the authority, nothing is
 * reclassified here. Only typed, full-game, own-side options are drawn; every
 * other original stays in the catalog.
 *
 * WHICH NUMBER A DOT IS (Root's selected fallback, 10/15):
 * - before tip-off: the option's published value, only when `quoted` and its
 *   clock is recent — that price IS the pregame chance;
 * - once play starts: the producer's admitted pregame pin
 *   (`comparison.state == comparable`, `baseline.basis == pregame_pin`, dated),
 *   never a live or settled price;
 * - after the final: ONLY the producer's `pregame_reading` (contract
 *   `artifacts/authority-9483-pregame-reading/CONTRACT.md`, PR #11125) — the
 *   option's own stored pin, admitted by the same pregame clock rule, served
 *   on settled options where `comparison` says `not_quoted`. It counts only
 *   when every field is whole and its outcome is the option's single
 *   contributor; anything else (an older server, `unavailable`, a basis or
 *   clock this does not know) leaves the line's pregame chance unavailable.
 *   Never the terminal 0/100, `source_evidence`, a complement or movement.
 * Results are the producer's `result.state`, shown only on a finished page.
 */

import { isFinishedStatus } from "./eventState";
import { isRecentQuote } from "./nflEventCardDeck";

export const NBA_SPORT_KEY = "basketball_nba";
export const MATRIX_CONTRACT = "10238.v1";

export function nbaCardsApply(sportKey: string | null | undefined): boolean {
  return sportKey === NBA_SPORT_KEY;
}

/** A ladder needs this many lines to be a shape rather than a list. */
export const MIN_LADDER_LINES = 3;

// ─── A narrow, lenient decoder for the fields the cards read ───────────────

export interface MatrixOption {
  optionKey: string;
  label: string;
  side: string | null;
  source: string | null;
  /** The published value, only when `quoted` and a probability. */
  quoted: number | null;
  valueState: string | null;
  observedAt: string | null;
  /** The admitted pregame pin, or null. */
  baseline: number | null;
  baselineObservedAt: string | null;
  comparisonReason: string | null;
  /** The producer's settled-safe pregame reading, only when fully valid (see `admittedReading`). */
  reading: number | null;
  readingObservedAt: string | null;
  /** `won` → true, `lost` → false, anything else → null. */
  result: boolean | null;
}

export interface MatrixQuestion {
  questionKey: string;
  kind: string;
  label: string;
  marketName: string;
  quantityKey: string | null;
  periodKey: string | null;
  subjectSide: string | null;
  subjectLabel: string | null;
  relation: string | null;
  bound: number | null;
  line: number | null;
  typed: boolean;
  options: MatrixOption[];
}

type Raw = Record<string, unknown>;
const obj = (v: unknown): Raw | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Raw) : null);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const prob = (v: unknown): number | null => {
  const n = num(v);
  return n !== null && n >= 0 && n <= 1 ? n : null;
};

const isoClock = (v: unknown): string | null => {
  const s = str(v);
  return s !== null && !Number.isNaN(Date.parse(s)) ? s : null;
};

/**
 * `pregame_reading`, only when it is whole: `available`, no reason, basis
 * `pregame_pin`, a probability strictly inside (0, 1), a readable clock, on a
 * quoted or result option whose ONE contributor is the reading's outcome.
 * Everything else is unavailable — it is never repaired from other fields.
 */
function admittedReading(o: Raw, valueState: string | null): { probability: number; observedAt: string } | null {
  const r = obj(o.pregame_reading);
  if (!r || r.state !== "available" || (r.reason !== null && r.reason !== undefined) || r.basis !== "pregame_pin") return null;
  if (valueState !== "quoted" && valueState !== "result") return null;
  const probability = num(r.probability);
  if (probability === null || !(probability > 0 && probability < 1)) return null;
  const observedAt = isoClock(r.observed_at);
  if (observedAt === null) return null;
  const outcome = r.outcome_id;
  const contributors = o.contributor_outcome_ids;
  if (!Number.isInteger(outcome) || !Array.isArray(contributors) || contributors.length !== 1 || contributors[0] !== outcome) return null;
  return { probability, observedAt };
}

function decodeOption(raw: unknown): MatrixOption | null {
  const o = obj(raw);
  const key = str(o?.option_key);
  if (!o || !key) return null;
  const published = obj(o.published) ?? {};
  const comparison = obj(o.comparison) ?? {};
  const baseline = obj(comparison.baseline);
  const result = str(obj(o.result)?.state);
  const valueState = str(published.value_state);
  const pinned =
    comparison.state === "comparable" &&
    baseline?.basis === "pregame_pin" &&
    prob(baseline?.probability) !== null &&
    !!str(baseline?.observed_at);
  const reading = admittedReading(o, valueState);
  return {
    optionKey: key,
    label: str(o.label) ?? "",
    side: str(o.side),
    source: str(published.source),
    quoted: valueState === "quoted" ? prob(published.value) : null,
    valueState,
    observedAt: str(published.observed_at),
    baseline: pinned ? prob(baseline!.probability) : null,
    baselineObservedAt: pinned ? str(baseline!.observed_at) : null,
    comparisonReason: str(comparison.reason),
    reading: reading?.probability ?? null,
    readingObservedAt: reading?.observedAt ?? null,
    result: result === "won" ? true : result === "lost" ? false : null,
  };
}

/** The matrix's questions, or none when the contract is not the one this reads. */
export function decodeQuestionMatrix(raw: unknown): MatrixQuestion[] {
  const m = obj(raw);
  if (!m || m.contract !== MATRIX_CONTRACT || !Array.isArray(m.questions)) return [];
  const out: MatrixQuestion[] = [];
  for (const rq of m.questions) {
    const q = obj(rq);
    const key = str(q?.question_key);
    const kind = str(q?.kind);
    if (!q || !key || !kind) continue;
    const predicate = obj(q.predicate) ?? {};
    out.push({
      questionKey: key,
      kind,
      label: str(q.label) ?? "",
      marketName: str(q.market_name) ?? "",
      quantityKey: str(obj(q.quantity)?.key),
      periodKey: str(obj(q.period)?.key),
      subjectSide: str(obj(q.subject)?.side),
      subjectLabel: str(obj(q.subject)?.label),
      relation: str(predicate.relation),
      bound: num(predicate.bound),
      line: num(predicate.line),
      typed: obj(q.typing)?.state === "typed",
      options: (Array.isArray(q.options) ? q.options : []).map(decodeOption).filter((x): x is MatrixOption => x !== null),
    });
  }
  return out;
}

// ─── The ladder cards ──────────────────────────────────────────────────────

export type LadderFamily = "total" | "margin";
export type LadderPhase = "before" | "during" | "after";
export type LadderSide = "game" | "home" | "away";

/** The exact original behind a dot, frozen with the card for Details. */
export interface OptionDetail {
  detail: "option";
  label: string;
  marketName: string;
  source: string | null;
  quoted: number | null;
  observedAt: string | null;
  baseline: number | null;
  baselineObservedAt: string | null;
  result: boolean | null;
}

export interface LadderPoint {
  optionKey: string;
  /** Total: the line. Margin: the home side's margin (home wins by over N → +N, away → −N). */
  x: number;
  /** "Over 205.5", "Knicks by 3+". */
  label: string;
  side: LadderSide;
  /** The chance this card draws (see the module note), or null. */
  chance: number | null;
  /** The quote's clock while the chance is a current price (before tip-off), so it can expire. */
  observedAt: string | null;
  /** During play: the current quote beside the drawn pregame pin, or null. */
  now: number | null;
  /** The producer's verdict, finished pages only. */
  result: boolean | null;
  detail: OptionDetail;
}

export interface LadderCard {
  kind: "ladder";
  id: "total" | "margin";
  family: LadderFamily;
  phase: LadderPhase;
  points: LadderPoint[];
  /** Total (home + away) or home margin (home − away) from the page's score; null before play. */
  actual: number | null;
  /** The pregame projection on the same axis (same-book projected pair), or null. */
  forecast: number | null;
  awayShort: string;
  homeShort: string;
}

function phaseOf(status: string | null | undefined, commenceMs: number | null, nowMs: number): LadderPhase {
  if (isFinishedStatus(status)) return "after";
  if (status === "live" || commenceMs === null || commenceMs <= nowMs) return "during";
  return "before";
}

function pointChance(o: MatrixOption, phase: LadderPhase, nowMs: number): { chance: number | null; observedAt: string | null; now: number | null } {
  if (phase === "before") {
    const recent = o.quoted !== null && isRecentQuote(o.observedAt, nowMs);
    return { chance: recent ? o.quoted : null, observedAt: o.observedAt, now: null };
  }
  // A settled card reads the producer's pregame reading and nothing else.
  if (phase === "after") return { chance: o.reading, observedAt: null, now: null };
  const now = o.quoted !== null && isRecentQuote(o.observedAt, nowMs) ? o.quoted : null;
  return { chance: o.baseline, observedAt: null, now };
}

function detailOf(q: MatrixQuestion, o: MatrixOption, phase: LadderPhase): OptionDetail {
  const settled = phase === "after";
  return {
    detail: "option",
    label: o.label || q.label,
    marketName: q.marketName,
    source: o.source,
    quoted: o.quoted,
    observedAt: o.observedAt,
    baseline: settled ? o.reading : o.baseline,
    baselineObservedAt: settled ? o.readingObservedAt : o.baselineObservedAt,
    result: o.result,
  };
}

export interface LadderInputs {
  questions: MatrixQuestion[];
  status: string | null | undefined;
  commenceTime: string | null | undefined;
  homeScore: number | null;
  awayScore: number | null;
  /** The projected finish's pregame pair, when the page draws one. */
  pregameProjection: { home: number; away: number } | null;
  homeShort: string;
  awayShort: string;
  nowMs: number;
}

function commenceMs(iso: string | null | undefined): number | null {
  if (typeof iso !== "string") return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

function scored(i: LadderInputs, phase: LadderPhase): { home: number; away: number } | null {
  if (phase === "before" || i.homeScore === null || i.awayScore === null) return null;
  return { home: i.homeScore, away: i.awayScore };
}

/** The full-game total-points ladder, or null with fewer than three typed lines. */
export function totalLadderCard(i: LadderInputs): LadderCard | null {
  const phase = phaseOf(i.status, commenceMs(i.commenceTime), i.nowMs);
  const points: LadderPoint[] = [];
  for (const q of i.questions) {
    if (!q.typed || q.kind !== "count_threshold" || q.quantityKey !== "points" || q.subjectSide !== "game") continue;
    if (q.periodKey !== "full_game" || q.relation !== "ge") continue;
    const line = q.line ?? (q.bound !== null ? q.bound - 0.5 : null);
    if (line === null) continue;
    const own = q.options.filter((o) => o.side === "over");
    if (own.length !== 1) continue;
    const o = own[0];
    points.push({
      optionKey: o.optionKey,
      x: line,
      label: `Over ${line}`,
      side: "game",
      ...pointChance(o, phase, i.nowMs),
      result: phase === "after" ? o.result : null,
      detail: detailOf(q, o, phase),
    });
  }
  return ladder("total", phase, points, i, (s) => s.home + s.away);
}

/**
 * The full-game "wins by over N" ladder on one signed axis: each team's own
 * lines in its own colour, never a complement of the other side.
 */
export function marginLadderCard(i: LadderInputs): LadderCard | null {
  const phase = phaseOf(i.status, commenceMs(i.commenceTime), i.nowMs);
  const points: LadderPoint[] = [];
  for (const q of i.questions) {
    if (!q.typed || q.kind !== "signed_handicap" || q.quantityKey !== "points" || q.periodKey !== "full_game") continue;
    if (q.relation !== "handicap" || q.line === null || !(q.line < 0)) continue;
    const side = q.subjectSide;
    if (side !== "home" && side !== "away") continue;
    const own = q.options.filter((o) => o.side === side);
    if (own.length !== 1) continue;
    const o = own[0];
    const by = -q.line;
    const team = side === "home" ? i.homeShort : i.awayShort;
    points.push({
      optionKey: o.optionKey,
      x: side === "home" ? by : -by,
      label: `${team} by ${Math.floor(by) + 1}+`,
      side,
      ...pointChance(o, phase, i.nowMs),
      result: phase === "after" ? o.result : null,
      detail: detailOf(q, o, phase),
    });
  }
  return ladder("margin", phase, points, i, (s) => s.home - s.away);
}

function ladder(
  family: LadderFamily,
  phase: LadderPhase,
  points: LadderPoint[],
  i: LadderInputs,
  quantity: (pair: { home: number; away: number }) => number,
): LadderCard | null {
  const unique = new Map<number, LadderPoint>();
  for (const p of points) if (!unique.has(p.x)) unique.set(p.x, p);
  // Two options on one line on one axis would be two prices for one dot: refuse the line.
  const counts = new Map<number, number>();
  for (const p of points) counts.set(p.x, (counts.get(p.x) ?? 0) + 1);
  const kept = [...unique.values()].filter((p) => counts.get(p.x) === 1).sort((a, b) => a.x - b.x);
  if (kept.length < MIN_LADDER_LINES) return null;
  const score = scored(i, phase);
  return {
    kind: "ladder",
    id: family,
    family,
    phase,
    points: kept,
    actual: score ? quantity(score) : null,
    forecast: i.pregameProjection ? Math.round(quantity(i.pregameProjection) * 10) / 10 : null,
    awayShort: i.awayShort,
    homeShort: i.homeShort,
  };
}

/** What the card calls the drawn number, by phase. */
export function ladderCaption(card: LadderCard): string {
  const what = card.family === "total" ? "finishing above each line" : "winning by more than each margin";
  if (card.phase === "before") return `Pregame chance of ${what}`;
  if (card.points.some((p) => p.chance !== null)) return `Chance before tip-off of ${what}`;
  return "Pregame chance unavailable for these lines";
}

export function ladderTitle(card: LadderCard): string {
  return card.family === "total" ? "Scoring expectations" : "Winning margin";
}

/** The signed margin in words: "Knicks by 3", "Tie". */
export function marginWords(card: LadderCard, value: number): string {
  if (value === 0) return "Tie";
  const team = value > 0 ? card.homeShort : card.awayShort;
  const n = Math.abs(value);
  return `${team} by ${Math.round(n) === n ? n : n.toFixed(1)}`;
}

/** The default point: the drawn line nearest even odds; with none drawn, the line nearest the actual. */
export function defaultLadderIndex(card: LadderCard): number | null {
  let best: { index: number; distance: number } | null = null;
  card.points.forEach((p, index) => {
    if (p.chance === null) return;
    const distance = Math.abs(p.chance - 0.5);
    if (best === null || distance < best.distance) best = { index, distance };
  });
  if (best !== null) return (best as { index: number }).index;
  if (card.points.length === 0) return null;
  // Nothing drawn (a final with no admitted pin): open on the line nearest what happened.
  if (card.actual !== null) {
    let near = 0;
    card.points.forEach((p, index) => {
      if (Math.abs(p.x - card.actual!) < Math.abs(card.points[near].x - card.actual!)) near = index;
    });
    return near;
  }
  return Math.floor(card.points.length / 2);
}
