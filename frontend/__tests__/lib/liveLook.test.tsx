/**
 * UX-P249 — the live look tells the truth about time.
 *
 * Alex, 2026-09-01, LIVE UPDATES ruling (2). Three properties, and each has a
 * way of being wrong that looks right on a screenshot:
 *
 *   1. the number changes at most once per ~5s — and the LAST value of a burst
 *      is the one that lands, not the first, and not none of them;
 *   2. the age is the age of the number ON SCREEN — the throttle can hold a
 *      value back, so the naive wiring prints an age fresher than its pixel;
 *   3. the sparkline is the last ten minutes on the honest axis, drawn from
 *      real observations only.
 *
 * Every test drives an explicit clock. Nothing here sleeps, and nothing here
 * branches on the real time (gotcha #44).
 */

import { renderToStaticMarkup } from "react-dom/server";

import {
  INITIAL_LIVE_DISPLAY,
  LIVE_AGE_LIMIT_MS,
  LIVE_CHANGE_MIN_INTERVAL_MS,
  LIVE_SERIES_CAP,
  LIVE_SPARKLINE_WINDOW_MS,
  appendLivePoint,
  formatLiveAge,
  hasLiveSparkline,
  livePulse,
  liveWindow,
  receiveLivePoint,
  tickLiveDisplay,
  type LiveDisplayState,
  type LivePoint,
} from "@/lib/live/liveNumber";
import { parseBlendUpdate } from "@/hooks/useLiveBlend";
import { LiveNumber, LivePulse, LiveSparkline } from "@/components/live/LiveLook";

const T0 = 1_800_000_000_000; // a fixed epoch; nothing reads the real clock
const at = (offsetMs: number): number => T0 + offsetMs;
const point = (value: number, offsetMs: number): LivePoint => ({
  value,
  observedAt: at(offsetMs),
});

/* ─────────────────── 1. at most one change per ~5 seconds ─────────────────── */

describe("the number changes at most once per ~5s", () => {
  it("paints the first point immediately — there is nothing to protect", () => {
    const s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    expect(s.shown?.value).toBe(61);
    expect(s.pending).toBeNull();
    // First paint has no direction: nothing moved, it arrived.
    expect(s.lastDirection).toBe(0);
  });

  it("holds a second point that arrives inside the interval", () => {
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    s = receiveLivePoint(s, point(67, 1000), at(1000));
    expect(s.shown?.value).toBe(61); // still the old number on screen
    expect(s.pending?.value).toBe(67);
  });

  it("🔴 A BURST PAINTS ONCE, AND WITH ITS LATEST VALUE", () => {
    // Twenty frames in four seconds. A queue would paint 62 next (the first
    // held point) and be a whole interval behind; the display must land on 81.
    let s: LiveDisplayState = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    for (let i = 1; i <= 20; i += 1) {
      s = receiveLivePoint(s, point(61 + i, i * 200), at(i * 200));
    }
    expect(s.shown?.value).toBe(61);
    s = tickLiveDisplay(s, at(LIVE_CHANGE_MIN_INTERVAL_MS));
    expect(s.shown?.value).toBe(81);
    expect(s.pending).toBeNull();
    expect(s.lastDirection).toBe(1);
  });

  it("🔴 THE LAST UPDATE OF A BURST IS NOT SWALLOWED — the tick paints it", () => {
    // The classic throttle bug: traffic stops while a point is held, no further
    // frame arrives to carry it in, and the reader is left on a stale value
    // forever. Invisible under steady traffic, which is how tests send it.
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    s = receiveLivePoint(s, point(67, 500), at(500));
    // ...and nothing else ever arrives.
    s = tickLiveDisplay(s, at(2000));
    expect(s.shown?.value).toBe(61); // too soon
    s = tickLiveDisplay(s, at(LIVE_CHANGE_MIN_INTERVAL_MS + 1));
    expect(s.shown?.value).toBe(67);
  });

  it("a point arriving after the interval paints straight away", () => {
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    s = receiveLivePoint(s, point(67, 6000), at(6000));
    expect(s.shown?.value).toBe(67);
    expect(s.pending).toBeNull();
  });

  it("a replayed or out-of-order frame never walks the number backwards", () => {
    // SSE reconnects replay. An older observation is not news.
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 5000), at(5000));
    s = receiveLivePoint(s, point(40, 1000), at(6000));
    expect(s.shown?.value).toBe(61);
    expect(s.pending).toBeNull();
  });

  it("direction is judged on the RENDERED integer, not the raw float", () => {
    // 61.2 → 61.4 both render "61". Tinting digits that did not move is the
    // animation crying wolf, and it would fire on nearly every frame.
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61.2, 0), at(0));
    s = receiveLivePoint(s, point(61.4, 6000), at(6000));
    expect(s.shown?.value).toBeCloseTo(61.4);
    expect(s.lastDirection).toBe(0);
  });

  it("...but a float move that DOES cross a rounding boundary tints", () => {
    // The other arm, so the test above cannot pass by the direction always
    // being 0. 61.4 → 61.6 is 61% → 62% on screen and the reader sees it move.
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61.4, 0), at(0));
    s = receiveLivePoint(s, point(61.6, 6000), at(6000));
    expect(s.lastDirection).toBe(1);
  });

  it("a downward move tints downward", () => {
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    s = receiveLivePoint(s, point(52, 6000), at(6000));
    expect(s.lastDirection).toBe(-1);
  });
});

