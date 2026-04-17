"use client";

import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedEventData, FeedFuturesData } from "@/lib/types";
import Link from "next/link";
import { formatProbability } from "@/lib/api";

interface RelatedByTagProps {
  /** Tag queries to filter by, e.g. ["sport:basketball"] */
  tags: string[];
  /** ID to exclude from results (current item) */
  excludeId?: number;
  /** Type to match for exclusion */
  excludeType?: "event" | "futures";
  /** Max items to display */
  limit?: number;
  /** Section title */
  title?: string;
}

export default function RelatedByTag({
  tags,
  excludeId,
  excludeType,
  limit = 6,
  title = "More Like This",
}: RelatedByTagProps) {
  const { data, isLoading } = useSWR(
    tags.length > 0 ? ["related-by-tag", ...tags] : null,
    () => fetchFeed({ limit: limit + 5, tags }),
    { refreshInterval: 60000 }
  );

  if (!data || data.items.length === 0) return null;

  // Filter out the current item and limit
  const items = data.items
    .filter((item) => {
      if (excludeId === undefined) return true;
      const id =
        item.type === "event"
          ? (item.data as FeedEventData).id
          : item.type === "tournament"
          ? null
          : (item.data as FeedFuturesData).id;
      return !(item.type === excludeType && id === excludeId);
    })
    .slice(0, limit);

  if (items.length === 0) return null;

  return (
    <section className="mt-8">
      <h3 className="text-sm font-semibold text-text-secondary mb-3">
        {title}
      </h3>
      <div className="space-y-2">
        {items.map((item) => {
          if (item.type === "event") {
            const d = item.data as FeedEventData;
            return (
              <Link
                key={`rel-event-${d.id}`}
                href={`/events/${d.id}`}
                className="flex items-center justify-between p-3 rounded-lg bg-surface-card border border-surface-border hover:border-text-muted transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    {d.status === "live" && (
                      <span className="w-1.5 h-1.5 rounded-full bg-accent-live shrink-0" />
                    )}
                    <span className="text-xs font-medium text-text-primary truncate">
                      {d.away_team} @ {d.home_team}
                    </span>
                  </div>
                  {d.status === "live" && d.home_score !== null && (
                    <span className="text-micro text-text-muted">
                      {d.away_score} - {d.home_score}
                    </span>
                  )}
                </div>
                {d.current_odds && (
                  <div className="text-xs text-text-muted shrink-0 ml-2">
                    {formatProbability(d.current_odds.home_probability)} /{" "}
                    {formatProbability(d.current_odds.away_probability)}
                  </div>
                )}
              </Link>
            );
          }

          // Tournament — skip in related-by-tag (these are full cards elsewhere)
          if (item.type === "tournament") return null;

          // Futures
          const d = item.data as FeedFuturesData;
          const leader = d.top_outcomes?.[0];
          return (
            <Link
              key={`rel-futures-${d.id}`}
              href={`/futures/${d.id}`}
              className="flex items-center justify-between p-3 rounded-lg bg-surface-card border border-surface-border hover:border-text-muted transition-colors"
            >
              <span className="text-xs font-medium text-text-primary truncate flex-1 min-w-0">
                {d.name}
              </span>
              {leader && (
                <span className="text-xs text-text-muted shrink-0 ml-2">
                  {leader.name} {formatProbability(leader.probability)}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
