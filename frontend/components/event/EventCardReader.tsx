"use client";

/**
 * #9483 — a game-story card opened full size on web (design freeze v328; the
 * phone's `NFLCardReader9483`).
 *
 * - A compact match and chance line on top, so the reader never loses the game.
 * - One card at a time with the neighbour peeking, a count, dots and arrows;
 *   swipe and the arrow keys move too. Each card scrolls on its own.
 * - Exact details for a selected line, over the card.
 * - Back (or Escape) returns to the page, focused on the card it was opened
 *   from, not the last one read.
 *
 * HELD WHILE READING: the match line, every card and the rows Details show stay
 * as they were when the card opened until the reader presses Refresh, which
 * replaces all three together (`readerReducer`). One exception: a number that
 * stops being current leaves the held card too (a live projection past its
 * capture gap, a pregame price past its observation bound).
 */

import { useEffect, useReducer, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type Ref } from "react";
import { formatProbability } from "@/lib/api";
import { propVerdictLabel } from "@/lib/propGrade";
import { formatSourceStamp } from "@/lib/sourceAge";
import { sourceLabel } from "@/lib/sourceLabels";
import {
  displayedCards,
  formatPoints,
  lineLead,
  lineLeadLabel,
  openReader,
  readerHasUpdate,
  readerReducer,
  targetLabel,
  type MilestoneBasis,
  type NflEventCard,
  type NflPropRow,
  type ReaderHeader,
  type ReaderState,
} from "@/lib/nflEventCardDeck";
import type { OptionDetail } from "@/lib/nbaEventCards";
import { EventCardView, type CardSelection, type CardTeams } from "./NFLEventCards";

/** Re-read the clock each minute so a held number past its validity leaves. */
const TICK_MS = 60_000;
const SWIPE_PX = 40;