/* ────────────────────── 2. the age is the age on screen ────────────────────── */

describe("the pulse is honest about time", () => {
  it("says plain 'live' under two seconds — not 'live · 0s ago'", () => {
    expect(livePulse(at(0), at(900))?.label).toBe("live");
  });

  it("counts in whole seconds, then minutes, then hours", () => {
    expect(formatLiveAge(12_400)).toBe("12s ago");
    expect(formatLiveAge(4 * 60_000 + 30_000)).toBe("4m ago");
    expect(formatLiveAge(2 * 3_600_000 + 60_000)).toBe("2h ago");
  });

  it("reads 'live · Ns ago' inside the limit", () => {
    const p = livePulse(at(0), at(12_000));
    expect(p).toEqual({ tone: "live", label: "live · 12s ago", ageMs: 12_000 });
  });

  it("🔴 STOPS CLAIMING TO BE LIVE PAST THE TWO-MINUTE LIMIT", () => {
    const p = livePulse(at(0), at(LIVE_AGE_LIMIT_MS + 1_000));
    expect(p?.tone).toBe("paused");
    expect(p?.label).toBe("updates paused · 2m ago");
  });

  it("the boundary is inclusive on the live side", () => {
    expect(livePulse(at(0), at(LIVE_AGE_LIMIT_MS))?.tone).toBe("live");
    expect(livePulse(at(0), at(LIVE_AGE_LIMIT_MS + 1))?.tone).toBe("paused");
  });

  it("does not use the banned word for the degraded state", () => {
    // "stale" is our `price_state` enum — JARGON_BANS in lib/copyBans.ts. The
    // existing FreshnessChip says it; this one must not inherit that.
    const p = livePulse(at(0), at(LIVE_AGE_LIMIT_MS + 60_000));
    expect(p?.label.toLowerCase()).not.toContain("stale");
  });

  it("a future timestamp is a clock disagreement, not a fresher number", () => {
    const p = livePulse(at(10_000), at(0));
    expect(p?.ageMs).toBe(0);
    expect(p?.tone).toBe("live");
  });

  it("renders nothing at all without a timestamp", () => {
    expect(livePulse(null, at(0))).toBeNull();
    expect(livePulse(Number.NaN, at(0))).toBeNull();
  });

  it("🔴 THE AGE FOLLOWS THE PAINTED POINT, NOT THE NEWEST ONE RECEIVED", () => {
    // The wiring bug this whole design exists to prevent. A fresh point is held
    // by the throttle; the chip must describe the value the reader can see.
    let s = receiveLivePoint(INITIAL_LIVE_DISPLAY, point(61, 0), at(0));
    s = receiveLivePoint(s, point(67, 4_000), at(4_000));
    const nowMs = at(4_500);
    // What the component is handed: `shown`, which is still the 4.5s-old 61.
    expect(livePulse(s.shown!.observedAt, nowMs)?.label).toBe("live · 4s ago");
    // What the naive wiring would hand it: the pending point, half a second old.
    expect(livePulse(s.pending!.observedAt, nowMs)?.label).toBe("live");
  });
});

/* ───────────────────────── 3. the ten-minute window ───────────────────────── */

