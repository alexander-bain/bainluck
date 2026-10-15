/**
 * #683 — ON THE CHART, a point recovered from Kalshi's archive says so.
 *
 * `archiveHistory683.test.ts` proves the words. This proves the WIRING in
 * `FuturesChart`, the kernel every web `/history` and `/multi-history` reader
 * draws through (the futures page's Probability Trend, EvolutionView and the
 * event/golf charts built on it): the caption renders from the DRAWN points
 * only, and the hover tooltip names the archive for the row it reads.
 *
 * Fixtures follow calibration's documented additive contract (PR #11083 head
 * e882cb665b, unpublished). Controls: the same series with the archive markers
 * removed renders no caption and no tooltip line.
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";

import { FuturesChart } from "@/components/FuturesChart";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const START = Date.UTC(2026, 2, 2, 0, 0, 0);
const NOW = Date.UTC(2026, 9, 15, 20, 0, 0);

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

function archive(i: number, basis = "traded_interval"): FuturesHistoryPoint {
  const close = START + (i + 1) * HOUR;
  return {
    timestamp: new Date(close).toISOString(),
    probability: 0.3 + (i % 5) * 0.02,
    american_odds: null,
    bookmaker: "kalshi_archive",
    provenance: "kalshi_archive",
    interval_start: new Date(close - HOUR).toISOString(),
    period_minutes: 60,
    price_basis: basis,
  };
}
function live(atMs: number): FuturesHistoryPoint {
  return { timestamp: new Date(atMs).toISOString(), probability: 0.5, american_odds: null, bookmaker: "consensus" };
}
function unmarked(p: FuturesHistoryPoint): FuturesHistoryPoint {
  return { timestamp: p.timestamp, probability: p.probability, american_odds: null, bookmaker: "consensus" };
}

const archiveOnly = Array.from({ length: 48 }, (_, i) => archive(i));
const yes = (history: FuturesHistoryPoint[]): FuturesOutcomeHistory => ({ outcome_id: 1, name: "Yes", history });
const no = (history: FuturesHistoryPoint[]): FuturesOutcomeHistory => ({ outcome_id: 2, name: "No", history });

describe("#683 the archive caption", () => {
  it("a settled zero-snapshot outcome drawn only from the archive carries the caption", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={[yes(archiveOnly)]} settled />);
    expect(html).toContain('data-testid="futures-chart-archive"');
    expect(html).toContain('data-archive-points="48"');
    expect(html).toContain("this line is hourly trade prices recovered from Kalshi");
    expect(html).not.toContain("kalshi_archive<");
  });

  it("CONTROL: the same points without the archive markers render no caption", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={[yes(archiveOnly.map(unmarked))]} settled />);
    expect(html).not.toContain("futures-chart-archive");
    expect(html).not.toContain("Kalshi&#x27;s records");
  });

  it("live captures interleaved inside the archive span make it 'Some points'", () => {
    const mixed = [...archiveOnly, live(START + 10.5 * HOUR)].sort(
      (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
    );
    const html = renderToStaticMarkup(<FuturesChart historyData={[yes(mixed)]} />);
    expect(html).toContain("Some points from");
  });

  it("reads only the series the legend draws: deselecting the archive line removes the caption", () => {
    const liveNo = Array.from({ length: 48 }, (_, i) => live(START + (i + 1) * HOUR));
    const drawnBoth = renderToStaticMarkup(
      <FuturesChart historyData={[yes(archiveOnly), no(liveNo)]} selectedOutcomes={new Set([1, 2])} />,
    );
    expect(drawnBoth).toContain('data-archive-points="48"');
    const liveOnly = renderToStaticMarkup(
      <FuturesChart historyData={[yes(archiveOnly), no(liveNo)]} selectedOutcomes={new Set([2])} />,
    );
    expect(liveOnly).not.toContain("futures-chart-archive");
  });

  it("a mini sparkline prints no sentence (no axes to qualify), like the freshness note", () => {
    const html = renderToStaticMarkup(<FuturesChart historyData={[yes(archiveOnly)]} mini />);
    expect(html).not.toContain("futures-chart-archive");
  });
});

describe("#683 the hover tooltip names the archive for the row it reads", () => {
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
  function tooltipLine(host: HTMLElement): string | null {
    const node = descendants(host).find(
      (n) => n.tagName === "DIV" && props(n)?.["data-testid" as never] === ("futures-chart-archive-tooltip" as never),
    );
    return node ? node.textContent : null;
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

  // Archive for the first 48 hours, then our own live captures for 48 more.
  const history = [
    ...archiveOnly,
    ...Array.from({ length: 48 }, (_, i) => live(START + (49 + i) * HOUR)),
  ];

  it("over the archive stretch: 'From Kalshi's hourly record'; over live captures: nothing", () => {
    act(() => root.render(<FuturesChart historyData={[yes(history)]} />));
    hoverAt(host, 60); // just inside the left padding — the first archive interval
    expect(host.textContent).toContain("%");
    expect(tooltipLine(host)).toBe("From Kalshi's hourly record");
    hoverAt(host, 770); // just inside the right padding — the newest live capture
    expect(host.textContent).toContain("%");
    expect(tooltipLine(host)).toBeNull();
  });

  it("quote-only intervals add 'no trades'", () => {
    const quotes = Array.from({ length: 48 }, (_, i) => archive(i, "quote_only"));
    act(() => root.render(<FuturesChart historyData={[yes(quotes)]} />));
    hoverAt(host, 60);
    expect(tooltipLine(host)).toBe("From Kalshi's hourly record · no trades");
  });

  it("CONTROL: the same points without the markers show no tooltip line", () => {
    act(() => root.render(<FuturesChart historyData={[yes(history.map(unmarked))]} />));
    hoverAt(host, 60);
    expect(host.textContent).toContain("%");
    expect(tooltipLine(host)).toBeNull();
  });
});
