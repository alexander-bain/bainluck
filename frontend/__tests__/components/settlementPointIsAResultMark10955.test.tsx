/**
 * #10955 / #11158 Step 2 — A SETTLEMENT POINT IS A RESULT MARK, NOT A PRICE.
 *
 * The host half. `chartSettlementPoints.test.ts` proves the split; this proves
 * that `FuturesChart` — the one kernel behind `/futures/[id]`, `EvolutionView`,
 * `/categories/golf`, `SettledPathChart` and `TeamSeasonJourney` — plots what
 * the split hands it and nothing else, for every `settlement_basis` the server
 * can serve (Authority's 0545Z contract, G1–G6).
 *
 * ═══ THE DEFECT ═══
 *
 * `/api/futures/{id}/history` ends a graded leg with `bookmaker: "settlement"`
 * at 0.0 or 1.0. Its timestamp is a schedule, a system notice, a nudge, the
 * clock or nothing — never a trade. Drawn as a series point, a past
 * `resolution_date` an hour after the last trade sat inside the gap threshold
 * and the leg drew a SOLID drop to 0% at a time nobody traded; the tooltip
 * read 0% there, the domain stretched to it, freshness and the combined line
 * counted it.
 *
 * ═══ THE SHAPE OF EVERY ASSERTION ═══
 *
 * The control is the same field with the settlement points simply absent. With
 * the result marks and the legend's result words taken out, the chart drawn
 * WITH settlement points must be the control's markup byte for byte — domain,
 * axis labels, runs, bridges, dots, combined line, freshness caption. Then the
 * marks themselves are asserted: one per settled leg, at that leg's own last
 * real x/y, naming the grade, printing no time and no percent.
 *
 * Fixed anchors throughout — never Date.now() (gotcha #44).
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";

import { FuturesChart } from "@/components/FuturesChart";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const START = Date.UTC(2026, 8, 29, 12, 0, 0);
const LAST = START + 48 * HOUR; // 2026-10-01T12:00:00Z — the field's last real reading
const NOW = LAST + 3 * DAY;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

// Plot frame at height 200: padding.top 20, innerHeight 140, right edge 780.
const PLOT_TOP = 20;
const PLOT_FLOOR = 160;
const RIGHT_EDGE = 780;
const yAt = (p: number) => PLOT_TOP + (1 - p) * 140;

/** Step 1 (#11435) adds this field; the consumer rule must not need it. */
type ServedPoint = FuturesHistoryPoint & { settlement_basis?: string };

const real = (i: number, p: number): ServedPoint => ({
  timestamp: new Date(START + i * HOUR).toISOString(),
  probability: p,
  american_odds: null,
  bookmaker: "consensus",
});

const yesProb = (i: number) => 0.3 + 0.002 * i; // ends at 0.396
const noProb = (i: number) => 1 - yesProb(i); // ends at 0.604
const drawProb = (i: number) => 0.05 + 0.0005 * i;

const realYes = Array.from({ length: 49 }, (_, i) => real(i, yesProb(i)));
const realNo = Array.from({ length: 49 }, (_, i) => real(i, noProb(i)));
const realDraw = Array.from({ length: 49 }, (_, i) => real(i, drawProb(i)));

/** Every basis the server can serve, each at the x it would really carry. */
const BASES: { basis: string | undefined; label: string; at: number }[] = [
  // A scheduled close one hour after the last trade — INSIDE the gap threshold.
  { basis: "resolution_date", label: "resolution_date", at: LAST + HOUR },
  // The moment this system noticed the settlement; can lag by years.
  { basis: "settled_at", label: "settled_at", at: LAST + 400 * DAY },
  // A nudge past the leg's own last trade.
  { basis: "last_observation", label: "last_observation", at: LAST + 1000 },
  // The reading clock.
  { basis: "clock", label: "clock", at: NOW },
  // No basis at all (today's payloads, before Step 1).
  { basis: undefined, label: "missing", at: LAST + 2 * HOUR },
  // A value no client knows.
  { basis: "venue_close_v2", label: "unknown string", at: LAST + 26 * DAY },
];

