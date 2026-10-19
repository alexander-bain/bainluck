/**
 * #10090 — the web reader of `source_snapshot` (PR #11264's same-commit source
 * map), against the shared contract in
 * reconciliation-contract-20261019/NATIVE-SOURCE-SNAPSHOT-CONSUMER-CONTRACT.md
 * §2 (decoder), §3 (singleton adoption), §4 (unpriced) and §5 (evidence), and
 * ROOT-COHERENT-RAIL-PAYMENT-DECISION.md. Pure functions only; the mounted page
 * cases live in `__tests__/hooks/reconcileControlMounted10090.test.tsx`.
 */
import { applyLiveFrame, applyLiveFrameRail, type LiveFrame } from "@/lib/eventLivePush";
import { heldFrameAfter } from "@/hooks/useLiveEventStream";
import { rememberLiveChartFrame } from "@/lib/liveChartHistory";
import { createLiveStreamController, type LiveStreamFrame, type StreamHandle } from "@/lib/liveStreamController";
import { keepNewerHeldHeadline, reconcileEventPoll } from "@/lib/reconcileEventPoll";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import {
  SOURCE_SNAPSHOT_MAX_FRAME_BYTES,
  frameCarriesUnpricedSnapshot,
  readSourceSnapshot,
  snapshotFrameIsOversize,
  snapshotRailPaysPricelessTrigger,
} from "@/lib/sourceSnapshot";

const E = 15332323;
const T = (s: number) => new Date(Date.UTC(2026, 9, 19, 1, 0, s)).toISOString();
const entry = (value: number, s: number, extra: Record<string, unknown> = {}) =>
  ({ value, updated_at: T(s), display_name: "x", type: "market", color: "#000", evidence_status: "verified", ...extra });
type Entry = { value: number; updated_at?: string; evidence_status?: string; price_evidence?: string };
const held = (rev: number, rail: Record<string, Entry>, extra: Record<string, unknown> = {}) => ({
  id: E, status: "live", sport: "nfl", home_score: 7,
  hero_probability: 0.55, hero_probability_away: 0.45, hero_probability_source: "blend",
  hero_probability_observed_at: T(rev), blend_fold_revision: { [E]: rev } as Record<string, number>,
  win_probability_sources: rail, ...extra,
});
const withPm = (rev: number, evidence = "tradeable_book") =>
  ({ kalshi: entry(0.56, rev), polymarket: entry(0.5, rev - 1, { price_evidence: evidence }) });
const snap = (rev: number, rail: Record<string, unknown>, over: Record<string, unknown> = {}) =>
  ({ event_id: E, rev: { [String(E)]: rev }, win_probability_sources: rail, ...over });
const frame = (rev: number, p: number | null, snapshot?: unknown, over: Partial<LiveStreamFrame> = {}): LiveStreamFrame => ({
  event_id: E, p, source: "kalshi", source_value: p, updated_at: T(rev), status: "live", rev: { [E]: rev },
  ...(snapshot === undefined ? {} : { source_snapshot: snapshot }), ...over,
});
const priced = (f: LiveStreamFrame) => ({ ...f, p: f.p as number }) as LiveFrame;

