/**
 * #12028 — Website links to the App Store app on phone visits, and universal
 * links open the app from both `bainluck.com` and `www.bainluck.com`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";

const mockTrack = jest.fn();

jest.mock("next/navigation", () => ({
  __esModule: true,
  usePathname: () => "/",
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: mockTrack }),
}));

import Footer from "@/components/Footer";
import { APP_STORE_CAMPAIGNS, APP_STORE_URL, appStoreCampaignUrl } from "@/lib/brandCopy";

const REPO_ROOT = path.join(__dirname, "..", "..", "..");
const FRONTEND_ROOT = path.join(__dirname, "..", "..");

/** An href as static markup writes it (a tagged #12311 URL carries `&`). */
const hrefAttr = (url: string) => `href="${url.replace(/&/g, "&amp;")}"`;

describe("#12028 — App Store links on the website and Universal Links for both hosts", () => {
  beforeEach(() => {
    mockTrack.mockReset();
  });

  test("APP_STORE_URL points to the public App Store listing", () => {
    expect(APP_STORE_URL).toBe("https://apps.apple.com/us/app/bain-luck/id6759871755");
  });

  test("Footer renders both the App Store badge and the phone-width 'Get the app' line", () => {
    const html = renderToStaticMarkup(<Footer />);

    // 1. Badge in the footer brand column
    const badgeMatch = html.match(
      /<a\b[^>]*data-testid="footer-app-store-badge"[^>]*>([^<]*)<\/a>/,
    );
    expect(badgeMatch).not.toBeNull();
    // #12311: the listing, with this badge's campaign tag once the provider token is in.
    expect(badgeMatch![0]).toContain(hrefAttr(appStoreCampaignUrl(APP_STORE_CAMPAIGNS.footerBadge)));
    expect(badgeMatch![1].trim()).toBe("Download on the App Store");

    // 2. "Get the app" line on phone widths (`md:hidden`)
    const phoneRowMatch = html.match(
      /<div\b[^>]*data-testid="footer-phone-get-the-app-row"[^>]*class="([^"]+)"/,
    );
    expect(phoneRowMatch).not.toBeNull();
    expect(phoneRowMatch![1].split(/\s+/)).toContain("md:hidden");

    const phoneLinkMatch = html.match(
      /<a\b[^>]*data-testid="footer-phone-get-the-app"[^>]*>([^<]*)<\/a>/,
    );
    expect(phoneLinkMatch).not.toBeNull();
    expect(phoneLinkMatch![0]).toContain(
      hrefAttr(appStoreCampaignUrl(APP_STORE_CAMPAIGNS.footerGetTheApp)),
    );
    expect(phoneLinkMatch![1].trim()).toBe("Get the app");
  });

  test("RootLayout uses Safari's banner and removes the custom top bar", () => {
    const layoutSource = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "layout.tsx"),
      "utf8",
    );

    expect(layoutSource).not.toContain('data-testid="phone-get-the-app-bar"');
    expect(layoutSource).not.toContain('data-testid="phone-get-the-app-link"');
    // Per-page context is supplied by the covered route's own metadata.
    // A root app-argument would be inherited by every other page, so the call
    // takes the campaign alone (#12311 moved the tag from `itunes` to `other`).
    expect(layoutSource).toContain(
      '"apple-itunes-app": smartAppBannerContent(APP_STORE_CAMPAIGNS.banner)',
    );
    expect(layoutSource).not.toMatch(/\bitunes:/);
  });

  test("both iOS and macOS entitlements claim applinks for bainluck.com and www.bainluck.com", () => {
    for (const rel of [
      "ios/Bain Luck/Bain Luck/Bain Luck.entitlements",
      "ios/Bain Luck/Bain Luck/Bain Luck-macOS.entitlements",
    ]) {
      const xml = fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
      const blockMatch = xml.match(
        /<key>com\.apple\.developer\.associated-domains<\/key>\s*<array>([\s\S]*?)<\/array>/,
      );
      expect(blockMatch).not.toBeNull();
      const domains = Array.from(
        blockMatch![1].matchAll(/<string>([^<]+)<\/string>/g),
        (m) => m[1],
      );
      expect(domains).toContain("applinks:bainluck.com");
      expect(domains).toContain("applinks:www.bainluck.com");
    }
  });

  test("apple-app-site-association is valid JSON and next.config.mjs serves it as application/json", async () => {
    const aasaRaw = fs.readFileSync(
      path.join(FRONTEND_ROOT, "public", ".well-known", "apple-app-site-association"),
      "utf8",
    );
    const aasa = JSON.parse(aasaRaw);
    const detail = aasa?.applinks?.details?.[0];
    expect(detail?.appID).toBe("J893F72P4R.com.bainluck.Bain-Luck");
    expect(detail?.paths).toEqual(
      expect.arrayContaining([
        "/events/*",
        "/futures/*",
        "/ei/hall-of-fame",
        "/search",
        "/search?*",
        "/my-stuff",
        "/preferences",
      ]),
    );

    const nextConfigSource = fs.readFileSync(
      path.join(FRONTEND_ROOT, "next.config.mjs"),
      "utf8",
    );
    expect(nextConfigSource).toMatch(
      /source:\s*"\/\.well-known\/apple-app-site-association"[\s\S]{0,200}?"Content-Type"[\s\S]{0,80}?"application\/json"/,
    );
  });
});
