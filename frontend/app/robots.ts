import type { MetadataRoute } from "next";

import { CRAWLER_DISALLOWED_PREFIXES } from "@/lib/crawlPolicy";
import { getSiteUrl } from "@/lib/siteUrl";

// LAT-P278: `www`, not the apex — the apex 301s, and a sitemap that lists the
// redirecting host hands search two identities for one page.
const BASE = getSiteUrl();

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
        // #4193: the same list the self-canonical guard exempts, so "not
        // crawled" and "not required to self-canonicalise" cannot drift apart.
        disallow: [...CRAWLER_DISALLOWED_PREFIXES],
      },
    ],
    sitemap: `${BASE}/sitemap.xml`,
    host: BASE,
  };
}
