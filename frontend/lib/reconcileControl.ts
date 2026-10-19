import { coversQuoteRevision, isQuoteStreamStatus } from "./eventQuoteStream";
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from "./foldRevision";
import { carryNewerHeldState } from "./reconcileEventPoll";

/**
 * #10090 — the `reconcile` control: "a source left this event's fold; read the
 * current state". It is NOT a price. It names an obligation (`custody_id`) and
 * a row-wise coverage FLOOR (`removal_rev`, the same `{ "<row id>": rev }` space
 * as `blend_fold_revision`): a paired read pays the obligation only when the
 * value it WRITES is at or beyond the floor on every row, and so is the
 * history's own proof — a pinned edge's revision, or for an unpinned history
 * the complete fresh build's `history_fold_revision` (`reconcileFloorCoverage`).
 * A missing row never covers, and an unpinned history with no such vector
 * proves nothing, so it never pays.
 *
 *   event: reconcile
 *   data: {"event_id":15332323,"custody_id":"…","removal_rev":{"15332402":1129}}
 *
 * The floor is never adopted as a quote revision, and receiving one advances no
 * price clock, replay cursor, accepted-price receipt or delivering state.
 * (Decision: artifacts/live-iteration-goal-20261011/reconciliation-contract-20261019/ROOT-PAIRED-DECISION.md)
 */
export type ReconcileControl = { eventId: number; custodyId: string; floor: FoldRevision };

/** Bounds on one envelope, and on what a long-open page may remember. */
export const RECONCILE_MAX_DATA_CHARS = 4096;
export const RECONCILE_MAX_ROWS = 32;
export const RECONCILE_MAX_CUSTODY_CHARS = 128;
export const RECONCILE_MAX_OWED = 32;
export const RECONCILE_MAX_FULFILLED = 64;
export const RECONCILE_JOURNAL_CAP = 256;

// A price-shaped field on a control means the envelope is not the one agreed;
// refusing it keeps a control from ever being read as a quote.
const PRICE_FIELDS = ["p", "source", "source_value", "status", "updated_at", "rev", "folded_quote", "folded_quote_pending"];

/** The control from the raw SSE `data`, or `null` for anything outside the envelope. */
export function parseReconcileControl(data: unknown): ReconcileControl | null {
  if (typeof data !== "string" || data.length > RECONCILE_MAX_DATA_CHARS) return null;
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
  const body = value as Record<string, unknown>;
  if (PRICE_FIELDS.some((field) => field in body)) return null;
  const eventId = body.event_id;
  if (typeof eventId !== "number" || !Number.isSafeInteger(eventId) || eventId <= 0) return null;
  const custody = body.custody_id;
  const custodyId = typeof custody === "number" && Number.isSafeInteger(custody) ? String(custody) : custody;
  if (typeof custodyId !== "string" || custodyId.length === 0 || custodyId.length > RECONCILE_MAX_CUSTODY_CHARS) return null;
  const floor = parseFoldRevision(body.removal_rev);
  if (!floor) return null;
  const rows = Object.keys(floor);
  if (rows.length > RECONCILE_MAX_ROWS || rows.some((row) => !/^[1-9]\d{0,15}$/.test(row))) return null;
  return { eventId, custodyId, floor: { ...floor } };
}

function mergeFloor(a: FoldRevision, b: FoldRevision): FoldRevision {
  const merged: FoldRevision = { ...a };
  for (const [row, rev] of Object.entries(b)) merged[row] = Math.max(merged[row] ?? rev, rev);
  return merged;
}

const SPILL = "\u0000spill";

/**
 * What one page still owes. Bounded both ways: at most `RECONCILE_MAX_OWED`
 * unpaid entries (past that, the oldest folds into one merged floor, so its
 * coverage is never lost — only its id), and at most `RECONCILE_MAX_FULFILLED`
 * remembered paid ids (an evicted one costs at most one defensive re-read when
 * the server sends it again). The earliest unpaid receipt time is kept for
 * accounting and survives merges.
 */
export interface ReconcileLedger {
  /** Registers a control; false when an already-paid floor covers it. */
  owe(control: ReconcileControl, at: number): boolean;
  owed(): boolean;
  floors(): FoldRevision[];
  /** Pays every entry `covers` accepts; returns how many were paid. */
  settle(covers: (floor: FoldRevision) => boolean): number;
  earliestOwedAt(): number | null;
  /** Retirement with a named owner (the page says which). */
  clear(): void;
}

