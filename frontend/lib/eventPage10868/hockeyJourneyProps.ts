/**
 * #10868 — THE HOCKEY JOURNEY SCREEN (web), PARTS THREE AND FOUR: THE PLAYER
 * POINTS AND ASSISTS STORIES, AND "ALL PROPS".
 *
 * PILLARS: FORMATTING / TRUTH. SHIP: on `nhl-journey` the points card (columns)
 * and the assists card (bars) print, for each player and milestone, exactly the
 * pregame chance, in-game reading, count and result the native screen prints;
 * and "All props" lists every original the page's catalogue lists, once each,
 * with its own pregame chance, later reading and venue grade.
 *
 * The web port of native `HockeyJourneyContributionAdapter10868` and
 * `HockeyJourneyOriginalsAdapter10868` (their headers carry the full rules).
 * Web authorities used, and native rules mirrored where web has none:
 *
 *   - subject / team rows   `propSubjectDisplay` (playerPropsGrouping.ts:234),
 *                           `isTeamSubject` (nflEventCardDeck.ts), the subject
 *                           before the outcome's first colon.
 *   - stat                  `statFamily(statLabel(...))` (nflEventCardDeck.ts),
 *                           web's twin of native `PlayerPropsFamily.name(
 *                           PlayerPropsStatLabel.display(...))`.
 *   - over side             the catalogue's / milestone cards' side rule
 *                           (`propOutcomeSide` + the Over/Under words; both web
 *                           copies are private, so it is restated once here).
 *   - pregame bases         `milestoneCards`' two bases (nflEventCardDeck.ts):
 *                           before the start the quote's own `over_probability`
 *                           while `isRecentQuote` finds its own `observed_at`
 *                           recent; once started (live, finished, or the clock
 *                           past the listed start) the served `pregame_mark` and
 *                           nothing else. A flat ladder is no price (native
 *                           `PlayerPropsPricing.isPricedLadder`, #5137).
 *   - in-game reading       during play only: `catalogQuote` (questionCatalog.ts,
 *                           the All markets live rule) on the row's own clock;
 *                           a settled row is never a chance; no movement printed.
 *   - counts                the per-player box the page already holds
 *                           (`event.box_score_data.players`), exact normalised
 *                           name identity, fail closed (native
 *                           `PlayerPropsCardView.actualStatValue`). Points are
 *                           goals + assists, the server's own definition.
 *   - result / grade        after the final only, from the served settlement:
 *                           `servedSettlement` (is_winner + an authoritative
 *                           resolution_source). Unknown is not loss; a settlement
 *                           the box count or the served `hit` contradicts is
 *                           unconfirmed.
 *   - target, default       `targetLabel` and `defaultRungIndex`
 *                           (nflEventCardDeck.ts): nearest even odds, ties low.
 *   - order                 native `PlayerPropsOrder.cardPrecedes`: printed rungs,
 *                           then top printed chance, then name.
 *   - catalogue             `buildQuestionCatalog` (questionCatalog.ts:113) —
 *                           membership and order; each listed outcome is mapped
 *                           back to its served row by the catalogue's own keys.
 *   - words                 `formatProbabilityPercent`, `sourceLabel`,
 *                           `teamShortNames`, `clockWords` (formatSourceStamp).
 *   - original, later       during play only, always the CURRENT slot (native
 *                           `HockeyJourneyOriginalsAdapter10868.laterReading`).
 *                           It holds the catalogue's admitted price only as the
 *                           contribution card admits an in-game reading
 *                           (`inGameReading` below), in its order: dated,
 *                           observed at or after the listed start
 *                           (`commence_time`), not stale, recent
 *                           (`isRecentQuote`). Undated or stale is "No recent
 *                           probability update"; from before the start, "No in-game
 *                           reading". The quote it refuses — a stale one read by
 *                           `catalogQuote` at its own observation instant — is
 *                           never a headline figure: it is the Details' historical
 *                           quote with its own clock and venue ("Last recorded
 *                           probability (historical)", native's shared label; web
 *                           has no equivalent). No quote is the catalogue's
 *                           absence words. A row the venue already settled shows
 *                           no chance and keeps no quote (never a saved 0/1).
 *
 * PURE: no fetch, no subscription, no timer. `nowMs` is a parameter.
 */

import type { GameMarketsResponse } from "@/lib/api";
import type { EventDetailResponse } from "@/lib/types";
import { propSubjectDisplay } from "@/lib/playerPropsGrouping";
import {
  defaultRungIndex,
  isRecentQuote,
  isTeamSubject,
  statFamily,
  statLabel,
  targetLabel,
  type MilestoneCard,
  type MilestoneRung,
} from "@/lib/nflEventCardDeck";
import { propOutcomeSide } from "@/lib/propOutcomeSide";
import { buildQuestionCatalog, catalogQuote, type CatalogGroup, type CatalogOutcome } from "@/lib/questionCatalog";
import { isFinishedStatus } from "@/lib/eventState";
import { isPregameStatus } from "@/lib/settledQuote";
import { sourceIsStale } from "@/lib/sourceAge";
import { sourceLabel } from "@/lib/sourceLabels";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { propVerdictLabel } from "@/lib/propGrade";
import { teamShortNames } from "@/lib/teamShortName";
import {
  admissible,
  clockWords,
  hockeyJourneyPhase,
  joined,
  parseMs,
  servedSettlement,
  type HockeyJourneyPhase,
} from "./hockeyJourneyCore";

// ─── Shared ────────────────────────────────────────────────────────────────

/** One served market row, as much of it as these parts read. */
export interface HockeyJourneyMarketRow {
  market_name?: string | null;
  outcome_name?: string | null;
  threshold?: number | null;
  probability?: number | null;
  over_probability?: number | null;
  source?: string | null;
  period?: string | null;
  observed_at?: string | null;
  _inverted?: boolean | null;
  _market_id?: number | null;
  _market_ids?: number[] | null;
  contributor_outcome_ids?: number[] | null;
  is_winner?: boolean | null;
  resolution_source?: string | null;
  market_type?: string | null;
  pregame_mark?: number | null;
  hit?: boolean | null;
  player_team?: string | null;
}

