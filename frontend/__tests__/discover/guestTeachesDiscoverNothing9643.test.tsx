/**
 * #9643 — A GUEST TEACHES DISCOVER NOTHING, AT THE WRITERS.
 *
 * The swipe suite (`signedOutSwipeInvitesSignIn9643.test.tsx`) proves the card's
 * gate with the writers mocked. That left every OTHER learning action open:
 * impressions, taps (`detail_click`), shares, group expands and the bundle
 * like — each one scores the local profile (`ACTION_WEIGHTS`) and queues a
 * server interaction the backend personalises from. This suite runs the REAL
 * `lib/discoverInteractions` writers against a fake browser and asserts on what
 * actually lands: the `discover_interaction_profile_v1` blob, the pending
 * server queue, and the POST that leaves at flush.
 *
 * The GA4 `trackEvent` beside each write is ordinary non-personal analytics and
 * must keep firing; it is mocked here only so the suite can see that it did.
 *
 * No jsdom (`testEnvironment: node`): components render once under SSR so their
 * real hooks run, and the browser globals are installed AFTER the render, before
 * the captured handler is called — the same order a real tap has.
 */

import React from "react";
import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import type { MarketShape } from "../../lib/marketShape";

const trackEvent = jest.fn();
const routerPush = jest.fn();
let swipe: { left?: () => void; right?: () => void; tap?: (e: React.MouseEvent) => void } = {};
let actionBar: { setLiked?: (v: boolean) => void; onShare?: () => void } = {};

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));
jest.mock("../../lib/analytics", () => ({
  ...jest.requireActual("../../lib/analytics"),
  trackEvent: (...a: unknown[]) => trackEvent(...a),
}));
jest.mock("../../lib/firebase", () => ({ preloadFirebaseAuth: jest.fn() }));
jest.mock("../../components/discover/shared", () => {
  const actual = jest.requireActual("../../components/discover/shared");
  return {
    ...actual,
    useSwipe: (left?: () => void, right?: () => void, tap?: (e: React.MouseEvent) => void) => {
      swipe = { left, right, tap };
      return actual.useSwipe(left, right, tap);
    },
    // Capture the bundle bar's real handlers; the bar's markup is not the subject.
    ActionBar: (props: { setLiked: (v: boolean) => void; onShare?: () => void }) => {
      actionBar = { setLiked: props.setLiked, onShare: props.onShare };
      return null;
    },
  };
});
jest.mock("../../components/discover/utils", () => ({
  ...jest.requireActual("../../components/discover/utils"),
  isTrending: () => false,
  suppressBareZeroFuturesCard: () => false,
  feedItemHasRenderableContent: () => false,
  feedItemHref: () => "/events/1",
}));

import * as di from "../../lib/discoverInteractions";
import DiscoverCard from "../../components/DiscoverCard";
import { BundleActionBar } from "../../components/discover/BundleActionBar";
import {
  DiscoverFeedbackAttemptContext,
  decideDiscoverFeedbackAttempt,
  type DiscoverLearningState,
} from "../../lib/discoverFeedbackGate";
import type { FeedItem } from "../../lib/types";
import type { DiscoverGroupedItem } from "../../components/discover/types";

const PROFILE_KEY = "discover_interaction_profile_v1";

// ── a fake browser, installed per test ─────────────────────────────────────────

interface Browser {
  store: Record<string, string>;
  fetchMock: jest.Mock;
  profileEvents: string[];
}

let browser: Browser;

function installBrowser(): Browser {
  const store: Record<string, string> = { bainluck_consent: "all" };
  const profileEvents: string[] = [];
  const fetchMock = jest.fn((_url: string, _init: unknown) => Promise.resolve({ ok: true }));
  const g = global as unknown as Record<string, unknown>;
  g.fetch = fetchMock;
  g.window = {
    dataLayer: [],
    gtag: () => {},
    navigator: { userAgent: "node" },
    location: { href: "http://localhost/discover", pathname: "/discover" },
    addEventListener: () => {},
    dispatchEvent: (e: { type: string }) => {
      profileEvents.push(e.type);
      return true;
    },
  };
  g.CustomEvent = class {
    type: string;
    constructor(type: string) {
      this.type = type;
    }
  };
  g.localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  g.document = { title: "T", referrer: "" };
  // Consent GRANTED, so a refused write is refused by the auth gate and not by
  // consent — otherwise the flush assertions would pass for the wrong reason.
  require("../../lib/analytics/telemetryConsent").initTelemetryConsent();
  return { store, fetchMock, profileEvents };
}