describe("the sparkline is the last ten minutes of real observations", () => {
  const series: LivePoint[] = [
    point(50, -20 * 60_000),
    point(55, -11 * 60_000),
    point(60, -9 * 60_000),
    point(61, -5 * 60_000),
    point(62, -1 * 60_000),
  ];

  it("drops everything older than the window", () => {
    const w = liveWindow(series, at(0));
    expect(w.map((p) => p.value)).toEqual([60, 61, 62]);
  });

  it("the window edge is exclusive so a point cannot straddle two renders", () => {
    const edge = [point(9, -LIVE_SPARKLINE_WINDOW_MS), point(10, -LIVE_SPARKLINE_WINDOW_MS + 1)];
    expect(liveWindow(edge, at(0)).map((p) => p.value)).toEqual([10]);
  });

  it("sorts by observation time, not arrival order", () => {
    const jumbled = [point(3, -1000), point(1, -3000), point(2, -2000)];
    expect(liveWindow(jumbled, at(0)).map((p) => p.value)).toEqual([1, 2, 3]);
  });

  it("drops non-finite values rather than drawing a broken path", () => {
    const dirty = [point(Number.NaN, -3000), point(50, -2000), point(51, -1000), point(52, -500)];
    expect(liveWindow(dirty, at(0))).toHaveLength(3);
  });

  it("🔴 DOES NOT DRAW A ONE- OR TWO-POINT WINDOW", () => {
    // Sparkline handed one point draws a zero-length path: an empty box that
    // reads "we have no data" when the truth may be "nothing has changed".
    expect(hasLiveSparkline(liveWindow([point(61, -1000)], at(0)))).toBe(false);
    expect(hasLiveSparkline(liveWindow([point(61, -2000), point(62, -1000)], at(0)))).toBe(false);
    expect(hasLiveSparkline(liveWindow(series, at(0)))).toBe(true);
  });

  it("DOES draw a perfectly flat window — 'it has not moved' is information", () => {
    const flat = [point(61, -3000), point(61, -2000), point(61, -1000)];
    expect(hasLiveSparkline(liveWindow(flat, at(0)))).toBe(true);
  });

  it("the ring is bounded and keeps the NEWEST points", () => {
    let s: LivePoint[] = [];
    for (let i = 0; i < LIVE_SERIES_CAP + 50; i += 1) s = appendLivePoint(s, point(i % 100, i * 1000));
    expect(s).toHaveLength(LIVE_SERIES_CAP);
    expect(s[s.length - 1].observedAt).toBe(at((LIVE_SERIES_CAP + 49) * 1000));
  });

  it("the ring refuses an out-of-order append", () => {
    const s = appendLivePoint([point(1, 1000)], point(2, 500));
    expect(s.map((p) => p.value)).toEqual([1]);
  });
});

/* ──────────────────── the wire frame, before it is trusted ──────────────────── */

describe("a blend_update frame is parsed strictly", () => {
  const good = JSON.stringify({
    event_id: 123,
    probability: 0.614,
    observed_at: "2026-09-01T18:04:11Z",
  });

  it("converts the 0-1 blend to points once, here", () => {
    const p = parseBlendUpdate(good, 123);
    expect(p?.value).toBeCloseTo(61.4);
    expect(p?.observedAt).toBe(Date.parse("2026-09-01T18:04:11Z"));
  });

  it("🔴 IGNORES A FRAME FOR A DIFFERENT EVENT", () => {
    // The endpoint takes a comma list, so a shared connection carries siblings.
    // Without this, one card paints another card's number.
    expect(parseBlendUpdate(good, 456)).toBeNull();
  });

  it.each([
    ["not json", "{oops"],
    ["no observed_at", JSON.stringify({ event_id: 123, probability: 0.5 })],
    ["unparseable observed_at", JSON.stringify({ event_id: 123, probability: 0.5, observed_at: "soon" })],
    ["probability above 1", JSON.stringify({ event_id: 123, probability: 61.4, observed_at: "2026-09-01T18:04:11Z" })],
    ["probability below 0", JSON.stringify({ event_id: 123, probability: -0.1, observed_at: "2026-09-01T18:04:11Z" })],
    ["probability absent", JSON.stringify({ event_id: 123, observed_at: "2026-09-01T18:04:11Z" })],
  ])("rejects %s", (_name, frame) => {
    expect(parseBlendUpdate(frame, 123)).toBeNull();
  });

  it("rejects a non-string payload rather than coercing it", () => {
    expect(parseBlendUpdate({ event_id: 123 }, 123)).toBeNull();
    expect(parseBlendUpdate(null, 123)).toBeNull();
  });
});

/* ─────────────────────────── what actually renders ─────────────────────────── */

const text = (html: string): string => html.replace(/<[^>]*>/g, "").trim();

describe("the components render nothing when they have nothing", () => {
  it("no number, no element", () => {
    expect(renderToStaticMarkup(<LiveNumber value={null} direction={0} />)).toBe("");
    expect(renderToStaticMarkup(<LiveNumber value={Number.NaN} direction={0} />)).toBe("");
  });

  it("no timestamp, no pulse", () => {
    expect(renderToStaticMarkup(<LivePulse observedAt={null} now={at(0)} />)).toBe("");
  });

  it("too few points, no sparkline", () => {
    expect(
      renderToStaticMarkup(<LiveSparkline series={[point(61, -1000)]} now={at(0)} />)
    ).toBe("");
  });
});

