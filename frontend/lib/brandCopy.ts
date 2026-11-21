// One home for the brand one-liner, so the footer and the Discover first-run
// orientation line cannot drift apart (Queue 309 Item 1).
//
// Holds a real typographic apostrophe rather than an HTML entity: JSX escapes
// text children, so `&rsquo;` in a string literal would render literally.
export const BRAND_TAGLINE =
  "Probability, not betting. The world’s honest guess at what happens next.";

// #12028 / #12299 / #12813 / #12311 / #13261: one App Store identity for
// Safari's Smart App Banner (`apple-itunes-app`) and App Store links, ready
// to carry Apple campaign tags (`pt`, `ct`, `mt=8`) once `NEXT_PUBLIC_APP_STORE_PROVIDER_TOKEN`
// is set from App Store Connect.
export const APP_STORE_APP_ID = "6759871755";
export const APP_CLIP_BUNDLE_ID =
  process.env.NEXT_PUBLIC_APP_CLIP_BUNDLE_ID?.trim() || null;
export const APP_STORE_PROVIDER_TOKEN =
  process.env.NEXT_PUBLIC_APP_STORE_PROVIDER_TOKEN?.trim() || null;
export const APP_STORE_URL =
  `https://apps.apple.com/us/app/bain-luck/id${APP_STORE_APP_ID}`;

export const APP_STORE_CAMPAIGNS = {
  bannerDefault: "web-banner",
  bannerEventPage: "web-banner-event-page",
  bannerFuturesPage: "web-banner-futures-page",
  bannerCollectionPage: "web-banner-collection-page",
  footerBadge: "web-footer-badge",
  footerGetTheApp: "web-footer-get-the-app",
  collectionCta: "web-collection-cta",
} as const;

export function buildAppStoreUrl(
  campaign?: string | null,
  providerToken: string | null = APP_STORE_PROVIDER_TOKEN,
): string {
  const pt = providerToken?.trim();
  const ct = campaign?.trim();
  if (!pt || !ct) {
    return APP_STORE_URL;
  }
  return `${APP_STORE_URL}?pt=${encodeURIComponent(pt)}&ct=${encodeURIComponent(ct)}&mt=8`;
}

export function buildAppleItunesMetaContent(
  appArgument?: string | null,
  appClipBundleId: string | null = APP_CLIP_BUNDLE_ID,
  campaign?: string | null,
  providerToken: string | null = APP_STORE_PROVIDER_TOKEN,
): string {
  const parts = [`app-id=${APP_STORE_APP_ID}`];
  if (appClipBundleId) {
    parts.push(`app-clip-bundle-id=${appClipBundleId}`);
  }
  const pt = providerToken?.trim();
  const ct = campaign?.trim();
  if (pt && ct) {
    parts.push(`affiliate-data=pt=${encodeURIComponent(pt)}&ct=${encodeURIComponent(ct)}`);
  }
  if (appArgument) {
    parts.push(`app-argument=${appArgument}`);
  }
  return parts.join(", ");
}
