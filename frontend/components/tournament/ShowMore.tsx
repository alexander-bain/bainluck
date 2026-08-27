"use client";

import React from "react";

/**
 * The one expander (UX-P137, Alex's rulings 5 and 9).
 *
 * "EVERY long list, every view: show 3-5, then an expand/see-more control.
 * Standing rule now, not per-view."
 *
 * So it stops being per-view markup. This is lifted verbatim from the shape
 * `TournamentBoard` already shipped — same words, same border, same weight —
 * and every other list on the hub now renders THIS rather than its own
 * lookalike. A page that words the same affordance four ways teaches the
 * reader that some of them do something else.
 *
 * The count in the label is load-bearing, not decoration: `Show all 44` is the
 * only thing on a collapsed list that says how long the list is. That is the
 * whole complaint the ruling comes from — a list with no floor. `Show more`
 * would satisfy the letter of "an expand control" and lose the point.
 */
export default function ShowMore({
  expanded,
  total,
  onToggle,
  /** Border above, for a control sitting inside a bordered card. */
  bordered = true,
  label,
}: {
  expanded: boolean;
  /** The FULL length of the list, not the hidden remainder. */
  total: number;
  onToggle: () => void;
  bordered?: boolean;
  /** Overrides the collapsed label where "all" reads wrong (e.g. a picker). */
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={`w-full py-3 text-[13.5px] font-semibold text-text-primary ${
        bordered ? "border-t border-surface-border" : ""
      }`}
      data-testid="show-more"
      data-expanded={expanded ? "true" : "false"}
      data-total={total}
    >
      {expanded ? "Show fewer" : (label ?? `Show all ${total}`)}
    </button>
  );
}

/**
 * How many rows a collapsed list shows before the expander.
 *
 * Five, not three, everywhere except the championship board — the board is
 * pinned to three because the chart draws three lines and a list showing five
 * beside a chart drawing three invites the reader to hunt for two missing
 * lines (`COLLAPSED_ROW_COUNT`, and the reason is written down there).
 */
export const COLLAPSED_LIST_COUNT = 5;
