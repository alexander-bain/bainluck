/**
 * #9643 — A SIGNED-OUT SWIPE INVITES SIGN-IN AND TEACHES DISCOVER NOTHING.
 *
 * v3 rule: only a signed-in reader's swipes shape the feed. A signed-out
 * swipe opens a dismissible invitation; the local profile, the server
 * interaction queue and the dismiss set are all left untouched, and signing in
 * afterwards does not replay the refused swipe.
 *
 * ── HOW THE CARD IS DRIVEN WITHOUT A DOM ────────────────────────────────────
 *
 * `testEnvironment` is `node` with no jsdom (see #4431's suite). An SSR render
 * runs the real `SingleCard` hooks once, and the mocked `useSwipe` hands back
 * the exact left/right/tap callbacks the card built — so calling them is the
 * card's own code path, gate included. `setLiked` is a no-op under SSR; the
 * observables are the write functions, which are mocked.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

const recordDiscoverInteraction = jest.fn();
const sendDiscoverInteraction = jest.fn();
const trackEvent = jest.fn();
const routerPush = jest.fn();

type SwipeCallbacks = {
  left?: () => void;
  right?: () => void;
  tap?: (e: React.MouseEvent) => void;
};
let swipe: SwipeCallbacks = {};

jest.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));
jest.mock("../../lib/analytics", () => ({ trackEvent: (...a: unknown[]) => trackEvent(...a) }));
jest.mock("../../lib/firebase", () => ({ preloadFirebaseAuth: jest.fn() }));
jest.mock("../../lib/discoverInteractions", () => ({
  ...jest.requireActual("../../lib/discoverInteractions"),
  recordDiscoverInteraction: (...a: unknown[]) => recordDiscoverInteraction(...a),
  sendDiscoverInteraction: (...a: unknown[]) => sendDiscoverInteraction(...a),
  getDiscoverItemAnalytics: () => ({
    content_type: "event",
    item_id: "evt-1",
    category: "nfl",
    item_name: "A at B",
    score: 50,
    market_type: "unshaped",
  }),
}));
jest.mock("../../components/discover/shared", () => {
  const actual = jest.requireActual("../../components/discover/shared");
  return {
    ...actual,
    useSwipe: (
      left?: () => void,
      right?: () => void,
      tap?: (e: React.MouseEvent) => void,
    ) => {
      swipe = { left, right, tap };
      return actual.useSwipe(left, right, tap);
    },
  };
});
jest.mock("../../components/discover/utils", () => ({
  ...jest.requireActual("../../components/discover/utils"),
  isTrending: () => false,
  suppressBareZeroFuturesCard: () => false,
  // Render nothing below the hooks: the gate lives in the hooks, and the leaf
  // cards are not what this suite is about.
  feedItemHasRenderableContent: () => false,
  feedItemHref: () => "/events/1",
}));

import DiscoverCard from "../../components/DiscoverCard";
import SignInToPersonalizeInvite from "../../components/discover/SignInToPersonalizeInvite";
import {
  decideDiscoverFeedbackAttempt,
  resolveDiscoverLearning,
  runDiscoverInviteSignIn,
  type DiscoverLearningState,
} from "../../lib/discoverFeedbackGate";
import type { FeedItem } from "../../lib/types";
import type { DiscoverGroupedItem } from "../../components/discover/types";

const item = { type: "event", data: {} } as unknown as FeedItem;
const grouped: DiscoverGroupedItem = { type: "single", item } as DiscoverGroupedItem;

/** The page's `handleFeedbackAttempt`, driven by a settable auth state. */
function pageGate(initial: DiscoverLearningState) {
  const state = { current: initial, invites: 0 };
  const attempt = () => {
    const d = decideDiscoverFeedbackAttempt(state.current);
    if (d.invite) state.invites += 1;
    return d.proceed;
  };
  return { state, attempt };
}

function mountCard(onDismiss: () => void, onFeedbackAttempt?: () => boolean): SwipeCallbacks {
  swipe = {};
  renderToStaticMarkup(
    <DiscoverCard groupedItem={grouped} positionIndex={0} onDismiss={onDismiss} onFeedbackAttempt={onFeedbackAttempt} />,
  );
  if (!swipe.left || !swipe.right) throw new Error("the card never reached useSwipe");
  return swipe;
}

beforeEach(() => {
  recordDiscoverInteraction.mockClear();
  sendDiscoverInteraction.mockClear();
  trackEvent.mockClear();
  routerPush.mockClear();
});