export function createReconcileLedger(): ReconcileLedger {
  const owed = new Map<string, { floor: FoldRevision; at: number }>();
  const fulfilled = new Map<string, FoldRevision>();
  return {
    owe(control, at) {
      const paid = fulfilled.get(control.custodyId);
      if (paid && coversQuoteRevision(paid, control.floor)) return false;
      const held = owed.get(control.custodyId);
      if (held) {
        const floor = mergeFloor(held.floor, control.floor);
        const raised = Object.keys(floor).some((row) => floor[row] !== held.floor[row]);
        owed.set(control.custodyId, { floor, at: held.at });
        return raised;
      }
      if (owed.size >= RECONCILE_MAX_OWED) {
        const oldest = [...owed.keys()].find((key) => key !== SPILL);
        if (oldest !== undefined) {
          const out = owed.get(oldest)!;
          const spill = owed.get(SPILL);
          owed.delete(oldest);
          owed.set(SPILL, spill
            ? { floor: mergeFloor(spill.floor, out.floor), at: Math.min(spill.at, out.at) }
            : out);
        }
      }
      owed.set(control.custodyId, { floor: { ...control.floor }, at });
      return true;
    },
    owed: () => owed.size > 0,
    floors: () => [...owed.values()].map((entry) => entry.floor),
    settle(covers) {
      let paid = 0;
      for (const [key, entry] of [...owed]) {
        if (!covers(entry.floor)) continue;
        owed.delete(key);
        paid += 1;
        if (key === SPILL) continue;
        fulfilled.delete(key);
        fulfilled.set(key, entry.floor);
        if (fulfilled.size > RECONCILE_MAX_FULFILLED) fulfilled.delete(fulfilled.keys().next().value!);
      }
      return paid;
    },
    earliestOwedAt() {
      let earliest: number | null = null;
      for (const entry of owed.values()) earliest = earliest === null ? entry.at : Math.min(earliest, entry.at);
      return earliest;
    },
    clear() {
      owed.clear();
    },
  };
}

/**
 * Every write the page made to its event cache while one paired read was in
 * flight, as the function that made it. The read's own fresh detail already
 * contains everything committed before the read began, so replaying these, in
 * arrival order, onto that detail is the page's state as if the detail had
 * landed first. Each replay is the original ordered adopter (`applyLiveFrame`,
 * `adoptFoldedQuote`, `adoptNewerBlendEdge`; the poll's is `replayJournaledPoll`),
 * so a write the detail already contains is refused by its own revision rule.
 * Bounded: past the cap the journal is spoiled and cannot rebase anything.
 */
export interface WriteJournal<T> {
  record(replay: (event: T) => T | undefined): void;
  readonly entries: ReadonlyArray<(event: T) => T | undefined>;
  readonly overflowed: boolean;
}

export function createWriteJournal<T>(cap = RECONCILE_JOURNAL_CAP): WriteJournal<T> {
  const entries: Array<(event: T) => T | undefined> = [];
  let overflowed = false;
  return {
    record(replay) {
      if (overflowed) return;
      if (entries.length >= cap) {
        overflowed = true;
        entries.length = 0;
        return;
      }
      entries.push(replay);
    },
    get entries() { return entries; },
    get overflowed() { return overflowed; },
  };
}

/**
 * #10090 D4 — what one paired read proves about one owed floor.
 *
 *   "paid"   — the detail covers the floor and so does the history: a PINNED
 *              edge's own fold revision, or, when nothing is pinned, the
 *              `history_fold_revision` of a complete fresh build (or the
 *              detail is terminal: the final owner).
 *   "detail" — the detail covers the floor, but the history proves nothing
 *              about it: unpinned, and its coverage vector is absent, null,
 *              malformed, below the floor or missing a floor row (a partial,
 *              cached or failed build serves none). The rail may be rebased
 *              onto the detail; the chart half is unproven, so the floor stays
 *              owed and the page's persistent read asks again.
 *   "none"   — the detail is below the floor, or a pinned history edge is
 *              below it or carries no revision to order. A pinned edge is a
 *              claim about NOW, so a coverage vector never vouches past it.
 *
 * `history_fold_revision` (#10090, ROOT-HISTORY-CONSUMER-ADMISSION) says only
 * that every series the build drew was read after each listed row reached its
 * revision. It is read ordering, not a price, clock, chart point or pin: it is
 * never adopted, it moves no headline, freshness or edge, and a row absent
 * from it is not covered.
 *
 * `quotePairCoversTrigger` lets an unpinned history cover trivially, which is
 * right for a price trigger and wrong for a removal: nothing here (no forced
 * pin, read-start clock or existing price snapshot) stands in for the
 * history's own revision.
 */
