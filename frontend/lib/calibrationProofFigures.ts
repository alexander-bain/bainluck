// #7555 — the /about proof card's outcome count.
//
// It used to gate on 1e3 and divide by 1e6:
//
//   total_outcomes >= 1000 ? `${(total_outcomes / 1_000_000).toFixed(1)}M` : `${total_outcomes}`
//
// so the raw-integer branch was unreachable for any calibration population and
// every value below a million rendered as a sub-1 "M" figure — 747,028 published
// as "0.7M", and anything under ~50k as "0.0M", a number a reader cannot tell
// from zero. Every other compact formatter in the frontend gates on 1e6
// (`app/admin/page.tsx:241`, `app/admin/analytics/page.tsx:175`,
// `components/QuantityGroup.tsx:470`, `components/ThresholdSparkline.tsx:51`);
// `app/admin/page.tsx:995` is the three-tier M/K/raw form this card wanted.
//
// It lives in `lib/` rather than in the page because a Next.js page module may
// not carry a second named export — exporting it from `app/about/page.tsx` to
// reach a unit test fails the typecheck gate.

/**
 * A resolved-outcome count as compact display text, or `null` when the payload
 * carried no readable number.
 *
 * `null` is the caller's signal to keep the editorial fallback copy: a count the
 * server omitted is unknown, and printing `0` for it is a number the reader
 * cannot tell from a measured one.
 */
export function compactOutcomeCount(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return null;
  if (value < 1_000) return `${Math.round(value)}`;

  const thousands = Math.round(value / 1_000);
  // 999,750 rounds to 1000K — a million wearing the wrong suffix. Promote it
  // rather than publish a four-digit K.
  if (thousands >= 1_000) return `${(value / 1_000_000).toFixed(1)}M`;
  return `${thousands}K`;
}
