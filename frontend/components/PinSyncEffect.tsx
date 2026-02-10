/**
 * PinSyncEffect - Runs localStorage → server pin migration on first login.
 *
 * Must be rendered inside AuthProvider. Renders nothing visible.
 */

"use client";

import { usePinSync } from "@/hooks/usePinSync";

export default function PinSyncEffect() {
  usePinSync();
  return null;
}
