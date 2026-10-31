/**
 * #10090 — THE EVENT PAGE'S HEARTBEAT ("EKG"): ON BY DEFAULT (Alex decision 66),
 * AND IT BEATS ON WHAT THE STREAM ACTUALLY DELIVERS.
 *
 * Three things are proven here; the decision itself is
 * `__tests__/lib/ekgHeartbeat10090.test.ts`.
 *
 *   1. The reader's choice: ON with nothing remembered; `?ekg=0` turns it off
 *      and remembers that; `?ekg=1` turns it back on.
 *   2. The drawing: beating / flat / interrupted, the screen-reader label, and
 *      a beat that replays (a new path per beat).
 *   3. Through the REAL `useLiveEventStream` over a fake EventSource: a heartbeat
 *      whose `confirmed_at` advances beats; the keep-alive that repeats it does
 *      not; silence goes flat; an error never beats. And the page wiring that
 *      feeds the tracker is pinned by text, so the guard follows the page.
 *
 * Time is fake and fixed (gotcha #44). Node environment with the repo's
 * `minimalDom` (no jsdom in the sandbox that runs this suite).
 */
import "../helpers/minimalDom";
import React, { act, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import EkgHeartbeat from "@/components/event/EkgHeartbeat";
import { useLiveEventStream } from "@/hooks/useLiveEventStream";
import {
  EKG_FLAT_AFTER_MS,
  EMPTY_EKG_TRACKER,
  presentEkg,
  stepEkgTracker,
  type EkgTracker,
} from "@/lib/event/ekgHeartbeat";
import { EKG_STORAGE_KEY, resolveEkgOptIn } from "@/lib/ekgOptIn";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const PAGE = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

function memoryStore() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: jest.fn((k: string, v: string) => void m.set(k, v)),
    removeItem: jest.fn((k: string) => void m.delete(k)),
    m,
  };
}

describe("#10090 resolveEkgOptIn (default ON, Alex decision 66)", () => {
  test("ON on the plain URL with nothing remembered, and it writes nothing", () => {
    const s = memoryStore();
    expect(resolveEkgOptIn("", s)).toBe(true);
    expect(resolveEkgOptIn("?tenths=off", s)).toBe(true);
    expect(resolveEkgOptIn("", null)).toBe(true);
    expect(s.setItem).not.toHaveBeenCalled();
  });
  test("?ekg=0 turns it off and remembers; the plain URL then reads off", () => {
    const s = memoryStore();
    expect(resolveEkgOptIn("?ekg=0", s)).toBe(false);
    expect(s.m.get(EKG_STORAGE_KEY)).toBe("0");
    expect(resolveEkgOptIn("", s)).toBe(false);
    expect(resolveEkgOptIn("?tenths=off", s)).toBe(false);
  });
  test("?ekg=1 after ?ekg=0 turns it back on and remembers that", () => {
    const s = memoryStore();
    resolveEkgOptIn("?ekg=0", s);
    expect(resolveEkgOptIn("?ekg=1", s)).toBe(true);
    expect(s.m.get(EKG_STORAGE_KEY)).toBe("1");
    expect(resolveEkgOptIn("", s)).toBe(true);
  });
  test("a reader who opted in during the trial stays on", () => {
    const s = memoryStore();
    s.m.set(EKG_STORAGE_KEY, "1");
    expect(resolveEkgOptIn("", s)).toBe(true);
  });
  test("only the exact value 0 opts out", () => {
    expect(resolveEkgOptIn("?ekg=false", memoryStore())).toBe(true);
    expect(resolveEkgOptIn("?ekg=off", memoryStore())).toBe(true);
  });
  test("a store that throws reads the URL alone, defaulting ON", () => {
    const broken = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
    };
    expect(resolveEkgOptIn("?ekg=1", broken)).toBe(true);
    expect(resolveEkgOptIn("", broken)).toBe(true);
    expect(resolveEkgOptIn("?ekg=0", broken)).toBe(false);
  });
});

