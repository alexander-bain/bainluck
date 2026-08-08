/**
 * A debounce that cannot outlive the account that scheduled it
 * (UX-P017 / #1496, defect 3).
 *
 * The bug this replaces: `useCategoryInterests` debounced its server save by two
 * seconds and never cancelled the pending timer on identity change or unmount.
 * The captured payload was account A's map, but the API client's auth-token
 * getter is module-global and had already moved to account B by the time the
 * timer fired — so A's interests were written to B's account. Not a stale read:
 * a cross-account WRITE, durable server-side.
 *
 * The important property is that the guard is *cancel-before-dispatch*, not a
 * check inside the request. Once a request is in flight under B's token there is
 * nothing left to check — it is already B's write. So the owner is recorded when
 * the save is scheduled and the timer is dropped the moment the owner stops
 * being current.
 *
 * Framework-agnostic and timer-injectable so the A-edits→B-switch→advance-clock
 * case is a deterministic fake-timer test rather than a browser exercise.
 */

/** The owning identity of a scheduled save. `null` means "no owner" (anonymous). */
export type SaveOwner = string | null;

export interface PrincipalDebouncer<T> {
  /** Schedule `run` for `owner`, replacing any save already pending. */
  schedule(owner: SaveOwner, value: T, run: (value: T, owner: SaveOwner) => void): void;
  /** Drop any pending save unconditionally (use on unmount). */
  cancel(): void;
  /**
   * Drop any pending save that does NOT belong to `owner`. Call this whenever
   * the current identity changes; it is the account-switch guard.
   */
  retarget(owner: SaveOwner): void;
  /** The owner of the currently pending save, or `undefined` if none. */
  readonly pendingOwner: SaveOwner | undefined;
}

export function createPrincipalDebouncer<T>(
  delayMs: number,
  timers: {
    setTimeout: (fn: () => void, ms: number) => unknown;
    clearTimeout: (handle: never) => void;
  } = globalThis as never
): PrincipalDebouncer<T> {
  let handle: unknown = null;
  let owner: SaveOwner | undefined;

  const clear = () => {
    if (handle !== null) timers.clearTimeout(handle as never);
    handle = null;
    owner = undefined;
  };

  return {
    schedule(nextOwner, value, run) {
      clear();
      owner = nextOwner;
      handle = timers.setTimeout(() => {
        // Read the owner before clearing so `run` is told who it is writing as,
        // letting the caller add its own assertion at the call site.
        const firingOwner = owner as SaveOwner;
        handle = null;
        owner = undefined;
        run(value, firingOwner);
      }, delayMs);
    },

    cancel: clear,

    retarget(nextOwner) {
      if (owner !== undefined && owner !== nextOwner) clear();
    },

    get pendingOwner() {
      return owner;
    },
  };
}
