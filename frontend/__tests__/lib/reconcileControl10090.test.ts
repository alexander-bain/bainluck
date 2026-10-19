/**
 * #10090 G1 — the `reconcile` control's pure parts: the envelope, the bounded
 * ledger of owed floors, and the in-flight write journal that lets a covering
 * read be adopted after newer writes overtook it. Real ordered adopters
 * (`applyLiveFrame`, `adoptFoldedQuote`, `adoptNewerBlendEdge`,
 * `keepNewerHeldHeadline`) — nothing is a hand copy of their rules.
 */
import {
  RECONCILE_JOURNAL_CAP,
  RECONCILE_MAX_FULFILLED,
  RECONCILE_MAX_OWED,
  RECONCILE_MAX_ROWS,
  createReconcileLedger,
  createWriteJournal,
  parseReconcileControl,
  rebaseOnCoveringRead,
  reconcileFloorCoverage,
  servedHistoryIsNewer,
  type ReconcileControl,
} from "@/lib/reconcileControl";
import { applyLiveFrame, adoptFoldedQuote } from "@/lib/eventLivePush";
import { adoptNewerBlendEdge } from "@/lib/blendObservationClock";
import { keepNewerHeldHeadline } from "@/lib/reconcileEventPoll";
import { coversQuoteRevision } from "@/lib/eventQuoteStream";

const E = 15332323;
const wire = (body: Record<string, unknown>) => JSON.stringify(body);
const control = (custodyId: string, floor: Record<string, number>): ReconcileControl => ({ eventId: E, custodyId, floor });

describe("#10090 reconcile envelope", () => {
  it("accepts the agreed shape and copies the floor", () => {
    const parsed = parseReconcileControl(wire({ event_id: E, custody_id: "c-1", removal_rev: { 15332402: 1129 } }));
    expect(parsed).toEqual({ eventId: E, custodyId: "c-1", floor: { 15332402: 1129 } });
  });
  it("takes a numeric custody id as its decimal string", () => {
    expect(parseReconcileControl(wire({ event_id: E, custody_id: 77, removal_rev: { [E]: 3 } }))?.custodyId).toBe("77");
  });
  it.each([
    ["not a string", 42],
    ["not JSON", "{"],
    ["an array", "[]"],
    ["too long", wire({ event_id: E, custody_id: "x".repeat(5000), removal_rev: { [E]: 1 } })],
    ["no event id", wire({ custody_id: "c", removal_rev: { [E]: 1 } })],
    ["a fractional event id", wire({ event_id: 1.5, custody_id: "c", removal_rev: { [E]: 1 } })],
    ["an empty custody id", wire({ event_id: E, custody_id: "", removal_rev: { [E]: 1 } })],
    ["an oversized custody id", wire({ event_id: E, custody_id: "x".repeat(129), removal_rev: { [E]: 1 } })],
    ["no floor", wire({ event_id: E, custody_id: "c" })],
    ["an empty floor", wire({ event_id: E, custody_id: "c", removal_rev: {} })],
    ["a negative floor", wire({ event_id: E, custody_id: "c", removal_rev: { [E]: -1 } })],
    ["an unsafe floor", wire({ event_id: E, custody_id: "c", removal_rev: { [E]: 2 ** 60 } })],
    ["a non-row key", wire({ event_id: E, custody_id: "c", removal_rev: { polymarket: 3 } })],
    ["too many rows", wire({ event_id: E, custody_id: "c",
      removal_rev: Object.fromEntries(Array.from({ length: RECONCILE_MAX_ROWS + 1 }, (_, i) => [String(i + 1), 1])) })],
  ])("refuses %s", (_label, data) => {
    expect(parseReconcileControl(data)).toBeNull();
  });
  it.each(["p", "source", "source_value", "status", "updated_at", "rev", "folded_quote", "folded_quote_pending"])(
    "refuses an envelope carrying the price field %s", (field) => {
      expect(parseReconcileControl(wire({ event_id: E, custody_id: "c", removal_rev: { [E]: 1 }, [field]: 0.5 }))).toBeNull();
    });
});

