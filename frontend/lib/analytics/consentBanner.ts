/**
 * When the consent banner may be raised (L2-222 Item 2 / #1453).
 *
 * The banner is raised on a 1.5s delay so it does not shift layout during the
 * first paint. That delay is a window in which the question can be answered
 * somewhere else — the `/preferences` control, or another tab syncing a choice
 * in — and the timer used to fire regardless. The result was a banner asking
 * something the user had already decided, whose buttons would then overwrite
 * that decision with whichever one they pressed to make it go away.
 *
 * Two guards, because either alone leaves a hole:
 *  1. **Cancel on any choice.** Every consent change reaches the store, so
 *     subscribing to the store catches every decision path — including ones
 *     that do not exist yet.
 *  2. **Re-check at fire time.** A timer that has already been scheduled must
 *     not assert the question is open without looking. This covers a choice
 *     that lands without notifying (a store hydrated by a different code path)
 *     and makes the scheduler correct even with no subscription at all.
 *
 * Fully dependency-injected: the timer, the store read, and the subscription
 * are all parameters, so the whole matrix runs under jest fake timers in this
 * repo's DOM-free environment.
 */

import type { ConsentLevel } from './telemetryConsent';

/** Delay before an undecided visit is asked. */
export const CONSENT_BANNER_DELAY_MS = 1500;

export interface ConsentBannerSchedulerDeps {
  /** Read the current choice; `null` means undecided. */
  getConsent: () => ConsentLevel;
  /** Subscribe to consent changes. Returns an unsubscribe function. */
  subscribe: (listener: () => void) => () => void;
  /** Called whenever the banner's visibility should change. */
  setVisible: (visible: boolean) => void;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  delayMs?: number;
}

/**
 * Arm the banner (if undecided) and keep it honest. Returns a dispose function
 * that clears any pending timer and unsubscribes.
 */
export function startConsentBannerScheduler(
  deps: ConsentBannerSchedulerDeps,
): () => void {
  const {
    getConsent,
    subscribe,
    setVisible,
    setTimer = (fn: () => void, ms: number) => setTimeout(fn, ms),
    clearTimer = (h: unknown) => clearTimeout(h as ReturnType<typeof setTimeout>),
    delayMs = CONSENT_BANNER_DELAY_MS,
  } = deps;

  let handle: unknown = null;

  const cancelTimer = () => {
    if (handle !== null) {
      clearTimer(handle);
      handle = null;
    }
  };

  const onConsentChange = () => {
    if (getConsent() === null) return;
    // Decided — from anywhere. Nothing left to ask.
    cancelTimer();
    setVisible(false);
  };

  const unsubscribe = subscribe(onConsentChange);

  if (getConsent() !== null) {
    // Already decided before we even armed: never raise it.
    setVisible(false);
  } else {
    handle = setTimer(() => {
      handle = null;
      if (getConsent() === null) setVisible(true);
    }, delayMs);
  }

  return () => {
    cancelTimer();
    unsubscribe();
  };
}
