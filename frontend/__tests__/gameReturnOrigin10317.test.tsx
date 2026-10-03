/**
 * #10317 — the game page's Back goes to the page the reader tapped from, and
 * only when that entry is provably the one immediately behind the game.
 *
 * Specimen walk (latency/lat1828, production 390px): `/sports/americanfootball_nfl`
 * → game card → `/events/14639205` → "Back to events" landed on Discover,
 * because the control was a hard `<Link href="/">`. The proof is #10265's
 * (`lib/futuresReturnOrigin.ts`), from the game page's own store.
 *
 * The fake models the Navigation API as #10265's test does: same-origin entries
 * only, a push truncates forward entries and mints id + key, a replace keeps the
 * slot's key and mints a new id.
 */
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import {
  createGameOriginStore,
  createQuestionOriginStore,
  gameOrigin,
  gamePathOf,
  type OriginClick,
  type OriginEnv,
} from "@/lib/futuresReturnOrigin";

const ORIGIN = "https://bainluck.com";

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
    return { id: `g${fakeSeq}`, key: key ?? `gk${fakeSeq}`, index, url };
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
  get url() {
    return this.list[this.at].url;
  }
}

const envOf = (nav: FakeNavigation | null, now = 1_000_000, url?: string): OriginEnv => {
  const href = `${ORIGIN}${url ?? nav?.url ?? "/"}`;
  return { origin: ORIGIN, href, pathname: new URL(href).pathname, navigation: nav, now };
};

const tap = (href: string | null, over: Partial<OriginClick> = {}): OriginClick => ({
  href, button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
  target: null, download: false, ...over,
});

const LEAGUE = "/sports/americanfootball_nfl";
const GAME = "/events/14639205";

describe("#10317 the game page's proof", () => {
  it("SPECIMEN: league → game card → Back is proven to go to the league page", () => {
    const s = createGameOriginStore();
    const nav = new FakeNavigation(LEAGUE);
    expect(s.recordClick(tap(GAME), envOf(nav))).toBe(true);
    nav.push(GAME);
    expect(s.adopt(envOf(nav))).toBe(true);
    expect(s.canGoBack(envOf(nav))).toBe(true);
  });

  it("game → another game (a More NFL card) → Back is proven to go to the first game", () => {
    const s = createGameOriginStore();
    const nav = new FakeNavigation("/events/1");
    expect(s.recordClick(tap("/events/2"), envOf(nav))).toBe(true);
    nav.push("/events/2");
    expect(s.adopt(envOf(nav))).toBe(true);
    expect(s.canGoBack(envOf(nav))).toBe(true);
  });

  it("CONTROL: a direct open (shared link, reload) with history behind it has no proof", () => {
    const s = createGameOriginStore();
    const nav = new FakeNavigation(LEAGUE);
    nav.push(GAME); // an entry behind, but no tap recorded it
    expect(s.adopt(envOf(nav))).toBe(false);
    expect(s.canGoBack(envOf(nav))).toBe(false);
  });

  it("CONTROL: the game page replacing itself onto another game (a canonical redirect) loses the proof", () => {
    const s = createGameOriginStore();
    const nav = new FakeNavigation(LEAGUE);
    s.recordClick(tap(GAME), envOf(nav));
    nav.push(GAME);
    nav.replace("/events/99");
    expect(s.adopt(envOf(nav))).toBe(false);
    expect(s.canGoBack(envOf(nav))).toBe(false);
  });

  it("the stores are separate: each refuses the other's pages and the models subpage", () => {
    const game = createGameOriginStore();
    const question = createQuestionOriginStore();
    const env = envOf(new FakeNavigation(LEAGUE));
    expect(game.recordClick(tap("/futures/231"), env)).toBe(false);
    expect(game.recordClick(tap(`${GAME}/models`), env)).toBe(false);
    expect(question.recordClick(tap(GAME), env)).toBe(false);
    expect(gamePathOf(`${GAME}/`, env)).toBe(GAME);
    expect(gamePathOf(`https://bainluck.com.evil.example${GAME}`, env)).toBeNull();
  });

  it("a link to the game already on screen (a range or tab change) is not a move", () => {
    const s = createGameOriginStore();
    expect(s.recordClick(tap(`${GAME}?range=all`), envOf(new FakeNavigation(GAME)))).toBe(false);
  });
});

