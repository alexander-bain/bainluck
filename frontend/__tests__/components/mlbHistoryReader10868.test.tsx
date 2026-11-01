/** @jest-environment jsdom */
/**
 * #10868 Full chart — `MlbHistoryReader`: the baseball page's win-probability
 * history at full size, in the EXISTING `SoccerMatchReader` shell (unchanged,
 * `kind="history"`), drawing the page's own headline matrix (only while its
 * phase agrees) and the SAME history through `HockeyJourneyHistoryChart
 * layout="expanded"`; plus the shared compact context, moved verbatim into
 * the verdict-free `MlbReaderContext` (the run reader re-exports its type).
 *
 * SHIP: a baseball fan can read the probability journey at full size, with
 * the same game context and honest missing-history treatment.
 *
 * TEST HOST (CONSTRUCTED, test-only, NOT the page binding): `FullChartHost`
 * draws the page's inline chart, an opener, a status line and a focusable
 * local anchor, and the reader while open — the shape a later page binding
 * will take. Nothing here mounts the reader on the page.
 *
 * INPUTS, labelled per test:
 *   - REAL — `../lib/mlbGame10868.fixtures.json` (White Sox at Astros
 *     15321836, final 3–7) through the ACTUAL `buildMlbGame`, drawn from the
 *     page's away-first presentation copies (`inDisplayOrder`, as
 *     `MlbGamePage` makes them); `../lib/mlbRunTotals10868.fixtures.json` for
 *     the run reader's unchanged-behaviour check. Neither fixture is edited.
 *   - CONSTRUCTED — every host value and clock (the final host's displayed
 *     3–7 equals the retained row); the live event (native `liveEdits`); the
 *     caller's context strings; a missing and a foreign history; a phase the
 *     headline does not match; the page scroll offset.
 *
 * jsdom implements no dialog behaviour; `showModal` / `close` are stubbed as
 * `soccerMatchReader10868.test.tsx` stubs them (state only). These tests read
 * the computed SVG attributes and the DOM, never pixels: browser fit,
 * modality, accessibility, native, device and TestFlight stay unverified, and
 * no native pixel parity is claimed for the 360 px plot.
 */
import React from "react";
import fs from "node:fs";
import path from "node:path";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import fixtures from "../lib/mlbGame10868.fixtures.json";
import runTotalsFixture from "../lib/mlbRunTotals10868.fixtures.json";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";
import type { GameMarketsResponse } from "@/lib/api";
import type { HockeyJourneyHeadline, HockeyJourneyHistory, HockeyJourneyPhase, HockeyJourneyTeam } from "@/lib/eventPage10868/hockeyJourneyTypes";
import { HISTORY_WORDS } from "@/lib/eventPage10868/hockeyJourneyHistory";
import { buildMlbGame, type MlbGameHost, type MlbGameModel, type MlbGameView } from "@/lib/eventPage10868/mlbGame";
import { mlbFinalTotals, mlbRunLines } from "@/lib/eventPage10868/mlbRunTotals";
import MlbHistoryReader from "@/components/event/eventpage10868/MlbHistoryReader";
import { RunReaderContext, type MlbRunReaderContext } from "@/components/event/eventpage10868/MlbReaderContext";
import MlbRunTotalsReader, {
  MLB_RUN_READER_WORDS,
  type MlbRunReaderContext as RunReaderContextFromOldPath,
} from "@/components/event/eventpage10868/MlbRunTotalsReader";
import HockeyJourneyHistoryChart from "@/components/event/eventpage10868/HockeyJourneyHistoryChart";
import { inDisplayOrder } from "@/components/event/eventpage10868/FootballJourneySection";
import { SOCCER_READER_WORDS } from "@/components/event/eventpage10868/SoccerMatchReader";

// ─── Inputs ────────────────────────────────────────────────────────────────

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
/** A deep copy with keys replaced — a TEST MUTATION (CONSTRUCTED). */
const mutate = <T,>(x: T, patch: Record<string, unknown>): T => ({ ...clone(x), ...patch });