describe("§2 decoder: absent / refused / valid", () => {
  it("absent when the key is missing", () => {
    expect(readSourceSnapshot(frame(11, 0.6))).toEqual({ state: "absent" });
  });

  it("valid, priced, for the producer's shape (unknown sibling keys ignored)", () => {
    const rail = { kalshi: entry(0.6, 11), betting_book_count: { value: 7, display_name: "Books", type: "count", color: "#000" },
      polymarket: entry(0.5, 10, { price_evidence: "not_evaluated", verified_scope: "game", contract_version: "v2" }) };
    const decoded = readSourceSnapshot(frame(11, 0.6, snap(11, rail)));
    expect(decoded).toEqual({ state: "valid", revision: { [E]: 11 }, sources: rail, priced: true });
  });

  const refusals: Array<[string, unknown, Partial<LiveStreamFrame>?]> = [
    ["not an object", "x"],
    ["array", []],
    ["event id mismatch", snap(11, {}, { event_id: E + 1 })],
    ["multi-row rev", snap(11, {}, { rev: { [E]: 11, 1: 1 } })],
    ["wrong row key", snap(11, {}, { rev: { 1: 11 } })],
    ["rev differs from the frame's", snap(12, {})],
    ["rev out of range", snap(11, {}, { rev: { [E]: 2 ** 53 } })],
    ["negative rev", snap(11, {}, { rev: { [E]: -1 } })],
    ["non-integer rev", snap(11, {}, { rev: { [E]: 11.5 } })],
    ["frame has no rev", snap(11, {}), { rev: null }],
    ["frame rev multi-row", snap(11, {}), { rev: { [E]: 11, 1: 1 } }],
    ["map missing", { event_id: E, rev: { [E]: 11 } }],
    ["map is an array", snap(11, [] as unknown as Record<string, unknown>)],
    ["33 entries", snap(11, Object.fromEntries(Array.from({ length: 33 }, (_, i) => [`m${i}`, entry(0.5, 1)])))],
    ["empty key", snap(11, { "": entry(0.5, 1) })],
    ["65-byte key", snap(11, { ["k".repeat(65)]: entry(0.5, 1) })],
    ["key over 64 UTF-8 bytes in 22 chars", snap(11, { ["€".repeat(22)]: entry(0.5, 1) })],
    ["bare-number entry", snap(11, { kalshi: 0.5 })],
    ["null value", snap(11, { kalshi: entry(0.5, 1, { value: null }) })],
    ["NaN value", snap(11, { kalshi: entry(0.5, 1, { value: NaN }) })],
    ["string value", snap(11, { kalshi: entry(0.5, 1, { value: "0.5" }) })],
    ["real source above 1", snap(11, { kalshi: entry(1.2, 1) })],
    ["real source below 0", snap(11, { polymarket: entry(-0.1, 1) })],
    ["other key below 0", snap(11, { kalshi: entry(0.5, 1), betting_book_count: { value: -1 } })],
    ["unparseable updated_at", snap(11, { kalshi: entry(0.5, 1, { updated_at: "soon" }) })],
    ["non-string display_name", snap(11, { kalshi: entry(0.5, 1, { display_name: 3 }) })],
    ["on a folded quote", snap(11, {}), { folded_quote: null }],
    ["on a pending fold", snap(11, {}), { folded_quote_pending: true }],
  ];
  // Rest parameters: a three-parameter callback would receive jest's `done`.
  it.each(refusals)("refused: %s", (...[, snapshot, over]) => {
    expect(readSourceSnapshot(frame(11, 0.6, snapshot, over))).toEqual({ state: "refused" });
  });

  it("64 entries of 64-byte keys pass the key rule at the boundary; 32 entries pass the count rule", () => {
    const rail = Object.fromEntries(Array.from({ length: 32 }, (_, i) => [`${"k".repeat(62)}${String(i).padStart(2, "0")}`, entry(0.5, 1)]));
    expect(readSourceSnapshot(frame(11, 0.6, snap(11, rail))).state).toBe("valid");
  });

  it("unpriced: an empty map, only `betting_book_count`, only `final_result`, or no usable p", () => {
    for (const [rail, p] of [[{}, 0.5], [{ betting_book_count: { value: 3 } }, 0.5], [{ final_result: entry(1, 1) }, 1],
      [{ kalshi: entry(0.6, 1) }, null], [{ kalshi: entry(0.6, 1) }, 1.5]] as const) {
      const decoded = readSourceSnapshot(frame(11, p as number | null, snap(11, rail as Record<string, unknown>)));
      expect(decoded).toMatchObject({ state: "valid", priced: false });
    }
  });

  it("D3: over 16 KiB of UTF-8 the controller drops the snapshot and the frame is its legacy shape", () => {
    expect(snapshotFrameIsOversize("a".repeat(SOURCE_SNAPSHOT_MAX_FRAME_BYTES))).toBe(false);
    expect(snapshotFrameIsOversize("a".repeat(SOURCE_SNAPSHOT_MAX_FRAME_BYTES + 1))).toBe(true);
    expect(snapshotFrameIsOversize("€".repeat(5462))).toBe(true); // 16,386 bytes in 5,462 chars
    expect(snapshotFrameIsOversize("€".repeat(5461))).toBe(false);
    expect(snapshotFrameIsOversize("😀".repeat(4097))).toBe(true);

    const delivered: LiveStreamFrame[] = [];
    const listeners = new Map<string, (event: unknown) => void>();
    const stream: StreamHandle = { readyState: 1, close: () => {}, addEventListener: (n, l) => { listeners.set(n, l); } };
    createLiveStreamController({ open: () => stream, now: () => 1, onDeliveringChange: () => {}, onFrame: (f) => delivered.push(f) }).start();
    const small = frame(11, 0.6, snap(11, { kalshi: entry(0.6, 11) }));
    listeners.get("probability")!({ data: JSON.stringify(small) });
    const padded = { ...frame(12, 0.6, snap(12, { kalshi: entry(0.6, 12, { pad: "p".repeat(SOURCE_SNAPSHOT_MAX_FRAME_BYTES) }) })) };
    listeners.get("probability")!({ data: JSON.stringify(padded) });
    expect(delivered[0].source_snapshot).toEqual(small.source_snapshot);
    expect("source_snapshot" in delivered[1]).toBe(false);
    expect(delivered[1].p).toBe(0.6);
  });
});

