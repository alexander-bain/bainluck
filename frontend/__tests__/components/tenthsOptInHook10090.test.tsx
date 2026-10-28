/**
 * @jest-environment jsdom
 */
/**
 * #10090 — THE OPT-IN IS A LINK ALEX OPENS, AND IT STAYS WITH HIM.
 *
 * `?tenths=fit` turns one-decimal headlines on and remembers it (navigation and
 * reloads keep it); `?tenths=off` turns them off and forgets. With neither, the
 * remembered choice decides, and with none it is OFF. A reader who never opted
 * in costs nothing: the hook writes nothing and re-renders nothing.
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
  it("is OFF with no link and nothing remembered", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("", s)).toBe(false);
    expect(resolveTenthsOptIn("?utm_source=share", s)).toBe(false);
    expect(s.setItem).not.toHaveBeenCalled();
    expect(s.removeItem).not.toHaveBeenCalled();
  });

  it("?tenths=fit turns it on and remembers; a later plain url stays on", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("?tenths=fit", s)).toBe(true);
    expect(s.m.get(TENTHS_STORAGE_KEY)).toBe("fit");
    expect(resolveTenthsOptIn("", s)).toBe(true);
  });

  it("?tenths=off turns it off and forgets", () => {
    const s = memoryStore();
    resolveTenthsOptIn("?tenths=fit", s);
    expect(resolveTenthsOptIn("?tenths=off", s)).toBe(false);
    expect(s.m.has(TENTHS_STORAGE_KEY)).toBe(false);
    expect(resolveTenthsOptIn("", s)).toBe(false);
  });

  it("only `fit` ships: the preview's small/big variants turn nothing on", () => {
    const s = memoryStore();
    expect(resolveTenthsOptIn("?tenths=small", s)).toBe(false);
    expect(resolveTenthsOptIn("?tenths=big", s)).toBe(false);
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
    expect(resolveTenthsOptIn("", throwing)).toBe(false);
    expect(resolveTenthsOptIn("?tenths=fit", throwing)).toBe(true);
    expect(resolveTenthsOptIn("?tenths=off", throwing)).toBe(false);
    expect(resolveTenthsOptIn("?tenths=fit", null)).toBe(true);
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

  it("a reader who never opted in renders once, OFF, and nothing is written", () => {
    window.history.replaceState(null, "", "/events/15332593");
    const setItem = jest.spyOn(Storage.prototype, "setItem");
    act(() => root.render(<Probe />));
    expect(renders).toEqual([false]);
    expect(host.textContent).toBe("off");
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  it("the link turns it on after first paint, and a reload without it stays on", () => {
    window.history.replaceState(null, "", "/events/15332593?tenths=fit");
    act(() => root.render(<Probe />));
    // First paint is today's (the server render cannot see the store).
    expect(renders[0]).toBe(false);
    expect(host.textContent).toBe("on");

    act(() => root.unmount());
    renders = [];
    root = createRoot(host);
    window.history.replaceState(null, "", "/events/15337684");
    act(() => root.render(<Probe />));
    expect(host.textContent).toBe("on");
  });
});
