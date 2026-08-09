/**
 * Principal-partitioned local storage, and the anonymous-migration policy
 * (UX-P017 / #1496).
 *
 * Before this module every locally cached slice of personal state lived under a
 * device-global key — `bainluck_pinnedEvents`, `bainluck_pinnedFutures`,
 * `bainluck_categoryInterests`. A device-global key cannot answer "whose is
 * this?", which produced two distinct failures:
 *
 *   READ leak   — account B mounts, paints the ids account A left behind, and
 *                 only later corrects itself from the server.
 *   WRITE leak  — the far worse half. Those same hooks treat local state as
 *                 merge input and push it to the server, so B does not merely
 *                 *see* A's pins, it ADOPTS them. The contamination becomes
 *                 durable and survives the device.
 *
 * The fix is a bucket per owner plus one explicit rule about the legacy bucket:
 * **a signed-in account's cache is never migration input.** Only a bucket we can
 * prove is anonymous may ever be merged into an account.
 */

import type { ClientScope } from "./clientPrincipal";

/** The `localStorage` surface used here — narrowed so tests can inject a fake. */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/**
 * Wrap a store so no storage failure can ever reach React.
 *
 * `localStorage` is not a safe API. It throws on a full quota, and in some
 * privacy modes and embedded/automated browsers even *reading* throws. The pin
 * hooks this module replaced knew that — `savePinnedIds` carried an explicit
 * `try/catch` with a "localStorage might be full or disabled" comment — and the
 * UX-P017 refactor dropped it while moving the logic here.
 *
 * That regression is worse than the original gap, because these calls now run
 * inside a `useEffect` on pages that merely *read* preferences (`/sports` mounts
 * `useCategoryInterests`). An effect that throws unmounts its subtree, so a
 * storage failure stops being "pins didn't persist" and becomes "the page is
 * blank". Personalization is an enhancement; it must never be able to take a
 * page down with it.
 *
 * Reads degrade to `null` (indistinguishable from "nothing stored", which every
 * caller already handles) and writes degrade to a no-op.
 */
export function safeStore(store: KeyValueStore): KeyValueStore {
  return {
    getItem(key) {
      try {
        return store.getItem(key);
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        store.setItem(key, value);
      } catch {
        // Full, disabled, or partitioned — the feature degrades, the page lives.
      }
    },
    removeItem(key) {
      try {
        store.removeItem(key);
      } catch {
        // As above.
      }
    },
  };
}

/**
 * The browser store, already made safe — or `null` during SSR.
 *
 * Hooks should reach for THIS rather than `window.localStorage`, so the guard
 * cannot be forgotten at a new call site.
 */
export function browserStore(): KeyValueStore | null {
  if (typeof window === "undefined") return null;
  try {
    return safeStore(window.localStorage);
  } catch {
    // Accessing the property itself can throw when storage is blocked outright.
    return null;
  }
}

/**
 * One partitioned slice of client state.
 *
 * `legacyDoneKey` names a pre-existing "already migrated" flag that must keep
 * being honoured. Category interests shipped with `bainluck_interestsSyncedToServer`
 * long before this module; ignoring it would re-run a migration that already
 * happened on every device that has the flag set.
 */
export interface BucketPolicy {
  /** The historical device-global key, e.g. `bainluck_pinnedEvents`. */
  base: string;
  /** A pre-UX-P017 migration flag to keep honouring, if the slice had one. */
  legacyDoneKey?: string;
}

/** The device-global key this slice used before it was partitioned. */
export function legacyKey(policy: BucketPolicy): string {
  return policy.base;
}

/** Where an anonymous visitor's own state lives. */
export function anonymousKey(policy: BucketPolicy): string {
  return `${policy.base}:anon`;
}

/** Where account `principal`'s cached state lives. */
export function principalBucketKey(policy: BucketPolicy, principal: string): string {
  return `${policy.base}:${principal}`;
}