describe("§3 adoption: only a strictly newer frame on a singleton held live blend", () => {
  it("same-commit current map: hero, revision and the WHOLE rail are the snapshot's (withdrawn venue gone)", () => {
    const rail = { kalshi: entry(0.6, 11) };
    const out = applyLiveFrameRail(held(10, withPm(10)), priced(frame(11, 0.6, snap(11, rail))));
    expect(out.snapshotRail).toBe(true);
    expect(out.next).toEqual({ ...held(10, {}), hero_probability: 0.6, hero_probability_away: 0.4,
      hero_probability_observed_at: T(11), blend_fold_revision: { [E]: 11 }, win_probability_sources: rail });
    // The cache never aliases the frame's own map.
    expect(out.next!.win_probability_sources).not.toBe(rail);
  });

  it("removal then genuine re-addition follow quote order; older REST restores and prunes nothing", () => {
    let page = applyLiveFrame(held(12, withPm(12)), priced(frame(13, 0.6, snap(13, { kalshi: entry(0.6, 13) }))))!;
    expect(Object.keys(page.win_probability_sources)).toEqual(["kalshi"]);
    // A REST response at 12 still folding Polymarket keeps the held headline WITH its rail.
    expect(Object.keys(keepNewerHeldHeadline(held(12, withPm(12)), page).win_probability_sources)).toEqual(["kalshi"]);
    page = applyLiveFrame(page, priced(frame(14, 0.58, snap(14, { kalshi: entry(0.6, 13), polymarket: entry(0.52, 14) }))))!;
    expect(Object.keys(page.win_probability_sources).sort()).toEqual(["kalshi", "polymarket"]);
    expect(Object.keys(keepNewerHeldHeadline(held(13, { kalshi: entry(0.6, 13) }), page).win_probability_sources).sort())
      .toEqual(["kalshi", "polymarket"]);
  });

  it("equal and older frames adopt nothing, and a replayed snapshot adopts nothing", () => {
    const page = held(11, withPm(11));
    for (const rev of [10, 11]) {
      expect(applyLiveFrameRail(page, priced(frame(rev, 0.7, snap(rev, { kalshi: entry(0.7, rev) }))))).toEqual({ next: page, snapshotRail: false });
    }
  });

  const legacyResult = (f: LiveStreamFrame) => applyLiveFrame(held(10, withPm(10)), priced({ ...f, source_snapshot: undefined }));
  it.each([
    ["event id mismatch", snap(11, { kalshi: entry(0.6, 11) }, { event_id: 1 })],
    ["rev differs from the frame's", snap(12, { kalshi: entry(0.6, 11) })],
    ["33 entries", snap(11, Object.fromEntries(Array.from({ length: 33 }, (_, i) => [`m${i}`, entry(0.5, 1)])))],
    ["out-of-range value", snap(11, { kalshi: entry(1.5, 11) })],
  ])("refused (%s) gives exactly the legacy result: p moves, rail merged, nothing replaced", (_name, snapshot) => {
    const f = frame(11, 0.6, snapshot);
    const out = applyLiveFrameRail(held(10, withPm(10)), priced(f));
    expect(out.snapshotRail).toBe(false);
    expect(out.next).toEqual(legacyResult(f));
    expect(Object.keys(out.next!.win_probability_sources).sort()).toEqual(["kalshi", "polymarket"]);
  });

  it("a folded (two-row) hero refuses the raw frame whole, snapshot or not", () => {
    const folded = held(10, withPm(10), { blend_fold_revision: { [E]: 10, 15332999: 4 } });
    const f = priced(frame(11, 0.6, snap(11, { kalshi: entry(0.6, 11) })));
    expect(applyLiveFrameRail(folded, f)).toEqual({ next: folded, snapshotRail: false });
  });

  it("a held blend with no revision vector is not the singleton path: clocks decide and the rail is merged", () => {
    const unversioned = held(10, withPm(10), { blend_fold_revision: undefined });
    const out = applyLiveFrameRail(unversioned, priced(frame(11, 0.6, snap(11, { kalshi: entry(0.6, 11) }))));
    expect(out.snapshotRail).toBe(false);
    expect(Object.keys(out.next!.win_probability_sources).sort()).toEqual(["kalshi", "polymarket"]);
  });

  it("a held value for another event takes the legacy merge, never the snapshot rail", () => {
    const other = held(10, withPm(10), { id: E + 1 });
    const out = applyLiveFrameRail(other, priced(frame(11, 0.6, snap(11, { kalshi: entry(0.6, 11) }))));
    expect(out.snapshotRail).toBe(false);
    expect(Object.keys(out.next!.win_probability_sources).sort()).toEqual(["kalshi", "polymarket"]);
  });

  it("A3: a frame that ends the game, or a finished page, takes nothing from the snapshot", () => {
    const f = priced(frame(11, 1, snap(11, { kalshi: entry(1, 11) }), { status: "completed" }));
    const page = held(10, withPm(10));
    expect(applyLiveFrameRail(page, f)).toEqual({ next: page, snapshotRail: false });
    const done = held(10, withPm(10), { status: "completed", hero_probability_source: "settled" });
    const g = priced(frame(11, 0.6, snap(11, { kalshi: entry(0.6, 11) })));
    expect(applyLiveFrameRail(done, g)).toEqual({ next: done, snapshotRail: false });
  });

  it("a REST poll older than a snapshot frame takes the frame's whole rail, not a one-source merge", () => {
    const polled = held(12, withPm(12));
    const out = reconcileEventPoll(polled, frame(13, 0.6, snap(13, { kalshi: entry(0.6, 13) })));
    expect(Object.keys(out.win_probability_sources)).toEqual(["kalshi"]);
    expect(out.blend_fold_revision).toEqual({ [E]: 13 });
  });
});