/** Which side of the line an outcome names (gotcha #17). */
function lineSide(row: HockeyJourneyMarketRow): "over" | "under" | "unreadable" {
  if (row._inverted === true) return "under";
  const side = propOutcomeSide(row.outcome_name);
  if (side !== "unreadable") return side;
  const o = row.outcome_name ?? "";
  if (/\bunder\b/i.test(o)) return "under";
  if (/\bover\b/i.test(o)) return "over";
  return "unreadable";
}

/** Live, finished, or the clock past the listed start (a missing start counts as started). */
export function propsHaveStarted(event: EventDetailResponse, nowMs: number): boolean {
  const start = parseMs(event.commence_time);
  return event.status === "live" || isFinishedStatus(event.status) || start === null || start <= nowMs;
}

/** The served subject before the outcome's first colon; null when it names none. */
export function propSubject(outcomeName: string | null | undefined): string | null {
  const o = outcomeName ?? "";
  const colon = o.indexOf(":");
  if (colon < 0) return null;
  const name = propSubjectDisplay(o.slice(0, colon).trim());
  return name ? name : null;
}

/** Native `PlayerPropsCardView.normalizedPlayerName`: lowercase, no periods/commas, single spaces. */
export function normalizedPlayerName(raw: string): string {
  return raw.toLowerCase().replace(/[.,]/g, "").split(/\s+/).filter(Boolean).join(" ");
}

export function playerId(subject: string): string {
  return `player:${normalizedPlayerName(subject)}`;
}

/** One source record: the venue, then the row id `market_name-outcome_name`. */
export function milestoneId(row: HockeyJourneyMarketRow): string {
  return `${row.source ?? ""}|${row.market_name ?? ""}-${row.outcome_name ?? ""}`;
}

/**
 * Settlement of a player-prop row after the final, refused when the box count
 * (by the props card's own verdict, count ≥ line) or the served `hit` disagrees.
 */
export function propContractResult(
  row: HockeyJourneyMarketRow,
  count: number | null,
  threshold: number,
): "reached" | "missed" | "unconfirmed" {
  const won = servedSettlement(row.is_winner, row.resolution_source);
  if (won === null) return "unconfirmed";
  if (count !== null && (count >= threshold) !== won) return "unconfirmed";
  if (typeof row.hit === "boolean" && row.hit !== won) return "unconfirmed";
  return won ? "reached" : "missed";
}

// ─── Part three: points and assists ────────────────────────────────────────

export type HockeyJourneyStat = "points" | "assists";

export const CONTRIBUTION_WORDS = {
  pointsEyebrow: "PLAYER POINTS",
  assistsEyebrow: "PLAYER ASSISTS",
  pointsTitle: "Points in context",
  assistsTitle: "Who creates the goals?",
  pointsDefinition: "One point for each goal or assist.",
  assistsDefinition: "An assist credits a player who helped create a goal.",
  chartTitle: "Pregame chances · at least this many",
  unavailable: "Unavailable",
  notPriced: "No probability",
  noRecentUpdate: "No recent probability update",
  noInGameReading: "No in-game reading",
  reachedSoFar: "Reached so far",
  milestoneReachedSoFar: "Milestone reached so far",
  unconfirmed: "Result unconfirmed",
  countUnavailable: "Count unavailable",
  finalCountUnavailable: "Final count unavailable",
  savedBeforeStart: "saved before the start",
  boxSoFar: "box score · update time not served",
  boxFinal: "box score after the final",
  timingSuffix: "probability timing",
  pregameTitle: "Pregame chance",
  recordedTitle: "Recorded in-game",
  currentStatusTitle: "In-game chance",
  actualSoFarTitle: "Actual so far",
  resultTitle: "Final result",
  countSoFarTitle: "Count so far",
  finalCountTitle: "Final count",
  /** Native `PlayerContributionInput10868.playerUnavailable` / `.milestoneUnavailable`. */
  playerUnavailable: "Selected player unavailable.",
  milestoneUnavailable: "Selected milestone unavailable.",
} as const;

export interface HockeyJourneyObservation {
  probability: number;
  text: string;
  /** Clock and venue words for the timing details. */
  detail: string;
}

export type HockeyJourneyCurrent =
  | { kind: "recorded"; observation: HockeyJourneyObservation }
  | { kind: "unavailable"; words: string }
  | { kind: "withheld"; words: string }
  | { kind: "reached"; words: string };

export interface HockeyJourneyResult {
  kind: "reached" | "missed" | "unconfirmed";
  words: string;
}

export interface HockeyJourneyMilestone {
  id: string;
  threshold: number;
  target: string;
  title: string;
  before: HockeyJourneyObservation | null;
  beforeMissing: string;
  /** During play only. */
  current: HockeyJourneyCurrent | null;
  /** During play, with a box count only. */
  progress: { status: string; fraction: number | null } | null;
  /** After the final only. */
  result: HockeyJourneyResult | null;
  timingTitle: string;
  timing: string[];
}

export type HockeyJourneyActual =
  | { kind: "count"; count: string; unit: string; breakdown: string | null; detail: string }
  | { kind: "unavailable"; words: string };

export interface HockeyJourneyPlayer {
  id: string;
  name: string;
  /** The team's short name, from the first served row that knows; null when none does. */
  team: string | null;
  milestones: HockeyJourneyMilestone[];
  actual: HockeyJourneyActual;
  /** Nearest even odds over printed pregame chances, ties low; null when none print. */
  defaultMilestoneId: string | null;
}

