/**
 * PinSyncEffect - Runs localStorage → server sync on first login.
 *
 * Handles both pin sync and interest/affinity sync.
 * Must be rendered inside AuthProvider. Renders nothing visible.
 */

"use client";

import { usePinSync } from "@/hooks/usePinSync";
import { useInterestSync } from "@/hooks/useInterestSync";

export default function PinSyncEffect() {
  usePinSync();
  useInterestSync();
  return null;
}
