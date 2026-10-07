/** Mounted Search page: real fetch/race effects + navigation hook, stubbed leaf
 * cards and browser layout/history. Actual Chromium proof is recorded in #9731. */
import '../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import SearchPage from '@/app/search/page';
import { searchEvents, fetchSearchSuggestions } from '@/lib/api';
import type { SearchResponse } from '@/lib/types';

let mockParams = new URLSearchParams('q=Lakers');
const mockTrack = jest.fn();
const mockRouter = { push: jest.fn() };
jest.mock('next/navigation', () => ({ useSearchParams: () => mockParams, useRouter: () => mockRouter }));
jest.mock('next/link', () => ({ __esModule: true, default: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <a {...props}>{children}</a> }));
jest.mock('@/lib/api', () => ({ searchEvents: jest.fn(), fetchSearchSuggestions: jest.fn() }));
jest.mock('@/hooks', () => ({
  useAnalytics: () => ({ track: mockTrack }), usePageTracking: jest.fn(), useScrollDepth: jest.fn(), useEngagementTime: jest.fn(),
  usePinnedEvents: () => ({ isPinned: () => false, togglePin: jest.fn(), isMaxReached: false }),
  usePinnedFutures: () => ({ isPinned: () => false, togglePin: jest.fn(), isMaxReached: false }),
}));
jest.mock('@/lib/analytics', () => ({ trackEvent: jest.fn() }));
jest.mock('@/lib/searchFunnel', () => ({ markSearchDestination: jest.fn() }));
jest.mock('@/components/EventCard', () => ({ __esModule: true, default: ({ event }: { event: { id: number; away_team: string } }) => <a href={`/events/${event.id}`}>{event.away_team}</a> }));
jest.mock('@/components/FuturesCard', () => () => null);
jest.mock('@/components/SearchFamilyCard', () => () => null);
jest.mock('@/components/SearchTeamCard', () => () => null);
jest.mock('@/components/CategoryBrowser', () => () => <p>Browse categories</p>);
jest.mock('@/components/LeagueChips', () => () => null);
jest.mock('@/components/LoadingState', () => ({ __esModule: true, default: ({ message }: { message: string }) => <p>{message}</p> }));
jest.mock('@/components/ErrorState', () => ({ __esModule: true, default: ({ message }: { message: string }) => <p>{message}</p> }));
jest.mock('@/components/SearchDegradedState', () => () => <p>Search unavailable</p>);
jest.mock('@/components/discover/EndOfFeedCard', () => ({ END_OF_FEED_CATEGORIES: [] }));

