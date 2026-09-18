import XCTest
@testable import Bain_Luck

/// Native's arm of the `card_sum` half of `contracts/rendered_percent.json`
/// (#2088, contract version 4).
///
/// ## Why the table is inlined instead of read from the JSON
///
/// The same split `RenderedPercentContractTests` documents: this suite runs under
/// `scripts/ios_native_gate.sh test`, a LOCAL gate, because CI does not run
/// xcodebuild. So the RUNTIME check is here and executes the real functions, and
/// the DRIFT check lives in `frontend/__tests__/lib/renderedPercentContract.test.ts`,
/// which runs in CI and asserts that the rows below still equal the contract's.
/// Editing this table without editing the contract turns CI red. That is the point.
///
/// ## What was broken when this arm was written
///
/// `card_sum_implementations` listed python and typescript — two runtimes, where
/// the scalar and duel arms list three — and the iOS tree contained no reference
/// to `card_sum_reason` in any file. Measured on production 2026-09-18,
/// `GET /api/feed?limit=200`: 98 objects carry the field and 2 read
/// `independent_prices`, so two cards that explained themselves on the web stood
/// bare on the phone.
///
/// CARD SUM ROWS BEGIN
private let cardSumCases: [(probabilities: [Double?], percents: [Int?], sum: Int?, reason: String?)] = [
    ([0.57, 0.4], [57, 40], 97, "independent_prices"),
    ([0.507, 0.478], [51, 48], 99, "independent_prices"),
    ([0.925, 0.075], [93, 7], 100, nil),
    ([0.51, 0.48], [52, 48], 100, nil),
    ([0.505, 0.505], [50, 50], 100, nil),
    ([0.57, nil], [57, nil], 57, "unpriced_outcome"),
    ([nil, nil], [nil, nil], nil, "unpriced_outcome"),
    ([0.5, 0.3, 0.17], [50, 30, 17], 97, nil),
    ([0.6], [60], 60, nil),
    ([], [], nil, nil),
    ([0.001, 0.001], [0, 0], 0, "independent_prices"),
    ([0.95, 0.95], [95, 95], 190, "independent_prices"),
]
/// CARD SUM ROWS END

final class CardSumContractTests: XCTestCase {

    // MARK: - The contract, executed

    func testEveryContractRowRendersItsPercents() {
        for row in cardSumCases {
            XCTAssertEqual(
                renderedCardPercents(row.probabilities), row.percents,
                "percents for \(row.probabilities)"
            )
        }
    }

    func testEveryContractRowTotalsItsSum() {
        for row in cardSumCases {
            XCTAssertEqual(cardSum(row.probabilities), row.sum, "sum for \(row.probabilities)")
        }
    }

    func testEveryContractRowCarriesItsReason() {
        for row in cardSumCases {
            XCTAssertEqual(
                cardSumReason(row.probabilities), row.reason,
                "reason for \(row.probabilities)"
            )
        }
    }

    /// The not-firing direction, asserted as explicitly as the firing one
    /// (gotcha #43): a complement pair is normalized, rounded once and derived, so
    /// it totals 100 by construction and can NEVER earn a reason. A guard that only
    /// proves the fix fires is how the Sports tab got emptied.
    func testAComplementPairCanNeverEarnAReason() {
        let complements = cardSumCases.filter { isComplementPair($0.probabilities) }
        XCTAssertGreaterThanOrEqual(complements.count, 3, "the table must carry complement rows")
        for row in complements {
            XCTAssertNil(cardSumReason(row.probabilities), "\(row.probabilities) is a pair")
            XCTAssertEqual(cardSum(row.probabilities), 100, "\(row.probabilities) totals 100")
        }
    }

    /// Non-vacuity: the table is the test, so an empty one would pass everything
    /// above forever.
    func testTheTableIsNotEmpty() {
        XCTAssertEqual(cardSumCases.count, 12)
        XCTAssertTrue(cardSumCases.contains { $0.reason == "independent_prices" })
        XCTAssertTrue(cardSumCases.contains { $0.reason == "unpriced_outcome" })
        XCTAssertTrue(cardSumCases.contains { $0.reason == nil })
    }

    // MARK: - The sentence

    func testEachReasonHasItsOwnSentence() {
        XCTAssertEqual(
            cardSumExplanation(sumIndependentPrices),
            "These two sides are quoted separately, so they do not add up to 100."
        )
        XCTAssertEqual(
            cardSumExplanation(sumUnpricedOutcome),
            "One side has no number, so there is nothing to add up."
        )
    }

