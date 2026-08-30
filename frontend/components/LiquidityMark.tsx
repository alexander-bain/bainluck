"use client";

import React from "react";

import {
  isMarked,
  liquidityReveal,
  readLiquidity,
  type LiquidityFacts,
} from "@/lib/liquidity";

/**
 * ONE MARK, EVERY SURFACE (UX-P157 — Alex's illiquidity ruling, #2256/#2257).
 *
 * *"A really clean, universal signal for illiquidity."* Universal is the hard
 * word in that sentence, and it is why this file sits in `components/` rather
 * than in `components/tournament/`: the boards, the bracket grid, the match
 * slate and the questions section each grew their own freshness treatment, and
 * a fifth surface-specific glyph is how a signal stops being a signal. There is
 * exactly one of these, and every surface renders the same twelve pixels.
 *
 * ═══ THE GLYPH, AND WHY IT IS A DRAINING CIRCLE ═══
 *
 * A ring that empties as the market thins:
 *
 *     traded / unknown   (nothing)     no mark at all
 *     thin               ◐             ring, filled to half
 *     barely             ○             ring, empty
 *
 * Three properties the four surfaces jointly demand, and this is the only
 * shape found that has all three:
 *
 *   1. **It survives a grid cell.** The binding constraint is the US Open
 *      bracket at phone width, where a value track is 46px and already holds a
 *      percentage and a spark bar. Anything with text in it — a chip, an age,
 *      a word — cannot go there, which rules out the three `FreshnessVariant`
 *      treatments UX-P154 shipped one section over.
 *   2. **It grades without a legend.** Emptier is thinner. Alex asked for at
 *      least two levels; a reader who never opens the reveal still gets the
 *      ordering right, because "less filled" needs no key to decode.
 *   3. **It does not collide with the freshness dot.** That one is a SOLID
 *      dot and this one is a HOLLOW ring, which matters because the two facts
 *      are genuinely different: a number can be minutes old and still come off
 *      a book nobody will trade at, and Q428's whole residual is that case.
 *
 * Muted grey, and deliberately NOT amber. Amber is `accent-warning`, which the
 * quiet-freshness treatment already owns; painting a second, unrelated caution
 * in the same colour would teach the reader that the two mean one thing.
 *
 * ═══ THE REVEAL, AND THE NON-HOVER HALF ═══
 *
 * Alex's constraint: mouse-over reveals precisely when the probability was last
 * updated, and *native needs a non-hover equivalent designed at the same time,
 * not later*. A phone has no hover, and neither does a keyboard.
 *
 * So the reveal exists three ways and says the same sentence in all three
 * (`liquidityReveal` returns one string precisely so it cannot drift):
 *
 *   • `title=` — the mouse.
 *   • the accessible name on a real `<button>` — the screen reader and the
 *     keyboard. It is a button and not a `<span>` because a tooltip nobody can
 *     focus is a tooltip half the readers do not have.
 *   • `onReveal` — the tap. The surface owns the panel (a grid cell cannot host
 *     one; a card can), so this component owns the affordance and hands the
 *     sentence up rather than guessing where it should be drawn.
 *
 * The native mirror is `ios/Bain Luck/Bain Luck/Components/LiquidityMarkView.swift`,
 * which draws the same two states and uses a long-press for the third path.
 * Keep them in step; the pair is documented at the top of that file the way
 * `SignalBarsView` documents its own.
 */

export type LiquidityMarkSize = "sm" | "md";

/** 8px inside a grid cell, 10px beside a card number. Nothing else. */
const PX: Record<LiquidityMarkSize, number> = { sm: 8, md: 10 };

export function LiquidityMark({
  facts,
  observedAt,
  size = "md",
  onReveal,
  decorative = false,
  className = "",
}: {
  /** The payload row itself — cell, board row, match side or prop card. */
  facts: LiquidityFacts;
  /** Last time a probability for this question reached us. */
  observedAt?: string | null;
  size?: LiquidityMarkSize;
  /**
   * Tap/click handler for surfaces that can host a panel. When omitted the
   * mark is still focusable and still announces, it just has nothing to open —
   * which is the right behaviour in a 46px grid cell.
   */
  onReveal?: (sentence: string) => void;
  /**
   * Draw the glyph and nothing else — no focus stop, no announcement.
   *
   * For the ONE case where the surface already carries the sentence: a grid
   * cell whose own `title` and `sr-only` text include the reveal (see
   * `gridCellExplanation`). Without this the 336-cell bracket would grow up to
   * 336 extra tab stops, each announcing a sentence the cell just read out —
   * and a focusable control inside an `aria-hidden` wrapper is a defect in its
   * own right, not a trade-off.
   */
  decorative?: boolean;
  className?: string;
}) {
  const level = readLiquidity(facts.liquidity);
  if (!isMarked(level)) return null;
  const marked = level as "thin" | "barely";

  const sentence = liquidityReveal(facts, observedAt);
  if (sentence === null) return null;

  const px = PX[size];
  const Tag = decorative ? "span" : "button";
  // A 24-unit box for both sizes so the stroke weight and the half-fill scale
  // together — a hand-tuned 8px path and a hand-tuned 10px path would be two
  // glyphs that happen to look alike, which is the thing this file exists to
  // prevent.
  const r = 9;

  return (
    <Tag
      {...(decorative
        ? { "aria-hidden": true as const }
        : { type: "button" as const, "aria-label": sentence })}
      // `title` is the mouse path, and it is on BOTH forms: a reader with a
      // mouse and no screen reader is the one this signal is mostly for.
      title={sentence}
      data-testid="liquidity-mark"
      data-level={marked}
      data-size={size}
      onClick={
        onReveal && !decorative
          ? (event: React.MouseEvent) => {
              // The mark sits inside cards and rows that are themselves links.
              // Without this, asking why a number is thin navigates away from
              // the number.
              event.preventDefault();
              event.stopPropagation();
              onReveal(sentence);
            }
          : undefined
      }
      className={`inline-flex shrink-0 items-center justify-center align-middle text-text-muted ${
        onReveal ? "cursor-help" : "cursor-default"
      } ${className}`}
      style={{ width: px, height: px }}
    >
      <svg
        viewBox="0 0 24 24"
        width={px}
        height={px}
        aria-hidden="true"
        focusable="false"
      >
        {/* The ring. Always drawn, at both levels — it is the constant that
            makes the fill readable as a QUANTITY rather than as two unrelated
            icons. */}
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        />
        {marked === "thin" && (
          // The bottom half, as a filled semicircle. Bottom rather than top so
          // it reads as a level in a container — the same intuition as a
          // battery, and the reason "emptier is thinner" needs no legend.
          <path
            d={`M ${12 - r} 12 A ${r} ${r} 0 0 0 ${12 + r} 12 Z`}
            fill="currentColor"
          />
        )}
      </svg>
    </Tag>
  );
}

export default LiquidityMark;
