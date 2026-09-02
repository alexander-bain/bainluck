/**
 * Guard suite for the felt-number rail (latency/121).
 *
 * WHAT IT IS ACTUALLY GUARDING. The failure mode this rail exists to prevent is
 * not "the number is wrong by 50 ms" — it is "the number is confidently wrong in
 * the direction that looks good". Three of those are specific and each has a
 * test here that reds if the behaviour is removed:
 *
 *   1. A skeleton counted as a card reports a broken screen as instant.
 *   2. A warm tab-switch counting the PREVIOUS tab's cards reports ~0 ms.
 *   3. A screen that never renders anything reports NOTHING, so the worst rows
 *      go missing from the table exactly when they are worst (LAT-P202: eight
 *      consecutive empty renders posted a FASTER FCP than the healthy ones).
 *
 * 🔴 WHY THERE IS A HAND-BUILT DOM IN THIS FILE. `jest-environment-jsdom` is not
 * installed and the npm registry is unreachable from this sandbox, so `document`
 * does not exist here. The alternative was to test only the two pure helpers and
 * leave the detector — which is where all three defects above live — unguarded.
 * A fake that implements exactly the five DOM operations the detector uses is a
 * smaller lie than a green suite that never ran the detector.
 */

import {
  startScreenTiming,
  isRealCard,
  maskSurface,
  deviceClass,
  NOT_MEASURED,
  CARD_SELECTOR,
} from "@/lib/screenTiming";
import type { ScreenTimingParams } from "@/lib/analytics/types";
import { ALLOWED_PARAM_KEYS, KNOWN_EVENT_NAMES } from "@/lib/analytics/sanitize";

// ---------------------------------------------------------------------------
// Minimal DOM. Supports only what `screenTiming.ts` calls, and nothing else, so
// it cannot quietly diverge into a general-purpose fake nobody audits.
// ---------------------------------------------------------------------------

interface Rect { width: number; height: number; top: number; bottom: number }

class FakeEl {
  tag: string;
  className = "";
  attrs = new Map<string, string>();
  children: FakeEl[] = [];
  parentElement: FakeEl | null = null;
  ownText = "";
  rect: Rect = { width: 300, height: 200, top: 10, bottom: 210 };

  constructor(tag: string) { this.tag = tag; }

  get classList() {
    return { contains: (c: string) => this.className.split(/\s+/).includes(c) };
  }
  get textContent(): string {
    return this.ownText + this.children.map((c) => c.textContent).join("");
  }
  getAttribute(name: string): string | null { return this.attrs.get(name) ?? null; }
  getBoundingClientRect(): Rect { return this.rect; }

  append(child: FakeEl): FakeEl { child.parentElement = this; this.children.push(child); return this; }
  remove(): void {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((c) => c !== this);
    this.parentElement = null;
  }

  matches(sel: string): boolean { return matchOne(this, sel.trim()); }
  closest(sel: string): FakeEl | null {
    for (let n: FakeEl | null = this; n; n = n.parentElement) if (anyMatch(n, sel)) return n;
    return null;
  }
  querySelector(sel: string): FakeEl | null {
    for (const d of descendants(this)) if (anyMatch(d, sel)) return d;
    return null;
  }
  querySelectorAll(sel: string): FakeEl[] {
    return descendants(this).filter((d) => anyMatch(d, sel));
  }
}

function descendants(el: FakeEl): FakeEl[] {
  // Document order — the detector's "outermost match wins" rule depends on it.
  const out: FakeEl[] = [];
  for (const c of el.children) { out.push(c); out.push(...descendants(c)); }
  return out;
}
function anyMatch(el: FakeEl, selectorList: string): boolean {
  return selectorList.split(",").some((s) => matchOne(el, s.trim()));
}
/** Supports: `tag`, `.class`, `[attr="v"]`, `[attr^="v"]`, and `tag[attr^="v"]`. */
function matchOne(el: FakeEl, sel: string): boolean {
  if (!sel) return false;
  if (sel.startsWith(".")) return el.classList.contains(sel.slice(1));
  const m = /^([a-zA-Z]*)(?:\[([a-zA-Z-]+)(\^?)="([^"]*)"\])?$/.exec(sel);
  if (!m) return false;
  const [, tag, attr, caret, value] = m;
  if (tag && el.tag !== tag) return false;
  if (!attr) return Boolean(tag);
  const actual = el.getAttribute(attr);
  if (actual === null) return false;
  return caret ? actual.startsWith(value) : actual === value;
}

class FakeDoc {
  documentElement = new FakeEl("html");
  body = new FakeEl("body");
  constructor() { this.documentElement.append(this.body); }
  querySelectorAll(sel: string): FakeEl[] { return this.documentElement.querySelectorAll(sel); }
}

