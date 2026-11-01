'use client';

import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from 'react';

import type { HeroFact } from '@/lib/event/heroFreshness';
import {
  formatObservationClock,
  priceAgeClock,
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

export type ObservationDelivery = 'dnpl' | 'committed' | 'unknown';

/**
 * The exact clocks behind a tap. ONE model, opened from the chart status and,
 * since Alex 67, from the hero's EKG — the same panel, never a second copy
 * (#8336, #4469).
 */
export interface ConnectionTimes {
  observation?: { eventId: number; count: number; delivery: ObservationDelivery };
  /** The accepted price clock — the same one the tracker keys receipts on. */
  priceObservedAt: string | null | undefined;
  /**
   * #10090 decision J = A — the stream's `confirmed_at`: the newest venue input
   * that agreed with the published price. Shown as its own row only when it is
   * newer than the observation; `data-observation-at` stays the observation.
   */
  priceConfirmedAt?: string | null;
  /** True when a score is on screen, so its confirmation time is a fact worth giving. */
  scoreShown: boolean;
  /** The clock of the score tuple actually drawn (#4571). */
  scoreConfirmedAt: string | null | undefined;
  /** `heroFreshness`'s answer: which visible fact is the oldest. */
  oldestFact: HeroFact | null;
  /**
   * #10090 Alex 2026-10-31 — when a source last told us the number on screen
   * (`marketUpdateClock`): never a database write time.
   */
  marketUpdatedAt?: string | null;
}

interface LiveConnectionStatusProps extends ConnectionTimes {
  presentation: ConnectionPresentation;
  /**
   * Whether this copy speaks to screen readers. The fullscreen copy sits over
   * the inline one, which stays mounted; two live regions would say it twice.
   */
  announces?: boolean;
  /**
   * #10090 Alex 67 — the EKG is showing and the connection is healthy, so the
   * status draws nothing. The live region stays mounted (empty until there is
   * something to say), so an interruption is still announced the moment it
   * happens rather than appearing inside a region the reader never heard.
   */
  quiet?: boolean;
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

function Clock({ iso, now, milliseconds = false }: { iso: string | null | undefined; now: number; milliseconds?: boolean }) {
  const wall = formatObservationClock(iso, milliseconds);
  if (!wall) return <span>Time unavailable</span>;
  const age = ageWords(iso, now);
  return (
    <span>
      <time dateTime={iso as string}>{wall}</time>
      {age ? <span className="text-text-muted"> · {age}</span> : null}
    </span>
  );
}

/**
 * Open/close for a button that shows the exact times. Escape and an outside tap
 * close; Escape returns focus to the button. Listening only while open, so a
 * closed button costs the page nothing.
 */
export function useTimesDisclosure() {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

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

  // Stable, so a caller can subscribe it to window events without churn.
  const close = useCallback(() => setOpen(false), []);
  return { open, id, root, button, toggle: () => setOpen((v) => !v), close };
}

/**
 * The exact-times panel. By default it hangs from the caller's `relative` row
 * (see above); a caller with no room for that row passes its own `placement`
 * classes and `style` (the EKG's, which sits in a clipped hero).
 */
export function ConnectionTimesPanel({
  id,
  open,
  now,
  placement = 'absolute inset-x-3 top-full',
  style,
  priceObservedAt,
  priceConfirmedAt = null,
  scoreShown,
  scoreConfirmedAt,
  marketUpdatedAt,
  children,
}: ConnectionTimes & {
  id: string; open: boolean; now: number; placement?: string; style?: CSSProperties;
  /** #10090: the EKG's update list, above the times (`EkgTimesButton`). */
  children?: ReactNode;
}) {
  return (
    <div
      id={id}
      hidden={!open}
      style={style}
      className={`${placement} z-20 rounded-lg border border-surface-border bg-surface-card p-3 text-left text-xs text-text-secondary shadow-card`}
    >
      {children}
      <dl className="space-y-1.5">
        <div>
          <dt className="font-medium text-text-primary">Latest source update</dt>
          <dd>
            <Clock iso={marketUpdatedAt ?? priceAgeClock(priceObservedAt, priceConfirmedAt)} now={now} />
          </dd>
        </div>
        {scoreShown ? (
          <div>
            <dt className="font-medium text-text-primary">Score</dt>
            <dd>
              <Clock iso={scoreConfirmedAt} now={now} />
            </dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}

export default function LiveConnectionStatus({
  presentation,
  announces = true,
  quiet = false,
  now = Date.now(),
  ...times
}: LiveConnectionStatusProps) {
  const { open, id: detailsId, root, button, toggle, close } = useTimesDisclosure();
  // Quiet unmounts the button; a panel left open must not return untapped.
  useEffect(() => { if (quiet) close(); }, [quiet, close]);
  const { label, tone, breathes, announcement } = presentation;
  const { observation, priceObservedAt } = times;

  return (
    <div ref={root} className="min-w-0" data-testid="live-connection-status" data-status={label}
      data-quiet={quiet ? 'true' : undefined}
      data-observation-at={typeof priceObservedAt === 'string' && Number.isFinite(Date.parse(priceObservedAt)) ? priceObservedAt : ''}
      data-observation-count={observation?.count ?? 0}
      data-observation-delivery={observation?.delivery ?? 'unknown'}
      data-observation-event-id={observation?.eventId ?? ''}
    >
      {quiet ? null : (
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={detailsId}
        onClick={toggle}
        className={`flex max-w-full items-start gap-1.5 rounded-xl px-2 py-0.5 text-left text-[11px] font-medium hover:bg-surface-elevated focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand ${TEXT_TONE[tone]}`}
      >
        <span
          aria-hidden="true"
          // The breathe is the gentlest motion the system has, and only a
          // healthy open connection earns it; Reduce Motion gets a still dot.
          className={`mt-1 h-2 w-2 shrink-0 rounded-full ${DOT_TONE[tone]} ${breathes ? 'motion-safe:animate-pulse' : ''}`}
        />
        {/* #9655 — the whole state, never an ellipsis. "Updates interrupted ·
            reconnecting" is wider than the room beside the title at 390px, and
            truncated it read "reconn…", hiding the half that says it is being
            handled. So the words wrap — whole words, never mid-word — and the
            dot sits on the first line (`mt-1` centres 8px on a 16px line). */}
        <span className="min-w-0 leading-4">{label}</span>
        <span className="sr-only">, show update times</span>
      </button>
      )}
      {announces ? (
        <span className="sr-only" role="status" aria-live="polite">
          {announcement}
        </span>
      ) : null}
      {quiet ? null : <ConnectionTimesPanel id={detailsId} open={open} now={now} {...times} />}
    </div>
  );
}
