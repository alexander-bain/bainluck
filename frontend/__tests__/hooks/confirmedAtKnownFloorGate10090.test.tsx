/**
 * #10090 decision J, C1 — a confirmation never vouches for a revision older
 * than a commit floor the page already knows (live's contract, 0830Z §3–§4).
 *
 * `confirmed_at` is true of the backend's published state when it was sent. A
 * heartbeat repeats the last value whatever is owed, and on the floor-only
 * paths the server may even ADVANCE it for a commit the reader does not hold.
 * So once the stream announces a floor the committed revision on screen does
 * not cover, the page claims no confirmation: no "Connected" without
 * "waiting", no "Probability confirmed" row, no confirmation in the age clock
 * (it reads the shown value's own clock). Received values are kept, and only a
 * committed revision covering every floor — an adopted result or a load —
 * lets them count again under J's rule.
 *
 *   confirmationOwed = F non-empty AND (P == nil OR some k in F: P[k] missing or P[k] < F[k])
 *
 * Real hook + controller over a fake EventSource; the page's own push callback
 * lifted from `app/events/[id]/page.tsx` with the TypeScript AST; the detail
 * cache is React state standing in for the page's swr cache. Every COMMIT is
 * recorded, not just the last render of a batch.
 */
import "../helpers/minimalDom";
import React, { act, useLayoutEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";

import LiveConnectionStatus from "../../components/event/LiveConnectionStatus";
import { heldFrameAfter, useLiveEventStream, type LiveFrame } from "../../hooks/useLiveEventStream";
import { adoptFoldedQuote, applyLiveFrame, applyLiveFrameRail, frameInvalidatesFoldedBlend } from "../../lib/eventLivePush";
import { frameFoldOrder } from "../../lib/foldRevision";
import { frameCarriesUnpricedSnapshot, snapshotRailPaysPricelessTrigger } from "../../lib/sourceSnapshot";
import { canSubscribeEventQuotes } from "../../lib/eventQuoteStream";
import { displayedProbabilityObservedAt, overlayBlendPreview } from "../../lib/blendPreview";
import {
  EMPTY_CONNECTION_TRACKER,
  confirmationFloorsAfter,
  confirmationOwed,
  presentConnectionStatus,
  priceAgeClock,
} from "../../lib/event/liveConnectionStatus";

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

// The page's own words for J, read from the page so the guard follows edits.
test("the page feeds the hook's confirmedAt to the age clock, the words and the details row", () => {
  expect(PAGE).toContain("confirmedAt: streamConfirmedAt");
  expect(PAGE).toContain("priceStamp: priceAgeClock(freshestSourceStamp, streamConfirmedAt)");
  expect(PAGE).toContain('priceConfirmed: Boolean(acceptedPriceClock) && typeof streamConfirmedAt === "string"');
  expect(PAGE).toContain("priceConfirmedAt={streamConfirmedAt}");
  expect(PAGE).toMatch(/useLiveEventStream\(eventId, quoteEligible, applyPushedFrame, applyReconcileControl, event\?\.blend_fold_revision\)/);
});

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

// ── fixtures: canonical row 1 folded with row 2 (fixed clocks, gotcha #44) ──
const E = 1;
const session = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const authority = { incarnation: "1", namespace: "11111111-1111-4111-8111-111111111111" };
const vector = { "1": 11, "2": 22 };
const moved = { "1": 11, "2": 23 };
const committedAt = "2026-10-30T07:00:00Z";
const observed = "2026-10-30T07:00:05Z";
const resultAt = "2026-10-30T07:00:06Z";
const T = "2026-10-30T07:00:08Z"; // newer than every shown clock
const T2 = "2026-10-30T07:00:09Z"; // c' > T
const NOW = Date.parse("2026-10-30T07:00:10Z");
type Held = {
  id: number; status: string; sport: string; hero_probability: number; hero_probability_away: number | null;
  hero_probability_source: string; hero_probability_observed_at: string;
  blend_fold_revision: Record<string, number>; win_probability_sources: Record<string, unknown>;
};
const held = (revision: Record<string, number> = vector, over: Partial<Held> = {}): Held => ({
  id: E, status: "live", sport: "soccer_epl", hero_probability: 0.4, hero_probability_away: 0.6,
  hero_probability_source: "blend", hero_probability_observed_at: committedAt,
  blend_fold_revision: revision, win_probability_sources: {}, ...over,
});
const opening = { protocol: 3, event_id: E, authority, stream_session: session, members: [1, 2] };
const folded = (seq: number, p: number, base: Record<string, number> = vector) => ({
  protocol: 3, event_id: E, authority, stream_session: session, frame: {
    event_id: E, p, p_away: null, status: "live", sport: "soccer_epl", display_observed_at: observed,
    preview: { kind: "blend", folded_version: 2, fold_session: session, fold_seq: seq, ttl_ms: 5000,
      origin_authority: { "1": { epoch: 900, seq, state: "pending", ttl_ms: 5000 },
        "2": { epoch: 12, seq: 80 + seq, state: "pending", ttl_ms: 5000 } }, base_fold_revision: base },
  },
});
const heartbeat = (confirmed_at: string) => ({ t: 1, confirmed_at });
const floorPacket = (floor: Record<string, number>) => ({ event_id: E, floor });
const pendingRaw = (rev: Record<string, number>) => ({
  event_id: E, origin_event_id: 2, invalidation: true, p: null, source: null, source_value: null,
  updated_at: resultAt, rev, folded_quote_pending: true,
});
const quote = (p: number, revision: Record<string, number>) => ({
  event_id: E, hero_probability: p, hero_probability_away: 1 - p, hero_probability_source: "blend",
  hero_probability_observed_at: resultAt, blend_fold_revision: revision,
  win_probability_sources: { kalshi: { value: p, display_name: "Kalshi", type: "market", color: "#000" } },
  hero_sportsbook_count: null, status: "live", sport: "soccer_epl", hero_settled_result: null,
});
const result = (rev: Record<string, number>, folded_quote: unknown) =>
  ({ ...pendingRaw(rev), folded_quote_pending: false, folded_quote });

type Commit = {
  headline: number; confirmedAt: string | null; shownClock: string | null; ageClock: string | null;
  label: string; revision: Record<string, number>;
};
let commits: Commit[] = [];
let requests = 0;
let load: (next: Held) => void = () => {};

function HeldPage({ initial }: { initial: Held }) {
  const [cache, setCache] = useState(initial);
  load = setCache;
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
  const { blendPreview, blendPreviewNow, confirmedAt, status } = useLiveEventStream(
    E, true, applyPushedFrame, undefined, cache.blend_fold_revision);
  const headline = overlayBlendPreview(cache, blendPreview, blendPreviewNow).hero_probability;
  // The page's `acceptedPriceClock`: the displayed value's own observation.
  const shownClock = displayedProbabilityObservedAt(cache, blendPreview, blendPreviewNow, cache.hero_probability_observed_at) ?? null;
  const label = presentConnectionStatus(EMPTY_CONNECTION_TRACKER, {
    status, terminalLabel: null, priceMayBeOld: false, scoreMayBeOld: false,
    priceConfirmed: Boolean(shownClock) && typeof confirmedAt === "string",
  }, NOW).label;
  const commit: Commit = {
    headline, confirmedAt, shownClock, ageClock: priceAgeClock(shownClock, confirmedAt), label,
    revision: cache.blend_fold_revision,
  };
  useLayoutEffect(() => { commits.push(commit); });
  return <span>{headline}</span>;
}

const details = (c: Commit) => renderToStaticMarkup(
  <LiveConnectionStatus
    presentation={{ label: c.label, tone: "live", breathes: true, announcement: "" }}
    priceObservedAt={c.shownClock} priceConfirmedAt={c.confirmedAt}
    scoreShown={false} scoreConfirmedAt={null} oldestFact={null} now={NOW}
  />,
);

async function mount(initial: Held = held(), withPreview = true) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<HeldPage initial={initial} />); });
  // A membership change replaces the controller, so always the newest socket.
  const emit = async (...events: [string, unknown?][]) => {
    await act(async () => { for (const [k, v] of events) Source.all.at(-1)!.emit(k, v); });
  };
  await emit(["open"], ...(withPreview
    ? [["preview_open_v3", opening], ["preview_v3", folded(1, 0.48)]] as [string, unknown][]
    : []));
  return {
    emit,
    last: () => commits.at(-1)!,
    mark: () => commits.length,
    since: (mark: number) => commits.slice(mark),
    load: async (next: Held) => { await act(async () => { load(next); }); },
    unmount: async () => { await act(async () => root.unmount()); document.body.removeChild(el); },
  };
}
type Page = Awaited<ReturnType<typeof mount>>;

