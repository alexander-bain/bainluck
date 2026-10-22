/**
 * #10955 (release-root 327) — the same-consumer follow-up to Step 2 (PR #11436).
 *
 *   U1  The event sections' "has history" counters (`SettledPathChart`,
 *       `WinnerEvolutionChart`, `TwoSidedTimeline`) count a settlement point as
 *       a reading no longer: one reading plus a result keeps each section's old
 *       absence instead of opening a sparse box, and a result stamped days after
 *       a 20-hour history no longer grows a "1D" chip.
 *   C   The chart legend's "Lost" reads at `text-text-secondary`, not the faint
 *       `text-text-muted` the shared `SettledMark` draws — chart-local, the
 *       shared mark untouched (#4040 owns its colour).
 *   T   The hover callout stays inside the visible card at either edge of the
 *       plot, wrapping names rather than cutting them off; the crosshair and
 *       the values it names do not move.
 *
 * Controlled examples with fixed anchors (gotcha #44) — not real-game evidence.
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";

let HISTORY: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false, mutate: () => {} };
    return { data: HISTORY, error: null, isLoading: false, mutate: () => {} };
  },
}));
jest.mock("../../components/event/FighterAvatar", () => ({ __esModule: true, default: () => null }));

import { FuturesChart, LOST_LEGEND_WORD_CLASS } from "@/components/FuturesChart";
import SettledPathChart from "@/components/event/SettledPathChart";
import TwoSidedTimeline from "@/components/event/TwoSidedTimeline";
import WinnerEvolutionChart from "@/components/event/WinnerEvolutionChart";
import {
  TOOLTIP_EDGE_MARGIN_PX,
  placeChartTooltip,
  tooltipMaxWidth,
} from "@/lib/chartTooltipPlacement";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const START = Date.UTC(2026, 9, 10, 0, 0, 0);
const LAST_REAL = START + 20 * HOUR;
const RESULT_AT = LAST_REAL + 3 * DAY;
const NOW = RESULT_AT + DAY;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

const pt = (at: number, p: number, bookmaker = "consensus"): FuturesHistoryPoint => ({
  timestamp: new Date(at).toISOString(),
  probability: p,
  american_odds: null,
  bookmaker,
});
const leg = (id: number, name: string, history: FuturesHistoryPoint[]): FuturesOutcomeHistory => ({
  outcome_id: id,
  name,
  history,
});
const response = (outcomes: FuturesOutcomeHistory[]) => ({
  market_id: 4242,
  market_name: "Who wins?",
  hours: 8760,
  actual_hours: 8760,
  outcomes,
  round_boundaries: null,
  leaderboard: null,
  total_data_points: outcomes.reduce((s, o) => s + o.history.length, 0),
  sparse: false,
  history_range: null,
});

const SPARSE = "Limited price history available";
const CHIPS = 'aria-label="Chart time range"';

const SECTIONS: [string, () => React.ReactElement][] = [
  ["SettledPathChart", () => <SettledPathChart marketId={4242} />],
  ["WinnerEvolutionChart", () => <WinnerEvolutionChart marketId={4242} />],
];
const TWO_SIDED = () => (
  <TwoSidedTimeline
    competitors={[{ name: "Yes", probability: 0.4 }, { name: "No", probability: 0.6 }] as never}
    label="Head to head"
    evolutionMarketId={4242}
  />
);
const render = (make: () => React.ReactElement, outcomes: FuturesOutcomeHistory[]) => {
  HISTORY = response(outcomes);
  return renderToStaticMarkup(make());
};

/** One real reading per leg, each leg's result stamped later. */
const ONE_PLUS_RESULT = [
  leg(1, "Yes", [pt(START, 0.4), pt(RESULT_AT, 1, "settlement")]),
  leg(2, "No", [pt(START, 0.6), pt(RESULT_AT, 0, "settlement")]),
];
/** The reviewer's example: 20 h of real readings, results 3 days later. */
const realYes = Array.from({ length: 21 }, (_, i) => pt(START + i * HOUR, 0.4 + 0.01 * i));
const realNo = Array.from({ length: 21 }, (_, i) => pt(START + i * HOUR, 0.6 - 0.01 * i));
const TWENTY_HOURS = [
  leg(1, "Yes", [...realYes, pt(RESULT_AT, 1, "settlement")]),
  leg(2, "No", [...realNo, pt(RESULT_AT, 0, "settlement")]),
];

