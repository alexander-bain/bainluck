import {
  CONFIDENCE_TIER_BARS,
  confidenceFromSources,
  crossSourceAgreement,
  normalizeTier,
  scoreToTier,
  tierBars,
} from "@/lib/confidence";

// #490 — the frontend confidence math MIRRORS the backend
// (feed_market_quality.compute_confidence_score). These pins must match the
// backend guard test in test_feed_market_quality.py::TestConfidenceSignal.

describe("confidence lib", () => {
  it("maps tiers to 3/2/1 bars", () => {
    expect(CONFIDENCE_TIER_BARS).toEqual({ high: 3, moderate: 2, low: 1 });
    expect(tierBars("high")).toBe(3);
    expect(tierBars("moderate")).toBe(2);
    expect(tierBars("low")).toBe(1);
  });

  it("cuts tiers at 0.70 / 0.40", () => {
    expect(scoreToTier(0.7)).toBe("high");
    expect(scoreToTier(0.69)).toBe("moderate");
    expect(scoreToTier(0.4)).toBe("moderate");
    expect(scoreToTier(0.39)).toBe("low");
    expect(scoreToTier(0)).toBe("low");
  });

  it("returns null when there is no source (render-only-where-present)", () => {
    expect(confidenceFromSources({ sourceCount: 0 })).toBeNull();
    expect(confidenceFromSources({ sourceCount: null })).toBeNull();
    expect(confidenceFromSources({ sourceCount: undefined })).toBeNull();
  });

  it("reaches high with full signals", () => {
    const sig = confidenceFromSources({
      sourceCount: 3,
      hasMovement: true,
      hasVolume: true,
    });
    expect(sig).not.toBeNull();
    expect(sig!.score).toBe(1);
    expect(sig!.tier).toBe("high");
    expect(sig!.bars).toBe(3);
  });

  it("is low for a lone thin source", () => {
    const sig = confidenceFromSources({ sourceCount: 1 });
    expect(sig!.tier).toBe("low");
    expect(sig!.bars).toBe(1);
  });

  it("gives a 3-source active market a full bar without agreement data", () => {
    // matches backend test_absent_signal_renormalizes
    const sig = confidenceFromSources({ sourceCount: 3, hasMovement: true });
    expect(sig!.tier).toBe("high");
  });

  it("saturates source count at 3", () => {
    const three = confidenceFromSources({ sourceCount: 3 })!.score;
    const five = confidenceFromSources({ sourceCount: 5 })!.score;
    expect(five).toBe(three);
  });

  it("matches the backend fixture values", () => {
    // parity spot-checks against the Python smoke output
    expect(confidenceFromSources({ sourceCount: 1 })!.score).toBeCloseTo(0.1765, 4);
    expect(
      confidenceFromSources({ sourceCount: 2, hasMovement: true })!.score
    ).toBeCloseTo(0.6471, 4);
    expect(
      confidenceFromSources({
        sourceCount: 4,
        hasMovement: true,
        sourcesAgree: true,
      })!.score
    ).toBeCloseTo(0.85, 4);
  });

  // L2-172 — cross-source agreement mirrors the backend
  // (feed_market_quality.cross_source_agreement). These pins must match
  // test_feed_market_quality.py::TestCrossSourceAgreement.
  it("returns null below two readings", () => {
    expect(crossSourceAgreement(null)).toBeNull();
    expect(crossSourceAgreement([])).toBeNull();
    expect(crossSourceAgreement([0.5])).toBeNull();
  });

  it("agrees within the 10-point band, disagrees outside", () => {
    expect(crossSourceAgreement([0.55, 0.6, 0.58])).toBe(true);
    expect(crossSourceAgreement([0.5, 0.6])).toBe(true); // band edge
    expect(crossSourceAgreement([0.4, 0.62])).toBe(false);
  });

  it("ignores non-numeric readings", () => {
    expect(crossSourceAgreement([0.55, 0.58, null, undefined])).toBe(true);
  });

  it("normalizes only known tiers", () => {
    expect(normalizeTier("high")).toBe("high");
    expect(normalizeTier("moderate")).toBe("moderate");
    expect(normalizeTier("low")).toBe("low");
    expect(normalizeTier(null)).toBeNull();
    expect(normalizeTier(undefined)).toBeNull();
    expect(normalizeTier("bogus")).toBeNull();
  });
});
