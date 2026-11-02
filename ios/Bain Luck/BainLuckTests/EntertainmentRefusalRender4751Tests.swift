import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// The production page consumes a decoded category response through its normal
/// view model. No provider/cache I/O or synthetic replacement card renderer.
@MainActor
final class EntertainmentRefusalRender4751Tests: XCTestCase {
    private func payload(section: String, refused: Bool) throws -> EntertainmentResponse {
        let row: [String: Any] = [
            "q": "Synthetic threshold conflict", "market_id": 4751, "src": "kalshi",
            "kind": section == "spotify" ? "spotify" : "rt", "prob": 95,
            "outcome_count": 3, "ladder_treatment_refused": refused,
            "hook": "Above 30 is 95% likely",
            "top_outcomes": [
                ["name": "Above 30", "prob": 95, "delta_24h": 12],
                ["name": "Above 20", "prob": 90], ["name": "Above 10", "prob": 20]
            ]
        ]
        var data: [String: Any] = ["total_markets": 1, "themes": [:],
                                  "by_source": ["kalshi": 1, "polymarket": 0]]
        switch section {
        case "hero": data["trending"] = [row]
        case "spotify": data["themes"] = ["music": ["count": 1, "spotify_race": [row]]]
        case "rt": data["themes"] = ["movies_tv": ["count": 1, "rt_markets": [row]]]
        case "grouped":
            data["themes"] = ["movies_tv": ["count": 2, "rt_markets": [row],
                "rt_groups": [["title": "Coherent sibling", "thresholds": [
                    ["label": "Above 40", "prob": 70, "market_id": 4752]]]]]]
        case "cultural": data["cultural_moments"] = [row]
        case "tech": data["themes"] = ["tech_culture": ["count": 1, "markets": [row]]]
        default: XCTFail("Unknown fixture section \(section)")
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EntertainmentResponse.self, from: JSONSerialization.data(withJSONObject: data))
    }

    private func render(section: String, refused: Bool, size: DynamicTypeSize = .large) async throws -> String {
        let data = try payload(section: section, refused: refused)
        var loads = 0
        let model = EntertainmentViewModel(fetchEntertainment: { loads += 1; return data })
        let page = NavigationStack {
            EntertainmentView(viewModel: model)
                .navigationDestination(for: Route.self) { _ in Text("Fixture destination") }
        }
        .environment(\.colorScheme, .light)
        .environment(\.horizontalSizeClass, .compact)
        let host = hostForMeasurement(page, at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 844))
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        host.view.frame = window.bounds
        // Yield to the real .task loader and layout; this is not a retry loop.
        try await Task.sleep(for: .milliseconds(500))
        host.view.setNeedsLayout(); host.view.layoutIfNeeded()
        XCTAssertEqual(loads, 1, "The mounted page must use the injected loader exactly once")
        XCTAssertEqual(model.data?.totalMarkets, data.totalMarkets)
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let name = "entertainment-4751-\(section)-\(refused ? "refused" : "control")-\(size)"
        let attachment = XCTAttachment(image: image)
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(name + ".png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("ENTERTAINMENT_RENDER: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        print("ENTERTAINMENT_TEXT \(name): \(lines)")
        return lines.joined(separator: " ")
    }

    func testRefusedPricesAreAbsentFromActualPhoneCards() async throws {
        for section in ["hero", "spotify", "rt", "grouped", "cultural", "tech"] {
            let text = try await render(section: section, refused: true)
            XCTAssertTrue(text.contains("Probabilities unavailable"), "\(section): \(text)")
            XCTAssertTrue(text.contains("The threshold probabilities conflict"), "\(section): \(text)")
            XCTAssertFalse(text.contains("95%"), "\(section): \(text)")
            XCTAssertFalse(text.contains("90%"), "\(section): \(text)")
            XCTAssertFalse(text.contains("20%"), "\(section): \(text)")
            XCTAssertFalse(text.contains("Above 30"), "\(section): \(text)")
        }
    }

    func testTheSameRigSeesLegacyPricesWithoutRefusal() async throws {
        let text = try await render(section: "hero", refused: false)
        XCTAssertTrue(text.contains("95%"), text)
        XCTAssertFalse(text.contains("Probabilities unavailable"), text)
    }

    func testRefusalReadsWholeAtLargerText() async throws {
        let text = try await render(section: "hero", refused: true, size: .xxxLarge)
        XCTAssertTrue(text.contains("Probabilities unavailable"), text)
        XCTAssertTrue(text.contains("The threshold probabilities conflict"), text)
    }
}