describe("U1 the event sections do not count a result as recorded history", () => {
  it.each(SECTIONS)("%s: one reading + a result keeps the section's old absence", (_n, make) => {
    expect(render(make, ONE_PLUS_RESULT)).toBe("");
    // CONTROL: the same field without results was already absent.
    expect(render(make, ONE_PLUS_RESULT.map((o) => leg(o.outcome_id, o.name, o.history.slice(0, 1))))).toBe("");
  });

  it("TwoSidedTimeline: one reading + a result draws no sparse chart box", () => {
    const html = render(TWO_SIDED, ONE_PLUS_RESULT);
    expect(html).not.toContain(SPARSE);
    expect(html).not.toContain("<svg");
  });

  it.each(SECTIONS)("%s: a 20-hour history with a result 3 days later offers no 1D chip", (_n, make) => {
    const html = render(make, TWENTY_HOURS);
    expect(html).toContain("<svg"); // the real history draws
    expect(html).not.toContain(CHIPS); // one range (All) ⇒ no chip row
    expect(html).not.toMatch(/>1D</);
  });

  it.each(SECTIONS)("HEALTHY %s: real 0% and 100% readings are history and draw", (_n, make) => {
    const html = render(make, [
      leg(1, "Yes", [pt(START, 0.5), pt(LAST_REAL, 1)]),
      leg(2, "No", [pt(START, 0.5), pt(LAST_REAL, 0)]),
    ]);
    expect(html).toContain("<svg");
    expect(html).not.toContain(SPARSE);
  });

  it("HEALTHY TwoSidedTimeline: two real readings + a result draw the chart", () => {
    const html = render(TWO_SIDED, TWENTY_HOURS);
    expect(html).toContain("<svg");
    expect(html).not.toContain(SPARSE);
  });
});

// ─── C: the legend's Lost word contrast ────────────────────────────────────

