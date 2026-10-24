/**
 * #9483 — the NFL page's game-story cards on web (design freeze v328,
 * `nfl-web-nba-adoption-v328/NFL-WEB.md`), translated from the shipped phone
 * build's decisions (`NFLEventCardDeck9483.swift`, `NFLCardReader9483.swift`,
 * production 06048a81f4). This file holds the decisions; the components only
 * draw them.
 *
 * Every number a card prints is one the page already serves. The deck adds no
 * source, no fetch and no ranking service, and its order is fixed per page
 * state, so a card never moves while someone is reading it.
 *
 * - **Projected finish**: the sportsbook's projected final against what
 *   happened, from the page's own projected-points input. Three moments, never
 *   blended: the last projection before the first observed game state, the
 *   newest projection while it is still a current capture, and the final score
 *   (a result, never a projection or a 100% quote).
 * - **Player milestones**: one player's quoted ladder as a milestone profile.
 *   Before kickoff each line's chance is the current quote, only while its
 *   observation clock is recent. Once play starts it is the served pregame mark,
 *   never a live or settled price. The final actual and the grade are the
 *   server's and appear only after the final.
 *
 * NFL ONLY: every entry point starts with `nflCardsApply`.
 */

import { propOutcomeSide } from "./propOutcomeSide";
import { propSubjectDisplay } from "./playerPropsGrouping";
import { SOURCE_STALE_AFTER_MS, sourceAgeMs } from "./sourceAge";
import { isFinishedStatus } from "./eventState";
import {
  buildProjectedFinalPointsSeries,
  MAX_CAPTURE_GAP_MS,
  type ProjectedFinalPointsInput,
} from "./projectedFinalPointsSeries";
import type { LadderCard } from "./nbaEventCards";

export const NFL_SPORT_KEY = "americanfootball_nfl";

export function nflCardsApply(sportKey: string | null | undefined): boolean {
  return sportKey === NFL_SPORT_KEY;
}

/** #9483 NBA slice — the sports whose pages carry game-story cards and both teams' lines. */
export function storyCardsApply(sportKey: string | null | undefined): boolean {
  return sportKey === NFL_SPORT_KEY || sportKey === "basketball_nba";
}

/** At most this many player cards: the deck is a story, not the catalog. */
export const MAX_MILESTONE_CARDS = 2;

/** Fewer priced lines than this is a choice between chips, not a shape. */
export const MIN_PRICED_MILESTONES = 3;

// ─── Projected finish ──────────────────────────────────────────────────────

export interface FinishPair {
  away: number;
  home: number;
  /** Epoch ms of the capture or score, or null when unknown. */
  at: number | null;
}

export type FinishPhase = "before" | "during" | "after";

export interface FinishCard {
  kind: "finish";
  id: "finish";
  phase: FinishPhase;
  pregame: FinishPair;
  /** The newest admitted projection while live. */
  projectedNow: FinishPair | null;
  /** The final score after the final. */
  final: FinishPair | null;
}

/** null when level. */
function homeLeads(pair: FinishPair): boolean | null {
  return pair.home === pair.away ? null : pair.home > pair.away;
}

export function finishKicker(card: FinishCard): string {
  return card.phase === "after" ? "Final vs forecast" : "Projected finish";
}

/**
 * The card's one sentence. It names a flip only when the projected leader
 * actually changed, and never one from a level pregame projection.
 */
export function finishHeadline(card: FinishCard, awayName: string, homeName: string): string {
  const name = (leads: boolean) => (leads ? homeName : awayName);
  const before = homeLeads(card.pregame);
  switch (card.phase) {
    case "before":
      return before === null ? "Projected level" : `${name(before)} projected ahead`;
    case "during": {
      if (!card.projectedNow) {
        return before === null
          ? "Projected level before kickoff"
          : `${name(before)} projected ahead before kickoff`;
      }
      const now = homeLeads(card.projectedNow);
      if (now === null) return "The projected finish is level";
      if (before !== null && before !== now) return "The projected finish has flipped";
      return `${name(now)} still projected ahead`;
    }
    case "after": {
      const winner = card.final ? homeLeads(card.final) : null;
      if (winner === null) return "Final vs forecast";
      if (before === null) return `${name(winner)} won`;
      return before === winner ? `${name(winner)} won as projected` : `${name(winner)} beat the forecast`;
    }
  }
}

