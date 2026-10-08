/**
 * #5105 (thin supply) — the ordinary-live continuation, separated on the client.
 *
 * When the opening deck runs thin, the server seats an "ordinary-live
 * continuation" after it and states where it begins as `continuation_start`:
 * the GLOBAL 0-based position in the whole ranked deck (never an index into one
 * page). Every offset page of one deck carries the same value, and it is bound
 * into that deck's `edition` token. Absent / `null` means the server drew no
 * section (every legacy response); `0` is a real boundary — the whole deck is
 * continuation.
 *
 * 🔴 CLASSIFY FROM THE SERVER'S POSITION, BEFORE ANY CLIENT FILTER. A card's
 * section is `page.offset + rawIndex >= continuation_start`, decided on the
 * array the server sent. The page then drops cards (renderability, staleness,
 * dismissals, category cooldown) and dedups across pages, so neither the length
 * of a filtered array nor "the first continuation card's id" can locate the
 * boundary afterwards — that exact card may be the one that was filtered out.
 * Membership is recorded per card id and survives every filter.
 *
 * 🔴 PROCESS EACH SECTION SEPARATELY. The page's grouping, sport spacing and
 * local personalization reorder cards across windows; run over the combined
 * list they carry cards back across the boundary. A caller partitions first
 * (`partitionBySection`) and runs those passes on each section on its own.
 * This module does not wire the Discover page and claims nothing about it.
 *
 * Combining pages requires the same deck: equal boundary, and for a section
 * deck an equal non-null edition and total. Anything else is returned as
 * `unsupported` with the caller's state untouched — this module never expires,
 * clears or merges sessions. Accept/reset policy belongs to the caller.
 *
 * 🔴 ONE IDENTITY PER SERVER POSITION (section decks). Each received card's
 * position is recorded; a page that puts another card at a held position, or a
 * held card at another position, is not the same deck (`position_conflict`).
 * Sections are kept in server-position order whatever order pages arrive in,
 * and a nonempty page reaching past `total` is refused (an empty page at or
 * past the end is ordinary pagination). Legacy decks keep their existing
 * first-sight, arrival-order reconciliation.
 *
 * Identity is the caller's `getId` (the page's `getItemId`); this module builds
 * no ids of its own. Item references are kept as received.
 */

export type ContinuationSection = "opening" | "continuation";

export type ContinuationUnsupportedReason =
  | "invalid_page"
  | "invalid_boundary"
  | "boundary_mismatch"
  | "edition_missing"
  | "edition_mismatch"
  | "total_mismatch"
  | "membership_conflict"
  | "position_conflict"
  | "page_out_of_range";

/** The page fields this module reads, as received (untrusted JSON). */
export interface ContinuationPageInput<T> {
  items: readonly T[];
  offset: unknown;
  total: unknown;
  edition?: unknown;
  continuation_start?: unknown;
}

export type ContinuationBoundary =
  | { kind: "legacy" }
  | { kind: "section"; start: number }
  | { kind: "invalid" };

/** Accumulated sections for one deck. Never mutated after it is returned. */
export interface ContinuationSections<T> {
  /** `null` = legacy: the server drew no section; everything is opening. */
  readonly boundary: number | null;
  readonly edition: string | null;
  readonly total: number;
  /** Received cards in server order, original references, first sight wins. */
  readonly opening: readonly T[];
  readonly continuation: readonly T[];
  readonly membership: ReadonlyMap<string, ContinuationSection>;
  /** Section decks: card id -> global server position. Empty for legacy. */
  readonly positions: ReadonlyMap<string, number>;
}

export type ContinuationResult<T> =
  | { status: "ok"; sections: ContinuationSections<T> }
  | { status: "unsupported"; reason: ContinuationUnsupportedReason };

