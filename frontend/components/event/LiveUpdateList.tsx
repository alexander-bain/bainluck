'use client';

import { updateTimeText, venueName, type LiveUpdate } from '@/lib/event/liveUpdateStream';

/**
 * #10090 (Alex 2026-11-01) — the EKG panel's scrolling list of every venue
 * update feeding the headline: source and receipt time to the hundredth,
 * newest at the top, duplicates included. Activity only, never a price's age.
 */
export default function LiveUpdateList({ updates, timeZone }: { updates: LiveUpdate[]; timeZone?: string }) {
  return (
    <div className="mb-2 border-b border-surface-border pb-2" data-testid="live-update-list">
      <p className="mb-1 font-medium text-text-primary">Updates feeding this number</p>
      {updates.length === 0 ? (
        <p className="text-text-muted">Waiting for the next update…</p>
      ) : (
        <ol className="max-h-48 space-y-0.5 overflow-y-auto tabular-nums" aria-label="Venue updates, newest first">
          {updates.map((update) => (
            <li key={update.seq} className="flex justify-between gap-3">
              <span className="text-text-primary">{venueName(update.source)}</span>
              <span>{updateTimeText(update.at, timeZone)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
