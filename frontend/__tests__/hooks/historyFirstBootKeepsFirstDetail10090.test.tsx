/**
 * #10090 — MOUNTED: a history body that lands before the first detail read.
 *
 * Production, event 15327809 (05:17:16Z): the since-start history body arrived
 * 1.1 ms before the first detail body, the history-edge effect wrote the event
 * cache while it held nothing, and swr discarded the in-flight first read — a
 * later mutation post-dates it, even one whose updater returns `undefined`.
 * The page printed "Couldn't reach the server", with no headline and no quote
 * stream, until the next 32 s poll answered.
 *
 * WHAT IS REAL: react-dom over `helpers/minimalDom`, the installed `swr` keyed
 * as the page keys detail and history, the real `fetchEventWithLiveFrame`
 * reconcile, the real edge helpers, and the page's OWN history-edge effect —
 * its callback, its dependency list and the `holdsHeadline` it reads — lifted
 * from `app/events/[id]/page.tsx` with the TypeScript AST and evaluated inside
 * the component every render, so nothing here is a hand copy that can drift.
 *
 * WHAT IS SIMPLIFIED: the boot fetchers are plain deferreds (no poll cadence,
 * so nothing but the test answers a read), `foldedRefetch` only counts its
 * requests, and the render prints the cached numbers rather than the hero.
 * The real-page replay of the captured bodies is the acceptance; this pins the
 * class in CI.
 */
