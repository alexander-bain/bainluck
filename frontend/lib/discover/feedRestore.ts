// #7417 — the Discover feed's session-scoped restore snapshot.
//
// THE DEFECT THIS EXISTS FOR. A reader scrolls Discover, taps a card, and
// presses Back. They land in the page footer — nav links, not one card on
// screen. Measured on a local production build at phone width, 3 runs of 3:
// they left at scrollY 4558 and settled at 14931, 15099, 14931 — a drift of
// ~10,400px, twelve screens.
//
// 🔴 IT IS NOT "SCROLL POSITION WAS NOT SAVED". The sampled timeline names a
// compounding loop, and every rung of it has to be cut or the reader still ends
// up at the bottom:
//
//   t=100ms   scrollY=7817  doc=8661   20 cards
//   t=1000ms  scrollY=14931 doc=15775  40 cards
//
// At EVERY sample `scrollY` is exactly `docHeight - 844` — the maximum scroll,
// to the pixel. The reader is not somewhere random; they are pinned to the very
// bottom of a document that keeps growing:
//
//   1. `initialFeedRequest()` is hard-coded to `offset: 0` and `allItems` /
//      `visibleCount` reset on remount, so every page the reader had scrolled
//      in (offset 20/40/60) is discarded and the document collapses.
//   2. The browser restores a scroll offset into that collapsed document and
//      CLAMPS it to the short document's maximum — the bottom.
//   3. At the bottom the pagination sentinel (`rootMargin: 400px`) is in view,
//      so the feed fetches another page. 20 cards become 40.
//   4. That content is inserted ABOVE the footer, and the browser's scroll
//      anchoring keeps the anchored node where it is — so `scrollY` tracks the
//      new maximum, and the sentinel is in view again. Back to 3.
//
// So restoring a pixel offset alone would fix nothing: the offset would be
// clamped against a document that is not there yet. THE ITEMS HAVE TO COME BACK
// FIRST. This module persists the reader's edition — the pages they had loaded,
// their window, and where they were — so the document is its old height before
// anyone scrolls it, and the landing is explicit instead of a clamp.
//
// Everything here is pure except the four thin `sessionStorage` wrappers at the
// bottom, so the decisions are testable without a browser.

/** The reader's loaded edition. Rewritten when the loaded pages change. */
export const FEED_SNAPSHOT_KEY = "discover_feed_snapshot";

/** Where they were. A separate key because scroll changes far more often than
 *  the edition does, and the edition is ~300KB — re-serializing it on a scroll
 *  tick would put a JSON encode of the whole feed in the scroll path. */
export const FEED_SCROLL_KEY = "discover_feed_scroll";

/** Bump when the stored shape changes. A snapshot written by an older build is
 *  refused rather than coerced — a half-understood edition is worse than a
 *  cold load, which is merely today's behaviour. */
export const FEED_SNAPSHOT_VERSION = 2;

/**
 * How long a snapshot is worth restoring.
 *
 * This is session-scoped storage, so it already dies with the tab. The TTL is
 * for the other case: a tab left open for hours, where the feed has moved on
 * and the reader is not mid-read any more. Restoring there would hand them a
 * stale edition and call it their place.
 */
export const FEED_SNAPSHOT_TTL_MS = 30 * 60 * 1000;

/**
 * Item ceiling. At ~2.8KB per serialized feed item (measured against
 * `/api/feed?limit=20`, 56,299 bytes for 20 items) this is ~340KB — comfortably
 * inside the ~5MB sessionStorage budget with room for the rest of the origin's
 * keys. A reader past this depth restores as far as the cap allows and lands as
 * close as the document permits; see `landingTarget`.
 */
export const FEED_SNAPSHOT_MAX_ITEMS = 120;

/**
 * How long the landing loop waits for the restored document to reach full
 * height before giving up and landing as close as it can. Generous because it
 * costs nothing when layout is quick — it resolves on the first frame that
 * fits — and the alternative to waiting is the clamp this module exists to
 * prevent.
 */
export const FEED_RESTORE_LANDING_TIMEOUT_MS = 3000;

