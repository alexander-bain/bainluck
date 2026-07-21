import type { MetadataRoute } from "next";

const BASE = "https://bainluck.com";

/**
 * Static sitemap of the durable, public marketing + category surfaces. Dynamic
 * per-event / per-market URLs are intentionally excluded (they churn and are
 * discovered via internal links + OG); this covers the stable entry points so
 * /about and the category hubs are indexable.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const routes: { path: string; priority: number; changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"] }[] = [
    { path: "/", priority: 1.0, changeFrequency: "hourly" },
    { path: "/discover", priority: 0.9, changeFrequency: "hourly" },
    { path: "/sports", priority: 0.8, changeFrequency: "hourly" },
    { path: "/about", priority: 0.7, changeFrequency: "monthly" },
    { path: "/calibration", priority: 0.7, changeFrequency: "daily" },
    { path: "/politics", priority: 0.6, changeFrequency: "daily" },
    { path: "/economics", priority: 0.6, changeFrequency: "daily" },
    { path: "/entertainment", priority: 0.6, changeFrequency: "daily" },
    { path: "/weather", priority: 0.6, changeFrequency: "daily" },
    { path: "/privacy", priority: 0.3, changeFrequency: "yearly" },
  ];

  const lastModified = new Date();

  return routes.map((r) => ({
    url: `${BASE}${r.path}`,
    lastModified,
    changeFrequency: r.changeFrequency,
    priority: r.priority,
  }));
}