function parseMs(value: string | null | undefined): number | null {
  if (typeof value !== "string") return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

/**
 * From the page's own projected-points input (`useProjectedFinalPointsMount`).
 * Null wherever that series is refused, or holds no projection before the game
 * began. A final comes only from the series' admitted actual score, never from
 * the last recorded intermediate score or a quote.
 */
export function buildFinishCard(input: ProjectedFinalPointsInput | null | undefined): FinishCard | null {
  if (!input || !storyCardsApply(input.sportKey)) return null;
  const series = buildProjectedFinalPointsSeries(input);
  if (!series.supported) return null;
  const points = series.segments.flat();
  const floor = parseMs(input.scoreObservationStartAt) ?? parseMs(input.kickoffAt);
  let pregamePoint: { home: number; away: number; at: number } | null = null;
  if (series.phase === "before") {
    pregamePoint = series.latestIntervalUnavailable ? null : series.latest;
  } else if (floor !== null) {
    for (const p of points) if (p.at < floor) pregamePoint = p;
  }
  if (!pregamePoint) return null;
  const pregame: FinishPair = { away: pregamePoint.away, home: pregamePoint.home, at: pregamePoint.at };
  if (series.phase === "before") {
    return { kind: "finish", id: "finish", phase: "before", pregame, projectedNow: null, final: null };
  }
  if (series.phase === "during") {
    const latest = series.latest;
    const current = !series.latestIntervalUnavailable && floor !== null && latest.at >= floor;
    return {
      kind: "finish",
      id: "finish",
      phase: "during",
      pregame,
      projectedNow: current ? { away: latest.away, home: latest.home, at: latest.at } : null,
      final: null,
    };
  }
  const actual = series.latestActual;
  if (!actual) return null;
  return {
    kind: "finish",
    id: "finish",
    phase: "after",
    pregame,
    projectedNow: null,
    final: { away: actual.away, home: actual.home, at: actual.at },
  };
}

/**
 * #11103 — the page prints one projected final. While the hero prints one, the
 * finish card's "projected now" is that pair, not the stored series' latest,
 * which lags the quote (SEA@DEN: the card said Seattle 18.8 directly above the
 * Projected final points card's 16). Only a card that already holds a current
 * projection takes it; pregame, final and the freshness gate are unchanged.
 */
export function withPageProjection(
  cards: NflEventCard[],
  pair: { home: number; away: number } | null,
): NflEventCard[] {
  if (!pair) return cards;
  return cards.map((card) =>
    card.kind === "finish" && card.phase === "during" && card.projectedNow
      ? { ...card, projectedNow: { ...card.projectedNow, home: pair.home, away: pair.away } }
      : card,
  );
}

/**
 * #2920 / #11296 — the page prints one pregame forecast. While the headline
 * prints the sportsbooks' projection before the scheduled start (under a final,
 * or beside a live projected final), the finish card's pregame is that pair,
 * not the series' own pre-game point: one book, picked by its row count in
 * whatever window the history served, at its last capture before the first
 * recorded game state. On a pick'em line that capture can name the other team
 * (GB–DAL 14780562: the headline said Cowboys 28–27 from 21 sportsbooks, the
 * card said "Packers won as projected" from betrivers' 27.5–26.5 at 00:23Z).
 * The card's own clock and its final are unchanged. With no headline pair
 * (none printed, or before the game, where the card already reads the current
 * projection) the card keeps the series' reading.
 */
export function withPagePregame(
  cards: NflEventCard[],
  pair: { home: number; away: number } | null,
): NflEventCard[] {
  if (!pair) return cards;
  return cards.map((card) =>
    card.kind === "finish" && card.phase !== "before"
      ? { ...card, pregame: { ...card.pregame, home: pair.home, away: pair.away } }
      : card,
  );
}

/** A projection keeps its half point; a final score is whole. */
export function formatPoints(value: number): string {
  return Math.round(value) === value ? String(value) : value.toFixed(1);
}

// ─── Player milestones ─────────────────────────────────────────────────────

/** A `player_props[]` row, as much of it as the cards read. */
export interface NflPropRow {
  market_name: string;
  outcome_name: string;
  threshold: number | null;
  over_probability: number | null;
  source: string;
  observed_at?: string | null;
  pregame_mark?: number | null;
  actual?: number | null;
  hit?: boolean | null;
  player_team?: "home" | "away";
  _inverted?: boolean;
}

/**
 * The original row's identity. Source, market and outcome together, so it is
 * stable across reorders and never an array index.
 */
export function propRowId(row: Pick<NflPropRow, "source" | "market_name" | "outcome_name">): string {
  return `${row.source}|${row.market_name}|${row.outcome_name}`;
}

/**
 * - `pregamePrice`: before kickoff, the venue's current price, which IS the
 *   pregame chance;
 * - `pregameMark`: once play starts, the server's pregame mark. A live or
 *   settled price is never relabelled pregame.
 */
export type MilestoneBasis = "pregamePrice" | "pregameMark";

export type PropSide = "home" | "away" | "unknown";

export interface MilestoneRung {
  threshold: number;
  /**
   * The chance this card may print for the line, or null: before kickoff a
   * quote with no recent observation, after it a line with no served pregame
   * mark. A null line stays on the card, draws no dot and never borrows
   * another number.
   */
  chance: number | null;
  /** The quote's observation clock (`pregamePrice` basis only), so it can expire. */
  observedAt: string | null;
  /** The original row, for exact details. */
  rowId: string;
  /** The server's grade, after the final only. */
  hit: boolean | null;
}

export interface MilestoneCard {
  kind: "milestone";
  id: string;
  player: string;
  stat: string;
  side: PropSide;
  basis: MilestoneBasis;
  rungs: MilestoneRung[];
  /** The stat's final value as the server graded it; null until then. */
  actual: number | null;
}

export type NflEventCard = FinishCard | MilestoneCard | LadderCard;

export function cardTitle(card: NflEventCard): string {
  if (card.kind === "finish") return finishKicker(card);
  if (card.kind === "ladder") return card.family === "total" ? "Scoring expectations" : "Winning margin";
  return `${card.player} · ${card.stat}`;
}

export function milestoneCaption(card: MilestoneCard): string {
  return card.basis === "pregamePrice" ? "Pregame chance to reach each line" : "Chance before kickoff to reach each line";
}

/** The line a target prints: `2+` for a whole line, `2.5+` for a half. */
export function targetLabel(threshold: number): string {
  return `${threshold}+`;
}

function displayPercent(p: number): number {
  return Math.round(p * 100);
}

/**
 * The rung a card opens on: the priced rung nearest even odds, ties to the
 * lower line. Null when no rung carries a price, so nothing is selected.
 */
export function defaultRungIndex(card: MilestoneCard): number | null {
  let best: { index: number; distance: number } | null = null;
  card.rungs.forEach((rung, index) => {
    if (rung.chance === null) return;
    const distance = Math.abs(rung.chance - 0.5);
    if (best === null || distance < best.distance) best = { index, distance };
  });
  return best === null ? null : (best as { index: number }).index;
}

export interface MilestoneProfile {
  /** Ascending by line; the rung index each point belongs to. */
  points: { index: number; threshold: number; chance: number }[];
  domain: [number, number];
}

/**
 * The milestone profile a card draws from its own priced rungs, or null:
 * fewer than three priced lines, a flat ladder (#5137: every line rounds to
 * one percent), or two quotes for one line. Nothing between the lines is drawn.
 */
export function milestoneProfile(card: MilestoneCard): MilestoneProfile | null {
  const priced = card.rungs
    .map((rung, index) => ({ index, threshold: rung.threshold, chance: rung.chance }))
    .filter(
      (p): p is { index: number; threshold: number; chance: number } =>
        p.chance !== null && Number.isFinite(p.chance) && p.chance >= 0 && p.chance <= 1 && Number.isFinite(p.threshold),
    );
  if (priced.length < MIN_PRICED_MILESTONES) return null;
  if (new Set(priced.map((p) => displayPercent(p.chance))).size <= 1) return null;
  const lines = priced.map((p) => p.threshold);
  if (new Set(lines).size !== lines.length) return null;
  const low = Math.min(...lines);
  const high = Math.max(...lines);
  if (!(high > low)) return null;
  const pad = (high - low) / (priced.length - 1) / 2;
  const lower = low >= 0 ? Math.max(0, low - pad) : low - pad;
  return { points: [...priced].sort((a, b) => a.threshold - b.threshold), domain: [lower, high + pad] };
}

/**
 * The stat axis the chart draws: the profile's own domain, widened so the
 * actual always sits inside it, a final 0 below a ladder starting at 0.5
 * included. The actual is a stat value on this axis, never a probability.
 */
export function statDomain(domain: [number, number], actual: number | null): [number, number] {
  if (actual === null || !Number.isFinite(actual)) return domain;
  const pad = Math.max((domain[1] - domain[0]) * 0.06, 0.5);
  return [Math.min(domain[0], actual - pad), Math.max(domain[1], actual + pad)];
}

/**
 * A quote is recent when its observation clock is readable and no older than
 * the 30-minute bound every live price on the page uses. An undatable quote is
 * NOT recent: the card would print it as a current chance.
 */
export function isRecentQuote(observedAt: string | null | undefined, nowMs: number): boolean {
  const age = sourceAgeMs(observedAt, nowMs);
  return age !== null && age <= SOURCE_STALE_AFTER_MS;
}

/**
 * The card as it may be shown at `nowMs`: an unobserved pregame price loses its
 * number, and so does a live projection whose own capture is older than the
 * series' capture gap (or undatable) — even when a newer projection exists.
 */
export function cardAt(card: NflEventCard, nowMs: number): NflEventCard {
  if (card.kind === "ladder") {
    // Same rule for the NBA ladders (`ladderAt`): only a pregame price ages.
    if (card.phase !== "before") return card;
    let aged = false;
    const points = card.points.map((p) => {
      if (p.chance === null || isRecentQuote(p.observedAt, nowMs)) return p;
      aged = true;
      return { ...p, chance: null };
    });
    return aged ? { ...card, points } : card;
  }
  if (card.kind === "finish") {
    const at = card.projectedNow?.at ?? null;
    if (!card.projectedNow || (at !== null && nowMs - at <= MAX_CAPTURE_GAP_MS)) return card;
    return { ...card, projectedNow: null };
  }
  if (card.kind !== "milestone" || card.basis !== "pregamePrice") return card;
  let changed = false;
  const rungs = card.rungs.map((rung) => {
    if (rung.chance === null || isRecentQuote(rung.observedAt, nowMs)) return rung;
    changed = true;
    return { ...rung, chance: null };
  });
  return changed ? { ...card, rungs } : card;
}

/**
 * The headline a line's Details may lead with: the chance its card prints for
 * that line right now, and the card's basis to name it by — never re-derived
 * from the row. Before kickoff the row's `pregame_mark` is the opening line,
 * not the pregame chance, so it never leads. Null when no displayed card
 * carries the line or the card prints no number for it.
 */
export function lineLead(cards: NflEventCard[], rowId: string): { chance: number; basis: MilestoneBasis } | null {
  for (const card of cards) {
    if (card.kind !== "milestone") continue;
    const rung = card.rungs.find((r) => r.rowId === rowId);
    if (rung) return rung.chance === null ? null : { chance: rung.chance, basis: card.basis };
  }
  return null;
}

export function lineLeadLabel(basis: MilestoneBasis): string {
  return basis === "pregamePrice" ? "Pregame chance" : "Chance before kickoff";
}

/** Kalshi's subject before the colon of `outcome_name` names a team, not a player. */
export function isTeamSubject(subject: string, teams: string[]): boolean {
  const name = subject.trim().toLowerCase();
  if (!name) return false;
  if (["d/st", "defense", "defence", "special teams"].some((word) => name.includes(word))) return true;
  return teams.some((team) => {
    const t = team.trim().toLowerCase();
    return t !== "" && ` ${t} `.includes(` ${name} `);
  });
}

function tokens(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^\p{L}\p{N}]+/u)
      .filter((t) => t.length >= 3),
  );
}

