import "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import fixture from "../fixtures/golfCurrentPrices8222.json";
import { EvolutionView } from "@/components/EvolutionView";

let detail: typeof fixture.detail | undefined;
let detailError: Error | undefined;
let detailLoading = false;
const mockKeys: unknown[] = [];
jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    mockKeys.push(key);
    return Array.isArray(key)
      ? { data: detail, error: detailError, isLoading: detailLoading }
      : { data: fixture.history, error: undefined, isLoading: false };
  },
}));

function descendants(node: HTMLElement): HTMLElement[] {
  return [node, ...Array.from(node.childNodes).flatMap((n) => descendants(n as HTMLElement))];
}
function props(node: HTMLElement): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return (node as unknown as Record<string, Record<string, (arg?: unknown) => void>>)[key];
}
let host: HTMLElement;
let root: ReturnType<typeof createRoot>;
function render(requireCurrentPrices = true, multi = false) {
  act(() => root.render(<EvolutionView marketId={fixture.detail.id} defaultTopN={9}
    requireCurrentPrices={requireCurrentPrices}
    positionOptions={multi ? [{key: "win", label: "Win", marketId: fixture.detail.id, marketIds: [fixture.detail.id, 2]}] : undefined} />));
}
function paths() {
  return descendants(host).filter((n) => n.tagName === "PATH").map((n) => props(n)?.d);
}
function selectBurke() {
  const input = descendants(host).find((n) => n.tagName === "INPUT" && props(n).placeholder)!;
  act(() => props(input).onChange({ target: { value: "Burke" } }));
  const button = descendants(host).find((n) => n.tagName === "BUTTON" && n.textContent?.includes("Burke"))!;
  expect(button.textContent).toContain("Unavailable now");
  act(() => props(button).onClick());
}

beforeEach(() => {
  jest.spyOn(Date, "now").mockReturnValue(Date.parse(fixture.captured_at));
  detail = structuredClone(fixture.detail);
  detailError = undefined;
  detailLoading = false;
  mockKeys.length = 0;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); document.body.removeChild(host); jest.restoreAllMocks(); });

it("retained current payload defaults exclude only Burke/Kimsey, preserving Rose/Jordan and leaders", () => {
  render();
  expect(host.textContent).not.toContain("Burke");
  expect(host.textContent).not.toContain("Kimsey");
  for (const name of ["Rose", "Jordan", "Fleetwood", "MacIntyre"]) expect(host.textContent).toContain(name);
  expect(host.textContent).toContain("7 of 9");
  expect(mockKeys).toContainEqual(["futures-market", fixture.detail.id]);
});

it("controlled earlier four-refused shape excludes all four, without pretending it is today's payload", () => {
  for (const o of detail!.outcomes) if ([236001245,236001194,236001145,236001195].includes(o.id)) o.probability = null;
  render();
  for (const name of ["Rose", "Jordan", "Burke", "Kimsey"]) expect(host.textContent).not.toContain(name);
  expect(host.textContent).toContain("5 of 9");
});

it("manual selection keeps unavailable history drawable and labeled, preserving every source point", () => {
  const before = JSON.stringify(fixture.history);
  render();
  const initialPaths = paths();
  selectBurke();
  expect(host.textContent).toContain("Burke");
  expect(host.textContent).toContain("Unavailable now");
  expect(paths().length).toBeGreaterThan(initialPaths.length);
  const withUnavailable = paths();
  // Making current support available changes neither selected chart data nor SVG geometry.
  detail = structuredClone(detail!);
  detail.outcomes.find((o) => o.id === 236001145)!.probability = 0.046;
  render();
  expect(paths()).toEqual(withUnavailable);
  expect(host.textContent).not.toContain("Unavailable now");
  expect(JSON.stringify(fixture.history)).toBe(before);
});

it("a legitimate zero remains selectable by default", () => {
  detail!.outcomes.find((o) => o.id === 236001145)!.probability = 0;
  render();
  expect(host.textContent).toContain("Burke");
  expect(host.textContent).toContain("8 of 9");
});

it.each(["missing", "error", "sibling", "missing outcome"])("does not infer current support from historical tails with %s detail", (state) => {
  if (state === "missing") detail = undefined;
  if (state === "error") detailError = new Error("offline");
  if (state === "sibling") detail!.id = 2;
  if (state === "missing outcome") detail!.outcomes = [];
  render();
  expect(host.textContent).toContain("0 of 9");
  selectBurke();
  expect(host.textContent).toContain("Unavailable now");
});

it("waits for canonical current detail before showing defaults", () => {
  detail = undefined; detailLoading = true; render();
  expect(host.textContent).toContain("Loading odds history");
  expect(host.textContent).not.toContain("Rose");
});

it.each([false, true])("keeps existing non-opt-in/multi-market behavior (multi=%s)", (multi) => {
  render(multi, multi);
  expect(host.textContent).toContain("9 of 9");
  expect(host.textContent).toContain("Burke");
  expect(mockKeys.some(Array.isArray)).toBe(false);
});
