/**
 * UX-P178 — the hub upcoming card EXACTLY as it shipped before this queue.
 *
 * Extracted verbatim from `app/hub/[competition]/page.tsx` at `ad502189` with
 * `git show ad502189:'frontend/app/hub/[competition]/page.tsx' | sed -n '87,157p'`.
 * Nothing is retyped and nothing is simplified — the only edits are the `export`
 * keyword and the imports the page provided ambiently.
 *
 * It exists so the BEFORE panel of `artifacts-ux-p178/hub-upcoming-card.html` is
 * a RENDER OF THE CODE THAT ACTUALLY SHIPPED rather than a transcription of what
 * we remember it doing. That matters most for the third defect: the un-pinned
 * `toLocaleDateString` below is the reason a card read "Sat, Sep 12" in Los
 * Angeles, and the fixed component cannot reproduce it.
 *
 * DO NOT "fix" this file. Its wrongness is the point.
 */

import React from "react";
import Link from "next/link";

import { eventPath } from "@/lib/eventKey";
import type { HubUpcoming } from "@/lib/api";

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
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
        <span>{formatDate(card.start_date) || "TBD"}</span>
        {typeof card.fight_count === "number" && card.fight_count > 0 && (
          <span className="font-mono">{card.fight_count} fights</span>
        )}
      </div>
    </Link>
  );
}
