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

/** Scroll distance (px) that releases a deferred shared-set consent banner. */
export const CONSENT_BANNER_SCROLL_THRESHOLD_PX = 24;

/**
 * Ruling 279: A (#13103) — first arrival on a shared set (`/collections/<slug>`)
 * holds the consent banner back until the visitor scrolls or opens a second page.
 * Identified telemetry (GA4) remains off while undecided.
 */
export function isSharedSetLandingPath(pathname: string | null | undefined): boolean {
  return typeof pathname === 'string' && /^\/collections\/[^/]+/.test(pathname);
}

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
  /**
   * When true (shared set arrival), hold the banner back until
   * `subscribeEngagement` reports a scroll or second-page navigation.
   */
  deferUntilEngaged?: boolean;
  /**
   * Register a one-shot engagement trigger (scroll or second-page navigation)
   * when `deferUntilEngaged` is true. Returns an unsubscribe function.
   */
  subscribeEngagement?: (onEngage: () => void) => () => void;
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
    deferUntilEngaged = false,
    subscribeEngagement,
  } = deps;

  let handle: unknown = null;
  let unsubscribeEngagement: (() => void) | null = null;
  let disposed = false;

  const cancelTimer = () => {
    if (handle !== null) {
      clearTimer(handle);
      handle = null;
    }
  };

  const cancelEngagement = () => {
    if (unsubscribeEngagement !== null) {
      unsubscribeEngagement();
      unsubscribeEngagement = null;
    }
  };

  const onConsentChange = () => {
    if (getConsent() === null) return;
    // Decided — from anywhere. Nothing left to ask.
    cancelTimer();
    cancelEngagement();
    setVisible(false);
  };

  const unsubscribe = subscribe(onConsentChange);

  if (getConsent() !== null) {
    // Already decided before we even armed: never raise it.
    setVisible(false);
  } else if (deferUntilEngaged && subscribeEngagement) {
    // Ruling 279: A — keep the arrival screen clear until the visitor scrolls
    // or navigates to a second page, re-checking consent at release time.
    setVisible(false);
    unsubscribeEngagement = subscribeEngagement(() => {
      cancelEngagement();
      if (disposed || getConsent() !== null) return;
      setVisible(true);
    });
  } else {
    handle = setTimer(() => {
      handle = null;
      if (getConsent() === null) setVisible(true);
    }, delayMs);
  }

  return () => {
    disposed = true;
    cancelTimer();
    cancelEngagement();
    unsubscribe();
  };
}
