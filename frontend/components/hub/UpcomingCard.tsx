import Link from "next/link";

import { eventPath } from "@/lib/eventKey";
import type { HubUpcoming } from "@/lib/api";

/**
 * The `upcoming` rail card shared by every hub (/hub/mma, /hub/boxing,
 * /hub/golf, /hub/tennis).
 *
 * Extracted from `app/hub/[competition]/page.tsx` by UX-P178 for one reason: a
 * Next.js route file may only export the reserved names, so nothing inside one
 * can be rendered by a test. This card had two things worth pinning — a marquee
 * chip that had never rendered anywhere in production, and a date that was a day
 * early for every reader west of Greenwich — and neither could be asserted while
 * it lived in the page. The markup is unchanged by the move.
 */

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  // `timeZone` is pinned deliberately. These instants are midnight UTC, so
  // rendering them in the viewer's zone moves the DAY for everyone west of
  // Greenwich: `2026-09-13T00:00:00+00:00` reads "Sat, Sep 12" in Los Angeles and
  // "Sun, Sep 13" in UTC (measured 2026-08-29). Every hub card was a day early for
  // US readers, and CI cannot see it because CI runs TZ=UTC. The date we publish
  // is the date the data states.
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function StatusPill({ status }: { status: string }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent-live">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
        Live
      </span>
    );
  }
  if (status === "settled") {
    return <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Final</span>;
  }
  return <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-brand">Upcoming</span>;
}

export function UpcomingCard({ card }: { card: HubUpcoming }) {
  return (
    <Link
      href={eventPath(card.key)}
      className="group flex-shrink-0 w-64 bg-surface-card border border-surface-border rounded-2xl p-4 transition-colors hover:border-accent-brand/50 hover:bg-surface-elevated"
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={card.status} />
        {card.is_major && (
          <span className="text-[10px] font-bold uppercase tracking-wide text-accent-brand">★ Marquee</span>
        )}
      </div>
      <div className="text-[15px] font-semibold text-text-primary leading-snug line-clamp-2 min-h-[2.6em]">
        {card.name}
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
        {/* A start date is printed bare, because a bare date on a fixture card
            reads as "when it starts". The tennis rail has no start to give — its
            only date is when the tournament ENDS — so that one is labelled. An
            unlabelled end date under a LIVE pill is a contradiction the reader
            has to resolve; "Ends Sun, Sep 13" is the same fact, stated. */}
        <span>
          {formatDate(card.start_date) ||
            (formatDate(card.end_date) && `Ends ${formatDate(card.end_date)}`) ||
            "TBD"}
        </span>
        {typeof card.fight_count === "number" && card.fight_count > 0 && (
          <span className="font-mono">{card.fight_count} fights</span>
        )}
      </div>
    </Link>
  );
}