function uninstallBrowser() {
  const g = global as unknown as Record<string, unknown>;
  delete g.window;
  delete g.localStorage;
  delete g.document;
}

/** What the page registers: the current auth state, read at write time. */
function registerPageGate(initial: DiscoverLearningState) {
  const auth = { current: initial, invites: 0 };
  di.setDiscoverLearningGate(() => auth.current === "learn");
  const attempt = () => {
    const d = decideDiscoverFeedbackAttempt(auth.current);
    if (d.invite) auth.invites += 1;
    return d.proceed;
  };
  return { auth, attempt };
}

const ITEM = {
  content_type: "futures" as const,
  item_id: "f-1",
  category: "politics",
  item_name: "Test market",
  score: 50,
  market_type: "claim" as MarketShape,
};

const ALL_ACTIONS = [
  "impression",
  "detail_click",
  "dismiss",
  "like",
  "unlike",
  "share",
  "group_expand",
  "challenge_start",
  "challenge_complete",
  "context_expand",
  "context_collapse",
] as const;

function writeEveryAction() {
  for (const a of ALL_ACTIONS) {
    di.recordDiscoverInteraction("politics", a);
    di.sendDiscoverInteraction(ITEM, a, 0);
  }
}

function sentBatches(): Array<{ interactions: Array<{ action: string }> }> {
  return browser.fetchMock.mock.calls.map((c) => JSON.parse((c[1] as { body: string }).body));
}

beforeEach(() => {
  jest.useFakeTimers();
  trackEvent.mockClear();
  routerPush.mockClear();
  swipe = {};
  actionBar = {};
  browser = installBrowser();
});

afterEach(() => {
  di.setDiscoverLearningGate(null);
  di.dropPendingDiscoverInteractions();
  uninstallBrowser();
  jest.useRealTimers();
});

// ── the writers ────────────────────────────────────────────────────────────────

