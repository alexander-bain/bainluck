import { readFileSync } from 'fs';
import { resolve } from 'path';
import ts from 'typescript';
import type { DiscoverProfile, ProfileBucket } from '@/lib/discoverInteractions';
import type { MarketShape } from '@/lib/marketShape';

const PROFILE = 'discover_interaction_profile_v1';
const bucket = (changes: Partial<ProfileBucket> = {}): ProfileBucket => ({
  score: 0, impressions: 0, clicks: 0, likes: 0, dismisses: 0, shares: 0,
  last_interaction_at: '2026-09-30T00:00:00Z', ...changes,
});
const profile = (categories: Record<string, ProfileBucket>): DiscoverProfile => ({ categories, updated_at: '2026-09-30T00:00:00Z' });
const item = (id: string) => ({ content_type: 'event' as const, item_id: id, category: 'baseball', item_name: 'Yankees vs Orioles', score: 50, market_type: 'duel' as MarketShape });

function setup(scoped = false) {
  jest.resetModules(); jest.useFakeTimers();
  const store: Record<string, string> = { bainluck_consent: 'all' };
  const fetchMock = jest.fn((_url: string, _init: RequestInit) => Promise.resolve({ ok: true }));
  const globals = global as unknown as Record<string, unknown>;
  globals.window = { addEventListener: jest.fn(), dispatchEvent: jest.fn(), location: { pathname: '/' } };
  globals.localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
  };
  globals.CustomEvent = class { constructor(public type: string) {} }; globals.fetch = fetchMock;
  const di = require('@/lib/discoverInteractions') as typeof import('@/lib/discoverInteractions');
  const consent = require('@/lib/analytics/telemetryConsent') as typeof import('@/lib/analytics/telemetryConsent');
  consent.initTelemetryConsent();
  const auth = { uid: 'account-a' as string | null, allowed: true };
  const getToken = jest.fn((): Promise<string | null> => Promise.resolve('token-a'));
  di.setDiscoverLearningGate(() => auth.allowed, scoped ? { getUid: () => auth.uid, getToken } : null);
  return { di, store, fetchMock, auth, getToken, consent };
}

