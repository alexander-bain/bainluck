/**
 * Core Web Vitals reporting (L2-189, Item 2).
 *
 * Turns Next's `useReportWebVitals` samples (LCP / INP / CLS / TTFB / FCP /
 * FID) into bounded, non-PII `web_vital` analytics events, closing the two
 * UNMEASURED rows (LCP, image/hydration) the L2-188 curl audit could not see.
 *
 * Uses Next's built-in `next/web-vitals` primitive — NO new runtime dependency.
 * Routed through the consent-aware `trackEvent` rail (GA4 Consent Mode), so
 * consent behavior is unchanged by this queue.
 */

import { trackEvent } from "@/lib/analytics";
import type { WebVitalParams } from "@/lib/analytics/types";

/** Minimal shape of a web-vitals / NextWebVitalsMetric sample we consume. */
export interface WebVitalMetricLike {
  name: string;
  value: number;
  rating?: string;
  navigationType?: string;
}

const RATINGS = new Set(["good", "needs-improvement", "poor"]);

/**
 * Map a raw metric + route path to a `web_vital` event payload.
 *
 * Units follow web-vitals: time metrics (LCP/INP/TTFB/FCP/FID) are milliseconds
 * and rounded to whole ms; CLS is a unitless score kept to 3 decimals. Pure and
 * side-effect free so units/shape are directly unit-testable — it asserts no
 * latency *targets*, only correct shape and units.
 */
export function webVitalToEvent(
  metric: WebVitalMetricLike,
  pagePath: string
): WebVitalParams {
  const isUnitless = metric.name === "CLS";
  const value = isUnitless
    ? Math.round(metric.value * 1000) / 1000
    : Math.round(metric.value);

  const event: WebVitalParams = {
    metric_name: metric.name,
    metric_value: value,
    page_path: pagePath,
  };
  if (metric.rating && RATINGS.has(metric.rating)) {
    event.rating = metric.rating as WebVitalParams["rating"];
  }
  if (metric.navigationType) {
    event.navigation_type = metric.navigationType;
  }
  return event;
}

/** Current route path with no query string / ids. Safe on the server. */
function currentPagePath(): string {
  if (typeof window === "undefined") return "";
  return window.location?.pathname ?? "";
}

/**
 * Build and emit a single `web_vital` event. Best-effort — never throws, so a
 * telemetry failure can never affect rendering.
 */
export function reportWebVital(
  metric: WebVitalMetricLike,
  pagePath: string = currentPagePath()
): WebVitalParams | null {
  try {
    const event = webVitalToEvent(metric, pagePath);
    trackEvent("web_vital", event);
    return event;
  } catch {
    return null;
  }
}
