"use client";

/**
 * #10868 — the soccer match's full-size READER (web): ONE local shell, used by
 * the story reader (`SoccerMatchStories`, "Open full card") and the history
 * reader (`SoccerMatchPage`, "Full chart"). Native counterpart: the host's one
 * reader sheet (`SoccerEventPageHostAdapter10868` Session, Done in the
 * toolbar) showing `SoccerEventPagePresentation10868.reader(card)`: the
 * compact scoreboard and state, then the same leaf at full size.
 *
 * The shell draws no card and reads no payload: its owner passes the title,
 * the compact context, the neighbours and the SAME content it draws on the
 * page. It is rendered only while open, so a closed reader adds nothing to the
 * page's markup.
 *
 * MODAL: one local native `<dialog>` opened with `showModal()`. The browser's
 * top layer makes the rest of the page inert (no pointer, no keyboard focus)
 * while it is open; this file touches no ancestor, no shared modal layer and
 * no global history. Escape arrives as the dialog's `cancel`, which is
 * cancelled and turned into the owner's controlled close, as is any `close`
 * the browser makes on its own. Where `showModal` does not exist the dialog is
 * opened by its `open` attribute and Escape closes it (no background
 * isolation there: no current browser lacks `showModal`).
 *
 * While open: the page's own vertical scroll is held (prior `body` overflow
 * kept and restored); the reader's body scrolls inside the dialog, Close stays
 * in the persistent top bar, and content with its own horizontal scroll (the
 * exact-score map) keeps it. No swipe and no key but Escape is handled here.
 *
 * RETURN: a close the reader asked for (Close, Escape, cancel) puts the page
 * back at the scroll it had when the reader opened and focuses the owner's
 * `returnTo()` target with `preventScroll`, after the owner's update has
 * committed. A close the owner made (a new event or phase, the page going)
 * restores no scroll; it focuses `returnTo()` only when focus was lost with the
 * dialog, so a live update never moves focus. Each open focuses Close once.
 */

import { useId, useRef, type ReactNode } from "react";
import { useIsomorphicLayoutEffect } from "./useFrameMeasure";

export const SOCCER_READER_WORDS = {
  close: "Close",
  /** Native StoryStreamPresentation10868 "Open full card", spoken "Open full card: <name>". */
  openCard: "Open full card",
  /** Native HockeyJourneyHistoryAdapter10868.Words.expand. */
  fullChart: "Full chart",
  /** Native SoccerPageInputAdapter10868.Words.storyUnavailable, verbatim. */
  storyUnavailable: "This story isn’t available for this match state. Every original is still in All props.",
  previous: "Previous",
  next: "Next",
} as const;

/** A neighbour the reader can move to, by its name and only on an explicit press. */
export interface SoccerReaderStep {
  name: string;
  go: () => void;
}

export type SoccerReaderEntryKind = "story" | "history";

/**
 * Where focus lands when a reader's own opener did not survive: this match's
 * entry of the same kind, else any reader entry in it; null when none is left.
 * Entries are marked `data-soccer-reader-entry`.
 */
export function soccerReaderEntry(from: Element | null, kind: SoccerReaderEntryKind): HTMLElement | null {
  if (!from || !from.isConnected) return null;
  const match = from.closest("[data-soccer-match]") ?? from;
  return (
    match.querySelector<HTMLElement>(`[data-soccer-reader-entry="${kind}"]:not([disabled])`) ??
    match.querySelector<HTMLElement>("[data-soccer-reader-entry]:not([disabled])")
  );
}

const CONTROL =
  "min-h-11 rounded-md border border-surface-border px-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand";

