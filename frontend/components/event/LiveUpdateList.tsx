'use client';

import { useEffect, useState } from 'react';
import {
  advanceScreen, openScreen, updateProbabilityText, updateTimeText, venueName,
  type LiveUpdate, type UpdateScreen,
} from '@/lib/event/liveUpdateStream';

/** How often queued rows are checked for their reveal time. */
const REVEAL_TICK_MS = 40;

/**
 * #10090 (Alex 2026-11-01) — the EKG panel's stream of every venue update
 * feeding the headline: source, the venue's chance for the home team after
 * that update, and the receipt time to the hundredth, newest at the top,
 * duplicates included. Rows are revealed at the venues' own pace
 * (`advanceScreen`), not a heartbeat's worth at once.
 */
export default function LiveUpdateList({ updates, homeTeam, timeZone }: {
  updates: LiveUpdate[]; homeTeam?: string; timeZone?: string;
}) {
  const [screen, setScreen] = useState<UpdateScreen>(() => openScreen(updates));
  useEffect(() => {
    setScreen(previous => advanceScreen(previous, updates, performance.now()));
  }, [updates]);
  const waiting = screen.playback.queue.length > 0;
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(() => setScreen(previous => advanceScreen(previous, updates, performance.now())),
      REVEAL_TICK_MS);
    return () => clearInterval(timer);
  }, [waiting, updates]);
  return (
    <div className="mb-2 border-b border-surface-border pb-2" data-testid="live-update-list">
      <p className="font-medium text-text-primary">Updates feeding this number</p>
      {homeTeam ? <p className="mb-1 text-text-muted">{homeTeam} chance at each venue update</p> : null}
      {screen.rows.length === 0 ? (
        <p className="text-text-muted">Waiting for the next update…</p>
      ) : (
        <ol className="max-h-48 space-y-0.5 overflow-y-auto tabular-nums" aria-label="Venue updates, newest first">
          {screen.rows.map((update) => (
            <li key={update.seq} className="grid grid-cols-[1fr_auto_auto] gap-3 animate-update-row-in">
              <span className="text-text-primary">{venueName(update.source)}</span>
              <span className="text-right text-text-primary">{updateProbabilityText(update.p)}</span>
              <span className="text-right">{updateTimeText(update.at, timeZone)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
