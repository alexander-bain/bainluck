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

/**
 * ═══ WHY THIS FILE DOES NOT IMPORT `cn` (LAT-P211) ═══
 *
 * `cn` is `twMerge(clsx(...))`, and `tailwind-merge` is 26,985 raw / 7,398 brotli.
 * This component was the ONLY module in the Discover landing page's eager import
 * graph that reached `lib/utils`, so `/` downloaded a Tailwind class-conflict
 * resolver for one button — measured, not assumed: `lib/utils.ts` had exactly one
 * eager importer on `/`, this file, via `components/discover/shared.tsx`.
 *
 * The resolver was doing real work: the Discover caller passed
 * `className="text-text-muted hover:text-text-secondary"` and relied on `twMerge`
 * to drop this component's own `text-text-secondary hover:text-text-primary` (and,
 * when pinned, its `text-amber-600`). LAT-P201 counted exactly those two
 * divergences here.
 *
 * So the override is expressed as a `tone` prop instead of as a class conflict, and
 * the colour classes are a total lookup table — the component can no longer emit two
 * classes that fight, so nothing has to resolve them. **There is deliberately no
 * `className` prop:** re-adding one would let a caller reintroduce the conflict that
 * `twMerge` used to absorb, silently, and this file no longer has a resolver. Add a
 * `tone` entry instead.
 */

export function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z" />
      </svg>
    );
  }
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
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
 * Every colour this button can wear, keyed by `${tone}-${variant}-${pinned}`.
 *
 * A total table rather than nested ternaries plus a caller override, so that the
 * class list can never contain two classes from the same Tailwind group. That is
 * what makes `twMerge` unnecessary here — see the note at the top of the file.
 *
 * `muted` reproduces, exactly, what the Discover ActionBar rendered when it passed
 * `className="text-text-muted hover:text-text-secondary"` through `twMerge`: the
 * background still changes when pinned, the text colour does not.
 */
export const PIN_TONE = {
  "default-labelled-true": "bg-amber-500/10 text-amber-600",
  "default-labelled-false": "bg-surface-elevated text-text-secondary hover:text-text-primary",
  "default-icon-true": "text-accent-warning",
  "default-icon-false": "text-text-muted hover:text-text-secondary hover:bg-surface-elevated",
  "muted-labelled-true": "bg-amber-500/10 text-text-muted hover:text-text-secondary",
  "muted-labelled-false": "bg-surface-elevated text-text-muted hover:text-text-secondary",
  "muted-icon-true": "text-text-muted hover:text-text-secondary",
  "muted-icon-false": "text-text-muted hover:text-text-secondary hover:bg-surface-elevated",
} as const;

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
  /**
   * `muted` for a Discover ActionBar, where the pin sits beside share/dismiss and
   * must not shout. Replaces the old `className` override — see the file header.
   */
  tone?: "default" | "muted";
  /** Discover cards live inside a swipe handler — see the note on the click guard. */
  stopPropagation?: boolean;
}

export function PinButton({
  pinned,
  onToggle,
  atMax = false,
  noun = "market",
  variant = "icon",
  tone = "default",
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
      className={[
        "inline-flex items-center gap-1.5 rounded-lg transition-colors",
        variant === "labelled" ? "px-3 py-1.5 text-sm font-medium" : "p-1",
        PIN_TONE[`${tone}-${variant}-${pinned}`],
        disabled ? "cursor-not-allowed opacity-30" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <PinIcon filled={pinned} className={PIN_ICON_SIZE[variant]} />
      {variant === "labelled" && <span>{pinned ? "Pinned" : "Pin"}</span>}
    </button>
  );
}
