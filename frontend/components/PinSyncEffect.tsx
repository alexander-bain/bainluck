/**
 * PinSyncEffect - Runs localStorage → server sync on first login.
 *
 * Handles pin sync, interest/affinity sync, and populating the GA4
 * `preferred_sport` user property from the established affinity source.
 * Must be rendered inside AuthProvider. Renders nothing visible.
 */

"use client";

import { usePinSync } from "@/hooks/usePinSync";
import { useInterestSync } from "@/hooks/useInterestSync";
import { usePreferredSportProperty } from "@/hooks/usePreferredSportProperty";

export default function PinSyncEffect() {
  usePinSync();
  useInterestSync();
  usePreferredSportProperty();
  return null;
}
