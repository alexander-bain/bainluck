// L2-214 Item 1 — Discover web request shape: one bounded initial request and
// monotonic pagination from the returned page boundary.
//
// This is the single source of truth for the request plan so the Discover page
// and its tests share the SAME production logic (no cloned helper). The rules
// enforced here mirror backend/scripts/evals/feed_speed_fixtures.json:
//   • the initial request is bounded to FEED_PAGE_LIMIT (<= initial_page_limit_max)
//   • pagination offsets are strictly increasing and never re-request offset 0
//   • rendered items are de-duplicated by their stable id across pages

/** Bounded first-paint page size. Kept small so the first cards render fast and
 *  the remainder streams in on scroll, instead of pulling the whole feed up front. */
export const FEED_PAGE_LIMIT = 20;

/** The event/futures mix every Discover feed request asks for.
 *
 *  LAT-P184 lifted this out of `app/discover/page.tsx`, where the same literal
 *  appeared at each call site. The boot fetch in `feedBoot.ts` has to build a
 *  URL that is byte-identical to the one `fetchFeed` puts on the wire, and two
 *  copies of a magic number in two files is exactly how that stops being true. */
export const FEED_EVENT_PCT = 0.15;

export interface FeedRequestPlan {
  limit: number;
  offset: number;
}

/** The single initial (offset-zero) request. Exactly one owner should issue this. */
export function initialFeedRequest(): FeedRequestPlan {
  return { limit: FEED_PAGE_LIMIT, offset: 0 };
}

/**
 * The next page request, advancing monotonically from the number of items already
 * loaded. Never re-requests offset 0 as pagination — the boundary is exactly the
 * count already held, so offsets march 0 → 20 → 40 … with no overlap or regression.
 */
export function nextFeedRequest(loadedCount: number): FeedRequestPlan {
  // Offset is exactly the number of items already held — the returned page
  // boundary — so pages march 0 → 20 → 40 … with no overlap. Floored at 1 so a
  // paginated request can never masquerade as a second offset-zero fetch.
  const offset = Math.max(1, loadedCount);
  return { limit: FEED_PAGE_LIMIT, offset };
}

