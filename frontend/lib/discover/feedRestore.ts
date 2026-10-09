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

import type { ContinuationSections } from "./continuationSections";
import {
  decodeContinuationDeck,
  decodeUnsectionedDeck,
  encodeContinuationDeck,
  encodeUnsectionedDeck,
  type StoredContinuationDeck,
  type StoredUnsectionedDeck,
} from "./continuationSnapshot";

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
 * #5105 — the version a snapshot carrying a section deck is written under.
 *
 * Deliberately NOT a bump of `FEED_SNAPSHOT_VERSION`: legacy snapshots and the
 * scroll mark keep version 2 and their exact bytes. It is a distinct value so
 * that any reader that does not opt into sections — an older build, or today's
 * page — refuses the edition (a cold load) instead of flattening the
 * continuation back into the opening.
 */
export const FEED_SECTION_SNAPSHOT_VERSION = "2+continuation.1";

/**
 * #5105 — the version a TOKENED deck with no continuation is written under,
 * for the same reason as the section version: a reader that does not opt in
 * refuses it (a cold load) rather than read a pinned edition as a token-less
 * legacy one. Only a section-aware writer that passes the deck's raw `cursor`
 * produces it; without one, such a deck still writes today's v2 bytes.
 */
export const FEED_EDITION_SNAPSHOT_VERSION = "2+edition.1";

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

/** #5105 — opt into section decks. Identity is the caller's (the page's `getItemId`). */
export interface FeedSectionOptions<T> {
  getId: (item: T) => string;
}

/** A snapshot read by a section-aware caller. `null` sections = a legacy edition. */
export interface FeedSectionSnapshot<T> extends FeedSnapshot<T> {
  sections: ContinuationSections<T> | null;
  /** The raw server offset a section edition resumes paging from; present only
   *  when the writer supplied one (see `FeedSectionWrite.cursor`). */
  cursor?: number;
}

/**
 * #5105 — what a section-aware writer passes. `cursor` is the accepted deck's
 * RAW server cursor (`EditionDeck.nextOffset`), never a count of held cards.
 *
 * 🔴 THE CAP DECIDES WHERE PAGING RESUMES. The snapshot keeps only the first
 * `FEED_SNAPSHOT_MAX_ITEMS` cards. Restoring 120 of 160 accepted cards with the
 * old cursor (160) would skip the 40 it dropped; restoring them with the old
 * `hasMore: false` would strand them. With a cursor, the stored cursor is the
 * lowest server position the deck received but the snapshot did not keep (or
 * the deck's own cursor when it kept everything), and `hasMore` is stored true
 * whenever that moved the cursor back — the server answers for what is really
 * left. A card held but not kept for any reason moves the cursor back, so a
 * filter, a hole or a duplicate-only page can never move it forward.
 */
export type FeedSectionWrite<T> = { deck: ContinuationSections<unknown> | null; cursor?: number } & FeedSectionOptions<T>;

/**
 * Whether a write carries an edition that must not be stored as legacy: a
 * section deck, or a tokened deck without a section whose writer passed its raw
 * cursor (`FEED_EDITION_SNAPSHOT_VERSION`). Everything else is today's v2.
 */
function writesEdition<T>(section: FeedSectionWrite<T> | undefined): section is FeedSectionWrite<T> & { deck: ContinuationSections<unknown> } {
  if (!section?.deck) return false;
  if (section.deck.boundary !== null) return true;
  return section.deck.edition !== null && section.cursor !== undefined;
}

interface StoredSnapshot<T> extends FeedSnapshot<T> {
  v: number;
}

interface StoredSectionSnapshot<T> extends FeedSnapshot<T> {
  v: typeof FEED_SECTION_SNAPSHOT_VERSION;
  sections: StoredContinuationDeck;
  cursor?: number;
}

interface StoredEditionSnapshot<T> extends FeedSnapshot<T> {
  v: typeof FEED_EDITION_SNAPSHOT_VERSION;
  sections: StoredUnsectionedDeck;
  cursor: number;
}

interface StoredScroll extends FeedScrollMark {
  v: number;
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isCursor(value: unknown, total: number): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= total;
}

