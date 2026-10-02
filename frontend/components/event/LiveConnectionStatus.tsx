'use client';

import { useEffect, useId, useRef, useState } from 'react';

import type { HeroFact } from '@/lib/event/heroFreshness';
import {
  formatObservationClock,
  type ConnectionPresentation,
  type ConnectionTone,
} from '@/lib/event/liveConnectionStatus';
import { formatAgeFromSeconds } from '@/lib/sourceAge';

/**
 * #10200 — the event chart's one connection status, with the exact times on tap.
 *
 * The words are decided in `lib/event/liveConnectionStatus` and handed in as
 * one `presentation`, so the chart card and the fullscreen view print the same
 * model rather than two components each keeping their own (#8336, #4469).
 *
 * The button never prints a ticking age. The exact clocks live behind it: when
 * the probability was observed, when the score shown was confirmed, and which of
 * the two is older — each with its time zone, and "Time unavailable" rather than
 * a guess when a clock is absent or unreadable.
 */

interface LiveConnectionStatusProps {
  presentation: ConnectionPresentation;
  /** The accepted price clock — the same one the tracker keys receipts on. */
  priceObservedAt: string | null | undefined;
  /** True when a score is on screen, so its confirmation time is a fact worth giving. */
  scoreShown: boolean;
  /** The clock of the score tuple actually drawn (#4571). */
  scoreConfirmedAt: string | null | undefined;
  /** `heroFreshness`'s answer: which visible fact is the oldest. */
  oldestFact: HeroFact | null;
  /**
   * Whether this copy speaks to screen readers. The fullscreen copy sits over
   * the inline one, which stays mounted; two live regions would say it twice.
   */
  announces?: boolean;
  /** Injected for tests; the page re-renders every second, so `Date.now()` is fresh. */
  now?: number;
}

// THE DETAILS HANG FROM THE ROW, NOT THE BUTTON. Anchored to the button, the
// panel started wherever "Win Probability" ended and ran off the card at 390px
// (photographed on Kazakhstan v Moldova, 2026-10-02). So this component is not
// positioned itself: the caller's header row is (`relative`), and the panel
// spans that row's width beneath it, whatever the phone.

const DOT_TONE: Record<ConnectionTone, string> = {
  live: 'bg-accent-live',
  steady: 'bg-accent-live',
  attention: 'bg-accent-warning',
  neutral: 'bg-text-muted',
};

const TEXT_TONE: Record<ConnectionTone, string> = {
  live: 'text-text-primary',
  steady: 'text-text-primary',
  attention: 'text-text-primary',
  neutral: 'text-text-secondary',
};

function ageWords(iso: string | null | undefined, now: number): string | null {
  if (typeof iso !== 'string') return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const seconds = Math.max(0, Math.round((now - t) / 1000));
  return seconds < 60 ? `${seconds}s ago` : formatAgeFromSeconds(seconds);
}

function Clock({ iso, now }: { iso: string | null | undefined; now: number }) {
  const wall = formatObservationClock(iso);
  if (!wall) return <span>Time unavailable</span>;
  const age = ageWords(iso, now);
  return (
    <span>
      <time dateTime={iso as string}>{wall}</time>
      {age ? <span className="text-text-muted"> · {age}</span> : null}
    </span>
  );
}

export default function LiveConnectionStatus({
  presentation,
  priceObservedAt,
  scoreShown,
  scoreConfirmedAt,
  oldestFact,
  announces = true,
  now = Date.now(),
}: LiveConnectionStatusProps) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  // Escape and an outside tap close the details. Listening only while open, so
  // a closed status costs the page nothing.
  useEffect(() => {
    if (!open || typeof document === 'undefined') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onPointer = (e: Event) => {
      const target = e.target as Node | null;
      if (root.current && target && !root.current.contains(target)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open]);

  const { label, tone, breathes, announcement } = presentation;

  return (
    <div ref={root} className="min-w-0" data-testid="live-connection-status" data-status={label}>
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={() => setOpen((v) => !v)}
        className={`flex max-w-full items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium hover:bg-surface-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand ${TEXT_TONE[tone]}`}
      >
        <span
          aria-hidden="true"
          // The breathe is the gentlest motion the system has, and only a
          // healthy open connection earns it; Reduce Motion gets a still dot.
          className={`h-2 w-2 shrink-0 rounded-full ${DOT_TONE[tone]} ${breathes ? 'motion-safe:animate-pulse' : ''}`}
        />
        <span className="truncate whitespace-nowrap">{label}</span>
        <span className="sr-only">, show update times</span>
      </button>
      {announces ? (
        <span className="sr-only" role="status" aria-live="polite">
          {announcement}
        </span>
      ) : null}
      <div
        id={detailsId}
        hidden={!open}
        className="absolute inset-x-3 top-full z-20 rounded-lg border border-surface-border bg-surface-card p-3 text-xs text-text-secondary shadow-card"
      >
        <dl className="space-y-1.5">
          <div>
            <dt className="font-medium text-text-primary">Probability observed</dt>
            <dd>
              <Clock iso={priceObservedAt} now={now} />
            </dd>
          </div>
          {scoreShown ? (
            <div>
              <dt className="font-medium text-text-primary">Score confirmed</dt>
              <dd>
                <Clock iso={scoreConfirmedAt} now={now} />
              </dd>
            </div>
          ) : null}
          {scoreShown && oldestFact ? (
            <div>
              <dt className="font-medium text-text-primary">Oldest on screen</dt>
              <dd>{oldestFact === 'score' ? 'The score' : 'The probability'}</dd>
            </div>
          ) : null}
        </dl>
      </div>
    </div>
  );
}
