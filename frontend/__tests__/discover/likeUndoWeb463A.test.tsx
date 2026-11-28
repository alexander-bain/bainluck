/**
 * 463: A (#13829) — Website tapping a filled heart off sends `like_undo` and
 * leaves the card in that reader's Discover, with no negative score and no
 * dismissal count in the browser category profile.
 *
 * Covers both heart senders (`DiscoverCard` and `BundleActionBar`), both real
 * `"unlike"` senders ("Less like this" and left swipe), and the real
 * `lib/discoverInteractions` browser profile + flush batch.
 */

import React from "react";
import { readFileSync } from "fs";
import { resolve } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import type { MarketShape } from "../../lib/marketShape";

const trackEvent = jest.fn();
const routerPush = jest.fn();

let swipe: { left?: () => void; right?: () => void } = {};
let cardBar: { setLiked?: (v: boolean) => void; onDismiss?: () => void } = {};
let bundleBar: { setLiked?: (v: boolean) => void; onDismiss?: () => void } = {};

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));
jest.mock("../../lib/analytics", () => ({
  ...jest.requireActual("../../lib/analytics"),
  trackEvent: (...a: unknown[]) => trackEvent(...a),
}));
jest.mock("../../lib/firebase", () => ({ preloadFirebaseAuth: jest.fn() }));
jest.mock("../../components/discover/EventCard", () => ({
  EventCard: (props: { setLiked: (v: boolean) => void; onDismiss?: () => void }) => {
    cardBar = { setLiked: props.setLiked, onDismiss: props.onDismiss };
    return null;
  },
}));
jest.mock("../../components/discover/shared", () => {
  const actual = jest.requireActual("../../components/discover/shared");
  return {
    ...actual,
    useSwipe: (left?: () => void, right?: () => void, tap?: (e: React.MouseEvent) => void) => {
      swipe = { left, right };
      return actual.useSwipe(left, right, tap);
    },
    ActionBar: (props: { setLiked: (v: boolean) => void; onDismiss?: () => void }) => {
      bundleBar = { setLiked: props.setLiked, onDismiss: props.onDismiss };
      return null;
    },
  };
});
jest.mock("../../components/discover/utils", () => ({
  ...jest.requireActual("../../components/discover/utils"),
  isTrending: () => false,
  suppressBareZeroFuturesCard: () => false,
  feedItemHasRenderableContent: () => true,
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
  require("../../lib/analytics/telemetryConsent").initTelemetryConsent();
  return { store, fetchMock, profileEvents };
}

function uninstallBrowser() {
  const g = global as unknown as Record<string, unknown>;
  delete g.window;
  delete g.localStorage;
  delete g.document;
  delete g.CustomEvent;
  delete g.fetch;
}

function registerPageGate(initial: DiscoverLearningState, uid = "reader-1") {
  const auth = { current: initial, invites: 0 };
  di.setDiscoverLearningGate(
    () => auth.current === "learn",
    { getUid: () => (auth.current === "learn" ? uid : null), getToken: () => Promise.resolve("token-1") },
  );
  const attempt = () => {
    const d = decideDiscoverFeedbackAttempt(auth.current);
    if (d.invite) auth.invites += 1;
    return d.proceed;
  };
  return { auth, attempt };
}

function readSuppressedCategories(profile: di.DiscoverProfile | null): Set<string> {
  const page = readFileSync(resolve(__dirname, "../../app/discover/page.tsx"), "utf8");
  const cooldown = page.slice(page.indexOf("function getSuppressedCategories("), page.indexOf("function getGroupedCategory("));
  const code = ts.transpileModule(cooldown, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  const fn = new Function(
    "isSportsDiscoverCategory",
    "CATEGORY_COOLDOWN_DISMISSES",
    "CATEGORY_COOLDOWN_SCORE",
    code + "\nreturn getSuppressedCategories;",
  )(di.isSportsDiscoverCategory, 3, -3) as (p: di.DiscoverProfile | null) => Set<string>;
  return fn(profile);
}

async function settlePromises() {
  for (let i = 0; i < 6; i++) await Promise.resolve();
}

const NON_SPORTS_EVENT = {
  type: "futures",
  data: { id: 101, name: "Will rate cuts happen?", category: "economics", score: 72, top_outcomes: [] },
};

const NON_SPORTS_CONCEPT_LIKE_EVENT = {
  type: "event",
  data: {
    id: 55,
    sport: "politics_us",
    sport_name: "Politics",
    away_team: "Candidate A",
    home_team: "Candidate B",
    score: 80,
  },
} as unknown as FeedItem;

const BUNDLE_ITEMS = [
  {
    type: "futures",
    data: { id: "m-bundle-1", name: "Who wins?", llm_sport_category: "politics", score: 65, top_outcomes: [] },
  },
] as unknown as FeedItem[];

beforeEach(() => {
  jest.useFakeTimers();
  trackEvent.mockClear();
  routerPush.mockClear();
  swipe = {};
  cardBar = {};
  bundleBar = {};
  browser = installBrowser();
});

afterEach(() => {
  di.setDiscoverLearningGate(null);
  di.dropPendingDiscoverInteractions();
  uninstallBrowser();
  jest.useRealTimers();
});

describe("DiscoverCard heart toggle vs Less like this and swipes", () => {
  function mountSingleCard(state: DiscoverLearningState, onDismiss: jest.Mock) {
    uninstallBrowser();
    const gate = registerPageGate(state);
    renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{ type: "single", item: NON_SPORTS_CONCEPT_LIKE_EVENT } as DiscoverGroupedItem}
        positionIndex={2}
        onDismiss={onDismiss}
        onFeedbackAttempt={gate.attempt}
      />,
    );
    browser = installBrowser();
    if (!cardBar.setLiked || !cardBar.onDismiss || !swipe.left || !swipe.right) {
      throw new Error("DiscoverCard did not wire both action bar and swipe handlers");
    }
    return gate;
  }

  it("sends like on heart-on and like_undo on filled-heart-off without calling onDismiss", async () => {
    const onDismiss = jest.fn();
    mountSingleCard("learn", onDismiss);

    cardBar.setLiked!(true);
    cardBar.setLiked!(false);

    expect(onDismiss).not.toHaveBeenCalled();
    expect(trackEvent.mock.calls).toEqual([
      ["feed_card_action", expect.objectContaining({ action: "like", item_id: 55 })],
      ["feed_card_action", expect.objectContaining({ action: "like_undo", item_id: 55 })],
    ]);
    expect(di.peekPendingDiscoverInteractions().map((i) => [i.action, i.source])).toEqual([
      ["like", "card"],
      ["like_undo", "card"],
    ]);

    const bucket = di.readDiscoverInteractionProfile()!.categories.politics;
    expect(bucket).toMatchObject({ score: 0, likes: 0, dismisses: 0 });
    expect(di.getDiscoverCategoryAdjustment(di.readDiscoverInteractionProfile(), "politics")).toBe(0);

    di.flushDiscoverInteractions();
    await settlePromises();
    const sent = JSON.parse(browser.fetchMock.mock.calls[0][1].body as string);
    expect(sent.interactions.map((i: { action: string; source: string }) => [i.action, i.source])).toEqual([
      ["like", "card"],
      ["like_undo", "card"],
    ]);
  });

  it("keeps Less like this and left swipe sending unlike and calling onDismiss", () => {
    const onDismiss = jest.fn();
    mountSingleCard("learn", onDismiss);

    cardBar.onDismiss!();
    swipe.left!();

    expect(onDismiss).toHaveBeenCalledTimes(2);
    expect(di.peekPendingDiscoverInteractions().map((i) => i.action)).toEqual(["unlike", "unlike"]);
    const bucket = di.readDiscoverInteractionProfile()!.categories.politics;
    expect(bucket).toMatchObject({ score: -2, dismisses: 2 });
  });

  it("keeps right swipe sending like and calling onDismiss", () => {
    const onDismiss = jest.fn();
    mountSingleCard("learn", onDismiss);

    swipe.right!();

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(di.peekPendingDiscoverInteractions().map((i) => i.action)).toEqual(["like"]);
  });

  it("refuses filled-heart-off cleanly when signed out", () => {
    const onDismiss = jest.fn();
    const gate = mountSingleCard("invite", onDismiss);

    cardBar.setLiked!(false);

    expect(gate.auth.invites).toBe(1);
    expect(onDismiss).not.toHaveBeenCalled();
    expect(trackEvent).not.toHaveBeenCalled();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});

describe("BundleActionBar heart toggle vs set dismiss", () => {
  function mountBundle(state: DiscoverLearningState, onDismiss: jest.Mock) {
    uninstallBrowser();
    const gate = registerPageGate(state);
    renderToStaticMarkup(
      <DiscoverFeedbackAttemptContext.Provider value={gate.attempt}>
        <BundleActionBar
          items={BUNDLE_ITEMS}
          title="Politics"
          storyKey="story-463"
          positionIndex={1}
          onDismiss={onDismiss}
        />
      </DiscoverFeedbackAttemptContext.Provider>,
    );
    browser = installBrowser();
    if (!bundleBar.setLiked || !bundleBar.onDismiss) {
      throw new Error("BundleActionBar did not render ActionBar");
    }
    return gate;
  }

  it("sends like on heart-on and like_undo on filled-heart-off with source bundle and leaves no negative score", async () => {
    const onDismiss = jest.fn();
    mountBundle("learn", onDismiss);

    bundleBar.setLiked!(true);
    bundleBar.setLiked!(false);

    expect(onDismiss).not.toHaveBeenCalled();
    expect(trackEvent.mock.calls).toEqual([
      ["feed_card_action", expect.objectContaining({ action: "like", story_key: "story-463" })],
      ["feed_card_action", expect.objectContaining({ action: "like_undo", story_key: "story-463" })],
    ]);
    expect(di.peekPendingDiscoverInteractions().map((i) => [i.action, i.source])).toEqual([
      ["like", "bundle"],
      ["like_undo", "bundle"],
    ]);

    const bucket = di.readDiscoverInteractionProfile()!.categories.politics;
    expect(bucket).toMatchObject({ score: 0, likes: 0, dismisses: 0 });

    di.flushDiscoverInteractions();
    await settlePromises();
    const sent = JSON.parse(browser.fetchMock.mock.calls[0][1].body as string);
    expect(sent.interactions.map((i: { action: string; source: string }) => [i.action, i.source])).toEqual([
      ["like", "bundle"],
      ["like_undo", "bundle"],
    ]);
  });

  it("keeps bundle Less like this sending dismiss and calling onDismiss", () => {
    const onDismiss = jest.fn();
    mountBundle("learn", onDismiss);

    bundleBar.onDismiss!();

    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(di.peekPendingDiscoverInteractions().map((i) => [i.action, i.source])).toEqual([
      ["dismiss", "bundle"],
    ]);
    expect(di.readDiscoverInteractionProfile()!.categories.politics).toMatchObject({
      score: -2,
      dismisses: 1,
    });
  });

  it("refuses signed-out bundle heart-off cleanly", () => {
    const onDismiss = jest.fn();
    const gate = mountBundle("invite", onDismiss);

    bundleBar.setLiked!(false);

    expect(gate.auth.invites).toBe(1);
    expect(trackEvent).not.toHaveBeenCalled();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});

describe("discoverInteractions category profile handling of like_undo", () => {
  it("like -> like_undo -> like leaves net +2, likes=1, dismisses=0, never suppressed", () => {
    registerPageGate("learn");

    di.recordDiscoverInteraction("economics", "like");
    di.recordDiscoverInteraction("economics", "like_undo");
    di.recordDiscoverInteraction("economics", "like");

    const profile = di.readDiscoverInteractionProfile()!;
    expect(profile.categories.economics).toMatchObject({ score: 2, likes: 1, dismisses: 0 });
    expect([...readSuppressedCategories(profile)]).toEqual([]);
  });

  it("three consecutive like -> like_undo pairs never cool down or penalize the category", () => {
    registerPageGate("learn");

    for (let i = 0; i < 4; i++) {
      di.recordDiscoverInteraction("economics", "like");
      di.recordDiscoverInteraction("economics", "like_undo");
    }

    const profile = di.readDiscoverInteractionProfile()!;
    expect(profile.categories.economics).toMatchObject({ score: 0, likes: 0, dismisses: 0 });
    expect([...readSuppressedCategories(profile)]).toEqual([]);
  });

  it("unmatched like_undo on empty profile or detail_click-only bucket is a clean no-op", () => {
    registerPageGate("learn");

    di.recordDiscoverInteraction("economics", "like_undo");
    expect(di.readDiscoverInteractionProfile()).toBeNull();

    di.recordDiscoverInteraction("economics", "detail_click");
    const before = di.readDiscoverInteractionProfile()!;
    di.recordDiscoverInteraction("economics", "like_undo");
    const after = di.readDiscoverInteractionProfile()!;
    expect(after).toEqual(before);
    expect(after.categories.economics).toMatchObject({ score: 1.5, clicks: 1, likes: 0, dismisses: 0 });
  });

  it("sports like -> like_undo cancels cleanly without negative score", () => {
    registerPageGate("learn");

    di.recordDiscoverInteraction("baseball", "like");
    di.recordDiscoverInteraction("baseball", "like_undo");

    const profile = di.readDiscoverInteractionProfile()!;
    expect(profile.categories.baseball).toMatchObject({ score: 0, likes: 0, dismisses: 0 });
    di.recordDiscoverInteraction("baseball", "like_undo");
    expect(di.readDiscoverInteractionProfile()!.categories.baseball).toMatchObject({ score: 0, likes: 0, dismisses: 0 });
  });

  it("preserves prior positive detail_click score when undoing a like alongside an analytics payload", () => {
    const analytics = di.getDiscoverItemAnalytics(NON_SPORTS_EVENT as unknown as FeedItem);
    expect(analytics.category).toBe("other");
    expect(analytics.market_type).toBeDefined();
    registerPageGate("learn");

    di.recordDiscoverInteraction("politics", "detail_click");
    di.recordDiscoverInteraction("politics", "like");
    di.recordDiscoverInteraction("politics", "like_undo");

    const bucket = di.readDiscoverInteractionProfile()!.categories.politics;
    expect(bucket).toMatchObject({ score: 1.5, clicks: 1, likes: 0, dismisses: 0 });
    expect(bucket.last_interaction_at).toBeTruthy();
    expect(Object.keys(di.readDiscoverInteractionProfile()!.categories)).toEqual(["politics"]);
  });

  it("still preserves market_type on sent like_undo wire item", () => {
    registerPageGate("learn");
    di.sendDiscoverInteraction(
      {
        content_type: "futures",
        item_id: "f-99",
        category: "politics",
        item_name: "Election market",
        score: 50,
        market_type: "claim" as MarketShape,
      },
      "like_undo",
      0,
    );
    expect(di.peekPendingDiscoverInteractions()[0]).toMatchObject({
      action: "like_undo",
      item_type: "futures",
      item_id: "f-99",
      source: "card",
      market_type: "claim",
    });
  });
});