describe("the writers refuse every learning action unless the reader is signed in", () => {
  it("CONTROL: signed in, every action scores the profile and queues for the server", () => {
    registerPageGate("learn");
    writeEveryAction();

    expect(JSON.parse(browser.store[PROFILE_KEY]).categories.politics).toBeDefined();
    expect(di.peekPendingDiscoverInteractions()).toHaveLength(ALL_ACTIONS.length);
    di.flushDiscoverInteractions();
    expect(sentBatches()[0].interactions).toHaveLength(ALL_ACTIONS.length);
  });

  it.each(["invite", "hold"] as const)("%s: no profile, no queue, no request, no profile event", (state) => {
    registerPageGate(state);
    writeEveryAction();

    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(browser.profileEvents).toEqual([]);
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
    di.flushDiscoverInteractions();
    jest.runOnlyPendingTimers();
    expect(browser.fetchMock).not.toHaveBeenCalled();
  });

  it("a guest's existing (pre-v3) profile is left exactly as it was", () => {
    const before = JSON.stringify({ categories: { nfl: { score: 4 } }, updated_at: "2026-09-01T00:00:00Z" });
    browser.store[PROFILE_KEY] = before;
    registerPageGate("invite");
    writeEveryAction();
    expect(browser.store[PROFILE_KEY]).toBe(before);
  });

  it("guest actions, then sign-in: nothing is replayed — the first request carries only signed-in actions", () => {
    const { auth } = registerPageGate("invite");
    di.sendDiscoverInteraction(ITEM, "impression", 0, "viewport");
    di.sendDiscoverInteraction(ITEM, "detail_click", 0);
    di.sendDiscoverInteraction(ITEM, "share", 0);

    auth.current = "learn";
    jest.runOnlyPendingTimers();
    di.flushDiscoverInteractions();
    expect(browser.fetchMock).not.toHaveBeenCalled();

    di.sendDiscoverInteraction(ITEM, "like", 0);
    di.flushDiscoverInteractions();
    expect(sentBatches().map((b) => b.interactions.map((i) => i.action))).toEqual([["like"]]);
  });

  it("a batch queued while signed in does not land after a sign-out", () => {
    const { auth } = registerPageGate("learn");
    di.sendDiscoverInteraction(ITEM, "detail_click", 0);
    expect(di.peekPendingDiscoverInteractions()).toHaveLength(1);

    auth.current = "invite";
    jest.runOnlyPendingTimers();
    expect(browser.fetchMock).not.toHaveBeenCalled();

    // Signing back in does not resurrect it either — it was dropped, not held.
    auth.current = "learn";
    di.flushDiscoverInteractions();
    expect(browser.fetchMock).not.toHaveBeenCalled();
  });

  it("a gate that throws refuses (fail closed)", () => {
    di.setDiscoverLearningGate(() => {
      throw new Error("auth context gone");
    });
    writeEveryAction();
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });

  it("before the page auth effect registers, child interactions cannot learn", () => {
    writeEveryAction();
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
    di.flushDiscoverInteractions();
    expect(browser.fetchMock).not.toHaveBeenCalled();
  });

  it("unmounting the auth owner cannot flush a previously queued batch", () => {
    registerPageGate("learn");
    di.sendDiscoverInteraction(ITEM, "like", 0);
    expect(di.peekPendingDiscoverInteractions()).toHaveLength(1);
    di.setDiscoverLearningGate(null);
    di.flushDiscoverInteractions();
    expect(browser.fetchMock).not.toHaveBeenCalled();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});

// ── real components over the real writers ──────────────────────────────────────

const eventItem = { type: "event", data: {} } as unknown as FeedItem;

function tapEvent(): React.MouseEvent {
  return {
    defaultPrevented: false,
    button: 0,
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    target: { closest: () => null },
  } as unknown as React.MouseEvent;
}

describe("a guest's tap on a card opens it, fires GA4, and teaches nothing", () => {
  function mountAndTap(state: DiscoverLearningState) {
    uninstallBrowser(); // SSR render: no window, as on the server
    const grouped = { type: "single", item: eventItem } as DiscoverGroupedItem;
    renderToStaticMarkup(<DiscoverCard groupedItem={grouped} positionIndex={0} onDismiss={() => {}} />);
    browser = installBrowser();
    registerPageGate(state);
    swipe.tap!(tapEvent());
  }

  it("CONTROL: signed in, the tap scores the profile and queues detail_click", () => {
    mountAndTap("learn");
    expect(routerPush).toHaveBeenCalledWith("/events/1");
    expect(browser.store[PROFILE_KEY]).toBeDefined();
    expect(di.peekPendingDiscoverInteractions().map((i) => i.action)).toEqual(["detail_click"]);
  });

  it("guest: navigates and fires the GA4 event, but no profile and no queued interaction", () => {
    mountAndTap("invite");
    expect(routerPush).toHaveBeenCalledWith("/events/1");
    expect(trackEvent).toHaveBeenCalledWith("feed_card_action", expect.objectContaining({ action: "detail_click" }));
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});

describe("the bundle action bar", () => {
  const bundleItems = [
    { type: "futures", data: { id: "m1", name: "Who wins?", top_outcomes: [] } },
  ] as unknown as FeedItem[];

  function mountBar(state: DiscoverLearningState, withContext = true) {
    uninstallBrowser();
    const gate = registerPageGate(state);
    const bar = <BundleActionBar items={bundleItems} title="Politics" storyKey="story-1" positionIndex={2} />;
    renderToStaticMarkup(
      withContext ? (
        <DiscoverFeedbackAttemptContext.Provider value={gate.attempt}>{bar}</DiscoverFeedbackAttemptContext.Provider>
      ) : (
        bar
      ),
    );
    browser = installBrowser();
    if (!actionBar.setLiked || !actionBar.onShare) throw new Error("the bar never rendered its ActionBar");
    return gate;
  }

  it("CONTROL: signed in, a bundle like scores the profile and queues", () => {
    const gate = mountBar("learn");
    actionBar.setLiked!(true);
    expect(gate.auth.invites).toBe(0);
    expect(browser.store[PROFILE_KEY]).toBeDefined();
    expect(di.peekPendingDiscoverInteractions().map((i) => [i.action, i.source])).toEqual([["like", "bundle"]]);
  });

  it("guest: a bundle like is refused before anything happens, and invites", () => {
    const gate = mountBar("invite");
    actionBar.setLiked!(true);
    expect(gate.auth.invites).toBe(1);
    expect(trackEvent).not.toHaveBeenCalled();
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });

  it("auth loading: a bundle like is refused silently", () => {
    const gate = mountBar("hold");
    actionBar.setLiked!(true);
    expect(gate.auth.invites).toBe(0);
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });

  it("guest share still shares and fires GA4, but teaches nothing", () => {
    const gate = mountBar("invite");
    actionBar.onShare!();
    expect(gate.auth.invites).toBe(0);
    expect(trackEvent).toHaveBeenCalledWith("feed_card_action", expect.objectContaining({ action: "share" }));
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });

  it("outside the page's provider the writers' gate still holds", () => {
    mountBar("invite", false);
    actionBar.setLiked!(true);
    expect(browser.store[PROFILE_KEY]).toBeUndefined();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});

// ── the census: the gate covers every writer call site ─────────────────────────

describe("every writer call site sits under the page that registers the gate", () => {
  const root = join(__dirname, "../..");
  const strip = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  function sourceFiles(dir: string): string[] {
    return readdirSync(dir).flatMap((name) => {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) return sourceFiles(p);
      return /\.(ts|tsx)$/.test(name) ? [p] : [];
    });
  }
  const files = ["app", "components", "lib", "hooks"]
    .map((d) => join(root, d))
    .filter((d) => {
      try {
        return statSync(d).isDirectory();
      } catch {
        return false;
      }
    })
    .flatMap(sourceFiles);

  it("the writers are called from exactly these files — a new caller must be traced to the gate", () => {
    const callers = files
      .filter((f) => !f.endsWith("lib/discoverInteractions.ts"))
      .filter((f) => /\b(recordDiscoverInteraction|sendDiscoverInteraction)\(/.test(strip(readFileSync(f, "utf8"))))
      .map((f) => relative(root, f))
      .sort();
    expect(callers).toEqual([
      "app/discover/page.tsx",
      "components/DiscoverCard.tsx",
      "components/discover/BundleActionBar.tsx",
      "components/discover/GroupCard.tsx",
      "components/discover/ThemeBundleCard.tsx",
    ]);
  });

  it("the card components that call them mount only under the Discover page", () => {
    const importers = (pattern: RegExp) =>
      files
        .filter((f) => pattern.test(strip(readFileSync(f, "utf8"))))
        .map((f) => relative(root, f))
        .sort();
    expect(importers(/from "[^"]*\/DiscoverCard"/)).toEqual(["app/discover/page.tsx"]);
    expect(importers(/from "[^"]*\/(GroupCard|ThemeBundleCard)"/)).toEqual(["components/DiscoverCard.tsx"]);
    expect(importers(/from "[^"]*\/BundleActionBar"/)).toEqual([
      "components/discover/GroupCard.tsx",
      "components/discover/ThemeBundleCard.tsx",
    ]);
  });

  it("the page registers the writers' gate from the current auth state and provides the attempt handler", () => {
    const page = strip(readFileSync(join(root, "app/discover/page.tsx"), "utf8"));
    expect(page).toMatch(/setDiscoverLearningGate\(\(\) => learningStateRef\.current === "learn"\)/);
    expect(page).toContain("return () => setDiscoverLearningGate(null);");
    expect(page).toContain("<DiscoverFeedbackAttemptContext.Provider value={handleFeedbackAttempt}>");
  });
});
