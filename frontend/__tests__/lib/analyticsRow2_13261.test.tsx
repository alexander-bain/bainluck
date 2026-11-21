export {};

type GtagCall = unknown[];

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function setup(consent: "none" | "all") {
  jest.resetModules();
  process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = "G-TEST13261";
  const calls: GtagCall[] = [];
  const gtag = (...args: unknown[]) => calls.push(args);
  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    navigator: { userAgent: "node" },
    location: {
      href: "https://www.bainluck.com/collections/machinery-fed-and-macro?utm_source=twitter&utm_medium=social&utm_campaign=fed_week",
      pathname: "/collections/machinery-fed-and-macro",
      search: "?utm_source=twitter&utm_medium=social&utm_campaign=fed_week",
    },
  };
  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
  };
  (global as unknown as { document: unknown }).document = {
    title: "Fed & Macro",
    referrer: "",
    visibilityState: "visible",
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  };
  const core = require("@/lib/analytics/core") as typeof import("@/lib/analytics/core");
  core.initializeAnalytics();
  core.updateConsent(consent);
  const { trackCollectionSharedLinkOpen } = require(
    "@/app/collections/[slug]/CollectionPageClient",
  ) as typeof import("@/app/collections/[slug]/CollectionPageClient");
  return {
    calls,
    trackCollectionSharedLinkOpen,
    sharedCalls: () =>
      calls.filter((c) => c[0] === "event" && c[1] === "shared_link_open"),
  };
}

afterAll(() => {
  if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  else process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_ENV;
});

describe("#13261 row 2: collection shared_link_open (181-C consent-gated) & Apple campaign links", () => {
  it("does NOT send shared_link_open without Allow consent (181-C)", () => {
    const h = setup("none");
    h.trackCollectionSharedLinkOpen(
      "machinery-fed-and-macro",
      "?utm_source=twitter&utm_medium=social&utm_campaign=fed_week",
    );
    expect(h.sharedCalls()).toHaveLength(0);
  });

  it("sends shared_link_open with content_type=collection when Allow consent is granted", () => {
    const h = setup("all");
    const fired = h.trackCollectionSharedLinkOpen(
      "machinery-fed-and-macro",
      "?utm_source=twitter&utm_medium=social&utm_campaign=fed_week",
    );
    expect(fired).toBe(true);
    expect(h.sharedCalls()).toHaveLength(1);
    expect(h.sharedCalls()[0][2]).toMatchObject({
      content_type: "collection",
      item_id: "machinery-fed-and-macro",
      source: "twitter",
      medium: "social",
      campaign: "fed_week",
    });
  });

  it("ignores plain collection visits with no share/UTM params", () => {
    const h = setup("all");
    expect(h.trackCollectionSharedLinkOpen("machinery-fed-and-macro", "")).toBe(false);
    expect(h.sharedCalls()).toHaveLength(0);
  });

  it("formats Apple campaign params (pt, ct, mt=8) on App Store URLs and Smart App Banner metadata", () => {
    const {
      APP_STORE_CAMPAIGNS,
      APP_STORE_URL,
      buildAppStoreUrl,
      buildAppleItunesMetaContent,
    } = require("@/lib/brandCopy") as typeof import("@/lib/brandCopy");

    expect(buildAppStoreUrl(APP_STORE_CAMPAIGNS.footerBadge, null)).toBe(APP_STORE_URL);
    expect(buildAppStoreUrl(APP_STORE_CAMPAIGNS.footerBadge, "")).toBe(APP_STORE_URL);
    expect(buildAppStoreUrl(APP_STORE_CAMPAIGNS.footerBadge, "12345678")).toBe(
      `${APP_STORE_URL}?pt=12345678&ct=web-footer-badge&mt=8`,
    );

    expect(
      buildAppleItunesMetaContent(
        "https://www.bainluck.com/collections/machinery-fed-and-macro",
        null,
        APP_STORE_CAMPAIGNS.bannerCollectionPage,
        null,
      ),
    ).toBe(
      "app-id=6759871755, app-argument=https://www.bainluck.com/collections/machinery-fed-and-macro",
    );
    expect(
      buildAppleItunesMetaContent(
        "https://www.bainluck.com/collections/machinery-fed-and-macro",
        null,
        APP_STORE_CAMPAIGNS.bannerCollectionPage,
        "12345678",
      ),
    ).toBe(
      "app-id=6759871755, affiliate-data=pt=12345678&ct=web-banner-collection-page, app-argument=https://www.bainluck.com/collections/machinery-fed-and-macro",
    );
  });
});
