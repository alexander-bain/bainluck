/**
 * #10646 (parent #10090) — a held opening/nonblend web page whose fresh
 * detail/history pair FAILS or comes back BEHIND the triggering revision must
 * still reach the coherent headline, even when the stream then goes quiet.
 *
 * Before the fix the pair callback correctly refused the incomplete read and
 * kept the trigger, but the scheduler had already cleared its pending flag, so
 * nothing re-read until another frame or the fallback poll. The repair is one
 * opt-in automatic retry per external invalidation, inside the scheduler's
 * existing one-second start bound.
 *
 * WHAT IS REAL: the page's own paired-read callback and its `[foldedRefetch]`
 * scheduler factory, lifted out of `app/events/[id]/page.tsx` with the
 * TypeScript AST and evaluated as written (no hand copy), over the real
 * `createFoldedRefetchScheduler`, `canSubscribeEventQuotes`,
 * `quotePairCoversTrigger`, `keepNewerHeldHeadline`, `historyRangeParam` and
 * the page's `FOLDED_FRAME_REFETCH_MS`. WHAT IS DOUBLED: the two fetches, the
 * two cache writers, and the clock (`jest.useFakeTimers`, `Date.now`
 * included). The mounted twin is `hooks/pairedQuoteRecoveryMounted10646`.
 *
 * Not claimed: network cancellation. `Promise.all` can settle on one rejected
 * half while its sibling request is still finishing; that is unchanged.
 */
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import { createFoldedRefetchScheduler } from "@/lib/foldedRefetchScheduler";
import { canSubscribeEventQuotes, quotePairCoversTrigger } from "@/lib/eventQuoteStream";
import { keepNewerHeldHeadline } from "@/lib/reconcileEventPoll";
import { historyRangeParam } from "@/lib/event/historyRange";
import { EVENT_BOOT_HISTORY_HOURS } from "@/lib/event/detailBoot";

const PAGE_PATH = path.join(__dirname, "../../app/events/[id]/page.tsx");
const PAGE = fs.readFileSync(PAGE_PATH, "utf8");
const FOLDED_FRAME_REFETCH_MS = Number(PAGE.match(/const FOLDED_FRAME_REFETCH_MS = (\d+)/)![1]);

function pageExpressions(): { pair: string; factory: string } {
  const tree = ts.createSourceFile("page.tsx", PAGE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let pair: string | undefined;
  let factory: string | undefined;
  const visit = (n: ts.Node) => {
    if (ts.isBinaryExpression(n) && n.left.getText(tree) === "pairedQuoteReadRef.current" &&
        ts.isArrowFunction(n.right)) pair = n.right.getText(tree);
    if (ts.isVariableDeclaration(n) && n.name.getText(tree) === "[foldedRefetch]" &&
        n.initializer && ts.isCallExpression(n.initializer)) {
      const init = n.initializer.arguments[0];
      if (init && ts.isArrowFunction(init)) factory = init.body.getText(tree);
    }
    ts.forEachChild(n, visit);
  };
  visit(tree);
  if (!pair || !factory) throw new Error("page no longer exposes the paired read / scheduler factory");
  return { pair, factory };
}

const EXPR = pageExpressions();
const EVENT_ID = 7;

type Detail = { id: number; status: string; hero_probability: number; hero_probability_source: string;
  blend_fold_revision?: Record<string, number>; completed_at?: string | null };
type History = { event_id: number; blend_edge_pinned: boolean; blend_edge_fold_revision?: Record<string, number>;
  aggregate_line?: { home_probability: number }[] };

async function settle() {
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
}

function setup(detailRevisions: Array<() => Promise<number>>) {
  let calls = 0;
  let applied = 0;
  let active = 0;
  let maxActive = 0;
  const quoteTriggerRef: { current: unknown } = { current: { event_id: EVENT_ID, rev: { 7: 12 } } };
  const heldEventRef: { current: Detail | undefined } = {
    current: { id: EVENT_ID, status: "scheduled", hero_probability_source: "opening", hero_probability: 0.4 },
  };
  const historyRef: { current: History | null } = { current: null };
  const pairedQuoteReadRef: { current: (() => Promise<unknown>) | null } = { current: null };
  const context: Record<string, unknown> = {
    createFoldedRefetchScheduler, canSubscribeEventQuotes, quotePairCoversTrigger,
    keepNewerHeldHeadline, historyRangeParam, EVENT_BOOT_HISTORY_HOURS, FOLDED_FRAME_REFETCH_MS,
    pairedQuoteReadRef, quoteTriggerRef, heldEventRef,
    eventId: EVENT_ID, fullHistoryRequested: false,
    quoteEventIdRef: { current: EVENT_ID }, quoteHistoryRangeRef: { current: false },
    freshNextEventReadRef: { current: false },
    fetchEvent: async (): Promise<Detail> => {
      const index = calls++;
      active += 1;
      maxActive = Math.max(maxActive, active);
      try {
        const rev = await (detailRevisions[index] ?? detailRevisions[detailRevisions.length - 1])();
        return { id: EVENT_ID, status: "scheduled", blend_fold_revision: { 7: rev },
          hero_probability_source: "blend", hero_probability: 0.52 };
      } finally {
        active -= 1;
      }
    },
    fetchEventHistory: async (): Promise<History> => ({ event_id: EVENT_ID, blend_edge_pinned: true,
      blend_edge_fold_revision: { 7: 12 }, aggregate_line: [{ home_probability: 0.52 }] }),
    refreshHistoryRef: { current: async (h: History) => { historyRef.current = h; } },
    refreshEventRef: { current: async (d: Detail) => { heldEventRef.current = d; applied += 1; } },
    setLastRefresh: () => {},
    Date,
  };
  const evaluate = (code: string) => vm.runInNewContext(
    ts.transpileModule(`(${code})`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText,
    context,
  );
  pairedQuoteReadRef.current = evaluate(EXPR.pair);
  const scheduler = evaluate(EXPR.factory) as ReturnType<typeof createFoldedRefetchScheduler>;
  return {
    scheduler, context, quoteTriggerRef, heldEventRef, historyRef,
    calls: () => calls, applied: () => applied, maxActive: () => maxActive,
  };
}

const advance = (ms: number) => jest.advanceTimersByTimeAsync(ms);

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(Date.UTC(2026, 9, 6, 20, 0, 0)));
});
afterEach(() => {
  jest.useRealTimers();
});

