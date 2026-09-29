import { canSubscribeEventQuotes, coversQuoteRevision, quotePairCoversTrigger } from '@/lib/eventQuoteStream';
import { applyLiveFrame, frameInvalidatesFoldedBlend } from '@/lib/eventLivePush';
import { appendHeroObservation, mergeLiveChartHistory, quoteChartFrames, rememberLiveChartFrame } from '@/lib/liveChartHistory';
import { reconcileEventPoll, keepNewerHeldHeadline } from '@/lib/reconcileEventPoll';
import { resolveProbability } from '@/lib/eventKeyStats';
import type { EventDetailResponse, EventHistoryResponse } from '@/lib/types';
const t0 = '2026-09-28T23:00:00Z', t1 = '2026-09-28T23:00:05Z';
const hero = {
  id: 14780549, status: 'scheduled', hero_probability: .4, hero_probability_away: .6,
  hero_probability_source: 'blend', hero_probability_observed_at: t0,
  blend_fold_revision: { '14780549': 10 }, home_score: null,
  win_probability_sources: { kalshi: { value: .4, updated_at: t0, display_name: 'Kalshi' } },
  current_odds: { home_probability: .2, away_probability: .8, source: 'aggregate' },
};
const frame = {
  event_id: hero.id, status: 'scheduled', p: .6, source: 'kalshi', source_value: .6,
  updated_at: t1, rev: { '14780549': 11 },
};
const history = {
  event_id: hero.id, history: [], aggregate_line: [{ timestamp: t0, home_probability: .4 }],
  blend_edge_pinned: true, blend_edge_observed_at: t0, blend_edge_fold_revision: hero.blend_fold_revision,
};

test.each(['scheduled', 'suspended', 'live'])('%s moves hero, source and chart without promoting sport state', status => {
  const held = { ...hero, status }, quote = { ...frame, status };
  expect(canSubscribeEventQuotes(held)).toBe(true);
  const adopted = applyLiveFrame(held, quote)!;
  expect(adopted.status).toBe(status);
  expect(adopted.home_score).toBeNull();
  expect(adopted.hero_probability).toBe(.6);
  expect(adopted.win_probability_sources.kalshi.value).toBe(.6);
  const points = rememberLiveChartFrame([], quote, hero.id);
  const chart = mergeLiveChartHistory(history, quoteChartFrames(points, adopted))!;
  expect(chart.aggregate_line.at(-1)?.home_probability).toBe(.6);
  const displayed = resolveProbability(adopted as unknown as EventDetailResponse,
    chart as unknown as EventHistoryResponse, null, status === 'live', false, status === 'suspended');
  expect(displayed.homeProb).toBe(.6);
  expect(displayed.probSourceLabel).toBe(status === 'live' ? 'Live · Bain Luck blend' : 'Bain Luck blend');
  expect(reconcileEventPoll(held, quote).hero_probability).toBe(.6);
  expect(keepNewerHeldHeadline(held, adopted).hero_probability).toBe(.6);
  expect(applyLiveFrame(adopted, { ...quote, p: .1, rev: { '14780549': 9 } })).toBe(adopted);
  expect(appendHeroObservation(history, adopted, history)?.aggregate_line.at(-1)?.home_probability).toBe(.6);
});

test.each(['completed', 'closed', 'cancelled', 'postponed', 'unknown'])('%s refuses quote adoption', status => {
  const terminal = { ...hero, status, hero_probability: 1 };
  expect(canSubscribeEventQuotes(terminal)).toBe(false);
  expect(applyLiveFrame(terminal, frame)).toBe(terminal);
  expect(reconcileEventPoll(terminal, frame)).toBe(terminal);
  expect(rememberLiveChartFrame([], { ...frame, status }, hero.id)).toEqual([]);
});

test('completed timestamp refuses a stale scheduled status', () => {
  expect(canSubscribeEventQuotes({ status: 'scheduled', completed_at: t0 })).toBe(false);
});

test('opening and absent-status null invalidations request a pair without adopting raw values', () => {
  const opening = { ...hero, hero_probability_source: 'opening', blend_fold_revision: undefined };
  expect(frameInvalidatesFoldedBlend(opening, frame)).toBe(true);
  expect(applyLiveFrame(opening, frame)).toBe(opening);
  expect(frameInvalidatesFoldedBlend(opening, { rev: frame.rev, p: null })).toBe(true);
  expect(frameInvalidatesFoldedBlend(hero, { rev: frame.rev, p: null })).toBe(true);
  expect(quoteChartFrames(rememberLiveChartFrame([], frame, hero.id), opening)).toEqual([]);
});

test('phase change requests detail instead of promoting sporting state', () => {
  expect(frameInvalidatesFoldedBlend(hero, { ...frame, status: 'live' })).toBe(true);
  expect(applyLiveFrame(hero, { ...frame, status: 'live' })).toBe(hero);
});

test('pair must cover triggering row, while extra fold rows are allowed', () => {
  const rev = { '14780549': 11, twin: 5 };
  const detail = { ...hero, blend_fold_revision: rev };
  const paired = { ...history, blend_edge_fold_revision: rev };
  expect(quotePairCoversTrigger(detail, paired, hero.id, frame.rev)).toBe(true);
  expect(coversQuoteRevision({ '14780549': 10, twin: 5 }, frame.rev)).toBe(false);
  expect(quotePairCoversTrigger(detail, history, hero.id, frame.rev)).toBe(false);
  expect(quotePairCoversTrigger(detail, paired, 15320435, frame.rev)).toBe(false);
  expect(quoteChartFrames(rememberLiveChartFrame([], frame, hero.id), detail)).toEqual([]);
  expect(frameInvalidatesFoldedBlend(detail, frame)).toBe(true);
});


test('delayed older revision with later observation cannot outrun the accepted hero', () => {
  const held = { ...hero, hero_probability: .55, blend_fold_revision: { '14780549': 11 } };
  const old = { ...frame, p: .9, rev: { '14780549': 10 } };
  expect(applyLiveFrame(held, old)).toBe(held);
  expect(quoteChartFrames(rememberLiveChartFrame([], old, hero.id), held)).toEqual([]);
  const historical = { ...old, updated_at: '2026-09-28T22:59:00Z' };
  expect(quoteChartFrames(rememberLiveChartFrame([], historical, hero.id), held)).toHaveLength(1);
});
