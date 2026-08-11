/**
 * entityPageChrome — the §4 chrome-earning grammar, client side.
 *
 * Spec: `docs/entity-page-templates.md` §4. Ruling 027. Epic #1741, step 0 (#1742).
 *
 * ── THE ONE RULE THIS FILE EXISTS TO ENFORCE ──
 *
 * Containers are gated, not items. A section header over one card, a two-card
 * carousel, "+1 more" — each is the page apologizing for its own existence. Every
 * rule below is a count check, applied ONCE for every entity class, so a thin
 * league page and a thin team page cannot disagree about what a header is for.
 *
 * ── WHY THE CONSTANTS ARE DUPLICATED FROM PYTHON, AND WHY THAT IS SAFE ──
 *
 * They are not really duplicated: `__tests__/lib/entityPageChromeParity.test.ts`
 * reads `backend/app/utils/entity_page_tiers.py` and asserts every value here
 * equals the value there. A rule duplicated in TypeScript and Python is two
 * rules — this lane has filed that shape (#1620) eleven times — so the copy is
 * mechanically pinned rather than trusted.
 *
 * The backend remains the AUTHORITY for the tier itself (ruling 021): `tier`
 * arrives as a typed field and is never re-derived here. What lives client-side
 * is only the rendering grammar that consumes it.
 */

export type EntityTier = "full" | "standard" | "answer" | "present";

/** Ruling 025's conforming vocabulary. Never `live`/`stale_ok`/`unavailable`. */
export type EntityAvailability = "fresh" | "stale" | "degraded" | "empty";

/** A section header organizes; below two items it labels a pair. */
export const CHROME_SECTION_HEADER_MIN_ITEMS = 2;
/** ...and a header needs something to distinguish it FROM. */
export const CHROME_SECTION_HEADER_MIN_SECTIONS = 2;
/** A rail that does not scroll is a broken carousel. */
export const CHROME_RAIL_MIN_ITEMS = 4;
/** A grid that renders one orphaned row is a stack with extra steps. */
export const CHROME_GRID_MIN_ITEMS = 3;
/** "+1 more" is an apology; render the one extra item instead. */
export const CHROME_MORE_LINK_MIN_HIDDEN = 2;
/** An anchor nav with two anchors is two links pretending to be navigation. */
export const CHROME_ANCHOR_NAV_MIN_SECTIONS = 3;
/** A movers strip below this is a list of one thing that moved. */
export const CHROME_MOVERS_MIN = 3;

/**
 * A section header earns its place when it organizes a group a reader could
 * otherwise lose track of, AND there is another section to distinguish it from.
 *
 * Register E1, verbatim: the hub page renders a header + count chip over a single
 * card. That is the broken shelf in its purest form.
 */
export function earnsSectionHeader(itemCount: number, sectionCount: number): boolean {
  return (
    itemCount >= CHROME_SECTION_HEADER_MIN_ITEMS &&
    sectionCount >= CHROME_SECTION_HEADER_MIN_SECTIONS
  );
}

export function earnsRail(itemCount: number): boolean {
  return itemCount >= CHROME_RAIL_MIN_ITEMS;
}

export function earnsGrid(itemCount: number): boolean {
  return itemCount >= CHROME_GRID_MIN_ITEMS;
}

/** Register E1: `+{n} more` currently fires at n=1. Render the extra item. */
export function earnsMoreLink(hiddenCount: number): boolean {
  return hiddenCount >= CHROME_MORE_LINK_MIN_HIDDEN;
}

export function earnsAnchorNav(renderingSectionCount: number): boolean {
  return renderingSectionCount >= CHROME_ANCHOR_NAV_MIN_SECTIONS;
}

export function earnsMoversStrip(moverCount: number): boolean {
  return moverCount >= CHROME_MOVERS_MIN;
}

/**
 * A count chip is a STAT. At 1-3 answers the count is already visible and
 * printing it is the page apologizing for its size (spec §3 bans it at T1).
 *
 * Takes the tier rather than a number on purpose: this is the one grammar rule
 * that keys off the backend's declared decision instead of a local count, which
 * is precisely the ruling-021 posture the whole system is built on.
 */
export function earnsCountChip(tier: EntityTier | null | undefined): boolean {
  return tier === "full" || tier === "standard";
}

/**
 * The width of a probability bar, or `null` when there is no probability.
 *
 * Register E2: `width: ${pct ?? 0}%` renders a null probability as a 0%-wide bar,
 * which is a CLAIM — it says "we measured this and it is zero" about something we
 * did not measure. Doctrine A3: honest or absent. Callers must not render the bar
 * track at all when this returns null; a 0%-width bar inside a visible track is
 * the same lie with extra steps.
 */
export function probabilityBarWidth(probability: number | null | undefined): number | null {
  if (probability == null || Number.isNaN(probability)) return null;
  const pct = Math.round(probability * 100);
  return Math.max(0, Math.min(100, pct));
}

/**
 * How many items to render, and what to say about the rest.
 *
 * Spec §4: a cap is ALWAYS counted — "Showing X of Y". An uncounted cap reads as
 * coverage, which is ruling 025 clause 3's concealment. When the remainder is a
 * single item this returns it as shown instead: rendering "+1 more" costs the same
 * row as the item it is hiding.
 */
export function applyCountedCap(
  total: number,
  cap: number,
): { shown: number; hidden: number; showMoreLink: boolean } {
  if (total <= cap) return { shown: total, hidden: 0, showMoreLink: false };
  const hidden = total - cap;
  if (!earnsMoreLink(hidden)) {
    // Absorb the single leftover rather than announce it.
    return { shown: total, hidden: 0, showMoreLink: false };
  }
  return { shown: cap, hidden, showMoreLink: true };
}