export default function SoccerMatchReader({
  kind,
  title,
  position = null,
  context,
  previous = null,
  next = null,
  navLabel,
  onClose,
  returnTo,
  children,
}: {
  kind: SoccerReaderEntryKind;
  title: string;
  /** "2 of 4"; null when there is no place to tell. */
  position?: string | null;
  /** The compact match context (names, score, state) above the content. */
  context: ReactNode;
  previous?: SoccerReaderStep | null;
  next?: SoccerReaderStep | null;
  navLabel?: string;
  /** The owner's controlled close: it stops rendering the reader. */
  onClose: () => void;
  /** The element focus returns to, read after the owner's close has committed. */
  returnTo: () => HTMLElement | null;
  children: ReactNode;
}) {
  const titleId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const closing = useRef(false);
  const modal = useRef(false);
  const latest = useRef({ onClose, returnTo });
  useIsomorphicLayoutEffect(() => {
    latest.current = { onClose, returnTo };
  });

  /** Close, Escape, cancel or the browser's own close: once, through the owner. */
  const requestClose = () => {
    if (closing.current) return;
    closing.current = true;
    latest.current.onClose();
  };

  // Open once per mount; never again on a live update.
  useIsomorphicLayoutEffect(() => {
    const el = dialog.current;
    if (!el) return;
    closing.current = false;
    const page = { x: window.scrollX, y: window.scrollY };
    const body = document.body;
    const priorOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    modal.current = false;
    if (typeof el.showModal === "function") {
      try {
        if (!el.open) el.showModal();
        modal.current = true;
      } catch {
        modal.current = false;
      }
    }
    if (!modal.current && !el.hasAttribute("open")) el.setAttribute("open", "");
    closeButton.current?.focus({ preventScroll: true });
    return () => {
      const asked = closing.current;
      // From here on a close event is the shell's own leaving, not a request.
      closing.current = true;
      if (modal.current && el.open && typeof el.close === "function") el.close();
      else el.removeAttribute("open");
      body.style.overflow = priorOverflow;
      queueMicrotask(() => {
        const active = document.activeElement;
        const lost = !active || active === document.body || !active.isConnected;
        if (asked) window.scrollTo(page.x, page.y);
        else if (!lost) return;
        const target = latest.current.returnTo();
        if (target?.isConnected) target.focus({ preventScroll: true });
      });
    };
  }, []);

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      data-soccer-reader={kind}
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClose={requestClose}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !modal.current) {
          event.preventDefault();
          requestClose();
        }
      }}
      // Phone: the whole viewport. Wider: a centred panel, so a wide page never opens a phone-sized reader.
      // The margins are important: the dialog sits inside its owner's `space-y-*` stack, whose sibling margin must not move it.
      className="fixed inset-0 z-[100] !m-0 hidden h-[100dvh] max-h-none w-full max-w-none flex-col overflow-hidden border-0 bg-surface-card p-0 text-text-primary backdrop:bg-surface-deep/60 open:flex sm:!m-auto sm:h-fit sm:max-h-[85dvh] sm:max-w-2xl sm:rounded-xl sm:border sm:border-surface-border sm:shadow-lg"
    >
      {/* The persistent top bar: title, place and Close wrap at enlarged text; Close is never scrolled away. */}
      <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 border-b border-surface-border p-[16px]">
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="break-words text-lg font-bold">
            {title}
          </h2>
          {position && (
            <p className="text-sm text-text-secondary" data-soccer-reader-position="">
              {position}
            </p>
          )}
        </div>
        <button ref={closeButton} type="button" onClick={requestClose} className={`${CONTROL} shrink-0`}>
          {SOCCER_READER_WORDS.close}
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-[16px]" data-soccer-reader-body="">
        {context}
        {children}
        {previous && next && (
          <nav aria-label={navLabel} className="flex flex-wrap justify-between gap-2 border-t border-surface-border pt-[12px]">
            <button type="button" onClick={previous.go} className={CONTROL}>
              {SOCCER_READER_WORDS.previous}
              <span className="font-normal text-text-secondary">{` · ${previous.name}`}</span>
            </button>
            <button type="button" onClick={next.go} className={CONTROL}>
              {SOCCER_READER_WORDS.next}
              <span className="font-normal text-text-secondary">{` · ${next.name}`}</span>
            </button>
          </nav>
        )}
      </div>
    </dialog>
  );
}
