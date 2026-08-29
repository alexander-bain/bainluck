/**
 * UX-P179 — the VERBATIM pre-fix `CurrentEventBanner`, committed as a fixture.
 *
 * Produced by `git show b79130bd:frontend/app/categories/golf/page.tsx` and
 * slicing lines 451-534 — the whole function, untouched. It exists so the
 * BEFORE panel of `artifacts-ux-p179/golf-current-event.html` is a real render
 * of the broken component rather than a drawing of one: the fixed component
 * cannot produce a day-early date, so there is no other way to show the defect.
 *
 * Precedents: `uxp178HubUpcomingCardLegacy.tsx`, `uxp177RelatedByTagLegacy.tsx`.
 *
 * ⚠️ DO NOT "FIX" THIS FILE. Its whole value is that it is wrong in exactly the
 * way production was wrong on 2026-08-29.
 */

import { formatProbability } from "@/lib/api";
import type { GolfCurrentEvent, FuturesOutcomeHistory } from "@/lib/types";

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
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} \u2013 ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else if (now > end) {
      statusLabel = "Just Finished";
    } else {
      const daysUntil = Math.ceil(
        (start.getTime() - now.getTime()) / 86400000
      );
      statusLabel = daysUntil <= 7 ? "This Week" : "Coming Up";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} \u2013 ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
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
      dateLabel = `Ends ${resDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else {
      dateLabel = resDate.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
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