/** The retained frontier: see `FeedSectionWrite`. Null when the cursor is not a raw offset of this deck. */
function retainedFrontier(
  deck: ContinuationSections<unknown>,
  storedIds: ReadonlySet<string>,
  cursor: number,
  hasMore: boolean,
): { cursor: number; hasMore: boolean } | null {
  if (!isCursor(cursor, deck.total)) return null;
  let resume = cursor;
  for (const [id, position] of deck.positions) {
    if (!storedIds.has(id) && position < resume) resume = position;
  }
  return { cursor: resume, hasMore: hasMore || resume < cursor };
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
 *  keeping. An empty page one is a cold feed — there is no edition to protect.
 *
 *  #5105: with `section.deck` a section deck (non-null boundary), the edition is
 *  written under `FEED_SECTION_SNAPSHOT_VERSION` with each retained card's
 *  position evidence, and `null` is returned when that evidence cannot be bound
 *  — never a legacy snapshot of an intended section. A tokened deck without a
 *  section, written with its `cursor`, is stored the same way under
 *  `FEED_EDITION_SNAPSHOT_VERSION`. Without `section`, or with a legacy deck,
 *  the bytes are exactly today's. */
export function serializeFeedSnapshot<T>(
  snapshot: FeedSnapshot<T>,
  section?: FeedSectionWrite<T>,
): string | null {
  if (!Array.isArray(snapshot.page1) || snapshot.page1.length === 0) return null;
  const capped = capSnapshotItems(snapshot.page1, snapshot.rest ?? []);
  if (writesEdition(section) && section.deck.boundary === null && section.cursor !== undefined) {
    const sections = encodeUnsectionedDeck(section.deck, [...capped.page1, ...capped.rest], section.getId);
    if (!sections) return null;
    const frontier = retainedFrontier(section.deck, new Set(sections.cards.map(([id]) => id)), section.cursor, snapshot.hasMore);
    if (!frontier) return null;
    const stored: StoredEditionSnapshot<T> = {
      v: FEED_EDITION_SNAPSHOT_VERSION,
      page1: capped.page1,
      rest: capped.rest,
      visibleCount: snapshot.visibleCount,
      hasMore: frontier.hasMore,
      sections,
      cursor: frontier.cursor,
    };
    return JSON.stringify(stored);
  }
  if (section?.deck && section.deck.boundary !== null) {
    const sections = encodeContinuationDeck(section.deck, [...capped.page1, ...capped.rest], section.getId);
    if (!sections) return null;
    let paging: { cursor?: number; hasMore: boolean } = { hasMore: snapshot.hasMore };
    if (section.cursor !== undefined) {
      // `encodeContinuationDeck` bound every stored card to an id, so these are its ids.
      const frontier = retainedFrontier(section.deck, new Set(sections.cards.map(([id]) => id)), section.cursor, snapshot.hasMore);
      if (!frontier) return null;
      paging = frontier;
    }
    const stored: StoredSectionSnapshot<T> = {
      v: FEED_SECTION_SNAPSHOT_VERSION,
      page1: capped.page1,
      rest: capped.rest,
      visibleCount: snapshot.visibleCount,
      hasMore: paging.hasMore,
      sections,
      ...(paging.cursor !== undefined ? { cursor: paging.cursor } : {}),
    };
    return JSON.stringify(stored);
  }
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
export function parseFeedSnapshot<T>(raw: string | null): FeedSnapshot<T> | null;
/**
 * #5105 — the section-aware read. Accepts a legacy (v2) edition as
 * `sections: null` and a section edition only when its deck rebuilds through
 * the adapter against exactly the stored cards. A v2 body carrying section
 * evidence, or a section body whose evidence is missing or does not bind, is
 * refused — it never falls through to legacy. A tokened edition without a
 * section (`FEED_EDITION_SNAPSHOT_VERSION`) is read the same way, with
 * `sections.boundary` null and its required cursor.
 */
export function parseFeedSnapshot<T>(raw: string | null, section: FeedSectionOptions<T>): FeedSectionSnapshot<T> | null;
export function parseFeedSnapshot<T>(
  raw: string | null,
  section?: FeedSectionOptions<T>,
): FeedSnapshot<T> | FeedSectionSnapshot<T> | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const candidate = parsed as
    | Partial<StoredSnapshot<T>>
    | Partial<StoredSectionSnapshot<T>>
    | Partial<StoredEditionSnapshot<T>>;
  if (candidate.v === FEED_SNAPSHOT_VERSION) {
    // `sections` is reserved for the section edition. A v2 body carrying it is
    // contradictory, and BOTH readers refuse it — the default reader returning
    // its cards would flatten a continuation into the opening. Today's v2
    // bytes never hold the field, so their read is unchanged.
    if ("sections" in candidate) return null;
    const snapshot = readStoredEdition(candidate);
    if (!snapshot || !section) return snapshot;
    return { ...snapshot, sections: null };
  }
  // Without the opt-in a section or tokened edition is refused exactly as an
  // unknown version is: a cold load, not a flattened or unpinned deck.
  if (candidate.v === FEED_EDITION_SNAPSHOT_VERSION && section) {
    const snapshot = readStoredEdition(candidate);
    if (!snapshot) return null;
    const sections = decodeUnsectionedDeck(
      (candidate as Partial<StoredEditionSnapshot<T>>).sections,
      [...snapshot.page1, ...snapshot.rest],
      section.getId,
    );
    if (!sections) return null;
    const cursor = (candidate as Partial<StoredEditionSnapshot<T>>).cursor;
    if (!isCursor(cursor, sections.total)) return null;
    return { ...snapshot, sections, cursor };
  }
  if (candidate.v !== FEED_SECTION_SNAPSHOT_VERSION || !section) return null;
  const snapshot = readStoredEdition(candidate);
  if (!snapshot) return null;
  const sections = decodeContinuationDeck(
    (candidate as Partial<StoredSectionSnapshot<T>>).sections,
    [...snapshot.page1, ...snapshot.rest],
    section.getId,
  );
  if (!sections) return null;
  // A section edition's resume cursor is optional; one that is present must be
  // a raw offset inside the deck, or the edition is refused.
  if (!("cursor" in candidate)) return { ...snapshot, sections };
  const cursor = (candidate as Partial<StoredSectionSnapshot<T>>).cursor;
  if (!isCursor(cursor, sections.total)) return null;
  return { ...snapshot, sections, cursor };
}

function readStoredEdition<T>(candidate: Partial<FeedSnapshot<T>>): FeedSnapshot<T> | null {
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

export function readFeedSnapshot<T>(): FeedSnapshot<T> | null;
export function readFeedSnapshot<T>(section: FeedSectionOptions<T>): FeedSectionSnapshot<T> | null;
export function readFeedSnapshot<T>(
  section?: FeedSectionOptions<T>,
): FeedSnapshot<T> | FeedSectionSnapshot<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(FEED_SNAPSHOT_KEY);
    return section ? parseFeedSnapshot<T>(raw, section) : parseFeedSnapshot<T>(raw);
  } catch {
    return null;
  }
}

export function writeFeedSnapshot<T>(
  snapshot: FeedSnapshot<T>,
  section?: FeedSectionWrite<T>,
): void {
  if (typeof window === "undefined") return;
  if (writesEdition(section)) {
    writeSectionSnapshot(snapshot, section);
    return;
  }
  try {
    const raw = serializeFeedSnapshot(snapshot, section);
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

/**
 * #5105 — a section edition's write. Encoding happens BEFORE storage is touched:
 * evidence that will not bind, or a card that cannot be encoded, is a refusal
 * and leaves the stored edition exactly as it was. Missing evidence for a new
 * candidate does not prove the accepted edition expired; resetting or replacing
 * it is the caller's decision. Only a failed `setItem` reaches today's cleanup.
 */
function writeSectionSnapshot<T>(
  snapshot: FeedSnapshot<T>,
  section: FeedSectionWrite<T>,
): void {
  let raw: string | null;
  try {
    raw = serializeFeedSnapshot(snapshot, section);
  } catch {
    return;
  }
  if (raw === null) return;
  try {
    window.sessionStorage.setItem(FEED_SNAPSHOT_KEY, raw);
  } catch {
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