describe("#10090 reconcile ledger", () => {
  it("owes until a read covers every row of the floor; a missing row never covers", () => {
    const ledger = createReconcileLedger();
    expect(ledger.owe(control("a", { 1: 5, 2: 7 }), 100)).toBe(true);
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 9 }, floor))).toBe(0);
    expect(ledger.owed()).toBe(true);
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 5, 2: 6 }, floor))).toBe(0);
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 5, 2: 7 }, floor))).toBe(1);
    expect(ledger.owed()).toBe(false);
  });
  it("a repeat of an owed custody merges row-wise and keeps the earliest receipt time", () => {
    const ledger = createReconcileLedger();
    ledger.owe(control("a", { 1: 5 }), 100);
    expect(ledger.owe(control("a", { 1: 4 }), 200)).toBe(false);
    expect(ledger.owe(control("a", { 1: 6, 2: 1 }), 300)).toBe(true);
    expect(ledger.floors()).toEqual([{ 1: 6, 2: 1 }]);
    expect(ledger.earliestOwedAt()).toBe(100);
  });
  it("a paid custody sent again is not owed again; a higher floor under the same id is", () => {
    const ledger = createReconcileLedger();
    ledger.owe(control("a", { 1: 5 }), 0);
    ledger.settle(() => true);
    expect(ledger.owe(control("a", { 1: 5 }), 1)).toBe(false);
    expect(ledger.owed()).toBe(false);
    expect(ledger.owe(control("a", { 1: 6 }), 2)).toBe(true);
  });
  it("only the entries a read covers are paid; the rest stay owed", () => {
    const ledger = createReconcileLedger();
    ledger.owe(control("a", { 1: 5 }), 10);
    ledger.owe(control("b", { 1: 8 }), 20);
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 6 }, floor))).toBe(1);
    expect(ledger.floors()).toEqual([{ 1: 8 }]);
    expect(ledger.earliestOwedAt()).toBe(20);
  });
  it("past the owed cap the oldest folds into one merged floor: its id is lost, never its coverage", () => {
    const ledger = createReconcileLedger();
    for (let i = 0; i < RECONCILE_MAX_OWED + 10; i += 1) ledger.owe(control(`c${i}`, { 1: i, 2: 100 - i }), 1000 + i);
    expect(ledger.floors().length).toBeLessThanOrEqual(RECONCILE_MAX_OWED + 1);
    expect(ledger.earliestOwedAt()).toBe(1000);
    // A read that covers every remaining id but not the spilled rows pays nothing for them.
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 999, 2: 90 }, floor))).toBeGreaterThan(0);
    expect(ledger.owed()).toBe(true);
    expect(ledger.settle((floor) => coversQuoteRevision({ 1: 999, 2: 999 }, floor))).toBeGreaterThan(0);
    expect(ledger.owed()).toBe(false);
  });
  it("remembers at most the fulfilled cap: an evicted id costs one defensive re-read, nothing more", () => {
    const ledger = createReconcileLedger();
    for (let i = 0; i <= RECONCILE_MAX_FULFILLED; i += 1) {
      ledger.owe(control(`c${i}`, { 1: 1 }), i);
      ledger.settle(() => true);
    }
    expect(ledger.owe(control(`c${RECONCILE_MAX_FULFILLED}`, { 1: 1 }), 0)).toBe(false);
    expect(ledger.owe(control("c0", { 1: 1 }), 0)).toBe(true);
  });
  it("clear retires everything owed", () => {
    const ledger = createReconcileLedger();
    ledger.owe(control("a", { 1: 1 }), 0);
    ledger.clear();
    expect(ledger.owed()).toBe(false);
    expect(ledger.earliestOwedAt()).toBeNull();
  });
});

// ── the rebase ──────────────────────────────────────────────────────────────
type Rail = Record<string, { value: number; updated_at: string; display_name: string; type: string; color: string }>;
type Held = {
  id: number; status: string; sport?: string; completed_at?: string | null;
  hero_probability: number; hero_probability_away?: number | null; hero_probability_source: string;
  hero_probability_observed_at?: string | null; blend_fold_revision?: Record<string, number>;
  win_probability_sources: Rail;
};
const src = (value: number, at: string) => ({ value, updated_at: at, display_name: "x", type: "market", color: "#000" });
const T = (s: number) => new Date(Date.UTC(2026, 9, 19, 1, 0, s)).toISOString();
const held = (rev: number, p: number, rail: Rail): Held => ({
  id: E, status: "live", sport: "nfl", hero_probability: p, hero_probability_away: 1 - p,
  hero_probability_source: "blend", hero_probability_observed_at: T(rev), blend_fold_revision: { [E]: rev },
  win_probability_sources: rail,
});
const frame = (rev: number, p: number, source = "kalshi") => ({
  event_id: E, p, source, source_value: p, updated_at: T(rev), status: "live", rev: { [E]: rev },
});