export interface FeedSnapshot<T> {
  /** The SWR-owned page-one edition the reader was holding. */
  page1: T[];
  /** Every paginated page after it, in order. */
  rest: T[];
  /** How many cards of the processed list were on screen. */
  visibleCount: number;
  /** Whether the backend still had more to give. */
  hasMore: boolean;
}

export interface FeedScrollMark {
  scrollY: number;
  savedAt: number;
}

interface StoredSnapshot<T> extends FeedSnapshot<T> {
  v: number;
}

interface StoredScroll extends FeedScrollMark {
  v: number;
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/**
 * Cap the edition at `FEED_SNAPSHOT_MAX_ITEMS`, page one first.
 *
 * Page one is never sacrificed to fit: it is the edition `reconcilePage1` folds
 * background revalidations into, and dropping part of it would make the
 * reader's first screen a different first screen. The paginated tail is what
 * gets truncated, and a reader deep enough to hit the cap lands as close as the
 * restored document reaches rather than at the top.
 */
export function capSnapshotItems<T>(page1: T[], rest: T[]): { page1: T[]; rest: T[] } {
  const keptPage1 = page1.slice(0, FEED_SNAPSHOT_MAX_ITEMS);
  const room = FEED_SNAPSHOT_MAX_ITEMS - keptPage1.length;
  return { page1: keptPage1, rest: room > 0 ? rest.slice(0, room) : [] };
}

/** Serialize an edition for storage, or `null` when there is nothing worth
 *  keeping. An empty page one is a cold feed — there is no edition to protect. */
export function serializeFeedSnapshot<T>(snapshot: FeedSnapshot<T>): string | null {
  if (!Array.isArray(snapshot.page1) || snapshot.page1.length === 0) return null;
  const capped = capSnapshotItems(snapshot.page1, snapshot.rest ?? []);
  const stored: StoredSnapshot<T> = {
    v: FEED_SNAPSHOT_VERSION,
    page1: capped.page1,
    rest: capped.rest,
    visibleCount: snapshot.visibleCount,
    hasMore: snapshot.hasMore,
  };
  return JSON.stringify(stored);
}

/**
 * Parse a stored edition, refusing anything it cannot fully vouch for.
 *
 * Every branch here returns `null`, which means "cold load" — today's
 * behaviour. That is the whole reason this validates so bluntly: the failure
 * mode of a rejected snapshot is the status quo, while the failure mode of a
 * half-trusted one is a reader dropped into a document built from a shape we
 * guessed at.
 */
export function parseFeedSnapshot<T>(raw: string | null): FeedSnapshot<T> | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const candidate = parsed as Partial<StoredSnapshot<T>>;
  if (candidate.v !== FEED_SNAPSHOT_VERSION) return null;
  if (!Array.isArray(candidate.page1) || candidate.page1.length === 0) return null;
  if (!Array.isArray(candidate.rest)) return null;
  if (!isPositiveInt(candidate.visibleCount)) return null;
  if (typeof candidate.hasMore !== "boolean") return null;
  return {
    page1: candidate.page1,
    rest: candidate.rest,
    visibleCount: candidate.visibleCount,
    hasMore: candidate.hasMore,
  };
}

export function serializeScrollMark(mark: FeedScrollMark): string {
  const stored: StoredScroll = { v: FEED_SNAPSHOT_VERSION, ...mark };
  return JSON.stringify(stored);
}

/**
 * Parse the scroll mark, refusing a stale or impossible one.
 *
 * 🔴 `now - savedAt` is checked on BOTH sides. A negative age means the mark was
 * written in the future — a clock that moved backwards, or a snapshot carried
 * across a system time change — and "not older than the TTL" is true for every
 * such mark no matter how wrong it is. A one-sided check would restore them
 * forever.
 */
export function parseScrollMark(raw: string | null, now: number): FeedScrollMark | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const candidate = parsed as Partial<StoredScroll>;
  if (candidate.v !== FEED_SNAPSHOT_VERSION) return null;
  if (typeof candidate.scrollY !== "number" || !Number.isFinite(candidate.scrollY)) return null;
  if (candidate.scrollY < 0) return null;
  if (typeof candidate.savedAt !== "number" || !Number.isFinite(candidate.savedAt)) return null;
  const age = now - candidate.savedAt;
  if (age < 0 || age > FEED_SNAPSHOT_TTL_MS) return null;
  return { scrollY: candidate.scrollY, savedAt: candidate.savedAt };
}

