import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// 1.0.8 Item 6 — Sub-0.5% single distribution rows print "<1%" instead of "0%"
/// (e.g. `rendered_percent: 0` with `probability: 0.0005`), matching `formatProbability`.
@MainActor
final class DistributionCardSubOnePercent108Tests: XCTestCase {

    func testFormatProbabilityPrintsSubHalfPercentAsLessThanOnePercent() {
        XCTAssertEqual(formatProbability(0.0005, renderedPercent: 0), "<1%")
        XCTAssertEqual(formatProbability(0.004, renderedPercent: 0), "<1%")
        XCTAssertEqual(formatProbability(0.42, renderedPercent: 42), "42%")
    }

    func testDistributionCardRendersLessThanOnePercentNotZeroPercent() async throws {
        let json = """
        {
          "id": 910806,
          "name": "Which movie has biggest opening weekend in 2026?",
          "llm_sport_category": "entertainment",
          "source": "polymarket",
          "source_count": 1,
          "sources": ["polymarket"],
          "market_tier": 2,
          "discover_card": {
            "card_type": "outcome_distribution",
            "distribution_outcomes": [
              { "label": "Avengers: Doomsday", "probability": 0.48, "rendered_percent": 48 },
              { "label": "The Hunger Games: Sunrise on the Reaping", "probability": 0.0005, "rendered_percent": 0 },
              { "label": "Zero Placeholder", "probability": 0.0, "rendered_percent": 0 }
            ]
          }
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let futures = try dec.decode(FeedFuturesData.self, from: Data(json.utf8))

        let view = DistributionCardView(data: futures, navigationPath: .constant(NavigationPath()))
            .padding(16)
            .frame(width: 390)
            .background(DS.cardBg)
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(view, at: .large)
        let h = max(180, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 600)).height), 600))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: h))
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }

        let att = XCTAttachment(image: img)
        att.name = "108-distribution-sub-one-percent-390.png"
        att.lifetime = .keepAlways
        add(att)

        let cgImage = try XCTUnwrap(img.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([req])
        let texts = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let joined = texts.joined(separator: " | ")

        XCTAssertTrue(texts.contains("<1%"), "Expected '<1%' in rendered card, OCR read: \(joined)")
        XCTAssertTrue(texts.contains("48%"), "Expected '48%' in rendered card, OCR read: \(joined)")
        XCTAssertFalse(texts.contains("0%"), "Must never print '0%' for priced sub-1% row, OCR read: \(joined)")
    }
}
