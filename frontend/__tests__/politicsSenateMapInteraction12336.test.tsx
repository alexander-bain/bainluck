/** @jest-environment jsdom */

import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import type { PoliticsData } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: payload, error: undefined }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

import PoliticsPage from "@/app/politics/page";

let payload: PoliticsData;
let root: Root;
let host: HTMLDivElement;

function renderPage() {
  act(() => root.render(<PoliticsPage />));
}

function stateButton(label: string): HTMLButtonElement {
  const button = host.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
  if (!button) throw new Error(`Missing state button ${label}`);
  return button;
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  payload = {
    total_markets: 1,
    updated_at: "2026-11-02T18:00:00+00:00",
    themes: {
      presidential: {
        count: 0, headline_q: null, candidates: [], has_dual_source: false,
        kalshi_market_id: null, poly_market_id: null, side_markets: [],
      },
      congressional: {
        count: 1, markets: [], chamber_control: { senate: null, house: null },
        senate_map: { AK: 97.4 },
      },
      gubernatorial: { count: 0, markets: [] },
      policy: { count: 0, markets: [] },
      scotus: { count: 0, markets: [] },
      international: { count: 0, markets: [] },
      other: { count: 0, markets: [] },
    },
    cross_source: [], by_source: { kalshi: 1, polymarket: 0 },
  };
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

test("one-state copy and a touch selection reveal the state's served probability", () => {
  renderPage();
  expect(host.textContent).toContain("1 state with Senate race data · Select a state for detail");
  expect(host.textContent).not.toContain("Hover for detail");
  act(() => stateButton("AK, 97% Democratic probability").click());
  expect(host.textContent).toContain("AK — Dem prob 97%");
  expect(stateButton("ME, no race data").disabled).toBe(true);
});

test("keyboard focus reveals detail and multiple states use plural copy", () => {
  payload.themes.congressional!.senate_map = { AK: 97.4, ME: 62 };
  renderPage();
  act(() => stateButton("ME, 62% Democratic probability").focus());
  expect(host.textContent).toContain("ME — Dem prob 62%");
  expect(host.textContent).toContain("2 states with Senate race data · Select a state for detail");
});

test("a retired map renders no empty grid", () => {
  payload.themes.congressional!.senate_map = null;
  renderPage();
  expect(host.textContent).not.toContain("Senate races by state");
  expect(host.querySelector("button[aria-label*='no race data']")).toBeNull();
});
