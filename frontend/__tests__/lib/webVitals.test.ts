/**
 * L2-189 Item 2 — Core Web Vitals reporting.
 *
 * Asserts event SHAPE and UNITS (not invented latency targets) and that one
 * event is emitted per metric. Malformed input degrades silently.
 */

jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import { trackEvent } from "@/lib/analytics";
import { webVitalToEvent, reportWebVital } from "@/lib/webVitals";

const mockTrackEvent = trackEvent as jest.MockedFunction<typeof trackEvent>;

const ALLOWED_KEYS = new Set([
  "metric_name",
  "metric_value",
  "rating",
  "navigation_type",
  "page_path",
]);

describe("webVitalToEvent — shape and units", () => {
  it("rounds time metrics (LCP/INP/TTFB/FCP) to whole milliseconds", () => {
    const e = webVitalToEvent(
      { name: "LCP", value: 2431.7, rating: "needs-improvement", navigationType: "navigate" },
      "/discover"
    );
    expect(e).toEqual({
      metric_name: "LCP",
      metric_value: 2432,
      rating: "needs-improvement",
      navigation_type: "navigate",
      page_path: "/discover",
    });
  });

  it("keeps CLS as a unitless score (3 decimals), never rounds to an integer", () => {
    const e = webVitalToEvent({ name: "CLS", value: 0.04217 }, "/");
    expect(e.metric_name).toBe("CLS");
    expect(e.metric_value).toBe(0.042);
  });

  it("omits rating when it is not a recognized bucket", () => {
    const e = webVitalToEvent({ name: "INP", value: 180, rating: "bogus" }, "/discover");
    expect(e).not.toHaveProperty("rating");
  });

  it("only ever emits the allowed, non-PII keys", () => {
    const e = webVitalToEvent(
      { name: "TTFB", value: 120, rating: "good", navigationType: "reload" },
      "/discover"
    );
    Object.keys(e).forEach((k) => expect(ALLOWED_KEYS.has(k)).toBe(true));
    // page_path is a route path, not a full URL with query/ids.
    expect(e.page_path).toBe("/discover");
  });
});

describe("reportWebVital — emission", () => {
  beforeEach(() => mockTrackEvent.mockReset());

  it("emits exactly one web_vital event per metric", () => {
    const out = reportWebVital({ name: "FCP", value: 900, rating: "good" }, "/discover");
    expect(mockTrackEvent).toHaveBeenCalledTimes(1);
    expect(mockTrackEvent).toHaveBeenCalledWith("web_vital", out);
  });

  it("never throws on malformed input", () => {
    expect(() =>
      reportWebVital({ name: "LCP", value: Number.NaN }, "/")
    ).not.toThrow();
  });
});
