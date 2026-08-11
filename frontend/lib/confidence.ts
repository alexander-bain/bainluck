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
  high: 3,
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

// ── UX-P052 (#1690): display authority couples to the tier ─────────────────
// The census finding: a card renders its leader % at FULL visual authority
// regardless of provenance, so "a single print, one source, 48h old" and
// "3-source consensus, 2 min ago" are indistinguishable at the same 62%.
// `SignalBars` already ships on these cards — but as a SIBLING of the number
// instead of something that governs how the number is drawn, and a reader takes
// the big number.
//
// This is a COUPLING, not a new signal. The input is the tier that already
// exists; nothing here recomputes provenance (ruling 003 — the client must not
// adjudicate trust twice, and #1690 forbids a second derivation explicitly).
//
// Deliberately ONE lever (opacity):
//   - it composes with an inline `color` (EventCard paints team colors) and with
//     `text-white` over a photo (FuturesCard variant A), where a token swap
//     would not;
//   - it cannot shift layout, so a tier flip mid-poll never reflows a live card.
// Weight and size were rejected for that second reason: EventCard's percentages
// are proportional (not `tabular-nums`), so `font-bold` -> `font-semibold` moves
// the row.
//
// `high` and an ABSENT tier both render byte-identically to before. Absent must
// not mute — most cards outside the feed carry no tier, and muting them would
// turn "we didn't measure this" into "we doubt this", which is a stronger claim
// than the data supports and the exact inversion #1690 is fixing.
export const PROBABILITY_AUTHORITY_CLASS: Record<ConfidenceTier, string> = {
  high: "",
  moderate: "opacity-80",
  low: "opacity-60",
};

/**
 * Tailwind class coupling a rendered probability's visual authority to its
 * confidence tier. Returns "" for a full-authority render (high tier, or no
 * tier at all) so call sites can concatenate unconditionally.
 *
 * Visual only — deliberately silent. The tier is already ANNOUNCED to assistive
 * tech by the sibling `SignalBars` (`aria-label` names the tier and its inputs),
 * so adding a second announcement here would read the same fact twice.
 */
export function probabilityAuthorityClass(
  tier: string | null | undefined
): string {
  const t = normalizeTier(tier);
  if (!t) return "";
  return PROBABILITY_AUTHORITY_CLASS[t];
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