const fetcher = searchEvents as jest.Mock;
let root: Root | undefined;
let host: HTMLElement;
let historyState: Record<string, unknown>;
let listeners: Map<string, Set<EventListener>>;
let cardAbsoluteTop: number;
const scrollTo = jest.fn((_x: number, y: number) => { window.scrollY = y; });
function descendants(node: HTMLElement): HTMLElement[] {
  return [node, ...Array.from(node.childNodes).flatMap(n => descendants(n as HTMLElement))];
}
function props(node: HTMLElement): Record<string, any> { // Same mounted-node seam as golfCurrentPrices8222.
  const key = Object.keys(node).find(k => k.startsWith('__reactProps$'))!;
  return (node as unknown as Record<string, Record<string, any>>)[key];
}
function response(query = 'Lakers', id = 15197567): SearchResponse {
  return {
    query, teams: [], futures: [], sports: [],
    results: [{ id, home_team: 'Spurs', away_team: query, commence_time: '2026-11-27T18:30:00Z' }] as SearchResponse['results'],
    pagination: { page: 1, per_page: 25, total_results: 1, total_pages: 1, has_prev: false, has_next: false },
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function mount() {
  host = document.createElement('div'); document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => { root!.render(<SearchPage />); });
}
function unmount() {
  act(() => root?.unmount()); root = undefined;
  if (host?.parentNode) document.body.removeChild(host);
}
async function rerender(params: string, state: Record<string, unknown> = { __NA: true }) {
  mockParams = new URLSearchParams(params); historyState = state;
  window.location.href = `https://www.bainluck.com/search?${params}`;
  await act(async () => { root!.render(<SearchPage />); });
}
function captureResult(modifiers: Record<string, unknown> = {}) {
  const wrapper = descendants(host).find(node => props(node)?.onClickCapture);
  if (!wrapper) return; // Original page has no capture; the final landing assertion must fail.
  const anchor = {
    href: 'https://www.bainluck.com/events/15197567', target: '',
    getAttribute: (name: string) => name === 'href' ? '/events/15197567' : null,
    hasAttribute: () => false,
    getBoundingClientRect: () => ({ top: cardAbsoluteTop - window.scrollY }),
  };
  act(() => props(wrapper!).onClickCapture({
    button: 0, defaultPrevented: false, target: { closest: () => anchor }, ...modifiers,
  }));
}
async function frames() { await act(async () => { await jest.advanceTimersByTimeAsync(32); }); }
function interrupt(type: string, key?: string) {
  act(() => listeners.get(type)?.forEach(fn => fn({ type, key } as unknown as Event)));
}
beforeEach(() => {
  jest.useFakeTimers();
  mockParams = new URLSearchParams('q=Lakers');
  historyState = { __NA: true, __PRIVATE_NEXTJS_INTERNALS_TREE: ['search'] };
  listeners = new Map(); cardAbsoluteTop = 1315.8;
  Object.assign(window, { scrollY: 968.8, innerHeight: 606, scrollTo, location: { href: 'https://www.bainluck.com/search?q=Lakers', origin: 'https://www.bainluck.com' } });
  Object.defineProperty(window, 'history', { configurable: true, value: {
    get state() { return historyState; },
    replaceState: jest.fn(state => { historyState = state; }),
  } });
  window.addEventListener = jest.fn((type: string, fn: EventListener) => { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type)!.add(fn); }) as typeof window.addEventListener;
  window.removeEventListener = jest.fn((type: string, fn: EventListener) => { listeners.get(type)?.delete(fn); }) as typeof window.removeEventListener;
  global.requestAnimationFrame = jest.fn(fn => setTimeout(() => fn(0), 16) as unknown as number);
  global.cancelAnimationFrame = jest.fn(id => clearTimeout(id));
  document.querySelectorAll = jest.fn(() => descendants(host).filter(n => props(n)?.href).map(n => ({
    href: new URL(props(n).href, window.location.href).href,
    getBoundingClientRect: () => ({ top: cardAbsoluteTop - window.scrollY }),
  }))) as unknown as typeof document.querySelectorAll;
  Object.defineProperty(document.documentElement, 'scrollHeight', { configurable: true, value: 6472 });
  fetcher.mockReset().mockResolvedValue(response());
  (fetchSearchSuggestions as jest.Mock).mockReset().mockResolvedValue({ suggestions: [] });
  scrollTo.mockClear(); mockTrack.mockClear();
});
afterEach(() => { if (root) unmount(); jest.useRealTimers(); });

it('returns to the clicked result only after its refetched list is committed; preserves Next history', async () => {
  await mount(); captureResult();
  const entry = historyState;
  expect(entry.__NA).toBe(true);
  expect(entry.__PRIVATE_NEXTJS_INTERNALS_TREE).toEqual(['search']);
  unmount();
  const back = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(back.promise);
  window.scrollY = 5866.4; historyState = entry;
  await mount(); await frames();
  expect(host.textContent).toContain('Searching for');
  expect(scrollTo).not.toHaveBeenCalled();
  await act(async () => { back.resolve(response()); }); await frames();
  expect(host.textContent).toContain('Results for');
  expect(scrollTo).toHaveBeenLastCalledWith(0, expect.closeTo(968.8, 3));
  expect(fetcher).toHaveBeenCalledTimes(2); // No stale-price result cache replaces the fresh read.
});

it('restores the card viewport slot even when refreshed results above it change height', async () => {
  await mount(); captureResult(); unmount();
  window.scrollY = 5866.4; cardAbsoluteTop += 200;
  await mount(); await frames();
  expect(scrollTo).toHaveBeenLastCalledWith(0, expect.closeTo(1168.8, 3));
});

it('handles repeated result visits and Back/Forward without overwriting the mark with the footer clamp', async () => {
  await mount(); captureResult(); const first = historyState; unmount();
  window.scrollY = 5866.4; await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(968.8);
  window.scrollY = 1050; captureResult(); const second = historyState; unmount();
  historyState = first; window.scrollY = 5866.4; await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(968.8); unmount();
  historyState = second; window.scrollY = 5866.4; await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(1050);
});

it.each(['q=Lakers&sport=basketball_nba', 'q=Lakers&page=2', 'q=Celtics', 'q='])('refuses another query/filter/page: %s', async params => {
  await mount(); captureResult(); const entry = historyState;
  await rerender(params, entry); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});

it('a fresh search for the same text does not inherit an older history entry', async () => {
  await mount(); captureResult(); unmount();
  historyState = { __NA: true }; window.scrollY = 0;
  await mount(); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});

it.each(['wheel', 'touchstart', 'keydown'])('does not snap the reader back after intentional %s input during loading', async type => {
  await mount(); captureResult(); unmount();
  const back = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(back.promise);
  await mount(); interrupt(type, 'PageDown');
  await act(async () => { back.resolve(response()); }); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});

