/**
 * #8464 — a verified Polymarket pick'em read "No price yet".
 *
 * Found by lane1/643 at 390px on production, `/events/15316415` (Cubs @ Red Sox,
 * game 1, 2026-09-25 17:05Z), 2026-09-24 20:47Z. The payload served, as the
 * event's only source:
 *
 *     polymarket: { value: 0.5, evidence_status: "verified",
 *                   verified_scope: "full_event_winner" }
 *
 * with a 0.49/0.51 book behind it (venue: 0.505/0.495). `isUntradedPlaceholder`
 * judged it by value alone and withheld the hero while the chart below drew the
 * same leg at 49%.
 *
 * Both directions (gotcha #43): the verified reading keeps its number; the UX-P042
 * specimen (no stamp), the feed's bare number and an `unverified` stamp are still
 * withheld at exactly 0.500.
 */
import {
  isUntradedPlaceholder,
  shouldWithholdProbability,
} from "../../lib/probabilityEvidence";

/** `/api/events/15316415`, 2026-09-24 20:46Z, trimmed to the fields the gate reads. */
const CUBS_RED_SOX_15316415 = {
  status: "scheduled",
  win_probability_sources: {
    polymarket: {
      value: 0.5,
      display_name: "Polymarket",
      type: "market",
      evidence_status: "verified",
      verified_scope: "full_event_winner",
    },
  },
};

const withStatus = (evidence_status: string | undefined) => ({
  status: "scheduled",
  win_probability_sources: {
    polymarket: { value: 0.5, display_name: "Polymarket", type: "market", evidence_status },
  },
});

describe("#8464 a verified lone-Polymarket 0.500 is a price, not a placeholder", () => {
  test("the production specimen keeps its number", () => {
    expect(isUntradedPlaceholder(CUBS_RED_SOX_15316415.win_probability_sources)).toBe(false);
    expect(shouldWithholdProbability(CUBS_RED_SOX_15316415)).toBe(false);
  });

  test("control: no stamp at all (the UX-P042 shape) is still withheld", () => {
    expect(shouldWithholdProbability(withStatus(undefined))).toBe(true);
  });

  test("control: an unverified stamp is still withheld", () => {
    expect(shouldWithholdProbability(withStatus("unverified"))).toBe(true);
  });

  test("control: an ineligible stamp is still withheld", () => {
    expect(shouldWithholdProbability(withStatus("ineligible"))).toBe(true);
  });

  test("control: the feed's bare-number shape cannot carry a stamp and is still withheld", () => {
    expect(
      shouldWithholdProbability({ status: "scheduled", win_probability_sources: { polymarket: 0.5 } }),
    ).toBe(true);
  });
});