/** The flag recording that this device's anonymous bucket has been consumed. */
export function migrationDoneKey(policy: BucketPolicy): string {
  return `${policy.base}:anonMigrated`;
}

/**
 * The bucket the current scope may read and write, or `null` for "touch
 * nothing" while identity is unresolved.
 */
export function bucketKeyFor(policy: BucketPolicy, scope: ClientScope): string | null {
  switch (scope.kind) {
    case "pending":
      return null;
    case "anonymous":
      return anonymousKey(policy);
    case "principal":
      return principalBucketKey(policy, scope.principal);
  }
}

/**
 * Retire the legacy device-global bucket, exactly once, according to what we can
 * PROVE about it.
 *
 * The upgrade has a genuine ambiguity: on the first run after this ships, the
 * legacy bucket may hold an anonymous visitor's pins or it may hold the pins of
 * whichever account was last signed in. Nothing stored alongside it says which.
 *
 * So the rule is decided by the scope observing it:
 *
 *   • `anonymous`  — nobody is signed in, so the bucket IS this visitor's own
 *                    state. Adopt it as the anonymous bucket (only if that
 *                    bucket is still empty, so a real anonymous bucket is never
 *                    overwritten), then drop the legacy key.
 *   • `principal`  — an account is signed in and we cannot prove the legacy
 *                    bucket belongs to it. DELETE IT UNREAD. This is the line
 *                    that closes the cross-account write: unread means it can
 *                    never become merge input for the wrong account.
 *   • `pending`    — decide nothing yet.
 *
 * The cost of the `principal` branch is that a signed-in user loses a purely
 * local paint-before-fetch cache once, on one load. The server is the source of
 * truth for authenticated pins and is fetched on mount, so the visible effect is
 * bounded by one fetch. That is the correct side to err on against a durable
 * cross-account write.
 */
export function reconcileLegacyBucket(
  policy: BucketPolicy,
  scope: ClientScope,
  store: KeyValueStore
): void {
  if (scope.kind === "pending") return;

  const legacy = legacyKey(policy);
  const existing = store.getItem(legacy);
  if (existing === null) return;

  if (scope.kind === "anonymous") {
    const anon = anonymousKey(policy);
    if (store.getItem(anon) === null) {
      store.setItem(anon, existing);
    }
  }

  store.removeItem(legacy);
}

/**
 * The raw anonymous payload awaiting migration into an account, or `null` when
 * there is nothing to migrate or this device has already migrated once.
 *
 * "At most once per device" is deliberate, and it is the conservative direction.
 * A user who signs in as A (consuming the device bucket), signs out, pins a few
 * things anonymously, then signs in as B will NOT have that second batch merged
 * into B. The cost is up to six local pins not following them into a second
 * account; the alternative — re-arming migration after every sign-out — reopens
 * a path where device state crosses into an account that never created it.
 */
export function pendingAnonymousMigration(
  policy: BucketPolicy,
  store: KeyValueStore
): string | null {
  if (store.getItem(migrationDoneKey(policy)) !== null) return null;
  if (policy.legacyDoneKey && store.getItem(policy.legacyDoneKey) !== null) return null;

  const raw = store.getItem(anonymousKey(policy));
  if (raw === null || raw === "") return null;
  return raw;
}

/**
 * Record that the anonymous bucket has been merged into an account, and clear
 * it.
 *
 * Call this only after the server write SUCCEEDS. Marking it done on a failed
 * merge would silently discard the visitor's state; leaving it unmarked lets the
 * next mount retry, which is safe because the flag still bounds it to one
 * SUCCESSFUL migration.
 *
 * Clearing matters as much as the flag: an empty bucket cannot leak to a second
 * account even if the flag were somehow lost.
 */
export function completeAnonymousMigration(
  policy: BucketPolicy,
  store: KeyValueStore
): void {
  store.setItem(migrationDoneKey(policy), "1");
  store.removeItem(anonymousKey(policy));
}
