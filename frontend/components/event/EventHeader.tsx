"use client";

// #999 L2-64 Event Concept Page — event-framed header. H1 = the event (not a
// market), a status chip, date/venue line, a "markets tracked" count, and a
// section nav that anchor-scrolls to the page sections. Light tokens, no odds,
// no source names.

import { useEffect, useState } from "react";
import { statusLabel, eventDateRange, countdownLabel } from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

interface SectionNavItem {
  id: string;
  label: string;
}

interface EventHeaderProps {
  event: EventConceptResponse["event"];
  marketsTracked: number;
  /** Section anchors present on the page (built by the page from what rendered). */
  nav: SectionNavItem[];
  fallbackName: string;
}

export default function EventHeader({
  event,
  marketsTracked,
  nav,
  fallbackName,
}: EventHeaderProps) {
  const dateRange = eventDateRange(event.start_date, event.end_date);
  const meta = [dateRange, event.venue, event.location].filter(Boolean).join(" · ");

  // L2-78: honest "Starts in N days" countdown for the pre-tournament header
  // (The Open, July 15). Computed after mount so the SSR/CSR clocks can't diverge
  // and trip a hydration mismatch near a day boundary.
  const [countdown, setCountdown] = useState<string | null>(null);
  useEffect(() => {
    setCountdown(countdownLabel(event.status, event.start_date, Date.now()));
  }, [event.status, event.start_date]);

  return (
    <header className="border-b border-surface-border pb-4">
      <div className="flex items-center gap-2 mb-2 text-[11px] uppercase tracking-widest text-text-muted">
        <span>{event.domain}</span>
        <span
          className={`px-1.5 py-0.5 rounded font-semibold ${
            event.status === "live"
              ? "bg-accent-live/15 text-accent-live"
              : event.status === "settled"
                ? "bg-text-muted/15 text-text-secondary"
                : "bg-accent-brand/10 text-accent-brand"
          }`}
        >
          {statusLabel(event.status)}
        </span>
        {event.is_major && (
          <span className="px-1.5 py-0.5 rounded font-semibold bg-accent-futures/10 text-accent-futures">
            Major
          </span>
        )}
        {countdown && (
          <span className="px-1.5 py-0.5 rounded font-semibold bg-accent-brand/10 text-accent-brand">
            {countdown}
          </span>
        )}
      </div>

      <h1 className="text-title-1 font-semibold text-text-primary tracking-tight">
        {event.name || fallbackName}
      </h1>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5 text-sm text-text-secondary">
        {meta && <span>{meta}</span>}
        {meta && marketsTracked > 0 && <span className="text-text-muted">·</span>}
        {marketsTracked > 0 && (
          <span className="text-text-muted">
            {marketsTracked} market{marketsTracked === 1 ? "" : "s"} tracked
          </span>
        )}
      </div>

      {nav.length > 0 && (
        <nav className="flex flex-wrap gap-2 mt-3">
          {nav.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className="text-xs px-2.5 py-1 rounded-full bg-surface-elevated text-text-secondary hover:text-text-primary transition-colors"
            >
              {n.label}
            </a>
          ))}
        </nav>
      )}
    </header>
  );
}
