/**
 * usePinnedFutures - Hook for managing pinned futures markets
 *
 * Anonymous visitors keep their pins on the device; signed-in accounts are
 * server-backed so pins follow them across web and iOS. The device's anonymous
 * pins are merged into an account once, on sign-in.
 *
 * The account boundary — one storage bucket per owner, and never using a
 * signed-in account's cache as migration input — lives in `usePinnedIds`
 * (UX-P017 / #1496). This file is the futures binding of it.
 */

"use client";

import { usePinnedIds, type UsePinnedIdsResult } from "./usePinnedIds";
import type { BucketPolicy } from "@/lib/principalStorage";

const PIN_POLICY: BucketPolicy = { base: "bainluck_pinnedFutures" };
const MAX_PINNED_FUTURES = 6;

interface UsePinnedFuturesResult {
  /** Array of pinned futures IDs */
  pinnedIds: number[];
  /** Check if a futures market is pinned */
  isPinned: (futuresId: number) => boolean;
  /** Toggle pin status for a futures market */
  togglePin: (futuresId: number) => void;
  /** Pin a futures market (no-op if already pinned or at max) */
  pin: (futuresId: number) => boolean;
  /** Unpin a futures market */
  unpin: (futuresId: number) => void;
  /** Clear all pins */
  clearAll: () => void;
  /** Whether max pins have been reached */
  isMaxReached: boolean;
}

export function usePinnedFutures(): UsePinnedFuturesResult {
  const result: UsePinnedIdsResult = usePinnedIds(
    PIN_POLICY,
    "future",
    "futures",
    MAX_PINNED_FUTURES
  );
  return result;
}
