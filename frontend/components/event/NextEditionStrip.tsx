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

import { formatEditionWindow, daysUntil } from "@/lib/eventConceptDisplay";
import type { EventConceptResponse } from "@/lib/types";

// #8139 (ux/1455): these two moved to `lib/eventConceptDisplay` so the concept
// HEADER can print the same edition window when a standing competition has no
// dates of its own — one date grammar for both surfaces, not two (notice 35).
// Re-exported here because this component was their home and callers import
// them from it; the implementations are unchanged.
export { formatEditionWindow, daysUntil };

interface NextEditionStripProps {
  competition: EventConceptResponse["competition"];
  // The page only mounts this once settled, but gate here too: a live or
  // upcoming edition already IS the next edition, and telling a reader watching
  // the Masters that the Masters returns in April is nonsense.
  settled: boolean;
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
