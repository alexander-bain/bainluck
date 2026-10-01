/**
 * #10092 — a pushed probability reaches the hero's digits in the SAME render.
 *
 * The hero used to count (600ms easeOutCubic) from the old whole percent to the
 * new one, printing values no venue priced — 22, 31, 37 on the way from 9 to 42
 * — while the chart beside it already showed the real point. These tests mount
 * the real component through `react-dom/client` (the static-markup harness the
 * older hero tests use runs no effects, so it could never see a count) and give
 * it a MANUAL `requestAnimationFrame` queue, so any frame-driven count would be
 * visible here: the old component fails every "immediately" and "only old/new"
 * assertion below.
 *
 * The change cue is a Web Animations API crossfade on the digit spans. The DOM
 * here is the repo's minimal one, extended locally with exactly what the hook
 * touches — `querySelectorAll`, `dataset`, `animate` — and `animate` records
 * what was asked of it.
 */

import { minimalDom } from "../helpers/minimalDom";
import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";

// ── the DOM the hook touches ────────────────────────────────────────────────

type Anim = { node: Record<string, unknown>; keyframes: unknown; options: unknown; cancelled: boolean };
let anims: Anim[] = [];

type FakeNode = Record<string, unknown> & { childNodes: FakeNode[] };

function walk(node: FakeNode, out: FakeNode[]) {
  for (const c of node.childNodes ?? []) {
    out.push(c);
    walk(c, out);
  }
  return out;
}

const doc = minimalDom.document as unknown as Record<string, unknown>;
const baseCreate = doc.createElement as (t: string) => FakeNode;
doc.createElement = (tag: string) => {
  const el = baseCreate(tag);
  el.dataset = {};
  el.querySelectorAll = (sel: string) => {
    if (sel !== "[data-hero-digits]") throw new Error(`unexpected selector ${sel}`);
    return walk(el, []).filter((n) => "data-hero-digits" in n);
  };
  el.animate = (keyframes: unknown, options: unknown) => {
    const a: Anim = { node: el, keyframes, options, cancelled: false };
    anims.push(a);
    return { cancel: () => { a.cancelled = true; } };
  };
  return el;
};

let reducedMotion = false;
(globalThis as Record<string, unknown>).window = Object.assign(
  (globalThis as Record<string, unknown>).window as object,
  { matchMedia: (q: string) => ({ matches: reducedMotion && q.includes("reduce") }) },
);

// A manual frame queue: nothing runs until `flushFrames` says so.
let frames: Array<(t: number) => void> = [];
let clock = 0;
(globalThis as Record<string, unknown>).requestAnimationFrame = (cb: (t: number) => void) => {
  frames.push(cb);
  return frames.length;
};
(globalThis as Record<string, unknown>).cancelAnimationFrame = () => {};
jest.spyOn(performance, "now").mockImplementation(() => clock);

/** Run every queued frame, 16ms apart, recording the printed pair after each. */
function flushFrames(read: () => [string, string]): Array<[string, string]> {
  const seen: Array<[string, string]> = [];
  for (let guard = 0; guard < 200 && frames.length; guard++) {
    const batch = frames;
    frames = [];
    clock += 16;
    act(() => { for (const cb of batch) cb(clock); });
    seen.push(read());
  }
  return seen;
}

// ── harness ─────────────────────────────────────────────────────────────────

type Props = React.ComponentProps<typeof EventHeroProbabilityPair>;
let container: FakeNode;
let root: Root;

function digits(): [string, string] {
  const spans = walk(container, []).filter((n) => "data-hero-digits" in n);
  const text = spans.map((n) => String(n.textContent));
  return [text[0] ?? "", text[1] ?? ""];
}

function pair(homePct: number | null, extra: Partial<Props> = {}): Props {
  return {
    homeProb: homePct === null ? null : homePct / 100,
    awayProb: homePct === null ? null : 1 - homePct / 100,
    homePct,
    awayPct: homePct === null ? null : 100 - homePct,
    homeColor: "#111827",
    awayColor: "#6B7280",
    animate: true,
    ...extra,
  };
}

function render(props: Props) {
  act(() => { root.render(<EventHeroProbabilityPair {...props} />); });
}

