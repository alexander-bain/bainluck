/**
 * #10090 Alex 67 — "I say yes to the extras."
 *
 *   1. TAP THE EKG FOR THE EXACT TIMES. The heartbeat is a labelled button that
 *      opens the SAME panel the chart's status opens (observed, confirmed and
 *      score times, each with its time zone; "Time unavailable", never a guess).
 *      One model, two places (#8336, #4469). Escape closes and focus returns.
 *   2. THE CHART'S STATUS SPEAKS ONLY WHEN SOMETHING IS WRONG. While the EKG is
 *      showing, a healthy socket draws no status; reconnecting, an old price or
 *      score, a finish, or no EKG (`?ekg=0`) keep today's words. The live
 *      region stays mounted, so trouble is still announced.
 *
 * The button is MOUNTED on `helpers/minimalDom` (no jsdom here), driven the way
 * `liveConnectionStatus9655.test.tsx` drives the status: React's own onClick,
 * and the document listeners captured and called. Part 2 on the real page is
 * `__tests__/ekgQuietStatusPageAlex67.test.tsx`.
 */
import "../helpers/minimalDom";
import React, { act } from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot, type Root } from "react-dom/client";

import EkgTimesButton from "@/components/event/EkgTimesButton";
import { connectionStatusIsHealthy } from "@/lib/event/liveConnectionStatus";

const NOW = Date.UTC(2026, 9, 2, 20, 0, 0);
const OBSERVED_AT = new Date(NOW - 8_000).toISOString();
const CONFIRMED_AT = new Date(NOW - 2_000).toISOString();
const SCORE_AT = new Date(NOW - 7 * 60_000).toISOString();

type Props = React.ComponentProps<typeof EkgTimesButton>;
function props(over: Partial<Props> = {}): Props {
  return {
    children: <span role="img" aria-label="Markets reporting: last update 2 seconds ago" />,
    priceObservedAt: OBSERVED_AT,
    priceConfirmedAt: CONFIRMED_AT,
    scoreShown: true,
    scoreConfirmedAt: SCORE_AT,
    oldestFact: "score",
    now: NOW,
    ...over,
  };
}

type N = { tagName?: string; childNodes: N[]; textContent: string; [k: string]: unknown };
function find(node: N, pred: (n: N) => boolean): N | null {
  if (pred(node)) return node;
  for (const c of node.childNodes ?? []) {
    const hit = find(c, pred);
    if (hit) return hit;
  }
  return null;
}
const reactProps = (node: N) =>
  node[Object.keys(node).find((k) => k.startsWith("__reactProps"))!] as Record<string, (...a: unknown[]) => void>;

const listeners = new Map<string, Set<(e: unknown) => void>>();
const doc = document as unknown as Record<string, unknown>;
doc.addEventListener = (type: string, fn: (e: unknown) => void) => {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type)!.add(fn);
};
doc.removeEventListener = (type: string, fn: (e: unknown) => void) => {
  listeners.get(type)?.delete(fn);
};
const send = (type: string, e: unknown) => {
  for (const fn of [...(listeners.get(type) ?? [])]) fn(e);
};

function mount(p: Props) {
  const host = (document as unknown as { createElement: (t: string) => N }).createElement("div");
  (document as unknown as { body: { appendChild: (n: N) => void } }).body.appendChild(host);
  const root: Root = createRoot(host as unknown as Element);
  act(() => root.render(<EkgTimesButton {...p} />));
  const wrapper = find(host, (n) => n["data-testid"] === "ekg-times")!;
  const button = find(host, (n) => n.tagName === "BUTTON")!;
  const panel = () => find(host, (n) => n.tagName === "DIV" && n.id === button["aria-controls"])!;
  let focused = false;
  button.focus = () => { focused = true; };
  wrapper.contains = (t: unknown) => find(wrapper, (n) => n === t) !== null;
  return {
    button, panel,
    focused: () => focused,
    click: () => act(() => reactProps(button).onClick({})),
    unmount: () => act(() => root.unmount()),
  };
}

