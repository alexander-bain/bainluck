/**
 * #12311 — the website's ways into the App Store carry campaign tags, so App
 * Store Connect's analytics can say which one brought an install: Safari's
 * banner (on an event's page, where shared links land, and on every other page)
 * and the footer's badge and "Get the app" line.
 *
 * Apple counts a campaign token (`ct`) only beside the account's provider token
 * (`pt`), which comes from App Store Connect and can't be made up. Until it is
 * filled in nothing a reader gets changes, so these tests pin both states: the
 * helpers with and without a token, and the pages wired with one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";

type BrandCopy = typeof import("@/lib/brandCopy");

// The footer and the event layout get the real helpers with a provider token
// filled in, as they will once the number from App Store Connect is committed.
jest.mock("@/lib/brandCopy", () => {
  const actual = jest.requireActual<BrandCopy>("@/lib/brandCopy");
  return {
    ...actual,
    appStoreCampaignUrl: (
      campaign: Parameters<BrandCopy["appStoreCampaignUrl"]>[0],
      providerToken: string | null = "123456",
    ) => actual.appStoreCampaignUrl(campaign, providerToken),
    smartAppBannerContent: (
      campaign: Parameters<BrandCopy["smartAppBannerContent"]>[0],
      appArgument?: string,
      providerToken: string | null = "123456",
    ) => actual.smartAppBannerContent(campaign, appArgument, providerToken),
  };
});

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/",
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: jest.fn() }),
}));

import Footer from "@/components/Footer";
import { generateMetadata } from "@/app/events/[id]/layout";

const real = jest.requireActual<BrandCopy>("@/lib/brandCopy");
const { APP_STORE_CAMPAIGNS: CAMPAIGNS } = real;

/** The token the mock fills in; any digits would do. */
const TOKEN = "123456";
const LISTING = "https://apps.apple.com/us/app/bain-luck/id6759871755";
const EVENT_URL = "https://www.bainluck.com/events/1";

const FRONTEND_ROOT = path.join(__dirname, "..", "..");

afterEach(() => {
  jest.restoreAllMocks();
});

describe("#12311 — the links and the banner, without and with the provider token", () => {
  test("with no provider token, every link is the plain listing and the banner is what `itunes` printed", () => {
    for (const campaign of Object.values(CAMPAIGNS)) {
      expect(real.appStoreCampaignUrl(campaign, null)).toBe(LISTING);
    }
    expect(real.smartAppBannerContent(CAMPAIGNS.banner, undefined, null)).toBe("app-id=6759871755");
    expect(real.smartAppBannerContent(CAMPAIGNS.bannerEventPage, EVENT_URL, null)).toBe(
      `app-id=6759871755, app-argument=${EVENT_URL}`,
    );
  });

  test("with the provider token, a link carries it, its own campaign and Apple's mt=8", () => {
    expect(real.appStoreCampaignUrl(CAMPAIGNS.footerBadge, TOKEN)).toBe(
      `${LISTING}?pt=123456&ct=web-footer-badge&mt=8`,
    );
    expect(real.appStoreCampaignUrl(CAMPAIGNS.footerGetTheApp, TOKEN)).toBe(
      `${LISTING}?pt=123456&ct=web-footer-get-the-app&mt=8`,
    );
  });

  test("the banner carries the same two tokens in affiliate-data, between app-id and app-argument", () => {
    expect(real.smartAppBannerContent(CAMPAIGNS.banner, undefined, TOKEN)).toBe(
      "app-id=6759871755, affiliate-data=pt=123456&ct=web-banner",
    );
    expect(real.smartAppBannerContent(CAMPAIGNS.bannerEventPage, EVENT_URL, TOKEN)).toBe(
      `app-id=6759871755, affiliate-data=pt=123456&ct=web-banner-event-page, app-argument=${EVENT_URL}`,
    );
  });

  test("a provider token that isn't digits tags nothing", () => {
    for (const bad of ["", " 123456", "12 34", "pt=123456", "abc"]) {
      expect(real.appStoreCampaignUrl(CAMPAIGNS.footerBadge, bad)).toBe(LISTING);
      expect(real.smartAppBannerContent(CAMPAIGNS.banner, undefined, bad)).toBe("app-id=6759871755");
    }
  });

  test("the committed provider token is empty or Apple's digits", () => {
    const token = real.APP_STORE_PROVIDER_TOKEN;
    expect(token === null || /^\d+$/.test(token)).toBe(true);
  });

  test("each way in has its own campaign token, short enough for App Store Connect and safe in a URL and the banner's list", () => {
    const tokens = Object.values(CAMPAIGNS);
    expect(new Set(tokens).size).toBe(tokens.length);
    for (const token of tokens) {
      // Apple allows 30 characters; commas, ampersands and spaces would split
      // the banner's comma list or the query string, so these stay plainer.
      expect(token).toMatch(/^[a-z0-9-]{1,30}$/);
    }
  });
});