export interface HockeyJourneyContribution {
  stat: HockeyJourneyStat;
  phase: HockeyJourneyPhase;
  orientation: "columns" | "bars";
  eyebrow: string;
  title: string;
  definition: string;
  chartTitle: string;
  ticks: Array<{ p: number; label: string }>;
  /** In the props card's order. The first is shown when nothing is chosen. */
  players: HockeyJourneyPlayer[];
  /** "Choose player · N" when there is a choice to make. */
  chooserTitle: string | null;
  /**
   * The same words for any count, for the one case the chooser must stay
   * reachable with fewer than two players: a held choice that is no longer
   * served.
   */
  chooseLabel: string;
}

/**
 * The reader's own held choice for one story. Null means "not chosen": only
 * then does the card show its first player at that player's default
 * milestone. The page holds it (native host `pointsPlayer`/`pointsMilestone`),
 * so a refresh or a story switch never rewrites it; only a new explicit
 * choice does.
 */
export interface HockeyJourneyHeldChoice {
  playerId: string | null;
  milestoneId: string | null;
}

export const NO_HELD_CHOICE: HockeyJourneyHeldChoice = { playerId: null, milestoneId: null };

export interface HockeyJourneyResolvedChoice {
  /** Null when a held player is no longer served — never another player. */
  player: HockeyJourneyPlayer | null;
  /** The exact held (or, with none held, default) milestone; null when missing or duplicated. */
  selected: HockeyJourneyMilestone | null;
  /** "Selected player unavailable." / "Selected milestone unavailable.", else null. */
  notice: string | null;
}

/**
 * Native `HockeyJourneyContributionAdapter10868.input` + `PlayerContributionInput10868
 * .selection`/`.selectionNotice`: with no choice, the first player at its
 * default milestone; a held player id that no card carries is no player and
 * says so; a held milestone id is resolved exactly — a missing or duplicated id
 * gets no substitute.
 */
export function resolveContributionChoice(
  card: HockeyJourneyContribution,
  held: HockeyJourneyHeldChoice,
): HockeyJourneyResolvedChoice {
  const player =
    held.playerId === null ? (card.players[0] ?? null) : (card.players.find((p) => p.id === held.playerId) ?? null);
  if (!player) return { player: null, selected: null, notice: CONTRIBUTION_WORDS.playerUnavailable };
  const id = held.milestoneId ?? player.defaultMilestoneId;
  if (id === null) return { player, selected: null, notice: null };
  const matches = player.milestones.filter((m) => m.id === id);
  if (matches.length === 1) return { player, selected: matches[0], notice: null };
  return { player, selected: null, notice: CONTRIBUTION_WORDS.milestoneUnavailable };
}

type PlayerProp = GameMarketsResponse["player_props"][number];

export interface HockeyJourneyLadder {
  playerId: string;
  name: string;
  servedSide: string | null;
  rows: HockeyJourneyMarketRow[];
}

/** One ladder per player for `stat`: over-side rows, distinct finite lines, ascending. */
export function contributionLadders(
  stat: HockeyJourneyStat,
  event: EventDetailResponse,
  markets: GameMarketsResponse | null | undefined,
): HockeyJourneyLadder[] {
  const servedSide = new Map<string, string>();
  const order: string[] = [];
  const groups = new Map<string, { playerId: string; name: string; market: string; source: string; rows: HockeyJourneyMarketRow[] }>();
  const teams = [event.home_team, event.away_team];
  for (const prop of (markets?.player_props ?? []) as PlayerProp[]) {
    const row = prop as unknown as HockeyJourneyMarketRow;
    const name = propSubject(row.outcome_name);
    if (!name || isTeamSubject(name, teams)) continue;
    const id = playerId(name);
    // #4919 — the first row that KNOWS, across the player's props.
    if (!servedSide.has(id) && row.player_team) servedSide.set(id, row.player_team);
    const label = statLabel(row.market_name ?? "", event.home_team, event.away_team, name);
    if (statFamily(label).toLowerCase() !== stat) continue;
    const threshold = row.threshold;
    if (typeof threshold !== "number" || !Number.isFinite(threshold) || lineSide(row) !== "over") continue;
    const market = (row.market_name ?? "").trim();
    const source = row.source ?? "";
    const key = [id, market, source].join("\u001f");
    let group = groups.get(key);
    if (!group) {
      group = { playerId: id, name, market, source, rows: [] };
      groups.set(key, group);
      order.push(key);
    }
    // A second row at one line is a duplicate, never a second chance.
    if (group.rows.some((r) => r.threshold === threshold)) continue;
    group.rows.push(row);
  }
  const best = new Map<string, { name: string; market: string; source: string; rows: HockeyJourneyMarketRow[] }>();
  const players: string[] = [];
  for (const key of order) {
    const group = groups.get(key);
    if (!group) continue;
    const held = best.get(group.playerId);
    if (!held) {
      best.set(group.playerId, group);
      players.push(group.playerId);
      continue;
    }
    // The longer ladder, then the market name, then the source (a stable deal).
    const longer = group.rows.length > held.rows.length;
    const sameLength = group.rows.length === held.rows.length;
    if (longer || (sameLength && (group.market < held.market || (group.market === held.market && group.source < held.source)))) {
      best.set(group.playerId, group);
    }
  }
  return players.flatMap((id): HockeyJourneyLadder[] => {
    const group = best.get(id);
    if (!group) return [];
    return [{
      playerId: id,
      name: group.name,
      servedSide: servedSide.get(id) ?? null,
      rows: [...group.rows].sort((a, b) => (a.threshold ?? 0) - (b.threshold ?? 0)),
    }];
  });
}

/** `[name: [stat: value]]`, the per-player box the page already holds, or null. */
export type HockeyJourneyBox = Record<string, Record<string, number>>;

