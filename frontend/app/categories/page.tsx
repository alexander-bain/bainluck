"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { fetchTagCounts } from "@/lib/api";
import { buildTiles } from "@/lib/categoryTiles";
import Link from "next/link";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorState from "@/components/ErrorState";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

export default function CategoriesIndexPage() {
  usePageTracking({ pageType: "category_index", pageTitle: "Categories" });
  useScrollDepth({ pageType: "category_index" });
  useEngagementTime({ pageType: "category_index" });

  const { data, isLoading, error } = useSWR("tag-counts", fetchTagCounts, {
    refreshInterval: 60000,
  });

  const tiles = useMemo(() => buildTiles(data?.counts), [data?.counts]);

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

      {!isLoading && !error && tiles.length === 0 && (
        <p className="text-sm text-text-muted">No categories available right now.</p>
      )}

      {!isLoading && tiles.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {tiles.map((cat) => (
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
              <p className="text-micro text-text-muted">
                {cat.events > 0 && (
                  <>
                    {cat.events} event{cat.events !== 1 ? "s" : ""}
                  </>
                )}
                {cat.events > 0 && cat.futures > 0 && " · "}
                {cat.futures > 0 && (
                  <>
                    {cat.futures} market
                    {cat.futures !== 1 ? "s" : ""}
                  </>
                )}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