export type FloorCoverage = "paid" | "detail" | "none";

export function reconcileFloorCoverage(
  detail: { id: number; status?: string | null; blend_fold_revision?: unknown },
  history: {
    event_id: number; blend_edge_pinned?: boolean | null; blend_edge_fold_revision?: unknown;
    history_fold_revision?: unknown;
  },
  eventId: number, floor: unknown,
): FloorCoverage {
  if (detail.id !== eventId || history.event_id !== eventId || !parseFoldRevision(floor)) return "none";
  if (!isQuoteStreamStatus(detail.status)) return "paid";
  if (!coversQuoteRevision(detail.blend_fold_revision, floor)) return "none";
  if (history.blend_edge_pinned === true) {
    return coversQuoteRevision(history.blend_edge_fold_revision, floor) ? "paid" : "none";
  }
  // The floor parsed above, so this is never the trivial "no trigger" true.
  return coversQuoteRevision(history.history_fold_revision, floor) ? "paid" : "detail";
}

type Versioned = { id: number; status?: string | null; blend_fold_revision?: unknown };

/**
 * #10090 — the poll a pair journaled, replayed onto the value it lands on: the
 * poll whole when it is a result (the final owner) or its fold revision is
 * strictly NEWER than that value's, otherwise nothing. The live poll's own
 * adopter (`keepNewerHeldHeadline`) is not a replay rule: for an older poll it
 * keeps only the headline and takes score, status and clock from the poll, and
 * for an incomparable one it returns the poll whole — so replayed after a
 * fresher read it put the game back a step, or the removed source back on the
 * rail. A same, older, incomparable or unversioned poll is not replayed: the
 * pair overwrites the cache with its own adopted value, so a same-revision
 * poll's game state (status, score) yields to the pair's detail.
 * A replayed poll is newer in PRICE, not necessarily in game state: when the
 * value it lands on read the row provably later, that state is carried onto
 * it (`carryNewerHeldState`), exactly as a poll landing on the page would be.
 */
export function replayJournaledPoll<T extends Versioned>(polled: T, onto: T): T | undefined {
  if (!isQuoteStreamStatus(polled.status)) return carryNewerHeldState(polled, onto);
  const polledRevision = parseFoldRevision(polled.blend_fold_revision);
  const ontoRevision = parseFoldRevision(onto.blend_fold_revision);
  return polledRevision && ontoRevision && compareFoldRevision(polledRevision, ontoRevision) === "newer"
    ? carryNewerHeldState(polled, onto) : undefined;
}

/**
 * The covering read with the in-flight writes replayed onto it, or `null` when
 * that cannot be trusted: a spoiled journal, or a result whose fold revision is
 * OLDER than the headline the page holds (the read missed something the page
 * had before it began — a cache or a lagging replica; the obligation stays owed).
 *
 * No value is computed here. The headline is the newest ordered write (the
 * detail's own or a replayed one), each paired with its own revision; the rail
 * is the detail's, as later frames amended it. That is why the headline may be
 * kept newer than the detail without keeping a removed source inside it: the
 * detail covers the removal floor, and every replayed write is newer still.
 * A terminal read is returned whole — it is the final owner, never refused.
 */
export function rebaseOnCoveringRead<T extends Versioned>(
  read: T, journal: WriteJournal<T>, held: T | undefined,
): T | null {
  if (!isQuoteStreamStatus(read.status)) return read;
  if (journal.overflowed) return null;
  let next = read;
  for (const replay of journal.entries) next = replay(next) ?? next;
  const heldRevision = parseFoldRevision(held?.blend_fold_revision);
  const nextRevision = parseFoldRevision(next.blend_fold_revision);
  if (heldRevision && (!nextRevision || compareFoldRevision(nextRevision, heldRevision) === "older")) return null;
  return next;
}

/**
 * True when the chart history the page already serves has a pinned edge
 * strictly NEWER than the covering read's own history — a history poll landed
 * while the read was out. Writing the read's history then would take genuine
 * observations off the chart until the next poll; the served one covers the
 * floor too (it is newer on the same rows), so the read keeps it.
 */
export function servedHistoryIsNewer(
  served: { foldRevision?: FoldRevision } | null | undefined,
  history: { blend_edge_pinned?: boolean | null; blend_edge_fold_revision?: unknown },
): boolean {
  const servedRevision = parseFoldRevision(served?.foldRevision);
  const readRevision = history.blend_edge_pinned ? parseFoldRevision(history.blend_edge_fold_revision) : null;
  return !!servedRevision && !!readRevision && compareFoldRevision(readRevision, servedRevision) === "older";
}