function shares(prefixTokens: Set<string>, team: string): boolean {
  const teamTokens = tokens(team);
  for (const t of teamTokens) if (prefixTokens.has(t)) return true;
  return false;
}

const NOISE_PREFIXES = ["Player ", "Batter ", "Pitcher "];

/**
 * What a ladder's stat is called on the card. Drops the market's prefix only
 * when the reader can already see it (both of this event's teams, or the
 * card's player). The venue's own wording, "(Protected)" included, is kept.
 */
export function statLabel(marketName: string, homeTeam: string, awayTeam: string, player: string | null): string {
  const raw = marketName.trim();
  let label = raw;
  const colon = raw.indexOf(":");
  if (colon >= 0) {
    const prefix = raw.slice(0, colon).trim();
    const remainder = raw.slice(colon + 1).trim();
    const prefixTokens = tokens(prefix);
    const namesBoth = prefixTokens.size > 0 && shares(prefixTokens, homeTeam) && shares(prefixTokens, awayTeam);
    const namesPlayer =
      !!player && prefix.localeCompare(player.trim(), undefined, { sensitivity: "base" }) === 0;
    if (remainder && (namesBoth || namesPlayer)) label = remainder;
  }
  for (const p of NOISE_PREFIXES) if (label.startsWith(p)) label = label.slice(p.length);
  const trimmed = label.trim();
  return trimmed || raw;
}

