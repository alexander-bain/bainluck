import type { MetadataRoute } from "next";

const BASE = "https://bainluck.com";

/**
 * robots.txt — pairs with app/sitemap.ts (L2-144 Item 2). Public marketing +
 * category surfaces are indexable; admin, API-proxy, and share-redirect paths
 * are disallowed (they are operational/ephemeral, not content). Points crawlers
 * at the sitemap so /about and the category hubs get discovered.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/admin", "/api/", "/share/"],
      },
    ],
    sitemap: `${BASE}/sitemap.xml`,
    host: BASE,
  };
}
