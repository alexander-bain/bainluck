/**
 * #10090 G1 repairs — the pure halves of Authority's REVISE (0930Z, F1/F2) and
 * Latency's COST-REVISE (0931Z, R1/R2). The mounted page cases live in
 * `__tests__/hooks/reconcileControlMounted10090.test.tsx` ("G1 repairs").
 *
 *   - A journaled poll is replayed onto a pair's fresher read only when it is a
 *     result or strictly newer (`replayJournaledPoll`); the live poll adopter
 *     `keepNewerHeldHeadline` is NOT a replay rule (cases A and B below show
 *     what it did when replayed).
 *   - The folded scheduler: an ordinary invalidation (`keepBackoff`) leaves the
 *     persistent ladder alone, a ladder read says so (`backoff`), and a 429's
 *     `retryAfterMs` holds every next read.
 *   - `fetchEvent` / `fetchEventHistory` fresh reads take `maxRetries`, so an
 *     owed pair's step is exactly one request per half.
 */
import { createWriteJournal, rebaseOnCoveringRead, replayJournaledPoll } from "@/lib/reconcileControl";
import { keepNewerHeldHeadline } from "@/lib/reconcileEventPoll";
import { createFoldedRefetchScheduler } from "@/lib/foldedRefetchScheduler";
import { fetchEvent, fetchEventHistory, setAuthTokenGetter } from "@/lib/api";

type Ev = {
  id: number; status: string; hero_probability_source: string; hero_probability: number;
  hero_probability_away: number; hero_probability_observed_at: string;
  home_score: number | null; away_score: number | null;
  win_probability_sources: Record<string, { value: number }>; blend_fold_revision?: Record<string, number>;
};
const base = (o: Partial<Ev>): Ev => ({
  id: 7, status: "live", hero_probability_source: "blend", hero_probability: 0.6, hero_probability_away: 0.4,
  hero_probability_observed_at: "2026-10-19T09:00:00Z", home_score: 14, away_score: 7,
  win_probability_sources: { kalshi: { value: 0.6 }, polymarket: { value: 0.6 } }, blend_fold_revision: { 7: 10 }, ...o,
});