describe("#12311 — each way in on the site uses its own campaign", () => {
  test("the footer's badge and its 'Get the app' line are tagged apart", () => {
    const html = renderToStaticMarkup(<Footer />);
    const href = (testId: string) =>
      html
        .match(new RegExp(`<a\\b[^>]*data-testid="${testId}"[^>]*>`))?.[0]
        .match(/href="([^"]+)"/)?.[1]
        .replace(/&amp;/g, "&");

    expect(href("footer-app-store-badge")).toBe(real.appStoreCampaignUrl(CAMPAIGNS.footerBadge, TOKEN));
    expect(href("footer-phone-get-the-app")).toBe(
      real.appStoreCampaignUrl(CAMPAIGNS.footerGetTheApp, TOKEN),
    );
  });

  test("an event's page banner names its own campaign and opens the event's URL", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 1,
        home_team: "Celtics",
        away_team: "76ers",
        home_score: null,
        away_score: null,
        status: "scheduled",
        // An offset, not a date: "scheduled" is a relation to the clock (gotcha #44).
        commence_time: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
        hero_probability: 0.65,
        hero_probability_source: "blend",
        current_odds: { home_probability: 0.65, away_probability: 0.35 },
      }),
    }) as unknown as typeof fetch;

    const meta = await generateMetadata({ params: Promise.resolve({ id: "1" }) });

    expect(meta.alternates?.canonical).toBe(EVENT_URL);
    expect(meta.other?.["apple-itunes-app"]).toBe(
      real.smartAppBannerContent(CAMPAIGNS.bannerEventPage, EVENT_URL, TOKEN),
    );
  });

  test("the root layout's banner is the every-page campaign", () => {
    const source = fs.readFileSync(path.join(FRONTEND_ROOT, "app", "layout.tsx"), "utf8");
    expect(source).toContain('"apple-itunes-app": smartAppBannerContent(APP_STORE_CAMPAIGNS.banner)');
  });

  test("no page or component links to the App Store, or prints a banner, around the helpers", () => {
    // A new "Get the app" link written with the bare listing URL would send
    // installs ASC can't place; an `itunes:` field would print a second,
    // untagged banner tag beside the one written through `other`.
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== "node_modules" && !entry.name.startsWith(".")) walk(full);
        } else if (/\.(ts|tsx)$/.test(entry.name) && full !== path.join(FRONTEND_ROOT, "lib", "brandCopy.ts")) {
          const text = fs.readFileSync(full, "utf8");
          if (/APP_STORE_URL|apps\.apple\.com\/|\bitunes:\s*\{/.test(text)) {
            offenders.push(path.relative(FRONTEND_ROOT, full));
          }
        }
      }
    };
    for (const dir of ["app", "components", "lib"]) walk(path.join(FRONTEND_ROOT, dir));

    expect(offenders).toEqual([]);
  });
});