/** The stat words a ladder is browsed under: a leading `2+ ` and trailing `O/U 2.5` dropped. */
export function statFamily(label: string): string {
  const name = label
    .trim()
    .replace(/^\d+(?:\.\d+)?\+\s+/, "")
    .replace(/\s+O\/U\s+\d+(?:\.\d+)?$/i, "")
    .trim();
  return name || label;
}

/** Families with the most ladders first, ties by name, so a reload deals the same deck. */
function orderedFamilies(families: string[]): string[] {
  const counts = new Map<string, number>();
  for (const f of families) counts.set(f, (counts.get(f) ?? 0) + 1);
  return [...counts.keys()].sort((a, b) => {
    const d = (counts.get(b) ?? 0) - (counts.get(a) ?? 0);
    return d !== 0 ? d : a < b ? -1 : a > b ? 1 : 0;
  });
}

/** The over side only reads `over_probability` or its mark (gotcha #17). */
function isOverRow(row: NflPropRow): boolean {
  if (row._inverted) return false;
  const side = propOutcomeSide(row.outcome_name);
  if (side !== "unreadable") return side === "over";
  if (/\bunder\b/i.test(row.outcome_name)) return false;
  return /\bover\b/i.test(row.outcome_name);
}

export function milestoneCards(opts: {
  props: NflPropRow[];
  eventStatus: string | null | undefined;
  commenceTime: string | null | undefined;
  homeTeam: string;
  awayTeam: string;
  nowMs: number;
}): MilestoneCard[] {
  const { props, eventStatus, homeTeam, awayTeam, nowMs } = opts;
  const commence = parseMs(opts.commenceTime);
  const finished = isFinishedStatus(eventStatus);
  const started = eventStatus === "live" || finished || commence === null || commence <= nowMs;
  const basis: MilestoneBasis = started ? "pregameMark" : "pregamePrice";

  const ladders = new Map<string, { player: string; market: string; rows: NflPropRow[] }>();
  for (const row of props) {
    const colon = row.outcome_name.indexOf(":");
    if (colon < 0) continue;
    const player = propSubjectDisplay(row.outcome_name.slice(0, colon).trim());
    if (!player || isTeamSubject(player, [homeTeam, awayTeam])) continue;
    const market = row.market_name.trim();
    const key = `${player}|${market}`;
    const ladder = ladders.get(key) ?? { player, market, rows: [] };
    ladder.rows.push(row);
    ladders.set(key, ladder);
  }

  const candidates: { card: MilestoneCard; family: string }[] = [];
  for (const [key, ladder] of ladders) {
    const rungs: MilestoneRung[] = [];
    for (const row of ladder.rows) {
      const threshold = row.threshold;
      if (typeof threshold !== "number" || !Number.isFinite(threshold) || !isOverRow(row)) continue;
      const observedAt = basis === "pregamePrice" ? (row.observed_at ?? null) : null;
      let chance: number | null = basis === "pregamePrice" ? row.over_probability : (row.pregame_mark ?? null);
      if (chance !== null && !(Number.isFinite(chance) && chance >= 0 && chance <= 1)) chance = null;
      if (basis === "pregamePrice" && !isRecentQuote(observedAt, nowMs)) chance = null;
      rungs.push({ threshold, chance, observedAt, rowId: propRowId(row), hit: finished ? (row.hit ?? null) : null });
    }
    rungs.sort((a, b) => a.threshold - b.threshold);
    const stat = statLabel(ladder.market, homeTeam, awayTeam, ladder.player);
    const servedSide = ladder.rows.find((r) => r.player_team)?.player_team;
    const actualRow = finished ? ladder.rows.find((r) => typeof r.actual === "number" && Number.isFinite(r.actual)) : undefined;
    const card: MilestoneCard = {
      kind: "milestone",
      id: `milestone:${key}`,
      player: ladder.player,
      stat,
      side: servedSide === "home" || servedSide === "away" ? servedSide : "unknown",
      basis,
      rungs,
      actual: actualRow ? (actualRow.actual as number) : null,
    };
    if (!milestoneProfile(card)) continue;
    candidates.push({ card, family: statFamily(stat) });
  }

  const order = orderedFamilies(candidates.map((c) => c.family));
  const rank = new Map(order.map((f, i) => [f, i]));
  const priced = (c: MilestoneCard) => c.rungs.filter((r) => r.chance !== null).length;
  candidates.sort((a, b) => {
    const ra = rank.get(a.family) ?? Number.MAX_SAFE_INTEGER;
    const rb = rank.get(b.family) ?? Number.MAX_SAFE_INTEGER;
    if (ra !== rb) return ra - rb;
    const pa = priced(a.card);
    const pb = priced(b.card);
    if (pa !== pb) return pb - pa;
    return a.card.id < b.card.id ? -1 : a.card.id > b.card.id ? 1 : 0;
  });
  const players = new Set<string>();
  const chosen: MilestoneCard[] = [];
  for (const { card } of candidates) {
    if (chosen.length >= MAX_MILESTONE_CARDS) break;
    if (players.has(card.player)) continue;
    players.add(card.player);
    chosen.push(card);
  }
  return chosen;
}