const finalDetail = fixtures.finalDetail as unknown as EventDetailResponse;
const finalHistory = fixtures.finalHistory as unknown as EventHistoryResponse;
const finalMarkets = fixtures.finalMarkets as unknown as GameMarketsResponse;
const FINAL_NOW = Date.parse("2026-10-11T04:57:23.592725Z");
const LIVE_NOW = Date.parse("2026-10-01T00:16:30Z");
const LIVE_OBSERVED = "2026-10-01T00:15:57.061753Z";
const INLINE_PX = 230;
const EXPANDED_PX = 360;
const COLORS = { home: "var(--series-1)", away: "var(--series-2)" };

/** CONSTRUCTED host: the displayed final pair equal to the retained row (3–7). */
const finalHost: MlbGameHost = {
  nowMs: FINAL_NOW,
  hero: null,
  probabilityObservedAt: null,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 7, observedAt: null },
  projectedFinal: null,
};
/** CONSTRUCTED: native `liveEdits` over the real final, with a displayed 3–6. */
const liveDetail = mutate(finalDetail, {
  status: "live",
  completed_at: null,
  hero_settled_result: null,
  hero_probability: null,
  hero_probability_away: null,
  hero_probability_source: null,
});
const liveHost: MlbGameHost = {
  nowMs: LIVE_NOW,
  hero: { homeProb: 0.001, awayProb: 0.999, homePct: 0, awayPct: 100, probSourceLabel: null },
  probabilityObservedAt: LIVE_OBSERVED,
  deliveryInterrupted: false,
  liveClaimUnbacked: false,
  score: { home: 3, away: 6, observedAt: LIVE_OBSERVED },
  projectedFinal: { home: 4, away: 7 },
};

function view(event: EventDetailResponse, host: MlbGameHost, history: EventHistoryResponse | null = finalHistory): MlbGameView {
  const m: MlbGameModel = buildMlbGame({ event, history, gameMarkets: finalMarkets, host });
  if (m.kind !== "game") throw new Error("refused");
  return m;
}
/** The page's away-first presentation copies, made exactly as `MlbGamePage` makes them. */
function pageCopies(v: MlbGameView): { headline: HockeyJourneyHeadline; history: HockeyJourneyHistory; phase: HockeyJourneyPhase } {
  return {
    headline: { ...v.headline, matrix: { ...v.headline.matrix, rows: inDisplayOrder(v.headline.matrix.rows) } },
    history: { ...v.history, series: inDisplayOrder(v.history.series) },
    phase: v.phase,
  };
}
const shown = (team: HockeyJourneyTeam) => team.short ?? team.name;
/** CONSTRUCTED caller strings, as the page would pass them (away first). */
const contextFor = (headline: HockeyJourneyHeadline, score: MlbRunReaderContext["score"]): MlbRunReaderContext => ({
  away: shown(headline.away),
  home: shown(headline.home),
  score,
  state: headline.state,
});

const FINAL = pageCopies(view(finalDetail, finalHost));
const FINAL_CONTEXT = contextFor(FINAL.headline, { away: "7", home: "3" });

// ─── The test host (CONSTRUCTED, test-only) ────────────────────────────────

interface HostProps {
  headline: HockeyJourneyHeadline;
  phase: HockeyJourneyPhase;
  history: HockeyJourneyHistory;
  context: MlbRunReaderContext;
  /** CONSTRUCTED: false = the opener has left the page. */
  opener?: boolean;
  /** CONSTRUCTED: a new event or phase closes the reader (the caller's rule). */
  scope?: string;
}
const log = { closes: 0, unavailable: 0 };

