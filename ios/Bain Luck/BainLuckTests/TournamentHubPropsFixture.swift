import Foundation
@testable import Bain_Luck

/// The `props` array of the 2026-09-05 production `GET /api/tournaments/us-open`
/// payload, verbatim, wrapped in the smallest hub response that decodes.
///
/// ═══ WHY THIS IS A SECOND FIXTURE AND NOT A LINE IN THE FIRST ═══
///
/// `TournamentHubProdFixture` is the 2026-09-03 capture and its own doc says it
/// is frozen deliberately: it cut `props` along with everything else the screen
/// did not draw that day. Splicing a 9/5 array into a 9/3 capture would make one
/// fixture that is two payloads and honest about neither, and re-capturing the
/// whole thing to pick up five props would destroy the only thing the frozen one
/// is for — the unpriced upcoming match and the empty bracket nobody would
/// hand-write.
///
/// ═══ WHAT THIS ONE IS FOR: THE FIVE SPECIMENS, UNEDITED ═══
///
/// Nothing here is trimmed, including the telemetry the phone does not draw
/// (`liquidity_reasons`, `mixed_freshness`, `stale_outcomes`, `freshest_*`,
/// `unpriced_legs`, `observed_at`). Keeping it proves the decoder tolerates the
/// members it ignores, which is the half of the contract a hand-built fixture
/// always gets right by construction and therefore never tests.
///
/// The register served exactly five, and between them they cover every branch
/// the presentation has:
///
///   • `sinner-competes` — **SETTLED**. `settled: true`, `settled_answer: "No"`,
///     and Kalshi is STILL QUOTING the Yes at `0.01`. A client that decodes the
///     probability and ignores the verdict prints "Yes 1%" as the current answer
///     to a question that was answered No on 30 August. This is UX-P207's
///     specimen, on the wire, today.
///   • `usa-men-final-berth` — an ordinary live answer card, 27%, one hour old.
///   • `second-major` — **a two-leg COMPARISON**, both legs priced. CERT-430's
///     shape with its hole filled; the guards build the holed variant from it.
///   • `sabalenka-title-defence` — a live answer card whose answer is a PLAYER
///     rather than a Yes, so the answer line is a name.
///   • `usa-women-quarterfinal-count` — a live answer card whose answer is a
///     THRESHOLD rung ("3+ Americans").
///
/// Not frozen for its own sake: if a re-capture keeps a settled card, a
/// multi-leg card and a live card, it is a fine replacement. What must not
/// happen is the settled specimen quietly leaving, because the rule it pins is
/// the one that costs the reader a wrong answer rather than a stale one.
enum TournamentHubPropsFixture {

    /// `generated_at` as served.
    static let servedGeneratedAt = "2026-09-05T06:35:50.491844+00:00"

