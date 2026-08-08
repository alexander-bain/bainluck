/**
 * usePinnedEvents - Hook for managing pinned events
 *
 * Anonymous visitors keep their pins on the device; signed-in accounts are
 * server-backed so pins follow them across web and iOS. The device's anonymous
 * pins are merged into an account once, on sign-in.
 *
 * The account boundary — one storage bucket per owner, and never using a
 * signed-in account's cache as migration input — lives in `usePinnedIds`
 * (UX-P017 / #1496). This file is the events binding of it.
 */

"use client";

import { usePinnedIds, type UsePinnedIdsResult } from "./usePinnedIds";
import type { BucketPolicy } from "@/lib/principalStorage";

const PIN_POLICY: BucketPolicy = { base: "bainluck_pinnedEvents" };
const MAX_PINNED_EVENTS = 6;

interface UsePinnedEventsResult {
  /** Array of pinned event IDs */
  pinnedIds: number[];
  /** Check if an event is pinned */
  isPinned: (eventId: number) => boolean;
  /** Toggle pin status for an event */
  togglePin: (eventId: number) => void;
  /** Pin an event (no-op if already pinned or at max) */
  pin: (eventId: number) => boolean;
  /** Unpin an event */
  unpin: (eventId: number) => void;
  /** Clear all pins */
  clearAll: () => void;
  /** Whether max pins have been reached */
  isMaxReached: boolean;
}

export function usePinnedEvents(): UsePinnedEventsResult {
  const result: UsePinnedIdsResult = usePinnedIds(
    PIN_POLICY,
    "event",
    "events",
    MAX_PINNED_EVENTS
  );
  return result;
}
