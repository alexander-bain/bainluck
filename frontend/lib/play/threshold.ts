// L2-195 — deterministic Higher/Lower threshold.
//
// C39 P1: `generateThreshold` (Math.random) was called inside a `useMemo([deck])`,
// so every background page append rebuilt every question and re-rolled the random
// threshold. Near the deck end a page could land while a child was deciding or
// viewing a submitted answer, changing the displayed comparison AFTER the earlier
// threshold/correctness/streak was already recorded — the game contradicting its
// own grading.
//
// The fix is to derive the threshold as a PURE function of stable question/session
// identity, so an append, re-render, retry, or React Strict-Mode replay always
// yields the identical threshold for the same question. The shape (a 10–25% gap,
// clamped to 5–95, guaranteed ≥10% away) mirrors the original `generateThreshold`;
// only the entropy source changes from Math.random to a seeded PRNG.

// FNV-1a — small, stable string hash. Deterministic across runs and platforms.
function hashString(str: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// mulberry32 — a compact, well-distributed seeded PRNG. Same seed → same stream.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * A stable threshold percentage (integer 5–95) for a Higher/Lower question.
 *
 * @param actualProb the real probability, 0..1
 * @param seed       stable question/session identity (e.g. `${sessionId}:${marketId}`)
 */
export function deterministicThreshold(actualProb: number, seed: string): number {
  const rand = mulberry32(hashString(seed));
  const minGap = 0.1;
  // Two draws from the stable stream — order matters, so it is fixed here.
  const goHigher = rand() > 0.5;
  const offset = minGap + rand() * 0.15; // 10–25% away
  let threshold = goHigher ? actualProb + offset : actualProb - offset;
  // Clamp to 5%–95%.
  threshold = Math.max(0.05, Math.min(0.95, threshold));
  // Guarantee still ≥10% away after clamping.
  if (Math.abs(threshold - actualProb) < minGap) {
    threshold = actualProb > 0.5 ? actualProb - offset : actualProb + offset;
    threshold = Math.max(0.05, Math.min(0.95, threshold));
  }
  return Math.round(threshold * 100);
}