/**
 * Where to actually land, given how tall the document currently is.
 *
 * `reached` is true only when the document can hold the target offset — that is
 * the single test that separates a real landing from the clamp in step 2 of the
 * defect. While it is false the caller waits another frame; the returned `y` is
 * the best available position for when the caller runs out of patience, which
 * is strictly better than leaving the reader at the top.
 */
export function landingTarget(
  targetY: number,
  docHeight: number,
  viewportHeight: number,
): { y: number; reached: boolean } {
  const maxScroll = Math.max(0, docHeight - viewportHeight);
  if (maxScroll >= targetY) return { y: targetY, reached: true };
  return { y: maxScroll, reached: false };
}

/**
 * Is this mount a client-side transition within a document that has already
 * rendered Discover once?
 *
 * 🔴 THE NAVIGATION TYPE CANNOT ANSWER THIS ON ITS OWN, and reaching for it is
 * the trap. A Back out of a card is a client-side route change: it creates no
 * new navigation entry, so `performance` still reports whatever loaded the tab
 * — usually `"navigate"`. Gating the restore on `"back_forward"` would refuse
 * exactly the case this module was built for.
 *
 * What distinguishes them is the `window` object itself, which a document load
 * tears down and a client-side transition does not. An absent marker therefore
 * means "first mount of this document"; a present one means the reader got here
 * without reloading.
 */
export function markAndDetectClientTransition(win: Window): boolean {
  const holder = win as Window & { __blDiscoverDocumentSeen?: boolean };
  if (holder.__blDiscoverDocumentSeen) return true;
  holder.__blDiscoverDocumentSeen = true;
  return false;
}

/**
 * Whether this mount should restore at all.
 *
 * A client-side transition always restores. A fresh document restores only when
 * the browser says it is a back/forward traversal: a reload is the reader
 * asking for a fresh feed, and a typed URL is not a return at all. Honouring
 * either of those with a restored edition would override an explicit request.
 */
export function shouldRestoreOnMount(args: {
  clientTransition: boolean;
  navigationType: string | null;
}): boolean {
  if (args.clientTransition) return true;
  return args.navigationType === "back_forward";
}

// ── sessionStorage wrappers ─────────────────────────────────────────────────
// Every one of these swallows its errors. Storage throws for reasons that have
// nothing to do with this feature — quota, private browsing, a disabled origin
// — and none of them are a reason to break Discover. A failed read is a cold
// load; a failed write is a Back that behaves the way it does today.

export function readFeedSnapshot<T>(): FeedSnapshot<T> | null {
  if (typeof window === "undefined") return null;
  try {
    return parseFeedSnapshot<T>(window.sessionStorage.getItem(FEED_SNAPSHOT_KEY));
  } catch {
    return null;
  }
}

export function writeFeedSnapshot<T>(snapshot: FeedSnapshot<T>): void {
  if (typeof window === "undefined") return;
  try {
    const raw = serializeFeedSnapshot(snapshot);
    if (raw === null) return;
    window.sessionStorage.setItem(FEED_SNAPSHOT_KEY, raw);
  } catch {
    // Over quota is the expected failure. Drop the edition rather than leave a
    // truncated one behind — a partial edition parses fine and restores wrong.
    try {
      window.sessionStorage.removeItem(FEED_SNAPSHOT_KEY);
    } catch {
      /* storage is unavailable entirely; nothing to clean up */
    }
  }
}

export function readScrollMark(now: number): FeedScrollMark | null {
  if (typeof window === "undefined") return null;
  try {
    return parseScrollMark(window.sessionStorage.getItem(FEED_SCROLL_KEY), now);
  } catch {
    return null;
  }
}

export function writeScrollMark(mark: FeedScrollMark): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(FEED_SCROLL_KEY, serializeScrollMark(mark));
  } catch {
    /* a lost scroll mark costs the landing, not the page */
  }
}

export function clearFeedRestore(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(FEED_SNAPSHOT_KEY);
    window.sessionStorage.removeItem(FEED_SCROLL_KEY);
  } catch {
    /* nothing to clear */
  }
}