/**
 * The NBA deck: winning margin, scoring expectations, then the projected
 * finish — a fixed order per page state (no ranking service).
 */
export function nbaEventCards(
  sportKey: string | null | undefined,
  finish: FinishCard | null,
  ladders: { margin: LadderCard | null; total: LadderCard | null },
): NflEventCard[] {
  if (sportKey !== "basketball_nba") return [];
  return [ladders.margin, ladders.total, finish].filter((c): c is LadderCard | FinishCard => c !== null);
}

/** The deck for this page, or empty to draw none. NFL only. */
export function nflEventCards(
  sportKey: string | null | undefined,
  finish: FinishCard | null,
  milestones: MilestoneCard[],
): NflEventCard[] {
  if (!nflCardsApply(sportKey)) return [];
  return [...(finish ? [finish] : []), ...milestones];
}

// ─── The reader's hold ─────────────────────────────────────────────────────

/** The match line the reader keeps on top. */
export interface ReaderHeader {
  /** "DEN 20–7 SEA · Q3 5:47", "SEA vs DEN · Pregame", "SEA 7–27 DEN · Final". */
  match: string;
  /** "Win chances · SEA 43% · DEN 57%"; empty after the final. */
  chances: string;
}

export function readerHeader(opts: {
  awayShort: string;
  homeShort: string;
  awayScore: number | null;
  homeScore: number | null;
  stateLabel: string | null;
  awayChance: string | null;
  homeChance: string | null;
  finished: boolean;
}): ReaderHeader {
  const { awayShort, homeShort, awayScore, homeScore, stateLabel, finished } = opts;
  const scored = awayScore !== null && homeScore !== null;
  const core = scored ? `${awayShort} ${awayScore}–${homeScore} ${homeShort}` : `${awayShort} vs ${homeShort}`;
  const match = stateLabel ? `${core} · ${stateLabel}` : core;
  const chances =
    !finished && opts.awayChance && opts.homeChance
      ? `Win chances · ${awayShort} ${opts.awayChance} · ${homeShort} ${opts.homeChance}`
      : "";
  return { match, chances };
}