it('keeps #1469 stale-response protection when a newer query wins and when the field is cleared', async () => {
  const old = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(old.promise);
  await mount(); await rerender('q=Celtics');
  await act(async () => { old.resolve(response('Old Lakers')); });
  expect(host.textContent).not.toContain('Old Lakers');
  const pending = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(pending.promise);
  await rerender('q=Warriors'); await rerender('q=');
  await act(async () => { pending.resolve(response('Late Warriors')); }); await frames();
  expect(host.textContent).toContain('Browse categories');
  expect(host.textContent).not.toContain('Late Warriors');
  expect(scrollTo).not.toHaveBeenCalled();
});

it('cancels a queued restore when the user navigates away before the frame', async () => {
  await mount(); captureResult(); unmount();
  await mount(); unmount(); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});

it('does not capture a modified click that leaves this tab in place', async () => {
  await mount(); const original = historyState;
  captureResult({ metaKey: true });
  expect(historyState).toBe(original);
});

it('falls back to the saved offset if fresh results no longer contain the opened card', async () => {
  await mount(); captureResult(); unmount(); window.scrollY = 5866.4;
  fetcher.mockResolvedValueOnce(response('Lakers', 999));
  await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(968.8);
});

it.each([31 * 60_000, -60_000])('refuses expired or future-dated marks (age %s)', async age => {
  await mount(); captureResult(); unmount();
  jest.setSystemTime(Date.now() + age);
  await mount(); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});

it('an error on return does not scroll the short error document', async () => {
  await mount(); captureResult(); unmount();
  fetcher.mockRejectedValueOnce(new Error('Could not load results'));
  await mount(); await frames();
  expect(host.textContent).toContain('Could not load results');
  expect(scrollTo).not.toHaveBeenCalled();
});

it('survives unavailable history writes without breaking the result click', async () => {
  await mount();
  (window.history.replaceState as jest.Mock).mockImplementation(() => { throw new Error('History unavailable'); });
  expect(() => captureResult()).not.toThrow();
});

it('does not apply a late return response after leaving for another query', async () => {
  await mount(); captureResult(); unmount();
  const back = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(back.promise);
  await mount(); await rerender('q=Celtics');
  await act(async () => { back.resolve(response('Late Lakers')); }); await frames();
  expect(host.textContent).not.toContain('Late Lakers');
  expect(scrollTo).not.toHaveBeenCalled();
});

it('StrictMode effect replay still lands once after the guarded response', async () => {
  await mount(); captureResult(); unmount(); window.scrollY = 5866.4;
  host = document.createElement('div'); document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => { root!.render(<React.StrictMode><SearchPage /></React.StrictMode>); });
  await frames();
  expect(scrollTo).toHaveBeenCalledTimes(1);
  expect(window.scrollY).toBeCloseTo(968.8);
});


it('updates the same entry after scrolling, then leaving via Forward or persistent navigation', async () => {
  await mount(); captureResult(); unmount(); window.scrollY = 5866.4;
  await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(968.8);
  interrupt('wheel'); window.scrollY = 3000; interrupt('scroll'); interrupt('scrollend'); await frames();
  unmount(); window.scrollY = 5866.4; scrollTo.mockClear();
  await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(3000);
});

it('does not resurrect a cancelled landing on a subsequent non-result return', async () => {
  await mount(); captureResult(); unmount();
  const back = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(back.promise);
  await mount(); interrupt('wheel');
  await act(async () => { back.resolve(response()); }); await frames();
  unmount(); await mount(); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});


it('a fresh same-query submission while the return request is pending cannot inherit the landing', async () => {
  await mount(); captureResult(); unmount();
  const back = deferred<SearchResponse>(); fetcher.mockReturnValueOnce(back.promise);
  await mount(); await rerender('q=Lakers');
  await act(async () => { back.resolve(response()); }); await frames();
  expect(scrollTo).not.toHaveBeenCalled();
});


it('bounds history writes during sustained scrolling and flushes the final scroll offset', async () => {
  await mount(); captureResult();
  const writes = window.history.replaceState as jest.Mock; writes.mockClear();
  for (let i = 0; i < 60; i++) {
    window.scrollY = 1500 + i * 10; interrupt('scroll');
    await act(async () => { await jest.advanceTimersByTimeAsync(16); });
  }
  expect(writes).toHaveBeenCalledTimes(1);
  interrupt('scrollend');
  expect(writes).toHaveBeenCalledTimes(2);
  unmount(); window.scrollY = 5866.4; await mount(); await frames();
  expect(window.scrollY).toBeCloseTo(2090);
});
