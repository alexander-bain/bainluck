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
  networkClass,
  EFFECTIVE_TYPES,
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

describe("networkClass", () => {
  // #3276 sibling: the domain here was restated from the spec as `length <= 12`,
  // which is a SHAPE test, not a domain test. `network_class` is a GA4
  // dimension, so an unrecognised value does not just log oddly — it opens a
  // new row and splits every cold-load comparison the rail exists to make.
  // `navigator` is NOT a given here. CI runs this file under the `node` test
  // environment, where the global does not exist at all — the first draft of
  // these tests referenced it directly, passed locally under jsdom, and failed
  // in CI with `ReferenceError: navigator is not defined`. So install the
  // global when it is absent and remove it again afterwards, and the tests
  // then assert the same rule under either environment.
  const g = globalThis as unknown as { navigator?: { connection?: unknown } };

  const withConnection = (effectiveType: unknown, run: () => void) => {
    const hadNav = Object.prototype.hasOwnProperty.call(g, "navigator");
    const prevNav = g.navigator;
    if (!hadNav) {
      Object.defineProperty(g, "navigator", { value: {}, configurable: true, writable: true });
    }
    const nav = g.navigator as { connection?: unknown };
    const hadConn = Object.prototype.hasOwnProperty.call(nav, "connection");
    const prevConn = nav.connection;
    Object.defineProperty(nav, "connection", {
      value: effectiveType === undefined ? undefined : { effectiveType },
      configurable: true,
      writable: true,
    });
    try {
      run();
    } finally {
      if (hadConn) {
        Object.defineProperty(nav, "connection", { value: prevConn, configurable: true, writable: true });
      } else {
        delete (nav as Record<string, unknown>).connection;
      }
      if (!hadNav) {
        delete (g as Record<string, unknown>).navigator;
      } else {
        Object.defineProperty(g, "navigator", { value: prevNav, configurable: true, writable: true });
      }
    }
  };

  it.each([...EFFECTIVE_TYPES])("passes the spec value %s through", (t) => {
    withConnection(t, () => expect(networkClass()).toBe(t));
  });

  it("maps an unrecognised SHORT value to unknown, not through", () => {
    // The exact hole: every one of these is <= 12 chars and sailed through.
    for (const bogus of ["5g", "wifi", "ethernet", "unknown-x", "lte", "", "4G"]) {
      withConnection(bogus, () => expect(networkClass()).toBe("unknown"));
    }
  });

  it("maps a missing or malformed connection to unknown", () => {
    withConnection(undefined, () => expect(networkClass()).toBe("unknown"));
    withConnection(null, () => expect(networkClass()).toBe("unknown"));
    withConnection(42, () => expect(networkClass()).toBe("unknown"));
  });

  it("returns unknown when there is no navigator at all", () => {
    // The CI path, asserted rather than assumed: Node 26 ships a `navigator`
    // global and older Node does not, so this branch is the one that only ever
    // runs on the build machine unless a test removes the global on purpose.
    const had = Object.prototype.hasOwnProperty.call(g, "navigator");
    const prev = g.navigator;
    delete (g as Record<string, unknown>).navigator;
    try {
      expect(networkClass()).toBe("unknown");
    } finally {
      if (had) {
        Object.defineProperty(g, "navigator", { value: prev, configurable: true, writable: true });
      }
    }
  });

  it("only ever emits a value from a closed set", () => {
    const closed = new Set<string>([...EFFECTIVE_TYPES, "unknown"]);
    for (const t of [...EFFECTIVE_TYPES, "5g", "wifi", undefined, null, 42]) {
      withConnection(t, () => expect(closed.has(networkClass())).toBe(true));
    }
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

  it("the native rail claims cold/warm at ARM time, not when the card finally lands", () => {
    // 🔴 CERT-782's first finding, ratcheted from the CI-reachable side. The
    // label used to come from a DEFAULT ARGUMENT on the bridge factory, which is
    // evaluated at the call site — and the call site is the first render. A cold
    // launch whose first card took 21 s therefore fell outside the 20 s cold
    // window and filed itself as `warm`. Making the argument mandatory is what
    // makes the wrong moment unexpressible; a default creeping back is exactly
    // the regression this watches for.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const swift = fs.readFileSync(
      path.join(__dirname, "../../../ios/Bain Luck/Bain Luck/Services/ScreenTiming.swift"),
      "utf8",
    );
    expect(swift).not.toMatch(/entry:\s*String\s*=\s*ScreenTimingSession\.nextEntry\(\)/);
    expect(swift).toMatch(/public static func armScreen\(/);
  });

  it("a native screen that never renders reports no_card on a stated deadline", () => {
    // CERT-782's second finding: the bridge only fires from a real first render,
    // so a top-tab load that showed NOTHING emitted no row at all — and 3 of the
    // 40 cold loads in the 2026-09-02 battery were exactly that. The deadline is
    // pinned by value here so it cannot quietly become "eventually".
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const swift = fs.readFileSync(
      path.join(__dirname, "../../../ios/Bain Luck/Bain Luck/Services/ScreenTiming.swift"),
      "utf8",
    );
    expect(swift).toMatch(/noCardDeadlineSeconds:\s*TimeInterval\s*=\s*10\b/);
    expect(swift).toMatch(/outcome:\s*"no_card"/);
  });

  it("every outcome the native rail can emit is one the web type declares", () => {
    // One table, two producers. A native-only outcome value would be a column
    // the web half's union type cannot hold, and the promised single table would
    // quietly become two again.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const root = path.join(__dirname, "../../..");
    const swift = fs.readFileSync(
      path.join(root, "ios/Bain Luck/Bain Luck/Services/ScreenTiming.swift"),
      "utf8",
    );
    const types = fs.readFileSync(path.join(root, "frontend/lib/analytics/types.ts"), "utf8");
    const declared = /outcome_class:\s*((?:'[a-z_]+'\s*\|?\s*)+)/.exec(types);
    expect(declared).not.toBeNull();
    const allowed = new Set((declared as RegExpExecArray)[1].match(/'([a-z_]+)'/g)!.map((s) => s.slice(1, -1)));
    expect(allowed.size).toBeGreaterThanOrEqual(4);

    const emitted = new Set(
      [...swift.matchAll(/(?:outcome|outcomeClass|resolved):\s*"([a-z_]+)"/g)].map((m) => m[1]),
    );
    // The Swift also builds outcomes with a ternary; catch those literals too.
    for (const m of swift.matchAll(/cardCount\s*>\s*0\s*\?\s*"([a-z_]+)"\s*:\s*"([a-z_]+)"/g)) {
      emitted.add(m[1]);
      emitted.add(m[2]);
    }
    expect(emitted.size).toBeGreaterThan(0);
    for (const outcome of emitted) {
      expect([...allowed]).toContain(outcome);
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
