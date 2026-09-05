"use client";

import React from "react";

/**
 * The Men's / Women's pill strip.
 *
 * Alex's mock verdict at UX-P132, ruling 1: "take direction A's toggle
 * EVERYWHERE, and never two stacked gender lists." One toggle flips the slate,
 * the chart and the contender list together, so the page shows one draw at a
 * time and the reader never scrolls one draw to reach the other.
 *
 * ═══ WHY IT IS A COMPONENT AS OF UX-P142 ═══
 *
 * Alex, on his phone, 2026-08-27: **"the Men's/Women's pills sit too close to
 * the line above."** They did. The strip carried `pb-3` and no top padding at
 * all, so a 30px pill was flush against the tab row's 1px bottom border and
 * read as part of the tab chrome rather than as its own control.
 *
 * The fix is one class. It lives in a component rather than inline in
 * `page.tsx` because the page is a client component with three GA4 hooks and a
 * fetch, and the jest gate could not reach it: there was no test anywhere in
 * the repo that rendered these pills, so the spacing had no guard and neither
 * would the next spacing ruling. A layout fix nothing can assert is a layout
 * fix that comes back.
 */

export interface DrawOption {
  id: string;
  label: string;
}

export const DRAWS: DrawOption[] = [
  { id: "mens-singles", label: "Men's" },
  { id: "womens-singles", label: "Women's" },
];

/**
 * The draw to open on when NOTHING is being played (live/077 item 2).
 *
 * The hub used to open on this unconditionally, which is the defect: on
 * 2026-09-05 both in-progress matches were women's and a phone landing mid-
 * session was shown five men's rows and no sign the live ones existed. The
 * opening draw is `defaultDraw`'s answer now, and this is only what it falls
 * back to between sessions — a tournament with no match on court has no draw
 * to prefer, and SOME tab has to be pressed.
 *
 * It lives here, beside `DRAWS`, for the reason the whole strip does: a route
 * file may not carry named exports (Next's generated page types fail the
 * typecheck gate on them), so the page cannot declare its own default.
 */
export const OPENING_DRAW_FALLBACK = DRAWS[0].id;

/**
 * Symmetric padding, and the same 12px the tab row uses under its labels, so
 * the two strips read as one rhythm instead of one strip crowding the other.
 * Exported so a guard can assert the top padding EXISTS rather than asserting
 * a whole class string, which would fail on any unrelated Tailwind edit.
 */
export const DRAW_TOGGLE_PADDING = "px-4 pb-3 pt-3";

export default function DrawToggle({
  draw,
  onSelect,
  draws = DRAWS,
}: {
  draw: string;
  onSelect: (id: string) => void;
  draws?: DrawOption[];
}) {
  return (
    <div
      className={`flex gap-1.5 border-b border-surface-border bg-surface-card ${DRAW_TOGGLE_PADDING}`}
      role="group"
      aria-label="Draw"
      data-testid="draw-toggle"
    >
      {draws.map((entry) => (
        <button
          key={entry.id}
          type="button"
          aria-pressed={draw === entry.id}
          onClick={() => onSelect(entry.id)}
          data-testid="draw-pill"
          data-draw={entry.id}
          data-active={draw === entry.id ? "true" : "false"}
          className={`rounded-full px-3.5 py-1.5 text-[13px] font-semibold ${
            draw === entry.id
              ? "bg-text-primary text-text-inverse"
              : "bg-surface-elevated text-text-secondary"
          }`}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );
}
