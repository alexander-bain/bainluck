/**
 * CAL-P1023 (#3297) — a 429 is the one failure the server tells us how to
 * recover from, and `apiFetch` used to discard that instruction unread.
 *
 * Measured on production 2026-09-05: `GET /api/calibration` answered
 * `HTTP 429 / retry-after: 2 / {"detail":"Rate limit exceeded: 60/minute",
 * "retry_after":2}` while the same endpoint returned 200 twelve times in a row
 * one window later. The server asked for two seconds; the client threw, SWR's
 * own retry is off globally on purpose (`SWRProvider`, #L2-137), and the reader
 * got "Failed to load calibration data" for a curve that was fine.
 *
 * These tests pin BOTH directions, because a retry that is not bounded is its
 * own outage: an in-budget wait must recover, and an over-budget one must fail
 * FAST rather than hold the reader on a wait we already know is too short to
 * clear the limiter's window.
 */
import { setAuthTokenGetter, fetchCalibration, parseRetryAfterMs } from "../../lib/api";

/** A `!res.ok` response whose headers behave like a real `Headers`. */
function throttled(retryAfterHeader: string | null, body: unknown) {
  return {
    ok: false,
    status: 429,
    headers: { get: (n: string) => (n.toLowerCase() === "retry-after" ? retryAfterHeader : null) },
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function served(payload: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: jest.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

describe("parseRetryAfterMs", () => {
  it("reads the HTTP header first — an intermediary that throttles us is honoured too", () => {
    // The body value is deliberately different, so a passing test cannot be
    // explained by the fallback happening to agree.
    expect(parseRetryAfterMs("2", { retry_after: 47 })).toBe(2000);
  });

  it("falls back to our own limiter's JSON field when no header is set", () => {
    expect(parseRetryAfterMs(null, { retry_after: 3 })).toBe(3000);
  });

  it("treats an HTTP-date Retry-After as 'the server did not say', never as a guess", () => {
    // The date form is legal HTTP and we do NOT parse it: a date needs a trusted
    // clock, and a skewed one yields either an instant retry or a wait of days.
    // Unparseable must route to the caller's existing backoff, not to a number
    // we invented.
    expect(parseRetryAfterMs("Wed, 21 Oct 2026 07:28:00 GMT", undefined)).toBeNull();
  });

  it("refuses zero, negative and non-numeric waits", () => {
    expect(parseRetryAfterMs("0", undefined)).toBeNull();
    expect(parseRetryAfterMs("-5", undefined)).toBeNull();
    expect(parseRetryAfterMs("soon", undefined)).toBeNull();
    expect(parseRetryAfterMs(null, { retry_after: 0 })).toBeNull();
    expect(parseRetryAfterMs(null, { retry_after: "2" })).toBeNull();
    expect(parseRetryAfterMs(null, null)).toBeNull();
  });
});

describe("apiFetch and a rate-limited response", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    setAuthTokenGetter(null);
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("recovers: waits the advertised delay once, then serves the payload", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(throttled("0.05", { detail: "Rate limit exceeded: 60/minute", retry_after: 0.05 }))
      .mockResolvedValueOnce(served({ buckets: [], total_outcomes: 7 }));
    global.fetch = fetchMock;

    // This is the whole ship: the call that used to reject now resolves.
    await expect(fetchCalibration()).resolves.toMatchObject({ total_outcomes: 7 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("waits before retrying — it does not simply hammer the same window", async () => {
    // A retry with no wait re-enters the SAME saturated fixed window and is a
    // second 429, so "it retried" is not the property; "it waited" is.
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(throttled("0.15", { retry_after: 0.15 }))
      .mockResolvedValueOnce(served({ ok: true }));
    global.fetch = fetchMock;

    const started = Date.now();
    await fetchCalibration();
    expect(Date.now() - started).toBeGreaterThanOrEqual(140);
  });

  it("refuses an over-budget wait: throws at once, on ONE attempt, without sleeping", async () => {
    // The limiter's window is a fixed 60s, so `retry_after: 47` means the window
    // has barely started. Clamping to the caller's budget and retrying then would
    // spend the reader's seconds and land back inside the same saturated window.
    const fetchMock = jest
      .fn()
      .mockResolvedValue(throttled("47", { detail: "Rate limit exceeded: 60/minute", retry_after: 47 }));
    global.fetch = fetchMock;

    const started = Date.now();
    await expect(fetchCalibration()).rejects.toThrow("Rate limit exceeded: 60/minute");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // Fast is half the requirement: a page that must say "we were throttled"
    // should say it now, not in three quarters of a minute.
    expect(Date.now() - started).toBeLessThan(1000);
  });

  it("gives up after the existing retry ceiling rather than looping forever", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValue(throttled("0.01", { detail: "Rate limit exceeded: 60/minute", retry_after: 0.01 }));
    global.fetch = fetchMock;

    await expect(fetchCalibration()).rejects.toThrow("Rate limit exceeded: 60/minute");
    // `maxRetries` is 2, so three attempts total — the same ceiling the timeout
    // path has always used. This retry does not get its own, larger budget.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("carries the status and detail through, so the page can still name the failure", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue(throttled("47", { detail: "Rate limit exceeded: 60/minute", retry_after: 47 }));

    const err = await fetchCalibration().catch((e) => e);
    expect(err.status).toBe(429);
    expect(err.detail).toBe("Rate limit exceeded: 60/minute");
  });

  it("does not retry a 404 — the control that keeps this scoped to 429", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: { get: () => "1" },
      json: jest.fn().mockResolvedValue({ detail: "Not found" }),
    } as unknown as Response);
    global.fetch = fetchMock;

    await expect(fetchCalibration()).rejects.toThrow("Not found");
    // A `Retry-After` on a 404 is meaningless and must not be obeyed: reloading
    // a 404 reloads a 404 (`lib/loadFailure.ts`).
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
