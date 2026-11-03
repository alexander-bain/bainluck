/** @jest-environment jsdom */
/**
 * Election night: once the API serves a graded Midterms card, the open
 * collection page shows "Settled - <winner>" on its next 30 s refresh, with no
 * reload, focus or tap.
 *
 * The page is mounted with the real CollectionHub, the real fetchCollection
 * (stubbed fetch only) and the real refresh interval, on a fake clock. The
 * served snapshot is the reviewed production fixture; the graded card is that
 * snapshot's card in the exact shape `blend_card` serves after an official
 * venue result (status "resolved", `settled_winner`, every price null, one
 * `is_winner`, `resolution_source: "api_settlement"`), guarded on the backend by
 * tests/test_midterms_kalshi_grade_reaches_served_card.py.
 */
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import snapshot from "./fixtures/midterms2026Presentation.json";

jest.mock("@/lib/api", () => ({ ...jest.requireActual("@/lib/api"), API_URL: "http://fixture.invalid" }));
jest.mock("@/components/Analytics", () => ({ useAnalyticsContext: () => ({ track: () => {} }) }));
jest.mock("@/components/EntityImage", () => ({ __esModule: true, default: () => null }));

import CollectionHub from "@/components/collections/CollectionHub";
import { forgetAcceptedCollections } from "@/lib/collections";

const REFRESH_MS = 30000;
type Outcome = { name: string; probability: number | null; is_winner?: boolean | null; resolution_source?: string | null };
type Card = { id: number; status: string; settled_winner?: string; top_outcomes: Outcome[] };
type Payload = { sections: { members: { id: number; card: Card }[] }[] };

const open = (): Payload => JSON.parse(JSON.stringify(snapshot));
function graded(id: number, winner: string): Payload {
  const payload = open();
  const card = payload.sections.flatMap((s) => s.members).find((m) => m.id === id)!.card;
  Object.assign(card, { status: "resolved", settled_winner: winner });
  card.top_outcomes = card.top_outcomes.map((o) => ({ ...o, probability: null, is_winner: o.name === winner, resolution_source: "api_settlement" }));
  return payload;
}

let served: Payload;
let fetchMock: jest.Mock;
let container: HTMLDivElement;
let root: Root;

// The page's own collection reads; the party row's chart history is not one.
const reads = () => fetchMock.mock.calls.filter((c) => String(c[0]).endsWith("/api/containers/midterms-2026")).length;
const flush = async () => { for (let i = 0; i < 5; i += 1) await act(async () => { await Promise.resolve(); }); };
const member = (id: number) => container.querySelector(`[data-collection-member="market:${id}"]`)?.textContent ?? "";

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  forgetAcceptedCollections();
  jest.useFakeTimers();
  served = open();
  fetchMock = jest.fn(async (url: string) => (String(url).endsWith("/api/containers/midterms-2026")
    ? { status: 200, ok: true, json: async () => JSON.parse(JSON.stringify(served)) }
    : { status: 404, ok: false, json: async () => null }));  // chart history: absent
  global.fetch = fetchMock as unknown as typeof fetch;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  jest.useRealTimers();
});

// One market per layout the collection draws: party control, the balance
// field, a Senate duel, and the two governors-section shapes (field, Yes/No).
test.each([
  [108620, "Republican Party", null],
  [108619, "Republicans sweep", 108619],
  [109082, "Susan Collins", 109082],
  [108629, "Kansas", 108629],
  [109918, "Yes", 109918],
])("market %i graded %s shows Settled on the next refresh", async (id, winner, cardId) => {
  await act(async () => { root.render(<CollectionHub slug="midterms-2026" />); });
  await flush();
  expect(reads()).toBe(1);
  expect(container.textContent).not.toContain("Settled -");
  if (cardId) expect(member(cardId)).toMatch(/\d+%/);

  // Kalshi grades the market; the next read serves the graded card.
  served = graded(id, winner);
  await act(async () => { jest.advanceTimersByTime(REFRESH_MS - 1); });
  await flush();
  expect(reads()).toBe(1);
  expect(container.textContent).not.toContain("Settled -");

  await act(async () => { jest.advanceTimersByTime(1); });
  await flush();
  expect(reads()).toBe(2);
  expect(container.textContent).toContain(`Settled - ${winner}`);
  if (cardId) {
    expect(member(cardId)).toContain(`Settled - ${winner}`);
    expect(member(cardId)).not.toMatch(/\d+%/);
  }

  // The rest of the night is still live, so the page keeps its 30 s clock.
  await act(async () => { jest.advanceTimersByTime(REFRESH_MS); });
  await flush();
  expect(reads()).toBe(3);
});
