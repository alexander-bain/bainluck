/**
 * #10090 — Search's game cards re-price live (Fable's decision A, Nov 8).
 *
 * The same transport as Search's futures cards (`lib/searchFuturesStream`):
 * a game's price is re-read through `/api/feed/price-cards?event_ids=`, which
 * folds the blend from one row read and stamps it with `blend_fold_revision`.
 * Live games get their `/api/events/{id}/stream` as the "read now" signal;
 * scheduled games refresh on the dispatcher's 60 s recovery read.
 *
 * THE RULES, each one a sentence from that decision:
 *
 * * **A live card's probability is never newer than its score.** A live game
 *   is patched only from a card that carries `live_state` (period and clock
 *   from the same row read as its score and probability), and then all of
 *   probability, score and clock move together. A card without it (an older
 *   server) patches nothing on a live game.
 * * **A game that changes status stops updating** — with one exception.
 *   Only a card whose status equals the served one is adopted, EXCEPT a live
 *   game whose card says it finished (`completed`/`closed`, decision (b), Fable
 *   Nov 9). That card takes the status, final score and `completed_at` from
 *   the same read, so the open page shows the FINAL card a fresh search shows
 *   (`EventCard` reads a finished game's probabilities from the served
 *   `opening_odds`; this module never touches them on a finish).
 * * **Never backwards.** The fold revision must be the same or newer than the
 *   one held, and the blend's own reading time no older.
 * * **Probability fields only, plus score and clock on a live game.** The
 *   card's `win_probability_sources` has a different shape from Search's and
 *   is never copied; spreads, totals and everything else keep their served
 *   values.
 */
import type { CurrentOdds, Event, FeedEventData } from '@/lib/types';
import type { DiscoverPriceCards } from '@/lib/discover/priceRefresh';
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from '@/lib/foldRevision';
import { isFinishedStatus } from '@/lib/eventState';

const PRICED_STATUSES = new Set(['scheduled', 'live']);

/** What one adopted card says about one game. */
export interface HeldGame {
  status: string;
  revision: FoldRevision;
  observedMs: number | null;
  homeProbability: number | null;
  awayProbability: number | null;
  heroProbability: number | null;
  heroProbabilityAway: number | null;
  heroSource: string | null;
  /** Live games only: the score and clock read with the probability. */
  live: { homeScore: number | null; awayScore: number | null; period: string | null; clock: string | null } | null;
  /** A live game the card says finished: its final score and stamp (decision (b)). */
  final?: { homeScore: number | null; awayScore: number | null; completedAt: string | null } | null;
}
export type SearchEventBook = Map<number, HeldGame>;

export function searchEventStreamable(event: Event): boolean {
  return PRICED_STATUSES.has(event.status);
}

function ms(raw: unknown): number | null {
  if (typeof raw !== 'string' || !raw) return null;
  const value = Date.parse(raw);
  return Number.isFinite(value) ? value : null;
}

function liveState(raw: unknown): { period: string | null; clock: string | null } | null {
  if (!raw || typeof raw !== 'object') return null;
  const state = raw as { period?: unknown; game_clock?: unknown };
  const text = (value: unknown) => (typeof value === 'string' && value ? value : null);
  return { period: text(state.period), clock: text(state.game_clock) };
}