function settlement(at: number, p: 0 | 1, basis: string | undefined): ServedPoint {
  const point: ServedPoint = {
    timestamp: new Date(at).toISOString(),
    probability: p,
    american_odds: null,
    bookmaker: "settlement",
  };
  if (basis !== undefined) point.settlement_basis = basis;
  return point;
}

const leg = (id: number, name: string, history: ServedPoint[]): FuturesOutcomeHistory => ({
  outcome_id: id,
  name,
  history,
});

/** The control: the same field, no settlement points anywhere. */
const CONTROL: FuturesOutcomeHistory[] = [
  leg(1, "Yes", realYes),
  leg(2, "No", realNo),
  leg(3, "Draw", realDraw),
];

/** Yes graded lost, No graded won, Draw never graded. */
function settledField(at: number, basis: string | undefined): FuturesOutcomeHistory[] {
  return [
    leg(1, "Yes", [...realYes, settlement(at, 0, basis)]),
    leg(2, "No", [...realNo, settlement(at, 1, basis)]),
    leg(3, "Draw", realDraw),
  ];
}

// ─── markup readers ─────────────────────────────────────────────────────────

const MARK_RE = /<g data-testid="futures-chart-result-mark"[\s\S]*?<\/g>/g;
const LEGEND_WORD_RE =
  /<span data-testid="futures-chart-legend-result"[^>]*><span[^>]*>[^<]*<\/span><\/span>/g;

/** The chart with every result carrier removed — what must equal the control. */
const withoutResults = (html: string) => html.replace(MARK_RE, "").replace(LEGEND_WORD_RE, "");

function resultMarks(html: string) {
  return (html.match(MARK_RE) ?? []).map((g) => ({
    raw: g,
    outcome: Number(/data-outcome-id="(\d+)"/.exec(g)?.[1]),
    result: /data-result="([a-z]+)"/.exec(g)?.[1],
    anchor: /data-anchor="([a-z-]+)"/.exec(g)?.[1],
    label: /aria-label="([^"]*)"/.exec(g)?.[1] ?? "",
    cx: Number(/<circle[^>]*cx="([-\d.]+)"/.exec(g)?.[1]),
    cy: Number(/<circle[^>]*cy="([-\d.]+)"/.exec(g)?.[1]),
    r: Number(/<circle[^>]*\sr="([-\d.]+)"/.exec(g)?.[1]),
  }));
}

/** Solid run `d` strings: paths that are neither bridges, the combined line, nor glyphs. */
function solidRuns(html: string): string[] {
  return [...withoutResults(html).matchAll(/<path ([^>]*)>/g)]
    .map((m) => m[1])
    .filter((attrs) => !/stroke-dasharray="(1 5|7 4)"/.test(attrs))
    .map((attrs) => /\sd="([^"]+)"/.exec(" " + attrs)?.[1] ?? "")
    .filter((d) => d.startsWith("M"));
}

