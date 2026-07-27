"use client";

/**
 * WebVitalsReporter (L2-189, Item 2)
 *
 * Streams Core Web Vitals (LCP / INP / CLS / TTFB / FCP) into the analytics
 * rail via Next's built-in `useReportWebVitals`. Renders nothing. Uses the
 * consent-aware `trackEvent` path (GA4 Consent Mode), so consent behavior is
 * unchanged by this queue. One event is emitted per metric per navigation.
 */

import { useReportWebVitals } from "next/web-vitals";
import { reportWebVital } from "@/lib/webVitals";

export default function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    reportWebVital(metric);
  });
  return null;
}