/**
 * Whether the auto-pager should fetch the next page RIGHT NOW.
 *
 * LAT-P171. This lived inline in `app/discover/page.tsx` as
 * `visibleCount >= processedItems.length - 5 && hasMore && !loadingMore`, which
 * is true on the very first commit: `visibleCount` starts at `FEED_PAGE_LIMIT`
 * and `renderedCount` is 0, so the test reads `20 >= -5`. A cold load therefore
 * issued `/api/feed?limit=20&offset=1` — `nextFeedRequest` floors the offset at
 * 1 — concurrently with the `offset=0` request that gates the first card. That
 * is a second full feed build, at an offset the backend prewarm does not cover,
 * returning a page that overlaps page one by 19 of 20 items. The 2026-08-31
 * browser rail observed it as `net::ERR_ABORTED` on that exact URL.
 *
 * 🔴 `renderedCount > 0` IS THE PRECONDITION, NOT A THRESHOLD TWEAK. "The reader
 * is running out of rendered items" cannot be true before any item has rendered.
 * It does not risk stranding an exhausted feed: an empty page one closes
 * `has_more` through the availability decision, so pagination is already over.
 *
 * Extracted here rather than left in the component because this harness renders
 * with `renderToStaticMarkup`, which never runs effects — inline, the predicate
 * has no test path at all.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * LAT-P172 — THE SAME BUG ONE COMMIT LATER, AND IT COST A WHOLE FEED BUILD.
 *
 * `renderedCount > 0` closed the mount case and left the FIRST-PAINT case wide
 * open. The visible window is seeded to `PAGE_SIZE`, which is the same 20 the
 * first page returns, so the instant page one lands the comparison reads
 * `20 >= 20 - 5` — TRUE — and Discover issued a second full `/api/feed` build
 * before the reader had scrolled a single pixel.
 *
 * Fable's browser measurement of 2026-08-31 caught it on the wire: three
 * `/api/feed` requests on one cold page load, the third starting at 1,727 ms —
 * 78 ms after the first returned at 1,649 ms, which is one React commit — and
 * running until 4,425 ms. Content was not complete until that third request
 * finished. Two of the three were never asked for by the reader.
 *
 * 🔴 THE PREDICATE COULD NOT TELL "THE READER CONSUMED THE WINDOW" FROM "THE
 * WINDOW JUST ARRIVED". `visibleCount === renderedCount` is the definition of
 * first paint, not the definition of running out. The precondition that
 * distinguishes them is whether the window has ever been ADVANCED past the
 * value it was seeded with — which only the infinite-scroll sentinel does, and
 * only when the reader scrolls it into view.
 *
 * It does not strand a short page. If page one renders fewer cards than fill
 * the screen, the sentinel is immediately in view, the observer advances the
 * window, and the next line of this function fetches — the same path a scroll
 * takes, arrived at without one. That self-healing is asserted in
 * `__tests__/lib/discoverColdPagerRace.test.ts`, not assumed here.
 *
 * ⚠️ WHAT IT COSTS, STATED PLAINLY: page two is no longer in hand before the
 * reader reaches the bottom of page one. The lead time is now the sentinel's
 * `rootMargin` (400 px) instead of a whole page. That eager prefetch was never
 * designed — it was an accident of seeding the window to exactly the page size
 * — but it was real, and trading it for the cold path is a choice, not a
 * free win.
 *
 * ────────────────────────────────────────────────────────────────────────────
 * CERT-603 (BLOCK, P1) — `renderedCount` WAS THE WRONG SIGNAL FOR "HAS A PAGE
 * LANDED", AND THE COST WAS A PERMANENTLY BLANK FEED.
 *
 * LAT-P171 gated the cold mount on `renderedCount === 0`, reading it as "no page
 * has arrived yet". It is not. The caller passes `processedItems.length`, which
 * is DOWNSTREAM of renderability (L2-215 empty-envelope fail-closed), staleness,
 * local dismissal and category suppression. A perfectly good non-empty page can
 * land with backend `has_more = true` and filter to zero rendered rows.
 *
 * In that reachable state the old precondition disabled pagination permanently:
 * nothing rendered, so it never paged; it never paged, so nothing ever rendered.
 * The reader sits on a blank Discover surface while later pages exist. That
 * directly contradicts the L2-215 contract written at `page.tsx:887-891` — "the
 * auto-pager keeps fetching when this shortens a page, so it can never leave a
 * blank tab" — which the precondition had quietly revoked.
 *
 * 🔴 THE FIX IS TO SEPARATE THE TWO QUESTIONS THAT `renderedCount` WAS ANSWERING
 * AT ONCE. `loadedCount` is the RAW count of items received from the API before
 * any client filter, so it answers "did a page land" and nothing else.
 * `renderedCount` answers "is there anything on screen". The cold mount is
 * `loadedCount === 0`. A landed-but-fully-filtered page is `loadedCount > 0 &&
 * renderedCount === 0`, and it MUST page — that is the only way out of a blank
 * tab, and it is exactly what L2-215 promises.
 *
 * ⚠️ That branch deliberately ignores the window preconditions. A reader with
 * nothing on screen cannot scroll, so demanding an advanced window would
 * reinstate the deadlock in a new place. It walks forward a page at a time until
 * something renders or `has_more` closes; `loadingMore` serialises it, so it is
 * a walk, not a storm. On a feed whose every remaining page filters to nothing
 * this will page to exhaustion — which is the honest outcome and is what an
 * empty feed's end state is for.
 */