beforeEach(() => {
  anims = [];
  frames = [];
  clock = 0;
  reducedMotion = false;
  container = baseCreate("div");
  (minimalDom.body as unknown as { appendChild: (n: unknown) => void }).appendChild(container);
  root = createRoot(container as unknown as HTMLElement);
});

afterEach(() => {
  act(() => root.unmount());
});

// ── the value ───────────────────────────────────────────────────────────────

describe("a pushed frame prints its accepted value at once", () => {
  test("9 → 42 reads 42–58 in the render the frame arrives in, before any frame runs", () => {
    render(pair(9));
    expect(digits()).toEqual(["9", "91"]);
    render(pair(42));
    expect(frames).toHaveLength(0);
    expect(digits()).toEqual(["42", "58"]);
  });

  test("no in-between number ever reaches the screen, and every printed pair sums to 100", () => {
    render(pair(9));
    render(pair(42));
    const seen = [digits(), ...flushFrames(digits)];
    for (const [h, a] of seen) {
      expect(["9", "42"]).toContain(h);
      expect(Number(h) + Number(a)).toBe(100);
    }
  });

  test("a burst retargets immediately: 9 → 42 → 38 → 61 prints each accepted value, no queue", () => {
    render(pair(9));
    for (const v of [42, 38, 61]) {
      render(pair(v));
      expect(digits()).toEqual([String(v), String(100 - v)]);
    }
    expect(flushFrames(digits).every(([h]) => h === "61")).toBe(true);
  });

  test("the served pair is printed as served — a 32/68 pair never reads 33/68", () => {
    render({ ...pair(50), homeProb: 0.325, awayProb: 0.675, homePct: 50, awayPct: 50 });
    render({ ...pair(32), homeProb: 0.325, awayProb: 0.675 });
    expect(digits()).toEqual(["32", "68"]);
  });

  test("a withheld side prints the em-dash at once, and a returning value prints at once", () => {
    render(pair(40));
    render({ ...pair(40), awayProb: null, awayPct: null });
    expect(digits()).toEqual(["40", "—"]);
    render(pair(55));
    expect(digits()).toEqual(["55", "45"]);
  });
});

// ── the cue ─────────────────────────────────────────────────────────────────

describe("only a genuine pushed change is marked, and the mark never holds the value", () => {
  test("first paint is not a change", () => {
    render(pair(42));
    expect(anims).toHaveLength(0);
  });

  test("a change crossfades BOTH digit spans and names its direction", () => {
    render(pair(9));
    render(pair(42));
    expect(anims).toHaveLength(2);
    for (const a of anims) {
      expect(a.keyframes).toEqual([{ opacity: 0.55 }, { opacity: 1 }]);
      expect((a.options as { duration: number }).duration).toBeLessThanOrEqual(400);
    }
    expect((container.childNodes[0].dataset as Record<string, string>).changeCue).toBe("up");
    render(pair(30));
    expect((container.childNodes[0].dataset as Record<string, string>).changeCue).toBe("down");
  });

  test("a new frame mid-cue cancels the running cue instead of queueing behind it", () => {
    render(pair(9));
    render(pair(42));
    const first = [...anims];
    render(pair(38));
    expect(first.every((a) => a.cancelled)).toBe(true);
    expect(anims.filter((a) => !a.cancelled)).toHaveLength(2);
  });

  test("an unchanged value re-sent by the stream is not a change", () => {
    render(pair(42));
    render(pair(42));
    render({ ...pair(42), probSourceLabel: "Kalshi" });
    expect(anims).toHaveLength(0);
  });

  test("a side appearing or disappearing is not marked as a move", () => {
    render(pair(null));
    render(pair(42));
    render(pair(null));
    expect(anims).toHaveLength(0);
  });

  test("reduced motion: no cue, the value is already exact", () => {
    reducedMotion = true;
    render(pair(9));
    render(pair(42));
    expect(anims).toHaveLength(0);
    expect(digits()).toEqual(["42", "58"]);
  });

  test("on the poll (animate off) a change is a plain swap, exactly as before", () => {
    render(pair(9, { animate: false }));
    render(pair(42, { animate: false }));
    expect(anims).toHaveLength(0);
    expect(digits()).toEqual(["42", "58"]);
  });
});