describe("Alex 67 — tap the EKG for the exact times", () => {
  it("is a labelled, collapsed button wrapping the heartbeat", () => {
    const html = renderToStaticMarkup(<EkgTimesButton {...props()} />);
    expect(html).toMatch(/<button type="button" aria-expanded="false" aria-controls="[^"]+"/);
    expect(html).toContain('aria-label="Markets reporting: last update 2 seconds ago"');
    expect(html).toContain('<span class="sr-only">, show update times</span>');
    const id = html.match(/aria-controls="([^"]+)"/)![1];
    expect(html).toContain(`<div id="${id}" hidden=""`);
  });

  it("a tap opens the panel with the observed, confirmed and score rows, each zoned", () => {
    const m = mount(props());
    try {
      expect(m.panel().hidden).toBe("");
      m.click();
      expect(m.button["aria-expanded"]).toBe("true");
      expect(m.panel().hidden).toBeUndefined();
      const text = m.panel().textContent;
      expect(text).toContain("Probability observedOct 2, 7:59:52.000 PM UTC · 8s ago");
      expect(text).toContain("Probability confirmedOct 2, 7:59:58 PM UTC · 2s ago");
      expect(text).toContain("Score confirmedOct 2, 7:53:00 PM UTC · 7m ago");
      m.click();
      expect(m.button["aria-expanded"]).toBe("false");
    } finally {
      m.unmount();
    }
  });

  it("Escape closes it and returns focus to the button", () => {
    const m = mount(props());
    try {
      m.click();
      act(() => send("keydown", { key: "Enter" }));
      expect(m.button["aria-expanded"]).toBe("true");
      act(() => send("keydown", { key: "Escape" }));
      expect(m.button["aria-expanded"]).toBe("false");
      expect(m.focused()).toBe(true);
      expect(listeners.get("keydown")?.size ?? 0).toBe(0);
    } finally {
      m.unmount();
    }
  });

  it("opens fixed, centred under the EKG and inside the screen — never in the clipped hero column", () => {
    // Photographed at 390px: hung from the hero's middle column the panel was
    // 30px wide and cut off by the card's overflow. It measures the button.
    const win = window as unknown as Record<string, unknown>;
    const winListeners = new Map<string, Set<() => void>>();
    win.innerWidth = 390;
    win.addEventListener = (t: string, fn: () => void) => {
      if (!winListeners.has(t)) winListeners.set(t, new Set());
      winListeners.get(t)!.add(fn);
    };
    win.removeEventListener = (t: string, fn: () => void) => void winListeners.get(t)?.delete(fn);
    const m = mount(props());
    try {
      m.button.getBoundingClientRect = () => ({ left: 168, width: 54, top: 190, bottom: 214 });
      m.click();
      const panel = m.panel();
      expect(String(panel["class"])).toMatch(/^fixed z-20 /);
      const style = panel.style as unknown as Record<string, string>;
      // 320 wide, centred on the button's centre (195): 35..355, 12px clear of each edge at 390.
      expect(style).toMatchObject({ top: "218px", left: "35px", width: "320px" });
      // A narrow screen keeps 12px either side.
      m.click();
      win.innerWidth = 320;
      m.button.getBoundingClientRect = () => ({ left: 250, width: 54, top: 190, bottom: 214 });
      m.click();
      expect(m.panel().style as unknown as Record<string, string>).toMatchObject({ left: "12px", width: "296px" });
      // A scroll closes it rather than leaving it behind the EKG.
      expect(winListeners.get("scroll")?.size).toBe(1);
      act(() => { for (const fn of [...winListeners.get("scroll")!]) fn(); });
      expect(m.button["aria-expanded"]).toBe("false");
      expect(winListeners.get("scroll")?.size ?? 0).toBe(0);
    } finally {
      m.unmount();
    }
  });

  it("an absent or unreadable clock says Time unavailable, never a guess", () => {
    const html = renderToStaticMarkup(
      <EkgTimesButton {...props({ priceObservedAt: null, priceConfirmedAt: null, scoreConfirmedAt: "garbage" })} />,
    );
    expect(html.split("Time unavailable").length - 1).toBe(2);
  });

  it("is the same panel, not a copy: one definition, imported by both", () => {
    const button = readFileSync(join(process.cwd(), "components/event/EkgTimesButton.tsx"), "utf8");
    const status = readFileSync(join(process.cwd(), "components/event/LiveConnectionStatus.tsx"), "utf8");
    expect(button).toContain("ConnectionTimesPanel");
    expect(button).toContain("useTimesDisclosure");
    expect(button).not.toContain("<dl");
    expect(button).not.toContain("Probability observed");
    expect(status.split("<dl").length - 1).toBe(1);
    expect(status).toContain("<ConnectionTimesPanel id={detailsId}");
  });
});

describe("Alex 67 — healthy, by the model's own inputs", () => {
  const ok = { terminalLabel: null, priceMayBeOld: false, scoreMayBeOld: false };
  it("open, quiet and a scheduled rollover are healthy", () => {
    for (const status of ["open", "quiet", "rollover"] as const) {
      expect(connectionStatusIsHealthy({ ...ok, status })).toBe(true);
    }
  });
  it("reconnecting, connecting and checking are not", () => {
    for (const status of ["retrying", "connecting", "unavailable", "closed", "idle"] as const) {
      expect(connectionStatusIsHealthy({ ...ok, status })).toBe(false);
    }
  });
  it("a terminal label or old evidence outranks an open socket", () => {
    expect(connectionStatusIsHealthy({ ...ok, status: "open", terminalLabel: "Finished" })).toBe(false);
    expect(connectionStatusIsHealthy({ ...ok, status: "open", priceMayBeOld: true })).toBe(false);
    expect(connectionStatusIsHealthy({ ...ok, status: "quiet", scoreMayBeOld: true })).toBe(false);
  });
});
