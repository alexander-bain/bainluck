// #999 L2-75: pure calibration math extracted from the /calibration page so it's
// unit-testable without SWR/data mocking. ECE is the n-weighted headline metric
// (reflects the outcomes users actually see); MCE is the equal-weighted
// worst-bucket-sensitivity number (a tiny bucket counts as much as a huge one).

export interface CalibrationErrorBucket {
  n: number;
  /** actual - predicted, in percentage points. */
  error: number;
}

/** Equal-weighted mean |error| (pp). Worst-bucket sensitive. */
export function mce(cal: CalibrationErrorBucket[]): number {
  if (!cal.length) return 0;
  return cal.reduce((s, b) => s + Math.abs(b.error), 0) / cal.length;
}

/** n-weighted mean |error| (pp). The headline calibration metric. */
export function ece(cal: CalibrationErrorBucket[]): number {
  const totalN = cal.reduce((s, b) => s + b.n, 0);
  if (!totalN) return 0;
  return cal.reduce((s, b) => s + (b.n / totalN) * Math.abs(b.error), 0);
}

/** "Jul 2026" from an ISO date; echoes the raw string if unparseable. */
export function monthYear(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
