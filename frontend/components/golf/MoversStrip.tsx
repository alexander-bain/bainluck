"use client";

import { formatProbability } from "@/lib/api";
// UX-P274: the strip renders a MOVEMENT, and UX-P048 is the one place a
// movement crosses from a wire fraction into points. See the note in the map
// below for what this call site used to do instead.
import { formatMovementPoints, movementPoints } from "@/lib/probabilityDisplay";
import type { GolfMover } from "@/lib/types";

/**
 * `/golf` — "Biggest Movers (24h)".
 *
 * Lifted out of `app/categories/golf/page.tsx` by UX-P274 (#2672) so a render
 * test can reach it. It sits beside `GolferRow` and `UpcomingTournaments`,
 * which is where this page's other subcomponents already live; a named export
 * from the page file itself is a Next.js page-contract type error.
 */
export function MoversStrip({ movers }: { movers: GolfMover[] }) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3">
        Biggest Movers (24h)
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0">
        {movers.map((mover, i) => {
          // UX-P274. The note that used to sit here was right about the half it
          // addressed and did not cover the half that was broken. It is right
          // that a MOVEMENT is not a probability, so UX-P046's `<1%` floor does
          // not apply and none is applied below. But UX-P048 does not only own
          // that floor's absence — it owns the fraction->points conversion
          // itself, and its rule is that *no call site multiplies by 100*. This
          // was the one renderer on the site that still did, and it rounded the
          // result to a whole point, which broke twice:
          //
          //  1. Every other movement renderer prints ONE DECIMAL — including
          //     `TournamentCard`, ~600px further down this same page. So one
          //     golfer's one move read "1%" up here and "+0.5% today" down
          //     there, on one screen.
          //  2. `Math.round` is half-up toward +Infinity, so it is ASYMMETRIC
          //     about zero: `Math.round(0.5)` is `1` but `Math.round(-0.5)` is
          //     `-0`. The backend admits a mover at exactly
          //     `abs(movement_24h) >= 0.005` (`routes/golf.py`) — half a point —
          //     so the smallest DOWNWARD move it is able to admit was the one
          //     value guaranteed to print "0%", in red, under a down arrow,
          //     beneath a heading calling it a biggest mover.
          //
          // Passing the wire fraction to UX-P048 fixes both at once and cannot
          // drift from the sibling renderers, because it is the same function.
          const pts = movementPoints(mover.movement_24h);
          const delta = formatMovementPoints(mover.movement_24h);
          // `formatMovementPoints` returns null for anything unusable, which is
          // exactly why it exists: the old arithmetic turned a null into a
          // confident red "0%" rather than rendering nothing at all.
          if (pts == null || delta == null) return null;
          const isUp = pts > 0;

          return (
            <div
              key={`${mover.name}-${i}`}
              className="flex-shrink-0 bg-surface-card rounded-lg border border-surface-border p-3 w-[160px]"
            >
              <div className="flex items-center gap-1 mb-1">
                <span
                  data-mover-delta={mover.name}
                  className={`text-sm font-bold ${
                    isUp ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {isUp ? "▲" : "▼"} {delta}%
                </span>
              </div>
              <div className="text-sm text-text-primary font-medium truncate">
                {mover.name}
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-text-muted truncate">
                  {mover.tournament_name}
                </span>
                <span className="text-xs font-mono text-text-secondary">
                  {formatProbability(mover.probability)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default MoversStrip;