function FullChartHost({ headline, phase, history, context, opener = true, scope = "mlb:15321836:final" }: HostProps) {
  const [state, setState] = React.useState({ scope, open: false, unavailable: false });
  if (state.scope !== scope) setState({ scope, open: false, unavailable: false });
  const now = state.scope === scope ? state : { scope, open: false, unavailable: false };
  const entry = React.useRef<HTMLButtonElement>(null);
  const anchor = React.useRef<HTMLDivElement>(null);
  return (
    <section data-test-page="">
      <div ref={anchor} tabIndex={-1} data-test-anchor="">
        <HockeyJourneyHistoryChart history={history} colors={COLORS} />
        {opener && (
          <button ref={entry} type="button" disabled={now.open} onClick={() => setState((s) => ({ ...s, open: true, unavailable: false }))} data-test-entry="">
            {SOCCER_READER_WORDS.fullChart}
          </button>
        )}
        <p role="status" data-test-status="">
          {now.unavailable ? SOCCER_READER_WORDS.fullSizeUnavailable : null}
        </p>
      </div>
      {now.open && (
        <MlbHistoryReader
          headline={headline}
          phase={phase}
          history={history}
          colors={COLORS}
          context={context}
          onClose={() => {
            log.closes += 1;
            setState((s) => ({ ...s, open: false }));
          }}
          onUnavailable={() => {
            log.unavailable += 1;
            setState((s) => ({ ...s, open: false, unavailable: true }));
          }}
          returnTo={() => {
            const own = entry.current;
            return own?.isConnected && !own.disabled ? own : anchor.current;
          }}
        />
      )}
    </section>
  );
}

// ─── Harness ───────────────────────────────────────────────────────────────

let host: HTMLDivElement;
let root: Root;
let showModalCalls: number;
/** CONSTRUCTED jsdom dialog stub (see header): state only, no browser modality. */
function stubShowModal(this: HTMLDialogElement) {
  showModalCalls += 1;
  this.setAttribute("open", "");
}
let pageScroll: jest.SpyInstance;
const dialogProto = HTMLDialogElement.prototype as unknown as { showModal?: () => void; close?: () => void };

beforeEach(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  showModalCalls = 0;
  log.closes = 0;
  log.unavailable = 0;
  dialogProto.showModal = stubShowModal;
  dialogProto.close = function (this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
  pageScroll = jest.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  // CONSTRUCTED: the page is scrolled 640 px down when the reader opens.
  window.scrollY = 640;
  document.body.style.overflow = "";
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  delete dialogProto.showModal;
  delete dialogProto.close;
  window.scrollY = 0;
  jest.restoreAllMocks();
});

