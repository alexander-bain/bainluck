"use client";

/**
 * UX-P234 — THE ONE PIN AFFORDANCE (TOP-PRODUCT-DEFECTS items 15 + 16).
 *
 * Alex named the two halves separately and they are one defect:
 *
 *   15. the futures DETAIL page's pin was the bare word "Pin", inside a container
 *       whose own comment called it *"Legacy hero kept for share/pin actions"* —
 *       leftover scaffolding that shipped.
 *   16. on the web DISCOVER feed there was no indication a card could be pinned.
 *
 * ⚠️ AND ITEM 16'S PREMISE NEEDED A CORRECTION, MEASURED NOT ASSUMED. It reads
 * *"the capability exists and is invisible."* On the Discover card the capability
 * **did not exist at all**: `components/discover/FuturesCard.tsx` never referenced
 * pinning, and `grep` finds no pin state anywhere under `components/discover/`.
 * What existed was the hook (`usePinnedFutures`) plus a real, working pin on
 * `components/FuturesCard.tsx` — the card used by search, my-stuff and preferences.
 * So Discover was not hiding an affordance; it was the one surface that never got
 * one, while every neighbouring surface had it. That is why Alex expected it.
 *
 * ═══ WHY A COMPONENT RATHER THAN A FOURTH BUTTON ═══
 *
 * `PinIcon` was defined **three times**, byte-for-byte, in `FuturesCard.tsx`,
 * `EventCard.tsx` and `app/events/[id]/page.tsx` — and the detail page, which had
 * no icon at all, was drifting away from all three. "One affordance, used in both
 * places" is Alex's wording and it is a design instruction, not a refactor: a pin
 * has to look like a pin everywhere or the reader has to learn it twice.
 *
 * The title/aria wording, the filled-vs-outline states and the max-pins treatment
 * are lifted verbatim from `components/FuturesCard.tsx`, which is the copy that was
 * already live on three surfaces — so this component changes how the DETAIL page
 * and DISCOVER look, and leaves the surfaces that were already right alone.
 */

import { cn } from "@/lib/utils";

/**
 * THE PIN, AS ONE BOOKMARK SHAPE (#12616). Both states draw this path; only the treatment differs.
 *
 * Replaces the #7165 pushpin silhouette per Alex's Saturday Nov 14 ruling (#12616: "website game
 * card parity with the bookmark pin", matching Decision 178-B / #11934 onboarding pass 5 on iOS).
 * Unpinned (`filled={false}`) strokes this silhouette at `strokeWidth="1.5"` with `fill="none"`;
 * pinned (`filled={true}`) fills the exact same `PIN_PATH` with `currentColor` so both states
 * share one silhouette across every website surface (`EventCard`, `EventCard183A`, `FuturesCard`,
 * Discover `ActionBar`, event detail, and futures detail).
 */
export const PIN_PATH =
  "M6 3.75h12A1.25 1.25 0 0 1 19.25 5v15.25l-7.25-4.2-7.25 4.2V5A1.25 1.25 0 0 1 6 3.75Z";

export function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d={PIN_PATH} />
      </svg>
    );
  }
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path strokeLinejoin="round" d={PIN_PATH} />
    </svg>
  );
}

/** What a reader is told, in every state. One table so the states cannot drift. */
export function pinTitle(pinned: boolean, disabled: boolean): string {
  if (pinned) return "Unpin";
  return disabled ? "Max 6 pins" : "Pin";
}

export function pinAriaLabel(pinned: boolean, noun: string): string {
  return `${pinned ? "Unpin" : "Pin"} ${noun}`;
}

/** The two icon sizes, named so a guard can assert the icon is actually drawn. */
export const PIN_ICON_SIZE = { labelled: "w-4 h-4", icon: "w-3.5 h-3.5" } as const;

/**
 * What a pin click does, as a pure function — extracted ONLY so it can be tested.
 *
 * There is no `@testing-library/react` in this project; component guards are
 * `renderToStaticMarkup`, which cannot dispatch a click. A source-substring guard
 * for the swallow (`expect(SHARED).toContain("stopPropagation")`) is satisfied by
 * the PROP NAME appearing anywhere in the file, so deleting the actual
 * `e.preventDefault()` / `e.stopPropagation()` calls left it green — that mutant
 * survived the first battery. This makes the behaviour assertable instead.
 */
export function pinClickAction(opts: { disabled: boolean; swallow: boolean }): {
  preventDefault: boolean;
  stopPropagation: boolean;
  toggles: boolean;
} {
  return {
    preventDefault: opts.swallow,
    stopPropagation: opts.swallow,
    toggles: !opts.disabled,
  };
}

interface PinButtonProps {
  pinned: boolean;
  onToggle: () => void;
  /** At the 6-pin ceiling. An already-pinned item stays clickable so it can be UNpinned. */
  atMax?: boolean;
  /** Goes into the aria-label: "Pin market", "Pin event". */
  noun?: string;
  /** `icon` for a dense card corner; `labelled` where there is room for the word. */
  variant?: "icon" | "labelled";
  className?: string;
  /** Discover cards live inside a swipe handler — see the note on the click guard. */
  stopPropagation?: boolean;
}

export function PinButton({
  pinned,
  onToggle,
  atMax = false,
  noun = "market",
  variant = "icon",
  className,
  stopPropagation = false,
}: PinButtonProps) {
  const disabled = atMax && !pinned;

  return (
    <button
      type="button"
      data-testid="pin-button"
      data-pinned={pinned ? "true" : "false"}
      onClick={(e) => {
        // A Discover card is wrapped in `useSwipe` and, in some variants, in a
        // <Link>. Without this a pin click also navigates to the detail page —
        // the pin appears to do nothing because the surface it changed is gone.
        const action = pinClickAction({ disabled, swallow: stopPropagation });
        if (action.preventDefault) e.preventDefault();
        if (action.stopPropagation) e.stopPropagation();
        if (action.toggles) onToggle();
      }}
      disabled={disabled}
      aria-pressed={pinned}
      title={pinTitle(pinned, disabled)}
      aria-label={pinAriaLabel(pinned, noun)}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg transition-colors",
        variant === "labelled" ? "px-3 py-1.5 text-sm font-medium" : "p-1",
        pinned
          ? variant === "labelled"
            ? "bg-amber-500/10 text-amber-600"
            : "text-accent-warning"
          : variant === "labelled"
            ? "bg-surface-elevated text-text-secondary hover:text-text-primary"
            : "text-text-muted hover:text-text-secondary hover:bg-surface-elevated",
        disabled && "cursor-not-allowed opacity-30",
        className,
      )}
    >
      <PinIcon filled={pinned} className={PIN_ICON_SIZE[variant]} />
      {variant === "labelled" && <span>{pinned ? "Pinned" : "Pin"}</span>}
    </button>
  );
}