/** The book after one `price-cards` answer; `book` itself when nothing was adopted. */
export function adoptSearchEventCards(
  book: SearchEventBook,
  events: Event[],
  response: DiscoverPriceCards,
  requested: Set<number>,
): SearchEventBook {
  if (!Array.isArray(response?.items)) return book;
  const byId = new Map(events.map((e) => [e.id, e]));
  let next = book;
  for (const item of response.items) {
    if (item.type !== 'event') continue;
    const fresh = item.data as FeedEventData & {
      blend_fold_revision?: unknown; hero_probability_observed_at?: string | null;
      hero_probability?: number | null; hero_probability_away?: number | null;
      hero_probability_source?: string | null; live_state?: unknown; completed_at?: string | null;
    };
    const served = byId.get(fresh.id);
    if (!served || !requested.has(fresh.id) || !searchEventStreamable(served)) continue;
    if (response.dispositions?.[`event-${fresh.id}`] !== 'updated') continue;
    const finished = served.status === 'live' && isFinishedStatus(fresh.status);
    if (fresh.status !== served.status && !finished) continue;
    const revision = parseFoldRevision(fresh.blend_fold_revision);
    if (!revision) continue;
    let live: HeldGame['live'] = null;
    let final: HeldGame['final'] = null;
    if (finished) {
      // Terminal, so it must carry the result: no final score, no finish (a
      // later read can still finish it).
      if (typeof fresh.home_score !== 'number' || typeof fresh.away_score !== 'number') continue;
      final = { homeScore: fresh.home_score, awayScore: fresh.away_score,
        completedAt: fresh.completed_at ?? null };
    } else if (served.status === 'live') {
      const state = liveState(fresh.live_state);
      if (!state) continue;
      live = { homeScore: fresh.home_score ?? null, awayScore: fresh.away_score ?? null, ...state };
    }
    const observedMs = ms(fresh.hero_probability_observed_at);
    const held = next.get(fresh.id);
    // A finish is terminal: nothing after it, a late live card included, reopens the game.
    if (held?.final) continue;
    if (held) {
      const order = compareFoldRevision(revision, held.revision);
      if (order !== 'newer' && order !== 'same') continue;
      // A finish adopts a status and a result, not a newer probability, so the
      // blend's reading time does not gate it (a settled card has none).
      if (!final && held.observedMs !== null && (observedMs === null || observedMs < held.observedMs)) continue;
    }
    const game: HeldGame = {
      status: fresh.status,
      revision,
      observedMs,
      homeProbability: fresh.current_odds?.home_probability ?? null,
      awayProbability: fresh.current_odds?.away_probability ?? null,
      heroProbability: typeof fresh.hero_probability === 'number' ? fresh.hero_probability : null,
      heroProbabilityAway: typeof fresh.hero_probability_away === 'number' ? fresh.hero_probability_away : null,
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

/** The served card with its adopted reading applied; `event` itself when nothing changed. */
export function patchSearchEvent(event: Event, book: SearchEventBook): Event {
  const game = book.get(event.id);
  if (game?.final && event.status === 'live') {
    // The result, from one read: status, score and stamp together; the live
    // period and clock go, and the served probabilities stay (a finished card
    // reads `opening_odds`).
    const { period: _period, game_clock: _clock, ...espn } = event.espn ?? {};
    return {
      ...event, status: game.status, home_score: game.final.homeScore, away_score: game.final.awayScore,
      completed_at: game.final.completedAt ?? event.completed_at, espn,
    } as Event;
  }
  if (!game || game.status !== event.status || !searchEventStreamable(event)) return event;
  if (event.status === 'live' && !game.live) return event;
  const next: Event & { hero_probability_source?: string | null } = { ...event };
  let changed = false;
  const set = <K extends keyof typeof next>(key: K, value: (typeof next)[K]) => {
    if (next[key] !== value) { next[key] = value; changed = true; }
  };
  if (event.current_odds && game.homeProbability !== null && game.awayProbability !== null &&
      (event.current_odds.home_probability !== game.homeProbability ||
       event.current_odds.away_probability !== game.awayProbability)) {
    next.current_odds = { ...event.current_odds, home_probability: game.homeProbability,
      away_probability: game.awayProbability } as CurrentOdds;
    changed = true;
  }
  if (game.heroProbability !== null) set('hero_probability', game.heroProbability);
  if (game.heroProbabilityAway !== null) set('hero_probability_away', game.heroProbabilityAway);
  if ('hero_probability_source' in event && game.heroSource !== null) set('hero_probability_source', game.heroSource);
  if (game.live) {
    set('home_score', game.live.homeScore);
    set('away_score', game.live.awayScore);
    const espn = event.espn ?? {};
    if ((espn.period ?? null) !== game.live.period || (espn.game_clock ?? null) !== game.live.clock) {
      const nextEspn = { ...espn };
      if (game.live.period) nextEspn.period = game.live.period; else delete nextEspn.period;
      if (game.live.clock) nextEspn.game_clock = game.live.clock; else delete nextEspn.game_clock;
      next.espn = nextEspn;
      changed = true;
    }
  }
  return changed ? next : event;
}