const show = (props: HostProps) => act(() => root.render(<FullChartHost {...props} />));
const showAndSettle = async (props: HostProps) => {
  await act(async () => {
    root.render(<FullChartHost {...props} />);
  });
};
function click(el: Element) {
  act(() => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
async function clickAndSettle(el: Element) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
}
const outside = (el: Element) => !el.closest("dialog");
const dialogs = () => Array.from(document.querySelectorAll("dialog"));
function reader(): HTMLDialogElement {
  const all = dialogs();
  if (all.length !== 1) throw new Error(`expected one reader, found ${all.length}`);
  return all[0];
}
function buttonIn(within: ParentNode, label: string): HTMLButtonElement {
  const found = Array.from(within.querySelectorAll("button")).find((b) => (b.textContent ?? "") === label);
  if (!found) throw new Error(`no button "${label}"`);
  return found;
}
const closeButton = () => buttonIn(reader(), SOCCER_READER_WORDS.close);
const entry = () => host.querySelector<HTMLButtonElement>("[data-test-entry]");
const anchor = () => host.querySelector<HTMLElement>("[data-test-anchor]")!;
const pagePlot = () => Array.from(host.querySelectorAll('svg[role="img"]')).find(outside) ?? null;
const readerPlot = () => reader().querySelector('svg[role="img"]');
const disclosureIn = (within: ParentNode) =>
  Array.from(within.querySelectorAll("button")).find((b) => b.textContent === HISTORY_WORDS.details) ?? null;
const pageDisclosure = () => Array.from(host.querySelectorAll("button")).find((b) => outside(b) && b.textContent === HISTORY_WORDS.details) ?? null;

const num = (el: Element, name: string) => Number(el.getAttribute(name));
/** One plot's geometry, read from its own attributes. */
function geometry(svg: Element) {
  const yTicks = Array.from(svg.querySelectorAll('text[text-anchor="end"]')).map((t) => ({ label: t.textContent, x: num(t, "x"), y: num(t, "y") }));
  return {
    width: num(svg, "width"),
    height: num(svg, "height"),
    yTicks,
    paths: Array.from(svg.querySelectorAll("path")).map((p) => {
      const tokens = (p.getAttribute("d") ?? "").trim().split(/\s+/);
      const points: Array<{ cmd: string; x: number; y: number }> = [];
      for (let i = 0; i + 2 < tokens.length; i += 3) points.push({ cmd: tokens[i], x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) });
      return points;
    }),
    marks: Array.from(svg.querySelectorAll("circle, rect")).map((m) =>
      m.tagName.toLowerCase() === "circle" ? { kind: "circle", x: num(m, "cx"), y: num(m, "cy") } : { kind: "rect", x: num(m, "x") + 3.5, y: num(m, "y") + 3.5 },
    ),
    xLabels: Array.from(svg.querySelectorAll("text[data-axis-tick]")).map((t) => ({ text: t.textContent, lane: t.getAttribute("data-axis-lane"), x: num(t, "x"), y: num(t, "y") })),
  };
}
/** The plot's own vertical frame, from two y ticks of the history: y(p) = top + (1 − p) · height. */
function plotFrame(svg: Element, history: HockeyJourneyHistory) {
  const g = geometry(svg);
  const pOf = (label: string | null) => history.yTicks.find((tick) => tick.label === label)!.p;
  const [a, b] = [g.yTicks[0], g.yTicks[g.yTicks.length - 1]];
  const height = (a.y - b.y) / (pOf(b.label) - pOf(a.label));
  return { top: a.y - (1 - pOf(a.label)) * height, height };
}
/** Static source reads, for the census boundary (comments stripped). */
const ROOT = path.resolve(__dirname, "../..");
const importsOf = (file: string) => {
  const src = fs.readFileSync(path.join(ROOT, file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  return { src, specs: Array.from(src.matchAll(/from\s+["']([^"']+)["']/g)).map((m) => m[1]) };
};

// ─── The shared context and the run reader, unchanged ──────────────────────

describe("the compact context moved verbatim; the run reader is unchanged", () => {
  it("the shared view draws the run reader's exact context markup for the same strings, and the history reader draws the same", () => {
    const totals = mlbFinalTotals(mlbRunLines(runTotalsFixture.game_question_matrix), { home: 3, away: 7 }, { home: finalDetail.home_team, away: finalDetail.away_team })!;
    // The type is still public from the run reader's path, and is the same type.
    const oldPath: RunReaderContextFromOldPath = FINAL_CONTEXT;
    const none = () => undefined;
    for (const ctx of [oldPath, { ...FINAL_CONTEXT, score: null }, { ...FINAL_CONTEXT, score: { away: "7", home: "" } }]) {
      act(() =>
        root.render(
          <MlbRunTotalsReader
            totals={totals}
            scope="mlb:15321836:final"
            colors={COLORS}
            selection={{ held: null, onSelect: none }}
            context={ctx}
            onClose={none}
            onUnavailable={none}
            returnTo={() => null}
          />,
        ),
      );
      const fromRunReader = reader().querySelector("[data-mlb-run-reader-context]")!.outerHTML;
      expect(reader().querySelector("h2")?.textContent).toBe(MLB_RUN_READER_WORDS.title);
      expect(reader().querySelector("[data-run-plot]")?.getAttribute("data-run-plot")).toBe("expanded");
      act(() => root.unmount());
      root = createRoot(host);
      act(() => root.render(<RunReaderContext context={ctx} />));
      expect(host.innerHTML).toBe(fromRunReader);
      act(() =>
        root.render(
          <MlbHistoryReader
            headline={FINAL.headline}
            phase={FINAL.phase}
            history={FINAL.history}
            colors={COLORS}
            context={ctx}
            onClose={none}
            onUnavailable={none}
            returnTo={() => null}
          />,
        ),
      );
      expect(reader().querySelector("[data-mlb-run-reader-context]")!.outerHTML).toBe(fromRunReader);
      act(() => root.unmount());
      root = createRoot(host);
    }
    // With no input the run reader still keeps only its words, and no context.
    act(() =>
      root.render(
        <MlbRunTotalsReader
          totals={null}
          scope="mlb:15321836:final"
          colors={COLORS}
          selection={{ held: null, onSelect: none }}
          context={FINAL_CONTEXT}
          onClose={none}
          onUnavailable={none}
          returnTo={() => null}
        />,
      ),
    );
    expect(reader().querySelector("[data-mlb-run-reader-context]")).toBeNull();
    expect(reader().querySelector("[data-mlb-run-reader-unavailable]")?.textContent).toBe(MLB_RUN_READER_WORDS.storyUnavailable);
  });

  it("census boundary: the context module imports nothing and holds no hook; the history reader imports only outside the propGrade closure, never the run reader", () => {
    const context = importsOf("components/event/eventpage10868/MlbReaderContext.tsx");
    expect(context.specs).toEqual([]);
    expect(/^\s*import\b/m.test(context.src)).toBe(false);
    expect(/\buse[A-Z]\w*\s*\(/.test(context.src)).toBe(false);
    const historyReader = importsOf("components/event/eventpage10868/MlbHistoryReader.tsx");
    expect(historyReader.specs.sort()).toEqual(
      ["./HockeyJourneyHistoryChart", "./HockeyJourneyMatrix", "./MlbReaderContext", "./SoccerMatchReader", "@/lib/eventPage10868/hockeyJourneyTypes"].sort(),
    );
    expect(historyReader.src).not.toMatch(/MlbRunTotalsReader|MlbRunTotalsCard|propGrade/);
    // The run reader takes the shared view and re-exports the type from its old path.
    const runReader = importsOf("components/event/eventpage10868/MlbRunTotalsReader.tsx");
    expect(runReader.specs).toContain("./MlbReaderContext");
    expect(runReader.specs).toContain("./MlbRunTotalsCard");
    expect(runReader.src).toMatch(/export type \{ MlbRunReaderContext \} from "\.\/MlbReaderContext"/);
  });
});

// ─── The same journey, full size ───────────────────────────────────────────

describe("the reader draws the page's own history, taller: the same points, gaps and x positions", () => {
  it("REAL final: title, kind, context, the away-first matrix, then the expanded chart of the same runs; the page chart stays inline", () => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    const d = reader();
    expect(showModalCalls).toBe(1);
    expect(d.getAttribute("data-soccer-reader")).toBe("history");
    expect(d.querySelector("h2")?.textContent).toBe(FINAL.history.title);
    // Body order: the context, the matrix, the chart.
    const body = d.querySelector("[data-soccer-reader-body]")!;
    const ctx = body.querySelector("[data-mlb-run-reader-context]")!;
    const matrix = body.querySelector("[data-hockey-matrix]")!;
    const plot = readerPlot()!;
    expect(body.children[0]).toBe(ctx);
    expect(ctx.compareDocumentPosition(matrix) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(matrix.compareDocumentPosition(plot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(matrix.getAttribute("data-hockey-matrix")).toBe("final");
    // The matrix is away first, as on the page.
    const rowNames = Array.from(matrix.querySelectorAll("table tbody tr")).map((row) => row.querySelector("th")?.textContent ?? "");
    expect(rowNames).toEqual([expect.stringContaining(FINAL.headline.away.name), expect.stringContaining(FINAL.headline.home.name)]);
    // The chart: the same model, expanded in the reader and inline on the page.
    const page = geometry(pagePlot()!);
    const full = geometry(plot);
    expect(full.width).toBe(page.width);
    expect(full.height - page.height).toBe(EXPANDED_PX - INLINE_PX);
    const runs = FINAL.history.series.flatMap((s) => s.runs.filter((run) => run.length > 1));
    expect(runs.length).toBeGreaterThan(0);
    expect(full.paths).toHaveLength(runs.length);
    full.paths.forEach((points, i) => {
      // One path per recorded run: never bridged across a gap.
      expect(points.map((pt) => pt.cmd)).toEqual(["M", ...Array(runs[i].length - 1).fill("L")]);
      expect(points.map((pt) => pt.x)).toEqual(page.paths[i].map((pt) => pt.x));
    });
    expect(full.marks.map((m) => [m.kind, m.x])).toEqual(page.marks.map((m) => [m.kind, m.x]));
    expect(full.xLabels.map((l) => [l.text, l.lane, l.x])).toEqual(page.xLabels.map((l) => [l.text, l.lane, l.x]));
    expect(full.yTicks.map((t) => [t.label, t.x])).toEqual(page.yTicks.map((t) => [t.label, t.x]));
    // Every recorded point at its own probability on the taller plot.
    const frame = plotFrame(plot, FINAL.history);
    const pageFrame = plotFrame(pagePlot()!, FINAL.history);
    expect(frame.top).toBeCloseTo(pageFrame.top, 6);
    expect(frame.height - pageFrame.height).toBeCloseTo(EXPANDED_PX - INLINE_PX, 6);
    full.paths.forEach((points, i) =>
      points.forEach((pt, j) => expect(Math.abs(pt.y - (frame.top + (1 - runs[i][j].p) * frame.height))).toBeLessThanOrEqual(0.051)),
    );
    // The key, caption and notes are the page chart's words.
    const keyIn = (within: ParentNode) => Array.from(within.querySelectorAll("[data-line-key]")).map((k) => k.textContent);
    const basisIn = (within: ParentNode) => Array.from(within.querySelectorAll("[data-history-basis]")).map((k) => k.textContent);
    const pageSection = pagePlot()!.closest("section")!;
    expect(keyIn(d)).toEqual(keyIn(pageSection));
    expect(basisIn(d)).toEqual(basisIn(pageSection));
  });

  it("a phase the headline does not match hides the matrix; the context and the chart remain (CONSTRUCTED phase)", () => {
    show({ ...FINAL, phase: "live", context: FINAL_CONTEXT });
    click(entry()!);
    expect(reader().querySelector("[data-hockey-matrix]")).toBeNull();
    expect(reader().querySelector("table")).toBeNull();
    expect(reader().querySelector("[data-mlb-run-reader-context]")).not.toBeNull();
    expect(readerPlot()).not.toBeNull();
  });

  it("CONSTRUCTED live: the live matrix and the live page's history, its compact context's state", () => {
    const live = pageCopies(view(liveDetail, liveHost));
    expect(live.phase).toBe("live");
    show({ ...live, context: contextFor(live.headline, { away: "6", home: "3" }), scope: "mlb:15321836:live" });
    click(entry()!);
    expect(reader().querySelector("[data-hockey-matrix]")?.getAttribute("data-hockey-matrix")).toBe("live");
    expect(reader().querySelector("[data-mlb-run-reader-state]")?.textContent).toBe(live.headline.state);
    expect(reader().querySelector("h2")?.textContent).toBe(live.history.title);
  });

  it("each chart's Details disclosure is its own: opening the reader's never opens the page's, and the page's stays open through the reader", async () => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(pageDisclosure()!);
    expect(pageDisclosure()!.getAttribute("aria-expanded")).toBe("true");
    click(entry()!);
    const mine = disclosureIn(reader())!;
    expect(mine).not.toBe(pageDisclosure());
    expect(mine.getAttribute("aria-expanded")).toBe("false"); // a fresh instance, never the page's state
    click(mine);
    expect(mine.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(mine.getAttribute("aria-controls") ?? "")?.hidden).toBe(false);
    click(mine);
    expect(mine.getAttribute("aria-expanded")).toBe("false");
    expect(pageDisclosure()!.getAttribute("aria-expanded")).toBe("true");
    await clickAndSettle(closeButton());
    expect(pageDisclosure()!.getAttribute("aria-expanded")).toBe("true");
    // Every id unique while both charts are mounted.
    click(entry()!);
    const ids = Array.from(document.querySelectorAll("[id]")).map((el) => el.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

// ─── Missing or foreign history ────────────────────────────────────────────

describe("missing or foreign history: the chart's own absence, and the reader stays open", () => {
  it.each([
    ["no history response (CONSTRUCTED)", null],
    ["another event's history (CONSTRUCTED: event_id 1)", mutate(finalHistory, { event_id: 1 })],
  ] as const)("%s: no plot or mark, the chart's absence words, the context and matrix kept", (_name, body) => {
    const v = pageCopies(view(finalDetail, finalHost, body as EventHistoryResponse | null));
    expect(v.history.absence).not.toBeNull();
    show({ ...v, context: FINAL_CONTEXT });
    click(entry()!);
    const d = reader();
    expect(d.open).toBe(true);
    expect(readerPlot()).toBeNull();
    expect(d.querySelector("path")).toBeNull();
    expect(d.textContent).toContain(v.history.absence!.title);
    expect(d.querySelector("h2")?.textContent).toBe(v.history.title);
    expect(d.querySelector("[data-mlb-run-reader-context]")).not.toBeNull();
    expect(d.querySelector("[data-hockey-matrix]")).not.toBeNull();
    // Nothing to disclose: no control is offered.
    expect(disclosureIn(d)).toBeNull();
  });

  it("a plot lost during a same-scope update keeps the same open reader on the absence; its return redraws it — no reopen, no scroll", () => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    const d = reader();
    const missing = pageCopies(view(finalDetail, finalHost, null));
    show({ ...missing, context: FINAL_CONTEXT });
    expect(reader()).toBe(d);
    expect(readerPlot()).toBeNull();
    expect(d.textContent).toContain(missing.history.absence!.title);
    show({ ...FINAL, context: FINAL_CONTEXT });
    expect(reader()).toBe(d);
    expect(readerPlot()).not.toBeNull();
    expect(showModalCalls).toBe(1);
    expect(pageScroll).not.toHaveBeenCalled();
  });
});

// ─── The existing shell's behaviour ────────────────────────────────────────

describe("the existing shell: one modal, return of position and focus, failure, updates", () => {
  it("a same-scope update re-reads in place: one showModal, no refocus, no scroll", () => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    const d = reader();
    const mine = disclosureIn(d)!;
    act(() => mine.focus());
    show({ ...FINAL, context: { ...FINAL_CONTEXT, state: "CONSTRUCTED refreshed state" } });
    expect(reader()).toBe(d);
    expect(showModalCalls).toBe(1);
    expect(d.querySelector("[data-mlb-run-reader-state]")?.textContent).toBe("CONSTRUCTED refreshed state");
    expect(document.activeElement).toBe(mine);
    expect(pageScroll).not.toHaveBeenCalled();
  });

  it.each(["Close", "cancel (Escape)", "the browser's own close"] as const)(
    "%s closes once, restores the opening position and focuses the opener with preventScroll",
    async (how) => {
      document.body.style.overflow = "clip"; // CONSTRUCTED prior page style, kept and given back
      show({ ...FINAL, context: FINAL_CONTEXT });
      click(entry()!);
      expect(document.activeElement).toBe(closeButton());
      expect(document.body.style.overflow).toBe("hidden");
      const focus = jest.spyOn(HTMLElement.prototype, "focus");
      if (how === "Close") {
        await clickAndSettle(closeButton());
      } else if (how === "cancel (Escape)") {
        // jsdom has no Escape-to-cancel: the dialog's cancel event is dispatched directly (CONSTRUCTED).
        const cancel = new Event("cancel", { cancelable: true });
        await act(async () => {
          reader().dispatchEvent(cancel);
        });
        expect(cancel.defaultPrevented).toBe(true);
      } else {
        await act(async () => {
          reader().close();
        });
      }
      expect(dialogs()).toHaveLength(0);
      expect(log.closes).toBe(1);
      expect(document.body.style.overflow).toBe("clip");
      expect(pageScroll).toHaveBeenCalledTimes(1);
      expect(pageScroll).toHaveBeenCalledWith(0, 640);
      expect(document.activeElement).toBe(entry());
      expect(focus.mock.contexts.at(-1)).toBe(entry());
      expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
      click(entry()!);
      expect(showModalCalls).toBe(2);
    },
  );

  it("with the opener gone (CONSTRUCTED), Close focuses the caller's local anchor; a new scope closes without scrolling", async () => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    show({ ...FINAL, context: FINAL_CONTEXT, opener: false });
    await clickAndSettle(closeButton());
    expect(pageScroll).toHaveBeenCalledWith(0, 640);
    expect(document.activeElement).toBe(anchor());
    // A new event or phase in the caller closes it in that render, with no scroll restored and no close request.
    pageScroll.mockClear();
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    const closesBefore = log.closes;
    await showAndSettle({ ...FINAL, context: FINAL_CONTEXT, scope: "mlb:15321837:final" });
    expect(dialogs()).toHaveLength(0);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(log.closes).toBe(closesBefore);
  });

  it.each(["missing", "throwing"] as const)("showModal %s: nothing opens, the caller is told once, focus returns unscrolled; the page chart is untouched", async (failure) => {
    show({ ...FINAL, context: FINAL_CONTEXT });
    if (failure === "missing") delete dialogProto.showModal;
    else
      dialogProto.showModal = function () {
        showModalCalls += 1;
        throw new DOMException("CONSTRUCTED opening failure", "InvalidStateError");
      };
    const plotBefore = pagePlot();
    const focus = jest.spyOn(HTMLElement.prototype, "focus");
    await clickAndSettle(entry()!);
    expect(dialogs()).toHaveLength(0);
    expect(document.querySelector("[open], [aria-modal]")).toBeNull();
    expect(log.unavailable).toBe(1);
    expect(host.querySelector("[data-test-status]")?.textContent).toBe(SOCCER_READER_WORDS.fullSizeUnavailable);
    expect(document.activeElement).toBe(entry());
    expect(focus.mock.calls.at(-1)).toEqual([{ preventScroll: true }]);
    expect(pageScroll).not.toHaveBeenCalled();
    expect(pagePlot()).toBe(plotBefore);
    click(pageDisclosure()!);
    expect(pageDisclosure()!.getAttribute("aria-expanded")).toBe("true");
  });

  it("no fake navigation, place or Details: the only controls are Close and the chart's own disclosure; no history call", () => {
    const push = jest.spyOn(window.history, "pushState");
    const replace = jest.spyOn(window.history, "replaceState");
    show({ ...FINAL, context: FINAL_CONTEXT });
    click(entry()!);
    const d = reader();
    expect(dialogs()).toHaveLength(1);
    expect(d.querySelectorAll("nav")).toHaveLength(0);
    expect(d.querySelector("[data-soccer-reader-position], [data-soccer-details-entry]")).toBeNull();
    expect(Array.from(d.querySelectorAll("button")).map((b) => b.textContent)).toEqual([SOCCER_READER_WORDS.close, HISTORY_WORDS.details]);
    expect(d.textContent).not.toContain(SOCCER_READER_WORDS.fullChart);
    expect(d.textContent).not.toMatch(/\b1 of 1\b/);
    expect(push).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });
});
