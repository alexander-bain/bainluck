/**
 * #10090: Live committed `/api/feed/price-cards` + provisional SSE price overlays
 * (`authority-v3` for games, `market_preview` for futures/binaries) for
 * `/sport/[sport]/[league]`.
 *
 * Honors finished-game immutability (#12506), settled-outcome immutability
 * (#3868), and the three-way / draw-priced guard (#13509: never fabricate
 * `1 - p` away probability on soccer or draw-priced games when `p_away` is null).
 */
import type { LeagueGameBrief, LeagueMarket } from '@/lib/api';
import { displayedPreview, type BlendPreviewState } from '@/lib/blendPreview';
import type { MarketPreviews } from '@/lib/discover/marketPreview';
import { marketResolved, type DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import { sportPricesADraw } from '@/lib/drawPricedWinner';
import { isFinishedStatus } from '@/lib/eventState';
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from '@/lib/foldRevision';
import type { FeedEventData, FeedFuturesData } from '@/lib/types';

const PRICED_GAME_STATUSES = new Set(['scheduled', 'live']);
const STREAMED_MARKET_SOURCES = new Set(['kalshi', 'polymarket']);

export interface HeldLeagueLeg {
  probability: number | null;
  revision: number | null;
}

/** market id -> outcome id -> adopted leg. */
export type LeagueMarketBook = Map<number, Map<number, HeldLeagueLeg>>;

export interface HeldLeagueGame {
  status: string;
  revision: FoldRevision;
  observedMs: number | null;
  homeProbability: number | null;
  awayProbability: number | null;
  heroSource: string | null;
  live: {
    homeScore: number | null;
    awayScore: number | null;
    period: string | null;
    clock: string | null;
  } | null;
  final: {
    homeScore: number | null;
    awayScore: number | null;
    completedAt: string | null;
  } | null;
}

export type LeagueGameBook = Map<number, HeldLeagueGame>;

export function leagueGameStreamable(game: LeagueGameBrief): boolean {
  if (!PRICED_GAME_STATUSES.has(game.status)) return false;
  if (isFinishedStatus(game.status)) return false;
  if (game.venue_settled === true || game.venue_closed_no_winner === true) return false;
  return true;
}

export function leagueMarketStreamable(market: LeagueMarket): boolean {
  if (!STREAMED_MARKET_SOURCES.has(market.source)) return false;
  if (market.top_outcomes.some((o) => o.settled === true)) return false;
  return market.top_outcomes.some((o) => !o.settled);
}

export function leagueSectionMarkets(
  sections: Record<string, LeagueMarket[]> | undefined,
): LeagueMarket[] {
  if (!sections) return [];
  const seen = new Set<number>();
  const out: LeagueMarket[] = [];
  for (const list of Object.values(sections)) {
    for (const market of list) {
      if (seen.has(market.id)) continue;
      seen.add(market.id);
      out.push(market);
    }
  }
  return out;
}

function parseMs(raw: unknown): number | null {
  if (typeof raw !== 'string' || !raw) return null;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function liveStateOf(raw: unknown): { period: string | null; clock: string | null } | null {
  if (!raw || typeof raw !== 'object') return null;
  const state = raw as { period?: unknown; game_clock?: unknown };
  const text = (v: unknown) => (typeof v === 'string' && v ? v : null);
  return { period: text(state.period), clock: text(state.game_clock) };
}

export function adoptLeagueGameCards(
  book: LeagueGameBook,
  games: LeagueGameBrief[],
  response: DiscoverPriceCards,
  requested: Set<number>,
): LeagueGameBook {
  if (!Array.isArray(response?.items)) return book;
  const byId = new Map(games.map((g) => [g.id, g]));
  let next = book;
  for (const item of response.items) {
    if (item.type !== 'event') continue;
    const fresh = item.data as FeedEventData & {
      blend_fold_revision?: unknown;
      hero_probability_observed_at?: string | null;
      hero_probability_source?: string | null;
      live_state?: unknown;
      completed_at?: string | null;
    };
    const served = byId.get(fresh.id);
    if (!served || !requested.has(fresh.id) || !leagueGameStreamable(served)) continue;
    if (response.dispositions?.[`event-${fresh.id}`] !== 'updated') continue;
    const finished = served.status === 'live' && isFinishedStatus(fresh.status);
    if (fresh.status !== served.status && !finished) continue;
    const revision = parseFoldRevision(fresh.blend_fold_revision);
    if (!revision) continue;

    let live: HeldLeagueGame['live'] = null;
    let final: HeldLeagueGame['final'] = null;
    if (finished) {
      if (typeof fresh.home_score !== 'number' || typeof fresh.away_score !== 'number') continue;
      final = {
        homeScore: fresh.home_score,
        awayScore: fresh.away_score,
        completedAt: fresh.completed_at ?? null,
      };
    } else if (served.status === 'live') {
      const state = liveStateOf(fresh.live_state);
      if (!state) continue;
      live = {
        homeScore: fresh.home_score ?? null,
        awayScore: fresh.away_score ?? null,
        ...state,
      };
    }

    const observedMs = parseMs(fresh.hero_probability_observed_at);
    const held = next.get(fresh.id);
    if (held?.final) continue;
    if (held) {
      const order = compareFoldRevision(revision, held.revision);
      if (order !== 'newer' && order !== 'same') continue;
      if (!final && held.observedMs !== null && (observedMs === null || observedMs < held.observedMs)) {
        continue;
      }
    }

    const game: HeldLeagueGame = {
      status: fresh.status,
      revision,
      observedMs,
      homeProbability: fresh.current_odds?.home_probability ?? null,
      awayProbability: fresh.current_odds?.away_probability ?? null,
      heroSource: fresh.hero_probability_source ?? null,
      live,
      final,
    };
    if (held && JSON.stringify(held) === JSON.stringify(game)) continue;
    if (next === book) next = new Map(book);
    next.set(fresh.id, game);
  }
  return next;
}

export function patchLeagueGameFromBook(
  game: LeagueGameBrief,
  book: LeagueGameBook,
): LeagueGameBrief {
  const held = book.get(game.id);
  if (held?.final && game.status === 'live') {
    const { period: _period, game_clock: _clock, ...espn } = game.espn ?? {};
    return {
      ...game,
      status: held.status,
      home_score: held.final.homeScore,
      away_score: held.final.awayScore,
      completed_at: held.final.completedAt ?? game.completed_at,
      espn,
    };
  }
  if (!held || held.status !== game.status || !leagueGameStreamable(game)) return game;
  if (game.status === 'live' && !held.live) return game;

  let changed = false;
  const next: LeagueGameBrief = { ...game };
  if (
    held.homeProbability !== null &&
    held.homeProbability !== game.home_win_probability
  ) {
    next.home_win_probability = held.homeProbability;
    changed = true;
  }
  if (
    held.homeProbability !== null &&
    held.awayProbability !== null &&
    (game.current_odds?.home_probability !== held.homeProbability ||
      game.current_odds?.away_probability !== held.awayProbability)
  ) {
    next.current_odds = {
      ...(game.current_odds ?? {}),
      home_probability: held.homeProbability,
      away_probability: held.awayProbability,
    };
    changed = true;
  }
  if (held.live) {
    if (next.home_score !== held.live.homeScore) {
      next.home_score = held.live.homeScore;
      changed = true;
    }
    if (next.away_score !== held.live.awayScore) {
      next.away_score = held.live.awayScore;
      changed = true;
    }
    const espn = game.espn ?? {};
    if ((espn.period ?? null) !== held.live.period || (espn.game_clock ?? null) !== held.live.clock) {
      const nextEspn = { ...espn };
      if (held.live.period) nextEspn.period = held.live.period;
      else delete nextEspn.period;
      if (held.live.clock) nextEspn.game_clock = held.live.clock;
      else delete nextEspn.game_clock;
      next.espn = nextEspn;
      changed = true;
    }
  }
  return changed ? next : game;
}

export function overlayLeagueGamePreview(
  game: LeagueGameBrief,
  state: BlendPreviewState | null | undefined,
  now: number,
  held?: HeldLeagueGame | null,
): LeagueGameBrief {
  if (!state || held?.final || !leagueGameStreamable(game)) return game;
  const meta = game as LeagueGameBrief & {
    blend_fold_revision?: unknown;
    hero_probability_source?: string | null;
  };
  const p = displayedPreview(
    state,
    {
      id: game.id,
      status: held?.status ?? game.status,
      hero_probability_source: held?.heroSource ?? meta.hero_probability_source ?? null,
      blend_fold_revision: held?.revision ?? meta.blend_fold_revision,
      sport: game.sport ?? null,
    },
    now,
  );
  if (p === null) return game;

  const drawProb = (game.current_odds as { draw_probability?: number | null } | undefined)?.draw_probability;
  const hasDraw = sportPricesADraw(game.sport) || drawProb != null;
  if (hasDraw && state.pAway == null) return game;

  const away = state.pAway != null ? state.pAway : Number((1 - p).toFixed(6));
  return {
    ...game,
    home_win_probability: p,
    current_odds: {
      ...(game.current_odds ?? {}),
      home_probability: p,
      away_probability: away,
    },
  };
}

export function adoptLeagueMarketCards(
  book: LeagueMarketBook,
  markets: LeagueMarket[],
  response: DiscoverPriceCards,
  requested: Set<number>,
): LeagueMarketBook {
  if (!Array.isArray(response?.items)) return book;
  const byId = new Map(markets.map((m) => [m.id, m]));
  let next = book;
  for (const item of response.items) {
    if (item.type !== 'futures') continue;
    const fresh = item.data as FeedFuturesData;
    const served = byId.get(fresh.id);
    if (!served || !requested.has(fresh.id) || !leagueMarketStreamable(served)) continue;
    if (response.dispositions?.[`futures-${fresh.id}`] !== 'updated') continue;
    if (fresh.source !== served.source || marketResolved(fresh)) continue;

    const held = next.get(fresh.id);
    let legs: Map<number, HeldLeagueLeg> | null = null;
    for (const row of fresh.top_outcomes ?? []) {
      const prior = held?.get(row.id);
      const revision = parseMs((row as { price_revision_at?: unknown }).price_revision_at);
      if (prior) {
        if (prior.revision !== null && (revision === null || revision < prior.revision)) continue;
        if (prior.probability === row.probability && prior.revision === revision) continue;
      }
      legs ??= new Map(held ?? []);
      legs.set(row.id, { probability: row.probability ?? null, revision });
    }
    if (!legs) continue;
    if (next === book) next = new Map(book);
    next.set(fresh.id, legs);
  }
  return next;
}

export function patchLeagueMarketFromBook(
  market: LeagueMarket,
  book: LeagueMarketBook,
): LeagueMarket {
  const held = book.get(market.id);
  if (!held || !leagueMarketStreamable(market)) return market;
  let changed = false;
  const nextOutcomes = market.top_outcomes.map((row) => {
    if (row.settled) return row;
    const leg = held.get(row.id);
    if (!leg || leg.probability === row.probability) return row;
    changed = true;
    return { ...row, probability: leg.probability };
  });
  return changed ? { ...market, top_outcomes: nextOutcomes } : market;
}

export function overlayLeagueMarketPreview(
  market: LeagueMarket,
  previews: MarketPreviews,
  now: number,
  book?: LeagueMarketBook,
): LeagueMarket {
  if (!leagueMarketStreamable(market)) return market;
  const state = previews[market.id];
  if (!state || state.source !== market.source) return market;
  const heldLegs = book?.get(market.id);
  let changed = false;
  const nextOutcomes = market.top_outcomes.map((row) => {
    if (row.settled || row.probability === null) return row;
    const leg = state.legs[String(row.id)];
    if (!leg || leg.expiresAt <= now) return row;
    const observedMs = Date.parse(leg.observedAt);
    const committedRev = heldLegs?.get(row.id)?.revision ?? null;
    if (committedRev !== null && Number.isFinite(observedMs) && observedMs <= committedRev) {
      return row;
    }
    if (leg.p === row.probability) return row;
    changed = true;
    return { ...row, probability: leg.p };
  });
  return changed ? { ...market, top_outcomes: nextOutcomes } : market;
}