describe("#10090 replayJournaledPoll", () => {
  const onto = base({ blend_fold_revision: { 7: 11 } });
  it.each([
    ["strictly newer", base({ blend_fold_revision: { 7: 12 } }), true],
    ["a result (the final owner), whatever its revision", base({ status: "completed", blend_fold_revision: { 7: 9 } }), true],
    ["the same revision", base({ blend_fold_revision: { 7: 11 } }), false],
    ["older", base({ blend_fold_revision: { 7: 10 } }), false],
    ["incomparable (a twin joined)", base({ blend_fold_revision: { 7: 12, 9: 1 } }), false],
    ["unversioned", base({ blend_fold_revision: undefined }), false],
    ["scheduled and older (not a result)", base({ status: "scheduled", blend_fold_revision: { 7: 10 } }), false],
  ])("%s → %s", (_name, polled, replays) => {
    expect(replayJournaledPoll(polled, onto)).toBe(replays ? polled : undefined);
  });
  it("lands on nothing it cannot order: an unversioned value takes no live poll", () => {
    expect(replayJournaledPoll(base({ blend_fold_revision: { 7: 12 } }), base({ blend_fold_revision: undefined }))).toBeUndefined();
  });

  // Authority's measured cases, through the real journal + rebase.
  const rebase = (detail: Ev, held: Ev, polled: Ev, replay: (p: Ev, h: Ev) => Ev | undefined) => {
    const journal = createWriteJournal<Ev>();
    journal.record((h) => replay(polled, h));
    return rebaseOnCoveringRead(detail, journal, held);
  };
  const A = {
    held: base({ status: "scheduled", home_score: null, away_score: null }),
    polled: base({ status: "scheduled", home_score: null, away_score: null }),
    detail: base({ home_score: 7, away_score: 0, hero_probability: 0.55,
      win_probability_sources: { kalshi: { value: 0.55 } }, blend_fold_revision: { 7: 11 } }),
  };
  const B = {
    held: base({}), polled: base({}),
    detail: base({ hero_probability: 0.55, win_probability_sources: { kalshi: { value: 0.55 } },
      blend_fold_revision: { 7: 11, 9: 3 } }),
  };
  // The live poll adopter, replayed the way the frozen candidate did.
  const liveAdopter = keepNewerHeldHeadline as unknown as (p: Ev, h: Ev) => Ev;
  it("case A: an older cached poll keeps the fresh detail's live 7-0 (keepNewerHeldHeadline put it back to scheduled)", () => {
    const fixed = rebase(A.detail, A.held, A.polled, replayJournaledPoll)!;
    expect([fixed.status, fixed.home_score, fixed.away_score, fixed.hero_probability]).toEqual(["live", 7, 0, 0.55]);
    const old = rebase(A.detail, A.held, A.polled, liveAdopter)!;
    expect([old.status, old.home_score, old.away_score, old.hero_probability]).toEqual(["scheduled", null, null, 0.55]);
  });
  it("case B: an incomparable pre-removal poll keeps the Kalshi-only rail (keepNewerHeldHeadline returned the poll whole)", () => {
    const fixed = rebase(B.detail, B.held, B.polled, replayJournaledPoll)!;
    expect([Object.keys(fixed.win_probability_sources), fixed.blend_fold_revision]).toEqual([["kalshi"], { 7: 11, 9: 3 }]);
    const old = rebase(B.detail, B.held, B.polled, liveAdopter)!;
    expect([Object.keys(old.win_probability_sources), old.blend_fold_revision]).toEqual([["kalshi", "polymarket"], { 7: 10 }]);
  });
});