export function shouldLoadNextPage(state: {
  /** Cards the reader can currently see. */
  visibleCount: number;
  /**
   * RAW items received from the API across every page so far, BEFORE any
   * client-side filter. This — not `renderedCount` — is the "a page has landed"
   * signal (CERT-603).
   */
  loadedCount: number;
  /** Cards actually on screen: `loadedCount` after renderability, staleness,
   *  dismissal and suppression filtering. Can be 0 while `loadedCount` is not. */
  renderedCount: number;
  /**
   * The value `visibleCount` is seeded with on mount. The window has been
   * advanced — by the sentinel observer, which fires only on real content —
   * exactly when `visibleCount` exceeds it.
   */
  initialVisibleCount: number;
  /** The backend has not yet said the feed is exhausted. */
  hasMore: boolean;
  /** A pagination request is already in flight. */
  loadingMore: boolean;
}): boolean {
  const { visibleCount, loadedCount, renderedCount, initialVisibleCount, hasMore, loadingMore } =
    state;
  // Terminals first: exhausted or already in flight beats every other reason.
  if (!hasMore || loadingMore) return false;
  // Nothing has come back from the API yet. This is the cold mount, and it is
  // the ONLY state that means "page one has not landed" (CERT-603).
  if (loadedCount === 0) return false;
  // A page landed and every row was filtered away. Paging is the only way out
  // of a blank tab, and the reader cannot scroll to ask for it (L2-215).
  if (renderedCount === 0) return true;
  // The reader has not touched the window the page was seeded with: this is
  // first paint, not running out (LAT-P172).
  if (visibleCount <= initialVisibleCount) return false;
  return visibleCount >= renderedCount - PAGINATION_LOOKAHEAD;
}

/** How many unseen cards may remain before the next page is fetched. */
export const PAGINATION_LOOKAHEAD = 5;

/**
 * Whether the reveal window should advance by one page.
 *
 * #8176 — THE WINDOW ADVANCE IS A LEVEL, NOT AN EDGE. This existed inline in
 * `page.tsx` as an `IntersectionObserver` callback that incremented on the
 * transition into intersecting. An observer only fires when intersection
 * CHANGES, and the reveal window is the only thing that makes the document
 * taller (rendering is `processedItems.slice(0, visibleCount)`). So once the
 * window stopped advancing, the document stopped growing, the sentinel stayed
 * inside the 400px `rootMargin` band, and no further transition was ever
 * produced: the window was frozen by the fact that it was frozen.
 *
 * Measured on production at 390px signed out: the feed stopped at
 * `visibleCount = 40` against `renderedCount = 48` with `has_more = true` and
 * 67 more cards on the server, showing a spinner that could never resolve —
 * `visibleCount < renderedCount` keeps the spinner branch true, and
 * `EndOfFeedCard` needs `visibleCount >= renderedCount`, so the reader gets an
 * indefinite loader and can never reach the honest end state. Scrolling up 200px
 * (inside the band) produced 0 requests across 71s; scrolling up 1600px (out of
 * the band) resumed paging immediately and ran the feed to completion.
 *
 * Asking the question as a level — "is the sentinel in view and is the window
 * still behind the content" — cannot deadlock, because it is re-asked on every
 * commit rather than only on a transition the frozen document cannot produce.
 *
 * 🔴 THE `+ PAGE_SIZE` BOUND IS WHAT KEEPS THIS FROM BECOMING A FETCH STORM, AND
 * IT IS ALSO WHY THE COLD PATH STILL WORKS. Both halves matter:
 *
 *  - Without a bound, a sentinel parked in view advances the window on every
 *    commit while a page is in flight. Nothing new can render, so the document
 *    never grows, so the sentinel never leaves the band — `visibleCount` inflates
 *    without limit and `shouldLoadNextPage` walks the feed to exhaustion while
 *    the reader sits still. That is the uninvited-fetch defect LAT-P172 and
 *    #7417 were both about, re-entering through a new door.
 *  - Bounding at `renderedCount` alone (rather than one page past it) would kill
 *    pagination outright on the cold path: page one lands filtered to fewer rows
 *    than the seed window, so `visibleCount` already equals or exceeds
 *    `renderedCount`, the window could never advance past
 *    `initialVisibleCount`, and `shouldLoadNextPage`'s LAT-P172 gate would read
 *    that as "the reader has not scrolled" forever.
 *
 * One page past the content is exactly the room needed to signal "the reader
 * wants more" to the pager, and no more. The natural terminator is unchanged:
 * revealing cards makes the document taller, which pushes the sentinel out of
 * the band, which sets `sentinelVisible` false.
 */
