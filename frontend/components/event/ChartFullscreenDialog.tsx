"use client";

import { useEffect, useRef, type ReactNode, type RefObject } from "react";

/**
 * #10250 — the event page's fullscreen chart, as a dialog that sits above the
 * page chrome.
 *
 * It used to be a bare `fixed inset-0 z-50` div in `app/events/[id]/page.tsx`.
 * The phone bottom nav is also `fixed … z-50` and comes later in the DOM, so at
 * 390px the nav painted over the chart's bottom 57px. On production
 * (`/events/15318028`, 2026-10-02 23:24Z) the time-axis ticks sat at y=778 and
 * the nav started at y=787, so the one view a reader opens to read the chart
 * hid its time axis.
 *
 * `z-[100]` is the layer the site's other full-screen dialog already uses
 * (`MobileSearchOverlay`). The bottom padding takes the device's safe area, so
 * the axis also clears the iPhone home indicator. The shopper found two more
 * problems in the same view: the close button had no accessible name, and
 * Escape did nothing.
 */

type KeyTarget = Pick<Window, "addEventListener" | "removeEventListener">;
type Focusable = { focus: () => void } | null | undefined;

/**
 * Wires one open dialog: Escape closes it, focus moves to the close button,
 * and on teardown (by ×, Escape, or the page unmounting) focus returns to
 * the control that opened it. Returns the teardown. Exported so the arms can
 * be tested without a browser.
 */
export function attachFullscreenDialog({
  target,
  onClose,
  closeButton,
  opener,
}: {
  target: KeyTarget;
  onClose: () => void;
  closeButton: Focusable;
  opener: Focusable;
}): () => void {
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  };
  target.addEventListener("keydown", onKeyDown as EventListener);
  closeButton?.focus();
  return () => {
    target.removeEventListener("keydown", onKeyDown as EventListener);
    opener?.focus();
  };
}

export default function ChartFullscreenDialog({
  title,
  onClose,
  openerRef,
  status,
  children,
}: {
  title: string;
  onClose: () => void;
  openerRef?: RefObject<HTMLElement | null>;
  status?: ReactNode;
  children: ReactNode;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  // The latest onClose without re-binding on every render of the page.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    // The opener is read once, at open: the page's ref object never changes.
    const opener = openerRef?.current;
    return attachFullscreenDialog({
      target: window,
      onClose: () => onCloseRef.current(),
      closeButton: closeRef.current,
      opener,
    });
  }, [openerRef]);

  return (
    <div
      className="fixed inset-0 z-[100] bg-surface-card flex flex-col pb-[env(safe-area-inset-bottom,0px)]"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      data-testid="chart-fullscreen-dialog"
    >
      <div className="relative flex items-center justify-between px-4 py-3 border-b border-surface-border">
        <div className="flex min-w-0 items-center gap-3">
          <h2 className="shrink-0 text-sm font-semibold text-text-primary">{title}</h2>
          {status}
        </div>
        <button
          ref={closeRef}
          type="button"
          onClick={onClose}
          aria-label="Close fullscreen chart"
          title="Close fullscreen chart"
          className="p-2 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
        >
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="4" x2="4" y2="12" />
            <line x1="4" y1="4" x2="12" y2="12" />
          </svg>
        </button>
      </div>
      <div className="flex-1 p-4 min-h-0">{children}</div>
    </div>
  );
}
