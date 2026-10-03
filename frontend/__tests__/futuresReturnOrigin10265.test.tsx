/**
 * #10265 — the question page's Back goes to the entry the reader tapped from,
 * and only when that entry is provably the one immediately behind the page.
 *
 * Specimen walk: `/events/15318028` (Pitt @ Virginia Tech) → Bigger Picture
 * card → `/futures/231`. The control used to be a hard /discover link.
 *
 * The fake below models the Navigation API the way the browser does: it lists
 * SAME-ORIGIN entries only, a push truncates forward entries and adds a new
 * id + key, and a replace (Next's `replace`, `history.replaceState`) keeps the
 * slot's key and mints a new id. The discriminating case is sol's
 * counterexample: external page → fresh /discover → client replace to the
 * question. The old "path changed since load" rule said yes and Back left the
 * site; here it must say no.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  createQuestionOriginStore,
  ORIGIN_CLICK_TTL_MS,
  questionOrigin,
  questionPathOf,
  type OriginClick,
  type OriginEnv,
} from "@/lib/futuresReturnOrigin";

const ORIGIN = "https://bainluck.com";

// Ids and keys are unique across every fake, as the browser's UUIDs are: the
// store under test is a module singleton shared by several tests below.
let fakeSeq = 0;
class FakeNavigation {
  list: { id: string; key: string; index: number; url: string }[] = [];
  at = -1;
  constructor(firstUrl: string) {
    this.list = [this.mint(firstUrl, null, 0)];
    this.at = 0;
  }
  private mint(url: string, key: string | null, index: number) {
    fakeSeq += 1;
    return { id: `id${fakeSeq}`, key: key ?? `key${fakeSeq}`, index, url };
  }
  get currentEntry() {
    return this.list[this.at] ?? null;
  }
  entries() {
    return this.list;
  }
  push(url: string) {
    this.list = this.list.slice(0, this.at + 1);
    this.list.push(this.mint(url, null, this.list.length));
    this.at = this.list.length - 1;
  }
  replace(url: string) {
    const old = this.list[this.at];
    this.list[this.at] = this.mint(url, old.key, old.index);
  }
  back() {
    this.at -= 1;
  }
  forward() {
    this.at += 1;
  }
  get url() {
    return this.list[this.at].url;
  }
}

const envOf = (nav: FakeNavigation | null, now = 1_000_000, url?: string): OriginEnv => {
  const href = `${ORIGIN}${url ?? nav?.url ?? "/"}`;
  const u = new URL(href);
  return { origin: ORIGIN, href, pathname: u.pathname, navigation: nav, now };
};

const tap = (href: string | null, over: Partial<OriginClick> = {}): OriginClick => ({
  href, button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
  target: null, download: false, ...over,
});

describe("#10265 proof that the entry behind the question is the one the reader left", () => {
  it("game → question by an ordinary link: Back is allowed, and points at the game entry", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028?range=all#bigger-picture");
    expect(s.recordClick(tap("/futures/231"), envOf(nav))).toBe(true);
    nav.push("/futures/231");
    expect(s.adopt(envOf(nav))).toBe(true);
    expect(s.canGoBack(envOf(nav))).toBe(true);
  });

  it("COUNTEREXAMPLE: external → fresh /discover → client REPLACE to the question is refused", () => {
    const s = createQuestionOriginStore();
    // The external page is not same-origin, so the Navigation API never lists it.
    const nav = new FakeNavigation("/discover");
    // Even with a recorded tap (a Link with `replace`), the source entry is gone.
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.replace("/futures/231");
    expect(s.adopt(envOf(nav))).toBe(false);
    expect(s.canGoBack(envOf(nav))).toBe(false);
    // And a replace with no tap at all (router.replace) has nothing to adopt.
    const s2 = createQuestionOriginStore();
    const nav2 = new FakeNavigation("/discover");
    nav2.replace("/futures/231");
    expect(s2.adopt(envOf(nav2))).toBe(false);
    expect(s2.canGoBack(envOf(nav2))).toBe(false);
  });

  it("a replace INSIDE our history (source replaced, an older entry of ours behind) is refused too", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/discover");
    nav.push("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.replace("/futures/231");
    // /discover is behind, but it is not the entry the tap left.
    expect(s.adopt(envOf(nav))).toBe(false);
  });

  it("a range chip's replaceState keeps the proof (same entry, new query)", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.push("/futures/231");
    s.adopt(envOf(nav));
    nav.replace("/futures/231?range=1W");
    expect(s.canGoBack(envOf(nav))).toBe(true);
  });

  it("game → question A → question B: each Back targets its own immediate predecessor", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.push("/futures/231");
    expect(s.adopt(envOf(nav))).toBe(true);
    s.recordClick(tap("/futures/300"), envOf(nav));
    nav.push("/futures/300");
    expect(s.adopt(envOf(nav))).toBe(true);
    expect(s.canGoBack(envOf(nav))).toBe(true);
    nav.back(); // on A again: its own proof, source = the game
    expect(s.adopt(envOf(nav))).toBe(false); // nothing pending; remount is a no-op
    expect(s.canGoBack(envOf(nav))).toBe(true);
  });

  it("a different question that later takes over the same entry slot does not inherit the proof", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.push("/futures/231");
    s.adopt(envOf(nav));
    nav.replace("/futures/999"); // same key, different question
    expect(s.canGoBack(envOf(nav))).toBe(false);
  });

  it("a proof whose source entry has since changed authorizes nothing (re-checked at the tap)", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav));
    nav.push("/futures/231");
    s.adopt(envOf(nav));
    nav.back();
    nav.replace("/events/15318028?range=live"); // the game entry is now a new entry
    nav.forward();
    expect(s.canGoBack(envOf(nav))).toBe(false);
  });

  it("CANCELED OR STALE TAPS: a tap is consumed once and expires; a redirect elsewhere adopts nothing", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    s.recordClick(tap("/futures/231"), envOf(nav, 1_000));
    nav.push("/futures/231");
    expect(s.adopt(envOf(nav, 1_000 + ORIGIN_CLICK_TTL_MS + 1))).toBe(false);

    const s2 = createQuestionOriginStore();
    const nav2 = new FakeNavigation("/events/15318028");
    s2.recordClick(tap("/futures/231"), envOf(nav2));
    nav2.push("/futures/999"); // redirected
    expect(s2.adopt(envOf(nav2))).toBe(false);
    // The tap was retired by that attempt; arriving at 231 later proves nothing.
    nav2.push("/futures/231");
    expect(s2.adopt(envOf(nav2))).toBe(false);
  });

  it("NOT RECORDED: modified, middle, new-tab, download, external, protocol-relative, script and non-question links", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/events/15318028");
    const env = envOf(nav);
    for (const c of [
      tap("/futures/231", { metaKey: true }),
      tap("/futures/231", { ctrlKey: true }),
      tap("/futures/231", { shiftKey: true }),
      tap("/futures/231", { altKey: true }),
      tap("/futures/231", { button: 1 }),
      tap("/futures/231", { target: "_blank" }),
      tap("/futures/231", { target: "other" }),
      tap("/futures/231", { download: true }),
      tap("https://elsewhere.example/futures/231"),
      tap("//elsewhere.example/futures/231"),
      tap("javascript:void(0)"),
      tap("data:text/html,x"),
      tap("/events/1"),
      tap("/futures/231/extra"),
      tap(null),
    ]) {
      expect(s.recordClick(c, env)).toBe(false);
    }
    // `_self` and an absolute same-origin URL are ordinary taps.
    expect(s.recordClick(tap("/futures/231", { target: "_self" }), env)).toBe(true);
    expect(s.recordClick(tap(`${ORIGIN}/futures/231?range=1W#x`), env)).toBe(true);
  });

  it("a link to the question already on screen is not a move", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/futures/231");
    expect(s.recordClick(tap("/futures/231?range=1W"), envOf(nav))).toBe(false);
  });

  it("NO NAVIGATION API: nothing is recorded and Back stays the Discover link", () => {
    const s = createQuestionOriginStore();
    expect(s.recordClick(tap("/futures/231"), envOf(null, 1, "/events/1"))).toBe(false);
    expect(s.adopt(envOf(null, 1, "/futures/231"))).toBe(false);
    expect(s.canGoBack(envOf(null, 1, "/futures/231"))).toBe(false);
  });

  it("a direct open with history behind it (typed URL, reload, shared link) has no proof", () => {
    const s = createQuestionOriginStore();
    const nav = new FakeNavigation("/discover");
    nav.push("/futures/231"); // a same-origin entry behind, but no tap recorded it
    expect(s.adopt(envOf(nav))).toBe(false);
    expect(s.canGoBack(envOf(nav))).toBe(false);
  });

  it("questionPathOf resolves against the page and compares exact origin", () => {
    const env = { origin: ORIGIN, href: `${ORIGIN}/events/1` };
    expect(questionPathOf("/futures/231/", env)).toBe("/futures/231");
    expect(questionPathOf("../futures/231", env)).toBe("/futures/231");
    expect(questionPathOf("https://bainluck.com.evil.example/futures/231", env)).toBeNull();
  });
});

// ── The control and the click hook, through their real modules ──────────────

const linkProps: { onClick?: (e: unknown) => void; href?: string }[] = [];
jest.mock("next/link", () => ({
  __esModule: true,
  default: (props: { href: string; onClick?: (e: unknown) => void; children: React.ReactNode }) => {
    linkProps.push(props);
    return <a href={props.href}>{props.children}</a>;
  },
}));

import FuturesBackControl from "@/components/futures/FuturesBackControl";

describe("#10265 FuturesBackControl", () => {
  const g = globalThis as unknown as { window?: unknown };
  afterEach(() => {
    delete g.window;
    linkProps.length = 0;
  });

  const click = (over: Record<string, unknown> = {}) => ({
    button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
    preventDefault: jest.fn(), ...over,
  });

  it("renders the Discover link and label on the server (no history to read)", () => {
    const html = renderToStaticMarkup(<FuturesBackControl />);
    expect(html).toMatch(/^<a href="\/discover">[\s\S]*Back to Discover<\/a>$/);
  });

  it("with a proven predecessor a plain tap goes back exactly once; a double tap does not go back twice", () => {
    const nav = new FakeNavigation("/events/15318028");
    const back = jest.fn();
    g.window = { location: new URL(`${ORIGIN}/events/15318028`), navigation: nav, history: { back } };
    questionOrigin.recordClick(tap("/futures/231"), envOf(nav));
    nav.push("/futures/231");
    (g.window as { location: URL }).location = new URL(`${ORIGIN}/futures/231`);
    questionOrigin.adopt(envOf(nav));

    renderToStaticMarkup(<FuturesBackControl />);
    const onClick = linkProps[linkProps.length - 1].onClick!;
    const first = click();
    onClick(first);
    expect(first.preventDefault).toHaveBeenCalled();
    const second = click();
    onClick(second);
    expect(second.preventDefault).toHaveBeenCalled(); // the link must not navigate either
    expect(back).toHaveBeenCalledTimes(1);

    const modified = click({ metaKey: true });
    onClick(modified);
    expect(modified.preventDefault).not.toHaveBeenCalled();
  });

  it("CONTROL: without proof the tap is the Discover link's", () => {
    const nav = new FakeNavigation("/discover");
    nav.push("/futures/231");
    const back = jest.fn();
    g.window = { location: new URL(`${ORIGIN}/futures/231`), navigation: nav, history: { back } };
    renderToStaticMarkup(<FuturesBackControl />);
    const e = click();
    linkProps[linkProps.length - 1].onClick!(e);
    expect(e.preventDefault).not.toHaveBeenCalled();
    expect(back).not.toHaveBeenCalled();
  });
});

describe("#10265 NavigationProgress records the tap (the click hook is wired)", () => {
  const g = globalThis as unknown as { window?: unknown; document?: unknown };
  afterEach(() => {
    delete g.window;
    delete g.document;
  });

  const runNavigationProgressTap = (anchorAttrs: Record<string, string>, over: Record<string, unknown> = {}) => {
    let adopted = false;
    let started = 0;
    jest.isolateModules(() => {
      const listeners: Record<string, (e: unknown) => void> = {};
      g.document = {
        addEventListener: (t: string, f: (e: unknown) => void) => { listeners[t] = f; },
        removeEventListener: () => {},
      };
      jest.doMock("react", () => ({
        ...jest.requireActual("react"),
        useEffect: (f: () => void) => { f(); },
        useRef: (v: unknown) => ({ current: v }),
      }));
      jest.doMock("next/navigation", () => ({
        usePathname: () => "/events/15318028",
        useSearchParams: () => new URLSearchParams(),
      }));
      jest.doMock("nprogress", () => ({
        __esModule: true,
        default: { configure() {}, start() { started += 1; }, done() {} },
      }));
      const nav = new FakeNavigation("/events/15318028");
      g.window = { location: new URL(`${ORIGIN}/events/15318028`), navigation: nav, history: { back() {} } };
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const NavigationProgress = require("@/components/NavigationProgress").default as () => null;
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const store = require("@/lib/futuresReturnOrigin").questionOrigin as typeof questionOrigin;
      NavigationProgress();
      const anchor = {
        getAttribute: (n: string) => anchorAttrs[n] ?? null,
        hasAttribute: (n: string) => n in anchorAttrs,
      };
      listeners.click({
        target: { closest: () => anchor },
        button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
        ...over,
      });
      nav.push(anchorAttrs.href);
      (g.window as { location: URL }).location = new URL(`${ORIGIN}${anchorAttrs.href}`);
      // The hook stamps the tap with the real clock.
      adopted = store.adopt(envOf(nav, Date.now()));
    });
    return { adopted, started };
  };

  it("a plain tap on a question card is recorded, and the progress bar still starts", () => {
    expect(runNavigationProgressTap({ href: "/futures/231" })).toEqual({ adopted: true, started: 1 });
  });

  it("CONTROL: a cmd-tap is not recorded (and, as before, starts no progress bar)", () => {
    expect(runNavigationProgressTap({ href: "/futures/231" }, { metaKey: true })).toEqual({ adopted: false, started: 0 });
  });

  it("CONTROL: a download link to a question is not recorded, while the bar behaves as before", () => {
    expect(runNavigationProgressTap({ href: "/futures/231", download: "" })).toEqual({ adopted: false, started: 1 });
  });
});
