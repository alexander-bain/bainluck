import XCTest
@testable import Bain_Luck

/// Native's arm of `contracts/rendered_percent.json` (#1933).
///
/// ## Why the table is inlined instead of read from the JSON
///
/// This suite runs under `scripts/ios_native_gate.sh test`, which is a LOCAL
/// gate — CI does not run xcodebuild. A Swift test that read the contract file
/// at runtime would be the only thing checking Swift against it, and it would
/// only check on the days someone ran the native gate. So the split is:
///
/// * the RUNTIME check is here, and executes the real function;
/// * the DRIFT check is in `frontend/__tests__/lib/renderedPercentContract.test.ts`,
///   which runs in CI and asserts that the rows below still equal the contract's.
///
/// Editing this table without editing the contract turns CI red. That is the
/// point — a runtime check nobody runs is not a check, and a contract nobody
/// compares against is not a contract.
///
/// CONTRACT ROWS BEGIN
private let contractCases: [(probability: Double?, percent: Int?)] = [
    (nil, nil),
    (0.0, 0),
    (1.0, 100),
    (0.5, 50),
    (0.92, 92),
    (0.005, 1),
    (0.015, 2),
    (0.025, 3),
    (0.045, 5),
    (0.125, 13),
    (0.375, 38),
    (0.625, 63),
    (0.875, 88),
    (0.565, 56),
    (0.575, 57),
    (0.9999, 100),
    (0.0001, 0),
]
/// CONTRACT ROWS END
///
/// The CARD-level rows (#2060). Same split as above: the runtime check is here,
/// the drift check against `contracts/rendered_percent.json` is in the jest
/// suite. `naive` is what INDEPENDENT per-outcome rounding produces, and is what
/// native printed before this rule existed.
///
/// CARD ROWS BEGIN
private let cardCases: [(probabilities: [Double?], percents: [Int?], pair: Bool, naive: [Int?])] = [
    ([0.925, 0.075], [93, 7], true, [93, 8]),
    ([0.915, 0.085], [92, 8], true, [92, 9]),
    ([0.605, 0.395], [61, 39], true, [61, 40]),
    ([0.995, 0.01], [99, 1], true, [100, 1]),
    ([0.705, 0.305], [70, 30], true, [71, 31]),
    ([0.59, 0.4], [60, 40], true, [59, 40]),
    ([0.706, 0.305], [71, 31], false, [71, 31]),
    ([0.589, 0.4], [59, 40], false, [59, 40]),
    ([0.57, 0.4], [57, 40], false, [57, 40]),
    ([0.001, 0.0], [0, 0], false, [0, 0]),
    ([0.5, 0.5], [50, 50], true, [50, 50]),
    ([0.5, 0.3, 0.2], [50, 30, 20], false, [50, 30, 20]),
    ([0.6, nil], [60, nil], false, [60, nil]),
    ([0.925], [93], false, [93]),
    ([], [], false, []),
]
/// CARD ROWS END

final class RenderedPercentContractTests: XCTestCase {

    func testEveryContractRow() {
        for row in contractCases {
            XCTAssertEqual(
                renderedPercent(row.probability),
                row.percent,
                "probability \(String(describing: row.probability)) must print \(String(describing: row.percent))"
            )
        }
    }

    /// The five rows where Python's banker's rounding gives a different answer.
    /// Named separately so a future edit that quietly drops them from the table
    /// fails here as well as in the CI drift check — the defect this contract
    /// exists for lives entirely in these values.
    func testHalfUpAtTheBoundary() {
        XCTAssertEqual(renderedPercent(0.005), 1)   // banker's: 0
        XCTAssertEqual(renderedPercent(0.025), 3)   // banker's: 2
        XCTAssertEqual(renderedPercent(0.045), 5)   // banker's: 4
        XCTAssertEqual(renderedPercent(0.125), 13)  // banker's: 12
        XCTAssertEqual(renderedPercent(0.625), 63)  // banker's: 62
    }

