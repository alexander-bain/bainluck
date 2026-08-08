/**
 * Category-interest storage policy and pure merge logic (UX-P017 / #1496).
 *
 * Shared by `useCategoryInterests` (the editor) and `useInterestSync` (the
 * one-time anonymous→account migration) so both agree on which bucket belongs to
 * whom. They previously each hard-coded the same device-global key and drifted
 * into the same account-crossing bug independently.
 */

import type { BucketPolicy } from "./principalStorage";

export const INTERESTS_POLICY: BucketPolicy = {
  base: "bainluck_categoryInterests",
  // Shipped long before this module. Devices that already migrated carry this
  // flag and must not migrate a second time, so it stays honoured rather than
  // being replaced by the new one.
  legacyDoneKey: "bainluck_interestsSyncedToServer",
};

export type Interests = Record<string, number>;

/** Parse a stored interest map, tolerating absent or corrupt values. */
export function parseInterests(raw: string | null): Interests {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const out: Interests = {};
      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
      }
      return out;
    }
    return {};
  } catch {
    return {};
  }
}

export function serializeInterests(interests: Interests): string {
  return JSON.stringify(interests);
}

/**
 * Merge a device's ANONYMOUS interests into an account's server interests.
 *
 * Max-wins per category, matching the behaviour this replaces. `anonymous` must
 * come from the anonymous bucket alone — `pendingAnonymousMigration` enforces
 * that upstream — because a max-merge is the most contaminating direction
 * possible if the provenance is wrong: it can only ever raise another account's
 * affinities, never reveal the error by lowering one.
 */
export function mergeInterests(server: Interests, anonymous: Interests): Interests {
  const merged: Interests = { ...server };
  for (const [category, value] of Object.entries(anonymous)) {
    merged[category] = Math.max(merged[category] ?? 0, value);
  }
  return merged;
}

/** True when the merge would change nothing, so no server write is needed. */
export function mergeIsNoop(server: Interests, merged: Interests): boolean {
  const serverKeys = Object.keys(server);
  const mergedKeys = Object.keys(merged);
  if (serverKeys.length !== mergedKeys.length) return false;
  return mergedKeys.every((key) => server[key] === merged[key]);
}
