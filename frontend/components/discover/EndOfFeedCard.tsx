"use client";

import Link from "next/link";
import { trackEvent } from "@/lib/analytics";

// Graceful end-of-feed state — replaces the abrupt silent stop when the pool is
// exhausted (thin-pool has_more=false, the #1087 web sibling) or empty. Offers a
// refresh affordance (web has no pull-to-refresh) plus category exploration links.

export const END_OF_FEED_CATEGORIES = [
  { href: "/politics", label: "Politics" },
  { href: "/economics", label: "Economics" },
  { href: "/entertainment", label: "Entertainment" },
  { href: "/weather", label: "Weather" },
  { href: "/sports", label: "Sports" },
];

export default function EndOfFeedCard({
  count,
  onRefresh,
}: {
  count: number;
  onRefresh: () => void;
}) {
  return (
    // `data-testid` + `data-empty-state-name` are the browser-audit rail's
    // stable hook for "the feed legitimately has nothing more" (L2-223). The
    // audit previously matched the copy string, so a wording change would have
    // silently turned a proven empty state into an unproven blank page. The
    // name is exported as data rather than scraped from the DOM text.
    <div
      className="w-full max-w-md rounded-2xl bg-surface-card border border-surface-border px-6 py-8 text-center"
      data-testid="discover-empty-state"
      data-empty-state-name={count > 0 ? "end-of-feed" : "no-markets"}
      role="status"
    >
      <p className="text-lg font-medium text-text-primary">You&apos;re all caught up</p>
      <p className="text-sm text-text-secondary mt-1">
        {count > 0 ? `${count} markets explored — ` : ""}new markets open throughout the day, so check back soon.
      </p>
      <button
        onClick={onRefresh}
        className="mt-4 inline-flex items-center justify-center rounded-full bg-accent-brand/10 text-accent-brand text-sm font-medium px-4 py-2 hover:bg-accent-brand/20 transition-colors"
      >
        Refresh feed
      </button>
      <div className="mt-5 pt-4 border-t border-surface-border">
        <p className="text-xs text-text-muted mb-3">Explore by category</p>
        <div className="flex flex-wrap justify-center gap-2">
          {END_OF_FEED_CATEGORIES.map((c) => (
            <Link
              key={c.href}
              href={c.href}
              onClick={() =>
                trackEvent("navigation_click", {
                  click_type: "nav_tab",
                  from_page: "discover",
                  to_page: c.href,
                })
              }
              className="rounded-full bg-surface-elevated text-text-secondary text-xs px-3 py-1.5 hover:text-text-primary hover:bg-surface-border transition-colors"
            >
              {c.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
