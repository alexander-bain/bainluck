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
 * CERT-3408 blocked the first repair, which trusted `verified` alone: that stamp
 * proves the question, not the price. Two verified lone-Polymarket 0.500s sat
 * over books nobody trades inside (15314872 0.06/0.95, 15316031 0.09/0.90). The
 * server now stamps `price_evidence` from the stored book
 * (`app/utils/price_evidence.py`); the specimen serves `tradeable_book`, those
 * two serve `unproven`.
 *
 * Both directions (gotcha #43): the proven reading keeps its number; both
 * wide-book shapes, a verified reading with no price stamp, the UX-P042 specimen
 * (no stamp), the feed's bare number and `unverified`/`ineligible` stamps are
 * still withheld at exactly 0.500.
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
      price_evidence: "tradeable_book",
    },
  },
};

/**
 * `/api/events/{id}` for CERT-3408's two counterexamples, trimmed: verified
 * question, 0.500 reading, and the server's price grade over their wide books.
 */
const wideBook = (updated_at: string) => ({
  status: "scheduled",
  win_probability_sources: {
    polymarket: {
      value: 0.5,
      display_name: "Polymarket",
      type: "market",
      updated_at,
      evidence_status: "verified",
      verified_scope: "full_event_winner",
      price_evidence: "unproven",
    },
  },
});
const GALATASARAY_CAYIROVA_15314872 = wideBook("2026-09-22T08:39:06.291368+00:00");
const SKYLINERS_VECHTA_15316031 = wideBook("2026-09-24T03:40:21.275765+00:00");

const withStatus = (evidence_status: string | undefined) => ({
  status: "scheduled",
  win_probability_sources: {
    polymarket: { value: 0.5, display_name: "Polymarket", type: "market", evidence_status },
  },
});

describe("#8464 a lone-Polymarket 0.500 over a tradeable book is a price, not a placeholder", () => {
  test("the production specimen keeps its number", () => {
    expect(isUntradedPlaceholder(CUBS_RED_SOX_15316415.win_probability_sources)).toBe(false);
    expect(shouldWithholdProbability(CUBS_RED_SOX_15316415)).toBe(false);
  });

  test("CERT-3408: verified 0.500 over the 0.06/0.95 book (15314872) is still withheld", () => {
    expect(shouldWithholdProbability(GALATASARAY_CAYIROVA_15314872)).toBe(true);
  });

  test("CERT-3408: verified 0.500 over the 0.09/0.90 book (15316031) is still withheld", () => {
    expect(shouldWithholdProbability(SKYLINERS_VECHTA_15316031)).toBe(true);
  });

  test("control: verified with no price stamp (a server that predates it) is still withheld", () => {
    expect(shouldWithholdProbability(withStatus("verified"))).toBe(true);
  });

  test("control: a tradeable book on an unverified question is still withheld", () => {
    expect(
      shouldWithholdProbability({
        status: "scheduled",
        win_probability_sources: {
          polymarket: { value: 0.5, evidence_status: "unverified", price_evidence: "tradeable_book" },
        },
      }),
    ).toBe(true);
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