describe("#10090 the covering read with in-flight writes replayed", () => {
  // Removal of polymarket committed at rev 11; frames 12 and 13 land while the read is out.
  const before = held(10, 0.55, { kalshi: src(0.56, T(10)), polymarket: src(0.5, T(9)) });
  const detail = held(12, 0.6, { kalshi: src(0.6, T(12)) });

  it("keeps the newest headline and drops the removed source — the state as if the read had landed first", () => {
    const journal = createWriteJournal<Held>();
    const f12 = frame(12, 0.6), f13 = frame(13, 0.62);
    // What the page holds after the two frames: the removed source still on its rail.
    const page = applyLiveFrame(applyLiveFrame(before, f12), f13)!;
    journal.record((e) => applyLiveFrame(e, f12));
    journal.record((e) => applyLiveFrame(e, f13));
    expect(page.win_probability_sources.polymarket).toBeDefined();
    expect(keepNewerHeldHeadline(detail, page)).not.toBe(detail); // the old rule refuses it

    const rebased = rebaseOnCoveringRead(detail, journal, page)!;
    expect(rebased.hero_probability).toBe(0.62);
    expect(rebased.blend_fold_revision).toEqual({ [E]: 13 });
    expect(rebased.hero_probability_observed_at).toBe(T(13));
    expect(Object.keys(rebased.win_probability_sources)).toEqual(["kalshi"]);
    expect(rebased.win_probability_sources.kalshi.value).toBe(0.62);
  });

  it("a source re-added after the read's snapshot survives", () => {
    const journal = createWriteJournal<Held>();
    journal.record((e) => applyLiveFrame(e, frame(13, 0.58, "polymarket")));
    const rebased = rebaseOnCoveringRead(detail, journal, held(13, 0.58, {} as Rail))!;
    expect(rebased.win_probability_sources.polymarket.value).toBe(0.58);
    expect(rebased.hero_probability).toBe(0.58);
  });

  it("a write the read already contains is refused by its own revision rule", () => {
    const journal = createWriteJournal<Held>();
    journal.record((e) => applyLiveFrame(e, frame(11, 0.4)));
    journal.record((e) => applyLiveFrame(e, frame(12, 0.41)));
    expect(rebaseOnCoveringRead(detail, journal, before)).toBe(detail);
  });

  it("refuses when the result is older than what the page holds (the read missed something)", () => {
    const journal = createWriteJournal<Held>();
    expect(rebaseOnCoveringRead(detail, journal, held(14, 0.7, {} as Rail))).toBeNull();
  });

  it("a spoiled journal rebases nothing", () => {
    const journal = createWriteJournal<Held>(2);
    for (let i = 0; i < 3; i += 1) journal.record((e) => e);
    expect(journal.overflowed).toBe(true);
    expect(journal.entries).toHaveLength(0);
    expect(rebaseOnCoveringRead(detail, journal, before)).toBeNull();
    expect(RECONCILE_JOURNAL_CAP).toBeGreaterThan(0);
  });

  it("a terminal read is returned whole — the final owner is never refused", () => {
    const journal = createWriteJournal<Held>();
    journal.record((e) => applyLiveFrame(e, frame(13, 0.62)));
    const final = { ...held(12, 1, {} as Rail), status: "completed", hero_probability_source: "settled" };
    expect(rebaseOnCoveringRead(final, journal, held(13, 0.62, {} as Rail))).toBe(final);
  });

  it("replays a folded quote, a history edge and a poll by their own rules", () => {
    const rows = { [E]: 12, 15332402: 1130 };
    const folded = { ...detail, blend_fold_revision: rows };
    const quote = {
      event_id: E, hero_probability: 0.66, hero_probability_away: 0.34, hero_probability_source: "blend",
      hero_probability_observed_at: T(20), blend_fold_revision: { [E]: 13, 15332402: 1130 },
      win_probability_sources: { kalshi: src(0.66, T(20)) }, hero_sportsbook_count: 0,
      status: "live", sport: "nfl", hero_settled_result: null,
    };
    const edge = { p: 0.7, observedAt: T(30), foldRevision: { [E]: 14, 15332402: 1130 } };
    const olderPoll = { ...folded, hero_probability: 0.1, blend_fold_revision: { [E]: 11, 15332402: 1129 } };
    const journal = createWriteJournal<Held>();
    journal.record((e) => adoptFoldedQuote(e, { event_id: E, status: "live", folded_quote: quote }, E).next);
    journal.record((e) => adoptNewerBlendEdge(e, edge));
    journal.record((e) => keepNewerHeldHeadline(olderPoll, e));
    const rebased = rebaseOnCoveringRead(folded, journal, undefined)!;
    expect(rebased.hero_probability).toBe(0.7);
    expect(rebased.blend_fold_revision).toEqual({ [E]: 14, 15332402: 1130 });
    expect(Object.keys(rebased.win_probability_sources)).toEqual(["kalshi"]);
  });
});

