/** @jest-environment jsdom */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { FuturesChart } from "@/components/FuturesChart";
import type { FuturesOutcomeHistory } from "@/lib/types";

const history: FuturesOutcomeHistory[] = [
  {
    outcome_id: 1,
    name: "Leader",
    history: [
      {
        timestamp: "2026-11-03T20:00:00Z",
        probability: 0.2,
        american_odds: null,
        bookmaker: "kalshi",
      },
      {
        timestamp: "2026-11-03T21:00:00Z",
        probability: 0.8,
        american_odds: null,
        bookmaker: "kalshi",
      },
    ],
  },
];
let root: Root;
let host: HTMLDivElement;
const originalWidth = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "clientWidth",
);

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => 326,
  });
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  if (originalWidth)
    Object.defineProperty(HTMLElement.prototype, "clientWidth", originalWidth);
  else Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
});

test("preview opt-in fits both timeline endpoints without shrinking the requested height or axis", () => {
  act(() =>
    root.render(
      <FuturesChart
        historyData={history}
        height={380}
        fitToContainer
        showLegend={false}
      />,
    ),
  );
  const svg = host.querySelector("svg")!;
  expect(svg.getAttribute("viewBox")).toBe("0 0 326 380");
  expect(svg.classList.contains("min-w-[600px]")).toBe(false);
  expect(host.textContent).toContain("100%");
  expect(host.textContent).toContain("0%");
  // The final reading remains in the fitted plot rather than outside a
  // phone's visible window. The existing 20px right inset is preserved.
  expect(
    [...svg.querySelectorAll("path")].some((path) =>
      [
        ...(path.getAttribute("d") ?? "").matchAll(
          /[ML]\s+([\d.]+)\s+([\d.]+)/g,
        ),
      ].some(
        (point) =>
          Math.abs(Number(point[1]) - 306) < 0.01 &&
          Math.abs(Number(point[2]) - 84) < 0.01,
      ),
    ),
  ).toBe(true);
});

test("existing callers retain their scrollable geometry", () => {
  act(() =>
    root.render(
      <FuturesChart historyData={history} height={380} showLegend={false} />,
    ),
  );
  const svg = host.querySelector("svg")!;
  expect(svg.getAttribute("viewBox")).toBe("0 0 800 380");
  expect(svg.classList.contains("min-w-[600px]")).toBe(true);
});
