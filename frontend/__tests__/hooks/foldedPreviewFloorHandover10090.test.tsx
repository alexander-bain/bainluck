/**
 * #10090 — on a page that folds two rows, the commit floor withdraws the held
 * preview before the combined result that folds the same write arrives. The
 * committed hero in between is the value at the OLD base, so the headline went
 * new → old → new (native measured the same gap on iOS: 30 ms median, 255 ms
 * worst). The headline must keep the preview it is already showing until that
 * result decides, for at most its own lifetime and the hand-over cap, and
 * every other withdrawal stays immediate.
 *
 * Real hook + controller over a fake EventSource and minimal DOM; the page's
 * own push callback lifted from `app/events/[id]/page.tsx` with the TypeScript
 * AST; the detail cache is React state (the page's swr cache stands in), so a
 * frame's cache write and the hook's preview change commit together under the
 * controller's `flushSync` delivery. Every COMMIT is recorded, not just the
 * last render of a batch.
 */
import "../helpers/minimalDom";
import React, { act, useLayoutEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";

import { heldFrameAfter, useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { adoptFoldedQuote, applyLiveFrame, applyLiveFrameRail, frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { frameFoldOrder } from "../../lib/foldRevision";
import { frameCarriesUnpricedSnapshot, snapshotRailPaysPricelessTrigger } from "../../lib/sourceSnapshot";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";
import { displayedPreview, displayedProbabilityObservedAt, overlayBlendPreview, overlayBlendPreviewLine } from "../../lib/blendPreview";
import { headlineDisplayIdentity } from "../../lib/displayIdentity";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const tree = ts.createSourceFile("page.tsx", PAGE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let callbackText: string | undefined;
(function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(tree) === "applyPushedFrame" &&
      node.initializer && ts.isCallExpression(node.initializer) &&
      node.initializer.expression.getText(tree) === "useCallback") {
    callbackText = node.initializer.arguments[0].getText(tree);
  }
  ts.forEachChild(node, visit);
})(tree);
if (!callbackText) throw new Error("page push callback missing");
const CALLBACK = new vm.Script(ts.transpileModule(`(${callbackText})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText);

class Source {
  static all: Source[] = [];
  readyState = 0;
  listeners = new Map<string, ((e: unknown) => void)[]>();
  constructor(readonly url: string) { Source.all.push(this); }
  addEventListener(k: string, f: (e: unknown) => void) { this.listeners.set(k, [...(this.listeners.get(k) ?? []), f]); }
  close() { this.readyState = 2; }
  emit(k: string, v?: unknown) {
    if (k === "open") this.readyState = 1;
    for (const f of this.listeners.get(k) ?? []) f(v === undefined ? {} : { data: typeof v === "string" ? v : JSON.stringify(v) });
  }
}

// ── fixtures: canonical row 1 folded with row 2 ─────────────────────────────
const E = 1;
const session = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const authority = { incarnation: "1", namespace: "11111111-1111-4111-8111-111111111111" };
const vector = { "1": 11, "2": 22 };
const committedAt = "2026-10-30T07:00:00Z";
const observed = "2026-10-30T07:00:05Z";
type Held = {
  id: number; status: string; sport: string; hero_probability: number; hero_probability_away: number | null;
  hero_probability_source: string; hero_probability_observed_at: string;
  blend_fold_revision: Record<string, number>; win_probability_sources: Record<string, unknown>;
};
const held = (revision: Record<string, number> = vector): Held => ({
  id: E, status: "live", sport: "soccer_epl", hero_probability: 0.4, hero_probability_away: 0.6,
  hero_probability_source: "blend", hero_probability_observed_at: committedAt,
  blend_fold_revision: revision, win_probability_sources: {},
});
const opening = (members = [1, 2], over: Record<string, unknown> = {}) =>
  ({ protocol: 3, event_id: E, authority, stream_session: session, members, ...over });
const wrap = (frame: unknown, over: Record<string, unknown> = {}) =>
  ({ protocol: 3, event_id: E, authority, stream_session: session, frame, ...over });
const folded = (seq: number, p: number, base: Record<string, number> = vector, ttl = 5000) => ({
  event_id: E, p, p_away: null, status: "live", sport: "soccer_epl", display_observed_at: observed,
  preview: { kind: "blend", folded_version: 2, fold_session: session, fold_seq: seq, ttl_ms: ttl,
    origin_authority: { "1": { epoch: 900, seq, state: "pending", ttl_ms: ttl },
      "2": { epoch: 12, seq: 80 + seq, state: "pending", ttl_ms: ttl } }, base_fold_revision: base },
});
const floorPacket = (floor: Record<string, number>) => ({ event_id: E, floor });
// Server shape (`event_stream.py`): the sibling's raw write is a priceless
// invalidation with the promise; the combined result follows as its own event.
const pendingRaw = (rev: Record<string, number>, over: Record<string, unknown> = {}) => ({
  event_id: E, origin_event_id: 2, invalidation: true, p: null, source: null, source_value: null,
  updated_at: "2026-10-30T07:00:06Z", rev, folded_quote_pending: true, ...over,
});
const quote = (p: number, revision: Record<string, number>, over: Record<string, unknown> = {}) => ({
  event_id: E, hero_probability: p, hero_probability_away: 1 - p, hero_probability_source: "blend",
  hero_probability_observed_at: "2026-10-30T07:00:06Z", blend_fold_revision: revision,
  win_probability_sources: { kalshi: { value: p, display_name: "Kalshi", type: "market", color: "#000" } },
  hero_sportsbook_count: null, status: "live", sport: "soccer_epl", hero_settled_result: null, ...over,
});
const result = (rev: Record<string, number>, folded_quote: unknown) =>
  ({ ...pendingRaw(rev), folded_quote_pending: false, folded_quote });
const moved = { "1": 11, "2": 23 };

type Commit = { headline: number; chart: number | null; basis: string; state: string; received: number | null; observed: string | null };
let commits: Commit[] = [];
let requests = 0;
let showMembership: (m: Record<string, number>) => void = () => {};

function HeldPage({ initial }: { initial: Held }) {
  const [cache, setCache] = useState(initial);
  const [membership, setMembership] = useState<Record<string, number> | null>(null);
  showMembership = setMembership;
  const [refs] = useState(() => ({
    heldEventRef: { current: undefined as Held | undefined },
    quoteTriggerRef: { current: null as LiveFrame | null },
    sourceAddedHistoryRef: { current: null },
    latestLiveFrameRef: { current: null as LiveFrame | null },
    pairJournalRef: { current: null },
  }));
  refs.heldEventRef.current = cache;
  const [applyPushedFrame] = useState(() => CALLBACK.runInNewContext({
    eventId: E, ...refs,
    foldedRefetch: { request: () => { requests += 1; } },
    refreshEvent: (update: (prev: Held) => Held) => { setCache(prev => update(prev)); return Promise.resolve(); },
    setLastRefresh: () => {}, reconcileCatchupRef: { current: null }, reconcileOrdinalRef: { current: 0 },
    Date, adoptFoldedQuote, applyLiveFrame, frameInvalidatesFoldedBlend, canSubscribeEventQuotes, heldFrameAfter,
    applyLiveFrameRail, frameCarriesUnpricedSnapshot, frameFoldOrder, snapshotRailPaysPricelessTrigger,
  }) as (f: LiveFrame) => void);
  const { blendPreview, blendPreviewNow } = useLiveEventStream(
    E, true, applyPushedFrame, undefined, membership ?? cache.blend_fold_revision);
  // The page's three readers of one preview: headline, its identity, chart edge.
  const headline = overlayBlendPreview(cache, blendPreview, blendPreviewNow).hero_probability;
  const shown = displayedPreview(blendPreview, cache, blendPreviewNow) !== null;
  const identity = headlineDisplayIdentity({
    heroBlend: true, previewShown: shown, preview: blendPreview, committedRevision: cache.blend_fold_revision,
    observedAt: displayedProbabilityObservedAt(cache, blendPreview, blendPreviewNow, cache.hero_probability_observed_at),
  });
  const chart = overlayBlendPreviewLine(cache, blendPreview, blendPreviewNow, [])?.at(-1)?.home_probability ?? null;
  const commit: Commit = { headline, chart, basis: identity.basis, state: identity.state,
    received: identity.receivedAt, observed: identity.observedAt };
  useLayoutEffect(() => { commits.push(commit); });
  return <span>{headline}</span>;
}

async function mount(initial: Held = held(), members = [1, 2], first: unknown = folded(1, 0.48)) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<HeldPage initial={initial} />); });
  const stream = Source.all.at(-1)!;
  const emit = async (...events: [string, unknown?][]) => {
    await act(async () => { for (const [k, v] of events) stream.emit(k, v); });
  };
  await emit(["open"], ["preview_open_v3", opening(members)], ["preview_v3", wrap(first)]);
  const last = () => commits.at(-1)!;
  return {
    stream, emit, last,
    mark: () => commits.length,
    since: (mark: number) => commits.slice(mark).map(c => c.headline),
    advance: async (ms: number) => { await act(async () => { jest.advanceTimersByTime(ms); }); },
    unmount: async () => { await act(async () => root.unmount()); document.body.removeChild(el); },
  };
}

const originalEventSource = globalThis.EventSource;
beforeEach(() => {
  Source.all = []; commits = []; requests = 0;
  globalThis.EventSource = Source as unknown as typeof EventSource;
  jest.useFakeTimers();
});
afterEach(() => {
  globalThis.EventSource = originalEventSource;
  jest.useRealTimers();
});

describe("#10090 the folded headline keeps its preview across the commit floor", () => {
  test("floor → pending raw → adopted result: no commit prints the pre-floor value; headline, identity and chart move together", async () => {
    const page = await mount();
    const before = page.last();
    expect(before).toMatchObject({ headline: 0.48, chart: 0.48, basis: "preview", observed });
    const mark = page.mark();
    await page.emit(["fold_preview_floor", floorPacket(moved)]);
    // The SAME preview, not a re-admitted one: identity, receipt and observation unchanged.
    expect(page.last()).toEqual(before);
    await page.emit(["probability", pendingRaw({ "2": 23 })]);
    expect(page.last()).toEqual(before);
    await page.emit(["folded_probability", result({ "2": 23 }, quote(0.49, moved))]);
    expect(page.last()).toMatchObject({ headline: 0.49, chart: null, basis: "committed", observed: "2026-10-30T07:00:06Z" });
    expect(page.since(mark)).not.toContain(0.4);
    expect(requests).toBe(0);
    await page.unmount();
  });

  test("the whole sequence in one transport chunk ends on the result with no old value committed", async () => {
    const page = await mount();
    const mark = page.mark();
    await page.emit(["fold_preview_floor", floorPacket(moved)], ["probability", pendingRaw({ "2": 23 })],
      ["folded_probability", result({ "2": 23 }, quote(0.49, moved))]);
    expect(page.since(mark)).not.toContain(0.4);
    expect(page.last()).toMatchObject({ headline: 0.49, basis: "committed" });
    await page.unmount();
  });

  test.each([
    ["held (not newer)", quote(0.47, vector), 0],
    ["null (the server could not fold)", null, 1],
    ["refused (not a blend)", quote(0.47, moved, { hero_probability_source: "kalshi" }), 1],
  ])("a %s result ends the hand-over at once and the committed value shows", async (_name, folded_quote, reads) => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket(moved)], ["probability", pendingRaw({ "2": 23 })]);
    expect(page.last().headline).toBe(0.48);
    await page.emit(["folded_probability", result({ "2": 23 }, folded_quote)]);
    expect(page.last()).toMatchObject({ headline: 0.4, chart: null, basis: "committed" });
    expect(requests).toBe(reads);
    await page.unmount();
  });

  test("a result that carries no revision still ends the hand-over", async () => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket(moved)], ["probability", pendingRaw({ "2": 23 })]);
    const { rev: _rev, ...revless } = result({ "2": 23 }, null);
    await page.emit(["folded_probability", revless]);
    expect(page.last()).toMatchObject({ headline: 0.4, chart: null, basis: "committed" });
    await page.unmount();
  });

  test("no result: the hand-over ends at its cap, never at the preview's full lifetime", async () => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket(moved)], ["probability", pendingRaw({ "2": 23 })]);
    await page.advance(999);
    expect(page.last().headline).toBe(0.48);
    await page.advance(2);
    expect(page.last()).toMatchObject({ headline: 0.4, chart: null, basis: "committed" });
    await page.unmount();
  });

  test("no result: a preview whose own lifetime ends sooner ends the hand-over then", async () => {
    const page = await mount(held(), [1, 2], folded(1, 0.48, vector, 400));
    await page.emit(["fold_preview_floor", floorPacket(moved)]);
    await page.advance(399);
    expect(page.last().headline).toBe(0.48);
    await page.advance(2);
    expect(page.last().headline).toBe(0.4);
    await page.unmount();
  });

  test("a newer preview over the new floor replaces it; a refused one ends it", async () => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket(moved)]);
    await page.emit(["preview_v3", wrap(folded(2, 0.5, moved))]);
    expect(page.last()).toMatchObject({ headline: 0.5, chart: 0.5, basis: "preview" });

    const other = await mount();
    await other.emit(["fold_preview_floor", floorPacket(moved)]);
    // Still on the old base: the reader refuses it, and the reader decides.
    await other.emit(["preview_v3", wrap(folded(2, 0.52, vector))]);
    expect(other.last()).toMatchObject({ headline: 0.4, basis: "committed" });
    await page.unmount(); await other.unmount();
  });

  test.each([
    ["resync", (p: Page) => p.emit(["resync", { generation: 1 }])],
    ["reconcile", (p: Page) => p.emit(["reconcile", { event_id: E, custody_id: "removal:1", removal_rev: moved }])],
    ["a malformed floor", (p: Page) => p.emit(["fold_preview_floor", "{"])],
    ["a raw frame with no promise", (p: Page) => p.emit(["probability", { ...pendingRaw({ "2": 24 }), folded_quote_pending: undefined }])],
    ["a pending frame that changes status", (p: Page) => p.emit(["probability", pendingRaw({ "2": 24 }, { status: "suspended" })])],
    ["a new authority domain", (p: Page) => p.emit(["preview_open_v3", opening([1, 2], {
      authority: { incarnation: "2", namespace: "22222222-2222-4222-8222-222222222222" } })])],
    ["a membership change", async () => { await act(async () => { showMembership({ "1": 11, "3": 1 }); }); }],
  ])("%s during the hand-over withdraws the preview at once", async (_name, act_) => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket(moved)]);
    expect(page.last().headline).toBe(0.48);
    await act_(page);
    expect(page.last()).toMatchObject({ headline: 0.4, chart: null, basis: "committed" });
    await page.unmount();
  });

  test("a floor carrying a row outside the fold withdraws at once", async () => {
    const page = await mount();
    await page.emit(["fold_preview_floor", floorPacket({ ...moved, "3": 1 })]);
    expect(page.last()).toMatchObject({ headline: 0.4, basis: "committed" });
    await page.unmount();
  });

  test("a singleton page is unchanged: its commit floor withdraws at once", async () => {
    const single = { "1": 11 };
    const preview = {
      event_id: E, p: 0.48, status: "live", sport: "soccer_epl", display_observed_at: observed,
      preview: { kind: "blend", epoch: 900, seq: 1, base_rev: 11, ttl_ms: 5000 },
    };
    const page = await mount(held(single), [1], preview);
    expect(page.last().headline).toBe(0.48);
    await page.emit(["probability", { event_id: E, p: 0.45, source: "kalshi", source_value: 0.45,
      updated_at: "2026-10-30T07:00:06Z", status: "live", rev: { "1": 12 } }]);
    expect(page.last()).toMatchObject({ headline: 0.45, basis: "committed" });
    await page.unmount();
  });

  test("a singleton page handed a fold floor withdraws at once", async () => {
    const page = await mount(held({ "1": 11 }), [1], {
      event_id: E, p: 0.48, status: "live", sport: "soccer_epl", display_observed_at: observed,
      preview: { kind: "blend", epoch: 900, seq: 1, base_rev: 11, ttl_ms: 5000 },
    });
    expect(page.last().headline).toBe(0.48);
    await page.emit(["fold_preview_floor", floorPacket({ "1": 12 })]);
    expect(page.last()).toMatchObject({ headline: 0.4, basis: "committed" });
    await page.unmount();
  });
});

type Page = Awaited<ReturnType<typeof mount>>;
