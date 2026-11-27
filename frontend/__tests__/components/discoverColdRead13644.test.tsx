/**
 * #13644 — Cold-read fixes on Discover cards, /about TMDB notice, and grouped card `✕`.
 *
 * 1. "Your sport" (`sport_boost`) and "Following" (`discover_interest`) no longer draw cues.
 * 2. TMDB notice + logo stay on `/about` (`AboutPage189`) and `/picture-credits`, not on cards.
 * 3. Grouped cards (`RoundupCard`, `ThemeBundleCard`, `DeadlineFamilyCard`, `GroupCard`,
 *    `BundleActionBar`) draw an `✕` beside the heart that records `"dismiss"` against the set
 *    (`content_type: "bundle"`, `item_id: resolvedSetId`) under the #9643 feedback gate.
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem } from "@/lib/types";

const trackEvent = jest.fn();

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/picture-credits",
  useSearchParams: () => new URLSearchParams(),
}));
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ pageView: jest.fn(), track: jest.fn() }),
}));
jest.mock("@/lib/analytics", () => ({
  ...jest.requireActual("@/lib/analytics"),
  trackEvent: (...args: unknown[]) => trackEvent(...args),
}));

let capturedBarProps: { onDismiss?: () => void; setLiked?: (v: boolean) => void } = {};
jest.mock("@/components/discover/shared", () => {
  const actual = jest.requireActual("@/components/discover/shared");
  return {
    ...actual,
    ActionBar: (props: { onDismiss?: () => void; setLiked: (v: boolean) => void } & Record<string, unknown>) => {
      capturedBarProps = { onDismiss: props.onDismiss, setLiked: props.setLiked };
      return React.createElement(actual.ActionBar, props);
    },
  };
});

import * as di from "@/lib/discoverInteractions";
import { forYouCue } from "@/lib/discover/forYouCue";
import { BundleActionBar } from "@/components/discover/BundleActionBar";
import { GroupCard } from "@/components/discover/GroupCard";
import { ThemeBundleCard } from "@/components/discover/ThemeBundleCard";
import { RoundupCard } from "@/components/discover/roundup/RoundupCard";
import DiscoverCard from "@/components/DiscoverCard";
import AboutPage189 from "@/components/story/AboutPage189";
import PictureCreditsPage from "@/app/picture-credits/page";
import {
  DiscoverFeedbackAttemptContext,
  decideDiscoverFeedbackAttempt,
} from "@/lib/discoverFeedbackGate";

describe("#13644 — Discover cold-read cleanup", () => {
  const bundleMember = {
    type: "futures",
    score: 85,
    data: {
      id: 901,
      name: "Who will play James Bond next?",
      llm_sport_category: "entertainment",
      top_outcomes: [{ name: "Raye", probability: 0.42 }],
    },
  } as unknown as FeedItem;

  beforeEach(() => {
    trackEvent.mockClear();
    capturedBarProps = {};
    const g = global as unknown as Record<string, unknown>;
    g.window = {
      location: { href: "http://localhost/discover", pathname: "/discover" },
      addEventListener: () => {},
      dispatchEvent: () => true,
    };
    const store: Record<string, string> = {};
    g.localStorage = {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
      removeItem: (k: string) => {
        delete store[k];
      },
    };
    g.CustomEvent = class {
      type: string;
      constructor(type: string) {
        this.type = type;
      }
    };
    di.setDiscoverLearningGate(() => true);
    di.dropPendingDiscoverInteractions();
  });

  afterEach(() => {
    di.setDiscoverLearningGate(null);
    di.dropPendingDiscoverInteractions();
    const g = global as unknown as Record<string, unknown>;
    delete g.window;
    delete g.localStorage;
  });

  it("drops 'Your sport' (`sport_boost`) and 'Following' (`discover_interest`) cues while keeping specific cues", () => {
    expect(
      forYouCue({ personalized: true, multiplier: 1.3, personalization_reasons: ["sport_boost:0.20"] }),
    ).toBeNull();
    expect(
      forYouCue({ personalized: true, multiplier: 1.3, personalization_reasons: ["discover_interest:0.22"] }),
    ).toBeNull();
    expect(
      forYouCue({ personalized: true, multiplier: 1.35, personalization_reasons: ["your_team:0.35"] })?.mark,
    ).toBe("Your team");
  });

  it("places TMDB notice + logo on /about and /picture-credits, and keeps them off /entertainment footer", () => {
    const aboutHtml = renderToStaticMarkup(<AboutPage189 />);
    expect(aboutHtml).toContain('data-testid="tmdb-attribution-block"');
    expect(aboutHtml).toContain("/tmdb-blue-short.svg");
    expect(aboutHtml).toContain("This product uses the TMDB API but is not endorsed or certified by TMDB.");

    const creditsHtml = renderToStaticMarkup(<PictureCreditsPage />);
    expect(creditsHtml).toContain('data-testid="tmdb-attribution-block"');
    expect(creditsHtml).toContain("/tmdb-blue-short.svg");

    const entertainmentSrc = readFileSync(
      join(__dirname, "..", "..", "app", "entertainment", "page.tsx"),
      "utf8",
    );
    expect(entertainmentSrc).not.toContain("tmdb-blue-short.svg");
    expect(entertainmentSrc).not.toContain("endorsed or certified by TMDB");
  });

  it("draws `✕` beside heart on ThemeBundleCard, GroupCard, and RoundupCard without disturbing single-card ActionBar", () => {
    const themeHtml = renderToStaticMarkup(
      <ThemeBundleCard
        items={[bundleMember]}
        title="Entertainment"
        sharedQuestion="Next Bond"
        storyKey="bond-story"
        bundleId="machinery-next-james-bond"
      />,
    );
    expect(themeHtml).toMatch(/Like<\/button><button[^>]*data-testid="action-bar-dismiss"[^>]*aria-label="Not for me"/);

    const groupHtml = renderToStaticMarkup(
      <GroupCard items={[bundleMember]} title="Bond" sharedQuestion="Next Bond" setId="group:Bond" />,
    );
    expect(groupHtml).toContain('data-testid="action-bar-dismiss"');

    const roundupNow = Date.parse("2025-06-15T12:00:00Z");
    const roundupHtml = renderToStaticMarkup(
      <RoundupCard
        title="Next Bond"
        items={[bundleMember]}
        bundleId="roundup:machinery-next-james-bond"
        nowMs={roundupNow}
        collectionRef={{
          slug: "machinery-next-james-bond",
          name: "Next James Bond",
          revision: 1,
          collection_count: 5,
        }}
        contract={{
          kicker: "CULTURE",
          tag: "Bond",
          subtitle: "",
          footer: "Updated hourly",
          rows: [
            {
              market_id: 901,
              label: "Raye",
              probability: 0.42,
              rendered_percent: 42,
              observed_at: "2025-06-15T11:30:00Z",
            },
            {
              market_id: 902,
              label: "Olivia Dean",
              probability: 0.28,
              rendered_percent: 28,
              observed_at: "2025-06-15T11:30:00Z",
            },
            {
              market_id: 903,
              label: "Dua Lipa",
              probability: 0.14,
              rendered_percent: 14,
              observed_at: "2025-06-15T11:30:00Z",
            },
          ],
        } as never}
      />,
    );
    expect(roundupHtml).toContain('data-testid="action-bar-dismiss"');

    // Single cards retain top-right DismissBtn rather than an ActionBar dismiss button
    const singleFuturesHtml = renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{ type: "single", item: bundleMember }}
        onDismiss={() => {}}
      />,
    );
    expect(singleFuturesHtml).not.toContain('data-testid="action-bar-dismiss"');
    expect(singleFuturesHtml).toContain('aria-label="Less like this"');
  });

  it("records 'not for me' (`action: 'dismiss'`) against `item_type: 'bundle'` and `setId`, gated by #9643", () => {
    const onDismiss = jest.fn();
    renderToStaticMarkup(
      <BundleActionBar
        items={[bundleMember]}
        title="Next James Bond"
        sharedQuestion="Who will play James Bond next?"
        storyKey="story-bond"
        setId="machinery-next-james-bond"
        positionIndex={3}
        onDismiss={onDismiss}
      />,
    );
    expect(capturedBarProps.onDismiss).toBeDefined();
    capturedBarProps.onDismiss!();

    expect(onDismiss).toHaveBeenCalledTimes(1);
    const queued = di.peekPendingDiscoverInteractions();
    expect(queued).toHaveLength(1);
    expect(queued[0]).toMatchObject({
      action: "dismiss",
      item_type: "bundle",
      item_id: "machinery-next-james-bond",
      item_name: "Who will play James Bond next?",
      source: "bundle",
    });

    // Guest reader (#9643) is invited instead of writing a bundle dismissal
    di.dropPendingDiscoverInteractions();
    di.setDiscoverLearningGate(() => false);
    let invites = 0;
    const guestAttempt = () => {
      const decision = decideDiscoverFeedbackAttempt("invite");
      if (decision.invite) invites += 1;
      return decision.proceed;
    };
    const guestDismiss = jest.fn();
    renderToStaticMarkup(
      <DiscoverFeedbackAttemptContext.Provider value={guestAttempt}>
        <BundleActionBar
          items={[bundleMember]}
          title="Next James Bond"
          setId="machinery-next-james-bond"
          onDismiss={guestDismiss}
        />
      </DiscoverFeedbackAttemptContext.Provider>,
    );
    capturedBarProps.onDismiss!();
    expect(invites).toBe(1);
    expect(guestDismiss).not.toHaveBeenCalled();
    expect(di.peekPendingDiscoverInteractions()).toEqual([]);
  });
});
