/**
 * @jest-environment jsdom
 */
/**
 * #10090 — TENTHS ARE ON BY DEFAULT; `?tenths=off` IS A LINK A READER OPENS,
 * AND IT STAYS WITH THEM.
 *
 * With no link and nothing remembered, tenths are ON from the first render (the
 * plain event URL in a fresh browser prints tenths; the A6 recorder refuses
 * query strings) and the hook writes nothing and re-renders nothing.
 * `?tenths=off` turns them off and remembers it (navigation and reloads keep
 * it); `?tenths=fit` turns them back on and forgets the opt-out.
 */
import React from "react";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react-dom/test-utils";

import { TENTHS_STORAGE_KEY, resolveTenthsOptIn, useTenthsOptIn } from "@/lib/tenthsOptIn";

function memoryStore() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: jest.fn((k: string, v: string) => void m.set(k, v)),
    removeItem: jest.fn((k: string) => void m.delete(k)),
    m,
  };
}

describe("#10090 resolveTenthsOptIn", () => {
  it("is ON with no link and nothing remembered, and writes nothing", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("", s)).toBe(true);
    expect(resolveTenthsOptIn("?utm_source=share", s)).toBe(true);
    expect(s.setItem).not.toHaveBeenCalled();
    expect(s.removeItem).not.toHaveBeenCalled();
  });

  it("?tenths=off turns it off and remembers; a later plain url stays off", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("?tenths=off", s)).toBe(false);
    expect(s.m.get(TENTHS_STORAGE_KEY)).toBe("off");
    expect(resolveTenthsOptIn("", s)).toBe(false);
  });

  it("?tenths=fit turns it back on and forgets the opt-out", () => {
    const s = memoryStore();
    resolveTenthsOptIn("?tenths=off", s);
    expect(resolveTenthsOptIn("?tenths=fit", s)).toBe(true);
    expect(s.m.has(TENTHS_STORAGE_KEY)).toBe(false);
    expect(resolveTenthsOptIn("", s)).toBe(true);
  });

  it("a reader who opted in under the old default stays on", () => {
    const s = memoryStore();
    s.m.set(TENTHS_STORAGE_KEY, "fit");
    expect(resolveTenthsOptIn("", s)).toBe(true);
  });

  it("only `off` turns it off: other values leave the default on", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("?tenths=small", s)).toBe(true);
    expect(resolveTenthsOptIn("?tenths=0", s)).toBe(true);
    expect(s.setItem).not.toHaveBeenCalled();
  });

  it("a store that throws reads as nothing remembered, and the link still works", () => {
    const throwing = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: () => {
        throw new Error("SecurityError");
      },
    };
    expect(resolveTenthsOptIn("", throwing)).toBe(true);
    expect(resolveTenthsOptIn("?tenths=fit", throwing)).toBe(true);
    expect(resolveTenthsOptIn("?tenths=off", throwing)).toBe(false);
    expect(resolveTenthsOptIn("?tenths=off", null)).toBe(false);
    expect(resolveTenthsOptIn("", null)).toBe(true);
  });
});

describe("#10090 useTenthsOptIn", () => {
  let host: HTMLDivElement;
  let root: Root;
  let renders: boolean[];
  function Probe() {
    const on = useTenthsOptIn();
    renders.push(on);
    return <span>{on ? "on" : "off"}</span>;
  }
  beforeEach(() => {
    (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    window.localStorage.clear();
    renders = [];
    host = document.createElement("div");
    root = createRoot(host);
  });
  afterEach(() => {
    act(() => root.unmount());
    window.history.replaceState(null, "", "/");
  });

  it("a fresh browser on the plain url renders once, ON, and nothing is written", () => {
    window.history.replaceState(null, "", "/events/15332593");
    const setItem = jest.spyOn(Storage.prototype, "setItem");
    act(() => root.render(<Probe />));
    expect(renders).toEqual([true]);
    expect(host.textContent).toBe("on");
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it("?tenths=off turns it off after first paint, and a reload without it stays off", () => {
    window.history.replaceState(null, "", "/events/15332593?tenths=off");
    act(() => root.render(<Probe />));
    // First paint is the server render's (it cannot see the store).
    expect(renders[0]).toBe(true);
    expect(host.textContent).toBe("off");

    act(() => root.unmount());
    renders = [];
    root = createRoot(host);
    window.history.replaceState(null, "", "/events/15337684");
    act(() => root.render(<Probe />));
    expect(host.textContent).toBe("off");
  });
});