/** `event.box_score_data.players` when it is the per-player box (an object keyed by name). */
export function boxScoreOf(event: EventDetailResponse): HockeyJourneyBox | null {
  const players = (event.box_score_data as { players?: unknown } | undefined)?.players;
  if (!players || typeof players !== "object" || Array.isArray(players)) return null;
  const out: HockeyJourneyBox = {};
  for (const [name, stats] of Object.entries(players as Record<string, unknown>)) {
    if (!stats || typeof stats !== "object" || Array.isArray(stats)) continue;
    const kept: Record<string, number> = {};
    for (const [key, value] of Object.entries(stats as Record<string, unknown>)) {
      if (typeof value === "number" && Number.isFinite(value)) kept[key] = value;
    }
    out[name] = kept;
  }
  return out;
}

/** Exactly one box identity for the player, or no value (fail closed). */
export function boxStat(player: string, stat: "goals" | "assists", box: HockeyJourneyBox | null): number | null {
  if (!box) return null;
  const target = normalizedPlayerName(player);
  if (!target) return null;
  const matches = Object.keys(box).filter((key) => normalizedPlayerName(key) === target);
  if (matches.length !== 1) return null;
  const stats = box[matches[0]];
  const direct = stats[stat];
  if (typeof direct === "number") return direct;
  const alias = stat === "assists" ? stats.ast : undefined;
  return typeof alias === "number" ? alias : null;
}

interface Count {
  total: number;
  goals: number | null;
  assists: number;
}

function countFor(stat: HockeyJourneyStat, name: string, box: HockeyJourneyBox | null): Count | null {
  const assists = boxStat(name, "assists", box);
  if (assists === null || assists < 0) return null;
  if (stat === "assists") return { total: assists, goals: null, assists };
  const goals = boxStat(name, "goals", box);
  if (goals === null || goals < 0) return null;
  return { total: goals + assists, goals, assists };
}

function countWords(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
}

function observation(value: number, detail: string | null): HockeyJourneyObservation {
  return { probability: value, text: formatProbabilityPercent(value), detail: detail ?? "" };
}

/** Native `PlayerPropsPricing.isPricedLadder`: two or more printed chances that all print one percent are no price. */
function isPricedLadder(probabilities: number[]): boolean {
  if (probabilities.length < 2) return true;
  return new Set(probabilities.map((p) => Math.round(p * 100))).size > 1;
}

function pregameReading(
  row: HockeyJourneyMarketRow,
  started: boolean,
  nowMs: number,
): { observation: HockeyJourneyObservation | null; missing: string } {
  const venue = sourceLabel(row.source);
  if (started) {
    const mark = admissible(row.pregame_mark);
    if (mark === null) return { observation: null, missing: CONTRIBUTION_WORDS.unavailable };
    return {
      observation: observation(mark, joined([CONTRIBUTION_WORDS.savedBeforeStart, venue])),
      missing: CONTRIBUTION_WORDS.unavailable,
    };
  }
  const price = admissible(row.over_probability);
  if (price === null) return { observation: null, missing: CONTRIBUTION_WORDS.unavailable };
  if (!isRecentQuote(row.observed_at, nowMs)) return { observation: null, missing: CONTRIBUTION_WORDS.noRecentUpdate };
  return {
    observation: observation(price, joined([`recorded ${clockWords(row.observed_at) ?? ""}`, venue])),
    missing: CONTRIBUTION_WORDS.unavailable,
  };
}

function inGameReading(
  row: HockeyJourneyMarketRow,
  reachedSoFar: boolean,
  event: EventDetailResponse,
  nowMs: number,
): HockeyJourneyCurrent {
  if (reachedSoFar) return { kind: "reached", words: CONTRIBUTION_WORDS.reachedSoFar };
  if (typeof row.is_winner === "boolean" && row.resolution_source) {
    return { kind: "unavailable", words: CONTRIBUTION_WORDS.noInGameReading };
  }
  if (admissible(row.over_probability) === null) return { kind: "unavailable", words: CONTRIBUTION_WORDS.noInGameReading };
  const at = parseMs(row.observed_at);
  if (at === null) return { kind: "withheld", words: CONTRIBUTION_WORDS.noRecentUpdate };
  const start = parseMs(event.commence_time);
  if (start !== null && at < start) return { kind: "unavailable", words: CONTRIBUTION_WORDS.noInGameReading };
  if (!isRecentQuote(row.observed_at, nowMs)) return { kind: "withheld", words: CONTRIBUTION_WORDS.noRecentUpdate };
  const price = admissible(
    catalogQuote(
      {
        market_name: row.market_name,
        outcome_name: row.outcome_name,
        threshold: row.threshold,
        over_probability: row.over_probability,
        source: row.source,
        observed_at: row.observed_at,
        _inverted: row._inverted,
      },
      event.status,
      nowMs,
    ),
  );
  if (price === null) return { kind: "unavailable", words: CONTRIBUTION_WORDS.noInGameReading };
  return {
    kind: "recorded",
    observation: observation(price, joined([`recorded ${clockWords(row.observed_at) ?? ""}`, sourceLabel(row.source)])),
  };
}

function actualSlot(count: Count | null, stat: HockeyJourneyStat, phase: HockeyJourneyPhase): HockeyJourneyActual {
  const unit = (v: number) => (v === 1 ? (stat === "points" ? "point" : "assist") : stat);
  const breakdown = (c: Count): string | null =>
    c.goals === null
      ? null
      : `${countWords(c.goals)} ${c.goals === 1 ? "goal" : "goals"} + ${countWords(c.assists)} ${c.assists === 1 ? "assist" : "assists"}`;
  if (phase === "before") return { kind: "unavailable", words: CONTRIBUTION_WORDS.countUnavailable };
  if (phase === "live") {
    if (!count) return { kind: "unavailable", words: CONTRIBUTION_WORDS.countUnavailable };
    return {
      kind: "count",
      count: countWords(count.total),
      unit: `${unit(count.total)} so far`,
      breakdown: breakdown(count),
      detail: CONTRIBUTION_WORDS.boxSoFar,
    };
  }
  if (!count) return { kind: "unavailable", words: CONTRIBUTION_WORDS.finalCountUnavailable };
  return {
    kind: "count",
    count: countWords(count.total),
    unit: unit(count.total),
    breakdown: breakdown(count),
    detail: CONTRIBUTION_WORDS.boxFinal,
  };
}

