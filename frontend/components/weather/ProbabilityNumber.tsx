"use client";

import { probColor } from "./data";
import { NO_READING, probabilityParts } from "@/lib/probabilityDisplay";

interface ProbabilityNumberProps {
  /** The whole percent the server decided, 0-100. */
  value: number;
  /** The raw probability `value` is a rounding OF, 0-1 (#6616). Optional only
   *  because a pre-#6616 Redis payload carries no such field; the caller gets
   *  it from `weatherProbability`, which falls back to `value / 100`. */
  probability?: number;
  size?: number;
  forceColor?: string;
}

/**
 * The hero / wild-card percent, under the boundary rule (UX-P046, #6616).
 *
 * This printed `Math.round(value)`, so a market quoted at 0.995 drew a 64px
 * `100%` — "this question is settled" — over an open, tradeable book. It is the
 * same defect `/entertainment`'s `ProbPct` had, and the same shape: the integer
 * and the `%` are SEPARATE spans at different sizes, so `formatProbabilityPercent`
 * is not a drop-in — handed the finished above-the-boundary string this would
 * draw the marker at full size with a second `%` glued after it.
 * `probabilityParts` is the seam #6064 added for exactly that, and taking it
 * keeps the rule in one place. (The boundary strings are deliberately not spelled
 * here: `probabilityDisplay.test.ts` requires exactly one module to hold them,
 * and prose is indistinguishable from a second copy to a source-text guard.)
 *
 * `rendered` is passed so the integer stays the one the server decided; the
 * boundary rule still runs on the PROBABILITY, which is the composition
 * `probabilityDisplay.ts` documents.
 */
export default function ProbabilityNumber({
  value,
  probability,
  size = 36,
  forceColor,
}: ProbabilityNumberProps) {
  const color = forceColor ?? probColor(value);
  const pctSize = size * 0.42;
  const { marker, digits } = probabilityParts(probability ?? value / 100, {
    rendered: value,
  });

  return (
    <span
      className="font-mono"
      style={{
        fontSize: size,
        fontWeight: 600,
        letterSpacing: "-0.02em",
        color,
        lineHeight: 1,
      }}
    >
      {digits === NO_READING ? (
        NO_READING
      ) : (
        <>
          {marker}
          {digits}
          <span style={{ fontSize: pctSize, opacity: 0.7 }}>%</span>
        </>
      )}
    </span>
  );
}