    /// `0.565 * 100` is `56.49999999999999`, not `56.5`. An implementation that
    /// "fixed" that with a decimal type would print 57 and leave the contract
    /// while still looking more correct.
    func testTheMultiplyHappensInDouble() {
        XCTAssertEqual(renderedPercent(0.565), 56)
        XCTAssertEqual(renderedPercent(0.575), 57)
    }

    /// No price and 0% are different cards, and the card fingerprint that gates
    /// a judgment depends on them staying different.
    func testNilIsNotZero() {
        XCTAssertNil(renderedPercent(nil))
        XCTAssertEqual(renderedPercent(0.0), 0)
    }

    // ── THE CARD RULE (#2060) ────────────────────────────────────────────────

    func testEveryCardContractRow() {
        for row in cardCases {
            XCTAssertEqual(
                renderedCardPercents(row.probabilities),
                row.percents,
                "card \(row.probabilities) must render \(row.percents)"
            )
            XCTAssertEqual(
                isComplementPair(row.probabilities),
                row.pair,
                "card \(row.probabilities) complement-pair verdict"
            )
        }
    }

    /// THE display invariant: a two-outcome complement card sums to exactly 100.
    ///
    /// Alex's 08-20 card was `Los Angeles D 0.925 / Colorado 0.075`, which
    /// independent rounding printed as 93 and 8. Kalshi quotes complements on a
    /// half-cent grid, so both sides land on `.5` and half-up rounds both up.
    func testEveryComplementPairSumsToExactlyOneHundred() {
        var checked = 0
        for row in cardCases where row.pair {
            let rendered = renderedCardPercents(row.probabilities).compactMap { $0 }
            XCTAssertEqual(rendered.count, row.probabilities.count)
            XCTAssertEqual(rendered.reduce(0, +), 100, "card \(row.probabilities)")
            checked += 1
        }
        // A vacuous pass is the failure mode: if the predicate stopped matching
        // anything, the loop above is green and proves nothing.
        XCTAssertGreaterThanOrEqual(checked, 6)
    }

    /// The other direction, and it is not a formality (gotcha #43). A two-outcome
    /// book summing to 0.97 has a real three-point spread; flattening it to 100
    /// would claim precision the market does not have.
    func testNonComplementCardsAreLeftExactlyAlone() {
        var checked = 0
        for row in cardCases where !row.pair {
            XCTAssertEqual(
                renderedCardPercents(row.probabilities),
                row.probabilities.map { renderedPercent($0) },
                "card \(row.probabilities) is not a pair and must not be touched"
            )
            XCTAssertEqual(renderedCardPercents(row.probabilities), row.naive)
            checked += 1
        }
        XCTAssertGreaterThanOrEqual(checked, 6)
    }

    /// The band is CLOSED at both ends, and one thousandth past it flips the
    /// verdict. 1.01 mirrors `card_integrity.display_scale`'s existing
    /// two-outcome "true binary" threshold; 0.99 is that constant made symmetric.
    func testTheComplementBandIsClosedAtBothEnds() {
        XCTAssertTrue(isComplementPair([0.705, 0.305]))   // 1.01 exactly
        XCTAssertTrue(isComplementPair([0.59, 0.4]))      // 0.99 exactly
        XCTAssertFalse(isComplementPair([0.706, 0.305]))  // 1.011
        XCTAssertFalse(isComplementPair([0.589, 0.4]))    // 0.989
    }

    func testTheExemplarRendersNinetyThreeAndSeven() {
        XCTAssertEqual(renderedCardPercents([0.925, 0.075]), [93, 7])
        // …and the rendering it replaces really did sum to 101.
        XCTAssertEqual([renderedPercent(0.925), renderedPercent(0.075)], [93, 8])
    }

    // ── #2060 item 2: the card's WHEN ────────────────────────────────────────

    /// The server sends `datetime.isoformat()`, which emits fractional seconds
    /// only when the value carries microseconds. A parser configured for one
    /// shape silently returns nil on the other — and a dropped date is
    /// indistinguishable on screen from "this market has no commence time"
    /// (gotcha #53). Both shapes must parse.
    func testBothISOShapesParse() {
        XCTAssertNotNil(labelingShortDate("2026-08-18T00:40:00+00:00"))
        XCTAssertNotNil(labelingShortDate("2026-08-18T00:40:00.123456+00:00"))
        XCTAssertNotNil(labelingShortDate("2026-08-18T00:40:00Z"))
    }

