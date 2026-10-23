import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import LiveConnectionStatus from '@/components/event/LiveConnectionStatus';
import { useObservationCount } from '@/hooks/useObservationCount';
import { displayedPreview, displayedProbabilityObservedAt, previewAfter, type BlendPreviewState } from '@/lib/blendPreview';
import { formatObservationClock } from '@/lib/event/liveConnectionStatus';
import { resolveProbability } from '@/lib/eventKeyStats';
import type { EventDetailResponse, EventHistoryResponse } from '@/lib/types';

const BASE = Date.UTC(2026, 9, 21, 20, 0, 0);
const at = (ms: number) => new Date(BASE + ms).toISOString();
type Props = { eventId: number; committed: string | null; preview: BlendPreviewState | null; now: number; fullscreen?: boolean; visible?: boolean };
function Harness({ eventId, committed, preview, now, fullscreen, visible = true }: Props) {
  const event = { id: eventId, status: 'live', hero_probability_source: 'blend', blend_fold_revision: { [eventId]: 10 } };
  const observed = displayedProbabilityObservedAt(event, preview, now, committed);
  const count = useObservationCount(eventId, visible ? observed : null);
  const delivery = displayedPreview(preview, event, now) === null ? 'committed' : 'dnpl';
  const status = (announces: boolean) => <LiveConnectionStatus
    presentation={{ label: 'Connected · waiting', tone: 'live', breathes: true, announcement: '' }}
    observation={{ eventId, count, delivery }} priceObservedAt={observed}
    scoreShown={false} scoreConfirmedAt={null} oldestFact={null} now={now} announces={announces}
  />;
  return visible ? <>{status(true)}{fullscreen && status(false)}</> : null;
}
function pending(observed: string | null, p = .6, eventId = 1) {
  return previewAfter(null, {
    event_id: eventId, p, status: 'live', display_observed_at: observed ?? undefined,
    preview: { kind: 'blend', epoch: 1, seq: 1, base_rev: 10, ttl_ms: 1000 },
  }, eventId, BASE);
}
type N = { childNodes: N[]; textContent: string; [key: string]: unknown };
function all(node: N, predicate: (n: N) => boolean): N[] {
  return [...(predicate(node) ? [node] : []), ...node.childNodes.flatMap(child => all(child, predicate))];
}
function mounted(initial: Props) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = (props: Props) => act(() => root.render(<Harness {...props} />));
  render(initial);
  return {
    render,
    copies: () => all(host as unknown as N, n => n['data-testid'] === 'live-connection-status'),
    close: () => act(() => root.unmount()),
  };
}
function click(node: N) {
  const button = all(node, n => n.tagName === 'BUTTON')[0];
  const key = Object.keys(button).find(k => k.startsWith('__reactProps'))!;
  act(() => (button[key] as { onClick: () => void }).onClick());
}

test('counter advances within a second even at equal probability, but age, duplicate and backward clocks do not count', () => {
  const props: Props = { eventId: 1, committed: at(100), preview: null, now: BASE };
  const view = mounted(props);
  try {
    expect(view.copies()[0]['data-observation-count']).toBe('1');
    props.preview = pending(at(200)); // same .6 probability; genuinely newer observation
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    expect(view.copies()[0]['data-observation-at']).toBe(at(200));
    expect(view.copies()[0]['data-observation-delivery']).toBe('dnpl');
    props.now = BASE + 50;
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending(at(150));
    view.render(props);
    expect(view.copies()[0]['data-observation-at']).toBe(at(150));
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending(at(200));
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending(at(201));
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('3');
  } finally { view.close(); }
});

test('invalid observation, expiry fallback, reset and restoration do not manufacture updates', () => {
  const props: Props = { eventId: 1, committed: at(100), preview: null, now: BASE };
  const view = mounted(props);
  try {
    props.preview = pending(at(400));
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending('not-a-time');
    view.render(props);
    expect(view.copies()[0]['data-observation-at']).toBe('');
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending(at(400)); props.now = BASE + 1000;
    view.render(props);
    expect(view.copies()[0]['data-observation-at']).toBe(at(100));
    expect(view.copies()[0]['data-observation-delivery']).toBe('committed');
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = null;
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.preview = pending(at(400)); props.now = BASE + 500;
    view.render(props);
    expect(view.copies()[0]['data-observation-delivery']).toBe('dnpl');
    expect(view.copies()[0]['data-observation-count']).toBe('2');
  } finally { view.close(); }
});

test('one page owner survives disclosure/fullscreen toggles and resets on event navigation', () => {
  const props: Props = { eventId: 1, committed: null, preview: null, now: BASE };
  const view = mounted(props);
  try {
    expect(view.copies()[0]['data-observation-count']).toBe('0');
    props.committed = at(100);
    view.render(props);
    click(view.copies()[0]); click(view.copies()[0]);
    props.fullscreen = true; props.preview = pending(at(200));
    view.render(props);
    expect(view.copies()).toHaveLength(2);
    for (const copy of view.copies()) {
      expect(copy['data-observation-count']).toBe('2');
      expect(copy['data-observation-at']).toBe(at(200));
      expect(copy['data-observation-event-id']).toBe('1');
    }
    props.fullscreen = false;
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.eventId = 2; props.preview = null; props.committed = at(50);
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('1');
    expect(view.copies()[0]['data-observation-event-id']).toBe('2');
    props.eventId = 1;
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('1');
  } finally { view.close(); }
});

test('probability wall clock includes milliseconds in local time and the timezone', () => {
  expect(formatObservationClock(at(123), true)).toBe('Oct 21, 8:00:00.123 PM UTC');
  expect(formatObservationClock(at(123))).toBe('Oct 21, 8:00:00 PM UTC');
});


test('an undisplayed error/loading interval contributes no observations or high-water', () => {
  const props: Props = { eventId: 1, committed: at(100), preview: null, now: BASE };
  const view = mounted(props);
  try {
    props.visible = false; props.committed = at(400);
    view.render(props);
    expect(view.copies()).toHaveLength(0);
    props.visible = true; props.committed = at(200);
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('2');
    props.committed = at(300);
    view.render(props);
    expect(view.copies()[0]['data-observation-count']).toBe('3');
  } finally { view.close(); }
});

test('equal numbers do not turn history or opening selection into hero delivery', () => {
  const event = { id: 1, status: 'live', hero_probability: .6, hero_probability_source: 'blend',
    hero_probability_away: .4, opening_odds: { home_probability: .6, away_probability: .4 } } as EventDetailResponse;
  const history = { aggregate_line: [{ timestamp: at(100), home_probability: .6 }] } as EventHistoryResponse;
  const hero = resolveProbability(event, history, null, true, false, false, false, true);
  const historical = resolveProbability({ ...event, hero_probability_source: 'opening' }, history, null, true, false, false, false, true);
  const opening = resolveProbability({ ...event, status: 'completed' }, history, null, false, true, false, false, true);
  expect([hero.homeProb, historical.homeProb, opening.homeProb]).toEqual([.6, .6, .6]);
  expect(hero.selectedProbabilitySource).toBe('hero-blend');
  expect(historical.selectedProbabilitySource).toBe('history');
  expect(opening.selectedProbabilitySource).toBeUndefined();
});
