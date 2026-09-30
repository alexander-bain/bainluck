import { API_URL, type ApiError, type GameMarketsResponse } from './api';

export interface OpenWinnerQuote {
  event_id: number; market_id: number; market_name: string; source: string; status: string;
  observed_at: string | null;
  outcomes: { outcome_id: number; side: string; name: string; probability: number; observed_at: string | null }[];
}
export interface LiveGameMarkets extends GameMarketsResponse {
  stream_market_ids?: number[];
  outcome_market_ids?: Record<string, number>;
  outcome_revision_at?: Record<string, string | null>;
  outcome_observed_at?: Record<string, string | null>;
  open_winner_quote?: OpenWinnerQuote | null;
  closed_winner_market_ids?: number[];
}

type WireRow = Record<string, unknown>;
type Row = { key: string; prices: unknown[]; source: unknown; markets: number[]; contributors: string[];
  hit: unknown; winner: unknown; actual: unknown; priced: boolean };
const positive = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const ids = (value: unknown): number[] => Array.isArray(value) ? value.filter(positive) : [];
const grade = (value: unknown): boolean | null => typeof value === 'boolean' ? value : null;
const instant = (value: string | null | undefined): number | null => {
  const m = value?.match(/^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$/);
  if (!m) return null;
  const seconds = Date.parse(m[1] + m[3]);
  return Number.isFinite(seconds) ? seconds * 1000 + Number((m[2] ?? '').padEnd(6, '0').slice(0, 6)) : null;
};
const finished = (status: string) => ['completed', 'closed', 'final', 'settled'].includes(status);

function rows(body: LiveGameMarkets): Row[] {
  const result: Row[] = [];
  const add = (key: string, row: WireRow, inheritedMarkets: number[] = []) => {
    const prices = ['probability', 'over_probability'].filter(k => k in row).map(k => row[k]);
    result.push({ key, prices, source: row.source,
      markets: [...new Set([...inheritedMarkets, ...ids(row._market_ids), ...ids([row._market_id])])],
      contributors: ids(row.contributor_outcome_ids).map(String), hit: grade(row.hit), winner: grade(row.is_winner),
      actual: row.actual ?? null, priced: prices.some(value => typeof value === 'number' && Number.isFinite(value)) });
  };
  for (const section of ['totals', 'player_props', 'team_totals', 'spreads', 'period_markets', 'other'] as const) {
    for (const row of (body[section] ?? []) as unknown as WireRow[]) {
      add(JSON.stringify([section, row.market_name, row.outcome_name, row.threshold, row.period]), row);
    }
  }
  for (const matchup of (body.matchups ?? []) as unknown as WireRow[]) {
    for (const row of (matchup.outcomes ?? []) as WireRow[]) {
      add(JSON.stringify(['matchup', matchup.market_name, row.name]), { ...row, source: matchup.source },
        [...ids(matchup._market_ids), ...ids([matchup._market_id])]);
    }
  }
  if (body.open_winner_quote) {
    const quote = body.open_winner_quote;
    result.push({ key: `winner:${quote.market_id}`, prices: quote.outcomes.map(row => row.probability),
      source: quote.source, markets: [quote.market_id], contributors: quote.outcomes.map(row => String(row.outcome_id)),
      hit: null, winner: null, actual: null, priced: true });
  }
  // #9579: display fields do not name a row — four Kalshi "Both teams to score · Yes" markets share
  // all of them. A colliding key is qualified by its markets, then by an ordinal, so one read never
  // refuses itself (on the first read that left the page with no props at all).
  const count = new Map<string, number>();
  result.forEach(row => count.set(row.key, (count.get(row.key) ?? 0) + 1));
  const seen = new Map<string, number>();
  for (const row of result) {
    if (count.get(row.key)! < 2) continue;
    const qualified = JSON.stringify([row.key, [...row.markets].sort((a, b) => a - b)]);
    const n = seen.get(qualified) ?? 0;
    seen.set(qualified, n + 1);
    row.key = n ? JSON.stringify([qualified, n]) : qualified;
  }
  return result;
}

export function boundOpenWinnerQuote(body: LiveGameMarkets): OpenWinnerQuote | null {
  const quote = body.open_winner_quote;
  if (!quote || !finished(body.status) || quote.event_id !== body.event_id || quote.status !== 'open' ||
      !positive(quote.market_id) || !body.stream_market_ids?.includes(quote.market_id) ||
      !['kalshi', 'polymarket'].includes(quote.source) || body.closed_winner_market_ids?.includes(quote.market_id)) return null;
  const sides = new Set(quote.outcomes.map(row => row.side));
  const outcomes = new Set(quote.outcomes.map(row => row.outcome_id));
  if (!sides.has('home') || !sides.has('away') || sides.size !== quote.outcomes.length || outcomes.size !== quote.outcomes.length ||
      quote.outcomes.some(row => !positive(row.outcome_id) || !row.name?.trim() || body.outcome_market_ids?.[String(row.outcome_id)] !== quote.market_id ||
        !['home', 'away', 'draw'].includes(row.side) || !Number.isFinite(row.probability) || row.probability < 0 || row.probability > 1)) return null;
  return quote;
}