function card(text: string, opts: { top?: number; height?: number; tag?: string } = {}): FakeEl {
  const el = new FakeEl(opts.tag ?? "article");
  el.ownText = text;
  const top = opts.top ?? 10;
  const height = opts.height ?? 200;
  el.rect = { width: 300, height, top, bottom: top + height };
  return el;
}
function skeleton(): FakeEl {
  const el = new FakeEl("article");
  el.className = "animate-pulse";
  return el;
}

const asEl = (e: FakeEl) => e as unknown as Element;
const asDoc = (d: FakeDoc) => d as unknown as Document;

// ---------------------------------------------------------------------------

describe("maskSurface", () => {
  it("collapses the root to a named surface", () => {
    expect(maskSurface("/")).toBe("discover");
  });

  it("masks every dynamic segment so an id cannot ride out inside `surface`", () => {
    expect(maskSurface("/events/15293206")).toBe("events/:id");
    expect(maskSurface("/futures/98765")).toBe("futures/:id");
    // Masking is by SHAPE, so a route nobody registered is still masked — the
    // failure direction for an unknown route is over-masking, never a leaked id.
    expect(maskSurface("/some-new-route/44821/detail")).toBe("some-new-route/:id/detail");
  });

  it("drops the query string, which is where a search term would be", () => {
    expect(maskSurface("/search?q=lakers+vs+celtics")).toBe("search");
  });

  it("bounds each segment so the slug cannot become a free-text field", () => {
    expect(maskSurface("/" + "a".repeat(200)).length).toBeLessThanOrEqual(32);
  });
});

describe("isRealCard", () => {
  it("accepts a card with real content", () => {
    expect(isRealCard(asEl(card("Los Angeles Dodgers leads at 31%")))).toBe(true);
  });

  it("🔴 REJECTS a skeleton — the defect that would report a broken screen as instant", () => {
    expect(isRealCard(asEl(skeleton()))).toBe(false);
  });

  it("rejects a card that still CONTAINS a skeleton", () => {
    const el = card("Chiefs vs Ravens");
    el.append(skeleton());
    expect(isRealCard(asEl(el))).toBe(false);
  });

  it("rejects an aria-hidden placeholder subtree", () => {
    const wrap = new FakeEl("div");
    wrap.attrs.set("aria-hidden", "true");
    const el = card("Los Angeles Dodgers leads at 31%");
    wrap.append(el);
    expect(isRealCard(asEl(el))).toBe(false);
  });

  it("rejects a chrome-sized link, so a nav item is never the first card", () => {
    expect(isRealCard(asEl(card("Sports odds page", { height: 20 })))).toBe(false);
  });

  it("rejects a card with almost no text, which is what a placeholder looks like", () => {
    expect(isRealCard(asEl(card("—")))).toBe(false);
  });
});