function timingLines(
  before: { observation: HockeyJourneyObservation | null; missing: string },
  current: HockeyJourneyCurrent | null,
  actual: HockeyJourneyActual,
  result: HockeyJourneyResult | null,
  row: HockeyJourneyMarketRow,
  phase: HockeyJourneyPhase,
): string[] {
  const W = CONTRIBUTION_WORDS;
  const lines = [`${W.pregameTitle}: ${before.observation ? before.observation.detail : before.missing}`];
  if (phase === "live" && current) {
    if (current.kind === "recorded") lines.push(`${W.recordedTitle}: ${current.observation.detail}`);
    else if (current.kind === "reached") lines.push(`${W.actualSoFarTitle}: ${current.words}`);
    else lines.push(`${W.currentStatusTitle}: ${current.words}`);
  }
  if (phase !== "before") {
    const title = phase === "live" ? W.countSoFarTitle : W.finalCountTitle;
    lines.push(`${title}: ${actual.kind === "count" ? actual.detail : actual.words}`);
  }
  if (phase === "final" && result) {
    const venue = sourceLabel(row.source);
    const settledBy = result.kind !== "unconfirmed" && venue ? `settled by ${venue}` : null;
    lines.push(joined([`${W.resultTitle}: ${result.words}`, settledBy]) ?? result.words);
  }
  return lines;
}

interface BuiltPlayer {
  player: HockeyJourneyPlayer;
  rungs: number;
  top: number;
}

function buildPlayer(
  ladder: HockeyJourneyLadder,
  stat: HockeyJourneyStat,
  event: EventDetailResponse,
  phase: HockeyJourneyPhase,
  box: HockeyJourneyBox | null,
  names: { home: string; away: string },
  nowMs: number,
): BuiltPlayer {
  const started = propsHaveStarted(event, nowMs);
  let pregame = ladder.rows.map((row) => pregameReading(row, started, nowMs));
  // #5137 — a ladder printing one repeated number is not a price.
  const printed = pregame.flatMap((p) => (p.observation ? [p.observation.probability] : []));
  if (!isPricedLadder(printed)) pregame = pregame.map(() => ({ observation: null, missing: CONTRIBUTION_WORDS.notPriced }));
  const count = countFor(stat, ladder.name, box);
  const actual = actualSlot(count, stat, phase);

  const milestones: HockeyJourneyMilestone[] = ladder.rows.map((row, i) => {
    const threshold = row.threshold ?? 0;
    const target = targetLabel(threshold);
    const title = `${target} ${stat}`;
    const before = pregame[i];
    const reached = count !== null && count.total >= threshold;
    const current = phase === "live" ? inGameReading(row, reached, event, nowMs) : null;
    let progress: HockeyJourneyMilestone["progress"] = null;
    if (phase === "live" && count) {
      if (reached) {
        progress = { status: CONTRIBUTION_WORDS.milestoneReachedSoFar, fraction: 1 };
      } else {
        const more = Math.max(1, Math.ceil(threshold - count.total));
        progress = {
          status: `${more} more for ${target}`,
          fraction: threshold > 0 ? Math.min(Math.max(count.total / threshold, 0), 1) : null,
        };
      }
    }
    let result: HockeyJourneyResult | null = null;
    if (phase === "final") {
      const verdict = propContractResult(row, count?.total ?? null, threshold);
      result = {
        kind: verdict,
        // Web's ONE settled prop vocabulary (lib/propGrade.ts): HIT / MISS. Unknown is not loss.
        words: verdict === "unconfirmed" ? CONTRIBUTION_WORDS.unconfirmed : propVerdictLabel(verdict === "reached"),
      };
    }
    return {
      id: milestoneId(row),
      threshold,
      target,
      title,
      before: before.observation,
      beforeMissing: before.missing,
      current,
      progress,
      result,
      timingTitle: `${ladder.name} ${title} · ${CONTRIBUTION_WORDS.timingSuffix}`,
      timing: timingLines(before, current, actual, result, row, phase),
    };
  });

  // The production default: the milestone card's own `defaultRungIndex` over printed chances.
  const card: MilestoneCard = {
    kind: "milestone",
    id: `milestone:${ladder.playerId}`,
    player: ladder.name,
    stat,
    side: "unknown",
    basis: started ? "pregameMark" : "pregamePrice",
    rungs: milestones.map(
      (m): MilestoneRung => ({ threshold: m.threshold, chance: m.before?.probability ?? null, observedAt: null, rowId: m.id, hit: null }),
    ),
    actual: null,
  };
  const defaultIndex = defaultRungIndex(card);
  const chances = milestones.flatMap((m) => (m.before ? [m.before.probability] : []));
  return {
    player: {
      id: ladder.playerId,
      name: ladder.name,
      team: ladder.servedSide === "home" ? names.home : ladder.servedSide === "away" ? names.away : null,
      milestones,
      actual,
      defaultMilestoneId: defaultIndex === null ? null : milestones[defaultIndex].id,
    },
    rungs: chances.length,
    top: chances.length > 0 ? Math.max(...chances) : 0,
  };
}

const CONTRIBUTION_TICKS = [
  { p: 0, label: "0%" },
  { p: 0.5, label: "50%" },
  { p: 1, label: "100%" },
];