/** Adopt a coherent rendered body. Revisions order it; none certify quote age. */
export function createGameMarketsReconciler() {
  let held: LiveGameMarkets | undefined;
  let revisions = new Map<string, number>();
  let withdrawn = new Map<string, Set<string>>();
  const closed = new Set<number>();
  return {
    current: () => held,
    adopt(incoming: LiveGameMarkets): LiveGameMarkets | undefined {
      if (held && incoming.event_id !== held.event_id) return held;
      ids(incoming.closed_winner_market_ids).forEach(id => closed.add(id));
      const fenceClosed = (body: LiveGameMarkets): LiveGameMarkets => ({ ...body,
        closed_winner_market_ids: [...closed],
        open_winner_quote: body.open_winner_quote && closed.has(body.open_winner_quote.market_id) ? null : boundOpenWinnerQuote(body) });
      if (held) held = fenceClosed(held);
      incoming = fenceClosed(incoming);
      const nextRows = rows(incoming);
      const next = new Map(nextRows.map(row => [row.key, row]));
      if (next.size !== nextRows.length) return held;
      const clocks = new Map(Object.entries(incoming.outcome_revision_at ?? {}).flatMap(([id, value]) => {
        const date = instant(value); return date === null ? [] : [[id, date] as [string, number]];
      }));
      if (!held) {
        revisions = clocks;
        nextRows.filter(row => !row.priced).forEach(row => withdrawn.set(row.key, new Set(row.contributors)));
        return held = incoming;
      }
      if (finished(held.status) && (!finished(incoming.status) ||
          (held.home_score != null && held.home_score !== incoming.home_score) ||
          (held.away_score != null && held.away_score !== incoming.away_score))) return held;
      const winnerSelection = !!held.open_winner_quote && !!incoming.open_winner_quote && held.open_winner_quote.market_id !== incoming.open_winner_quote.market_id;
      const previous = rows(held), before = new Map(previous.map(row => [row.key, row]));
      const nextWithdrawn = new Map(withdrawn);
      const changed = new Set<number>();
      for (const [id, date] of clocks) {
        const prior = revisions.get(id);
        if (prior !== undefined && date < prior) return held;
        if (prior === undefined || date > prior) {
          const market = incoming.outcome_market_ids?.[id]; if (market) changed.add(market);
        }
      }
      for (const [id, market] of Object.entries(incoming.outcome_market_ids ?? {})) {
        if (held.outcome_market_ids?.[id] !== market) changed.add(market);
      }
      for (const prior of previous) {
        const row = next.get(prior.key);
        if ((prior.hit !== null && row?.hit !== prior.hit) || (prior.winner !== null && row?.winner !== prior.winner) ||
            ((prior.hit !== null || prior.winner !== null) && prior.actual !== null && row?.actual !== prior.actual)) return held;
        if (!row?.priced && !(winnerSelection && prior.key.startsWith('winner:'))) { nextWithdrawn.set(prior.key, new Set(prior.contributors)); prior.markets.forEach(id => changed.add(id)); }
      }
      const script = new Map((incoming.props_script ?? []).map(row => [row.key, row]));
      if ((held.props_script ?? []).some(row => row.graded_result != null && script.get(row.key)?.graded_result !== row.graded_result)) return held;
      const newGrade = (row: Row) => (before.get(row.key)?.hit == null && row.hit !== null) ||
        (before.get(row.key)?.winner == null && row.winner !== null);
      nextRows.filter(newGrade).forEach(row => row.markets.forEach(id => changed.add(id)));
      for (const row of nextRows) {
        const prior = before.get(row.key), terminal = newGrade(row);
        if (!row.priced) {
          nextWithdrawn.set(row.key, new Set([...row.contributors, ...(prior?.contributors ?? [])])); continue;
        }
        for (const id of row.contributors) {
          const known = revisions.get(id), date = clocks.get(id);
          if (known !== undefined && (date !== undefined ? date < known : !terminal)) return held;
        }
        const removed = withdrawn.get(row.key);
        if (!terminal && removed) {
          const contributors = new Set([...removed, ...row.contributors]);
          if (!contributors.size || [...contributors].some(id => !clocks.has(id)) ||
              ![...contributors].some(id => clocks.get(id)! > (revisions.get(id) ?? -Infinity))) return held;
        }
        if (!prior && !terminal && !row.key.startsWith('winner:') && row.contributors.length && row.contributors.every(id => revisions.has(id)) &&
            !row.contributors.some(id => (clocks.get(id) ?? -Infinity) > revisions.get(id)!)) return held;
        if (prior?.priced && (JSON.stringify(prior.prices) !== JSON.stringify(row.prices) || prior.source !== row.source) &&
            !terminal && !row.markets.some(id => changed.has(id))) return held;
        nextWithdrawn.delete(row.key);
      }
      for (const [id, date] of clocks) revisions.set(id, Math.max(date, revisions.get(id) ?? date));
      withdrawn = nextWithdrawn;
      return held = incoming;
    },
  };
}

/** Fresh path deliberately never claims SSR/boot data or the shared client cache. */
export async function fetchFreshGameMarkets(eventId: number, signal: AbortSignal): Promise<LiveGameMarkets> {
  const abort = new AbortController();
  const cancel = () => abort.abort();
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  const timeout = setTimeout(cancel, 10_000);
  try {
  const response = await fetch(`${API_URL}/api/events/${eventId}/game-markets?fresh=true`, {
    cache: 'no-store', signal: abort.signal, headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    const error = new Error(`Game markets read failed (${response.status})`) as ApiError;
    error.status = response.status;
    if (response.status === 429) {
      const body = await response.json().catch(() => ({}));
      const seconds = Number(body.retry_after);
      const header = response.headers.get('Retry-After');
      const delay = header && Number.isFinite(Number(header)) ? Number(header) * 1000 : header ? Date.parse(header) - Date.now() : NaN;
      error.retryAfterMs = Math.max(0, Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : Number.isFinite(delay) && delay > 0 ? delay : 60_000);
    }
    throw error;
  }
  return await response.json();
  } finally {
    clearTimeout(timeout);
    signal.removeEventListener('abort', cancel);
  }
}
