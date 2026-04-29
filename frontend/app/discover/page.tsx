"use client";

import { useState, useCallback, useEffect } from "react";
import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedEventData, FeedFuturesData } from "@/lib/types";
import DiscoverCard from "@/components/DiscoverCard";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

const DISMISSED_KEY = "discover_dismissed";

function getDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function addDismissed(id: string) {
  const set = getDismissed();
  set.add(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...set]));
}

export default function DiscoverPage() {
  usePageTracking({ pageType: "discover", pageTitle: "Discover" });
  useScrollDepth({ pageType: "discover" });
  useEngagementTime({ pageType: "discover" });

  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  useEffect(() => {
    setDismissed(getDismissed());
  }, []);

  const { data, isLoading } = useSWR(
    "discover-feed",
    () => fetchFeed({ limit: 80 }),
    { refreshInterval: 60000 }
  );

  const handleDismiss = useCallback((itemId: string) => {
    addDismissed(itemId);
    setDismissed((prev) => new Set([...prev, itemId]));
  }, []);

  const items = (data?.items ?? []).filter((item) => {
    const id = item.type === "event"
      ? `event-${(item.data as any).id}`
      : item.type === "futures"
      ? `futures-${(item.data as any).id}`
      : `tournament-${(item.data as any).key}`;
    if (dismissed.has(id)) return false;

    // Filter out effectively resolved futures (leader ≥ 95%)
    if (item.type === "futures") {
      const fd = item.data as FeedFuturesData;
      const leader = fd.top_outcomes?.[0];
      if (leader && (leader.probability ?? 0) >= 0.95) return false;
      if (fd.status === "closed" || fd.status === "resolved") return false;
    }

    // Filter out old completed events (> 6 hours ago)
    if (item.type === "event") {
      const ed = item.data as FeedEventData;
      if (ed.status === "completed" || ed.status === "closed") {
        const ct = new Date(ed.commence_time);
        const hoursAgo = (Date.now() - ct.getTime()) / (1000 * 60 * 60);
        if (hoursAgo > 12) return false;
      }
    }

    return true;
  });

  return (
    <div className="min-h-screen bg-[#fafbfc]">
      {/* Header */}
      <header className="sticky top-0 z-20 bg-white/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-lg mx-auto px-4 py-3 flex items-center justify-between">
          <h1 className="text-lg font-black tracking-tight">Discover</h1>
          <div className="flex items-center gap-2 text-text-muted text-sm">
            <span className="font-medium">{items.length} markets</span>
          </div>
        </div>
      </header>

      {/* Feed */}
      <main className="max-w-lg mx-auto px-4 py-4 space-y-4">
        {isLoading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-2xl bg-surface-card border border-surface-border animate-pulse">
                <div className="h-44 bg-surface-elevated rounded-t-2xl" />
                <div className="p-4 space-y-3">
                  <div className="h-5 bg-surface-elevated rounded w-3/4" />
                  <div className="h-3 bg-surface-elevated rounded w-full" />
                  <div className="h-3 bg-surface-elevated rounded w-2/3" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!isLoading && items.length === 0 && (
          <div className="text-center py-20 text-text-muted">
            <p className="text-lg font-medium">All caught up!</p>
            <p className="text-sm mt-1">Check back later for new markets</p>
          </div>
        )}

        {items.map((item) => {
          const itemId = item.type === "event"
            ? `event-${(item.data as any).id}`
            : item.type === "futures"
            ? `futures-${(item.data as any).id}`
            : `tournament-${(item.data as any).key}`;

          return (
            <DiscoverCard
              key={itemId}
              item={item}
              onDismiss={() => handleDismiss(itemId)}
            />
          );
        })}
      </main>
    </div>
  );
}
