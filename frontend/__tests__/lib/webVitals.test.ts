/**
 * L2-189 Item 2 — Core Web Vitals reporting.
 *
 * Asserts event SHAPE and UNITS (not invented latency targets) and that one
 * event is emitted per metric. Malformed input degrades silently.
 */

jest.mock("@/lib/analytics", () => ({
  trackEvent: jest.fn(),
}));

import * as fs from "fs";
import * as path from "path";

import { trackEvent } from "@/lib/analytics";
import { webVitalToEvent, reportWebVital, NAVIGATION_TYPES } from "@/lib/webVitals";

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

/**
 * Locate the installed web-vitals package by walking up from this file, so the
 * guard survives dependency hoisting. Throws rather than skipping: web-vitals
 * is a build dependency, so "not installed" is a broken checkout, never a
 * reason to let the assertion below quietly not run.
 */
function webVitalsDir(): string {
  let dir = __dirname;
  for (let i = 0; i < 8; i++) {
    const candidate = path.join(dir, "node_modules", "web-vitals");
    if (fs.existsSync(candidate)) return candidate;
    dir = path.dirname(dir);
  }
  throw new Error("web-vitals is not installed — this guard cannot run");
}

describe("navigation_type is bounded by its producer", () => {
  /**
   * LAT-P233. The bug this catches is not a hostile input; it is our own
   * dependency legitimately growing a value we were never told about.
   *
   * `NAVIGATION_TYPES` is still a hand-written set, so on its own it is just a
   * restatement one level closer to the truth. This test is what makes it a
   * derivation: it reads the union off the web-vitals release actually
   * installed and requires the two to match EXACTLY.
   *
   * Both directions are asserted, and each catches a different defect:
   *   - a value we are missing is dropped telemetry (the original bug:
   *     `back-forward-cache`, emitted on every back-button restore);
   *   - a value we have that web-vitals cannot emit is the fingerprint of a
   *     set copied from a spec instead of read off the writer (the original
   *     set carried `back_forward`, which the producer's `.replace(/_/g, "-")`
   *     makes unreachable).
   */
  it("NAVIGATION_TYPES matches the web-vitals release we actually ship", () => {
    const baseTypes = path.join(webVitalsDir(), "dist/modules/types/base.d.ts");
    expect(fs.existsSync(baseTypes)).toBe(true);

    const decl = fs
      .readFileSync(baseTypes, "utf8")
      .match(/navigationType\s*:\s*([^;]+);/);
    expect(decl).not.toBeNull();

    const produced = new Set(
      Array.from(decl![1].matchAll(/'([a-z-]+)'/g), (m) => m[1])
    );
    // A regex that silently matched nothing would make this test vacuous.
    expect(produced.size).toBeGreaterThan(1);

    const dropped = [...produced].filter((v) => !NAVIGATION_TYPES.has(v));
    expect(dropped).toEqual([]);

    const unproducible = [...NAVIGATION_TYPES].filter((v) => !produced.has(v));
    expect(unproducible).toEqual([]);
  });

  it("drops a navigation type the producer cannot emit", () => {
    const e = webVitalToEvent(
      { name: "LCP", value: 1200, navigationType: "back_forward" },
      "/discover"
    );
    expect(e).not.toHaveProperty("navigation_type");
  });

  it("keeps the bfcache restore label web-vitals checks first", () => {
    const e = webVitalToEvent(
      { name: "LCP", value: 12, navigationType: "back-forward-cache" },
      "/discover"
    );
    expect(e.navigation_type).toBe("back-forward-cache");
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