function isNonNegativeInteger(value: unknown): value is number {
  // `typeof` first: a boolean or a numeric string is malformed, never coerced.
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/**
 * Read `continuation_start` against the page's own `total`, with the backend's
 * bound (`0 <= start < total`). A malformed value is `invalid` — never a
 * fabricated section and never silently legacy.
 */
export function readContinuationBoundary(raw: unknown, total: unknown): ContinuationBoundary {
  if (raw === undefined || raw === null) return { kind: "legacy" };
  if (!isNonNegativeInteger(raw) || !isNonNegativeInteger(total) || raw >= total) {
    return { kind: "invalid" };
  }
  return { kind: "section", start: raw };
}

function readEdition(raw: unknown): string | null {
  return typeof raw === "string" && raw.length > 0 ? raw : null;
}

/**
 * Fold one successfully received page into `prior` (or start a deck when
 * `prior` is null). Pure: `prior` is never mutated; a refusal returns
 * `unsupported` and the caller keeps what it had.
 *
 * A card already held (a duplicate page, or a page overlapping one already
 * folded) is not added twice. A held card the new page places in the OTHER
 * section means the two pages are not one deck: `membership_conflict`. In a
 * section deck the same holds for positions: a held position under another id,
 * or a held id at another position, is `position_conflict`.
 */
export function foldContinuationPage<T>(
  prior: ContinuationSections<T> | null,
  page: ContinuationPageInput<T>,
  getId: (item: T) => string,
): ContinuationResult<T> {
  if (!page || !Array.isArray(page.items) || !isNonNegativeInteger(page.offset) || !isNonNegativeInteger(page.total)) {
    return { status: "unsupported", reason: "invalid_page" };
  }
  const boundary = readContinuationBoundary(page.continuation_start, page.total);
  if (boundary.kind === "invalid") return { status: "unsupported", reason: "invalid_boundary" };
  const start = boundary.kind === "section" ? boundary.start : null;
  const edition = readEdition(page.edition);

  if (prior) {
    if (prior.boundary !== start) return { status: "unsupported", reason: "boundary_mismatch" };
    if (start !== null) {
      // A section deck is identified by its edition; without one on both
      // sides, two pages cannot be proven to share a boundary.
      if (prior.edition === null || edition === null) return { status: "unsupported", reason: "edition_missing" };
      if (prior.edition !== edition) return { status: "unsupported", reason: "edition_mismatch" };
      if (prior.total !== page.total) return { status: "unsupported", reason: "total_mismatch" };
    }
  }
  if (start !== null && page.items.length > 0 && page.offset + page.items.length > page.total) {
    return { status: "unsupported", reason: "page_out_of_range" };
  }

  const membership = new Map<string, ContinuationSection>(prior?.membership ?? []);
  const positions = new Map<string, number>(prior?.positions ?? []);
  const idAt = new Map<number, string>();
  for (const [id, position] of positions) idAt.set(position, id);
  const opening: T[] = [...(prior?.opening ?? [])];
  const continuation: T[] = [...(prior?.continuation ?? [])];
  for (let index = 0; index < page.items.length; index += 1) {
    const item = page.items[index];
    const position = page.offset + index;
    const section: ContinuationSection = start !== null && position >= start ? "continuation" : "opening";
    const id = getId(item);
    const held = membership.get(id);
    if (held !== undefined && held !== section) return { status: "unsupported", reason: "membership_conflict" };
    if (start !== null) {
      const heldPosition = positions.get(id);
      const heldId = idAt.get(position);
      if ((heldPosition !== undefined && heldPosition !== position) || (heldId !== undefined && heldId !== id)) {
        return { status: "unsupported", reason: "position_conflict" };
      }
      positions.set(id, position);
      idAt.set(position, id);
    }
    if (held !== undefined) continue;
    membership.set(id, section);
    (section === "opening" ? opening : continuation).push(item);
  }
  if (start !== null) {
    // Pages may arrive in any order; the sections stay in server order.
    const byPosition = (a: T, b: T) => (positions.get(getId(a)) ?? 0) - (positions.get(getId(b)) ?? 0);
    opening.sort(byPosition);
    continuation.sort(byPosition);
  }

  return {
    status: "ok",
    sections: {
      boundary: start,
      edition: prior?.edition ?? edition,
      total: prior?.total ?? page.total,
      opening,
      continuation,
      membership,
      positions,
    },
  };
}

export interface SectionPartition<T> {
  opening: T[];
  continuation: T[];
  /** Cards this deck never received (e.g. a synthetic card the caller added). */
  unclassified: T[];
}

/**
 * Split a caller's FILTERED / deduped list by recorded membership, keeping the
 * caller's order within each section and the original references. Legacy decks
 * put every received card in `opening`. Run the page's grouping and ordering
 * passes on each returned section separately.
 */
export function partitionBySection<T>(
  items: readonly T[],
  sections: ContinuationSections<unknown>,
  getId: (item: T) => string,
): SectionPartition<T> {
  const partition: SectionPartition<T> = { opening: [], continuation: [], unclassified: [] };
  for (const item of items) {
    const section = sections.membership.get(getId(item));
    if (section === undefined) partition.unclassified.push(item);
    else partition[section].push(item);
  }
  return partition;
}
