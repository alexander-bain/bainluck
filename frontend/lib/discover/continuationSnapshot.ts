/**
 * #5105 (thin supply) — the position evidence a section deck needs to survive
 * the Back-restore snapshot (`lib/discover/feedRestore`).
 *
 * The snapshot stores the cards the reader was holding as JSON. A section deck
 * (`lib/discover/continuationSections`) is more than those cards: it is the
 * edition, the GLOBAL boundary, the total and each received card's server
 * position, held in Maps that JSON drops. Without them a restored deck can only
 * be re-derived from array indexes — and the cards are filtered, deduped and
 * capped, so an index is not a server position. That is the guess this module
 * exists to refuse.
 *
 * 🔴 ONE ENTRY PER RETAINED CARD, ALIGNED BY INDEX. `cards[i]` is
 * `[id, position]` for the i-th stored card (page one, then the tail). The id
 * is checked against the card under the caller's `getId`, so metadata cannot
 * drift onto a different card; holes in the positions stay holes. No card
 * payload is duplicated here, and only retained cards carry evidence — the
 * boundary and total stay global, so capping the tail renumbers nothing.
 *
 * 🔴 THE RESTORED DECK IS REBUILT BY THE ADAPTER, NOT BY HAND. Each card is
 * folded through `foldContinuationPage` as a one-card page at its stored
 * position, so a restored deck obeys exactly the rules a received one does:
 * boundary bound, one identity per position, positions inside `total`,
 * server-position order within each section. Membership is not stored; it is
 * the adapter's `position >= boundary`. A card repeated in the stored arrays
 * is fine only at the same position (the adapter's idempotent retry); an id at
 * two positions or two ids at one position is refused.
 *
 * Every refusal is `null` — the caller's cold-load path. This module chooses no
 * expiry, replacement or reconciliation policy; it only carries a deck the
 * caller already accepted.
 */
import { foldContinuationPage, type ContinuationSections } from "./continuationSections";

/** The section deck as stored inside a snapshot. */
export interface StoredContinuationDeck {
  boundary: number;
  edition: string;
  total: number;
  /** `[id, global server position]`, aligned with the stored cards. */
  cards: Array<[string, number]>;
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/**
 * Rebuild a section deck from stored evidence and the stored cards, or `null`
 * when the evidence is malformed, contradictory or does not bind to exactly
 * these cards.
 */
export function decodeContinuationDeck<T>(
  raw: unknown,
  retained: readonly T[],
  getId: (item: T) => string,
): ContinuationSections<T> | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const stored = raw as Partial<StoredContinuationDeck>;
  // A section deck has a real boundary (0 included) and an edition to bind it.
  if (!isNonNegativeInteger(stored.boundary) || !isNonNegativeInteger(stored.total)) return null;
  if (typeof stored.edition !== "string" || stored.edition.length === 0) return null;
  if (!Array.isArray(stored.cards) || stored.cards.length !== retained.length) return null;

  let deck: ContinuationSections<T> | null = null;
  for (let index = 0; index < retained.length; index += 1) {
    const entry: unknown = stored.cards[index];
    if (!Array.isArray(entry) || entry.length !== 2) return null;
    const [id, position] = entry;
    if (typeof id !== "string" || !isNonNegativeInteger(position)) return null;
    const item = retained[index];
    // Stored cards are untrusted JSON; a getId that throws on a malformed card
    // is a refusal like any other, not an exception out of a parse.
    let itemId: string;
    try {
      itemId = getId(item);
    } catch {
      return null;
    }
    if (itemId !== id) return null;
    const result = foldContinuationPage(
      deck,
      {
        items: [item],
        offset: position,
        total: stored.total,
        edition: stored.edition,
        continuation_start: stored.boundary,
      },
      getId,
    );
    if (result.status !== "ok") return null;
    deck = result.sections;
  }
  return deck;
}

/**
 * Encode the evidence for `retained` from an accepted section deck, or `null`
 * when the deck is not a section deck, or any retained card has no recorded
 * position (or a membership that disagrees with it). The encoding is decoded
 * once before it is returned, so nothing is written that the reader would
 * refuse.
 */
export function encodeContinuationDeck<T>(
  deck: ContinuationSections<unknown>,
  retained: readonly T[],
  getId: (item: T) => string,
): StoredContinuationDeck | null {
  const { boundary, edition, total } = deck;
  if (boundary === null || edition === null) return null;
  const cards: Array<[string, number]> = [];
  for (const item of retained) {
    const id = getId(item);
    const position = deck.positions.get(id);
    if (position === undefined) return null;
    const section = position >= boundary ? "continuation" : "opening";
    if (deck.membership.get(id) !== section) return null;
    cards.push([id, position]);
  }
  const stored: StoredContinuationDeck = { boundary, edition, total, cards };
  return decodeContinuationDeck(stored, retained, getId) ? stored : null;
}