/**
 * What the reader shows, given what it holds and what is live now: the held
 * cards, except that a live projection that stopped being current leaves, and
 * so does a pregame price no longer observed at `nowMs`. A forecast never
 * outlives its validity because someone was reading it.
 */
export function displayedCards(held: NflEventCard[], live: NflEventCard[], nowMs: number): NflEventCard[] {
  const liveFinish = live.find((c): c is FinishCard => c.kind === "finish") ?? null;
  return held.map((card) => {
    if (card.kind === "finish" && card.projectedNow && !liveFinish?.projectedNow) {
      return { ...card, projectedNow: null };
    }
    return cardAt(card, nowMs);
  });
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Whether Refresh would change anything on screen, Details included. */
export function readerHasUpdate(opts: {
  held: NflEventCard[];
  heldHeader: ReaderHeader;
  heldRows: Record<string, NflPropRow>;
  live: NflEventCard[];
  liveHeader: ReaderHeader;
  liveRows: Record<string, NflPropRow>;
  nowMs: number;
}): boolean {
  const shown = displayedCards(opts.held, opts.live, opts.nowMs);
  const fresh = opts.live.map((c) => cardAt(c, opts.nowMs));
  return !sameJson(shown, fresh) || !sameJson(opts.heldHeader, opts.liveHeader) || !sameJson(opts.heldRows, opts.liveRows);
}

/**
 * The card on screen after Refresh replaces `old` with `next`: the same card
 * when it survived; otherwise the survivor nearest to it in the old order (at
 * equal distance the following one wins); otherwise the first new card. Null
 * only when no card is left, never an id no card carries.
 */
export function reconcileVisible(visible: string | null, old: string[], next: string[]): string | null {
  if (visible !== null && next.includes(visible)) return visible;
  const at = visible !== null ? old.indexOf(visible) : -1;
  if (at >= 0) {
    for (let d = 1; d < old.length; d++) {
      const after = old[at + d];
      if (after !== undefined && next.includes(after)) return after;
      const before = old[at - d];
      if (before !== undefined && next.includes(before)) return before;
    }
  }
  return next[0] ?? null;
}

/** The original rows the cards' lines point at, by row id: what Details shows. */
export function rowsForCards(cards: NflEventCard[], props: NflPropRow[]): Record<string, NflPropRow> {
  const ids = new Set(cards.flatMap((c) => (c.kind === "milestone" ? c.rungs.map((r) => r.rowId) : [])));
  const rows: Record<string, NflPropRow> = {};
  for (const row of props) {
    const id = propRowId(row);
    if (ids.has(id) && !(id in rows)) rows[id] = row;
  }
  return rows;
}

// ─── The reader's state ────────────────────────────────────────────────────

/**
 * What a full-size reader holds. Everything on screen when the card opened
 * (cards, match line, the original rows Details show) stays until Refresh,
 * which replaces all three together. `origin` is the card it was opened on:
 * Back returns there, whichever card was read last (the shipped NFL rule; the
 * NBA references' last-explored return is deliberately not adopted).
 */
export interface ReaderState {
  held: NflEventCard[];
  heldHeader: ReaderHeader;
  heldRows: Record<string, NflPropRow>;
  /** The card on screen, or null on the empty state. */
  visible: string | null;
  origin: string;
  /** The deck's order when the reader opened, so a vanished origin still has neighbours. */
  originOrder: string[];
  /** The original row whose exact details are open, or null. */
  detailsRowId: string | null;
}

export type ReaderAction =
  | { type: "step"; delta: number; nowMs: number; live: NflEventCard[] }
  | { type: "details"; rowId: string | null }
  | { type: "refresh"; live: NflEventCard[]; liveHeader: ReaderHeader; liveRows: Record<string, NflPropRow> };

export function openReader(opts: {
  cardId: string;
  live: NflEventCard[];
  liveHeader: ReaderHeader;
  liveRows: Record<string, NflPropRow>;
}): ReaderState {
  const ids = opts.live.map((c) => c.id);
  return {
    held: opts.live,
    heldHeader: opts.liveHeader,
    heldRows: opts.liveRows,
    visible: ids.includes(opts.cardId) ? opts.cardId : (ids[0] ?? null),
    origin: opts.cardId,
    originOrder: ids,
    detailsRowId: null,
  };
}

export function readerReducer(state: ReaderState, action: ReaderAction): ReaderState {
  switch (action.type) {
    case "step": {
      const ids = displayedCards(state.held, action.live, action.nowMs).map((c) => c.id);
      const at = state.visible !== null ? ids.indexOf(state.visible) : -1;
      const next = ids[(at < 0 ? 0 : at) + action.delta];
      return next === undefined ? state : { ...state, visible: next, detailsRowId: null };
    }
    case "details":
      return { ...state, detailsRowId: action.rowId };
    case "refresh": {
      const visible = reconcileVisible(
        state.visible,
        state.held.map((c) => c.id),
        action.live.map((c) => c.id),
      );
      return {
        ...state,
        held: action.live,
        heldHeader: action.liveHeader,
        heldRows: action.liveRows,
        visible,
        detailsRowId: visible === state.visible ? state.detailsRowId : null,
      };
    }
  }
}

/**
 * The card Back returns focus to: the origin while the page's deck still
 * carries it, otherwise the nearest surviving card in the order the deck had
 * when the reader opened, or null (the deck heading) when the deck is empty.
 */
export function returnTarget(state: ReaderState, deckIds: string[]): string | null {
  if (deckIds.includes(state.origin)) return state.origin;
  const base = state.originOrder.includes(state.origin) ? state.originOrder : [state.origin, ...state.originOrder];
  return reconcileVisible(state.origin, base, deckIds);
}
