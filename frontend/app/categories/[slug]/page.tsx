"use client";

import { useMemo, useState, useCallback, type ReactNode } from "react";
import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import { useAuthContext } from "@/components/AuthProvider";
import { useDiscoverPriceStream } from "@/hooks/useDiscoverPriceStream";
import { usePriceVisibility } from "@/hooks/usePriceVisibility";
import { getCategoryByKey, SPORT_CATEGORIES } from "@/lib/sportCategories";
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";
import { groupFeedIntoSections, groupTopMarkets, isGroupedMarket, flattenFeedBundles } from "@/lib/feedSections";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData } from "@/lib/types";
import FeedCard from "@/components/FeedCard";
import CombinedFeedCard from "@/components/CombinedFeedCard";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import Link from "next/link";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

const PAGE_SIZE = 50;

function PricedCategoryCardShell({
  owner,
  items,
  report,
  children,
}: {
  owner: string;
  items: FeedItem[];
  report: (owner: string, keys: string[], visible: boolean) => void;
  children: ReactNode;
}) {
  const ref = usePriceVisibility(owner, items, report);
  return <div ref={ref}>{children}</div>;
}

export default function CategoryPage({
  params,
}: {
  params: { slug: string };
}) {
  const slug = params.slug;
  const category = getCategoryByKey(slug);
  const categoryName = category?.name ?? toTitleCaseAcronymSafe(slug);
  const categoryEmoji = category?.emoji ?? "\uD83C\uDFC6";

  usePageTracking({ pageType: "category", pageTitle: `${categoryName} - Bain Luck` });
  useScrollDepth({ pageType: "category" });
  useEngagementTime({ pageType: "category" });

  const { user, isLoading: authLoading } = useAuthContext();

  // The slug IS the category key the tiles count (`llm_sport_category`), so it
  // goes to the feed as `category=`, not as a `sport:<slug>` tag. The tag
  // vocabulary is a fixed 22-value allowlist that the classifier long ago
  // outgrew — 26 of the 48 counted categories, `table_tennis` (the largest on
  // the site) among them, carry no `sport:` tag at all, so every one of their
  // pages was structurally empty no matter how many markets the tile promised.

  const [extraItems, setExtraItems] = useState<FeedItem[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

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
    () => fetchFeed({ limit: PAGE_SIZE, category: slug }),
    {
      refreshInterval: 30000,
      onSuccess: (data) => {
        setHasMore(data?.has_more ?? false);
        setExtraItems([]);
      },
    }
  );

  const allItems = useMemo(() => {
    if (!feedData) return [];
    return [...feedData.items, ...extraItems];
  }, [feedData, extraItems]);

  // #10090: project live committed + provisional (< 0.5 s) SSE prices onto visible category cards.
  const priceGroups = useMemo(
    () => allItems.map((item) => ({ type: "single" as const, item })),
    [allItems],
  );
  const streamedPrices = useDiscoverPriceStream(priceGroups, user?.uid ?? "anonymous");
  const setPriceVisibility = streamedPrices.setPriceVisibility;
  const pricedItems = useMemo(
    () => streamedPrices.items.flatMap((group) => (group.item ? [group.item] : [])),
    [streamedPrices.items],
  );

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const result = await fetchFeed({
        limit: PAGE_SIZE,
        offset: allItems.length,
        category: slug,
      });
      setExtraItems((prev) => [...prev, ...result.items]);
      setHasMore(result.has_more);
    } catch (e) {
      console.error("Load more failed:", e);
    }
    setLoadingMore(false);
  }, [loadingMore, hasMore, allItems.length, slug]);

  const feedSections = useMemo(() => {
    if (pricedItems.length === 0) return [];
    return groupFeedIntoSections(pricedItems);
  }, [pricedItems]);

  const feedStats = useMemo(() => {
    if (pricedItems.length === 0) return { events: 0, futures: 0 };
    // #2597 — count the CARDS, not the feed slots. A bundle is one item that
    // renders as several, so the raw filter promised "18 markets" over a page
    // showing 22 and a section badge saying 19: three numbers for one page.
    const cards = flattenFeedBundles(pricedItems);
    return {
      events: cards.filter((i) => i.type === "event").length,
      futures: cards.filter((i) => i.type === "futures").length,
    };
  }, [pricedItems]);

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
            {allItems.length > 0 && (
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
          {allItems.length === 0 ? (
            <div className="text-center py-16" data-empty-state-name="category-no-items">
              <p className="text-body text-text-secondary mb-2">
                No {categoryName.toLowerCase()} items right now
              </p>
              {/* Ruling 142: the empty state says what this page IS, not when
                  it will refill. The link is navigation, not a promise. */}
              <p className="text-caption text-text-muted">
                This page lists open {categoryName.toLowerCase()} markets.{" "}
                <Link href="/categories" className="underline hover:text-text-secondary">
                  Browse other categories
                </Link>
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {feedSections.map((section) => {
                const isMarkets = section.key === "markets";
                const groupedMarkets = isMarkets
                  ? groupTopMarkets(section.items)
                  : null;

                return (
                  <section key={section.key}>
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-sm">{section.emoji}</span>
                      <h2 className={`text-sm font-semibold ${section.accent}`}>
                        {section.title}
                      </h2>
                      <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
                        {section.count}
                      </span>
                    </div>
                    <div
                      className="grid gap-3"
                      style={{
                        gridTemplateColumns:
                          "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
                      }}
                    >
                      {isMarkets && groupedMarkets
                        ? groupedMarkets.ordered.map((entry) => {
                            if (isGroupedMarket(entry)) {
                              const owner = `grouped-${entry.canonicalKey}`;
                              return (
                                <PricedCategoryCardShell
                                  key={owner}
                                  owner={owner}
                                  items={entry.items}
                                  report={setPriceVisibility}
                                >
                                  <CombinedFeedCard group={entry} />
                                </PricedCategoryCardShell>
                              );
                            }
                            const data = entry.data as FeedFuturesData;
                            const owner = `cat-futures-${data.id}`;
                            return (
                              <PricedCategoryCardShell
                                key={owner}
                                owner={owner}
                                items={[entry]}
                                report={setPriceVisibility}
                              >
                                <FeedCard item={entry} />
                              </PricedCategoryCardShell>
                            );
                          })
                        : section.items.map((item) => {
                            const key =
                              item.type === "event"
                                ? `cat-event-${(item.data as FeedEventData).id}`
                                : item.type === "tournament"
                                ? `cat-tournament-${(item.data as FeedTournamentData).key}`
                                : `cat-futures-${(item.data as FeedFuturesData).id}`;
                            return (
                              <PricedCategoryCardShell
                                key={key}
                                owner={key}
                                items={[item]}
                                report={setPriceVisibility}
                              >
                                <FeedCard item={item} />
                              </PricedCategoryCardShell>
                            );
                          })}
                    </div>
                  </section>
                );
              })}

              {/* Load More */}
              {hasMore && (
                <div className="flex justify-center pt-2 pb-4">
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="px-5 py-2 text-sm font-medium text-text-secondary bg-surface-elevated hover:bg-surface-hover rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loadingMore ? "Loading..." : "Load More"}
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