describe("#10090 a covering read keeps a newer served chart", () => {
  const read = { blend_edge_pinned: true, blend_edge_fold_revision: { [E]: 12 } };
  it("is true only when the served edge is strictly newer on the same rows", () => {
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 13 } }, read)).toBe(true);
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 12 } }, read)).toBe(false);
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 11 } }, read)).toBe(false);
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 13, 9: 1 } }, read)).toBe(false);
  });
  it("makes no claim without both revisions or without a pinned edge on the read", () => {
    expect(servedHistoryIsNewer(null, read)).toBe(false);
    expect(servedHistoryIsNewer({}, read)).toBe(false);
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 13 } }, { ...read, blend_edge_pinned: false })).toBe(false);
  });
});

describe("#10090 D4 what a paired read proves about an owed floor", () => {
  const TWIN = 15332402;
  const floor = { [TWIN]: 6 };
  const detail = (rev: Record<string, number> | null, status = "live") =>
    ({ id: E, status, blend_fold_revision: rev });
  const pinned = (rev: Record<string, number> | null) =>
    ({ event_id: E, blend_edge_pinned: true, blend_edge_fold_revision: rev });
  const unpinned = { event_id: E, blend_edge_pinned: false, blend_edge_fold_revision: null };
  const covering = { [E]: 12, [TWIN]: 6 };

  it("a covering detail with an unpinned (or unstated) history pays only the detail half", () => {
    expect(reconcileFloorCoverage(detail(covering), unpinned, E, floor)).toBe("detail");
    expect(reconcileFloorCoverage(detail(covering), { event_id: E }, E, floor)).toBe("detail");
    expect(reconcileFloorCoverage(detail(covering), { event_id: E, blend_edge_pinned: null }, E, floor)).toBe("detail");
    // An unpinned history's revision is not a claim, even when one is sent.
    expect(reconcileFloorCoverage(detail(covering),
      { event_id: E, blend_edge_pinned: false, blend_edge_fold_revision: covering }, E, floor)).toBe("detail");
  });
  it("pays only when a pinned history edge covers every floor row too", () => {
    expect(reconcileFloorCoverage(detail(covering), pinned(covering), E, floor)).toBe("paid");
    expect(reconcileFloorCoverage(detail(covering), pinned({ [E]: 12, [TWIN]: 7 }), E, floor)).toBe("paid");
  });
  it("a pinned history below the floor, missing the row, or with no revision proves nothing", () => {
    expect(reconcileFloorCoverage(detail(covering), pinned({ [E]: 12, [TWIN]: 5 }), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned({ [E]: 12 }), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned(null), E, floor)).toBe("none");
  });
  it("a detail below the floor never covers, whatever the history says", () => {
    expect(reconcileFloorCoverage(detail({ [E]: 12, [TWIN]: 5 }), pinned(covering), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail({ [E]: 12 }), unpinned, E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(null), pinned(covering), E, floor)).toBe("none");
  });
  it("another event's halves, or an unparseable floor, never cover", () => {
    expect(reconcileFloorCoverage({ ...detail(covering), id: E + 1 }, pinned(covering), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), { ...pinned(covering), event_id: E + 1 }, E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned(covering), E, null)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned(covering), E, {})).toBe("none");
  });
  it("a terminal detail is the final owner and retires the floor", () => {
    expect(reconcileFloorCoverage(detail(null, "completed"), unpinned, E, floor)).toBe("paid");
  });
});