    /// An absent or unparseable timestamp renders as nothing, never as a
    /// placeholder date — a wrong "when" is worse than no "when".
    func testAnUnparseableTimestampIsOmittedNotGuessed() {
        XCTAssertNil(labelingShortDate(nil))
        XCTAssertNil(labelingShortDate(""))
        XCTAssertNil(labelingShortDate("not-a-date"))
        XCTAssertNil(labelingShortDate("2026-13-45T99:99:99Z"))
    }

    func testNonFiniteIsNotAPercent() {
        XCTAssertNil(renderedPercent(Double.nan))
        XCTAssertNil(renderedPercent(Double.infinity))
    }
}

/// The native labeling client's half of the drift gate (#1933).
final class NativeLabelingDriftGateTests: XCTestCase {

    /// Sending the key is the capability declaration, so the encoded request
    /// must always carry it — including when the payload had no digest. Swift's
    /// synthesised `Encodable` omits nil Optionals, which is why the property is
    /// a non-optional `String` and the caller passes `?? ""`.
    func testTheFingerprintKeyIsAlwaysEncoded() throws {
        let request = RankingJudgmentRequest(
            secret: nil,
            surface: "native_discover",
            rankSeen: 1,
            itemType: "futures",
            marketId: 42,
            eventId: nil,
            marketName: "Michigan Senate winner?",
            label: "good",
            reasonTags: [],
            betterThan: nil,
            worseThan: nil,
            notes: nil,
            scoreAtReview: 0,
            categoryAtReview: "politics",
            archetypeAtReview: nil,
            qualityClassAtReview: nil,
            headlineAtReview: nil,
            feedRequestId: nil,
            cardSnapshot: Self.snapshot(),
            reviewer: "native",
            cardFingerprint: ""
        )
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: encoder.encode(request)) as? [String: Any]
        )
        XCTAssertTrue(
            json.keys.contains("card_fingerprint"),
            "an absent key means 'pre-gate build' to the server — a gate-aware build must never send one"
        )
        XCTAssertEqual(json["card_fingerprint"] as? String, "")
    }

    func testAFingerprintFromThePayloadIsEchoedVerbatim() throws {
        let decoded = try Self.decoder().decode(
            DiscoverLabelingDebugItem.self,
            from: Data(Self.candidateJSON.utf8)
        )
        XCTAssertEqual(decoded.cardFingerprint, "a1b2c3d4e5f60718")
    }

    /// A payload from a server that has not deployed the gate must still decode.
    func testAPayloadWithNoFingerprintStillDecodes() throws {
        let json = Self.candidateJSON.replacingOccurrences(
            of: "\"card_fingerprint\": \"a1b2c3d4e5f60718\",",
            with: ""
        )
        let decoded = try Self.decoder().decode(
            DiscoverLabelingDebugItem.self,
            from: Data(json.utf8)
        )
        XCTAssertNil(decoded.cardFingerprint)
    }

    /// The refusal reaches the screen with words, not an HTTP code.
    func testTheRefusalIsExplained() {
        let drifted = DiscoverLabelingViewModel.driftRefusalMessage(
            "{\"status\":\"conflict\",\"reason\":\"card_drifted\"}"
        )
        XCTAssertTrue(drifted.contains("re-priced"))
        XCTAssertTrue(drifted.contains("nothing was recorded"))

        let missing = DiscoverLabelingViewModel.driftRefusalMessage(
            "{\"status\":\"conflict\",\"reason\":\"card_fingerprint_missing\"}"
        )
        XCTAssertTrue(missing.contains("Reload"))
        XCTAssertNotEqual(drifted, missing, "the two reasons ask for different actions")
    }

    /// A truncated body does not decode as JSON. Substring matching is the
    /// point, and this is the case that would have caught a `JSONDecoder` here.
    func testATruncatedBodyStillYieldsTheRightMessage() {
        let truncated = "{\"status\":\"conflict\",\"reason\":\"card_drifted\",\"live_ca"
        XCTAssertTrue(
            DiscoverLabelingViewModel.driftRefusalMessage(truncated).contains("re-priced")
        )
    }

    func testAnUnrecognisedBodyFallsBackWithoutClaimingAReason() {
        let message = DiscoverLabelingViewModel.driftRefusalMessage(nil)
        XCTAssertTrue(message.contains("nothing was recorded"))
        XCTAssertFalse(message.contains("re-priced"))
    }

    /// The same configuration `APIClient` uses (`APIClient.swift:243`).
    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private static func snapshot() -> DiscoverLabelingCardSnapshot {
        DiscoverLabelingCardSnapshot(
            schemaVersion: "discover-card-v1",
            batchId: "b",
            feedRequestId: nil,
            rank: 1,
            itemType: "futures",
            itemId: 42,
            marketId: 42,
            eventId: nil,
            name: "Michigan Senate winner?",
            source: "kalshi",
            category: "politics",
            archetype: nil,
            qualityClass: nil,
            headline: nil,
            reason: nil,
            context: nil,
            hookDescription: nil,
            imageUrl: nil,
            storyKey: nil,
            familyKey: nil,
            groupId: nil,
            score: 0,
            renderedProbability: 0.61,
            topOutcomes: [],
            reasons: [],
            hasHook: false,
            hasImage: false,
            explanationOk: false
        )
    }

    // ── #2060: the card payload carries the new fields ───────────────────────

    func testTheCardDecodesCommenceTimeAndServedPercents() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(
            DiscoverLabelingDebugItem.self,
            from: Data(Self.trioCardJSON.utf8)
        )
        XCTAssertEqual(item.commenceTime, "2026-08-18T00:40:00+00:00")
        XCTAssertEqual(item.resolutionDate, "2026-08-22T00:40:00+00:00")
        // Item 3 — `name` is the repaired text, the source text is kept beside it.
        XCTAssertEqual(item.name, "Los Angeles Dodgers vs Colorado")
        XCTAssertEqual(item.nameAtSource, "Los Angeles D vs Colorado")

        let outcomes = try XCTUnwrap(item.topOutcomes)
        XCTAssertEqual(outcomes.map(\.renderedPercent), [93, 7])
        XCTAssertEqual(outcomes.first?.nameAtSource, "Los Angeles D")
        // The served field sums to 100, which is the whole point of #2060.
        XCTAssertEqual(outcomes.compactMap(\.renderedPercent).reduce(0, +), 100)
    }

    /// A payload from a pre-#2060 server must still decode — the app falls back
    /// to computing the card rule locally rather than blanking the field.
    func testAPayloadWithoutTheNewFieldsStillDecodes() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(
            DiscoverLabelingDebugItem.self,
            from: Data(Self.candidateJSON.utf8)
        )
        XCTAssertNil(item.commenceTime)
        XCTAssertNil(item.nameAtSource)
        XCTAssertEqual(renderedCardPercents([0.925, 0.075]), [93, 7])
    }

    private static let trioCardJSON = """
    {
      "rank": 1,
      "type": "futures",
      "id": 59183794,
      "score": 0.0,
      "name": "Los Angeles Dodgers vs Colorado",
      "name_at_source": "Los Angeles D vs Colorado",
      "category": "baseball",
      "commence_time": "2026-08-18T00:40:00+00:00",
      "resolution_date": "2026-08-22T00:40:00+00:00",
      "card_fingerprint": "a1b2c3d4e5f60718",
      "rendered_probability": 0.925,
      "top_outcomes": [
        {"name": "Los Angeles Dodgers", "name_at_source": "Los Angeles D",
         "probability": 0.925, "rendered_percent": 93},
        {"name": "Colorado", "probability": 0.075, "rendered_percent": 7}
      ]
    }
    """


    private static let candidateJSON = """
    {
      "rank": 1,
      "type": "futures",
      "id": 42,
      "score": 0.0,
      "name": "Michigan Senate winner?",
      "category": "politics",
      "card_fingerprint": "a1b2c3d4e5f60718",
      "rendered_probability": 0.61
    }
    """
}
