'use client';

import { useEffect, useState, type ReactNode } from 'react';

import type { LiveUpdate } from '@/lib/event/liveUpdateStream';

import LiveUpdateList from '@/components/event/LiveUpdateList';
import {
  ConnectionTimesPanel,
  useTimesDisclosure,
  type ConnectionTimes,
} from '@/components/event/LiveConnectionStatus';

/**
 * #10090 Alex 67 — tap the EKG for the exact times.
 *
 * The heartbeat (the child) becomes a button that opens the SAME panel the
 * chart's status opens — observed, confirmed and score times, each with its
 * time zone, "Time unavailable" rather than a guess — from the same model and
 * the same open/close behaviour (#8336, #4469: one model, two places).
 *
 * WHERE IT OPENS. The EKG sits in the hero's ~200px middle column, and the hero
 * card is `overflow-hidden` with ~80px below the EKG: hung from that row like
 * the status's, the panel was 30px wide and cut off at the card's edge
 * (photographed at 390px, Newcastle Jets v Wellington, 2026-10-31). So it is
 * placed `fixed`, measured from the button when tapped — centred under it and
 * kept 12px inside the screen — and closes on scroll or resize rather than
 * drifting away from the EKG it belongs to.
 */

interface EkgTimesButtonProps extends ConnectionTimes {
  children: ReactNode;
  /** Injected for tests; the page re-renders every second, so `Date.now()` is fresh. */
  now?: number;
  /** #10090 (Alex 2026-11-01): the venue updates feeding the number, newest first. */
  updates?: LiveUpdate[];
}

const EDGE_PX = 12;
const PANEL_MAX_PX = 320;
const GAP_PX = 4;

export default function EkgTimesButton({ children, now = Date.now(), updates, ...times }: EkgTimesButtonProps) {
  const { open, id, root, button, toggle, close } = useTimesDisclosure();
  const [place, setPlace] = useState<{ top: number; left: number; width: number } | null>(null);

  useEffect(() => {
    if (!open || typeof window === 'undefined') return;
    window.addEventListener('scroll', close, { passive: true, capture: true });
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, { capture: true });
      window.removeEventListener('resize', close);
    };
  }, [open, close]);

  const onClick = () => {
    const rect = button.current?.getBoundingClientRect?.();
    if (!open && rect && typeof window !== 'undefined') {
      const width = Math.min(PANEL_MAX_PX, window.innerWidth - 2 * EDGE_PX);
      const centred = rect.left + rect.width / 2 - width / 2;
      const left = Math.min(Math.max(EDGE_PX, centred), window.innerWidth - EDGE_PX - width);
      setPlace({ top: rect.bottom + GAP_PX, left, width });
    }
    toggle();
  };

  return (
    <div ref={root} data-testid="ekg-times">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onClick}
        // A 30×9 trace is too small to hit; the padding makes a ~24px target
        // without widening the row (#10090's −0.1px headroom is width only).
        className="inline-flex items-center rounded-xl px-3 py-1.5 hover:bg-surface-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand"
      >
        {children}
        <span className="sr-only">, show update times</span>
      </button>
      <ConnectionTimesPanel id={id} open={open} now={now} placement="fixed" style={place ?? undefined} {...times}>
        {updates ? <LiveUpdateList updates={updates} /> : null}
      </ConnectionTimesPanel>
    </div>
  );
}