describe("#10090 an unpinned history's complete-build coverage (history_fold_revision)", () => {
  const TWIN = 15332402;
  const floor = { [E]: 11, [TWIN]: 6 };
  const detail = (rev: Record<string, number> | null, status = "live") =>
    ({ id: E, status, blend_fold_revision: rev });
  const covering = { [E]: 12, [TWIN]: 6 };
  const unpinned = (vector: unknown, over: Record<string, unknown> = {}) =>
    ({ event_id: E, blend_edge_pinned: false, blend_edge_fold_revision: null, history_fold_revision: vector, ...over });

  it("pays when it covers every floor row, as the pinned edge would; extra rows and higher revisions are fine", () => {
    expect(reconcileFloorCoverage(detail(covering), unpinned(covering), E, floor)).toBe("paid");
    expect(reconcileFloorCoverage(detail(covering), unpinned({ [E]: 40, [TWIN]: 9, 77: 1 }), E, floor)).toBe("paid");
    // Unstated pin, same as false.
    const { blend_edge_pinned: _drop, ...noPin } = unpinned(covering);
    expect(reconcileFloorCoverage(detail(covering), noPin, E, floor)).toBe("paid");
    expect(reconcileFloorCoverage(detail(covering), unpinned(covering, { blend_edge_pinned: null }), E, floor)).toBe("paid");
  });
  it("never pays for a detail below the floor or from another event", () => {
    expect(reconcileFloorCoverage(detail({ [E]: 12, [TWIN]: 5 }), unpinned(covering), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(null), unpinned(covering), E, floor)).toBe("none");
    expect(reconcileFloorCoverage({ ...detail(covering), id: E + 1 }, unpinned(covering), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), unpinned(covering, { event_id: E + 1 }), E, floor)).toBe("none");
  });
  it("absent, null, malformed, partial, below-floor or missing-row coverage leaves only the detail half", () => {
    for (const vector of [
      undefined, null, "12", 12, [], [12], {}, { [E]: "12", [TWIN]: 6 }, { [E]: 12.5, [TWIN]: 6 },
      { [E]: -1, [TWIN]: 6 }, { [E]: 2 ** 53, [TWIN]: 6 }, { [E]: 12, [TWIN]: null },
      { [E]: 12 },                 // the twin row is missing: not covered
      { [E]: 12, [TWIN]: 5 },      // below on one row
      { [E]: 10, [TWIN]: 9 },      // below on the other
    ]) {
      expect(reconcileFloorCoverage(detail(covering), unpinned(vector), E, floor)).toBe("detail");
    }
  });
  it("a pinned edge keeps its own rule: the vector never vouches past an edge below the floor or without a revision", () => {
    const pinned = (edge: unknown) => unpinned(covering, { blend_edge_pinned: true, blend_edge_fold_revision: edge });
    expect(reconcileFloorCoverage(detail(covering), pinned({ [E]: 12, [TWIN]: 5 }), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned(null), E, floor)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), pinned(covering), E, floor)).toBe("paid");
    // and the pinned edge alone still pays without any vector
    expect(reconcileFloorCoverage(detail(covering),
      { event_id: E, blend_edge_pinned: true, blend_edge_fold_revision: covering }, E, floor)).toBe("paid");
  });
  it("an unparseable floor is never covered by any vector, and a terminal detail still retires it", () => {
    expect(reconcileFloorCoverage(detail(covering), unpinned(covering), E, null)).toBe("none");
    expect(reconcileFloorCoverage(detail(covering), unpinned(covering), E, {})).toBe("none");
    expect(reconcileFloorCoverage(detail(null, "completed"), unpinned(null), E, floor)).toBe("paid");
  });
  it("is not a pinned edge: a covering read with only a coverage vector never displaces a newer served chart edge", () => {
    expect(servedHistoryIsNewer({ foldRevision: { [E]: 13 } }, unpinned({ [E]: 99, [TWIN]: 99 }))).toBe(false);
  });
});
