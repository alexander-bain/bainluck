'use client';

import { useEffect, useState } from 'react';
import {
  EMPTY_PLAYBACK, revealUpdates, scheduleUpdates, updateProbabilityText, updateTimeText, venueName,
  type LiveUpdate, type UpdatePlayback,
} from '@/lib/event/liveUpdateStream';

/** How often queued rows are checked for their reveal time. */
const REVEAL_TICK_MS = 40;

/**
 * #10090 (Alex 2026-11-01) — the EKG panel's stream of every venue update
 * feeding the headline: source, the venue's chance for the home team after
 * that update, and the receipt time to the hundredth, newest at the top,
 * duplicates included. Rows are revealed at the venues' own pace
 * (`scheduleUpdates`), not a heartbeat's worth at once.
 */
export default function LiveUpdateList({ updates, homeTeam, timeZone }: {
  updates: LiveUpdate[]; homeTeam?: string; timeZone?: string;
}) {
  // Rows already listed when the panel opens are shown at once.
  const [playback, setPlayback] = useState<UpdatePlayback>(() => {
    const top = updates.length > 0 ? updates[0].seq : -1;
    return { ...EMPTY_PLAYBACK, scheduled: top, shown: top };
  });
  useEffect(() => {
    setPlayback(previous => scheduleUpdates(previous, updates, performance.now()));
  }, [updates]);
  const waiting = playback.queue.length > 0;
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(() => setPlayback(previous => revealUpdates(previous, performance.now())),
      REVEAL_TICK_MS);
    return () => clearInterval(timer);
  }, [waiting]);
  const shown = updates.filter(update => update.seq <= playback.shown);
  return (
    <div className="mb-2 border-b border-surface-border pb-2" data-testid="live-update-list">
      <p className="mb-1 font-medium text-text-primary">Updates feeding this number</p>
      {homeTeam ? <p className="mb-1 text-text-muted">{homeTeam} chance at each venue update</p> : null}
      {shown.length === 0 ? (
        <p className="text-text-muted">Waiting for the next update…</p>
      ) : (
        <ol className="max-h-48 space-y-0.5 overflow-y-auto tabular-nums" aria-label="Venue updates, newest first">
          {shown.map((update) => (
            <li key={update.seq} className="flex justify-between gap-3 animate-update-row-in">
              <span className="text-text-primary">{venueName(update.source)}</span>
              <span className="text-text-primary">{updateProbabilityText(update.p)}</span>
              <span>{updateTimeText(update.at, timeZone)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
