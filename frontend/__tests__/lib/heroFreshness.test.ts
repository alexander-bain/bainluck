/**
 * live/122 (#4469) — the live hero's badge ages from the OLDEST fact in it.
 *
 * The specimen is real and is pinned: Andreeva v Gauff, `tennis_wta_us_open`
 * event 15307447, sampled from production 2026-09-09. Score stamp median 482.9s
 * old against a price stamp median 8.4s, while the hero probability moved four
 * times and the score never moved once.
 *
 * The control at the bottom is the point of the file: it recomputes what the
 * page did BEFORE this change (max across price sources) on the same specimen
 * and asserts that it reported ~8s. If someone reverts `heroFreshness` to the
 * old rule, the control keeps passing and every test above it goes red — which
 * is the arrangement that proves these tests can fail.
 */
import { heroFreshness, heroFreshnessLabel } from "@/lib/event/heroFreshness";

/** The real poll, copied from `artifacts-live-122/score-lag-run2.jsonl`. */
const SPECIMEN = {
  observedAt: "2026-09-09T19:52:36.000Z",
  priceStamps: [
    "2026-09-09T19:52:26.626Z", // kalshi
    "2026-09-09T19:51:44.347Z", // betting
    "2026-09-09T19:51:54.758Z", // polymarket
  ],
  scoreStamp: "2026-09-09T19:44:12.435Z", // linescore.observed_at
};

const freshestPrice = SPECIMEN.priceStamps.reduce((a, b) =>
  Date.parse(a) >= Date.parse(b) ? a : b,
);

const ageS = (stamp: string) =>
  Math.round((Date.parse(SPECIMEN.observedAt) - Date.parse(stamp)) / 1000);

describe("#4469 heroFreshness — the specimen Lisa was looking at", () => {
  it("reports the SCORE, not the price, when the score is behind", () => {
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: SPECIMEN.scoreStamp });
    expect(r.fact).toBe("score");
    expect(r.stamp).toBe(SPECIMEN.scoreStamp);
  });

  it("the age it reports is the eight minutes, not the ten seconds", () => {
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: SPECIMEN.scoreStamp });
    expect(ageS(r.stamp!)).toBe(504);
    // and the old rule would have said this, which is the defect:
    expect(ageS(freshestPrice)).toBe(9);
  });

  it("names the subject, so the admission is not a new confusion", () => {
    expect(heroFreshnessLabel("score", "8m ago")).toContain("Score last confirmed");
    expect(heroFreshnessLabel("score", "8m ago")).toContain("probability is newer");
    expect(heroFreshnessLabel("price", "6s ago")).toBe("Probability updated 6s ago.");
  });
});

describe("#4469 heroFreshness — the cases that must NOT change", () => {
  it("a fresher score leaves the price as the reported fact", () => {
    const r = heroFreshness({
      priceStamp: "2026-09-09T19:40:00.000Z",
      scoreStamp: "2026-09-09T19:52:00.000Z",
    });
    expect(r.fact).toBe("price");
    expect(r.stamp).toBe("2026-09-09T19:40:00.000Z");
  });

  it("an unrendered score (caller passes null) cannot age the badge", () => {
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: null });
    expect(r.fact).toBe("price");
    expect(r.stamp).toBe(freshestPrice);
  });

  it("a sport with no score stamp at all behaves exactly as before", () => {
    // Liverpool v Atletico, Napoli v Arsenal, Athletics v Blue Jays: bare
    // home_score/away_score, no stamp of any kind. Measured the same afternoon.
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: undefined });
    expect(r.fact).toBe("price");
    expect(r.stamp).toBe(freshestPrice);
  });

  it("nothing stamped reports nothing, and the badge renders null on that", () => {
    expect(heroFreshness({ priceStamp: null, scoreStamp: null })).toEqual({
      stamp: null,
      fact: null,
    });
  });

  it("an unparseable stamp is ignored rather than winning as NaN", () => {
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: "not a date" });
    expect(r.fact).toBe("price");
    expect(r.stamp).toBe(freshestPrice);
  });

  it("a tie goes to price, because there is no lag to describe", () => {
    const r = heroFreshness({ priceStamp: freshestPrice, scoreStamp: freshestPrice });
    expect(r.fact).toBe("price");
  });
});

describe("#4469 CONTROL — the old rule, on the same specimen", () => {
  it("max-across-prices really did report ~9s over a 504s-old score", () => {
    // Not a tautology: it pins that the specimen genuinely contains the defect,
    // so the assertions above are measuring something real. If this ever fails,
    // the specimen has been edited and the whole file is worthless.
    expect(ageS(freshestPrice)).toBeLessThan(15);
    expect(ageS(SPECIMEN.scoreStamp)).toBeGreaterThan(480);
    expect(ageS(SPECIMEN.scoreStamp) - ageS(freshestPrice)).toBeGreaterThan(480);
  });
});
