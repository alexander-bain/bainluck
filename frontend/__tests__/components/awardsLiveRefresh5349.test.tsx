/** @jest-environment jsdom */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { SWRConfig } from "swr";
import sourceFixture from "../fixtures/awardsCategoryTruth5349.SYNTHETIC.json";
import type { EventConceptResponse } from "@/lib/types";
jest.mock("next/navigation", () => ({ useParams: () => ({ domain: "awards", slug: "oscars-2026" }), useRouter: () => ({ replace: () => {} }) }));
jest.mock("next/link", () => ({ __esModule: true, default: ({ children, ...props }: { children: React.ReactNode }) => <a {...props}>{children}</a> }));
jest.mock("@/hooks", () => ({ usePageTracking: () => {}, useScrollDepth: () => {}, useEngagementTime: () => {} }));
const mockRead = jest.fn();
jest.mock("@/lib/api", () => ({ fetchEventConcept: (key: string) => mockRead(key), fetchFuturesHistory: () => Promise.resolve(null), formatProbability: (p: number | null) => p == null ? "—" : `${Math.round(p * 100)}%` }));
import EventConceptPage from "@/app/event/[domain]/[slug]/page";
let root: Root; let host: HTMLDivElement;
const NOW = Date.UTC(2026, 9, 12, 12);
const fresh = (): EventConceptResponse => JSON.parse(JSON.stringify(sourceFixture));
beforeEach(() => { (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true; jest.useFakeTimers({ now: NOW }); Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }); host = document.createElement("div"); document.body.append(host); root = createRoot(host); mockRead.mockReset(); });
afterEach(() => { act(() => root.unmount()); host.remove(); jest.useRealTimers(); });
const tick = async (ms: number) => { await act(async () => { jest.advanceTimersByTime(ms); await Promise.resolve(); }); };
test("real SWR starts after initial missing data, admits a category announcement, and stops at the reader limit", async () => {
  const base = fresh(); const announced = fresh(); const category = announced.children.find((child) => child.market_id === 2)!;
  category.settled = true; category.graded_winner = "Another director"; category.outcomes![1].won = true;
  mockRead.mockResolvedValueOnce(base).mockResolvedValue(announced);
  const cache = new Map();
  await act(async () => { root.render(<SWRConfig value={{ provider: () => cache, dedupingInterval: 0 }}><EventConceptPage /></SWRConfig>); await Promise.resolve(); });
  expect(mockRead).toHaveBeenCalledTimes(1); expect(host.querySelector("#awards-category-2")?.textContent).toContain("Not announced");
  await tick(30000);
  expect(mockRead).toHaveBeenCalledTimes(2); expect(host.querySelector("#awards-category-2")?.textContent).toContain("Winner"); expect(host.querySelector("#awards-category-2")?.textContent).toContain("Another director");
  expect(host.querySelector("#awards-category-3")?.textContent).toContain("Result not yet confirmed");
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" }); await tick(30000); expect(mockRead).toHaveBeenCalledTimes(2);
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  // Advance at most one native interval at a time so async revalidation settles.
  for (let i = 0; i < 60; i++) await tick(30000);
  const count = mockRead.mock.calls.length; await tick(30000); expect(mockRead).toHaveBeenCalledTimes(count);
});
