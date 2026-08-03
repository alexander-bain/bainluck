"use strict";

/**
 * L2-239 Item 0 — what the main region actually rendered, as a pure function.
 *
 * The defect this exists to kill: `content.main_region_nonblank` was computed
 * inline in the spec as `mainText.trim().length > 40 && !skeletonVisible`, and
 * that second clause made the check unfalsifiable on one of the two surfaces it
 * grades.
 *
 * `/` and `/discover` render the SAME component — `app/page.tsx` is a bare
 * re-export of `app/discover/page`. But `/discover` is a route SEGMENT, so Next
 * also emits `app/discover/loading.tsx` as its Suspense fallback, and the
 * deployed `/discover` document therefore carries TWO `discover-skeleton`
 * markers where `/` carries one. `page.locator(SKELETON).first().isVisible()`
 * answered for whichever marker came first in DOM order, so a leftover route
 * shell zeroed the verdict no matter what the feed had done. Runs 30830689689
 * and 30830999441 both reported `/discover` RED at both viewports while their
 * terminal screenshots showed a fully populated 30,165px feed, and `/` — same
 * component, same feed — passed.
 *
 * A permanently-red assertion is not a strict assertion. It is an unread one,
 * which is the exact failure mode this whole rail exists to prevent.
 *
 * The fix is NOT "ignore skeletons". A page that is nothing but a skeleton is
 * still a page that never resolved, and that must stay red. The fix is to rank
 * the evidence: **rendered substance outranks a loading marker.** If the main
 * region holds real text OUTSIDE every skeleton subtree, the feed resolved and
 * a stale/inert/duplicated shell alongside it is noise. If it does not, the
 * visible skeleton is the whole story and the region is not content.
 *
 * Two properties this deliberately keeps:
 *
 *   - It never reads the card hook. `content.real_card_or_named_empty` grades
 *     the card/empty-state testids; this grades text volume. Two checks that
 *     consult the same signal cannot catch each other's false positive, and the
 *     card selector has produced one before (L2-223's `break-inside-avoid`).
 *   - Incoherent measurements are their OWN outcome, not a quiet pass or a
 *     quiet fail-with-the-wrong-reason. Malformed markup that makes the skeleton
 *     text exceed the region text means the observation cannot be trusted at
 *     all, and the report should say so.
 */

/** Below this many non-skeleton characters, the region is not showing content. */
const MIN_CONTENT_CHARS = 40;

/** Terminal classifications. */
const CONTENT_STATES = Object.freeze({
  /** Real rendered text outside every skeleton. */
  CONTENT: "content",
  /** Nothing but a visible loading placeholder. */
  LOADING: "loading",
  /** No skeleton, and nothing to read either. */
  BLANK: "blank",
  /** The measurements contradict each other — grade nothing on them. */
  MALFORMED: "malformed",
});

function isCount(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/**
 * @param {{textLength?: number, skeletonTextLength?: number, visibleSkeletonCount?: number, minChars?: number}} input
 * @returns {{state: string, nonBlank: boolean, detail: string}}
 */
function classifyMainRegion(input) {
  const o = input || {};
  const minChars = isCount(o.minChars) ? o.minChars : MIN_CONTENT_CHARS;

  // --- Coherence first. A measurement that cannot be true is never a verdict.
  if (!isCount(o.textLength) || !isCount(o.skeletonTextLength) || !isCount(o.visibleSkeletonCount)) {
    return {
      state: CONTENT_STATES.MALFORMED,
      nonBlank: false,
      detail:
        "main-region measurements are missing or not counts " +
        `(text=${o.textLength}, skeleton=${o.skeletonTextLength}, visibleSkeletons=${o.visibleSkeletonCount})`,
    };
  }
  if (o.skeletonTextLength > o.textLength) {
    return {
      state: CONTENT_STATES.MALFORMED,
      nonBlank: false,
      detail:
        `skeleton text (${o.skeletonTextLength} chars) exceeds the whole main region ` +
        `(${o.textLength} chars) — the markup or the read is broken`,
    };
  }

  const contentChars = o.textLength - o.skeletonTextLength;

  // --- Substance outranks a loading marker. This is the whole ruling: a
  //     leftover route-segment shell beside a rendered feed is noise, and a
  //     surface must not grade differently from its twin because of it.
  if (contentChars > minChars) {
    return {
      state: CONTENT_STATES.CONTENT,
      nonBlank: true,
      detail:
        `${contentChars} chars of non-skeleton content` +
        (o.visibleSkeletonCount > 0
          ? ` (${o.visibleSkeletonCount} skeleton marker(s) still mounted alongside it)`
          : ""),
    };
  }

  // --- Nothing resolved. Say WHICH nothing: still loading, or simply blank.
  if (o.visibleSkeletonCount > 0) {
    return {
      state: CONTENT_STATES.LOADING,
      nonBlank: false,
      detail:
        `only the loading skeleton rendered — ${o.visibleSkeletonCount} visible marker(s) ` +
        `and ${contentChars} chars of content (min ${minChars})`,
    };
  }
  return {
    state: CONTENT_STATES.BLANK,
    nonBlank: false,
    detail: `main region rendered blank — ${contentChars} chars of content (min ${minChars})`,
  };
}

module.exports = {
  MIN_CONTENT_CHARS,
  CONTENT_STATES,
  classifyMainRegion,
};
