// One home for the brand one-liner, so the footer and the Discover first-run
// orientation line cannot drift apart (Queue 309 Item 1).
//
// Holds a real typographic apostrophe rather than an HTML entity: JSX escapes
// text children, so `&rsquo;` in a string literal would render literally.
export const BRAND_TAGLINE =
  "Probability, not betting. The world’s honest guess at what happens next.";

// #12028 / #12299 / #12813: one App Store identity for Safari's Smart App Banner
// (`apple-itunes-app`), ready to carry `app-clip-bundle-id` once the App Clip ships.
export const APP_STORE_APP_ID = "6759871755";
export const APP_CLIP_BUNDLE_ID =
  process.env.NEXT_PUBLIC_APP_CLIP_BUNDLE_ID?.trim() || null;
export const APP_STORE_URL =
  `https://apps.apple.com/us/app/bain-luck/id${APP_STORE_APP_ID}`;

export function buildAppleItunesMetaContent(
  appArgument?: string | null,
  appClipBundleId: string | null = APP_CLIP_BUNDLE_ID,
): string {
  const parts = [`app-id=${APP_STORE_APP_ID}`];
  if (appClipBundleId) {
    parts.push(`app-clip-bundle-id=${appClipBundleId}`);
  }
  if (appArgument) {
    parts.push(`app-argument=${appArgument}`);
  }
  return parts.join(", ");
}
