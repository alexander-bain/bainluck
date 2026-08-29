"use client";

import { formatProbability } from "@/lib/api";
import type { GolfCurrentEvent, FuturesOutcomeHistory } from "@/lib/types";

/**
 * The banner at the top of `/categories/golf`, naming the tournament the page
 * is currently about.
 *
 * Extracted from `app/categories/golf/page.tsx` by UX-P179 with its markup
 * unchanged. A Next.js route file may only export the reserved names, so
 * nothing declared inside one can be rendered by a test — and this banner was
 * the one golf surface printing a schedule date the other three disagreed with.
 *
 * ⚠️ EVERY DATE HERE IS A CALENDAR DATE, SO EVERY FORMAT PINS `timeZone: "UTC"`.
 * `/api/golf` serves schedule dates at midnight UTC — 94 of 94 rows of
 * `pga_schedule` and 3 of 3 tournament start/end pairs, measured 2026-08-29 —
 * so an un-pinned `toLocaleDateString` moves every one of them back a day for
 * every reader west of Greenwich. The three sibling renderers of these same
 * values already pin it: `components/golf/UpcomingTournaments.tsx` (`utcPart`),
 * `components/TournamentCard.tsx` (`getUTCMonth`/`getUTCDate`), and
 * `app/categories/golf/tournaments/[slug]/page.tsx` (`timeZone: "UTC"`, three
 * places). This banner was the sole outlier of the four.
 */
export default function CurrentEventBanner({
  event,
  historyData,
}: {
  event: GolfCurrentEvent;
  historyData: FuturesOutcomeHistory[] | null;
}) {
  const now = new Date();
  let statusLabel = "Coming Up";
  let dateLabel = "";

  // Detect active tournament from golfer movement (fallback when no schedule dates)
  const topGolfers = event.top_golfers ?? [];
  const hasActiveMovement = topGolfers.some(
    (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01
  );

  if (event.start_date && event.end_date) {
    const start = new Date(event.start_date);
    const end = new Date(event.end_date);
    if (now >= start && now <= end) {
      statusLabel = "This Week";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} \u2013 ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })}`;
    } else if (now > end) {
      statusLabel = "Just Finished";
    } else {
      const daysUntil = Math.ceil(
        (start.getTime() - now.getTime()) / 86400000
      );
      statusLabel = daysUntil <= 7 ? "This Week" : "Coming Up";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} \u2013 ${end.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })}`;
    }
  } else if (hasActiveMovement) {
    statusLabel = "In Progress";
  } else if (event.resolution_date) {
    const resDate = new Date(event.resolution_date);
    const daysUntil = Math.ceil(
      (resDate.getTime() - now.getTime()) / 86400000
    );
    if (daysUntil < 0) {
      statusLabel = "Just Finished";
    } else if (daysUntil <= 7) {
      statusLabel = "This Week";
      dateLabel = `Ends ${resDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })}`;
    } else {
      dateLabel = resDate.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      });
    }
  }

  return (
    <div className="bg-gradient-to-r from-[#006747]/20 via-[#006747]/10 to-[#006747]/20 border border-[#006747]/30 rounded-xl p-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-[#006747] text-xs font-semibold uppercase tracking-wider mb-1">
            &#x1F3CC;&#xFE0F; {statusLabel}
          </p>
          <h2 className="text-xl font-bold text-text-primary">{event.name}</h2>
          <p className="text-text-muted text-sm mt-1">
            {event.venue && <span>{event.venue} &middot; </span>}
            {event.golfer_count} golfers with odds
            {dateLabel && <span> &middot; {dateLabel}</span>}
          </p>
        </div>
        {/* Leader callout (compact, no full leaderboard) */}
        {topGolfers.length > 0 && (
          <div className="text-right">
            <p className="text-xs text-text-muted uppercase tracking-wider">
              Favorite
            </p>
            <p className="text-lg font-semibold text-text-primary">
              {topGolfers[0].name}
            </p>
            <p className="text-[#006747] font-mono text-sm">
              {formatProbability(topGolfers[0].probability)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
