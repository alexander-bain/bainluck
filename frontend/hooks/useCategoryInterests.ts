"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchUserPreferences, updateSportAffinities } from "@/lib/api";
import { resolveScope, type ClientScope } from "@/lib/clientPrincipal";
import { bucketKeyFor, reconcileLegacyBucket } from "@/lib/principalStorage";
import {
  INTERESTS_POLICY,
  parseInterests,
  serializeInterests,
  type Interests,
} from "@/lib/categoryInterests";
import { createPrincipalDebouncer } from "@/lib/principalDebounce";

const SAVE_DEBOUNCE_MS = 2000;

/**
 * Interest levels — maps to the onboarding 4-level selector.
 * Thumbs up/down step through these levels.
 */
export const INTEREST_LEVELS = [0, 0.1, 0.3, 1.0] as const;

export function stepUp(current: number): number {
  if (current >= 0.8) return 1.0;
  if (current >= 0.2) return 1.0;
  if (current > 0) return 0.3;
  return 0.1;
}

export function stepDown(current: number): number {
  if (current >= 0.8) return 0.3;
  if (current >= 0.2) return 0.1;
  if (current > 0) return 0;
  return 0;
}

export function getLevelLabel(value: number): string {
  if (value >= 0.8) return "Love it";
  if (value >= 0.2) return "Big moments";
  if (value > 0) return "If wild";
  return "Nah";
}

/**
 * Hook for reading/writing category interests.
 * Auth'd users: reads/writes via API (sport affinities).
 * Anonymous users: reads/writes via the device's anonymous bucket.
 *
 * Account boundary (UX-P017 / #1496): state is bound to the owner it was loaded
 * for, and the debounced server save is cancelled the moment the owner changes.
 * Before this, a 2s save holding account A's map fired after a switch to B and
 * was written to B with B's token — a durable cross-account write, not a stale
 * read.
 */
interface OwnedInterests {
  bucket: string | null;
  interests: Interests;
}

export function useCategoryInterests() {
  const { isAuthenticated, isLoading: authLoading, user } = useAuthContext();
  const uid = user?.uid ?? null;

  const scope = useMemo<ClientScope>(
    () => resolveScope({ isLoading: authLoading, isAuthenticated, uid }),
    [authLoading, isAuthenticated, uid]
  );
  const bucket = bucketKeyFor(INTERESTS_POLICY, scope);

  // Interests carry the owner they belong to, so the render between an account
  // change and the reload effect shows nothing rather than the previous account.
  const [state, setState] = useState<OwnedInterests>({ bucket: null, interests: {} });
  const [isLoading, setIsLoading] = useState(true);

  const debouncerRef = useRef(createPrincipalDebouncer<Interests>(SAVE_DEBOUNCE_MS));

  // A synchronous mirror of `state`. Two thumb clicks in the same tick must
  // compose, and reading React state directly would give the pre-click value
  // for the second one. Every write goes through `publish` so the two cannot
  // drift.
  const stateRef = useRef<OwnedInterests>(state);
  const publish = useCallback((next: OwnedInterests) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const interests = state.bucket === bucket && bucket !== null ? state.interests : {};

  // Cancel any save that no longer belongs to the current owner. This runs on
  // every identity change, which is the account-switch guard; the unmount
  // cleanup covers navigating away mid-debounce.
  useEffect(() => {
    const debouncer = debouncerRef.current;
    debouncer.retarget(scope.kind === "principal" ? scope.principal : null);
  }, [scope]);

  useEffect(() => {
    const debouncer = debouncerRef.current;
    return () => debouncer.cancel();
  }, []);

  // Load for the current owner.
  useEffect(() => {
    if (scope.kind === "pending") {
      publish({ bucket: null, interests: {} });
      setIsLoading(true);
      return;
    }

    const store = typeof window === "undefined" ? null : window.localStorage;
    if (store) reconcileLegacyBucket(INTERESTS_POLICY, scope, store);

    const key = bucketKeyFor(INTERESTS_POLICY, scope);
    if (!key) return;

    if (scope.kind === "anonymous") {
      publish({ bucket: key, interests: parseInterests(store?.getItem(key) ?? null) });
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    fetchUserPreferences()
      .then((prefs) => {
        // A response that resolved after the account changed must not paint.
        if (cancelled) return;
        publish({ bucket: key, interests: (prefs.sport_affinities as Interests) || {} });
        setIsLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [scope]);

  const setInterest = useCallback(
    (category: string, value: number) => {
      // No stable owner yet — refuse rather than attribute the edit to the
      // wrong account.
      if (!bucket) return;

      const current = stateRef.current.bucket === bucket ? stateRef.current.interests : {};
      const updated = { ...current, [category]: value };
      publish({ bucket, interests: updated });

      if (scope.kind === "principal") {
        // Debounce server saves to batch rapid thumb clicks. The save is owned
        // by this principal; if the account changes before it fires, the
        // `retarget` effect above drops it before it is ever dispatched.
        debouncerRef.current.schedule(scope.principal, updated, (payload) => {
          updateSportAffinities(payload).catch((err) => {
            console.warn("Failed to save interests:", err);
          });
        });
      } else if (typeof window !== "undefined") {
        window.localStorage.setItem(bucket, serializeInterests(updated));
      }
    },
    [bucket, scope, publish]
  );

  return { interests, setInterest, isLoading };
}
