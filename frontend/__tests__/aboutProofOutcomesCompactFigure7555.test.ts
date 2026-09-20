// #7555 — /about published 747,028 resolved outcomes as "0.7M".
//
// The proof card gated on 1e3 and divided by 1e6, so its raw-integer branch was
// unreachable for any calibration population and the whole sub-million range
// rendered as a sub-1 "M" figure.
//
// The load-bearing assertion here is the CLASS one (`never a sub-1 M`), not the
// specimen. To prove it is not vacuous, the legacy formatter is carried below as
// a control and asserted to FAIL the same invariant: if a refactor ever makes
// the invariant unfalsifiable, the control stops failing and this file goes red.

import { compactOutcomeCount } from "@/lib/calibrationProofFigures";

/** The formatter exactly as it stood in `app/about/page.tsx` before #7555. */
function legacyCompact(n: number): string | null {
  return n && n >= 1000 ? `${(n / 1_000_000).toFixed(1)}M` : n ? `${n}` : null;
}

/** "0.7M", "0.0M" — a magnitude the reader cannot tell from zero. */
const SUB_ONE_M = /^0\.\dM$/;

/** 1,000 → 999,999 on a prime stride, plus the edges that bracket each tier. */
function subMillionSamples(): number[] {
  const out: number[] = [1_000, 1_001, 9_000, 50_000, 747_028, 999_499, 999_500, 999_999];
  for (let n = 1_000; n < 1_000_000; n += 997) out.push(n);
  return out;
}

describe("#7555 the /about proof card's outcome count", () => {
  it("publishes today's live population as 747K, not 0.7M", () => {
    // The payload at the minute the defect was photographed on production.
    expect(compactOutcomeCount(747_028)).toBe("747K");
  });

  it("never renders a sub-million population as a sub-1 M figure", () => {
    const offenders = subMillionSamples().filter((n) =>
      SUB_ONE_M.test(compactOutcomeCount(n) ?? "")
    );
    expect(offenders).toEqual([]);
  });

  it("CONTROL: the legacy formatter does violate that invariant", () => {
    // Non-vacuity, stated exactly. `(n / 1e6).toFixed(1)` carries a leading
    // "0." precisely while n < 950,000 — above that it rounds to "1.0M" and is
    // accidentally the right magnitude. So the legacy offender set IS the
    // sub-950k sample set, and it is not empty.
    const samples = subMillionSamples();
    const offenders = samples.filter((n) => SUB_ONE_M.test(legacyCompact(n) ?? ""));
    expect(offenders).toEqual(samples.filter((n) => n < 950_000));
    expect(offenders.length).toBeGreaterThan(900);

    // The three the issue tabulates, including the photographed specimen.
    expect(legacyCompact(9_000)).toBe("0.0M");
    expect(legacyCompact(50_000)).toBe("0.1M");
    expect(legacyCompact(747_028)).toBe("0.7M");
  });

  it("keeps the M tier for populations that really are millions", () => {
    expect(compactOutcomeCount(1_000_000)).toBe("1.0M");
    expect(compactOutcomeCount(1_250_000)).toBe("1.3M");
    expect(compactOutcomeCount(12_400_000)).toBe("12.4M");
  });

  it("promotes a count that rounds to 1000K rather than printing a four-digit K", () => {
    expect(compactOutcomeCount(999_750)).toBe("1.0M");
    expect(compactOutcomeCount(999_499)).toBe("999K");
  });

  it("reaches the raw branch below a thousand, which the legacy gate could not", () => {
    expect(compactOutcomeCount(999)).toBe("999");
    expect(compactOutcomeCount(1)).toBe("1");
  });

  it("returns null for a count the payload did not carry, so the editorial copy stands", () => {
    // `null` and `0` must not become the string "0" — an omitted field is
    // unknown, not measured.
    expect(compactOutcomeCount(null)).toBeNull();
    expect(compactOutcomeCount(undefined)).toBeNull();
    expect(compactOutcomeCount(0)).toBeNull();
    expect(compactOutcomeCount(-5)).toBeNull();
    expect(compactOutcomeCount(Number.NaN)).toBeNull();
    expect(compactOutcomeCount("747028")).toBeNull();
  });
});