const draw = (data: FuturesOutcomeHistory[], extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(<FuturesChart historyData={data} height={200} {...extra} />);

// ─── G1 / G3 / G5: every basis — nothing settled reaches the observed chart ─

describe.each(BASES)("basis $label", ({ basis, at }) => {
  const field = settledField(at, basis);

  test("G1/G3/G5: without its result marks, the chart is the control byte for byte", () => {
    // Domain (= x of every point and every axis label), runs, bridges, dots and
    // the freshness caption all live in this markup. The settlement point may
    // move none of them, and the never-graded Draw leg must be untouched.
    expect(withoutResults(draw(field))).toBe(draw(CONTROL));
  });

  test("G3: the combined line sums real points only", () => {
    const html = draw(field, { showCombinedProbability: true });
    expect(withoutResults(html)).toBe(draw(CONTROL, { showCombinedProbability: true }));
  });

  test("G1: exactly one result mark per graded leg, at that leg's own last real x/y", () => {
    const marks = resultMarks(draw(field));
    expect(marks.map((m) => m.outcome).sort()).toEqual([1, 2]);

    const yes = marks.find((m) => m.outcome === 1)!;
    const no = marks.find((m) => m.outcome === 2)!;
    expect(yes).toMatchObject({ result: "lost", anchor: "last-observation", cx: RIGHT_EDGE });
    expect(no).toMatchObject({ result: "won", anchor: "last-observation", cx: RIGHT_EDGE });
    expect(yes.cy).toBeCloseTo(yAt(yesProb(48)), 6);
    expect(no.cy).toBeCloseTo(yAt(noProb(48)), 6);
  });

  test("the mark names the grade and claims no time and no percent", () => {
    const marks = resultMarks(draw(field));
    expect(marks).toHaveLength(2);
    for (const m of marks) {
      expect(m.label).toMatch(m.result === "won" ? /: Won\./ : /: Lost\./);
      expect(m.label).toContain("not another probability update");
      expect(m.raw).not.toMatch(/\d%/);
      expect(m.raw).not.toMatch(/\b(19|20)\d\d\b|\d{1,2}:\d\d|\b(AM|PM)\b/);
    }
  });
});

// ─── G2: the causal control ─────────────────────────────────────────────────

describe("G2 a past resolution_date one hour after the last trade", () => {
  const field = settledField(LAST + HOUR, "resolution_date");

  test("draws no solid segment to the result — the leg ends at its last trade", () => {
    // Inside the gap threshold, the old chart drew the loser's solid stroke
    // straight down to the 0% floor and the winner's up to the 100% ceiling at
    // a time nobody traded.
    const runs = solidRuns(draw(field));
    for (const d of runs) {
      expect(d).not.toMatch(new RegExp(`L [\\d.]+ ${PLOT_FLOOR}(\\s|$)`));
      expect(d).not.toMatch(new RegExp(`L [\\d.]+ ${PLOT_TOP}(\\s|$)`));
    }
    const yesRun = runs.find((d) => d.endsWith(`${RIGHT_EDGE} ${yAt(yesProb(48))}`));
    expect(yesRun).toBeDefined();
  });

  test("no dotted bridge reaches it either", () => {
    expect(draw(field)).not.toContain('stroke-dasharray="1 5"');
  });
});

// ─── G3: the real hover/crosshair ───────────────────────────────────────────

describe("G3 the tooltip and crosshair read real points only", () => {
  function descendants(node: HTMLElement): HTMLElement[] {
    return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as HTMLElement))];
  }
  function props(node: HTMLElement): Record<string, (arg?: unknown) => void> {
    const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
    return (node as unknown as Record<string, Record<string, (arg?: unknown) => void>>)[key];
  }
  function hoverAt(host: HTMLElement, clientX: number) {
    const svg = descendants(host).find((n) => n.tagName === "SVG" && props(n)?.onMouseMove)!;
    expect(svg).toBeDefined();
    const event = { clientX, currentTarget: { getBoundingClientRect: () => ({ left: 0, width: 800 }) } };
    act(() => props(svg).onMouseMove(event));
  }
  function tooltip(host: HTMLElement): string | null {
    const node = descendants(host).find(
      (n) => n.tagName === "DIV" && String(props(n)?.className ?? "").includes("pointer-events-none z-50"),
    );
    return node ? node.textContent : null;
  }
  function crosshairDots(host: HTMLElement): number[] {
    // The hover dots: r=4 circles, each at its value's y.
    return descendants(host)
      .filter((n) => n.tagName === "CIRCLE" && Number(props(n)?.r as unknown) === 4)
      .map((n) => Number(props(n)?.cy as unknown));
  }

  let host: HTMLElement;
  let root: ReturnType<typeof createRoot>;
  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });
  afterEach(() => {
    act(() => root.unmount());
    document.body.removeChild(host);
  });

  test.each(BASES)("basis $label: at the right edge it reads the last trade, not the result", ({ basis, at }) => {
    act(() => root.render(<FuturesChart historyData={settledField(at, basis)} height={200} />));
    hoverAt(host, RIGHT_EDGE); // the cursor at the domain max — which must be the last trade
    const text = tooltip(host);
    expect(text).not.toBeNull();
    // Real last readings: No 60%, Yes 40%, Draw 7% — never the 100%/0% result.
    expect(text).toContain("No60%");
    expect(text).toContain("Yes40%");
    expect(text).not.toContain("100%");
    expect(text).not.toMatch(/Yes0%|No0%/);
    // The time printed is the field's last trade, never the settlement stamp.
    expect(text).toMatch(/^Oct 1 12 PM/);
    expect(crosshairDots(host).sort((a, b) => a - b)).toEqual(
      [yAt(noProb(48)), yAt(yesProb(48)), yAt(drawProb(48))].sort((a, b) => a - b),
    );
  });

  test("the 199045 shape: a loser whose result sits on a SIBLING's last stamp", () => {
    // `/futures/199045` (AL Champion, retained 2026-10-17): Houston's last
    // trade was 10/16 16:36 at 0.6%; its settlement point was stamped at the
    // field's last stamp, 10/17 09:03, where the live legs still traded. At the
    // right edge the settlement point is the NEAREST candidate to the cursor —
    // the hover must still read Houston's last trade, never its 0%.
    const houston = Array.from({ length: 40 }, (_, i) => real(i, 0.006));
    const field = [
      leg(1, "Cleveland", realNo),
      leg(2, "Houston", [...houston, settlement(LAST, 0, "last_observation")]),
    ];
    act(() => root.render(<FuturesChart historyData={field} height={200} />));
    hoverAt(host, RIGHT_EDGE);
    const text = tooltip(host);
    expect(text).toContain("Cleveland60%");
    expect(text).toContain("Houston1%");
    expect(text).not.toContain("Houston0%");
  });
});

