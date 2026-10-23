/** #10090 attempt149: run the page's actual `historyData` memo over the real
 * chart helpers. A recovered source reading stays on the chart at its own time
 * through a reversal and the finish, never becomes a blend point, and does not
 * disturb the blend-edge pin. This proves the memo, not a rendered page.
 */
import fs from "fs";
import path from "path";
import vm from "vm";
import ts from "typescript";
import * as chart from "@/lib/liveChartHistory";
import * as pin from "@/lib/chartEdgePin";

const page = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");
const tree = ts.createSourceFile("page.tsx", page, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let memo: string | undefined;
function visit(node: ts.Node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(tree) === "historyData" &&
      node.initializer && ts.isCallExpression(node.initializer)) {
    memo = node.initializer.arguments[0].getText(tree);
  }
  ts.forEachChild(node, visit);
}
visit(tree);
if (!memo) throw new Error("page historyData memo missing");
const PIN_LINE = "pushed !== observed ? pushed : pinChartEdgeToHero(observed, event)";
const compile = (text: string) =>
  new vm.Script(ts.transpileModule(`(${text})`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText);
const actual = compile(memo);

type Point = { timestamp: string; home_probability: number | null; game_state?: unknown };
type History = {
  event_id: number; history_fold_revision: Record<string, number>;
  win_prob_history: { polymarket: Point[] }; aggregate_line?: Point[];
  blend_edge_pinned?: boolean; blend_edge_observed_at?: string;
};
const at = (n: number) => new Date(Date.UTC(2026, 9, 19, 12, 0, 0) + n * 1000).toISOString();
const served = (): History => ({ event_id: 1, history_fold_revision: { 1: 3 },
  win_prob_history: { polymarket: [{ timestamp: at(0), home_probability: 0.66, away_probability: 0.34 } as Point] } });
const detail = (rev: number, value: number, time: number, status = "live") => ({
  id: 1, status, hero_probability: 0.67, hero_probability_source: "blend",
  hero_probability_observed_at: at(time) as string | null | undefined, blend_fold_revision: { 1: rev } as Record<string, number>,
  win_probability_sources: { polymarket: { value, updated_at: at(time) } } as Record<string, unknown>,
  completed_at: undefined as string | undefined,
});
const frame = (rev: number, value: number, time: number) => ({
  timestamp: at(time), home_probability: 0.63, source: "polymarket", source_probability: value, rev: { 1: rev } });

function rig(script = actual) {
  const ref = { current: null };
  return (event: unknown, chartPoints: unknown[] = [], history: History = served(), quoteEligible = true, eventId = 1) =>
    script.runInNewContext({ ...chart, ...pin, eventId, chartPoints, event, servedHistory: history,
      quoteEligible, admittedChartRef: ref })() as History;
}
const has = (h: History, v: number, t: number) =>
  h.win_prob_history.polymarket.some((p) => p.home_probability === v && p.timestamp === at(t));

describe("#10090 attempt149 recovered source continuity (actual page memo)", () => {
  it("retains a recovered excursion across a live reversal without making it a blend value", () => {
    const render = rig();
    expect(has(render(detail(3, 0.78, 1)), 0.78, 1)).toBe(true);
    const h = render(detail(4, 0.66, 2), [frame(4, 0.66, 2)]);
    expect(has(h, 0.78, 1)).toBe(true);
    expect(has(h, 0.66, 2)).toBe(true);
    expect((h.aggregate_line ?? []).some((p) => p.home_probability === 0.78)).toBe(false);
  });

  it("keeps the drawn pre-finish excursion at its original clock and admits nothing new at the finish", () => {
    const render = rig();
    render(detail(3, 0.78, 1));
    render(detail(4, 0.66, 2), [frame(4, 0.66, 2)]);
    const final = { ...detail(5, 1, 3, "completed"), completed_at: at(3) };
    const h = render(final, [frame(4, 0.66, 2)], served(), false);
    expect(has(h, 0.78, 1)).toBe(true);
    expect(has(h, 1, 3)).toBe(false);
    expect(h.aggregate_line).toBeUndefined();
  });

  it("keeps an earlier excursion but ends the series at a marked withdrawal", () => {
    const render = rig();
    render(detail(3, 0.78, 1));
    const h = served();
    h.history_fold_revision = { 1: 4 };
    h.win_prob_history.polymarket.push({ timestamp: at(2), home_probability: null, game_state: { live_source_withdrawal: true } });
    const d = detail(4, 0.78, 1);
    d.win_probability_sources = {};
    const out = render(d, [], h);
    expect(has(out, 0.78, 1)).toBe(true);
    expect(out.win_prob_history.polymarket.at(-1)?.home_probability).toBeNull();
  });

  it("does not carry the source bank across navigation or a folded membership", () => {
    const nav = rig();
    nav(detail(3, 0.78, 1));
    const h = served();
    h.event_id = 2;
    h.history_fold_revision = { 2: 4 };
    const d = { ...detail(4, 0.66, 2), id: 2, blend_fold_revision: { 2: 4 } };
    expect(has(nav(d, [], h, true, 2), 0.78, 1)).toBe(false);
    const fold = rig();
    fold(detail(3, 0.78, 1));
    const folded = { ...detail(4, 0.66, 2), blend_fold_revision: { 1: 4, 2: 4 } };
    expect(has(fold(folded), 0.78, 1)).toBe(false);
  });

  it("lets a later authoritative reading at the same time win", () => {
    const render = rig();
    render(detail(3, 0.78, 1));
    const h = served();
    h.history_fold_revision = { 1: 4 };
    h.win_prob_history.polymarket.push({ timestamp: at(1), home_probability: 0.75 });
    expect(has(render(detail(4, 0.75, 1), [], h), 0.78, 1)).toBe(false);
  });

  it("lets a served reading beat the banked one at the same time after the detail moved on", () => {
    const render = rig();
    expect(has(render(detail(3, 0.78, 1)), 0.78, 1)).toBe(true);
    const h = served();
    h.history_fold_revision = { 1: 4 };
    h.win_prob_history.polymarket.push({ timestamp: at(1), home_probability: 0.75 });
    const out = render(detail(4, 0.7, 2), [], h);
    expect(has(out, 0.75, 1)).toBe(true);
    expect(has(out, 0.7, 2)).toBe(true);
    expect(has(out, 0.78, 1)).toBe(false);
  });

  it("bounds the source bank at 720 observations, newest kept", () => {
    let bank: chart.AdmittedChartFrames | null = null;
    for (let i = 1; i <= 750; i++) {
      const d = detail(i + 3, 0.5 + i / 10000, i);
      bank = chart.admitCurrentSourceObservations(
        chart.admitChartFrames(1, [], d as never), bank, served() as never, d as never);
    }
    expect(bank?.sourcePoints?.length).toBe(720);
    expect(bank?.sourcePoints?.at(-1)?.timestamp).toBe(at(750));
  });

  // Source-only augmentation must not impersonate a pushed blend change: the
  // synthetic aggregate edge is still pinned to the hero (review 149 finding).
  const pinned = () => {
    const h = served();
    h.history_fold_revision = { 1: 2 };
    h.aggregate_line = [{ timestamp: at(10), home_probability: 0.6 }];
    h.blend_edge_pinned = true;
    h.blend_edge_observed_at = at(1);
    return h;
  };
  it.each([["present", "keep"], ["absent", "delete"], ["null", "null"]])(
    "a source-only extension keeps the blend pin when the hero clock is %s",
    (_label, clock) => {
      const d = detail(3, 0.78, 1);
      if (clock === "delete") delete d.hero_probability_observed_at;
      if (clock === "null") d.hero_probability_observed_at = null;
      const joined = rig()(d, [], pinned());
      expect(joined.aggregate_line?.at(-1)?.home_probability).toBe(0.67);
      expect(has(joined, 0.78, 1)).toBe(true);
    },
  );

  it("the pre-correction pin comparison loses the pin on the same input (control)", () => {
    expect(memo).toContain(PIN_LINE);
    const regressed = compile(memo!.replace(PIN_LINE,
      "pushed !== servedHistory ? pushed : pinChartEdgeToHero(servedHistory, event)"));
    const joined = rig(regressed)(detail(3, 0.78, 1), [], pinned());
    expect(joined.aggregate_line?.at(-1)?.home_probability).toBe(0.6);
  });

  it("a genuinely pushed blend keeps its own value rather than the older hero", () => {
    const h = served();
    h.history_fold_revision = { 1: 2 };
    h.aggregate_line = [{ timestamp: at(0), home_probability: 0.6 }];
    h.blend_edge_pinned = true;
    const out = rig()(detail(4, 0.66, 2), [frame(4, 0.66, 2)], h);
    expect(out.aggregate_line?.at(-1)?.home_probability).toBe(0.63);
  });
});

// Attempt155: admission happens at the accepted pair boundary before replay
// replaces an older source value. Retain the existing bank's newer observations.
describe("Attempt155 recovered pair source admission", () => {
  const bank = () => chart.admitCurrentSourceObservations(
    chart.admitChartFrames(1, [], { ...detail(4, 0.66, 2), win_probability_sources: { polymarket: { updated_at: at(2) } } }), null, served() as never, detail(4, 0.66, 2));
  it("retains both revisions without adding a blend frame or moving the current endpoint", () => {
    const original = bank();
    const next = chart.admitRecoveredSourceObservations(original, served() as never, detail(3, 0.78, 1), detail(4, 0.66, 2));
    expect(next?.sourcePoints?.map(p => [p.timestamp,p.source_probability])).toEqual([[at(1),0.78],[at(2),0.66]]);
    expect(next?.points).toBe(original.points);
    expect(next?.foldRevision).toEqual({1:4});
  });
  it.each(["terminal", "navigation", "fold", "regressed", "unknown"])('refuses %s adoption without changing the bank', kind => {
    const original = bank();
    const adopted = detail(4, 0.66, 2);
    if (kind === "terminal") { adopted.status = "completed"; adopted.completed_at = at(2); }
    if (kind === "navigation") adopted.id = 2;
    if (kind === "fold") adopted.blend_fold_revision = {1:4,2:4};
    if (kind === "regressed") adopted.blend_fold_revision = {1:2};
    if (kind === "unknown") adopted.blend_fold_revision = {};
    expect(chart.admitRecoveredSourceObservations(original, served() as never, detail(3, 0.78, 1), adopted)).toBe(original);
  });
  it("a newer authoritative history reading still defeats the recovered source at the same clock", () => {
    const h = served();
    const next = chart.admitRecoveredSourceObservations(bank(), h as never, detail(3, 0.78, 1), detail(4, 0.66, 2));
    h.win_prob_history.polymarket.push({timestamp:at(1),home_probability:0.75});
    h.history_fold_revision = {1:4};
    const rendered = chart.appendAdmittedSourceObservations(h as never, next, detail(4,0.66,2)) as unknown as History;
    expect(has(rendered,0.75,1)).toBe(true);
    expect(has(rendered,0.78,1)).toBe(false);
  });
  it("repeated recoveries remain within the existing 720-observation limit", () => {
    let current = bank();
    for (let n=5; n<740; n++) {
      const adopted = { ...detail(n+1,0.66,n+1), win_probability_sources: { polymarket: { value: 0.66, updated_at: at(n+1) } } };
      current = chart.admitRecoveredSourceObservations(current, served() as never, detail(n,0.78,n), adopted)!;
      // As on the page, the next memo admits the adopted current reading
      // against the retained served history; the pair adds only recovered ones.
      current = chart.admitCurrentSourceObservations(chart.admitChartFrames(1,[],adopted), current, served() as never, adopted);
    }
    expect(current.sourcePoints?.length).toBe(720);
    expect(current.sourcePoints?.at(-1)?.timestamp).toBe(at(740));
  });
});