describe("#10646 the page's scheduler opts the quote pair into one bounded retry", () => {
  it("the factory passes the page clock and an unresolved-quote predicate", () => {
    const code = EXPR.factory.replace(/\/\/[^\n]*/g, "");
    expect(code).toMatch(/\}, FOLDED_FRAME_REFETCH_MS, Date\.now,\s*\(\) => quoteTriggerRef\.current !== null && canSubscribeEventQuotes\(heldEventRef\.current\),\s*\)$/);
    expect(FOLDED_FRAME_REFETCH_MS).toBe(1000);
  });
});

describe.each([
  ["rejected", () => Promise.reject(new Error("temporary read failure"))],
  ["behind", () => Promise.resolve(11)],
] as const)("a lone %s pair", (_kind, first) => {
  it("recovers on one retry at the existing one-second bound, with no second frame", async () => {
    const h = setup([first, () => Promise.resolve(12)]);
    h.scheduler.request();
    await settle();
    await advance(FOLDED_FRAME_REFETCH_MS - 1);
    expect(h.calls()).toBe(1);
    expect(h.applied()).toBe(0);
    expect(h.heldEventRef.current?.hero_probability).toBe(0.4);
    await advance(1);
    expect(h.calls()).toBe(2);
    expect(h.applied()).toBe(1);
    expect(h.heldEventRef.current?.hero_probability).toBe(0.52);
    expect(h.historyRef.current?.aggregate_line?.[0].home_probability).toBe(0.52);
    expect(h.quoteTriggerRef.current).toBeNull();
    await advance(10_000);
    expect(h.calls()).toBe(2);
    h.scheduler.cancel();
  });
});

