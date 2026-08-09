/**
 * The shared implementation behind `usePinnedEvents` and `usePinnedFutures`
 * (UX-P017 / #1496).
 *
 * These two hooks were byte-identical apart from a storage key, a response
 * field and the string `'event'` / `'future'` — which is why #1496's P1
 * cross-account write existed twice and had to be fixed twice. It lives in one
 * place now so the account boundary has exactly one implementation to get right.
 *
 * What changed, beyond deduplication:
 *
 *   • The cache is partitioned by owner. `bainluck_pinnedEvents` was device
 *     global, so account B mounted, painted account A's ids, and then merged
 *     every A-only id into B's SERVER pins.
 *   • The merge input is the anonymous bucket only, consumed at most once. A
 *     signed-in account's cache is never migration input.
 *   • State is bound to the bucket it was loaded from, so a bucket change cannot
 *     flush the previous owner's ids into the new owner's storage during the
 *     render between the two effects.
 *   • Every server dispatch re-checks that its identity is still current, since
 *     the API client's auth-token getter is module-global and moves the instant
 *     the account does.
 */

"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchUserPins, addPin, removePin } from "@/lib/api";
import { resolveScope, type ClientScope } from "@/lib/clientPrincipal";
import {
  bucketKeyFor,
  reconcileLegacyBucket,
  pendingAnonymousMigration,
  completeAnonymousMigration,
  browserStore,
  type BucketPolicy,
} from "@/lib/principalStorage";
import { parseIds, serializeIds, mergeForMigration } from "@/lib/pinnedIds";

export interface UsePinnedIdsResult {
  /** Array of pinned ids for the CURRENT owner (empty while identity resolves) */
  pinnedIds: number[];
  isPinned: (id: number) => boolean;
  togglePin: (id: number) => void;
  /** Pin (no-op if already pinned, at max, or identity is unresolved) */
  pin: (id: number) => boolean;
  unpin: (id: number) => void;
  clearAll: () => void;
  isMaxReached: boolean;
}

/**
 * State carries the bucket it belongs to. Reading `ids` only when the bucket
 * still matches is the same guard `dataForPrincipal` applies to fetched bodies:
 * a value never outlives the identity it was loaded for, not even for the one
 * render between an owner change and the reload effect.
 */
interface BucketState {
  bucket: string | null;
  ids: number[];
}

const EMPTY: number[] = [];

export function usePinnedIds(
  policy: BucketPolicy,
  pinType: "event" | "future",
  serverField: "events" | "futures",
  max: number
): UsePinnedIdsResult {
  const { isAuthenticated, isLoading: authLoading, user } = useAuthContext();
  const uid = user?.uid ?? null;

  const scope = useMemo<ClientScope>(
    () => resolveScope({ isLoading: authLoading, isAuthenticated, uid }),
    [authLoading, isAuthenticated, uid]
  );
  const bucket = bucketKeyFor(policy, scope);

  const [state, setState] = useState<BucketState>({ bucket: null, ids: [] });

  // Only this owner's ids are ever visible. A stale bucket reads as empty
  // rather than as the previous account's pins.
  const pinnedIds = state.bucket === bucket && bucket !== null ? state.ids : EMPTY;

  // Storage failures must never reach React — see `safeStore`.
  const store = useMemo(() => browserStore(), []);

  // Load whenever the owner changes (mount, sign-in, A→B, sign-out).
  useEffect(() => {
    if (!store) return;
    if (scope.kind === "pending") {
      setState({ bucket: null, ids: [] });
      return;
    }

    reconcileLegacyBucket(policy, scope, store);

    const key = bucketKeyFor(policy, scope);
    if (!key) return;
    setState({ bucket: key, ids: parseIds(store.getItem(key)) });
  }, [scope, policy, store]);

  // Signed in: the server is authoritative. Merge the device's ANONYMOUS pins
  // in once, then adopt the server set.
  useEffect(() => {
    if (!store) return;
    if (scope.kind !== "principal") return;

    const key = bucketKeyFor(policy, scope);
    if (!key) return;

    let cancelled = false;

    (async () => {
      try {
        const serverPins = await fetchUserPins();
        if (cancelled) return;

        const serverIds = serverPins[serverField] ?? [];
        const migrateRaw = pendingAnonymousMigration(policy, store);
        const migrateIds = parseIds(migrateRaw);

        const { merged, toPush } = mergeForMigration(serverIds, migrateIds, max);

        setState({ bucket: key, ids: merged });
        store.setItem(key, serializeIds(merged));

        let allPushed = true;
        for (const id of toPush) {
          // Re-check before EVERY dispatch: the auth-token getter is global, so
          // a request started after the account changed would be written to the
          // new account. Cancel-before-dispatch is the only real guard.
          if (cancelled) return;
          try {
            await addPin(pinType, id);
          } catch {
            allPushed = false;
          }
        }

        // Mark consumed only on a fully successful merge, so a failed push
        // retries on the next mount instead of silently dropping the pins.
        if (!cancelled && migrateIds.length > 0 && allPushed) {
          completeAnonymousMigration(policy, store);
        }
      } catch {
        // Offline or a failed fetch: keep whatever the local bucket loaded.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [scope, policy, store, serverField, pinType, max]);

  // Cross-tab sync, scoped to THIS owner's bucket.
  useEffect(() => {
    if (!store || !bucket) return;

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key !== bucket) return;
      setState({ bucket, ids: parseIds(e.newValue) });
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [bucket, store]);

  /** Apply a local change and persist it to the owner's bucket. */
  const commit = useCallback(
    (next: (current: number[]) => number[]) => {
      if (!bucket) return;
      setState((prev) => {
        const current = prev.bucket === bucket ? prev.ids : [];
        const ids = next(current);
        if (store) store.setItem(bucket, serializeIds(ids));
        return { bucket, ids };
      });
    },
    [bucket, store]
  );

  const isPinned = useCallback((id: number): boolean => pinnedIds.includes(id), [pinnedIds]);

  const pin = useCallback(
    (id: number): boolean => {
      // No stable owner yet — refuse rather than write into the wrong bucket.
      if (!bucket) return false;
      if (pinnedIds.includes(id)) return false;
      if (pinnedIds.length >= max) return false;

      commit((current) => [...current, id]);

      if (scope.kind === "principal") {
        addPin(pinType, id).catch((err) =>
          console.warn("Failed to sync pin to server:", err)
        );
      }
      return true;
    },
    [bucket, pinnedIds, max, commit, scope, pinType]
  );

  const unpin = useCallback(
    (id: number): void => {
      if (!bucket) return;
      commit((current) => current.filter((existing) => existing !== id));

      if (scope.kind === "principal") {
        removePin(pinType, id).catch((err) =>
          console.warn("Failed to sync unpin to server:", err)
        );
      }
    },
    [bucket, commit, scope, pinType]
  );

  const togglePin = useCallback(
    (id: number): void => {
      if (pinnedIds.includes(id)) unpin(id);
      else pin(id);
    },
    [pinnedIds, pin, unpin]
  );

  const clearAll = useCallback((): void => {
    if (!bucket) return;
    if (scope.kind === "principal") {
      for (const id of pinnedIds) {
        removePin(pinType, id).catch((err) =>
          console.warn("Failed to remove pin from server:", err)
        );
      }
    }
    commit(() => []);
  }, [bucket, scope, pinnedIds, commit, pinType]);

  return {
    pinnedIds,
    isPinned,
    togglePin,
    pin,
    unpin,
    clearAll,
    isMaxReached: pinnedIds.length >= max,
  };
}