describe("resolveDiscoverLearning — three states, because auth restore is async", () => {
  it("signed in with a uid learns", () => {
    expect(resolveDiscoverLearning({ isLoading: false, isAuthenticated: true, uid: "u1" })).toBe("learn");
  });
  it("resolved signed-out is invited", () => {
    expect(resolveDiscoverLearning({ isLoading: false, isAuthenticated: false, uid: null })).toBe("invite");
  });
  it("auth still loading holds — even if a stale user object is present", () => {
    expect(resolveDiscoverLearning({ isLoading: true, isAuthenticated: true, uid: "u1" })).toBe("hold");
    expect(resolveDiscoverLearning({ isLoading: true, isAuthenticated: false, uid: null })).toBe("hold");
  });
  it("authenticated without a uid holds", () => {
    expect(resolveDiscoverLearning({ isLoading: false, isAuthenticated: true, uid: undefined })).toBe("hold");
  });
  it("only `learn` proceeds; only `invite` opens the invitation", () => {
    expect(decideDiscoverFeedbackAttempt("learn")).toEqual({ proceed: true, invite: false });
    expect(decideDiscoverFeedbackAttempt("invite")).toEqual({ proceed: false, invite: true });
    expect(decideDiscoverFeedbackAttempt("hold")).toEqual({ proceed: false, invite: false });
  });
});