describe("#10646 bounds", () => {
  it("a persistent failure stops after ONE automatic retry; a new real invalidation renews it", async () => {
    const h = setup([() => Promise.reject(new Error("offline"))]);
    h.scheduler.request();
    await settle();
    await advance(10_000);
    expect(h.calls()).toBe(2);
    expect(h.applied()).toBe(0);
    expect(h.quoteTriggerRef.current).not.toBeNull();
    expect(h.heldEventRef.current?.hero_probability).toBe(0.4);
    h.scheduler.request();
    await settle();
    await advance(10_000);
    expect(h.calls()).toBe(4);
    h.scheduler.cancel();
  });

  it("stale history retries too and never adopts half a pair", async () => {
    const h = setup([() => Promise.resolve(12)]);
    let reads = 0;
    h.context.fetchEventHistory = async (): Promise<History> => ({ event_id: EVENT_ID, blend_edge_pinned: true,
      blend_edge_fold_revision: { 7: ++reads === 1 ? 11 : 12 } });
    h.scheduler.request();
    await settle();
    expect(h.applied()).toBe(0);
    expect(h.historyRef.current).toBeNull();
    expect(h.heldEventRef.current?.hero_probability).toBe(0.4);
    await advance(FOLDED_FRAME_REFETCH_MS);
    expect(reads).toBe(2);
    expect(h.applied()).toBe(1);
    expect(h.heldEventRef.current?.hero_probability).toBe(0.52);
    h.scheduler.cancel();
  });

  it("a slow in-flight pair coalesces a burst into one trailing read and never overlaps detail reads", async () => {
    let resolve!: (rev: number) => void;
    const h = setup([() => new Promise<number>((done) => { resolve = done; }), () => Promise.resolve(12)]);
    h.scheduler.request();
    await advance(1500);
    for (let i = 0; i < 20; i += 1) h.scheduler.request();
    expect(h.calls()).toBe(1);
    resolve(11);
    await settle();
    expect(h.calls()).toBe(2);
    expect(h.maxActive()).toBe(1);
    expect(h.applied()).toBe(1);
    await advance(10_000);
    expect(h.calls()).toBe(2);
    h.scheduler.cancel();
  });
});

describe("#10646 obsolete work retires", () => {
  it("teardown cancels a queued retry, and a late failure after teardown schedules nothing", async () => {
    const h = setup([() => Promise.resolve(11)]);
    h.scheduler.request();
    await settle();
    h.scheduler.cancel();
    await advance(10_000);
    expect(h.calls()).toBe(1);

    let reject!: (e: Error) => void;
    const k = setup([() => new Promise<number>((_, fail) => { reject = fail; })]);
    k.scheduler.request();
    k.scheduler.cancel();
    reject(new Error("late"));
    await settle();
    await advance(10_000);
    expect(k.calls()).toBe(1);
  });

  it("navigation during the read leaves no retry for the old event", async () => {
    let resolve!: (rev: number) => void;
    const h = setup([() => new Promise<number>((done) => { resolve = done; })]);
    h.scheduler.request();
    // The page clears the trigger on render when `eventId` changes.
    (h.context.quoteEventIdRef as { current: number }).current = 8;
    h.quoteTriggerRef.current = null;
    resolve(11);
    await settle();
    await advance(10_000);
    expect(h.calls()).toBe(1);
    expect(h.applied()).toBe(0);
    h.scheduler.cancel();
  });

  it("a queued retry rechecks before it starts: navigation or a terminal held event retire it", async () => {
    const h = setup([() => Promise.resolve(11)]);
    h.scheduler.request();
    await settle();
    (h.context.quoteEventIdRef as { current: number }).current = 8;
    h.quoteTriggerRef.current = null;
    await advance(5000);
    expect(h.calls()).toBe(1);
    expect(h.applied()).toBe(0);
    h.scheduler.cancel();

    const k = setup([() => Promise.resolve(11)]);
    k.scheduler.request();
    await settle();
    k.heldEventRef.current = { ...k.heldEventRef.current!, status: "completed" };
    await advance(5000);
    expect(k.calls()).toBe(1);
    expect(k.applied()).toBe(0);
    k.scheduler.cancel();
  });

  it("an authoritative terminal response is adopted once and owes no retry", async () => {
    const h = setup([() => Promise.resolve(12)]);
    h.context.fetchEvent = async (): Promise<Detail> => ({ id: EVENT_ID, status: "completed",
      hero_probability_source: "final", hero_probability: 1 });
    h.scheduler.request();
    await settle();
    await advance(10_000);
    expect(h.applied()).toBe(1);
    expect(h.quoteTriggerRef.current).toBeNull();
    h.scheduler.cancel();
  });
});

describe("#10646 default scheduler callers are unchanged", () => {
  it("without the predicate a failed read is not retried", async () => {
    let calls = 0;
    const scheduler = createFoldedRefetchScheduler(async () => { calls += 1; throw new Error("offline"); }, 1000);
    scheduler.request();
    await settle();
    await advance(10_000);
    expect(calls).toBe(1);
    scheduler.cancel();
  });

  it("with the predicate, a successful read whose obligation cleared owes nothing", async () => {
    let calls = 0;
    let owed = true;
    const scheduler = createFoldedRefetchScheduler(async () => { calls += 1; owed = false; }, 1000, Date.now, () => owed);
    scheduler.request();
    await settle();
    await advance(10_000);
    expect(calls).toBe(1);
    scheduler.cancel();
  });
});