describe("#10090 the page wiring (pinned by text)", () => {
  test("the heartbeat is drawn only behind the opt-in, only on a live game, never finished", () => {
    expect(PAGE).toContain("const ekgOptIn = useEkgOptIn();");
    expect(PAGE).toContain(
      "const ekgVisible = ekgDraws({ optIn: ekgOptIn, quoteEligible, isLive, terminalLabel: connectionTerminalLabel });",
    );
    expect(PAGE).toContain('const isLive = event?.status === "live" && hasStarted;');
    expect(PAGE).toMatch(/\{ekgVisible && !isFinished \? \(\s*<div[^>]*data-testid="ekg-row">\s*<EkgHeartbeat tracker=\{ekgTrackerRef\.current\} status=\{streamStatus\} \/>/);
  });
  test("the tracker is fed the hook's confirmedAt and the ACCEPTED price clock", () => {
    expect(PAGE).toContain(
      "{ eventId, status: streamStatus, confirmedAt: streamConfirmedAt, priceObservedAt: acceptedPriceClock }",
    );
  });
  test("the opt-in hook is called before the page's first conditional return", () => {
    const hook = PAGE.indexOf("useEkgOptIn();");
    const firstReturn = PAGE.search(/\n\s{2}if \([^\n]*\) \{?\s*\n?\s*return\b/);
    expect(hook).toBeGreaterThan(0);
    expect(firstReturn === -1 || hook < firstReturn).toBe(true);
  });
});

// ── drawing ──────────────────────────────────────────────────────────────────
const T0 = Date.UTC(2026, 9, 30, 21, 0, 0);
const at = (s: number) => new Date(T0 + s * 1000).toISOString();

function draw(tracker: EkgTracker, status: Parameters<typeof EkgHeartbeat>[0]["status"], now: number): string {
  return renderToStaticMarkup(<EkgHeartbeat tracker={tracker} status={status} now={now} />);
}

describe("#10090 EkgHeartbeat drawing", () => {
  const base = stepEkgTracker(
    EMPTY_EKG_TRACKER,
    { eventId: 1, status: "open", confirmedAt: null, priceObservedAt: at(0) },
    T0,
  );
  const beat = stepEkgTracker(base, { eventId: 1, status: "open", confirmedAt: at(6), priceObservedAt: at(0) }, T0 + 6_000);

  test("a beat draws the trace with the replaying class and a screen-reader age", () => {
    const html = draw(beat, "open", T0 + 8_000);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Markets reporting: last update 2 seconds ago"');
    expect(html).toContain('data-ekg-mode="beating"');
    expect(html).toContain('data-ekg-beats="1"');
    expect(html).toMatch(/<path d="M1 6 H13[^"]*" pathLength="100" class="ekg-beat"/);
    expect(html).toMatch(/<svg[^>]*class="motion-reduce:hidden text-accent-live"/);
  });

  test("a mount with no report yet draws flat and says so", () => {
    const html = draw(base, "open", T0 + 1_000);
    expect(html).toContain('data-ekg-mode="flat"');
    expect(html).toContain('aria-label="Markets reporting: no update yet"');
    expect(html).not.toContain('class="ekg-beat"');
  });

  test("silence draws a flat, muted line", () => {
    const html = draw(beat, "open", T0 + 6_000 + EKG_FLAT_AFTER_MS);
    expect(html).toContain('data-ekg-mode="flat"');
    expect(html).toContain('<path d="M1 6 H39"></path>');
    expect(html).toMatch(/<svg[^>]*class="motion-reduce:hidden text-text-muted"/);
  });

  test("an interrupted transport draws the flat line in the warning tone, never a beat", () => {
    const html = draw(beat, "retrying", T0 + 7_000);
    expect(html).toContain('data-ekg-mode="interrupted"');
    expect(html).toContain('<path d="M1 6 H39"></path>');
    expect(html).not.toContain('class="ekg-beat"');
    expect(html).toMatch(/<svg[^>]*class="motion-reduce:hidden text-accent-warning"/);
  });

  test("Reduce Motion gets a still dot and the age instead of the trace", () => {
    const html = draw(beat, "open", T0 + 9_000);
    expect(html).toMatch(/<span aria-hidden="true" class="hidden [^"]*motion-reduce:inline-flex"><span class="h-1.5 w-1.5 rounded-full bg-accent-live"><\/span>3s ago<\/span>/);
  });

  test("the drawing and its animation use design-system tokens only (no hex)", () => {
    const src = fs.readFileSync(path.join(__dirname, "../../components/event/EkgHeartbeat.tsx"), "utf8");
    expect(src).not.toMatch(/["'`]#[0-9a-fA-F]{3,8}["'`]/);
    const css = fs.readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");
    const block = css.slice(css.indexOf("@keyframes ekg-beat"), css.indexOf(".ekg-beat {") + 200);
    expect(block).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\) \{\s*\.ekg-beat \{\s*animation: none;/);
  });
});

// ── through the real stream hook ────────────────────────────────────────────
class FakeEventSource {
  static all: FakeEventSource[] = [];
  readyState = 0;
  listeners = new Map<string, ((e: unknown) => void)[]>();
  constructor(readonly url: string) { FakeEventSource.all.push(this); }
  addEventListener(k: string, f: (e: unknown) => void) { this.listeners.set(k, [...(this.listeners.get(k) ?? []), f]); }
  close() { this.readyState = 2; }
  emit(k: string, v?: unknown) {
    if (k === "open") this.readyState = 1;
    for (const f of this.listeners.get(k) ?? []) f(v === undefined ? {} : { data: typeof v === "string" ? v : JSON.stringify(v) });
  }
}

const HELD_PRICE_AT = at(0);

/** The page's wiring, carried: the hook's answers into the tracker, presented as text. */
function StreamProbe({ eventId }: { eventId: number }) {
  const { confirmedAt, status } = useLiveEventStream(eventId, true);
  // The component's own once-a-second clock, carried, so silence is seen.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1_000);
    return () => clearInterval(id);
  }, []);
  const tracker = useRef<EkgTracker>(EMPTY_EKG_TRACKER);
  tracker.current = stepEkgTracker(
    tracker.current,
    { eventId, status, confirmedAt, priceObservedAt: HELD_PRICE_AT },
    Date.now(),
  );
  const p = presentEkg(tracker.current, status, Date.now());
  return <>{`${p.mode}:${p.beats}`}</>;
}

describe("#10090 EKG through the real useLiveEventStream", () => {
  const original = (globalThis as Record<string, unknown>).EventSource;
  let container: HTMLElement;
  let root: Root;
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(T0);
    FakeEventSource.all = [];
    (globalThis as Record<string, unknown>).EventSource = FakeEventSource;
    container = document.createElement("div");
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    (globalThis as Record<string, unknown>).EventSource = original;
    jest.useRealTimers();
  });

  const shown = () => container.textContent;
  const advance = (ms: number) => act(() => { jest.advanceTimersByTime(ms); });

  test("an advancing confirmed_at beats; the keep-alive repeating it does not; silence goes flat", () => {
    act(() => root.render(<StreamProbe eventId={7} />));
    const source = FakeEventSource.all.at(-1)!;
    act(() => source.emit("open"));
    expect(shown()).toBe("flat:0");

    advance(6_000);
    act(() => source.emit("heartbeat", { t: 1, confirmed_at: at(6) }));
    expect(shown()).toBe("beating:1");

    advance(6_000);
    act(() => source.emit("heartbeat", { t: 2, confirmed_at: at(12) }));
    expect(shown()).toBe("beating:2");

    // The 20 s keep-alive carries the newest value already sent: no beat.
    advance(8_000);
    act(() => source.emit("heartbeat", { t: 3, confirmed_at: at(12) }));
    expect(shown()).toBe("beating:2");
    // 15 s after the last report the line is flat, with no frame needed.
    advance(EKG_FLAT_AFTER_MS - 8_000 - 1_000);
    expect(shown()).toBe("beating:2");
    advance(1_000);
    expect(shown()).toBe("flat:2");
    // An old server's heartbeat (no confirmed_at) is a keep-alive too.
    act(() => source.emit("heartbeat", { t: 4 }));
    expect(shown()).toBe("flat:2");
  });

  test("a transport error never beats", () => {
    act(() => root.render(<StreamProbe eventId={8} />));
    const first = FakeEventSource.all.at(-1)!;
    act(() => first.emit("open"));
    advance(3_000);
    act(() => first.emit("heartbeat", { t: 1, confirmed_at: at(3) }));
    expect(shown()).toBe("beating:1");

    act(() => first.emit("error"));
    expect(shown()).toMatch(/^(interrupted|flat):1$/);
  });
});