describe("C the chart legend's Lost reads at secondary-text contrast, chart-local", () => {
  const field = [
    leg(1, "Yes", [...realYes, pt(LAST_REAL + HOUR, 0, "settlement")]),
    leg(2, "No", [...realNo, pt(LAST_REAL + HOUR, 1, "settlement")]),
  ];
  const html = () => renderToStaticMarkup(<FuturesChart historyData={field} height={200} />);
  const wrapper = (result: string) =>
    new RegExp(`<span data-testid="futures-chart-legend-result" data-result="${result}"([^>]*)><span class="([^"]*)">([A-Za-z]+)<`).exec(html());

  it("Lost's wrapper lifts its word to text-text-secondary with an existing token, no raw colour", () => {
    expect(LOST_LEGEND_WORD_CLASS).toBe("[&>span]:text-text-secondary");
    const m = wrapper("lost")!;
    expect(m).not.toBeNull();
    // React escapes the attribute: `[&>span]` is served as `[&amp;&gt;span]`.
    expect(m[1]).toContain('class="[&amp;&gt;span]:text-text-secondary"');
    expect(m[3]).toBe("Lost");
    expect(m[1]).not.toMatch(/#[0-9a-f]{3,6}|rgb\(/i);
  });

  it("the shared SettledMark is untouched: Lost's own span still carries text-text-muted (#4040 owns it)", () => {
    expect(wrapper("lost")![2]).toContain("text-text-muted");
  });

  it("Won is left alone — it already reads in the legend's primary text", () => {
    const m = wrapper("won")!;
    expect(m[3]).toBe("Won");
    expect(m[1]).toBe("");
  });

  it("other SettledMark callers get no chart-local class", () => {
    const { SettledMark } = jest.requireActual("@/components/SettledOutcomeMark");
    expect(renderToStaticMarkup(<SettledMark won={false} />)).toBe(
      '<span class="text-xs font-mono text-text-muted">Lost</span>',
    );
  });
});

// ─── T: the hover callout stays inside the visible card ─────────────────────

describe("T placement arithmetic", () => {
  const view = { viewLeft: 0, viewWidth: 340 };

  it("390 phone, right edge: the callout goes left of the crosshair and fits", () => {
    const left = placeChartTooltip({ anchorX: 331.5, tooltipWidth: 212, ...view });
    expect(left).toBe(331.5 - 8 - 212);
    expect(left).toBeGreaterThanOrEqual(TOOLTIP_EDGE_MARGIN_PX);
    expect(left + 212).toBeLessThanOrEqual(340 - TOOLTIP_EDGE_MARGIN_PX);
  });

  it("left edge: the callout goes right of the crosshair", () => {
    expect(placeChartTooltip({ anchorX: 20, tooltipWidth: 212, ...view })).toBe(28);
  });

  it("fits on neither side: clamped inside the visible window", () => {
    const left = placeChartTooltip({ anchorX: 170, tooltipWidth: 300, ...view });
    expect(left).toBeGreaterThanOrEqual(TOOLTIP_EDGE_MARGIN_PX);
    expect(left + 300).toBeLessThanOrEqual(340 - TOOLTIP_EDGE_MARGIN_PX);
  });

  it("a scrolled plot: placed in the visible window, not the content origin", () => {
    const left = placeChartTooltip({ anchorX: 582, tooltipWidth: 212, viewLeft: 260, viewWidth: 340 });
    expect(left).toBeGreaterThanOrEqual(260 + TOOLTIP_EDGE_MARGIN_PX);
    expect(left + 212).toBeLessThanOrEqual(600 - TOOLTIP_EDGE_MARGIN_PX);
  });

  it("the callout is never wider than the visible window", () => {
    expect(tooltipMaxWidth(340)).toBe(332);
    // Wider than the window (cannot happen once the cap applies): names lead.
    expect(placeChartTooltip({ anchorX: 300, tooltipWidth: 400, ...view })).toBe(TOOLTIP_EDGE_MARGIN_PX);
  });
});

describe("T the host places its callout from the measured window", () => {
  type El = HTMLElement & Record<string, unknown>;
  function descendants(node: HTMLElement): El[] {
    return [node as El, ...Array.from(node.childNodes).flatMap((n) => descendants(n as HTMLElement))];
  }
  function props(node: HTMLElement): Record<string, unknown> {
    const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
    return (node as unknown as Record<string, Record<string, unknown>>)[key];
  }
  const NAMES = ["Cleveland Guardians", "Tampa Bay Rays", "Baltimore Orioles", "Houston Astros", "Detroit Tigers"];
  const FIELD = NAMES.map((name, i) =>
    leg(i + 1, name, Array.from({ length: 21 }, (_, h) => pt(START + h * HOUR, 0.1 + 0.15 * i))),
  );
  const TOOLTIP_WIDTH = 212;

  let host: HTMLElement;
  let root: ReturnType<typeof createRoot>;
  let realCreate: typeof document.createElement;
  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    // The rendered callout width a browser would measure.
    realCreate = document.createElement;
    (document as unknown as Record<string, unknown>).createElement = (tag: string) => {
      const el = realCreate.call(document, tag) as El;
      Object.defineProperty(el, "offsetWidth", { value: TOOLTIP_WIDTH, configurable: true });
      return el;
    };
  });
  afterEach(() => {
    (document as unknown as Record<string, unknown>).createElement = realCreate;
    act(() => root.unmount());
    document.body.removeChild(host);
  });

  function mountAt390() {
    act(() => root.render(<FuturesChart historyData={FIELD} height={200} />));
    const svg = descendants(host).find((n) => n.tagName === "SVG" && props(n)?.onMouseMove)!;
    const scroller = descendants(host).find((n) => typeof props(n)?.onScroll === "function")!;
    // A 390px phone card: the plot compressed to the 340px visible window.
    Object.defineProperty(scroller, "clientWidth", { value: 340, configurable: true });
    scroller.scrollLeft = 0;
    svg.getBoundingClientRect = () => ({ left: 0, width: 340 }) as DOMRect;
    return svg;
  }
  function hover(svg: El, svgX: number) {
    const onMove = props(svg).onMouseMove as (e: unknown) => void;
    act(() => onMove({ clientX: svgX, currentTarget: { getBoundingClientRect: () => ({ left: 0, width: 800 }) } }));
  }
  const tooltipNode = () => descendants(host).find((n) => props(n)?.["data-testid"] === "futures-chart-tooltip")!;
  const crosshairX = () =>
    descendants(host).find((n) => n.tagName === "LINE" && props(n)?.strokeDasharray === "4 2")?.x1;

  it("at the right edge the whole callout sits inside the 340px window", () => {
    const svg = mountAt390();
    hover(svg, 780);
    const tip = tooltipNode();
    const left = parseFloat(String(tip.style.left));
    expect(String(tip.style.left)).toMatch(/px$/);
    expect(tip.style.transform).toBe("none");
    expect(tip.style.maxWidth).toBe("332px");
    expect(left).toBeGreaterThanOrEqual(TOOLTIP_EDGE_MARGIN_PX);
    expect(left + TOOLTIP_WIDTH).toBeLessThanOrEqual(340 - TOOLTIP_EDGE_MARGIN_PX);
    // Every row and its full name is still there — nothing dropped.
    for (const name of NAMES) expect(tip.textContent).toContain(name);
    // The crosshair names the same observation it did; only the callout moved.
    expect(Number(crosshairX())).toBe(780);
  });

  it("SCROLLED phone (the real 390 geometry): placed beside the crosshair inside the visible window", () => {
    // Measured on the built page at 390 (owner fit receipt): the plot keeps its
    // 600px minimum, the card shows 318px of it, scrolled to 282.
    const svg = mountAt390();
    const scroller = descendants(host).find((n) => typeof props(n)?.onScroll === "function")!;
    Object.defineProperty(scroller, "clientWidth", { value: 318, configurable: true });
    scroller.scrollLeft = 282;
    svg.getBoundingClientRect = () => ({ left: 0, width: 600 }) as DOMRect;
    hover(svg, 780); // crosshair at 780/800 of the plot = 585px of content
    const left = parseFloat(String(tooltipNode().style.left));
    expect(left).toBe((780 / 800) * 600 - 8 - TOOLTIP_WIDTH); // beside it, on its left
    expect(left).toBeGreaterThanOrEqual(282 + TOOLTIP_EDGE_MARGIN_PX);
    expect(left + TOOLTIP_WIDTH).toBeLessThanOrEqual(282 + 318 - TOOLTIP_EDGE_MARGIN_PX);
    expect(tooltipNode().style.maxWidth).toBe("310px");
  });

  it("at the left edge it sits right of the crosshair, still inside", () => {
    const svg = mountAt390();
    hover(svg, 60);
    const left = parseFloat(String(tooltipNode().style.left));
    expect(left).toBeCloseTo((60 / 800) * 340 + 8, 5);
    expect(left + TOOLTIP_WIDTH).toBeLessThanOrEqual(340 - TOOLTIP_EDGE_MARGIN_PX);
  });

  it("names wrap, never truncate", () => {
    const svg = mountAt390();
    hover(svg, 400);
    const nameSpans = descendants(tooltipNode()).filter(
      (n) => n.tagName === "SPAN" && String(props(n)?.className ?? "").includes("text-text-secondary"),
    );
    expect(nameSpans).toHaveLength(NAMES.length);
    for (const s of nameSpans) {
      expect(String(props(s).className)).toContain("break-words");
      expect(String(props(s).className)).not.toContain("truncate");
    }
  });
});
