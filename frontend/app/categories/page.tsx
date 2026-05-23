"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { fetchTagCounts } from "@/lib/api";
import { SPORT_CATEGORIES, getCategoryByKey } from "@/lib/sportCategories";
import Link from "next/link";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorState from "@/components/ErrorState";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

// Categories to display, grouped by tier
const DISPLAY_CATEGORIES = SPORT_CATEGORIES.filter(
  (c) => c.prefixes.length > 0 || ["politics", "entertainment", "economics", "tech", "weather", "geopolitics", "culture"].includes(c.key)
);

export default function CategoriesIndexPage() {
  usePageTracking({ pageType: "category_index", pageTitle: "Categories" });
  useScrollDepth({ pageType: "category_index" });
  useEngagementTime({ pageType: "category_index" });

  const { data, isLoading, error } = useSWR("tag-counts", fetchTagCounts, {
    refreshInterval: 60000,
  });

  const groups = useMemo(() => {
    const tier1 = DISPLAY_CATEGORIES.filter((c) => c.tier === 1);
    const tier2 = DISPLAY_CATEGORIES.filter((c) => c.tier === 2);
    const tier3 = DISPLAY_CATEGORIES.filter((c) => c.tier === 3);
    return [
      { label: "Major Sports", items: tier1 },
      { label: "More Sports & Topics", items: tier2 },
      { label: "Niche", items: tier3 },
    ].filter((g) => g.items.length > 0);
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-lg font-bold text-text-primary">Categories</h1>
        <p className="text-sm text-text-muted mt-1">
          Browse events and futures by sport or topic
        </p>
      </div>

      {isLoading && <SkeletonGrid count={12} />}

      {error && !isLoading && (
        <ErrorState message="Failed to load categories" onRetry={() => window.location.reload()} />
      )}

      {!isLoading &&
        groups.map((group) => (
          <section key={group.label}>
            <h2 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
              {group.label}
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {group.items.map((cat) => {
                const counts = data?.counts?.[cat.key];
                const eventCount = counts?.events ?? 0;
                const futuresCount = counts?.futures ?? 0;
                const total = eventCount + futuresCount;

                return (
                  <Link
                    key={cat.key}
                    href={`/categories/${cat.key}`}
                    className="flex flex-col gap-1 p-4 rounded-xl bg-surface-card border border-surface-border hover:border-text-muted transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{cat.emoji}</span>
                      <span className="text-sm font-semibold text-text-primary">
                        {cat.name}
                      </span>
                    </div>
                    {total > 0 && (
                      <p className="text-micro text-text-muted">
                        {eventCount > 0 && (
                          <>
                            {eventCount} event{eventCount !== 1 ? "s" : ""}
                          </>
                        )}
                        {eventCount > 0 && futuresCount > 0 && " · "}
                        {futuresCount > 0 && (
                          <>
                            {futuresCount} market
                            {futuresCount !== 1 ? "s" : ""}
                          </>
                        )}
                      </p>
                    )}
                    {total === 0 && (
                      <p className="text-micro text-text-muted">No items</p>
                    )}
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
    </div>
  );
}