// ─── G4: a winner with no history of its own; a chart with none at all ──────

describe("G4 a synthesized-only winner beside real legs", () => {
  const withWinner = (at: number, basis: string | undefined) => [
    leg(1, "Yes", realYes),
    leg(3, "Draw", realDraw),
    leg(99, "Other", [settlement(at, 1, basis)]),
  ];
  const control = [leg(1, "Yes", realYes), leg(3, "Draw", realDraw)];

  test.each([
    ["resolution_date 26 days later", LAST + 26 * DAY, "resolution_date"],
    ["the #6331 shape — at the field's own last stamp", LAST, "last_observation"],
    ["no basis", LAST + 2 * HOUR, undefined],
  ] as const)("%s: one mark at the real right edge, domain unchanged, no invented y", (_, at, basis) => {
    const html = draw(withWinner(at, basis));
    const marks = resultMarks(html);
    expect(marks).toHaveLength(1);
    expect(marks[0]).toMatchObject({ outcome: 99, result: "won", anchor: "real-edge", cx: RIGHT_EDGE });
    // Outside the plot's probability scale entirely — not at 100%, not anywhere on it.
    expect(marks[0].cy).toBeLessThan(PLOT_TOP);
    expect(marks[0].label).toContain("No probability history was recorded for it");
    // No path, run or dot of its own: the plot holds exactly the control's
    // lines (only the legend gains the new leg's entry).
    expect(solidRuns(html)).toEqual(solidRuns(draw(control)));
    expect(withoutResults(html).match(/<svg[\s\S]*<\/svg>/)?.[0]).toBe(
      draw(control).match(/<svg[\s\S]*<\/svg>/)?.[0],
    );
  });

  test("no real points anywhere: the sparse state, with no dot at a notice time or the clock", () => {
    for (const [at, basis] of [
      [NOW, "clock"],
      [LAST + 400 * DAY, "settled_at"],
    ] as const) {
      const html = draw([leg(99, "Other", [settlement(at, 1, basis)])]);
      expect(html).toContain("Limited price history available");
      expect(html).not.toContain("<circle");
      expect(resultMarks(html)).toEqual([]);
    }
  });

  test("enough-points: one real reading plus a settlement point is still sparse", () => {
    // The old count admitted the settlement point as the second point and drew
    // a one-trade chart ending in a timed move to 0%.
    const html = draw([leg(1, "Yes", [real(48, 0.4), settlement(LAST + HOUR, 0, "resolution_date")])]);
    expect(html).toContain("Limited price history available");
    expect(html).not.toContain("<svg viewBox");
  });

  test("enough-points counts real readings, even when the domain has width", () => {
    // A priceless reading widens the time domain without being a point, so the
    // count — not the domain — is what must refuse the settlement point here.
    const html = draw([
      leg(1, "Yes", [
        { ...real(0, 0.4), probability: null },
        real(48, 0.4),
        settlement(LAST + HOUR, 0, "resolution_date"),
      ]),
    ]);
    expect(html).toContain("Limited price history available");
    expect(html).not.toContain("<svg viewBox");
  });
});

