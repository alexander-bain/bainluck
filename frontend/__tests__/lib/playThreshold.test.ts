// L2-195 — deterministic Higher/Lower threshold (C39 P1). Proves the threshold is
// a pure function of (probability, seed): identical across repeated calls (an
// append/render/retry/Strict-Mode replay can't move it), while still honoring the
// original generateThreshold shape (integer 5–95, ≥10 points away).

import { deterministicThreshold } from "@/lib/play/threshold";

describe("deterministicThreshold", () => {
  it("is stable across repeated calls with the same seed", () => {
    const a = deterministicThreshold(0.6, "kid:sam:1234");
    const b = deterministicThreshold(0.6, "kid:sam:1234");
    const c = deterministicThreshold(0.6, "kid:sam:1234");
    expect(a).toBe(b);
    expect(b).toBe(c);
  });

  it("varies by seed (different questions / players get different thresholds)", () => {
    const seeds = ["kid:sam:1", "kid:sam:2", "kid:ava:1", "kid:ava:2", "kid:sam:99"];
    const vals = seeds.map((s) => deterministicThreshold(0.6, s));
    // Not all identical — the seed genuinely perturbs the draw.
    expect(new Set(vals).size).toBeGreaterThan(1);
  });

  it("returns an integer percentage in 5..95", () => {
    for (let p = 0; p <= 100; p++) {
      const t = deterministicThreshold(p / 100, `seed:${p}`);
      expect(Number.isInteger(t)).toBe(true);
      expect(t).toBeGreaterThanOrEqual(5);
      expect(t).toBeLessThanOrEqual(95);
    }
  });

  it("stays at least 10 points away from the actual probability", () => {
    for (let p = 5; p <= 95; p += 1) {
      const prob = p / 100;
      const t = deterministicThreshold(prob, `gap:${p}`);
      expect(Math.abs(t - p)).toBeGreaterThanOrEqual(10);
    }
  });

  it("recorded correctness cannot flip for a fixed question across rebuilds", () => {
    // Simulate what HigherLower does: derive the threshold, grade a guess, then
    // rebuild the question list (new deck ref) and re-grade — same verdict.
    const prob = 0.72;
    const seed = "kid:leo:5551";
    const t1 = deterministicThreshold(prob, seed);
    const guessHigher = Math.round(prob * 100) > t1;
    const t2 = deterministicThreshold(prob, seed); // after an append rebuild
    const regraded = Math.round(prob * 100) > t2;
    expect(t2).toBe(t1);
    expect(regraded).toBe(guessHigher);
  });
});
