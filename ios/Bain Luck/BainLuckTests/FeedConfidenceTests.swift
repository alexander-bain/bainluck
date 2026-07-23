import XCTest
@testable import Bain_Luck

/// #490 (L2-172 native half): verifies the feed models decode the confidence
/// signal fields (`confidence_tier`/`confidence_score`) and that the native
/// confidence math (`Confidence`) mirrors the web (`frontend/lib/confidence.ts`)
/// and backend (`feed_market_quality.compute_confidence_score`) exactly.
///
/// NOTE: this file is NOT yet wired into an Xcode target — the project currently
/// has no unit-test bundle (see BainLuckTests/README.md). Once a `Bain LuckTests`
/// target exists and includes this file, `xcodebuild test` runs it as-is.
final class FeedConfidenceTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    // MARK: - Model decode

    func testFuturesDataDecodesConfidenceFields() throws {
        let json = """
        {
          "id": 1, "name": "Who wins?", "sport": null, "sport_name": null,
          "llm_sport_category": "politics", "source": "kalshi", "source_count": 3,
          "status": "open", "confidence_tier": "high", "confidence_score": 0.82
        }
        """
        let d = try decoder().decode(FeedFuturesData.self, from: Data(json.utf8))
        XCTAssertEqual(d.confidenceTier, "high")
        XCTAssertEqual(d.confidenceScore ?? 0, 0.82, accuracy: 1e-9)
    }

    func testEventDataDecodesConfidenceFields() throws {
        let json = """
        {
          "id": 2, "home_team": "A", "away_team": "B",
          "confidence_tier": "moderate", "confidence_score": 0.55
        }
        """
        let d = try decoder().decode(FeedEventData.self, from: Data(json.utf8))
        XCTAssertEqual(d.confidenceTier, "moderate")
        XCTAssertEqual(d.confidenceScore ?? 0, 0.55, accuracy: 1e-9)
    }

    func testConfidenceFieldsAbsentDecodeToNil() throws {
        let json = """
        { "id": 3, "home_team": "A", "away_team": "B" }
        """
        let d = try decoder().decode(FeedEventData.self, from: Data(json.utf8))
        XCTAssertNil(d.confidenceTier)
        XCTAssertNil(d.confidenceScore)
    }

    // MARK: - Confidence math parity (mirror of lib/confidence.ts)

    func testNormalizeOnlyKnownTiers() {
        XCTAssertEqual(Confidence.normalize("high"), .high)
        XCTAssertEqual(Confidence.normalize("moderate"), .moderate)
        XCTAssertEqual(Confidence.normalize("low"), .low)
        XCTAssertNil(Confidence.normalize(nil))
        XCTAssertNil(Confidence.normalize("bogus"))
    }

    func testTierToBars() {
        XCTAssertEqual(ConfidenceTier.high.bars, 3)
        XCTAssertEqual(ConfidenceTier.moderate.bars, 2)
        XCTAssertEqual(ConfidenceTier.low.bars, 1)
    }

    func testTierCutPoints() {
        XCTAssertEqual(Confidence.scoreToTier(0.70), .high)
        XCTAssertEqual(Confidence.scoreToTier(0.69), .moderate)
        XCTAssertEqual(Confidence.scoreToTier(0.40), .moderate)
        XCTAssertEqual(Confidence.scoreToTier(0.39), .low)
        XCTAssertEqual(Confidence.scoreToTier(0.0), .low)
    }

    func testFromSourcesRenderNilWithoutSources() {
        XCTAssertNil(Confidence.fromSources(sourceCount: 0))
        XCTAssertNil(Confidence.fromSources(sourceCount: nil))
    }

    func testFromSourcesMatchesWebFixtures() {
        // Parity with frontend/lib/confidence.test.ts + the backend guard test.
        XCTAssertEqual(Confidence.fromSources(sourceCount: 1), .low)
        XCTAssertEqual(
            Confidence.fromSources(sourceCount: 3, hasMovement: true, hasVolume: true),
            .high
        )
        // 3-source active market reaches high without agreement data (renormalizes).
        XCTAssertEqual(Confidence.fromSources(sourceCount: 3, hasMovement: true), .high)
    }
}