/** Step 1: hold {1:11, 2:22}, heartbeat T newer than the shown clock — confirmed (the control). */
async function confirmedPage(): Promise<Page> {
  const page = await mount();
  await page.emit(["heartbeat", heartbeat(T)]);
  expect(page.last()).toMatchObject({ headline: 0.48, confirmedAt: T, shownClock: observed, ageClock: T, label: "Connected" });
  expect(details(page.last())).toContain("Probability confirmed");
  return page;
}

function expectUnconfirmed(c: Commit) {
  expect(c.confirmedAt).toBeNull();
  expect(c.ageClock).toBe(c.shownClock);
  expect(c.label).toBe("Connected · waiting");
  expect(details(c)).not.toContain("Probability confirmed");
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

describe("#10090 J C1 live's catching sequence", () => {
  test("floor → repeat T → advance c' → null result: never confirmed; the covering result resumes J with c'", async () => {
    const page = await confirmedPage();
    // 2. A floor with no raw frame. The committed revision is still {1:11, 2:22}.
    //    What shows is aged by its OWN clock: the committed value's, or — where
    //    #11780's hand-over keeps the preview up to 1 s — that preview's
    //    `display_observed_at`.
    let mark = page.mark();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 23 })]);
    expect(page.last().revision).toEqual(vector);
    for (const c of page.since(mark)) {
      expect([[0.4, committedAt], [0.48, observed]]).toContainEqual([c.headline, c.shownClock]);
    }
    page.since(mark).forEach(expectUnconfirmed);
    // 3. T again: a repeat is not a re-confirmation.
    mark = page.mark();
    await page.emit(["heartbeat", heartbeat(T)]);
    page.since(mark).forEach(expectUnconfirmed);
    expectUnconfirmed(page.last());
    // 4. c' > T: true of rev 23, which the reader does not hold.
    mark = page.mark();
    await page.emit(["heartbeat", heartbeat(T2)]);
    page.since(mark).forEach(expectUnconfirmed);
    expectUnconfirmed(page.last());
    // 5. The raw promise, then `folded_quote: null`: neither moves P.
    mark = page.mark();
    await page.emit(["probability", pendingRaw({ "2": 23 })]);
    await page.emit(["folded_probability", result({ "2": 23 }, null)]);
    expect(requests).toBe(1);
    expect(page.last().revision).toEqual(vector);
    page.since(mark).forEach(expectUnconfirmed);
    expectUnconfirmed(page.last());
    // 6. The covering result: J resumes, with the c' stored during the gap.
    await page.emit(["folded_probability", result({ "2": 23 }, quote(0.49, moved))]);
    expect(page.last()).toMatchObject({
      headline: 0.49, revision: moved, shownClock: resultAt, confirmedAt: T2, ageClock: T2, label: "Connected",
    });
    expect(details(page.last())).toContain("Probability confirmed");
    await page.unmount();
  });

  test("the whole sequence in one transport chunk commits no confirmation before the covering result", async () => {
    const page = await confirmedPage();
    const mark = page.mark();
    await page.emit(
      ["fold_preview_floor", floorPacket({ "2": 23 })], ["heartbeat", heartbeat(T)], ["heartbeat", heartbeat(T2)],
      ["probability", pendingRaw({ "2": 23 })], ["folded_probability", result({ "2": 23 }, null)],
    );
    page.since(mark).forEach(expectUnconfirmed);
    await page.emit(["folded_probability", result({ "2": 23 }, quote(0.49, moved))]);
    expect(page.last()).toMatchObject({ revision: moved, confirmedAt: T2, label: "Connected" });
    await page.unmount();
  });

  test("a committed load that covers the floor clears it; one that does not keeps it owed", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 23 })], ["heartbeat", heartbeat(T2)]);
    await page.load(held({ "1": 12, "2": 22 }, { hero_probability_observed_at: resultAt }));
    expectUnconfirmed(page.last());
    await page.load(held({ "1": 12, "2": 23 }, { hero_probability_observed_at: resultAt }));
    expect(page.last()).toMatchObject({ confirmedAt: T2, ageClock: T2, label: "Connected" });
    await page.unmount();
  });

  test("an equal displayed percentage is not coverage", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 23 })]);
    // The same 0.4 the page already shows, at the old revision: held, not adopted.
    await page.emit(["folded_probability", result({ "2": 23 }, quote(0.4, vector))]);
    expect(page.last()).toMatchObject({ headline: 0.4, revision: vector });
    expectUnconfirmed(page.last());
    // A load printing the same 0.4 below the floor is still owed too.
    await page.load(held({ "1": 11, "2": 22 }, { hero_probability_observed_at: resultAt }));
    expectUnconfirmed(page.last());
    await page.unmount();
  });

  test("a reconcile control's floor is a floor", async () => {
    const page = await confirmedPage();
    await page.emit(["reconcile", { event_id: E, custody_id: "removal:1", removal_rev: moved }]);
    expectUnconfirmed(page.last());
    await page.load(held(moved));
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.unmount();
  });

  test("a floor naming a row the shown revision lacks is owed until a load carries it", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "3": 1 })]);
    expectUnconfirmed(page.last());
    await page.load(held({ ...vector, "3": 1 }));
    await page.emit(["open"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.unmount();
  });

  test("a row leaving the committed fold no longer holds the confirmation", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 23 })]);
    expectUnconfirmed(page.last());
    await page.load(held({ "1": 12 }));
    await page.emit(["open"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.unmount();
  });

  // R1 (lane1 Q1): the reader parks a departing row's floor and restores it when
  // detail adopts the row again. Detail is cached per worker, so a stale read can
  // re-add the row below the floor the page already knows.
  test("a row that leaves and rejoins below its known floor is owed again until a load covers it", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 24 })]);
    expectUnconfirmed(page.last());
    await page.load(held({ "1": 12 }));
    await page.emit(["open"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.load(held({ "1": 12, "2": 22 }));
    await page.emit(["open"]);
    expectUnconfirmed(page.last());
    await page.load(held({ "1": 12, "2": 24 }));
    await page.emit(["open"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.unmount();
  });

  // R2 (lane1 Q5): the restore is an effect, so the render that re-adds the row
  // must already owe its parked floor — no commit of the stale rejoin confirms.
  test("no commit of a stale rejoin load claims the confirmation, before or after the restore", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 24 })]);
    await page.load(held({ "1": 12 }));
    await page.emit(["open"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    const mark = page.mark();
    await page.load(held({ "1": 12, "2": 22 }));
    expect(page.since(mark).length).toBeGreaterThan(0);
    // The membership change replaces the controller, so a later commit may
    // honestly read "Connecting"; none may read "Connected" or carry the claim.
    for (const c of page.since(mark)) {
      expect(c.confirmedAt).toBeNull();
      expect(c.ageClock).toBe(c.shownClock);
      expect(c.label).not.toBe("Connected");
      expect(details(c)).not.toContain("Probability confirmed");
    }
    await page.unmount();
  });
});

