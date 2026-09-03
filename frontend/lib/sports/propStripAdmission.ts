/**
 * UX-P276 / #2710 — a props-strip card that carries no number is not shown.
 *
 * Alex, filing #2710 against mobile `/sports`: "every outcome is a dash …
 * Rule: a card with no number is not shown." The strip renders whatever
 * `GET /api/futures/grouped-feed` returns, one card per row, with no admission
 * of any kind — so a market that arrives carrying `outcomes: []` renders a
 * full-height card whose body is the words "No outcomes available"
 * (`components/FuturesCard.tsx`), and a market whose outcomes are all
 * null-priced renders a column of dashes. Measured on the served payload at the
 * page's own `limit: 20` on 2026-09-03: 2 of 20 rows carried `outcomes: []`.
 *
 * WHY THIS EXISTS ALONGSIDE THE BACKEND FILTER, WHICH IS THE REAL FIX. The
 * route drops these before truncating now, so the reader gets 20 cards that
 * each say something instead of 18. But `/api/futures/grouped-feed` is
 * Redis-cached fresh-then-stale (LAT-P100), so a warm entry written before that
 * deploy keeps serving outcome-less rows for its whole TTL. Without a guard at
 * the renderer the fix is invisible until the cache turns over. The two are
 * deliberately not the same check: the backend one buys back the wasted slot,
 * this one is what makes the card unable to render bare.
 *
 * NOT `feedItemSuppressionReason` (`components/discover/utils.ts`) and NOT
 * `contracts/feed_card_admission.json`. That rule is the DISCOVER card
 * admission decision: its producer is `backend/app/routes/feed.py`, its
 * `emitted_types` are `event`/`futures`/`tournament`/`concept`, and its header
 * says in terms that an arm changed on one surface only is "#1939, #1935 and
 * #1951 in turn, three times in five weeks". The props strip is a different
 * endpoint with a different taxonomy (`market`/`threshold`/`stat_prop`/
 * `playoff_progression`) and none of those types appear in that contract.
 * Widening the contract to cover them, or calling it with a shape it does not
 * describe, is that same cross-surface mistake pointed the other way. What is
 * borrowed here is the SHAPE of the rule — per-type arms, fail closed — not the
 * rule itself.
 */
import type { GroupedFeedItem } from "@/lib/types";

/** A probability we would actually print, as opposed to a dash. */
function isShowableProbability(p: number | null | undefined): boolean {
  return typeof p === "number" && Number.isFinite(p);
}

/**
 * UX-1052 item 2 — can this ladder rung be LABELLED?
 *
 * Alex's rule, filing the exact-score ladders: "a rung that cannot be labelled
 * is not rendered." `buildThresholdRungs` enforces it in the renderer by
 * dropping such points; this is the same test at the admission boundary, so
 * the count beside "Player Props & Progressions" cannot claim a card that the
 * renderer then declines to draw — the #2646 class this module was written for.
 *
 * A point is labelable when the backend sent an explicit label (exact-score
 * scorelines) or when it is a genuine directional threshold the client can
 * format as "≥ N". A point marked `exact` with no label is neither.
 */
function isLabelableRung(p: {
  label?: string | null;
  threshold_direction?: string;
}): boolean {
  if ((p?.label ?? "").trim()) return true;
  return p?.threshold_direction !== "exact";
}

/**
 * Does this grouped-feed row carry at least one number the card can print?
 *
 * FAIL CLOSED. An unrecognised `type` returns `false`: a row shape this build
 * does not understand cannot be shown to have a number, and the failure we are
 * fixing is precisely a card rendered bare. A new row type must opt in here,
 * which is a compile-and-test change rather than a silent regression.
 */
export function groupedFeedRowHasNumber(item: GroupedFeedItem): boolean {
  if (!item || typeof item !== "object") return false;
  switch (item.type) {
    case "market":
      return (item.market?.outcomes ?? []).some((o) =>
        isShowableProbability(o?.probability),
      );
    case "threshold":
      return (item.points ?? []).some(
        (p) => isShowableProbability(p?.probability) && isLabelableRung(p),
      );
    case "placement_grid":
      // UX-1052 item 3. Every cell may legitimately be "—" for a given player,
      // so the row is not the unit — the GRID needs at least one real number
      // somewhere, and at least one column to put it under.
      return (
        (item.columns ?? []).length > 0 &&
        (item.rows ?? []).some((r) =>
          Object.values(r?.values ?? {}).some(isShowableProbability),
        )
      );
    case "stat_prop":
      return (item.lines ?? []).some((l) =>
        isShowableProbability(l?.probability),
      );
    case "playoff_progression":
      return (item.stages ?? []).some((s) =>
        isShowableProbability(s?.probability),
      );
    default:
      return false;
  }
}

/**
 * The rows the strip will actually render.
 *
 * The section heading prints a count beside it, and that count is what makes
 * this a shared helper rather than a filter inlined in the renderer: counting
 * the arrived rows while rendering the admitted ones is #2646 — a page stating
 * a number larger than the thing it puts on screen. Both the heading and the
 * grid read this one list.
 */
export function admittedPropStripRows(
  items: readonly GroupedFeedItem[] | null | undefined,
): GroupedFeedItem[] {
  if (!items) return [];
  return items.filter(groupedFeedRowHasNumber);
}