const linkProps: { onClick?: (e: unknown) => void; href?: string }[] = [];
jest.mock("next/link", () => ({
  __esModule: true,
  default: (props: { href: string; onClick?: (e: unknown) => void; children: React.ReactNode }) => {
    linkProps.push(props);
    return <a href={props.href}>{props.children}</a>;
  },
}));

import OriginBackControl from "@/components/OriginBackControl";

describe("#10317 the game page's control", () => {
  const g = globalThis as unknown as { window?: unknown };
  afterEach(() => {
    delete g.window;
    linkProps.length = 0;
  });
  const click = (over: Record<string, unknown> = {}) => ({
    button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
    preventDefault: jest.fn(), ...over,
  });
  const render = (onNavigate?: (to: string) => void) =>
    renderToStaticMarkup(
      <OriginBackControl store={gameOrigin} fallbackHref="/" fallbackLabel="Back to events" onNavigate={onNavigate} />,
    );

  it("renders the old link and label on the server (no history to read)", () => {
    expect(render()).toMatch(/^<a href="\/">[\s\S]*Back to events<\/a>$/);
  });

  it("with a proven predecessor a plain tap goes back exactly once and reports 'back'", () => {
    const nav = new FakeNavigation(LEAGUE);
    const back = jest.fn();
    const onNavigate = jest.fn();
    g.window = { location: new URL(`${ORIGIN}${LEAGUE}`), navigation: nav, history: { back } };
    gameOrigin.recordClick(tap(GAME), envOf(nav));
    nav.push(GAME);
    (g.window as { location: URL }).location = new URL(`${ORIGIN}${GAME}`);
    gameOrigin.adopt(envOf(nav));

    render(onNavigate);
    const onClick = linkProps[linkProps.length - 1].onClick!;
    const first = click();
    onClick(first);
    onClick(click());
    expect(first.preventDefault).toHaveBeenCalled();
    expect(back).toHaveBeenCalledTimes(1);
    expect(onNavigate).toHaveBeenCalledWith("back");
  });

  it("CONTROL: without proof the tap is the old link's, and analytics still sees '/'", () => {
    const nav = new FakeNavigation("/discover");
    nav.push(GAME);
    const back = jest.fn();
    const onNavigate = jest.fn();
    g.window = { location: new URL(`${ORIGIN}${GAME}`), navigation: nav, history: { back } };
    render(onNavigate);
    const e = click();
    linkProps[linkProps.length - 1].onClick!(e);
    expect(e.preventDefault).not.toHaveBeenCalled();
    expect(back).not.toHaveBeenCalled();
    expect(onNavigate).toHaveBeenCalledWith("/");
  });
});

describe("#10317 wiring", () => {
  const g = globalThis as unknown as { window?: unknown; document?: unknown };
  afterEach(() => {
    delete g.window;
    delete g.document;
  });

  it("NavigationProgress records a tap on a game card into the game store", () => {
    let adopted = false;
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
        usePathname: () => LEAGUE,
        useSearchParams: () => new URLSearchParams(),
      }));
      jest.doMock("nprogress", () => ({
        __esModule: true,
        default: { configure() {}, start() {}, done() {} },
      }));
      const nav = new FakeNavigation(LEAGUE);
      g.window = { location: new URL(`${ORIGIN}${LEAGUE}`), navigation: nav, history: { back() {} } };
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const NavigationProgress = require("@/components/NavigationProgress").default as () => null;
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const store = require("@/lib/futuresReturnOrigin").gameOrigin as typeof gameOrigin;
      NavigationProgress();
      const anchor = { getAttribute: (n: string) => (n === "href" ? GAME : null), hasAttribute: () => false };
      listeners.click({ target: { closest: () => anchor }, button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false });
      nav.push(GAME);
      (g.window as { location: URL }).location = new URL(`${ORIGIN}${GAME}`);
      adopted = store.adopt(envOf(nav, Date.now()));
    });
    expect(adopted).toBe(true);
  });

  it("the game page's back control is the origin control on the game store, not a hard link to /", () => {
    const page = readFileSync(join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    const uses = page.split("<OriginBackControl").slice(1).map((rest) => rest.slice(0, rest.indexOf("/>")));
    expect(uses).toHaveLength(1);
    expect(uses[0]).toContain("store={gameOrigin}");
    expect(uses[0]).toContain('fallbackHref="/"');
    // The defect's shape: a plain Link to / that is the page's back control.
    expect(page).not.toMatch(/<Link\s+href="\/"\s/);
  });
});