/** The story card for `stat`, or null when no player has a ladder for it. */
export function hockeyJourneyContribution(
  stat: HockeyJourneyStat,
  event: EventDetailResponse,
  markets: GameMarketsResponse | null | undefined,
  nowMs: number,
): HockeyJourneyContribution | null {
  const phase = hockeyJourneyPhase(event, nowMs);
  const ladders = contributionLadders(stat, event, markets);
  if (ladders.length === 0) return null;
  const box = boxScoreOf(event);
  const names = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );
  const built = ladders
    .map((ladder) => buildPlayer(ladder, stat, event, phase, box, names, nowMs))
    .sort((a, b) => {
      if (a.rungs !== b.rungs) return b.rungs - a.rungs;
      if (a.top !== b.top) return b.top - a.top;
      return a.player.name < b.player.name ? -1 : a.player.name > b.player.name ? 1 : 0;
    })
    .map((b) => b.player);
  const W = CONTRIBUTION_WORDS;
  return {
    stat,
    phase,
    orientation: stat === "points" ? "columns" : "bars",
    eyebrow: stat === "points" ? W.pointsEyebrow : W.assistsEyebrow,
    title: stat === "points" ? W.pointsTitle : W.assistsTitle,
    definition: stat === "points" ? W.pointsDefinition : W.assistsDefinition,
    chartTitle: W.chartTitle,
    ticks: CONTRIBUTION_TICKS,
    players: built,
    chooserTitle: built.length < 2 ? null : `Choose player · ${built.length}`,
    chooseLabel: `Choose player · ${built.length}`,
  };
}

// ─── Part four: All props ──────────────────────────────────────────────────

export const ORIGINALS_WORDS = {
  heading: "All props",
  emptyWords: "No retained originals for this game",
  noPregameChance: "No pregame chance",
  savedBeforeStart: "Saved before the start",
  recorded: "Recorded",
  noCurrentChance: "No current chance",
  notYetConfirmed: "Not yet confirmed",
  noSettlement: "No settlement served",
  disputed: "Served settlement and grade disagree",
  rulesUnavailable: "Rules unavailable",
  marketId: "Market ID",
  outcomeId: "Outcome ID",
  unattributed: "unattributed",
  noRecentPrice: "No recent probability update",
  periodFinished: "Period finished",
  unavailablePrice: "Probability unavailable",
  pregameLabel: "Pregame chance",
  currentLabel: "Current chance",
  resultLabel: "Result",
  /** Native `OriginalMarketDetails9483.historicalLabel`; web has no shared equivalent. */
  historicalLabel: "Last recorded probability (historical)",
  historicalRecorded: "recorded",
  historicalTimeUnknown: "time unknown",
} as const;

export interface HockeyJourneyOriginalIdentity {
  source: string;
  market: string;
  side: string;
}

export type HockeyJourneyOriginalReading =
  | { kind: "value"; text: string; placement: number; provenance: string | null }
  | { kind: "missing"; words: string };

/**
 * The quote a refused current slot keeps: explicitly historical, separately
 * dated, never a current chance. Native `OriginalMarketDetails9483.HistoricalQuote`
 * plus the row it prints ("69%, recorded 30 Oct, 10:05 PM · Kalshi").
 */
export interface HockeyJourneyHistoricalQuote {
  text: string;
  /** "<clock> · <venue>", or null when the quote is undated. */
  recorded: string | null;
  label: string;
  value: string;
}

export interface HockeyJourneyOriginal {
  /** `source|market|side`, unique per original. */
  key: string;
  identity: HockeyJourneyOriginalIdentity;
  /** The catalogue's question (the served market text). */
  title: string;
  /** The catalogue's outcome label. */
  outcome: string;
  /** "Kirill Kaprizov 2+ points" for a player prop ladder rung, else the outcome. */
  label: string;
  family: string;
  mode: "pregame" | "current" | "result";
  pregame: HockeyJourneyOriginalReading;
  /** During play only: the current slot, a value only when admitted as current. */
  later: HockeyJourneyOriginalReading | null;
  /** After the final only. */
  /**
   * After the final only. `hit` is the admitted verdict (null when unconfirmed);
   * `words` spells it in web's one settled vocabulary (`propVerdictLabel`: HIT /
   * MISS) or says why there is none.
   */
  grade: { hit: boolean | null; words: string; provenance: string } | null;
  about: {
    source: string | null;
    rules: string;
    rows: Array<{ label: string; value: string }>;
    /** During play, the quote the current slot refused; else null. */
    historical: HockeyJourneyHistoricalQuote | null;
  };
}

export interface HockeyJourneyOriginals {
  scope: string;
  heading: string;
  /** "9 originals"; null when none. */
  context: string | null;
  emptyWords: string;
  originals: HockeyJourneyOriginal[];
}