    /// Decoded with the app's own decoder, so the fixture exercises the shipped
    /// `.convertFromSnakeCase` path rather than a test-local one.
    static func decode() throws -> TournamentHubResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TournamentHubResponse.self, from: Data(json.utf8))
    }

    static func presentation() throws -> TournamentHubPresentation {
        TournamentHubPresentation(response: try decode())
    }

    static let json = #"""
    {
      "slug": "us-open",
      "title": "US Open",
      "subtitle": "Flushing Meadows",
      "season": "2026",
      "generated_at": "2026-09-05T06:35:50.491844+00:00",
      "slate": {
        "matches": [],
        "age_hours": null
      },
      "results": {
        "matches": []
      },
      "boards": [],
      "bracket": {},
      "props": [
        {
          "key": "sinner-competes",
          "title": "Will Sinner actually play?",
          "hook": "A withdrawal reshapes the entire men's board.",
          "draw": "mens-singles",
          "source": "kalshi",
          "outcomes": [
            {
              "entity_key": "sinner-competes:yes",
              "display_name": "Yes",
              "probability": 0.01,
              "probability_is_live": false,
              "observed_at": "2026-09-02T21:50:10.647878+00:00",
              "age_hours": 56.76,
              "price_state": "dark",
              "is_answer": true,
              "liquidity": "thin",
              "liquidity_reasons": [
                "spread_exceeds_price"
              ]
            }
          ],
          "legs": 1,
          "unpriced_legs": [],
          "answer_entity_key": "sinner-competes:yes",
          "settled": true,
          "settled_answer": "No",
          "settled_at": "2026-08-30T15:05:00+00:00",
          "price_state": "dark",
          "observed_at": "2026-09-02T21:50:10.647878+00:00",
          "age_hours": 56.76,
          "freshest_observed_at": "2026-09-02T21:50:10.647878+00:00",
          "freshest_age_hours": 56.76,
          "stale_outcomes": [
            "sinner-competes:yes"
          ],
          "mixed_freshness": false,
          "liquidity": "thin",
          "liquidity_reasons": [
            "spread_exceeds_price"
          ]
        },
        {
          "key": "usa-men-final-berth",
          "title": "Will an American reach the men's final?",
          "hook": "The market asks about the American men as a group, not one at a time.",
          "draw": "mens-singles",
          "source": "kalshi",
          "outcomes": [
            {
              "entity_key": "usa-men-final-berth:yes",
              "display_name": "Yes",
              "probability": 0.27,
              "probability_is_live": true,
              "observed_at": "2026-09-05T05:53:51.106831+00:00",
              "age_hours": 0.7,
              "price_state": "live",
              "is_answer": true,
              "liquidity": "traded",
              "liquidity_reasons": []
            }
          ],
          "legs": 1,
          "unpriced_legs": [],
          "answer_entity_key": "usa-men-final-berth:yes",
          "settled": false,
          "settled_answer": null,
          "settled_at": null,
          "price_state": "live",
          "observed_at": "2026-09-05T05:53:51.106831+00:00",
          "age_hours": 0.7,
          "freshest_observed_at": "2026-09-05T05:53:51.106831+00:00",
          "freshest_age_hours": 0.7,
          "stale_outcomes": [],
          "mixed_freshness": false,
          "liquidity": "traded",
          "liquidity_reasons": []
        },
        {
          "key": "second-major",
          "title": "Who wins a second major this year?",
          "hook": "Both already have one in 2026. These are two separate questions — they could both do it, or neither.",
          "draw": "mens-singles",
          "source": "kalshi",
          "outcomes": [
            {
              "entity_key": "second-major:carlos-alcaraz",
              "display_name": "Carlos Alcaraz",
              "probability": 0.465,
              "probability_is_live": true,
              "observed_at": "2026-09-05T05:53:50.175481+00:00",
              "age_hours": 0.7,
              "price_state": "live",
              "is_answer": false,
              "liquidity": "traded",
              "liquidity_reasons": []
            },
            {
              "entity_key": "second-major:jannik-sinner",
              "display_name": "Jannik Sinner",
              "probability": 0.01,
              "probability_is_live": true,
              "observed_at": "2026-09-05T05:53:49.979424+00:00",
              "age_hours": 0.7,
              "price_state": "live",
              "is_answer": false,
              "liquidity": "thin",
              "liquidity_reasons": [
                "spread_exceeds_price"
              ]
            }
          ],
          "legs": 2,
          "unpriced_legs": [],
          "answer_entity_key": null,
          "settled": false,
          "settled_answer": null,
          "settled_at": null,
          "price_state": "live",
          "observed_at": "2026-09-05T05:53:49.979424+00:00",
          "age_hours": 0.7,
          "freshest_observed_at": "2026-09-05T05:53:50.175481+00:00",
          "freshest_age_hours": 0.7,
          "stale_outcomes": [],
          "mixed_freshness": false,
          "liquidity": "thin",
          "liquidity_reasons": [
            "spread_exceeds_price"
          ]
        },
        {
          "key": "sabalenka-title-defence",
          "title": "Can Sabalenka go back-to-back?",
          "hook": "She won here last year — and with the US Open the last major of 2026, this market is now exactly that question.",
          "draw": "womens-singles",
          "source": "kalshi",
          "outcomes": [
            {
              "entity_key": "sabalenka-title-defence:aryna-sabalenka",
              "display_name": "Aryna Sabalenka",
              "probability": 0.275,
              "probability_is_live": true,
              "observed_at": "2026-09-05T05:53:49.664560+00:00",
              "age_hours": 0.7,
              "price_state": "live",
              "is_answer": true,
              "liquidity": "traded",
              "liquidity_reasons": []
            }
          ],
          "legs": 1,
          "unpriced_legs": [],
          "answer_entity_key": "sabalenka-title-defence:aryna-sabalenka",
          "settled": false,
          "settled_answer": null,
          "settled_at": null,
          "price_state": "live",
          "observed_at": "2026-09-05T05:53:49.664560+00:00",
          "age_hours": 0.7,
          "freshest_observed_at": "2026-09-05T05:53:49.664560+00:00",
          "freshest_age_hours": 0.7,
          "stale_outcomes": [],
          "mixed_freshness": false,
          "liquidity": "traded",
          "liquidity_reasons": []
        },
        {
          "key": "usa-women-quarterfinal-count",
          "title": "Can three American women reach the quarterfinals?",
          "hook": "One market for the whole American contingent, with a rung for one right through seven.",
          "draw": "womens-singles",
          "source": "kalshi",
          "outcomes": [
            {
              "entity_key": "usa-women-quarterfinal-count:3+-americans",
              "display_name": "3+ Americans",
              "probability": 0.44,
              "probability_is_live": true,
              "observed_at": "2026-09-05T05:53:51.308491+00:00",
              "age_hours": 0.7,
              "price_state": "live",
              "is_answer": true,
              "liquidity": "traded",
              "liquidity_reasons": []
            }
          ],
          "legs": 1,
          "unpriced_legs": [],
          "answer_entity_key": "usa-women-quarterfinal-count:3+-americans",
          "settled": false,
          "settled_answer": null,
          "settled_at": null,
          "price_state": "live",
          "observed_at": "2026-09-05T05:53:51.308491+00:00",
          "age_hours": 0.7,
          "freshest_observed_at": "2026-09-05T05:53:51.308491+00:00",
          "freshest_age_hours": 0.7,
          "stale_outcomes": [],
          "mixed_freshness": false,
          "liquidity": "traded",
          "liquidity_reasons": []
        }
      ]
    }
    """#
}