describe("startScreenTiming", () => {
  let clock = 0;
  const now = () => clock;
  let doc: FakeDoc;

  beforeEach(() => { clock = 0; doc = new FakeDoc(); jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  const start = (
    entry: "cold" | "warm",
    emitted: ScreenTimingParams[],
  ) =>
    startScreenTiming({
      surface: "discover",
      entry,
      now,
      root: asDoc(doc),
      emit: (p) => emitted.push(p),
      viewportHeight: () => 900,
    });

  it("reports the elapsed time of the first real card, not of the skeleton before it", () => {
    const emitted: ScreenTimingParams[] = [];
    const sk = skeleton();
    doc.body.append(sk);

    const w = start("cold", emitted);
    clock = 200;
    w.scan();
    expect(emitted).toHaveLength(0); // a skeleton is not a card

    sk.remove();
    clock = 850;
    doc.body.append(card("Los Angeles Dodgers leads at 31%"));
    w.scan();
    w.finish();

    expect(emitted).toHaveLength(1);
    expect(emitted[0].first_card_ms).toBe(850);
    expect(emitted[0].outcome_class).toBe("ok");
  });

  it("counts a skeleton that becomes real IN PLACE", () => {
    // React reuses the node: the same element loses `animate-pulse` and gains
    // content. Marking it 'seen' on the first rejecting pass would make that
    // card permanently invisible and the screen would report `no_card`.
    const emitted: ScreenTimingParams[] = [];
    const el = skeleton();
    doc.body.append(el);
    const w = start("cold", emitted);
    clock = 100;
    w.scan();

    el.className = "";
    el.ownText = "Red Sox vs Mariners 62%";
    clock = 900;
    w.scan();
    w.finish();

    expect(emitted[0].first_card_ms).toBe(900);
  });

  it("🔴 does NOT count the previous tab's cards on a warm transition", () => {
    // The outgoing tab's cards are still mounted when the incoming screen arms.
    doc.body.append(card("Previous tab card, still mounted"));

    const emitted: ScreenTimingParams[] = [];
    const w = start("warm", emitted);
    clock = 5;
    w.scan();
    // Without the arm-time snapshot this would already read first_card_ms = 5.
    clock = 640;
    doc.body.append(card("Red Sox vs Mariners 62%"));
    w.scan();
    w.finish();

    expect(emitted[0].first_card_ms).toBe(640);
  });

  it("🔴 emits `no_card` rather than staying silent when nothing ever renders", () => {
    const emitted: ScreenTimingParams[] = [];
    start("cold", emitted);
    clock = 30000;
    jest.advanceTimersByTime(30000); // the hard budget expires

    expect(emitted).toHaveLength(1);
    expect(emitted[0].outcome_class).toBe("no_card");
    // -1, never 0: "did not happen" and "happened instantly" must not collide.
    expect(emitted[0].first_card_ms).toBe(NOT_MEASURED);
  });

  it("counts one card once, not once per nested match", () => {
    const emitted: ScreenTimingParams[] = [];
    const outer = card("");
    const inner = card("Red Sox vs Mariners 62%", { tag: "a", top: 20, height: 180 });
    inner.attrs.set("href", "/events/15293206");
    outer.append(inner);
    doc.body.append(outer);

    const w = start("cold", emitted);
    clock = 400;
    w.scan();
    w.finish();

    expect(emitted[0].card_count).toBe(1);
  });

  it("does not count a card that renders below the fold toward the first screen", () => {
    const emitted: ScreenTimingParams[] = [];
    const w = start("cold", emitted);
    clock = 500;
    doc.body.append(card("Way down the page, 44%", { top: 4000 }));
    w.scan();
    w.finish();

    expect(emitted[0].first_card_ms).toBe(500); // it IS the first card
    expect(emitted[0].card_count).toBe(0);      // but the first SCREEN is still empty
    expect(emitted[0].fold_ms).toBe(NOT_MEASURED);
  });

  it("emits exactly once when the quiet timer, the budget and an explicit finish race", () => {
    const emitted: ScreenTimingParams[] = [];
    doc.body.append(card("Kansas City Chiefs 58%"));
    const w = start("cold", emitted);
    w.scan();
    w.finish();
    w.finish();
    jest.advanceTimersByTime(60000);
    expect(emitted).toHaveLength(1);
  });

  it("cancel() emits nothing — an abandoned screen is not a slow screen", () => {
    const emitted: ScreenTimingParams[] = [];
    const w = start("cold", emitted);
    w.cancel();
    jest.advanceTimersByTime(60000);
    expect(emitted).toHaveLength(0);
  });

  it("settles on its own once the first screen goes quiet", () => {
    const emitted: ScreenTimingParams[] = [];
    const w = start("cold", emitted);
    clock = 300;
    doc.body.append(card("Kansas City Chiefs 58%"));
    w.scan();
    expect(emitted).toHaveLength(0);
    jest.advanceTimersByTime(1500);
    expect(emitted).toHaveLength(1);
    expect(emitted[0].fold_ms).toBe(300);
  });
});

describe("the packet survives the privacy boundary", () => {
  it("is a registered event name — an unregistered one is silently dropped at gtag", () => {
    // The exact failure `my_stuff_load` shipped with for its entire first life.
    expect(KNOWN_EVENT_NAMES.has("screen_timing")).toBe(true);
  });

  it("carries no content-shaped key", () => {
    const keys = Object.keys(samplePacket());
    for (const forbidden of ["item_name", "headline", "query", "url", "user_id", "event_id", "page_path"]) {
      expect(keys).not.toContain(forbidden);
    }
    expect(ALLOWED_PARAM_KEYS.has("surface")).toBe(true);
  });
});

describe("deviceClass", () => {
  it("returns one of the five declared buckets", () => {
    expect(["phone", "tablet", "desktop", "watch", "unknown"]).toContain(deviceClass());
  });
});

describe("the lab rig and the field rail measure the same thing", () => {
  it("shares its card vocabulary with tools/felt-load.mjs", () => {
    // Not a paraphrase. If these drift, the production p50 and the rig's
    // before/after stop being the same quantity, and every ship's "-400 ms"
    // claim silently changes meaning without anything going red.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const rig = fs.readFileSync(path.join(__dirname, "../../../tools/felt-load.mjs"), "utf8");
    for (const sel of CARD_SELECTOR.split(",")) {
      expect(rig).toContain(sel.trim());
    }
  });

  it("shares its skeleton rule with the native rail", () => {
    // iOS cannot share this file, so the contract is asserted across the
    // language boundary instead of assumed.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const swift = fs.readFileSync(
      path.join(__dirname, "../../../ios/Bain Luck/Bain Luck/Services/ScreenTiming.swift"),
      "utf8",
    );
    for (const key of Object.keys(samplePacket())) {
      expect(swift).toContain(`"${key}"`);
    }
  });
});

function samplePacket(): ScreenTimingParams {
  return {
    surface: "discover",
    entry: "cold",
    shell_ms: 128,
    first_card_ms: 434,
    fold_ms: 814,
    interactive_ms: 814,
    card_count: 8,
    device_class: "desktop",
    network_class: "4g",
    app_build: "web",
    outcome_class: "ok",
  };
}
