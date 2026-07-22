/**
 * Pure helper for the Futures Detail "ambient history" hero (L2-161, design
 * Hero C — the declared ships variant). It extracts the hero outcome's recent
 * probability curve so the numeral can sit over its own 7-day history as quiet
 * texture (accent-brand, no source comparison — the blend-only ruling holds:
 * this is the single blended line, never a per-source overlay).
 *
 * Side-effect-free + SSR-safe so it is unit-testable.
 */
import type { FuturesOutcomeHistory } from "./types";

/**
 * Probabilities (0–1) for the hero outcome's history, oldest → newest, with
 * null points dropped. Returns [] when there is no usable series (the hero then
 * renders with no ambient layer — no empty frame).
 */
export function buildAmbientPoints(
  historyOutcomes: FuturesOutcomeHistory[] | null | undefined,
  heroOutcomeId: number | null | undefined,
): number[] {
  if (!historyOutcomes || heroOutcomeId == null) return [];
  const entry = historyOutcomes.find((o) => o.outcome_id === heroOutcomeId);
  if (!entry || !Array.isArray(entry.history)) return [];
  return entry.history
    .map((p) => p.probability)
    .filter((p): p is number => p !== null && p !== undefined);
}