describe("the number steps and marks the step", () => {
  it("prints the rounded integer and records it for the browser rail", () => {
    const html = renderToStaticMarkup(<LiveNumber value={61.6} direction={1} />);
    expect(text(html)).toBe("62%");
    expect(html).toContain('data-live-value="62"');
    expect(html).toContain('data-live-direction="1"');
  });

  it("tints by direction, and a flat change carries no tint", () => {
    expect(renderToStaticMarkup(<LiveNumber value={61} direction={1} />)).toContain("text-accent-live");
    expect(renderToStaticMarkup(<LiveNumber value={61} direction={-1} />)).toContain("text-accent-danger");
    const flat = renderToStaticMarkup(<LiveNumber value={61} direction={0} />);
    expect(flat).not.toContain("text-accent-live");
    expect(flat).not.toContain("text-accent-danger");
  });

  it("🔴 THE TINT IS COLOUR ONLY, AND IT IS DROPPED FOR REDUCED MOTION", () => {
    // A transform or a layout transition on a hero number moves the page under
    // a reader's thumb. And `motion-reduce` must remove the decoration WITHOUT
    // removing the number.
    const html = renderToStaticMarkup(<LiveNumber value={61} direction={1} />);
    expect(html).toContain("transition-colors");
    expect(html).toContain("motion-reduce:transition-none");
    expect(html).not.toContain("transition-transform");
    expect(text(html)).toBe("61%");
  });

  it("announces politely — one throttled change is one announcement", () => {
    expect(renderToStaticMarkup(<LiveNumber value={61} direction={1} />)).toContain('aria-live="polite"');
  });
});

describe("the pulse renders its state", () => {
  it("green and pulsing while live", () => {
    const html = renderToStaticMarkup(<LivePulse observedAt={at(0)} now={at(12_000)} />);
    expect(text(html)).toBe("live · 12s ago");
    expect(html).toContain('data-live-tone="live"');
    expect(html).toContain("animate-pulse");
    expect(html).toContain("motion-reduce:animate-none");
  });

  it("🔴 STOPS PULSING WHEN IT STOPS BEING LIVE", () => {
    // A green pulsing dot over a five-minute-old number is the exact defect
    // class the Flow Sentinel hunts.
    const html = renderToStaticMarkup(
      <LivePulse observedAt={at(0)} now={at(LIVE_AGE_LIMIT_MS + 180_000)} />
    );
    expect(html).toContain('data-live-tone="paused"');
    expect(html).not.toContain("animate-pulse");
    expect(html).not.toContain("accent-live");
    expect(text(html)).toContain("updates paused");
  });
});

describe("the sparkline rides the shared renderer on the honest axis", () => {
  const series = [point(61, -300_000), point(64, -200_000), point(62, -100_000), point(63, -1_000)];

  it("draws the window and says how many points it drew", () => {
    const html = renderToStaticMarkup(<LiveSparkline series={series} now={at(0)} />);
    expect(html).toContain('data-live-points="4"');
    expect(html).toContain("<svg");
  });

  it("🔴 NO SMOOTHING — raw M/L segments, no bezier command anywhere", () => {
    // The standing chart ruling, asserted on the emitted path rather than
    // trusted from the shared component's docblock.
    const html = renderToStaticMarkup(<LiveSparkline series={series} now={at(0)} />);
    const paths = html.match(/ d="[^"]*"/g) ?? [];
    expect(paths.length).toBeGreaterThan(0);
    for (const d of paths) {
      expect(d).not.toMatch(/[CcSsQqTtAa]/);
      expect(d).toMatch(/[ML]/);
    }
  });

  it("🔴 A FLAT WINDOW DRAWS FLAT — the axis is not auto-fitted", () => {
    // Auto-fitting is the most tempting change to this component and the one
    // that makes it lie: 61.2 → 61.6 would climb the full height of the box.
    const nearlyFlat = [point(61.2, -3_000), point(61.4, -2_000), point(61.6, -1_000)];
    const html = renderToStaticMarkup(<LiveSparkline series={nearlyFlat} now={at(0)} />);
    const ys = [...html.matchAll(/[ML]\s*[\d.]+\s*,\s*([\d.]+)/g)].map((m) => Number(m[1]));
    expect(ys.length).toBeGreaterThanOrEqual(3);
    // On a [0,100] domain a 0.4-point move is a fraction of a pixel.
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThan(1);
  });

  it("a REAL move is visibly a move on the same axis — the flat test is not vacuous", () => {
    const big = [point(20, -3_000), point(50, -2_000), point(80, -1_000)];
    const html = renderToStaticMarkup(<LiveSparkline series={big} now={at(0)} />);
    const ys = [...html.matchAll(/[ML]\s*[\d.]+\s*,\s*([\d.]+)/g)].map((m) => Number(m[1]));
    expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(5);
  });
});
