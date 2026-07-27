/**
 * L2-189 Item 1 — browser-safe feed telemetry.
 *
 * Proves feed cache status + backend elapsed time survive the (cross-origin)
 * fetch path into a bounded, non-PII analytics event, and that missing/
 * malformed headers degrade silently without affecting the returned payload.
 */

// Mock the analytics rail so we can observe emitted events without a browser.
jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import { trackEvent } from "@/lib/analytics";
import {
  resolveFeedCohort,
  parseElapsedMs,
  normalizeCacheStatus,
  buildFeedTelemetry,
  reportFeedTelemetry,
} from "@/lib/feedTelemetry";
import { fetchFeed, setAuthTokenGetter } from "@/lib/api";

const mockTrackEvent = trackEvent as jest.MockedFunction<typeof trackEvent>;

// The complete set of keys the privacy contract permits on a feed_telemetry
// event. Anything outside this set is a PII / payload leak.
const ALLOWED_KEYS = new Set([
  "endpoint",
  "cohort",
  "cache_status",
  "backend_elapsed_ms",
  "duration_ms",
]);

// Keys that must NEVER appear.
const FORBIDDEN_KEYS = [
  "token",
  "authorization",
  "Authorization",
  "cookie",
  "session_id",
  "sessionId",
  "x-session-id",
  "user_id",
  "userId",
  "email",
  "items",
  "data",
  "payload",
];

function makeResponse(headers: Record<string, string>, body: unknown = { items: [] }) {
  return {
    ok: true,
    headers: {
      get: (name: string) => {
        const key = Object.keys(headers).find(
          (k) => k.toLowerCase() === name.toLowerCase()
        );
        return key ? headers[key] : null;
      },
    },
    json: jest.fn().mockResolvedValue(body),
  } as unknown as Response;
}

describe("feedTelemetry — pure builders", () => {
  it("resolveFeedCohort prioritizes authenticated, then session, then shared", () => {
    expect(resolveFeedCohort(true, true)).toBe("authenticated");
    expect(resolveFeedCohort(true, false)).toBe("authenticated");
    expect(resolveFeedCohort(false, true)).toBe("session_anon");
    expect(resolveFeedCohort(false, false)).toBe("shared_anon");
  });

  it("parseElapsedMs handles valid, missing, and malformed values", () => {
    expect(parseElapsedMs("3912.5")).toBe(3913);
    expect(parseElapsedMs("0")).toBe(0);
    expect(parseElapsedMs(null)).toBeNull();
    expect(parseElapsedMs(undefined)).toBeNull();
    expect(parseElapsedMs("")).toBeNull();
    expect(parseElapsedMs("not-a-number")).toBeNull();
    expect(parseElapsedMs("-5")).toBeNull();
  });

  it("normalizeCacheStatus preserves values and defaults to unknown", () => {
    expect(normalizeCacheStatus("hit")).toBe("hit");
    expect(normalizeCacheStatus("error")).toBe("error");
    expect(normalizeCacheStatus(null)).toBe("unknown");
    expect(normalizeCacheStatus(undefined)).toBe("unknown");
    expect(normalizeCacheStatus("  ")).toBe("unknown");
  });

  it("buildFeedTelemetry emits ONLY the allowed, non-PII fields", () => {
    const t = buildFeedTelemetry({
      endpoint: "/api/feed",
      cohort: "shared_anon",
      cacheHeader: "miss",
      elapsedHeader: "4001.2",
      durationMs: 4123.9,
    });
    expect(t).toEqual({
      endpoint: "/api/feed",
      cohort: "shared_anon",
      cache_status: "miss",
      backend_elapsed_ms: 4001,
      duration_ms: 4124,
    });
    Object.keys(t).forEach((k) => expect(ALLOWED_KEYS.has(k)).toBe(true));
  });
});

describe("feedTelemetry — reportFeedTelemetry", () => {
  beforeEach(() => mockTrackEvent.mockReset());

  it("reads cache-status + backend-elapsed off the Response and emits them", () => {
    const res = makeResponse({
      "X-Feed-Cache": "hit",
      "X-Feed-Elapsed-Ms": "120.5",
    });
    const out = reportFeedTelemetry(res, {
      endpoint: "/api/feed",
      authenticated: true,
      hasSessionId: true,
      durationMs: 150,
    });
    expect(out).toEqual({
      endpoint: "/api/feed",
      cohort: "authenticated",
      cache_status: "hit",
      backend_elapsed_ms: 121,
      duration_ms: 150,
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith("feed_telemetry", out);
  });

  it("degrades silently when the headers are missing (CORS-hidden)", () => {
    const res = makeResponse({});
    const out = reportFeedTelemetry(res, {
      endpoint: "/api/feed",
      authenticated: false,
      hasSessionId: false,
      durationMs: 42,
    });
    expect(out).toMatchObject({
      cohort: "shared_anon",
      cache_status: "unknown",
      backend_elapsed_ms: null,
    });
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
  });

  it("never throws even if header access explodes", () => {
    const brokenRes = {
      headers: {
        get: () => {
          throw new Error("boom");
        },
      },
    } as unknown as Response;
    expect(() =>
      reportFeedTelemetry(brokenRes, {
        endpoint: "/api/feed",
        authenticated: false,
        hasSessionId: false,
        durationMs: 1,
      })
    ).not.toThrow();
  });
});

describe("fetchFeed — cross-origin header survival + payload integrity", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    mockTrackEvent.mockReset();
    setAuthTokenGetter(null);
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("emits telemetry with the backend headers and returns the untouched payload", async () => {
    const body = { items: [{ id: 1 }], sport: null };
    global.fetch = jest
      .fn()
      .mockResolvedValue(
        makeResponse(
          { "X-Feed-Cache": "error", "X-Feed-Elapsed-Ms": "3900" },
          body
        )
      );

    const result = await fetchFeed({ limit: 200, event_pct: 0.15 });

    // Payload is returned unchanged — telemetry did not interfere.
    expect(result).toEqual(body);

    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    const [eventName, params] = mockTrackEvent.mock.calls[0];
    expect(eventName).toBe("feed_telemetry");
    expect(params).toMatchObject({
      endpoint: "/api/feed",
      cache_status: "error",
      backend_elapsed_ms: 3900,
    });
    expect(typeof (params as { duration_ms: number }).duration_ms).toBe("number");

    // Privacy contract: no forbidden fields on the emitted event.
    FORBIDDEN_KEYS.forEach((k) =>
      expect(Object.prototype.hasOwnProperty.call(params, k)).toBe(false)
    );
    Object.keys(params as object).forEach((k) =>
      expect(ALLOWED_KEYS.has(k)).toBe(true)
    );
  });

  it("still returns the feed when headers are absent and telemetry is a no-op-ish", async () => {
    const body = { items: [], sport: null };
    global.fetch = jest.fn().mockResolvedValue(makeResponse({}, body));

    const result = await fetchFeed({ limit: 20 });
    expect(result).toEqual(body);
    // Telemetry still emits (with unknown/null), but never blocks the payload.
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    const [, params] = mockTrackEvent.mock.calls[0];
    expect(params).toMatchObject({
      cache_status: "unknown",
      backend_elapsed_ms: null,
    });
  });
});