export function shouldAdvanceWindow(state: {
  /** The sentinel is inside the observer's band RIGHT NOW — a level, not an edge. */
  sentinelVisible: boolean;
  /** Cards the reader can currently see. */
  visibleCount: number;
  /** Cards available to show: `processedItems.length`, independent of `visibleCount`. */
  renderedCount: number;
  /**
   * A scroll restore is still landing. #7417: the reader is clamped at the
   * bottom of a growing document for reasons that have nothing to do with them
   * running out of cards, and the restore is about to move them away.
   */
  restorePending: boolean;
  /** The page size the window advances by. */
  pageSize: number;
}): boolean {
  const { sentinelVisible, visibleCount, renderedCount, restorePending, pageSize } = state;
  if (!sentinelVisible) return false;
  if (restorePending) return false;
  return visibleCount < renderedCount + pageSize;
}

/**
 * Fold a fresh page-one payload into the one the reader is already looking at.
 *
 * #4430 — Alex, reading Discover on the web the morning of 2026-09-09: "cards
 * vanished mid-read twice (crude-oil card, others)". This is the web half of
 * #4110, which fixed the same class on iOS and never shipped here.
 *
 * `app/discover/page.tsx` revalidates page one every 120 s and assigned the
 * result straight over the top — `setPage1Items(data.items ?? [])` — for the
 * initial load AND every background tick alike. There was no reconciliation of
 * any kind: whatever page one the server last returned simply became the
 * rendered list. Any re-rank between two ticks (a game starting or ending, a
 * dismissal, a personalization update) moved or removed a card out from under
 * a reader who had not asked for anything.
 *
 * 🔴 THE FIX IS TO HOLD THE READER'S EDITION, NOT TO MERGE-AND-PRUNE. A card
 * missing from a later payload has almost never gone anywhere — it has been
 * re-ranked onto page two. Dropping it is exactly the harm reported, so a
 * background revalidation here NEVER removes and NEVER reorders. It updates in
 * place (so prices, scores and clocks stay live) and appends what is genuinely
 * new.
 *
 * That is safe rather than merely stubborn because this is not the surface that
 * decides what a reader sees. Every real reason to drop a card is enforced
 * downstream, per render, in `page.tsx`'s `processedItems`: local dismissal
 * (`dismissed`), staleness (`isStale`), and the L2-215 empty-envelope
 * fail-closed (`feedItemHasRenderableContent`). Holding an id here cannot
 * resurrect a card any of those three would refuse — it only stops the feed
 * yanking one the reader is mid-sentence on.
 *
 * The cold load is the one case that assigns wholesale: with nothing on screen
 * there is no edition to protect, and the served page IS the edition.
 *
 * Order is the reader's, not the server's: `prev` order is preserved exactly,
 * which is what keeps a card under the eye that is reading it.
 */
export function reconcilePage1<T>(
  prev: T[],
  incoming: T[],
  getId: (item: T) => string,
): T[] {
  // Cold load (or a feed that emptied and came back): nothing to protect.
  if (prev.length === 0) return incoming;

  const incomingById = new Map<string, T>();
  for (const item of incoming) incomingById.set(getId(item), item);

  // Still-served cards take the fresh copy so live data keeps moving; cards the
  // server no longer lists on page one keep the copy the reader already has.
  const held = prev.map((item) => incomingById.get(getId(item)) ?? item);

  const heldIds = new Set(prev.map(getId));
  const appended = incoming.filter((item) => !heldIds.has(getId(item)));

  return [...held, ...appended];
}

/**
 * De-duplicate items by stable id, preserving first-seen order. Defense in depth
 * so a paging/coalesce hiccup can never render the same card twice.
 */
export function dedupeById<T>(items: T[], getId: (item: T) => string): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    const id = getId(item);
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}
