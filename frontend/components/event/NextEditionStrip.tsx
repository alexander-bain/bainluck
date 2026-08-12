"use client";

// UX-P065 (#1744 step 2a, epic #1741) — THE BETWEEN-EDITIONS STRIP.
//
// A major is between editions ~51 weeks a year, so for a competition page this
// is not an edge case, it is the DEFAULT state of almost every visit. Measured
// 2026-08-12: `event:golf:the-masters` served April's settled Masters — Rory
// McIlroy, correct, four months old — with nothing anywhere saying the 2027
// edition exists. Settled-means-settled says the page keeps showing the champion;
// it does not say the page has to pretend the competition ended forever.
//
// Deliberately NOT a link. The next edition's `concept_key` is DECLARED data, and
// two of the declared keys 404 in production today (event:golf:masters-2027,
// event:golf:ryder-cup-2027) while their year-less siblings serve. Reconciling
// that is routing work and belongs to the page queue with its own before/after;
// linking to it now would ship a dead breadcrumb to prove a point about identity.
//
// Honest-empty (ruling 027): no next edition → no strip.

import type { EventConceptResponse } from "@/lib/types";

interface NextEditionStripProps {
  competition: EventConceptResponse["competition"];
  // The page only mounts this once settled, but gate here too: a live or
  // upcoming edition already IS the next edition, and telling a reader watching
  // the Masters that the Masters returns in April is nonsense.
  settled: boolean;
}

/** "April 8–11, 2027" · "April 8, 2027" · "December 30, 2026 – January 2, 2027". */
export function formatEditionWindow(
  startISO: string | null | undefined,
  endISO: string | null | undefined,
): string | null {
  const start = parseISODate(startISO);
  if (!start) return null;
  const end = parseISODate(endISO) ?? start;
  const month = (d: Date) => d.toLocaleString("en-US", { month: "long", timeZone: "UTC" });
  const day = (d: Date) => d.getUTCDate();
  if (start.getTime() === end.getTime()) {
    return `${month(start)} ${day(start)}, ${start.getUTCFullYear()}`;
  }
  if (start.getUTCFullYear() !== end.getUTCFullYear()) {
    return `${month(start)} ${day(start)}, ${start.getUTCFullYear()} – ${month(end)} ${day(
      end,
    )}, ${end.getUTCFullYear()}`;
  }
  if (start.getUTCMonth() !== end.getUTCMonth()) {
    return `${month(start)} ${day(start)} – ${month(end)} ${day(end)}, ${end.getUTCFullYear()}`;
  }
  return `${month(start)} ${day(start)}–${day(end)}, ${end.getUTCFullYear()}`;
}

/**
 * Whole days from `now` until the edition starts, or null when that is not a
 * forward-looking number. The countdown is computed HERE, in the client, and
 * never read off the payload: the envelope is mirrored for up to 24h and served
 * stale on a miss, so a server-stamped "240 days" would be wrong for most of the
 * life of the response it rode in on (the gotcha #118 shape — a number with no
 * window is not a measurement).
 */
export function daysUntil(startISO: string | null | undefined, now: Date): number | null {
  const start = parseISODate(startISO);
  if (!start) return null;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const days = Math.round((start.getTime() - today) / 86_400_000);
  return days > 0 ? days : null;
}

function parseISODate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const ms = Date.parse(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(ms) ? null : new Date(ms);
}

export default function NextEditionStrip({ competition, settled }: NextEditionStripProps) {
  const next = competition?.next_edition;
  const window = formatEditionWindow(next?.start, next?.end);
  if (!settled || !competition || !next || !window) return null;

  const name = competition.name || next.name;
  if (!name) return null;

  const days = daysUntil(next.start, new Date());

  return (
    <section
      aria-label="Next edition"
      className="bg-surface-card rounded-card shadow-card border border-surface-border px-4 py-3"
    >
      <div className="text-[11px] font-semibold uppercase tracking-widest text-text-muted mb-1">
        Next edition
      </div>
      <p className="text-sm leading-relaxed text-text-primary">
        <span className="font-semibold">{name}</span> returns {window}
        {days !== null && (
          <span className="text-text-secondary"> · in {days.toLocaleString()} days</span>
        )}
        .
      </p>
    </section>
  );
}
