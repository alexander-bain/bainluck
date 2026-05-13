/**
 * usePinSync - Legacy hook, now a no-op.
 *
 * Pin sync is now handled directly by usePinnedEvents and usePinnedFutures.
 * When authenticated, those hooks fetch server pins on mount and merge with
 * localStorage. Every pin/unpin operation syncs to the server immediately.
 *
 * This hook is kept as a no-op so PinSyncEffect.tsx doesn't need changes.
 */

"use client";

export function usePinSync() {
  // No-op — sync is now built into usePinnedEvents and usePinnedFutures.
}
