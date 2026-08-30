"use client";

import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedConceptData, FeedEventData, FeedFuturesData } from "@/lib/types";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import { eventPath } from "@/lib/eventKey";

/** The item types this section knows how to render.
 *
 * UX-P177: this was an inverted list — `event` rendered, `tournament` returned
 * null, and EVERYTHING ELSE fell through to the futures branch. `concept` and
 * `bundle` are both in `FeedItem["type"]` and neither carries a numeric `id`, so
 * a concept rendered as `/futures/undefined` with no probability beside it.
 * Measured live on 2026-08-29: every one of the four rows on `/futures/195`'s
 * "More Mma" section was a concept, so all four were dead links.
 *
 * An allowlist means the next type added to the union is invisible here until
 * someone teaches this component to draw it, rather than silently broken.
 */
const RENDERABLE = new Set(["event", "futures", "concept"]);

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
    .filter((item) => RENDERABLE.has(item.type))
    .filter((item) => {
      if (excludeId === undefined) return true;
      const id =
        item.type === "event"
          ? (item.data as FeedEventData).id
          : item.type === "futures"
          ? (item.data as FeedFuturesData).id
          : null;
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

          // Event concepts (UFC cards, F1 Grands Prix, cycling grand tours) link
          // to /event/{key}, never /futures/{id} — a concept has no numeric id.
          // The leader is guarded exactly as `ConceptFeedCard` guards it, never
          // laxer: presence plus a real name plus a numeric probability.
          if (item.type === "concept") {
            const d = item.data as FeedConceptData;
            const leader =
              d.leader && (d.leader.name ?? "").trim() &&
              typeof d.leader.probability === "number"
                ? d.leader
                : null;
            return (
              <Link
                key={`rel-concept-${d.key}`}
                href={eventPath(d.key)}
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
          }

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
