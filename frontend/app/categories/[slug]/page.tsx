"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import { getCategoryByKey, SPORT_CATEGORIES } from "@/lib/sportCategories";
import { groupFeedIntoSections } from "@/lib/feedSections";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import FeedCard from "@/components/FeedCard";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import Link from "next/link";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

// Map category slugs to sport tag values
function slugToTag(slug: string): string {
  return `sport:${slug}`;
}

export default function CategoryPage({
  params,
}: {
  params: { slug: string };
}) {
  const slug = params.slug;
  const category = getCategoryByKey(slug);
  const categoryName = category?.name ?? slug.charAt(0).toUpperCase() + slug.slice(1).replace(/_/g, " ");
  const categoryEmoji = category?.emoji ?? "\uD83C\uDFC6";

  usePageTracking({ pageType: "category", pageTitle: `${categoryName} - Bain Luck` });
  useScrollDepth({ pageType: "category" });
  useEngagementTime({ pageType: "category" });

  const { user, isLoading: authLoading } = useAuthContext();

  const tags = useMemo(() => [slugToTag(slug)], [slug]);

  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    authLoading
      ? null
      : user
        ? ["feed-category", slug, user.uid]
        : ["feed-category-anon", slug],
    () => fetchFeed({ limit: 200, tags }),
    { refreshInterval: 30000 }
  );

  const feedSections = useMemo(() => {
    if (!feedData || feedData.items.length === 0) return [];
    return groupFeedIntoSections(feedData.items);
  }, [feedData]);

  const feedStats = useMemo(() => {
    if (!feedData) return { events: 0, futures: 0 };
    return {
      events: feedData.items.filter((i) => i.type === "event").length,
      futures: feedData.items.filter((i) => i.type === "futures").length,
    };
  }, [feedData]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">{categoryEmoji}</span>
        <div>
          <h1 className="text-lg font-bold text-text-primary">
            {categoryName}
          </h1>
          <div className="flex items-center gap-2 text-micro text-text-muted">
            <Link href="/categories" className="hover:text-text-secondary transition-colors">
              All Categories
            </Link>
            {feedData && feedData.items.length > 0 && (
              <>
                <span>&middot;</span>
                <span>
                  {feedStats.events > 0 && `${feedStats.events} event${feedStats.events !== 1 ? "s" : ""}`}
                  {feedStats.events > 0 && feedStats.futures > 0 && ", "}
                  {feedStats.futures > 0 && `${feedStats.futures} market${feedStats.futures !== 1 ? "s" : ""}`}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {feedError && (
        <ErrorMessage
          message={feedError.message}
          onRetry={() => refreshFeed()}
        />
      )}

      {/* Loading */}
      {feedLoading && !feedData && <SkeletonGrid count={6} />}

      {/* Content */}
      {feedData && (
        <>
          {feedData.items.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-text-secondary mb-2">
                No {categoryName.toLowerCase()} items right now
              </p>
              <p className="text-caption text-text-muted">
                Check back soon or{" "}
                <Link href="/categories" className="underline hover:text-text-secondary">
                  browse other categories
                </Link>
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {feedSections.map((section) => (
                <section key={section.key}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">{section.emoji}</span>
                    <h2 className={`text-sm font-semibold ${section.accent}`}>
                      {section.title}
                    </h2>
                    <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
                      {section.items.length}
                    </span>
                  </div>
                  <div
                    className="grid gap-3"
                    style={{
                      gridTemplateColumns:
                        "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                    }}
                  >
                    {section.items.map((item) => {
                      const key =
                        item.type === "event"
                          ? `cat-event-${(item.data as FeedEventData).id}`
                          : `cat-futures-${(item.data as FeedFuturesData).id}`;
                      return <FeedCard key={key} item={item} />;
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
