// One home for the brand one-liner, so the footer and the Discover first-run
// orientation line cannot drift apart (Queue 309 Item 1).
//
// Holds a real typographic apostrophe rather than an HTML entity: JSX escapes
// text children, so `&rsquo;` in a string literal would render literally.
export const BRAND_TAGLINE =
  "Probability, not betting. The world’s honest guess at what happens next.";

// #12028 / #12299: one App Store identity for the badge and Safari banner.
export const APP_STORE_APP_ID = "6759871755";
export const APP_STORE_URL =
  `https://apps.apple.com/us/app/bain-luck/id${APP_STORE_APP_ID}`;

// #12311: campaign tags, so App Store Connect's analytics can say which way into
// the App Store brought an install. The provider token (`pt`) is the number in
// any campaign link made under Analytics → Acquisition → Campaigns in App Store
// Connect. It names the developer account and is the same for every campaign,
// and Apple says it can't be made up. Until it is filled in, the links and the
// banner stay exactly as they were: Apple counts no campaign token without it.
export const APP_STORE_PROVIDER_TOKEN: string | null = null;

/** One campaign token per way in, as App Store Connect will list them. */
export const APP_STORE_CAMPAIGNS = {
  /** Safari's banner on every page but an event's own. */
  banner: "web-banner",
  /** Safari's banner on an event's page, where shared links land. */
  bannerEventPage: "web-banner-event-page",
  /** The footer's "Download on the App Store" badge. */
  footerBadge: "web-footer-badge",
  /** The footer's "Get the app" line on phone widths. */
  footerGetTheApp: "web-footer-get-the-app",
} as const;

export type AppStoreCampaign = (typeof APP_STORE_CAMPAIGNS)[keyof typeof APP_STORE_CAMPAIGNS];

/** Apple's provider tokens are digits; anything else would tag nothing. */
function usableProviderToken(token: string | null): string | null {
  return token !== null && /^\d+$/.test(token) ? token : null;
}

/** The App Store listing, tagged with `campaign` once the provider token is in. */
export function appStoreCampaignUrl(
  campaign: AppStoreCampaign,
  providerToken: string | null = APP_STORE_PROVIDER_TOKEN,
): string {
  const pt = usableProviderToken(providerToken);
  if (pt === null) return APP_STORE_URL;
  return `${APP_STORE_URL}?${new URLSearchParams({ pt, ct: campaign, mt: "8" })}`;
}

/**
 * The `apple-itunes-app` meta content for Safari's banner. Next's `itunes`
 * metadata has no slot for `affiliate-data`, where the banner carries the same
 * two tokens, so the layouts write the tag through `other`. With no provider
 * token this is the string `itunes: { appId, appArgument }` rendered.
 */
export function smartAppBannerContent(
  campaign: AppStoreCampaign,
  appArgument?: string,
  providerToken: string | null = APP_STORE_PROVIDER_TOKEN,
): string {
  const pt = usableProviderToken(providerToken);
  let content = `app-id=${APP_STORE_APP_ID}`;
  if (pt !== null) content += `, affiliate-data=pt=${pt}&ct=${campaign}`;
  if (appArgument) content += `, app-argument=${appArgument}`;
  return content;
}