describe("#10090 folded scheduler: the ladder is the owed floor's only pace", () => {
  beforeEach(() => { jest.useFakeTimers(); jest.setSystemTime(0); });
  afterEach(() => { jest.useRealTimers(); });
  const flush = async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); };

  it("an invalidation (keepBackoff) neither restarts nor disarms an armed step; only the ladder's read says backoff", async () => {
    const reads: Array<{ at: number; backoff: boolean }> = [];
    const scheduler = createFoldedRefetchScheduler((read) => { reads.push({ at: Date.now(), ...read }); return Promise.resolve(); },
      1000, Date.now, undefined, { owed: () => true, delayMs: (n) => 1000 * 2 ** (n - 1) });
    scheduler.request();
    await flush();
    for (let t = 0; t < 30; t += 1) {
      await jest.advanceTimersByTimeAsync(1000);
      scheduler.request({ keepBackoff: true });
      await flush();
    }
    const ladder = reads.filter((r) => r.backoff).map((r) => r.at);
    expect(ladder).toEqual([1000, 3000, 7000, 15_000]);
    expect(reads[0]).toEqual({ at: 0, backoff: false });
    // Control: invalidations as full requests keep resetting the ladder to its
    // first step, so it never climbs to 2, 4, 8 s.
    const reset: Array<{ backoff: boolean }> = [];
    jest.setSystemTime(0);
    const resetting = createFoldedRefetchScheduler((read) => { reset.push(read); return Promise.resolve(); },
      1000, Date.now, undefined, { owed: () => true, delayMs: (n) => 1000 * 2 ** (n - 1) });
    resetting.request();
    await flush();
    for (let t = 0; t < 30; t += 1) { await jest.advanceTimersByTimeAsync(1000); resetting.request(); await flush(); }
    expect(reset.filter((r) => r.backoff).length).toBeLessThan(2);
    scheduler.cancel();
    resetting.cancel();
  });

  it("a 429's retryAfterMs (20 s) holds the next ladder read 20 s, not 1 s", async () => {
    const at: number[] = [];
    let throttle = true;
    const scheduler = createFoldedRefetchScheduler(() => {
      at.push(Date.now());
      if (!throttle) return Promise.resolve();
      throttle = false;
      return Promise.reject(Object.assign(new Error("429"), { retryAfterMs: 20_000 }));
    }, 1000, Date.now, undefined, { owed: () => true, delayMs: () => 1000 });
    scheduler.request();
    await flush();
    await jest.advanceTimersByTimeAsync(19_999);
    expect(at).toEqual([0]);
    await jest.advanceTimersByTimeAsync(1);
    expect(at).toEqual([0, 20_000]);
    scheduler.cancel();
  });

  it("the hold binds any read, not only the ladder: a request inside it waits it out", async () => {
    const at: number[] = [];
    let throttle = true;
    const scheduler = createFoldedRefetchScheduler(() => {
      at.push(Date.now());
      if (!throttle) return Promise.resolve();
      throttle = false;
      return Promise.reject(Object.assign(new Error("429"), { retryAfterMs: 5000 }));
    }, 1000);
    scheduler.request();
    await flush();
    await jest.advanceTimersByTimeAsync(1000);
    scheduler.request();
    await jest.advanceTimersByTimeAsync(3999);
    expect(at).toEqual([0]);
    await jest.advanceTimersByTimeAsync(1);
    expect(at).toEqual([0, 5000]);
    scheduler.cancel();
  });

  it("a rejection without a wait, or a non-finite one, holds nothing", async () => {
    const at: number[] = [];
    const errors = [new Error("offline"), Object.assign(new Error("x"), { retryAfterMs: Number.POSITIVE_INFINITY }),
      Object.assign(new Error("x"), { retryAfterMs: -5 })];
    const scheduler = createFoldedRefetchScheduler(() => { at.push(Date.now()); const e = errors.shift(); return e ? Promise.reject(e) : Promise.resolve(); },
      1000, Date.now, undefined, { owed: () => at.length < 4, delayMs: () => 1000 });
    scheduler.request();
    await flush();
    await jest.advanceTimersByTimeAsync(3000);
    expect(at).toEqual([0, 1000, 2000, 3000]);
    scheduler.cancel();
  });
});

describe("#10090 an owed pair's half is one request", () => {
  const originalFetch = global.fetch;
  beforeAll(() => setAuthTokenGetter(null));
  afterAll(() => { global.fetch = originalFetch; });
  const throttled = () => ({
    ok: false, status: 429, headers: { get: () => null },
    json: jest.fn().mockResolvedValue({ detail: "Rate limit exceeded: 60/minute", retry_after: 0.05 }),
  }) as unknown as Response;
  const served = (payload: unknown) => ({
    ok: true, status: 200, headers: { get: () => null }, json: jest.fn().mockResolvedValue(payload),
  }) as unknown as Response;

  it.each([
    ["fetchEvent", () => fetchEvent(7, true, { maxRetries: 0 })],
    ["fetchEventHistory", () => fetchEventHistory(7, 24, undefined, true, { maxRetries: 0 })],
  ])("%s(fresh, maxRetries 0): a 429 is one request, rejected with the server's wait", async (_name, call) => {
    const fetchMock = jest.fn().mockResolvedValueOnce(throttled()).mockResolvedValueOnce(served({ id: 7 }));
    global.fetch = fetchMock;
    await expect(call()).rejects.toMatchObject({ retryAfterMs: 50 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });

  it.each([
    ["fetchEvent", () => fetchEvent(7, true)],
    ["fetchEventHistory", () => fetchEventHistory(7, 24, undefined, true)],
  ])("control: %s(fresh) without it keeps the existing retry", async (_name, call) => {
    const fetchMock = jest.fn().mockResolvedValueOnce(throttled()).mockResolvedValueOnce(served({ id: 7 }));
    global.fetch = fetchMock;
    await expect(call()).resolves.toEqual({ id: 7 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
