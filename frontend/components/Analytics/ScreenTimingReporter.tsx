"use client";

/**
 * ScreenTimingReporter (latency/121) — emits one `screen_timing` packet per
 * screen arrival, on every route, with no per-page wiring.
 *
 * WHY IT LIVES IN THE GATE RATHER THAN IN EACH PAGE. The charter asks for a
 * table covering *every* top-level tab and the pages under them. There are 40+
 * routes. A per-page hook would cover the ones somebody remembered, and the
 * rows that went missing would be the rows nobody was thinking about — which is
 * the same population as the rows most likely to be slow. One observer in the
 * layout covers a route added next month without anyone touching this file.
 *
 * COLD vs WARM is read from the Navigation Timing API, not guessed: the FIRST
 * screen of a document is `cold`; every subsequent pathname change inside the
 * same document is a warm in-app transition. The two have different targets
 * (<3 s cold, <1 s warm) so they must never be blended.
 *
 * 🔴 A KNOWN AND DELIBERATE SAMPLING BIAS, recorded here so nobody reads the
 * resulting table as the whole population. This rail emits through `trackEvent`
 * → gtag, and gtag.js is only loaded after a consent grant, so the field table
 * describes CONSENTING visitors only. That is the same bias Alex ruled against
 * for Speed Insights (LAT-P197 / D30) — but the remedy there was to mount an
 * un-gated vendor, and there is no un-gated path to GA. So: the unbiased cold
 * number comes from `tools/felt-load.mjs` and Speed Insights; this rail is the
 * per-surface, per-device breakdown that neither of those can give.
 */

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { startScreenTiming, maskSurface, type ScreenTimingWatcher } from "@/lib/screenTiming";

export default function ScreenTimingReporter() {
  const pathname = usePathname();
  // Whether this document has already reported a screen. The first is the cold
  // one; a ref (not state) because flipping it must not re-render anything.
  const seenFirst = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const entry = seenFirst.current ? "warm" : "cold";
    seenFirst.current = true;

    let watcher: ScreenTimingWatcher | null = null;
    try {
      watcher = startScreenTiming({
        surface: maskSurface(pathname ?? window.location.pathname),
        entry,
        appBuild:
          document.querySelector('meta[name="bainluck-frontend-commit"]')?.getAttribute("content")?.slice(0, 12) ??
          "web",
      });
    } catch {
      // Instrumentation must never be able to break a screen. A rail that can
      // throw into a render path is a worse bug than the latency it measures.
      watcher = null;
    }

    return () => {
      // The reader left before the first screen settled. Cancel rather than
      // emit: a partial measurement of an abandoned screen is not a slow screen,
      // and reporting it as one would poison the p95 with reader impatience.
      watcher?.cancel();
    };
  }, [pathname]);

  return null;
}