// ─── The legend carries the readable result; unaffected charts unchanged ────

describe("the result is readable in words, and only where there is one", () => {
  const field = settledField(LAST + HOUR, "resolution_date");

  test("the static legend names Won and Lost beside their legs, nothing beside Draw", () => {
    const html = draw(field);
    const legend = html.slice(html.indexOf('aria-label="Chart legend"'));
    expect(legend).toMatch(/>Yes<\/span><span data-testid="futures-chart-legend-result" data-result="lost"><span[^>]*>Lost</);
    expect(legend).toMatch(/>No<\/span><span data-testid="futures-chart-legend-result" data-result="won"><span[^>]*>Won</);
    expect(legend).toMatch(/>Draw<\/span><\/span>/);
  });

  test("the interactive legend (the futures page's) names them too", () => {
    const html = draw(field, { onToggleOutcome: () => {}, selectedOutcomes: new Set([1, 2, 3]) });
    expect((html.match(LEGEND_WORD_RE) ?? []).length).toBe(2);
  });

  test("a value that is neither 1 nor 0 gets a mark and no verdict word — never 'Lost'", () => {
    const odd = [
      leg(1, "Yes", [...realYes, { ...settlement(LAST + HOUR, 0, "resolution_date"), probability: 0.5 }]),
      leg(3, "Draw", realDraw),
    ];
    const html = draw(odd);
    const [m] = resultMarks(html);
    expect(m.result).toBe("recorded");
    expect(m.label).not.toMatch(/Won|Lost/);
    expect(html.match(LEGEND_WORD_RE)).toBeNull();
  });

  test("G5: a field with no settlement point gains nothing at all", () => {
    const html = draw(CONTROL);
    expect(resultMarks(html)).toEqual([]);
    expect(html).not.toContain("futures-chart-legend-result");
  });

  test("the mark is not the recorded-dot vocabulary: bigger, ringed and carrying a glyph", () => {
    const marks = resultMarks(draw(field));
    expect(marks).toHaveLength(2);
    for (const m of marks) {
      expect(m.r).toBeGreaterThan(3); // the #6331 lone-observation dot is r=3
      expect(m.raw).toContain('stroke="#FFFFFF"');
      expect(m.raw).toMatch(/<path [^>]*d="M/);
    }
  });

  test("mini sparklines still mark the result, smaller", () => {
    const marks = resultMarks(renderToStaticMarkup(<FuturesChart historyData={field} mini />));
    expect(marks).toHaveLength(2);
    for (const m of marks) expect(m.r).toBeLessThan(3);
  });

  test("the served payload is never mutated", () => {
    const before = JSON.stringify(field);
    draw(field, { showCombinedProbability: true });
    renderToStaticMarkup(<FuturesChart historyData={field} settled height={200} />);
    expect(JSON.stringify(field)).toBe(before);
  });
});