export interface HockeyJourneyCatalogueSource {
  family: string;
  groupKey: string;
  label: string;
  threshold: number | null;
  row: HockeyJourneyMarketRow;
  closed: boolean;
  isPlayerProp: boolean;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** `buildQuestionCatalog`'s group key, spelled exactly as its `add` spells it. */
function catalogGroupKey(family: string, row: HockeyJourneyMarketRow): string {
  const question = (row.market_name ?? "").trim();
  return JSON.stringify([family, row.source ?? null, question, row.period ?? null, row._market_id ?? null]);
}

/** Every served outcome row, in the order `buildQuestionCatalog` reads them. */
function catalogSources(data: GameMarketsResponse): HockeyJourneyCatalogueSource[] {
  const out: HockeyJourneyCatalogueSource[] = [];
  const add = (family: string, rows: readonly HockeyJourneyMarketRow[] | null | undefined, closed = false, isPlayerProp = false) => {
    for (const row of rows ?? []) {
      out.push({
        family,
        groupKey: catalogGroupKey(family, row),
        label: (row.outcome_name ?? "").trim() || row.market_name || "",
        threshold: finite(row.threshold),
        row,
        closed,
        isPlayerProp,
      });
    }
  };
  const rows = (value: unknown) => (value ?? []) as unknown as HockeyJourneyMarketRow[];
  add("Game lines", rows(data.totals));
  add("Game lines", rows(data.spreads));
  add("Team scoring", rows(data.team_totals));
  add("Periods", rows(data.period_markets));
  add("Periods", rows(data.closed_period_markets), true);
  add("Player props", rows(data.player_props), false, true);
  for (const matchup of data.matchups ?? []) {
    for (const outcome of matchup.outcomes ?? []) {
      const row: HockeyJourneyMarketRow = {
        market_name: matchup.market_name,
        outcome_name: outcome.name,
        probability: outcome.probability,
        source: matchup.source,
        is_winner: outcome.is_winner,
        resolution_source: outcome.resolution_source,
        contributor_outcome_ids: (outcome as unknown as { contributor_outcome_ids?: number[] | null }).contributor_outcome_ids,
        _market_id: (matchup as unknown as { _market_id?: number | null })._market_id,
      };
      // `buildQuestionCatalog`'s matchup row carries no period and no market id.
      out.push({
        family: "Matchups",
        groupKey: JSON.stringify(["Matchups", row.source ?? null, (row.market_name ?? "").trim(), null, null]),
        label: outcome.name,
        threshold: null,
        row,
        closed: false,
        isPlayerProp: false,
      });
    }
  }
  const other = rows(data.other);
  add("Game lines", other.filter((row) => row.market_type === "moneyline"));
  add("Other", other.filter((row) => row.market_type !== "moneyline"));
  return out;
}

function outcomeKey(groupKey: string, label: string, threshold: number | null): string {
  return JSON.stringify([groupKey, label, threshold]);
}

export interface HockeyJourneyCatalogueMatch {
  group: CatalogGroup;
  outcome: CatalogOutcome;
  source: HockeyJourneyCatalogueSource;
}

/** Every outcome the catalogue lists, in its order, with the served row it came from. */
export function catalogueMatches(
  data: GameMarketsResponse,
  status: string | null | undefined,
  nowMs: number,
): HockeyJourneyCatalogueMatch[] {
  const buckets = new Map<string, HockeyJourneyCatalogueSource[]>();
  for (const source of catalogSources(data)) {
    const key = outcomeKey(source.groupKey, source.label, source.threshold);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(source);
    else buckets.set(key, [source]);
  }
  const out: HockeyJourneyCatalogueMatch[] = [];
  for (const group of buildQuestionCatalog(data, status, nowMs)) {
    for (const outcome of group.outcomes) {
      const bucket = buckets.get(outcomeKey(group.key, outcome.label, outcome.threshold));
      const source = bucket?.shift();
      if (source) out.push({ group, outcome, source });
    }
  }
  return out;
}

function idsText(values: number[] | null | undefined, separator: string): string | null {
  return values && values.length > 0 ? values.map(String).join(separator) : null;
}

function identityOf(row: HockeyJourneyMarketRow): HockeyJourneyOriginalIdentity {
  const source = row.source ? row.source : ORIGINALS_WORDS.unattributed;
  const market =
    (typeof row._market_id === "number" ? String(row._market_id) : null) ?? idsText(row._market_ids, "+") ?? (row.market_name ?? "");
  const side = idsText(row.contributor_outcome_ids, "+") ?? `${row.market_name ?? ""}-${row.outcome_name ?? ""}`;
  return { source, market, side };
}

/** `catalogQuote`'s reasons for printing nothing, in the catalogue's words. */
function absenceWords(source: HockeyJourneyCatalogueSource, status: string | null | undefined, nowMs: number): string {
  if (source.closed) return ORIGINALS_WORDS.periodFinished;
  if (!isPregameStatus(status) && sourceIsStale(source.row.observed_at ?? null, nowMs)) return ORIGINALS_WORDS.noRecentPrice;
  return ORIGINALS_WORDS.unavailablePrice;
}

function originalPregame(match: HockeyJourneyCatalogueMatch, started: boolean, status: string | null | undefined, nowMs: number): HockeyJourneyOriginalReading {
  const venue = sourceLabel(match.source.row.source);
  if (started) {
    const mark = match.source.isPlayerProp && lineSide(match.source.row) === "over" ? admissible(match.source.row.pregame_mark) : null;
    if (mark === null) return { kind: "missing", words: ORIGINALS_WORDS.noPregameChance };
    return {
      kind: "value",
      text: formatProbabilityPercent(mark),
      placement: mark,
      provenance: joined([ORIGINALS_WORDS.savedBeforeStart, venue]),
    };
  }
  const price = admissible(match.outcome.probability);
  if (price === null) return { kind: "missing", words: absenceWords(match.source, status, nowMs) };
  if (!isRecentQuote(match.outcome.observedAt, nowMs)) return { kind: "missing", words: ORIGINALS_WORDS.noRecentPrice };
  return { kind: "value", text: formatProbabilityPercent(price), placement: price, provenance: joined([clockWords(match.outcome.observedAt), venue]) };
}

function historicalQuote(price: number, at: number | null, venue: string | null): HockeyJourneyHistoricalQuote {
  const text = formatProbabilityPercent(price);
  // Undated: no clock, and no venue line either (native `date.flatMap`).
  const recorded = at === null ? null : joined([clockWords(at), venue]);
  return {
    text,
    recorded,
    label: ORIGINALS_WORDS.historicalLabel,
    value: recorded
      ? `${text}, ${ORIGINALS_WORDS.historicalRecorded} ${recorded}`
      : `${text}, ${ORIGINALS_WORDS.historicalTimeUnknown}`,
  };
}

/**
 * During play: the catalogue's price as the current chance only when the
 * contribution card's `inGameReading` would admit it — dated, at or after the
 * listed start, not stale, recent — in that order. A refused quote leaves that
 * rule's words and becomes the historical quote. No quote is the catalogue's
 * words; a settled row shows no chance and keeps no quote.
 */
function originalLater(
  match: HockeyJourneyCatalogueMatch,
  event: EventDetailResponse,
  nowMs: number,
): { later: HockeyJourneyOriginalReading; quote: HockeyJourneyHistoricalQuote | null } {
  const row = match.source.row;
  const venue = sourceLabel(row.source);
  const observed = match.outcome.observedAt;
  const at = parseMs(observed);
  // The catalogue's own "stale" reason (`catalogQuote`: during play, older than the bound).
  const stale = !isPregameStatus(event.status) && sourceIsStale(observed, nowMs);
  const missing = (words: string): HockeyJourneyOriginalReading => ({ kind: "missing", words });

  // The catalogue's admitted price, else a stale one's read by the catalogue's
  // own rule at the row's own observation instant.
  let price = admissible(match.outcome.probability);
  if (price === null && stale && at !== null && !match.source.closed) {
    price = admissible(catalogQuote(row, event.status, at));
  }
  if (price === null) return { later: missing(absenceWords(match.source, event.status, nowMs)), quote: null };
  // A settled 1 / 0 is a result: never a chance, never a saved price.
  if (servedSettlement(row.is_winner, row.resolution_source) !== null) {
    return { later: missing(ORIGINALS_WORDS.noCurrentChance), quote: null };
  }
  const quote = historicalQuote(price, at, venue);
  if (at === null) return { later: missing(ORIGINALS_WORDS.noRecentPrice), quote };
  const start = parseMs(event.commence_time);
  if (start !== null && at < start) return { later: missing(CONTRIBUTION_WORDS.noInGameReading), quote };
  if (stale || !isRecentQuote(observed, nowMs)) return { later: missing(ORIGINALS_WORDS.noRecentPrice), quote };
  return {
    later: {
      kind: "value",
      text: formatProbabilityPercent(price),
      placement: price,
      provenance: joined([`${ORIGINALS_WORDS.recorded} ${clockWords(at) ?? ""}`, venue]),
    },
    quote: null,
  };
}

function originalGrade(source: HockeyJourneyCatalogueSource): { hit: boolean | null; words: string; provenance: string } {
  const row = source.row;
  const served = servedSettlement(row.is_winner, row.resolution_source);
  let won: boolean | null;
  if (source.isPlayerProp) {
    const verdict = propContractResult(row, null, row.threshold ?? 0);
    won = verdict === "reached" ? true : verdict === "missed" ? false : null;
  } else {
    won = served;
  }
  if (won === null) {
    return {
      hit: null,
      words: ORIGINALS_WORDS.notYetConfirmed,
      provenance: served === null ? ORIGINALS_WORDS.noSettlement : ORIGINALS_WORDS.disputed,
    };
  }
  const venue = sourceLabel(row.source);
  // Web's ONE settled vocabulary (lib/propGrade.ts), for every original on this
  // surface; native says OutcomeVerdict's "Won" / "Lost" (platform difference).
  return { hit: won, words: propVerdictLabel(won), provenance: venue ? `Settlement · ${venue}` : "Venue settlement" };
}

function originalLabel(source: HockeyJourneyCatalogueSource, event: EventDetailResponse): string {
  const row = source.row;
  if (!source.isPlayerProp) return source.label;
  const subject = propSubject(row.outcome_name);
  const threshold = finite(row.threshold);
  if (!subject || threshold === null) return source.label;
  const target = targetLabel(threshold);
  const o = row.outcome_name ?? "";
  const colon = o.indexOf(":");
  if (colon < 0 || o.slice(colon + 1).trim() !== target) return source.label;
  const stat = statFamily(statLabel(row.market_name ?? "", event.home_team, event.away_team, subject));
  return `${subject} ${target} ${stat.toLowerCase()}`;
}

/** "All props": every original the page's catalogue lists, with its readings and grade. */
export function hockeyJourneyOriginals(
  event: EventDetailResponse,
  markets: GameMarketsResponse | null | undefined,
  nowMs: number,
): HockeyJourneyOriginals {
  const phase = hockeyJourneyPhase(event, nowMs);
  const started = propsHaveStarted(event, nowMs);
  const matches = markets ? catalogueMatches(markets, event.status, nowMs) : [];
  const originals = matches.map((match): HockeyJourneyOriginal => {
    const identity = identityOf(match.source.row);
    let mode: HockeyJourneyOriginal["mode"] = "pregame";
    let later: HockeyJourneyOriginalReading | null = null;
    let grade: HockeyJourneyOriginal["grade"] = null;
    let historical: HockeyJourneyHistoricalQuote | null = null;
    if (phase === "live") {
      const reading = originalLater(match, event, nowMs);
      mode = "current";
      later = reading.later;
      historical = reading.quote;
    } else if (phase === "final") {
      mode = "result";
      grade = originalGrade(match.source);
    }
    const rows: Array<{ label: string; value: string }> = [];
    const marketIds =
      (typeof match.source.row._market_id === "number" ? String(match.source.row._market_id) : null) ??
      idsText(match.source.row._market_ids, ", ");
    if (marketIds) rows.push({ label: ORIGINALS_WORDS.marketId, value: marketIds });
    const outcomeIds = idsText(match.source.row.contributor_outcome_ids, ", ");
    if (outcomeIds) rows.push({ label: ORIGINALS_WORDS.outcomeId, value: outcomeIds });
    return {
      key: `${identity.source}|${identity.market}|${identity.side}`,
      identity,
      title: match.group.question,
      outcome: match.outcome.label,
      label: originalLabel(match.source, event),
      family: match.group.family,
      mode,
      pregame: originalPregame(match, started, event.status, nowMs),
      later,
      grade,
      about: { source: sourceLabel(match.source.row.source), rules: ORIGINALS_WORDS.rulesUnavailable, rows, historical },
    };
  });
  return {
    scope: `nhl:${event.id}:${phase}:originals`,
    heading: ORIGINALS_WORDS.heading,
    context: originals.length === 0 ? null : originals.length === 1 ? "1 original" : `${originals.length} originals`,
    emptyWords: ORIGINALS_WORDS.emptyWords,
    originals,
  };
}
