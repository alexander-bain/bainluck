"use client";

import { useEffect, useMemo } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchUserPreferences, updateSportAffinities } from "@/lib/apiCore";
import { resolveScope, type ClientScope } from "@/lib/clientPrincipal";
import {
  reconcileLegacyBucket,
  pendingAnonymousMigration,
  completeAnonymousMigration,
  browserStore,
} from "@/lib/principalStorage";
import {
  INTERESTS_POLICY,
  parseInterests,
  mergeInterests,
  mergeIsNoop,
  type Interests,
} from "@/lib/categoryInterests";

/**
 * One-time migration of a device's ANONYMOUS category interests into an account
 * on first sign-in. Merge strategy: max of device and server value per category.
 *
 * UX-P017 (#1496, fourth defect — found while fixing the other three, not in the
 * original report). This hook used to read the device-global
 * `bainluck_categoryInterests` key and merge it into whichever account signed
 * in, gated on the device-global `bainluck_interestsSyncedToServer` flag. Two
 * failures fell out of that, both real:
 *
 *   • Account A's leftover interests were max-merged into account B's SERVER
 *     affinities the first time B signed in on A's device. A max-merge is the
 *     worst possible direction for a wrong-provenance write: it can only raise
 *     B's affinities, so it silently steers B's Discover feed toward A's tastes
 *     and never corrects itself.
 *   • Whichever account consumed the flag burned it for the device, so a later
 *     genuine anonymous→account migration was skipped forever.
 *
 * Both are fixed by the same rule the pin hooks now follow: the migration source
 * is the anonymous bucket, and a signed-in account's state is never input to it.
 */
export function useInterestSync() {
  const { isAuthenticated, isLoading, user } = useAuthContext();
  const uid = user?.uid ?? null;

  const scope = useMemo<ClientScope>(
    () => resolveScope({ isLoading, isAuthenticated, uid }),
    [isLoading, isAuthenticated, uid]
  );

  useEffect(() => {
    if (scope.kind !== "principal") return;

    const store = browserStore();
    if (!store) return;

    // Retire the pre-partition device-global key first. Under a signed-in scope
    // this DELETES it unread, which is precisely what stops another account's
    // leftovers from becoming this account's migration input.
    reconcileLegacyBucket(INTERESTS_POLICY, scope, store);

    const raw = pendingAnonymousMigration(INTERESTS_POLICY, store);
    if (raw === null) return;

    const anonymous = parseInterests(raw);
    if (Object.keys(anonymous).length === 0) {
      completeAnonymousMigration(INTERESTS_POLICY, store);
      return;
    }

    let cancelled = false;

    fetchUserPreferences()
      .then(async (prefs) => {
        // The account changed while the read was in flight — abandon rather
        // than write this device's interests into whoever is signed in now.
        if (cancelled) return;

        const server = (prefs.sport_affinities as Interests) || {};
        const merged = mergeInterests(server, anonymous);

        if (mergeIsNoop(server, merged)) {
          completeAnonymousMigration(INTERESTS_POLICY, store);
          return;
        }

        await updateSportAffinities(merged);
        if (cancelled) return;

        // Consumed only after the write succeeds; a failure leaves the bucket
        // intact so the next mount can retry.
        completeAnonymousMigration(INTERESTS_POLICY, store);
      })
      .catch((err) => {
        console.warn("Failed to sync interests to server:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [scope]);
}