// Run the actual small page functions without mounting its entire feed.
function pageFunctions(di: ReturnType<typeof setup>['di']) {
  const page = readFileSync(resolve(__dirname, '../../app/discover/page.tsx'), 'utf8');
  const storage = page.slice(page.indexOf('function getDismissed()'), page.indexOf('function getItemId('));
  const cooldown = page.slice(page.indexOf('function getSuppressedCategories('), page.indexOf('function getGroupedCategory('));
  const code = ts.transpileModule(storage + cooldown, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  return new Function('isSportsDiscoverCategory', 'getDiscoverDismissedStorageKey', 'DISMISS_TTL_MS', 'MAX_LOCAL_DISMISSES', 'CATEGORY_COOLDOWN_DISMISSES', 'CATEGORY_COOLDOWN_SCORE', code + '\nreturn { getDismissed, saveDismissed, getSuppressedCategories };')(di.isSportsDiscoverCategory, di.getDiscoverDismissedStorageKey, 6 * 60 * 60 * 1000, 40, 3, -3) as {
    getDismissed: () => Set<string>; saveDismissed: (items: Set<string>) => void;
    getSuppressedCategories: (profile: DiscoverProfile | null) => Set<string>;
  };
}
async function settle() { for (let i = 0; i < 5; i++) await Promise.resolve(); }
afterEach(() => {
  jest.useRealTimers(); const globals = global as unknown as Record<string, unknown>;
  delete globals.window; delete globals.localStorage; delete globals.CustomEvent;
});

it('keeps positive relevance while unrelated sports negatives remain exact', () => {
  const h = setup(); h.di.recordDiscoverInteraction('baseball', 'like'); h.di.recordDiscoverInteraction('baseball', 'detail_click');
  const before = h.di.readDiscoverInteractionProfile();
  for (let n = 0; n < 12; n++) {
    h.di.recordDiscoverInteraction('baseball', n % 2 ? 'unlike' : 'dismiss'); h.di.sendDiscoverInteraction(item('unrelated-' + n), 'unlike');
  }
  const after = h.di.readDiscoverInteractionProfile(); expect(after).toEqual(before);
  expect(h.di.getDiscoverCategoryAdjustment(after, 'baseball')).toBe(3.5);
  expect(h.di.peekPendingDiscoverInteractions()).toHaveLength(12);
  expect(h.di.peekPendingDiscoverInteractions()[0]).toMatchObject({ item_id: 'unrelated-0', action: 'unlike', item_type: 'event' });
  expect(Object.keys(after!.categories)).toEqual(['baseball']); // neither team inferred
});
it('keeps a Red Sox card above unrelated controls in the next local edition', () => {
  const h = setup();
  h.di.recordDiscoverInteraction('baseball', 'like');
  h.di.recordDiscoverInteraction('baseball', 'detail_click');
  for (let n = 0; n < 20; n++) h.di.recordDiscoverInteraction('baseball', 'unlike');
  const { applyLocalPersonalization } = require('@/lib/discover/editionOrder') as typeof import('@/lib/discover/editionOrder');
  const cards = [
    { name: 'pinned-1', category: 'politics', score: 60 },
    { name: 'pinned-2', category: 'politics', score: 60 },
    { name: 'pinned-3', category: 'politics', score: 60 },
    { name: 'Economics', category: 'economics', score: 52 },
    { name: 'Red Sox', category: 'baseball', score: 50 },
    { name: 'Politics', category: 'politics', score: 51 },
    { name: 'Weather', category: 'weather', score: 49 },
  ];
  const ordered = applyLocalPersonalization(cards, h.di.readDiscoverInteractionProfile(), card => card);
  expect(ordered.slice(0, 3)).toEqual(cards.slice(0, 3));
  expect(ordered[3].name).toBe('Red Sox');
});
it.each(['baseball', 'americanfootball', 'icehockey', 'aussierules', 'cycling', 'mma', 'motorsports', 'wrestling', 'olympics', 'rodeo', 'pickleball', 'sports', 'motorsport', 'rugbyleague', 'rugbyunion', ' BASEBALL '])('%s negatives create no broad profile', category => {
  const h = setup(); h.di.recordDiscoverInteraction(category, 'unlike'); h.di.recordDiscoverInteraction(category, 'dismiss'); expect(h.di.readDiscoverInteractionProfile()).toBeNull();
});
it('recovers clipped legacy positives while preserving other categories and exact history', () => {
  const h = setup(), politics = bucket({ score: -4, dismisses: 4 });
  h.store[PROFILE] = JSON.stringify(profile({ baseball: bucket({ score: -10, clicks: 4, likes: 1, dismisses: 30 }), politics }));
  h.store.discover_dismissed = JSON.stringify({ items: [{ id: 'event-42', ts: Date.now() }] });
  const saved = h.store[PROFILE], exact = h.store.discover_dismissed, recovered = h.di.readDiscoverInteractionProfile()!;
  expect(recovered.categories.baseball).toMatchObject({ score: 8, dismisses: 30 }); expect(recovered.categories.politics).toEqual(politics);
  expect(h.di.getDiscoverCategoryAdjustment(recovered, 'baseball')).toBe(8); expect(h.store[PROFILE]).toBe(saved); expect(h.store.discover_dismissed).toBe(exact);
  h.di.recordDiscoverInteraction('baseball', 'share'); expect(h.di.readDiscoverInteractionProfile()!.categories.baseball.score).toBe(11);
});
it('legacy negatives neither reorder nor cool down sports; politics controls still do', () => {
  const h = setup(), functions = pageFunctions(h.di), saved = profile({ baseball: bucket({ score: -8, dismisses: 8 }), politics: bucket({ score: -8, dismisses: 8 }) });
  expect(h.di.getDiscoverCategoryAdjustment(saved, 'baseball')).toBe(0); expect(h.di.getDiscoverCategoryAdjustment(saved, 'politics')).toBe(-8);
  expect([...functions.getSuppressedCategories(saved)]).toEqual(['politics']);
  h.di.recordDiscoverInteraction('politics', 'unlike'); h.di.recordDiscoverInteraction('politics', 'dismiss');
  expect(h.di.readDiscoverInteractionProfile()!.categories.politics).toMatchObject({ score: -3, dismisses: 2 });
});
it('keeps positive expands without reconstructing migrated scores twice', () => {
  const h = setup(); h.store[PROFILE] = JSON.stringify(profile({ golf: bucket({ score: 9, clicks: 2, dismisses: 9 }) })); h.di.recordDiscoverInteraction('golf', 'group_expand');
  expect(h.di.readDiscoverInteractionProfile()!.categories.golf.score).toBe(9.75); expect(h.di.readDiscoverInteractionProfile()!.categories.golf.score).toBe(9.75);
});
it('isolates accounts while leaving unowned legacy positives and exact dismissals intact', () => {
  const h = setup(true), functions = pageFunctions(h.di);
  h.store[PROFILE] = JSON.stringify(profile({ baseball: bucket({ score: 20, likes: 10 }) })); h.store.discover_dismissed = JSON.stringify({ items: [{ id: 'event-legacy', ts: Date.now() }] });
  const legacy = { profile: h.store[PROFILE], exact: h.store.discover_dismissed };
  expect(h.di.readDiscoverInteractionProfile()).toBeNull(); expect(functions.getDismissed().size).toBe(0);
  h.di.recordDiscoverInteraction('baseball', 'like'); h.di.recordDiscoverInteraction('baseball', 'detail_click'); const a = h.di.readDiscoverInteractionProfile()!;
  functions.saveDismissed(new Set(['event-a'])); expect([...functions.getDismissed()]).toEqual(['event-a']);
  h.auth.uid = 'account-b'; expect(h.di.readDiscoverInteractionProfile()).toBeNull(); expect(h.di.getDiscoverCategoryAdjustment(a, 'baseball')).toBe(0); expect(functions.getDismissed().size).toBe(0);
  h.di.recordDiscoverInteraction('politics', 'like'); functions.saveDismissed(new Set(['event-b'])); h.auth.uid = 'account-a';
  expect(h.di.readDiscoverInteractionProfile()).toEqual(a); expect([...functions.getDismissed()]).toEqual(['event-a']);
  expect(h.store[PROFILE]).toBe(legacy.profile); expect(h.store.discover_dismissed).toBe(legacy.exact);
  h.auth.allowed = false; expect(h.di.readDiscoverInteractionProfile()).toBeNull(); expect(functions.getDismissed().size).toBe(0); expect(h.di.getDiscoverCategoryAdjustment(a, 'baseball')).toBe(0);
});
it('guest/loading gestures never learn or replay after sign-in', async () => {
  const h = setup(true); h.auth.allowed = false; h.di.recordDiscoverInteraction('baseball', 'like'); h.di.sendDiscoverInteraction(item('guest'), 'like'); h.auth.allowed = true;
  jest.advanceTimersByTime(2000); await settle(); expect(h.fetchMock).not.toHaveBeenCalled(); expect(h.di.readDiscoverInteractionProfile()).toBeNull();
});
it('sends authenticated exact sports negatives with the existing server payload', async () => {
  const h = setup(true); h.di.sendDiscoverInteraction(item('exact'), 'unlike', 3); jest.advanceTimersByTime(2000); await settle();
  expect(h.fetchMock).toHaveBeenCalledTimes(1); const init = h.fetchMock.mock.calls[0][1];
  expect(init.headers).toMatchObject({ Authorization: 'Bearer token-a', 'X-Discover-Provenance': 'user' });
  expect(JSON.parse(init.body as string).interactions).toEqual([{ action: 'unlike', item_type: 'event', item_id: 'exact', category: 'baseball', item_name: 'Yankees vs Orioles', score: 50, rank: 4, surface: 'web', source: 'card', market_type: 'duel' }]);
});
it.each(['sign-out', 'account-switch', 'consent-revoke', 'drop-and-return'])('drops a batch when %s occurs during token retrieval', async transition => {
  const h = setup(true); let resolveToken!: (token: string) => void;
  h.getToken.mockImplementation(() => new Promise(resolve => { resolveToken = resolve; })); h.di.sendDiscoverInteraction(item('old'), 'like'); h.di.flushDiscoverInteractions();
  if (transition === 'sign-out') h.auth.allowed = false; if (transition === 'account-switch') h.auth.uid = 'account-b'; if (transition === 'drop-and-return') h.di.dropPendingDiscoverInteractions();
  if (transition === 'consent-revoke') { h.store.bainluck_consent = 'none'; h.consent.__resetTelemetryConsentForTests(); h.consent.initTelemetryConsent(); }
  resolveToken('token-a'); await settle(); expect(h.fetchMock).not.toHaveBeenCalled();
});
it('drops queued A rows before enqueuing B and only sends B', async () => {
  const h = setup(true); h.di.sendDiscoverInteraction(item('a'), 'like'); h.auth.uid = 'account-b'; h.getToken.mockResolvedValue('token-b'); h.di.sendDiscoverInteraction(item('b'), 'like');
  jest.advanceTimersByTime(2000); await settle(); expect(JSON.parse(h.fetchMock.mock.calls[0][1].body as string).interactions[0].item_id).toBe('b');
});
it.each(['missing', 'rejected', 'timeout'])('never sends without a resolved token: %s', async reason => {
  const h = setup(true); if (reason === 'missing') h.getToken.mockResolvedValue(null); if (reason === 'rejected') h.getToken.mockRejectedValue(new Error('offline')); if (reason === 'timeout') h.getToken.mockImplementation(() => new Promise(() => {}));
  h.di.sendDiscoverInteraction(item('tokenless'), 'like'); jest.advanceTimersByTime(7000); await settle(); expect(h.fetchMock).not.toHaveBeenCalled();
});
it('page wires current identity and excludes stale account snapshots', () => {
  const page = readFileSync(resolve(__dirname, '../../app/discover/page.tsx'), 'utf8');
  expect(page).toContain('getUid: () => learningAuthRef.current.uid'); expect(page).toContain('getToken: () => learningAuthRef.current.getToken()'); expect(page).toContain('}, [learningState, user?.uid]);');
  expect(page).toContain('dismissedOwner === currentUid'); expect(page).toContain('interactionProfile?.owner_uid === currentUid'); expect(page).toContain('orderingProfile?.owner_uid === currentUid');
});
