import XCTest
@testable import Bain_Luck

/// L2-184 — the single-number Discover kernels (`NativeFuturesDiscoverCard` /
/// `NativeEventDiscoverCard`) now render `SignalBarsView(tier:)` in their footer,
/// matching the multi-candidate kernels. SwiftUI views aren't unit-rendered in
/// this suite, so — like `FeedConfidenceTests` — these tests verify the exact
/// contract the footer relies on: each kernel's decoded `confidenceTier` drives
/// the glyph's render path (`Confidence.normalize(_:)?.bars`) for low/moderate/
/// high, and an absent tier renders nothing.
final class NativeDiscoverCardConfidenceTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func futures(tier: String?) throws -> FeedFuturesData {
        let tierField = tier.map { "\"confidence_tier\": \"\($0)\"," } ?? ""
        let json = """
        {
          "id": 1, "name": "Who wins?", "sport": null, "sport_name": null,
          "llm_sport_category": "politics", "source": "kalshi", "source_count": 3,
          "status": "open", \(tierField) "confidence_score": 0.8
        }
        """
        return try decoder().decode(FeedFuturesData.self, from: Data(json.utf8))
    }

    private func event(tier: String?) throws -> FeedEventData {
        let tierField = tier.map { "\"confidence_tier\": \"\($0)\"," } ?? ""
        let json = """
        { "id": 2, "home_team": "A", "away_team": "B", \(tierField) "confidence_score": 0.8 }
        """
        return try decoder().decode(FeedEventData.self, from: Data(json.utf8))
    }

    // MARK: - Futures kernel (NativeFuturesDiscoverCard footer)

    func testFuturesKernelTierDrivesGlyphBars() throws {
        XCTAssertEqual(Confidence.normalize(try futures(tier: "high").confidenceTier)?.bars, 3)
        XCTAssertEqual(Confidence.normalize(try futures(tier: "moderate").confidenceTier)?.bars, 2)
        XCTAssertEqual(Confidence.normalize(try futures(tier: "low").confidenceTier)?.bars, 1)
    }

    func testFuturesKernelAbsentTierRendersNothing() throws {
        let d = try futures(tier: nil)
        XCTAssertNil(d.confidenceTier)
        XCTAssertNil(Confidence.normalize(d.confidenceTier))
    }

    // MARK: - Event kernel (NativeEventDiscoverCard footer)

    func testEventKernelTierDrivesGlyphBars() throws {
        XCTAssertEqual(Confidence.normalize(try event(tier: "high").confidenceTier)?.bars, 3)
        XCTAssertEqual(Confidence.normalize(try event(tier: "moderate").confidenceTier)?.bars, 2)
        XCTAssertEqual(Confidence.normalize(try event(tier: "low").confidenceTier)?.bars, 1)
    }

    func testEventKernelAbsentTierRendersNothing() throws {
        let d = try event(tier: nil)
        XCTAssertNil(d.confidenceTier)
        XCTAssertNil(Confidence.normalize(d.confidenceTier))
    }
}