    /// A reason this build has never heard of draws NOTHING. The phone ships for
    /// months against a moving server, so a future reason is the live case — and an
    /// empty or invented explanation is worse than the unexplained card.
    func testAnUnknownOrAbsentReasonDrawsNothing() {
        XCTAssertNil(cardSumExplanation(nil))
        XCTAssertNil(cardSumExplanation("some_future_reason"))
        XCTAssertNil(cardSumExplanation(""))
    }

    /// Ruling 138 bans the `price` stem from reader copy. The machine-readable
    /// reasons carry it (`independent_prices`, `unpriced_outcome`) and that is fine
    /// — they are payload enums and are never rendered.
    func testNoSentenceUsesTheBannedStem() {
        for reason in [sumIndependentPrices, sumUnpricedOutcome] {
            let sentence = cardSumExplanation(reason) ?? ""
            XCTAssertFalse(sentence.isEmpty)
            for banned in ["price", "priced", "prices", "unpriced"] {
                XCTAssertFalse(
                    sentence.lowercased().contains(banned),
                    "\(reason)'s sentence says '\(banned)'"
                )
            }
        }
    }

    /// The words are web's, verbatim (`frontend/lib/cardSum.ts`). Two vocabularies
    /// for one fact is how two surfaces start disagreeing in front of a reader who
    /// opens both.
    func testTheSentencesMatchTheWebArmVerbatim() {
        let webCopy = [
            "independent_prices": "These two sides are quoted separately, so they do not add up to 100.",
            "unpriced_outcome": "One side has no number, so there is nothing to add up.",
        ]
        for (reason, sentence) in webCopy {
            XCTAssertEqual(cardSumExplanation(reason), sentence)
        }
    }

    // MARK: - The server's answer is taken verbatim

    /// A served null draws nothing, and native does NOT second-guess it from the
    /// probabilities. This pair would derive `independent_prices` locally; the
    /// server said the card is fine, and the server is the one deciding.
    func testAServedNullDrawsNothingEvenWhenTheLocalRuleWould() {
        XCTAssertEqual(cardSumReason([0.57, 0.4]), sumIndependentPrices, "the local rule would fire")
        XCTAssertNil(cardSumExplanation(nil), "but the served answer is what is drawn")
    }

    /// Swift's synthesized `decodeIfPresent` returns the same `nil` for an absent
    /// key and a served `null`. That is WHY there is no local fallback — a wrapper
    /// type with a `decodeNil()` check does not restore the distinction, because
    /// `decodeIfPresent` never calls the wrapper's initializer for a null. Pinned
    /// here so a later session does not rebuild the wrapper and believe it works.
    func testAnAbsentKeyAndAServedNullAreIndistinguishable() throws {
        struct Envelope: Decodable {
            let cardSumReason: String?
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let absent = try decoder.decode(Envelope.self, from: Data(#"{}"#.utf8))
        let servedNull = try decoder.decode(
            Envelope.self, from: Data(#"{"card_sum_reason": null}"#.utf8)
        )
        XCTAssertNil(absent.cardSumReason)
        XCTAssertNil(servedNull.cardSumReason)

        let servedReason = try decoder.decode(
            Envelope.self, from: Data(#"{"card_sum_reason": "independent_prices"}"#.utf8)
        )
        XCTAssertEqual(servedReason.cardSumReason, "independent_prices")
    }

    /// The real payload shape, decoded through the real model — the specimen
    /// production served on 2026-09-18.
    func testTheLiveSpecimenDecodesAndExplainsItself() throws {
        let json = #"""
        {
          "id": 16625182,
          "name": "Crude Oil all time high?",
          "card_sum_reason": "independent_prices",
          "top_outcomes": [
            {"id": 1, "name": "December 31", "probability": 0.13},
            {"id": 2, "name": "September 30", "probability": 0.01}
          ]
        }
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(FeedFuturesData.self, from: Data(json.utf8))

        XCTAssertEqual(data.cardSumReason, "independent_prices")
        XCTAssertEqual(
            cardSumExplanation(data.cardSumReason),
            "These two sides are quoted separately, so they do not add up to 100."
        )
        // ...and the local rule agrees with the server on this specimen, which is
        // the 98-of-98 agreement the served-only decision rests on.
        XCTAssertEqual(
            cardSumReason((data.topOutcomes ?? []).prefix(3).map(\.probability)),
            data.cardSumReason
        )
    }
}
