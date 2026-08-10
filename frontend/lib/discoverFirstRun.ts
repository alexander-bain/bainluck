// Discover first-run orientation cohort + game gating (Queue 309, Items 1-3).
//
// All of the DECISION logic lives here as pure functions taking plain data, for
// two reasons:
//
//  1. The page can only read browser storage in a post-mount effect. Reading it
//     during render diverges SSR from first-hydration markup (the L2-199 class
//     of bug). Keeping the read in one place makes that rule enforceable.
//  2. **No function here takes a time input, and none exists that could.** The
//     swipe hint this cohort is modelled on ALSO auto-dismisses on a 5s timer
//     (`window.setTimeout(dismissHint, 5000)`); copying that would make an
//     orientation line vanish while a first-time reader is still reading it.
//     The persistence mechanism is copied; the timer deliberately is not. A
//     state that cannot be derived from elapsed time cannot expire on one.

export const ORIENTATION_STORAGE_KEY = "discover_oriented";
export const GAMES_UNLOCKED_STORAGE_KEY = "discover_games_unlocked";
export const SWIPE_HINT_STORAGE_KEY = "discover_has_swiped";
/** Mirrors `PROFILE_KEY` in lib/discoverInteractions.ts. */
export const DISCOVER_PROFILE_STORAGE_KEY = "discover_interaction_profile_v1";

/** Cards a first-run reader must SEE (not scroll past) before games appear. */
export const GAMES_UNLOCK_CARDS_SEEN = 8;

/** The label that explains an otherwise-bare hero percentage. */
export const HERO_PROBABILITY_HINT = "chance this happens";

/**
 * What durable browser state says about this reader, read once at mount.
 * `null` anywhere upstream means "not yet resolved" — treat as NOT first-run,
 * so the pre-mount render is today's Discover exactly.
 */
export interface FirstRunStorage {
  /** The reader has already engaged once; orientation UI is spent. */
  oriented: boolean;
  /** The existing swipe-hint flag — proof of a prior visit. */
  swiped: boolean;
  /** Games were unlocked on an earlier visit; never re-lock them. */
  gamesUnlocked: boolean;
  /** A recorded interaction profile exists (likes/dismisses/clicks/impressions). */
  hasInteractionProfile: boolean;
}

function readFlag(key: string): boolean {
  try {
    return !!window.localStorage.getItem(key);
  } catch {
    // Blocked storage reads as "returning reader": fail closed, show no
    // first-run UI, rather than showing it on every single visit forever.
    return true;
  }
}

/** Read every durable first-run signal. Call from a mount effect only. */
export function readFirstRunStorage(): FirstRunStorage {
  if (typeof window === "undefined") {
    return { oriented: true, swiped: true, gamesUnlocked: true, hasInteractionProfile: true };
  }
  return {
    oriented: readFlag(ORIENTATION_STORAGE_KEY),
    swiped: readFlag(SWIPE_HINT_STORAGE_KEY),
    gamesUnlocked: readFlag(GAMES_UNLOCKED_STORAGE_KEY),
    hasInteractionProfile: readFlag(DISCOVER_PROFILE_STORAGE_KEY),
  };
}

/**
 * The first-run anonymous cohort: signed out, no orientation flag, no prior
 * visit, no recorded interaction. Everyone else — signed in, previously
 * engaged, or already oriented — is a returning reader and sees zero change.
 *
 * Note the games-unlocked flag is deliberately NOT consulted: scrolling a feed
 * is not engagement, so it unlocks games without spending the orientation line.
 */
export function isFirstRunAnonymous(input: {
  authenticated: boolean;
  storage: FirstRunStorage | null;
  engagedThisSession: boolean;
}): boolean {
  const { authenticated, storage, engagedThisSession } = input;
  if (storage === null) return false;
  if (authenticated) return false;
  if (engagedThisSession) return false;
  return !storage.oriented && !storage.swiped && !storage.hasInteractionProfile;
}

/**
 * Games (the daily challenge card and the inline quiz slots) are visible to
 * everyone except a first-run anonymous reader who has neither met ~8 cards nor
 * tapped anything yet. Content before the game.
 *
 * "Met 8 cards" is TWO conditions, and the second one is not redundant:
 *
 *   * 8 DISTINCT cards seen, counted off the existing impression observer
 *     rather than a pixel offset — the feed is a CSS multi-column masonry, so
 *     a scroll-distance threshold would never fire on a wide screen and would
 *     lock games forever for desktop first-timers.
 *   * the reader has actually SCROLLED. Measured on production at d9c526ad:
 *     the desktop masonry paints 4 columns and puts 10+ cards above the fold,
 *     so the card count alone is satisfied within milliseconds of first paint
 *     and the gate degrades into a no-op — the browser rail caught the daily
 *     challenge and a quiz card sitting in a cold anonymous first viewport.
 *     This is the same trap as the pixel offset, inverted: one measure never
 *     fires on desktop, the other fires instantly. Requiring both is what makes
 *     the gate mean "the reader has moved through some content" on every width.
 *
 * `hasScrolled` is a plain "did the reader move at all" boolean, NOT a distance
 * threshold — no pixel count decides how many cards were met.
 */
export function areGamesUnlocked(input: {
  firstRun: boolean;
  storage: FirstRunStorage | null;
  cardsSeen: number;
  hasScrolled: boolean;
  engagedThisSession: boolean;
}): boolean {
  const { firstRun, storage, cardsSeen, hasScrolled, engagedThisSession } = input;
  if (!firstRun) return true;
  if (engagedThisSession) return true;
  if (storage?.gamesUnlocked) return true;
  return cardsSeen >= GAMES_UNLOCK_CARDS_SEEN && hasScrolled;
}

function writeFlag(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // Persistence is best-effort; a blocked write must never break the feed.
  }
}

/** Engagement spends the orientation UI permanently, and unlocks games. */
export function markFirstRunEngaged(): void {
  writeFlag(ORIENTATION_STORAGE_KEY);
  writeFlag(GAMES_UNLOCKED_STORAGE_KEY);
}

/** Seeing enough of the feed unlocks games, but leaves orientation intact. */
export function markGamesUnlocked(): void {
  writeFlag(GAMES_UNLOCKED_STORAGE_KEY);
}
