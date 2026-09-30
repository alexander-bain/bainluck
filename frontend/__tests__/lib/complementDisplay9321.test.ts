import { renderedComplementPercents, renderedDuelPercents } from '../../lib/renderedPercent';
import { chartAxisPercents, homeProbToChartAxis, resolveProbability } from '../../lib/eventKeyStats';
import type { EventDetailResponse } from '../../lib/types';

test('six-decimal wire grid keeps the server complement decision after chart-axis conversion', () => {
  const mismatches: number[] = [];
  for (let i = 0; i <= 1_000_000; i++) {
    const home = i / 1_000_000;
    const expected = renderedDuelPercents(Number((1 - home).toFixed(6)), home);
    const pair = renderedComplementPercents(home);
    const chart = chartAxisPercents(homeProbToChartAxis(home));
    if (pair[0] !== expected[0] || pair[1] !== expected[1] || chart.away !== expected[0] || chart.home !== expected[1]) mismatches.push(home);
  }
  expect(mismatches).toEqual([]);
});

test.each([
  [.444999, 56, 44], [.445, 56, 44], [.445001, 55, 45],
  [.554999, 45, 55], [.555, 44, 56], [.555001, 44, 56],
])('complement of %s retains the quoted tie and real neighbors', (home, awayPct, homePct) => {
  expect(renderedComplementPercents(home)).toEqual([awayPct, homePct]);
});

test.each([[0, '0%', '100%'], [1, '100%', '0%'], [.001, '<1%', '>99%'], [.999, '>99%', '<1%']])(
  'boundary labels preserve certainty only for real boundaries (%s)', (home, homeLabel, awayLabel) => {
    expect(chartAxisPercents(homeProbToChartAxis(home as number))).toMatchObject({homeLabel, awayLabel});
  },
);

test('independently served live pair keeps its own display and raw values', () => {
  const event = Object.freeze({status: 'live', hero_probability: .445, hero_probability_away: .5,
    hero_probability_source: 'blend'}) as EventDetailResponse;
  const resolved = resolveProbability(event, undefined, null, true, false);
  expect([resolved.awayPct, resolved.homePct]).toEqual(renderedDuelPercents(.5, .445));
  expect(resolved.homeProb).toBe(.445);
  expect(resolved.awayProb).toBe(.5);
});
