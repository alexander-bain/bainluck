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
