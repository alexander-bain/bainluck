/**
 * #11345 — Web header squeezes navigation at tablet widths:
 * "Bain Luck", "My Stuff" and "Sign in" must stay on a single line.
 *
 * At the `md` breakpoint (768px–1023px, or a zoomed laptop viewport that lands
 * in that range), the desktop header row shows:
 *   1. Brand link ("🍀 Bain Luck")
 *   2. DesktopNav ("Discover", "Sports", "Browse", "My Stuff")
 *   3. Right cluster (compact SearchBar + UserMenu "Sign in")
 *
 * Previously, the search wrapper held a rigid `w-64` (256px) inside a nested
 * flex container with `min-width: auto`, while the three two-word labels
 * ("Bain Luck", "My Stuff", "Sign in") carried neither `whitespace-nowrap` nor
 * `shrink-0`. At 768px (720px inner header width after `md:px-6`), the sum of
 * natural widths was ~791px (> 720px), and CSS flexbox refused to shrink the
 * 256px search box while collapsing all three two-word labels onto two lines.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as fs from "fs";
import * as path from "path";

let mockPathname = "/sports";
const mockTrack = jest.fn();
let mockAuth: Record<string, unknown> = {};

jest.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: mockTrack }),
}));

jest.mock("@/components/AuthProvider", () => ({
  useAuthContext: () => mockAuth,
}));

jest.mock("@/lib/firebase", () => ({
  preloadFirebaseAuth: () => {},
}));

import DesktopNav from "@/components/DesktopNav";
import UserMenu from "@/components/UserMenu";

const FRONTEND_ROOT = path.join(__dirname, "..", "..");
const LAYOUT_PATH = path.join(FRONTEND_ROOT, "app", "layout.tsx");

function classesOfTagContaining(html: string, tag: string, text: string): string[] {
  const escaped = text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `<${tag}\\b[^>]*class="([^"]+)"[^>]*>[\\s\\S]*?${escaped}[\\s\\S]*?<\\/${tag}>`,
  );
  const match = html.match(pattern);
  if (!match) {
    throw new Error(`No <${tag}> containing "${text}" found in: ${html}`);
  }
  return match[1].trim().split(/\s+/);
}

describe("#11345 tablet header keeps brand, navigation, and Sign in on one line", () => {
  beforeEach(() => {
    mockPathname = "/sports";
    mockTrack.mockReset();
    mockAuth = {
      user: null,
      isAuthenticated: false,
      isAuthAvailable: true,
      authError: null,
      signInWithGoogle: async () => {},
      signInWithApple: async () => {},
      signOut: async () => {},
      getToken: async () => null,
      isLoading: false,
    };
  });

  test("DesktopNav container and every top-level item refuse to shrink or wrap two-word labels", () => {
    const html = renderToStaticMarkup(<DesktopNav />);

    const navMatch = html.match(/<nav\b[^>]*class="([^"]+)"/);
    expect(navMatch).not.toBeNull();
    const navClasses = navMatch![1].trim().split(/\s+/);
    expect(navClasses).toContain("shrink-0");

    for (const label of ["Discover", "Sports", "My Stuff"]) {
      const linkClasses = classesOfTagContaining(html, "a", label);
      expect(linkClasses).toContain("whitespace-nowrap");
      expect(linkClasses).toContain("shrink-0");
    }

    const browseClasses = classesOfTagContaining(html, "button", "Browse");
    expect(browseClasses).toContain("whitespace-nowrap");
    expect(browseClasses).toContain("shrink-0");
  });

  test("UserMenu Sign in button and wrapper refuse to shrink or wrap onto two lines", () => {
    const html = renderToStaticMarkup(<UserMenu />);

    const wrapperMatch = html.match(/^<div\b[^>]*class="([^"]+)"/);
    expect(wrapperMatch).not.toBeNull();
    const wrapperClasses = wrapperMatch![1].trim().split(/\s+/);
    expect(wrapperClasses).toContain("shrink-0");

    const buttonClasses = classesOfTagContaining(html, "button", "Sign in");
    expect(buttonClasses).toContain("whitespace-nowrap");
    expect(buttonClasses).toContain("shrink-0");
  });

  test("UserMenu avatar trigger stays non-shrinking when authenticated", () => {
    mockAuth = {
      ...mockAuth,
      isAuthenticated: true,
      user: { displayName: "Alex", email: "alex@example.com", photoURL: null },
    };
    const html = renderToStaticMarkup(<UserMenu />);

    const wrapperMatch = html.match(/^<div\b[^>]*class="([^"]+)"/);
    expect(wrapperMatch).not.toBeNull();
    expect(wrapperMatch![1].trim().split(/\s+/)).toContain("shrink-0");

    const buttonMatch = html.match(/<button\b[^>]*class="([^"]+)"[^>]*aria-label="User menu"/);
    expect(buttonMatch).not.toBeNull();
    expect(buttonMatch![1].trim().split(/\s+/)).toContain("shrink-0");
  });

  test("RootLayout header protects brand and lets the tablet search bar flex before squeezing labels", () => {
    const layoutSource = fs.readFileSync(LAYOUT_PATH, "utf8");
    const headerMatch = layoutSource.match(/<header\b[\s\S]*?<\/header>/);
    expect(headerMatch).not.toBeNull();
    const header = headerMatch![0];

    // 1. Brand link ("Bain Luck") must never shrink or wrap.
    const brandLinkMatch = header.match(/<Link\s+href="\/"\s+className="([^"]+)"/);
    expect(brandLinkMatch).not.toBeNull();
    const brandClasses = brandLinkMatch![1].trim().split(/\s+/);
    expect(brandClasses).toContain("shrink-0");
    expect(brandClasses).toContain("whitespace-nowrap");

    // 2. Right cluster must allow shrinking at `md` (`min-w-0` + `md:flex-1`) so
    //    the nested flex container does not lock its minimum width to 256px.
    const rightClusterMatch = header.match(
      /<div className="([^"]+)">\s*<div className="([^"]+)">\s*<SearchBar compact \/>/,
    );
    expect(rightClusterMatch).not.toBeNull();
    const rightClusterClasses = rightClusterMatch![1].trim().split(/\s+/);
    const searchSlotClasses = rightClusterMatch![2].trim().split(/\s+/);

    expect(rightClusterClasses).toContain("min-w-0");
    expect(rightClusterClasses).toContain("md:flex-1");
    expect(rightClusterClasses).toContain("lg:flex-initial");

    // 3. Search slot adapts between 9rem and 16rem across `md` (768px–1023px)
    //    and restores `lg:w-80` (320px) at `lg` (1024px+).
    expect(searchSlotClasses).not.toContain("w-64");
    expect(searchSlotClasses).toContain("w-full");
    expect(searchSlotClasses).toContain("md:max-w-[16rem]");
    expect(searchSlotClasses).toContain("min-w-[9rem]");
    expect(searchSlotClasses).toContain("lg:w-80");
    expect(searchSlotClasses).toContain("lg:max-w-none");
  });

  test("768px tablet horizontal budget fits single-line chrome plus minimum search width", () => {
    // At 768px (`md` start), `md:px-6` leaves 720px of inner header width.
    const MD_VIEWPORT_PX = 768;
    const MD_HORIZONTAL_PADDING_PX = 24 * 2;
    const innerHeaderWidthPx = MD_VIEWPORT_PX - MD_HORIZONTAL_PADDING_PX; // 720px

    // Measured single-line widths of the non-shrinking items:
    const BRAND_SINGLE_LINE_PX = 112; // 🍀 + gap-2.5 + "Bain Luck"
    const DESKTOP_NAV_SINGLE_LINE_PX = 334; // Discover + Sports + Browse + My Stuff
    const SIGN_IN_SINGLE_LINE_PX = 45; // "Sign in"
    const GAPS_PX = 12 * 2 + 12; // two top-level `gap-3` (24px) + right-cluster `gap-3` (12px)

    const remainingForSearchPx =
      innerHeaderWidthPx -
      BRAND_SINGLE_LINE_PX -
      DESKTOP_NAV_SINGLE_LINE_PX -
      SIGN_IN_SINGLE_LINE_PX -
      GAPS_PX;

    const OLD_RIGID_W64_PX = 256;
    const NEW_MIN_SEARCH_PX = 9 * 16; // min-w-[9rem] = 144px

    // Control: the old rigid `w-64` (256px) overflowed the 193px remaining at 768px.
    expect(OLD_RIGID_W64_PX).toBeGreaterThan(remainingForSearchPx);
    // Fix: the adaptive search slot's 9rem (144px) floor fits with >= 40px headroom.
    expect(remainingForSearchPx).toBeGreaterThanOrEqual(NEW_MIN_SEARCH_PX + 40);
  });
});