describe("DiscoverCard — the gate sits in front of every preference write", () => {
  it("CONTROL: signed in, both swipes record locally, queue for the server and dismiss", () => {
    const onDismiss = jest.fn();
    const { attempt } = pageGate("learn");
    const s = mountCard(onDismiss, attempt);

    s.left!();
    s.right!();

    expect(recordDiscoverInteraction.mock.calls).toEqual([["nfl", "unlike"], ["nfl", "like"]]);
    expect(sendDiscoverInteraction).toHaveBeenCalledTimes(2);
    expect(onDismiss).toHaveBeenCalledTimes(2);
  });

  it("guest: a swipe either way writes nothing, dismisses nothing, and invites", () => {
    const onDismiss = jest.fn();
    const { state, attempt } = pageGate("invite");
    const s = mountCard(onDismiss, attempt);

    s.left!();
    s.right!();

    expect(recordDiscoverInteraction).not.toHaveBeenCalled();
    expect(sendDiscoverInteraction).not.toHaveBeenCalled();
    expect(trackEvent).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();
    expect(state.invites).toBe(2);
  });

  it("auth loading: refused silently — no writes and no invitation", () => {
    const onDismiss = jest.fn();
    const { state, attempt } = pageGate("hold");
    const s = mountCard(onDismiss, attempt);

    s.left!();
    s.right!();

    expect(recordDiscoverInteraction).not.toHaveBeenCalled();
    expect(sendDiscoverInteraction).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();
    expect(state.invites).toBe(0);
  });

  it("guest tap still opens the card — taps never pass through the gate", () => {
    const gate = jest.fn(() => false);
    const s = mountCard(jest.fn(), gate);

    s.tap!({
      defaultPrevented: false,
      button: 0,
      metaKey: false,
      ctrlKey: false,
      shiftKey: false,
      altKey: false,
      target: { closest: () => null },
    } as unknown as React.MouseEvent);

    expect(routerPush).toHaveBeenCalledWith("/events/1");
    expect(gate).not.toHaveBeenCalled();
  });

  it("cancelled sign-in, then signed in: the refused swipe is never replayed", () => {
    const onDismiss = jest.fn();
    const gate = pageGate("invite");

    // Guest swipes, sees the invitation, cancels.
    mountCard(onDismiss, gate.attempt).left!();
    expect(gate.state.invites).toBe(1);
    expect(recordDiscoverInteraction).not.toHaveBeenCalled();

    // Browsing continues signed out: the next swipe is refused the same way.
    mountCard(onDismiss, gate.attempt).right!();
    expect(gate.state.invites).toBe(2);
    expect(recordDiscoverInteraction).not.toHaveBeenCalled();

    // Signs in. The page's gate reads the CURRENT state — nothing was queued.
    gate.state.current = "learn";
    expect(recordDiscoverInteraction).not.toHaveBeenCalled();
    expect(sendDiscoverInteraction).not.toHaveBeenCalled();

    // Their first signed-in swipe is the only thing recorded.
    mountCard(onDismiss, gate.attempt).right!();
    expect(recordDiscoverInteraction.mock.calls).toEqual([["nfl", "like"]]);
    expect(sendDiscoverInteraction).toHaveBeenCalledTimes(1);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("sign-out stops learning on the very next swipe, without a remount", () => {
    const onDismiss = jest.fn();
    const gate = pageGate("learn");
    const s = mountCard(onDismiss, gate.attempt);

    s.left!();
    expect(recordDiscoverInteraction).toHaveBeenCalledTimes(1);

    gate.state.current = "invite";
    s.left!();
    expect(recordDiscoverInteraction).toHaveBeenCalledTimes(1);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(gate.state.invites).toBe(1);
  });

  it("other surfaces that pass no gate keep today's behaviour", () => {
    const onDismiss = jest.fn();
    const s = mountCard(onDismiss);

    s.left!();

    expect(recordDiscoverInteraction.mock.calls).toEqual([["nfl", "unlike"]]);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

describe("the invitation", () => {
  const noop = async () => {};

  it("renders nothing while closed", () => {
    expect(
      renderToStaticMarkup(
        <SignInToPersonalizeInvite open={false} onClose={() => {}} onSignInGoogle={noop} onSignInApple={noop} />,
      ),
    ).toBe("");
  });

  it("open: a labelled dialog offering both existing providers and a way out", () => {
    const html = renderToStaticMarkup(
      <SignInToPersonalizeInvite open onClose={() => {}} onSignInGoogle={noop} onSignInApple={noop} />,
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-labelledby="discover-sign-in-invite-title"');
    expect(html).toContain("Sign in to personalize Discover");
    expect(html).toContain("Continue with Google");
    expect(html).toContain("Continue with Apple");
    expect(html).toContain("Not now");
  });

  it("the sheet sits above the phone's bottom nav, so 'Not now' can be tapped", () => {
    // At 390px the invitation is a bottom sheet and BottomNav is a fixed bar over
    // the same strip. Equal z-index let the nav (later in the DOM) cover the
    // sheet's last button — found in the browser, where "Not now" was untappable.
    const zOf = (cls: string) => {
      const m = cls.match(/(?:^|\s)z-(?:\[(\d+)\]|(\d+))(?=\s|$)/);
      if (!m) throw new Error(`no z-index class in: ${cls}`);
      return Number(m[1] ?? m[2]);
    };
    const html = renderToStaticMarkup(
      <SignInToPersonalizeInvite open onClose={() => {}} onSignInGoogle={noop} onSignInApple={noop} />,
    );
    const overlay = html.match(/<div class="([^"]*)"[^>]*data-testid="discover-sign-in-invite"/);
    expect(overlay).not.toBeNull();
    const nav = readFileSync(join(__dirname, "../../components/BottomNav.tsx"), "utf8")
      .match(/aria-label="Mobile navigation"|className="(md:hidden fixed bottom-0[^"]*)"/g)
      ?.map((s) => s.match(/className="([^"]*)"/)?.[1])
      .find(Boolean);
    expect(nav).toBeDefined();
    expect(zOf(overlay![1])).toBeGreaterThan(zOf(nav!));
  });

  it("the sheet sits above the first-visit privacy card, so Google and Apple can be tapped (#9767)", () => {
    // ConsentBanner is fixed near the bottom on a phone and is mounted after the
    // page in the layout, so an equal z-index let it cover the sheet's sign-in
    // buttons — measured on production at 390px: the taps hit the banner.
    const zOf = (cls: string) => {
      const m = cls.match(/(?:^|\s)z-(?:\[(\d+)\]|(\d+))(?=\s|$)/);
      if (!m) throw new Error(`no z-index class in: ${cls}`);
      return Number(m[1] ?? m[2]);
    };
    const html = renderToStaticMarkup(
      <SignInToPersonalizeInvite open onClose={() => {}} onSignInGoogle={noop} onSignInApple={noop} />,
    );
    const overlay = html.match(/<div class="([^"]*)"[^>]*data-testid="discover-sign-in-invite"/);
    expect(overlay).not.toBeNull();
    const banner = readFileSync(join(__dirname, "../../components/Analytics/ConsentBanner.tsx"), "utf8")
      .match(/className="(fixed bottom-[^"]*)"/)?.[1];
    expect(banner).toBeDefined();
    expect(zOf(overlay![1])).toBeGreaterThan(zOf(banner!));
  });

  it("a cancelled or failed sign-in is absorbed and still closes the invitation", async () => {
    const onSettled = jest.fn();
    await expect(
      runDiscoverInviteSignIn(() => Promise.reject(new Error("popup closed")), onSettled),
    ).resolves.toBeUndefined();
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it("a successful sign-in closes the invitation too", async () => {
    const onSettled = jest.fn();
    const signIn = jest.fn(() => Promise.resolve());
    await runDiscoverInviteSignIn(signIn, onSettled);
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledTimes(1);
  });
});

describe("the page wiring", () => {
  // Comments stripped so a quotation of the wiring cannot satisfy it.
  const page = readFileSync(join(__dirname, "../../app/discover/page.tsx"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  it("hands every Discover card the page's gate", () => {
    expect(page).toContain("onFeedbackAttempt={handleFeedbackAttempt}");
  });

  it("the page's own dismiss write refuses anything but `learn` before it writes", () => {
    const body = page.slice(page.indexOf("const handleDismiss = useCallback("));
    const guard = body.indexOf('if (learningStateRef.current !== "learn") return;');
    expect(guard).toBeGreaterThan(-1);
    expect(guard).toBeLessThan(body.indexOf("saveDismissed("));
    expect(guard).toBeLessThan(body.indexOf("sharedAnonEligibleRef.current = false"));
  });

  it("the gate reads auth state through the resolver, not `user` alone", () => {
    expect(page).toMatch(/resolveDiscoverLearning\(\{\s*isLoading: authLoading,\s*isAuthenticated,\s*uid: user\?\.uid\s*\}\)/);
  });
});
