/** #10090: run the page's actual push effect over the controller and cache.
 * The network/cache writer is doubled; the effect and fold/chart logic are
 * real. This proves local adoption, not production transport or screen time.
 */
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import { adoptFoldedQuote, applyLiveFrame, frameInvalidatesFoldedBlend } from "@/lib/eventLivePush";
import { appendHeroObservation } from "@/lib/liveChartHistory";
import { canSubscribeEventQuotes } from "@/lib/eventQuoteStream";
import { createLiveStreamController, type LiveStreamFrame, type StreamHandle } from "@/lib/liveStreamController";

const ID = 15323012;
const OLD_AT = "2026-10-08T23:00:00Z";
const NEW_AT = "2026-10-08T23:00:03Z";
const source = (value: number) => ({ value, display_name: "Polymarket", type: "prediction_market", color: "blue",
  updated_at: NEW_AT, price_evidence: { provenance: "clob_authoritative" } });
const held = () => ({ id: ID, sport: "basketball_nba", status: "live", home_score: 41,
  hero_probability_source: "blend", hero_probability: 0.37, hero_probability_away: 0.63,
  hero_probability_observed_at: OLD_AT, blend_fold_revision: { 15323012: 3796, 15326779: 63 },
  win_probability_sources: { retired: source(0.2) } });
const quote = () => ({ event_id: ID, status: "live", sport: "basketball_nba",
  hero_probability: 0.43, hero_probability_away: 0.49, hero_probability_source: "blend",
  hero_probability_observed_at: NEW_AT, hero_sportsbook_count: 0, hero_settled_result: null,
  blend_fold_revision: { 15323012: 3846, 15326779: 63 }, win_probability_sources: { polymarket: source(0.47) } });
const raw = (): LiveStreamFrame => ({ event_id: ID, p: 0.534, source: "kalshi", source_value: 0.6,
  updated_at: NEW_AT, rev: { 15323012: 3846 }, status: "live" });

const page = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const tree = ts.createSourceFile("page.tsx", page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let effect: string | undefined;
function visit(node: ts.Node) {
  if (ts.isCallExpression(node) && node.expression.getText(tree) === "useEffect" &&
      node.arguments[1]?.getText(tree) === "[liveFrame, refreshEvent, eventId, foldedRefetch]") {
    effect = node.arguments[0].getText(tree);
  }
  ts.forEachChild(node, visit);
}
visit(tree);
if (!effect) throw new Error("page push effect missing");
const effectScript = new vm.Script(ts.transpileModule(`(${effect})`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText);

function harness() {
  let cache = held();
  const reads = jest.fn();
  const mutations = jest.fn((update: (prev: typeof cache) => typeof cache, options: unknown) => {
    expect(options).toEqual({ revalidate: false }); cache = update(cache);
  });
  let chart = { aggregate_line: [{ timestamp: OLD_AT, home_probability: 0.37 }] };
  const context: Record<string, unknown> = {
    eventId: ID, heldEventRef: { current: cache }, foldedRefetch: { request: reads },
    quoteTriggerRef: { current: null }, latestLiveFrameRef: { current: null },
    refreshEvent: mutations, setLastRefresh: jest.fn(), Date,
    adoptFoldedQuote, applyLiveFrame, frameInvalidatesFoldedBlend, canSubscribeEventQuotes,
  };
  const listeners = new Map<string, (e: unknown) => void>();
  const stream: StreamHandle = { readyState: 1, close: () => {},
    addEventListener: (name, listener) => { listeners.set(name, listener); } };
  const controller = createLiveStreamController({ open: () => stream, now: () => 1,
    onDeliveringChange: () => {}, onFrame: frame => {
      context.liveFrame = frame;
      (context.heldEventRef as { current: typeof cache }).current = cache;
      effectScript.runInNewContext(context)();
      chart = appendHeroObservation(chart, cache)!;
    } });
  controller.start();
  return { reads, mutations, cache: () => cache, chart: () => chart,
    emit: (name: string, frame: LiveStreamFrame) => listeners.get(name)!({ data: JSON.stringify(frame) }) };
}

test("promised raw row stays refused, then same raw revision delivers full fold and chart without REST", () => {
  const h = harness();
  h.emit("probability", { ...raw(), folded_quote_pending: true });
  expect(h.cache()).toEqual(held());
  expect(h.reads).not.toHaveBeenCalled();
  h.emit("folded_probability", { ...raw(), folded_quote: { ...quote(), home_score: 999, id: 7 } });
  expect(h.reads).not.toHaveBeenCalled();
  expect(h.mutations).toHaveBeenCalledTimes(1);
  const { event_id, ...fields } = quote();
  expect(event_id).toBe(ID);
  expect(h.cache()).toEqual({ ...held(), ...fields });
  expect(h.cache().hero_probability).toBe(0.43);
  expect(h.chart().aggregate_line.at(-1)).toEqual({ timestamp: NEW_AT, home_probability: 0.43 });
});

test("legacy raw notification still reads detail; explicit null cannot recursively defer", () => {
  const h = harness();
  h.emit("probability", raw());
  expect(h.reads).toHaveBeenCalledTimes(1);
  h.emit("probability", { ...raw(), folded_quote_pending: true });
  expect(h.reads).toHaveBeenCalledTimes(1);
  h.emit("folded_probability", { ...raw(), folded_quote_pending: true, folded_quote: null });
  expect(h.reads).toHaveBeenCalledTimes(2);
  expect(h.mutations).not.toHaveBeenCalled();
});

test("same and older full vectors are consumed without mutation or detail reads", () => {
  const h = harness();
  h.emit("folded_probability", { ...raw(), folded_quote: quote() });
  h.emit("folded_probability", { ...raw(), folded_quote: quote() });
  h.emit("folded_probability", { ...raw(), folded_quote: { ...quote(),
    blend_fold_revision: held().blend_fold_revision, hero_probability: 0.9 } });
  expect(h.reads).not.toHaveBeenCalled();
  expect(h.mutations).toHaveBeenCalledTimes(1);
  expect(h.cache().hero_probability).toBe(0.43);
});

test.each([
  null,
  { ...quote(), event_id: 7 },
  { ...quote(), hero_probability: Infinity },
  { ...quote(), hero_probability_observed_at: undefined },
  { ...quote(), win_probability_sources: [] },
  { ...quote(), blend_fold_revision: { 15323012: 3846 } },
  { ...quote(), blend_fold_revision: { 15323012: 3846, 15326779: 62 } },
  { ...quote(), status: "completed" },
])("unavailable/malformed/incomparable/phase projection keeps raw fallback: %p", projection => {
  const h = harness();
  h.emit("folded_probability", { ...raw(), folded_quote: projection });
  expect(h.cache()).toEqual(held());
  expect(h.mutations).not.toHaveBeenCalled();
  expect(h.reads).toHaveBeenCalledTimes(1);
});

test("unknown observation clock stays null; no source stamp or wall clock is invented", () => {
  const h = harness();
  h.emit("folded_probability", { ...raw(), folded_quote: { ...quote(), hero_probability_observed_at: null,
    hero_probability_away: null } });
  expect(h.cache().hero_probability_observed_at).toBeNull();
  expect(h.cache().hero_probability_away).toBeNull();
  expect(h.chart().aggregate_line).toEqual([{ timestamp: OLD_AT, home_probability: 0.37 }]);
});
