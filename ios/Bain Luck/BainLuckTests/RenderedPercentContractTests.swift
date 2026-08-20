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