import "../helpers/minimalDom";
import React, { act, useEffect, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import useSWR, { SWRConfig } from "swr";

import { fetchEventWithLiveFrame } from "../../lib/reconcileEventPoll";
import {
  adoptNewerBlendEdge,
  edgeInvalidatesHeldBlend,
  servedBlendEdgeObservation,
  type BlendEdgeObservation,
} from "../../lib/blendObservationClock";

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const TREE = ts.createSourceFile("page.tsx", PAGE, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

function find<T>(pick: (n: ts.Node) => T | undefined): T | undefined {
  let found: T | undefined;
  const visit = (n: ts.Node) => { found ??= pick(n); ts.forEachChild(n, visit); };
  visit(TREE);
  return found;
}
const script = (source: string) => new vm.Script(ts.transpileModule(`(${source})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText);

// The one `useEffect` whose callback reads the served history's pinned edge.
const EDGE_EFFECT = find((n) => {
  if (!ts.isCallExpression(n) || n.expression.getText(TREE) !== "useEffect") return undefined;
  const [callback, deps] = n.arguments;
  if (!callback || !deps || !ts.isArrowFunction(callback) ||
      !callback.body.getText(TREE).includes("servedBlendEdgeObservation(servedHistory)")) return undefined;
  return { callback: script(callback.getText(TREE)), deps: script(deps.getText(TREE)) };
});
const HOLDS_HEADLINE = find((n) => (ts.isVariableDeclaration(n) && n.name.getText(TREE) === "holdsHeadline" && n.initializer)
  ? script(n.initializer.getText(TREE)) : undefined);

// ── network ─────────────────────────────────────────────────────────────────
type Detail = {
  id: number; status: string; hero_probability: number; hero_probability_source: string;
  hero_probability_observed_at: string; blend_fold_revision: Record<string, number>;
};
type History = {
  event_id: number; blend_edge_pinned: boolean; blend_edge_observed_at: string;
  blend_edge_fold_revision: Record<string, number>; aggregate_line: { home_probability: number }[];
};
class Deferred<T> {
  promise: Promise<T>;
  resolve!: (v: T) => void;
  constructor() { this.promise = new Promise<T>((res) => { this.resolve = res; }); }
}
type Net = { details: Deferred<Detail>[]; histories: Deferred<History>[] };

const ID = 15327809;
// The captured boot pair: detail and history at the SAME fold revision.
const detail = (): Detail => ({
  id: ID, status: "live", hero_probability: 0.296365, hero_probability_source: "blend",
  hero_probability_observed_at: "2026-10-12T05:17:53.568308+00:00", blend_fold_revision: { [ID]: 3809 },
});
const history = (opts: { pinned?: boolean; rev?: number; p?: number } = {}): History => ({
  event_id: ID, blend_edge_pinned: opts.pinned ?? true,
  blend_edge_observed_at: opts.rev && opts.rev > 3809 ? "2026-10-12T05:17:57.451111+00:00" : "2026-10-12T05:17:53.568308+00:00",
  blend_edge_fold_revision: { [ID]: opts.rev ?? 3809 },
  aggregate_line: [{ home_probability: 0.5 }, { home_probability: opts.p ?? 0.296365 }],
});
const newerEdge = () => history({ rev: 3810, p: 0.31 });

// ── the harness: the page's boot wiring around its history-edge effect ──────
function BootPage({ net, fetcherSeesEdge, folds }: { net: Net; fetcherSeesEdge: boolean; folds: { n: number } }) {
  const latestBlendEdgeRef = useRef<BlendEdgeObservation | null>(null);
  const heldEventRef = useRef<Detail | undefined>(undefined);
  const { data: event, mutate: refreshEvent } = useSWR(["event", ID], () => fetchEventWithLiveFrame(
    () => { const d = new Deferred<Detail>(); net.details.push(d); return d.promise; },
    () => null,
    // `false` stands in for production's passive-effect window: the detail
    // body's task ran its fetcher before the history render's effect had
    // written the ref (the two bodies were 1.1 ms apart).
    () => (fetcherSeesEdge ? latestBlendEdgeRef.current : null),
    () => heldEventRef.current,
  ), { dedupingInterval: 0 });
  heldEventRef.current = event;
  const { data: servedHistory } = useSWR(["history", ID, false], () => {
    const d = new Deferred<History>(); net.histories.push(d); return d.promise;
  }, { dedupingInterval: 0 });
  const foldedRefetch = useRef({ request: () => { folds.n += 1; } }).current;
  // ── app/events/[id]/page.tsx — the effect as the page writes it ───────────
  const scope: Record<string, unknown> = {
    event, servedHistory, refreshEvent, foldedRefetch, latestBlendEdgeRef, heldEventRef,
    servedBlendEdgeObservation, edgeInvalidatesHeldBlend, adoptNewerBlendEdge,
    pairJournalRef: { current: null }, // #10090 G1: no paired read in flight here
  };
  if (HOLDS_HEADLINE) scope.holdsHeadline = HOLDS_HEADLINE.runInNewContext(scope);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(EDGE_EFFECT!.callback.runInNewContext(scope), EDGE_EFFECT!.deps.runInNewContext(scope));

  if (!event) return <>no headline</>;
  const chart = servedHistory?.aggregate_line.at(-1)?.home_probability;
  return <>{`${Math.round(event.hero_probability * 100)}|${event.blend_fold_revision[ID]}|${chart === undefined ? "-" : Math.round(chart * 100)}`}</>;
}

async function settle() {
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
const doc = document as unknown as { createElement: (t: string) => Element; body: { appendChild: (c: unknown) => void } };

async function mount(fetcherSeesEdge = true) {
  const net: Net = { details: [], histories: [] };
  const folds = { n: 0 };
  const container = doc.createElement("div");
  doc.body.appendChild(container);
  const root: Root = createRoot(container);
  await act(async () => {
    root.render(
      <SWRConfig value={{ provider: () => new Map(), revalidateOnFocus: false, revalidateOnReconnect: false }}>
        <BootPage net={net} fetcherSeesEdge={fetcherSeesEdge} folds={folds} />
      </SWRConfig>,
    );
  });
  await settle();
  expect(net.details).toHaveLength(1);
  expect(net.histories).toHaveLength(1);
  return {
    net, folds,
    read: () => container.textContent ?? "",
    async answer(first: "history" | "detail", h: History) {
      const d = detail();
      if (first === "history") { net.histories[0].resolve(h); await settle(); net.details[0].resolve(d); }
      else { net.details[0].resolve(d); await settle(); net.histories[0].resolve(h); }
      await settle();
    },
    unmount: () => act(() => { root.unmount(); }),
  };
}

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

// ─────────────────────────────────────────────────────────────────────────────
describe("structural pin: the harness found the page's history-edge effect", () => {
  it("lifts exactly one effect, and it writes the event cache through adoptNewerBlendEdge", () => {
    expect(EDGE_EFFECT).toBeDefined();
    expect(PAGE.match(/servedBlendEdgeObservation\(servedHistory\)/g)).toHaveLength(1);
    expect(PAGE).toMatch(/refreshEvent\(\(prev\) => adoptNewerBlendEdge\(prev, edge\), \{ revalidate: false \}\);/);
  });
});

describe("#10090 mounted: the first detail read survives a history body that lands first", () => {
  it("history first, detail 1 tick later: the headline is the first read, with no second read", async () => {
    const page = await mount();
    await page.answer("history", history());
    expect(page.read()).toBe("30|3809|30");
    expect(page.net.details).toHaveLength(1);
    await page.unmount();
  });

  it("history first with a NEWER pinned edge: the first headline is already the edge", async () => {
    const page = await mount();
    await page.answer("history", newerEdge());
    expect(page.read()).toBe("31|3810|31");
    expect(page.net.details).toHaveLength(1);
    await page.unmount();
  });

  it("the edge reached the ref only after the first read's fetcher returned: the page still adopts it once held", async () => {
    const page = await mount(false);
    await page.answer("history", newerEdge());
    expect(page.read()).toBe("31|3810|31");
    expect(page.net.details).toHaveLength(1);
    await page.unmount();
  });

  it("an incomparable pinned edge that lands first asks for a fresh fold once the headline is held", async () => {
    const page = await mount(false);
    const twin = history({ rev: 3810, p: 0.31 });
    twin.blend_edge_fold_revision = { [ID]: 3810, 99: 1 };
    await page.answer("history", twin);
    expect(page.read()).toBe("30|3809|31");
    expect(page.folds.n).toBe(1);
    await page.unmount();
  });
  it("history first with an OLDER pinned edge: the first read stands, never rolled back", async () => {
    const page = await mount();
    await page.answer("history", history({ rev: 3808, p: 0.2 }));
    expect(page.read()).toBe("30|3809|20");
    await page.unmount();
  });
});

describe("#10090 mounted controls (unchanged behaviour)", () => {
  it("detail first, then history: the headline is the first read", async () => {
    const page = await mount();
    await page.answer("detail", history());
    expect(page.read()).toBe("30|3809|30");
    await page.unmount();
  });

  it("detail first, then a NEWER pinned edge: the held headline moves to the edge", async () => {
    const page = await mount();
    await page.answer("detail", newerEdge());
    expect(page.read()).toBe("31|3810|31");
    await page.unmount();
  });

  it("history first WITHOUT a pinned edge: nothing is written and the first read lands", async () => {
    const page = await mount();
    await page.answer("history", history({ pinned: false }));
    expect(page.read()).toBe("30|3809|30");
    await page.unmount();
  });

  it("detail first, then an OLDER pinned edge: the held headline is never rolled back", async () => {
    const page = await mount();
    await page.answer("detail", history({ rev: 3808, p: 0.2 }));
    expect(page.read()).toBe("30|3809|20");
    await page.unmount();
  });
});