describe("§4 unpriced: no reading, no clock, no chart point", () => {
  const unpriced = [
    frame(11, 0.5, snap(11, {})),
    frame(11, 0.5, snap(11, { betting_book_count: { value: 3 } })),
  ];
  it.each(unpriced.map((f) => [JSON.stringify(f.source_snapshot), f]))("%s: adopts neither p nor the map", (_n, f) => {
    const page = held(10, withPm(10));
    expect(frameCarriesUnpricedSnapshot(f)).toBe(true);
    expect(applyLiveFrameRail(page, priced(f))).toEqual({ next: page, snapshotRail: false });
    // Not banked on the live chart, and not held over a priced frame.
    expect(rememberLiveChartFrame([], f, E)).toEqual([]);
    const pricedBefore = frame(10, 0.55);
    expect(heldFrameAfter(pricedBefore, f)).toBe(f);
    expect(heldFrameAfter(f, frame(12, 0.6))).toEqual(frame(12, 0.6));
    // Like a frame with no price, it is not a price an older priced frame outranks.
    expect(heldFrameAfter(frame(12, 0.6), f)).toBe(f);
  });

  it("the same frame without a snapshot is still today's price (legacy, byte for byte)", () => {
    const f = frame(11, 0.5);
    expect(frameCarriesUnpricedSnapshot(f)).toBe(false);
    expect(applyLiveFrame(held(10, withPm(10)), priced(f))!.hero_probability).toBe(0.5);
    expect(rememberLiveChartFrame([], f, E)).toHaveLength(1);
  });

  it("a refused unpriced-looking snapshot is absent: legacy adoption", () => {
    const f = frame(11, 0.5, snap(12, {}));
    expect(frameCarriesUnpricedSnapshot(f)).toBe(false);
    expect(applyLiveFrame(held(10, withPm(10)), priced(f))!.hero_probability).toBe(0.5);
  });

  it("a priced snapshot at or past a priceless trigger discharges it; nothing else does", () => {
    const shown = frame(12, 0.6, snap(12, { kalshi: entry(0.6, 12) }));
    expect(snapshotRailPaysPricelessTrigger(frame(11, null), shown)).toBe(true);
    expect(snapshotRailPaysPricelessTrigger(frame(12, null), shown)).toBe(true);
    expect(snapshotRailPaysPricelessTrigger(frame(11, 0.5, snap(11, {})), shown)).toBe(true);
    expect(snapshotRailPaysPricelessTrigger(frame(13, null), shown)).toBe(false); // owed past what is shown
    expect(snapshotRailPaysPricelessTrigger(frame(11, 0.6, undefined, { status: "completed" }), shown)).toBe(false); // a status change
    expect(snapshotRailPaysPricelessTrigger(frame(11, 0.6), shown)).toBe(false); // a priced trigger is not a rail debt
    expect(snapshotRailPaysPricelessTrigger(frame(11, null, undefined, { event_id: 1, rev: { 1: 11 } }), shown)).toBe(false);
    expect(snapshotRailPaysPricelessTrigger(frame(11, null, undefined, { rev: null }), shown)).toBe(false);
    expect(snapshotRailPaysPricelessTrigger(null, shown)).toBe(false);
  });
});

describe("§5 evidence: the snapshot's own stamps, never a held one renewed by equality", () => {
  it("a byte-identical Polymarket entry with `not_evaluated` loses the held `tradeable_book`; web withholds the lone pre-game 0.500", () => {
    const pm = (evidence: string) => ({ polymarket: entry(0.5, 9, { price_evidence: evidence }) });
    const pregame = held(10, pm("tradeable_book"), { status: "scheduled" });
    expect(shouldWithholdProbability(pregame)).toBe(false);
    const f = { ...frame(11, 0.5, snap(11, pm("not_evaluated")), { status: "scheduled", source: "polymarket" }) };
    const next = applyLiveFrame(pregame, priced(f))!;
    expect(next.win_probability_sources.polymarket).toEqual(pm("not_evaluated").polymarket);
    expect(shouldWithholdProbability(next)).toBe(true);
  });

  it("an entry with no evidence key carries none forward", () => {
    const next = applyLiveFrame(held(10, withPm(10)), priced(frame(11, 0.55,
      snap(11, { kalshi: entry(0.56, 10), polymarket: entry(0.5, 9) }))))!;
    expect("price_evidence" in next.win_probability_sources.polymarket).toBe(false);
  });
});
