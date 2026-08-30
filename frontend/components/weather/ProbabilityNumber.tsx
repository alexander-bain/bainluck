"use client";

import { probColor, weatherPercent } from "./data";
import type { PrintedProbability } from "./data";

interface ProbabilityNumberProps {
  /** The served pair — the integer to print, and the value it came from. */
  item: PrintedProbability;
  size?: number;
  forceColor?: string;
}

/**
 * The weather page's big number.
 *
 * It used to render `Math.round(value)` and glue a `%` on, which meant a market
 * priced 0.0004 printed a flat `0%` in 64px type over a live quote. The string
 * now comes from `weatherPercent` — the page's adapter onto the site's single
 * home for the decision — so the same value prints `<1%`.
 *
 * The `%` keeps its own smaller span, so the split is on the trailing character
 * rather than on a re-derivation: `68%` -> `68` + `%`, `<1%` -> `<1` + `%`. A
 * second `formatProbabilityPercent` call to "get just the digits" would be the
 * two-decisions-for-one-number bug the formatter exists to prevent.
 */
export default function ProbabilityNumber({
  item,
  size = 36,
  forceColor,
}: ProbabilityNumberProps) {
  const color = forceColor ?? probColor(item.prob);
  const pctSize = size * 0.42;
  const printed = weatherPercent(item);
  const body = printed.endsWith("%") ? printed.slice(0, -1) : printed;

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
      {body}
      {printed.endsWith("%") ? (
        <span style={{ fontSize: pctSize, opacity: 0.7 }}>%</span>
      ) : null}
    </span>
  );
}
