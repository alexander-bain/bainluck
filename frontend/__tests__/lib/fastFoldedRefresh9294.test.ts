import { createFoldedRefetchScheduler } from "@/lib/foldedRefetchScheduler";

beforeEach(() => { jest.useFakeTimers(); jest.setSystemTime(0); });
afterEach(() => { jest.useRealTimers(); });
const settle = async () => { await Promise.resolve(); await Promise.resolve(); };

describe("fast folded reads remain bounded", () => {
  it("starts immediately, then waits for a slow request before one trailing read", async () => {
    const completions: Array<() => void> = [];
    const fetch = jest.fn(() => new Promise<void>(resolve => completions.push(resolve)));
    const scheduler = createFoldedRefetchScheduler(fetch, 1000);
    scheduler.request();
    expect(fetch).toHaveBeenCalledTimes(1);
    for (let i = 0; i < 25; i++) {
      jest.advanceTimersByTime(100);
      scheduler.request();
    }
    expect(fetch).toHaveBeenCalledTimes(1);
    completions[0](); await settle();
    expect(fetch).toHaveBeenCalledTimes(2);
    completions[1](); await settle();
    jest.advanceTimersByTime(5000);
    expect(fetch).toHaveBeenCalledTimes(2);
    scheduler.cancel();
  });

  it("keeps a burst's last request, caps starts at one second and cancels trailing work", async () => {
    const fetch = jest.fn(async () => undefined);
    const scheduler = createFoldedRefetchScheduler(fetch, 1000);
    scheduler.request(); await settle();
    jest.advanceTimersByTime(250); scheduler.request();
    jest.advanceTimersByTime(749); expect(fetch).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(1); await settle(); expect(fetch).toHaveBeenCalledTimes(2);
    scheduler.request(); scheduler.cancel();
    jest.advanceTimersByTime(1000); expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("a failed read does not strand trailing work or resurrect it after teardown", async () => {
    let reject!: (e: Error) => void;
    const fetch = jest.fn(() => new Promise<void>((_, fail) => { reject = fail; }));
    const scheduler = createFoldedRefetchScheduler(fetch, 1000);
    scheduler.request(); scheduler.request();
    scheduler.cancel(); reject(new Error("offline")); await settle();
    jest.advanceTimersByTime(5000);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});


it("retries the retained invalidation after a failed slow read", async () => {
  let reject!: (e: Error) => void;
  const fetch = jest.fn(() => new Promise<void>((_, fail) => { reject = fail; }));
  const scheduler = createFoldedRefetchScheduler(fetch, 1000);
  scheduler.request();
  jest.advanceTimersByTime(1500); scheduler.request();
  expect(fetch).toHaveBeenCalledTimes(1);
  reject(new Error("offline")); await settle();
  expect(fetch).toHaveBeenCalledTimes(2);
  scheduler.cancel();
});
