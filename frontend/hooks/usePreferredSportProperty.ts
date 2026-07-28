"use client";

import { useEffect, useRef } from "react";
import { useCategoryInterests } from "@/hooks/useCategoryInterests";
import { useAnalyticsContext } from "@/components/Analytics/AnalyticsProvider";

/**
 * usePreferredSportProperty — populates the already-defined `preferred_sport`
 * GA4 user property (dimension3, see `lib/analytics/core.ts`) from the ESTABLISHED
 * preference source: category/sport affinities (`useCategoryInterests`, backed by
 * server `sport_affinities` for auth'd users and localStorage for anonymous ones).
 *
 * Contract (Queue L2-204 Item 2):
 *  - No guessed default. When there is no positive-affinity interest, the property
 *    is left UNSET (we never call `setProperties({ preferred_sport })`).
 *  - Consent-safe. Denied/unknown consent emits nothing — we do not even set the
 *    property until analytics consent is explicitly granted.
 *  - Non-PII. The value is a coarse sport/category key (e.g. "basketball_nba"),
 *    never free-form user content.
 *  - Set-once-per-value. We dedupe so a rerender/remount never re-sends the same
 *    property, and only re-send when the derived preference actually changes.
 *
 * Mounted once, app-wide, from `PinSyncEffect` (inside AuthProvider).
 */

/**
 * Derive the single top-affinity sport/category key from an interests map.
 *
 * Only keys with a positive numeric affinity are considered. Ties are broken
 * deterministically (highest value, then lexicographically-smallest key) so the
 * same interests always yield the same property — important for a stable user
 * dimension. Returns `undefined` when nothing has a positive affinity, so callers
 * can leave the property unset rather than guessing a default.
 */
export function derivePreferredSport(
  interests: Record<string, number> | null | undefined,
): string | undefined {
  if (!interests) return undefined;

  let best: string | undefined;
  let bestVal = 0;

  for (const [key, value] of Object.entries(interests)) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
      continue;
    }
    if (
      value > bestVal ||
      (value === bestVal && best !== undefined && key < best)
    ) {
      best = key;
      bestVal = value;
    }
  }

  return best;
}

export function usePreferredSportProperty(): void {
  const { interests, isLoading } = useCategoryInterests();
  const { consent, setProperties } = useAnalyticsContext();
  const lastSet = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (isLoading) return;

    // Denied/unknown consent emits nothing — do not set the property at all.
    if (consent !== "all" && consent !== "analytics") return;

    const preferred = derivePreferredSport(interests);

    // No positive interest → leave the property unset (no guessed default).
    if (!preferred) return;

    // Set once per distinct value.
    if (preferred === lastSet.current) return;
    lastSet.current = preferred;

    setProperties({ preferred_sport: preferred });
  }, [interests, isLoading, consent, setProperties]);
}

export default usePreferredSportProperty;