describe("#10090 J C1 the gate suppresses only what it must", () => {
  test("strawman: a covered floor {2:22} keeps the confirmation", async () => {
    const page = await confirmedPage();
    const mark = page.mark();
    await page.emit(["fold_preview_floor", floorPacket({ "2": 22 })], ["heartbeat", heartbeat(T2)]);
    for (const c of page.since(mark)) expect(c.confirmedAt).not.toBeNull();
    expect(page.last()).toMatchObject({ headline: 0.48, confirmedAt: T2, ageClock: T2, label: "Connected" });
    await page.unmount();
  });

  test("a malformed floor adds nothing", async () => {
    const page = await confirmedPage();
    await page.emit(["fold_preview_floor", "{"]);
    expect(page.last()).toMatchObject({ confirmedAt: T, label: "Connected" });
    await page.unmount();
  });

  test("no floor at all: J unchanged", async () => {
    const page = await mount(held(), false);
    await page.emit(["heartbeat", heartbeat(T)]);
    expect(page.last()).toMatchObject({ confirmedAt: T, ageClock: T, label: "Connected" });
    await page.unmount();
  });
});

describe("#10090 J C1 pure rule", () => {
  test("floors merge max per row; malformed or non-row keys add nothing", () => {
    const f = confirmationFloorsAfter({}, { "2": 23 });
    expect(f).toEqual({ "2": 23 });
    expect(confirmationFloorsAfter(f, { "2": 22, "1": 4 })).toEqual({ "1": 4, "2": 23 });
    expect(confirmationFloorsAfter(f, { "2": 22 })).toBe(f);
    expect(confirmationFloorsAfter(f, null)).toBe(f);
    expect(confirmationFloorsAfter(f, { abc: 30 })).toBe(f);
    expect(confirmationFloorsAfter(f, { "2": -1 })).toBe(f);
  });

  test("owed exactly when some floor is uncovered or nothing on screen carries a revision", () => {
    expect(confirmationOwed({}, null)).toBe(false);
    expect(confirmationOwed({ "2": 23 }, null)).toBe(true);
    expect(confirmationOwed({ "2": 23 }, vector)).toBe(true);
    expect(confirmationOwed({ "2": 22 }, vector)).toBe(false);
    expect(confirmationOwed({ "2": 23 }, moved)).toBe(false);
    expect(confirmationOwed({ "3": 1 }, vector)).toBe(true);
  });
});
