/**
 * #11937: a rate-limited grade save waits what the server asks and goes again once.
 * Alex was stopped at card 27 by "Not saved (429)" and had to press again.
 */
import { MAX_RETRY_WAIT_MS, retryWaitMs, saveWithOneRetry } from "@/lib/ranking/gradeSession";

const res = (status: number, opts: { header?: string; body?: unknown } = {}) => ({
  status,
  headers: { get: (name: string) => (name === "Retry-After" ? opts.header ?? null : null) },
  clone: () => ({
    json: () => (opts.body === undefined ? Promise.reject(new Error("no body")) : Promise.resolve(opts.body)),
  }),
});

describe("retryWaitMs", () => {
  it("reads the body's retry_after, which is what a cross-origin page can see", async () => {
    expect(await retryWaitMs(res(429, { body: { detail: "Rate limit exceeded: 60/minute", retry_after: 1 } }))).toBe(1000);
    expect(await retryWaitMs(res(429, { body: { retry_after: 41 } }))).toBe(41000);
  });
  it("prefers a readable Retry-After header", async () => {
    expect(await retryWaitMs(res(429, { header: "7", body: { retry_after: 30 } }))).toBe(7000);
  });
  it("waits a second when nothing is readable, and caps at the limiter's window", async () => {
    expect(await retryWaitMs(res(429))).toBe(1000);
    expect(await retryWaitMs(res(429, { header: "soon", body: { retry_after: "x" } }))).toBe(1000);
    expect(await retryWaitMs(res(429, { body: { retry_after: 600 } }))).toBe(MAX_RETRY_WAIT_MS);
  });
  it("is null for anything but a 429", async () => {
    expect(await retryWaitMs(res(200))).toBeNull();
    expect(await retryWaitMs(res(500, { header: "3" }))).toBeNull();
  });
});

describe("saveWithOneRetry", () => {
  it("saves once when the first answer isn't a 429", async () => {
    const send = jest.fn().mockResolvedValue(res(200));
    const sleep = jest.fn().mockResolvedValue(undefined);
    expect((await saveWithOneRetry(send, sleep)).status).toBe(200);
    expect(send).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });
  it("waits the asked time after a 429, says so, and sends once more", async () => {
    const send = jest.fn()
      .mockResolvedValueOnce(res(429, { body: { retry_after: 1 } }))
      .mockResolvedValueOnce(res(200));
    const sleep = jest.fn().mockResolvedValue(undefined);
    const onWait = jest.fn();
    expect((await saveWithOneRetry(send, sleep, onWait)).status).toBe(200);
    expect(send).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(1000);
    expect(onWait).toHaveBeenCalledWith(1000);
  });
  it("retries only once: a second 429 is returned to the page", async () => {
    const send = jest.fn().mockResolvedValue(res(429, { body: { retry_after: 1 } }));
    const sleep = jest.fn().mockResolvedValue(undefined);
    expect((await saveWithOneRetry(send, sleep)).status).toBe(429);
    expect(send).toHaveBeenCalledTimes(2);
  });
});
