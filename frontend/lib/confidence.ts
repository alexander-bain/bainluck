// #490 — confidence signal (1-3 bars). Pure helpers, no React, so they can be
// unit-tested and reused by both the SignalBars glyph and the event hero, which
// computes its tier client-side from `win_probability_sources`.
//
// This MIRRORS backend/app/utils/feed_market_quality.py::compute_confidence_score
// exactly (same weights, same renormalization, same cut points). Feed cards get
// `confidence_tier` straight from the API; the event hero recomputes locally from
// the source list it already has. Keep the two in sync — the backend tests and
// the frontend tests both pin these numbers.

export type ConfidenceTier = "high" | "moderate" | "low";

// tier -> number of filled bars (out of 3). Backend keeps an identical map.
export const CONFIDENCE_TIER_BARS: Record<ConfidenceTier, number> = {
  high: 2,
  moderate: 2,
  low: 1,
};

export const CONFIDENCE_TIER_LABEL: Record<ConfidenceTier, string> = {
  high: "High confidence",
  moderate: "Moderate confidence",
  low: "Low confidence",
};

// Shown on hover / for screen readers — names the inputs so the glyph is never
// unexplained chrome (the rank-chip lesson).
export const CONFIDENCE_TOOLTIP = "Signal strength: sources + liquidity + freshness";

const CONFIDENCE_TIER_HIGH = 0.7;
const CONFIDENCE_TIER_MODERATE = 0.4;

const W_SOURCES = 0.45;
const W_MOVEMENT = 0.25;
const W_VOLUME = 0.15;
const W_AGREE = 0.15;
const SOURCE_SATURATION = 3;

export function scoreToTier(score: number): ConfidenceTier {
  if (score >= CONFIDENCE_TIER_HIGH) return "high";
  if (score >= CONFIDENCE_TIER_MODERATE) return "moderate";
  return "low";
}

export function tierBars(tier: ConfidenceTier): number {
  return CONFIDENCE_TIER_BARS[tier];
}

export interface ConfidenceInputs {
  sourceCount: number | null | undefined;
  hasMovement?: boolean;
  hasVolume?: boolean;
  sourcesAgree?: boolean | null;
}

export interface ConfidenceSignal {
  score: number;
  tier: ConfidenceTier;
  bars: number;
}

/**
 * Compute a confidence signal client-side (mirrors the backend). Returns null
 * when there's no source to count — render nothing rather than a misleading bar.
 */
export function confidenceFromSources({
  sourceCount,
  hasMovement = false,
  hasVolume = false,
  sourcesAgree = null,
}: ConfidenceInputs): ConfidenceSignal | null {
  const sc = Math.max(0, Math.trunc(sourceCount ?? 0));
  if (!sc) return null;

  const components: Array<[number, number]> = [
    [Math.min(sc, SOURCE_SATURATION) / SOURCE_SATURATION, W_SOURCES],
    [hasMovement ? 1 : 0, W_MOVEMENT],
    [hasVolume ? 1 : 0, W_VOLUME],
  ];
  if (sourcesAgree !== null && sourcesAgree !== undefined) {
    components.push([sourcesAgree ? 1 : 0, W_AGREE]);
  }

  const totalWeight = components.reduce((sum, [, w]) => sum + w, 0);
  if (totalWeight <= 0) return null;
  const raw = components.reduce((sum, [v, w]) => sum + v * w, 0) / totalWeight;
  const score = Math.round(Math.max(0, Math.min(1, raw)) * 10000) / 10000;
  const tier = scoreToTier(score);
  return { score, tier, bars: CONFIDENCE_TIER_BARS[tier] };
}

/** Coerce an API `confidence_tier` string into a known tier, or null. */
export function normalizeTier(
  tier: string | null | undefined
): ConfidenceTier | null {
  if (tier === "high" || tier === "moderate" || tier === "low") return tier;
  return null;
}

// ── L2-172: calibration-ready signals ──────────────────────────────────────
// The backend now records two extra signals on the confidence payload
// (`confidence_signals`): whether independent sources agree, and whether a
// closing line has landed. These are recorded raw for later calibration and do
// NOT move today's tier (weights untouched, tiers frozen — see
// feed_market_quality.confidence_signal). Mirrored here so the two math libs
// stay in lockstep, and typed so any future frontend consumer decodes them.

/** Sources "agree" when their probability spread is within this band (10 pts). */
export const CROSS_SOURCE_AGREE_SPREAD = 0.1;

export interface ConfidenceSignals {
  sources_agree?: boolean;
  has_closing_line?: boolean;
}

/**
 * Do independent sources agree on the probability? Mirrors
 * feed_market_quality.cross_source_agreement: true/false when there are >=2
 * numeric readings (agree = spread within `spreadThreshold`), null when
 * agreement isn't measurable (0-1 readings) so callers drop it rather than guess.
 */
export function crossSourceAgreement(
  probabilities: Array<number | null | undefined> | null | undefined,
  spreadThreshold: number = CROSS_SOURCE_AGREE_SPREAD
): boolean | null {
  const vals = (probabilities ?? []).filter(
    (p): p is number => typeof p === "number" && Number.isFinite(p)
  );
  if (vals.length < 2) return null;
  return Math.max(...vals) - Math.min(...vals) <= spreadThreshold;
}