export default function EventCardReader({
  openCardId,
  liveCards,
  liveHeader,
  liveRows,
  teams,
  selection,
  onSelect,
  onVisibleChange,
  onClose,
}: {
  openCardId: string;
  liveCards: NflEventCard[];
  liveHeader: ReaderHeader;
  liveRows: Record<string, NflPropRow>;
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  /** Reports the card on screen (for the page's own bookkeeping). */
  onVisibleChange?: (cardId: string | null) => void;
  /** Called with the reader's final state, so the page can choose the return target. */
  onClose: (state: ReaderState) => void;
}) {
  const [state, dispatch] = useReducer(readerReducer, undefined, () =>
    openReader({ cardId: openCardId, live: liveCards, liveHeader, liveRows }),
  );
  const [nowMs, setNowMs] = useState(() => Date.now());
  const dialogRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const detailsDoneRef = useRef<HTMLButtonElement>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const swipe = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    backRef.current?.focus();
  }, []);

  useEffect(() => {
    onVisibleChange?.(state.visible);
  }, [state.visible, onVisibleChange]);

  useEffect(() => {
    if (state.detailsRowId) detailsDoneRef.current?.focus();
  }, [state.detailsRowId]);

  const cards = displayedCards(state.held, liveCards, nowMs);
  const position = Math.max(0, cards.findIndex((c) => c.id === state.visible));
  const hasUpdate = readerHasUpdate({
    held: state.held,
    heldHeader: state.heldHeader,
    heldRows: state.heldRows,
    live: liveCards,
    liveHeader,
    liveRows,
    nowMs,
  });
  const close = () => onCloseRef.current(stateRef.current);
  const step = (delta: number) => dispatch({ type: "step", delta, nowMs, live: liveCards });

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (state.detailsRowId) dispatch({ type: "details", rowId: null });
      else close();
      return;
    }
    if (e.key === "Tab") {
      // Keep focus inside the reader while it is open.
      const focusables = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.closest("[inert]") && !el.closest('[aria-hidden="true"]'));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
      return;
    }
    if (state.detailsRowId) return;
    const target = e.target as HTMLElement;
    if (target.closest?.("[data-line-controls]")) return;
    if (e.key === "ArrowRight") step(1);
    if (e.key === "ArrowLeft") step(-1);
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    swipe.current = { x: e.clientX, y: e.clientY };
  };
  const onPointerUp = (e: ReactPointerEvent) => {
    const start = swipe.current;
    swipe.current = null;
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    // Horizontal only, so a vertical read never turns the card.
    if (Math.abs(dx) >= SWIPE_PX && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
  };

  // A prop line's original is in the held rows; an NBA ladder line's original
  // is frozen inside its held card. Either way Details read what was held.
  const detailsRow: NflPropRow | OptionDetail | undefined = state.detailsRowId
    ? (state.heldRows[state.detailsRowId] ??
      state.held
        .flatMap((c) => (c.kind === "ladder" ? c.points : []))
        .find((p) => p.optionKey === state.detailsRowId)?.detail)
    : undefined;

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Game story cards"
      onKeyDown={onKeyDown}
      className="fixed inset-0 z-[110] bg-surface-card flex flex-col pb-[env(safe-area-inset-bottom,0px)]"
      data-testid="event-card-reader"
    >
      <div className="px-4 pt-2 pb-2 border-b border-surface-border">
        <div className="flex items-center justify-between gap-2">
          <button
            ref={backRef}
            type="button"
            onClick={close}
            aria-label="Back to the game"
            className="min-h-11 px-2 -ml-2 rounded-md text-sm font-semibold text-text-primary hover:bg-surface-elevated"
          >
            <span aria-hidden="true">‹ </span>Back
          </button>
          {hasUpdate && (
            <button
              type="button"
              onClick={() => dispatch({ type: "refresh", live: liveCards, liveHeader, liveRows })}
              aria-label="New game update. Refresh the cards"
              className="min-h-11 px-3 rounded-md text-sm font-bold text-accent-brand hover:bg-surface-elevated"
              data-testid="reader-refresh"
            >
              Refresh
            </button>
          )}
        </div>
        <p className="text-sm font-bold text-text-primary" data-testid="reader-match">
          {state.heldHeader.match}
        </p>
        {state.heldHeader.chances && <p className="text-xs text-text-secondary">{state.heldHeader.chances}</p>}
      </div>

      {cards.length === 0 ? (
        <p className="flex-1 flex items-center justify-center text-sm text-text-secondary" data-testid="reader-empty">
          No game stories right now
        </p>
      ) : (
        <>
          <div
            className="relative flex-1 min-h-0 overflow-hidden"
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
            onPointerCancel={() => (swipe.current = null)}
            style={{ touchAction: "pan-y" }}
          >
            <div
              className="flex h-full gap-3 px-[14px] transition-transform duration-300 motion-reduce:transition-none"
              style={{ transform: `translateX(calc(${-position} * (100% - 60px)))` }}
            >
              {cards.map((card) => {
                const active = card.id === state.visible;
                return (
                  <div
                    key={card.id}
                    className="shrink-0 h-full overflow-y-auto py-4"
                    style={{ width: "calc(100% - 44px)" }}
                    aria-hidden={active ? undefined : true}
                    {...((active ? {} : { inert: "" }) as Record<string, string>)}
                    data-card-id={card.id}
                    data-active={active || undefined}
                  >
                    <div className="mx-auto max-w-[720px] bg-surface-card rounded-card border border-surface-border p-4">
                      <EventCardView
                        card={card}
                        teams={teams}
                        selection={selection}
                        onSelect={onSelect}
                        onDetails={(rowId) => dispatch({ type: "details", rowId })}
                        expanded
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            {detailsRow !== undefined || state.detailsRowId ? (
              <LineDetails
                row={detailsRow}
                lead={state.detailsRowId ? lineLead(cards, state.detailsRowId) : null}
                doneRef={detailsDoneRef}
                onDone={() => dispatch({ type: "details", rowId: null })}
              />
            ) : null}
          </div>
          <div className="flex items-center gap-1 px-3 py-2 border-t border-surface-border">
            <button
              type="button"
              onClick={() => step(-1)}
              disabled={position === 0}
              aria-label="Previous card"
              className="w-11 h-11 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted"
            >
              <span aria-hidden="true">‹</span>
            </button>
            <div className="flex-1 flex flex-col items-center gap-1">
              <span className="text-sm font-semibold tabular-nums text-text-secondary" data-testid="reader-count">
                {position + 1} of {cards.length}
              </span>
              <span className="flex gap-1.5" aria-hidden="true">
                {cards.map((card) => (
                  <span
                    key={card.id}
                    className={`h-[5px] rounded-full ${card.id === state.visible ? "w-[18px] bg-text-primary" : "w-[5px] bg-surface-border"}`}
                  />
                ))}
              </span>
            </div>
            <button
              type="button"
              onClick={() => step(1)}
              disabled={position >= cards.length - 1}
              aria-label="Next card"
              className="w-11 h-11 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted"
            >
              <span aria-hidden="true">›</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * The exact original row behind a line: what the venue quoted and when, the
 * pregame mark, and the server's grade — each named for what it is.
 *
 * Hierarchy (v335): the selected side's pregame chance leads — exactly the
 * number its card prints for the line (`lineLead`), never one re-derived from
 * the row — then the final and its grade as a separate Result, then the dated
 * quote and its venue as secondary, so a later quote never reads as the
 * earlier probability. No lead, no headline: nothing is promoted into it.
 */
export function LineDetails({
  row,
  lead = null,
  onDone,
  doneRef,
}: {
  row: NflPropRow | OptionDetail | undefined;
  lead?: { chance: number; basis: MilestoneBasis } | null;
  onDone: () => void;
  doneRef?: Ref<HTMLButtonElement>;
}) {
  if (row && "detail" in row) return <OptionDetails row={row} onDone={onDone} doneRef={doneRef} />;
  const venue = row ? sourceLabel(row.source) : null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Line details"
      className="absolute inset-0 z-10 bg-surface-card overflow-y-auto"
      data-testid="line-details"
    >
      <div className="max-w-[720px] mx-auto p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-text-primary">Line details</h3>
          <button
            ref={doneRef}
            type="button"
            onClick={onDone}
            className="min-h-11 px-3 rounded-md text-sm font-semibold text-accent-brand hover:bg-surface-elevated"
          >
            Done
          </button>
        </div>
        {row ? (
          <>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <dt className="col-span-2 font-semibold text-text-primary">{row.outcome_name}</dt>
              <dt className="text-text-secondary">Market</dt>
              <dd className="text-text-primary">{row.market_name}</dd>
              {row.threshold !== null && (
                <>
                  <dt className="text-text-secondary">Line</dt>
                  <dd className="text-text-primary">{targetLabel(row.threshold)}</dd>
                </>
              )}
            </dl>
            {lead && (
              <div data-testid="line-details-pregame">
                <div className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{lineLeadLabel(lead.basis)}</div>
                <div className="text-3xl font-bold text-text-primary tabular-nums">{formatProbability(lead.chance)}</div>
              </div>
            )}
            {(typeof row.actual === "number" || typeof row.hit === "boolean") && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm" data-testid="line-details-result">
                <dt className="col-span-2 font-semibold text-text-primary">Result</dt>
                {typeof row.actual === "number" && (
                  <>
                    <dt className="text-text-secondary">Final</dt>
                    <dd className="text-text-primary tabular-nums">{formatPoints(row.actual)}</dd>
                  </>
                )}
                {typeof row.hit === "boolean" && (
                  <>
                    <dt className="text-text-secondary">Graded</dt>
                    <dd className="text-text-primary">{propVerdictLabel(row.hit)}</dd>
                  </>
                )}
              </dl>
            )}
            {(typeof row.over_probability === "number" || venue) && (
              <dl
                className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs text-text-secondary border-t border-surface-border pt-3"
                data-testid="line-details-quote"
              >
                <dt className="col-span-2 font-semibold">Quote &amp; source</dt>
                {typeof row.over_probability === "number" && (
                  <>
                    <dt>Last quote</dt>
                    <dd className="tabular-nums">{formatProbability(row.over_probability)}</dd>
                    <dt>Quoted</dt>
                    <dd>{formatSourceStamp(row.observed_at) ?? "Time unknown"}</dd>
                  </>
                )}
                {venue && (
                  <>
                    <dt>Venue</dt>
                    <dd>{venue}</dd>
                  </>
                )}
              </dl>
            )}
          </>
        ) : (
          <p className="text-sm text-text-secondary">This line is no longer offered.</p>
        )}
      </div>
    </div>
  );
}

/** #9483 NBA — the served option behind a ladder line, each number named for what it is. */
function OptionDetails({ row, onDone, doneRef }: { row: OptionDetail; onDone: () => void; doneRef?: Ref<HTMLButtonElement> }) {
  const venue = row.source ? sourceLabel(row.source) : null;
  return (
    <div role="dialog" aria-modal="true" aria-label="Line details" className="absolute inset-0 z-10 bg-surface-card overflow-y-auto" data-testid="line-details">
      <div className="max-w-[720px] mx-auto p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-text-primary">Line details</h3>
          <button ref={doneRef} type="button" onClick={onDone} className="min-h-11 px-3 rounded-md text-sm font-semibold text-accent-brand hover:bg-surface-elevated">
            Done
          </button>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="col-span-2 font-semibold text-text-primary">{row.label}</dt>
          <dt className="text-text-secondary">Market</dt>
          <dd className="text-text-primary">{row.marketName}</dd>
          <dt className="text-text-secondary">Pregame baseline</dt>
          <dd className="text-text-primary tabular-nums">
            {row.baseline !== null ? formatProbability(row.baseline) : "Unavailable"}
            {row.baselineObservedAt ? ` · ${formatSourceStamp(row.baselineObservedAt)}` : ""}
          </dd>
          {row.quoted !== null && (
            <>
              <dt className="text-text-secondary">Last quote</dt>
              <dd className="text-text-primary tabular-nums">{formatProbability(row.quoted)}</dd>
              <dt className="text-text-secondary">Quoted</dt>
              <dd className="text-text-primary">{formatSourceStamp(row.observedAt) ?? "Time unknown"}</dd>
            </>
          )}
          {venue && (
            <>
              <dt className="text-text-secondary">Venue</dt>
              <dd className="text-text-primary">{venue}</dd>
            </>
          )}
          {row.result !== null && (
            <>
              <dt className="col-span-2 pt-2 font-semibold text-text-primary">Result</dt>
              <dt className="text-text-secondary">Graded</dt>
              <dd className="text-text-primary">{propVerdictLabel(row.result)}</dd>
            </>
          )}
        </dl>
      </div>
    </div>
  );
}
