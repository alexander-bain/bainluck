import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Item 4: `HeatMapCardView` must never name a passed date as "More likely than not: <date>"
/// when upcoming rungs exist, and its 5 drawn cells must track that upcoming rung.
@MainActor
final class HeatMapDateLadderPassedDateTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func decodeMarket(_ payload: [String: Any]) throws -> FeedFuturesData {
        try decoder().decode(FeedFuturesData.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    private func utcDate(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    /// Exact served shape for live ceasefire `69603905`.
    private func ceasefire69603905Payload() -> [String: Any] {
        [
            "id": 69603905,
            "name": "US x Iran Effective Ceasefire begins? (2 week pause)",
            "llm_sport_category": "geopolitics",
            "source": "polymarket",
            "status": "open",
            "resolution_date": "2026-12-31T20:29:00+00:00",
            "top_outcomes": [
                ["id": 260868679, "name": "December 31", "probability": 0.87, "rendered_percent": 87],
                ["id": 260851406, "name": "November 30", "probability": 0.745, "rendered_percent": 75],
                ["id": 260868681, "name": "November 22", "probability": 0.615, "rendered_percent": 62],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20001122, "unit": "date", "direction": "before", "probability": 0.615],
                    ["source": "date_bucket", "label": "November 30", "value": 20001130, "unit": "date", "direction": "before", "probability": 0.745],
                    ["source": "date_bucket", "label": "December 31", "value": 20001231, "unit": "date", "direction": "before", "probability": 0.87],
                ],
                "distribution_outcomes": [
                    ["label": "December 31", "probability": 0.87, "date": "2026-12-31"],
                    ["label": "November 30", "probability": 0.745, "date": "2026-11-30"],
                    ["label": "November 22", "probability": 0.615, "date": "2026-11-22"],
                ],
            ],
        ]
    }

    func testCeasefire69603905FullHeatMapCardSkipsPassedNovember22AndNamesNovember30() throws {
        let data = try decodeMarket(ceasefire69603905Payload())

        // After Nov 22 has passed: caption names November 30, never November 22.
        let nov26 = utcDate("2026-11-26T12:00:00Z")
        let cardNov26 = HeatMapCardView(data: data, navigationPath: .constant(NavigationPath()), now: nov26)
        XCTAssertEqual(cardNov26.lastAbove50Label, "November 30")

        // Before Nov 22 passed: caption still names November 22.
        let nov20 = utcDate("2026-11-20T12:00:00Z")
        let cardNov20 = HeatMapCardView(data: data, navigationPath: .constant(NavigationPath()), now: nov20)
        XCTAssertEqual(cardNov20.lastAbove50Label, "November 22")
    }

    func testLongDateLadderWindowCentersOnUpcomingOverEvenRungRatherThanPassedOne() throws {
        let now = utcDate("2026-11-26T12:00:00Z")
        let longCard = try decodeMarket([
            "id": 99969605,
            "name": "Extended ceasefire date ladder",
            "llm_sport_category": "geopolitics",
            "source": "polymarket",
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 10", "value": 20261110, "unit": "date", "probability": 0.55],
                    ["source": "date_bucket", "label": "November 18", "value": 20261118, "unit": "date", "probability": 0.60],
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "unit": "date", "probability": 0.64],
                    ["source": "date_bucket", "label": "November 24", "value": 20261124, "unit": "date", "probability": 0.67],
                    ["source": "date_bucket", "label": "November 25", "value": 20261125, "unit": "date", "probability": 0.69],
                    ["source": "date_bucket", "label": "November 28", "value": 20261128, "unit": "date", "probability": 0.72],
                    ["source": "date_bucket", "label": "December 5", "value": 20261205, "unit": "date", "probability": 0.79],
                    ["source": "date_bucket", "label": "December 15", "value": 20261215, "unit": "date", "probability": 0.85],
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "unit": "date", "probability": 0.91],
                ],
            ],
        ])

        let card = HeatMapCardView(data: longCard, navigationPath: .constant(NavigationPath()), now: now)
        XCTAssertEqual(card.lastAbove50Label, "November 28")
        XCTAssertTrue(card.drawnLabels.contains("November 28"), "Drawn cells must include caption rung: \(card.drawnLabels)")
        XCTAssertEqual(card.drawnLabels, ["November 24", "November 25", "November 28", "December 5", "December 15"])
    }

    func testUpcomingBelow50DoesNotPrintPassedDateAndAllPassedFallsBack() throws {
        let now = utcDate("2026-11-26T12:00:00Z")

        let upcomingBelowEven = try decodeMarket([
            "id": 70011,
            "name": "Ceasefire expired lead",
            "source": "polymarket",
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "unit": "date", "probability": 0.62],
                    ["source": "date_bucket", "label": "November 30", "value": 20261130, "unit": "date", "probability": 0.31],
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "unit": "date", "probability": 0.44],
                ],
            ],
        ])
        XCTAssertNil(HeatMapCardView(data: upcomingBelowEven, navigationPath: .constant(NavigationPath()), now: now).lastAbove50Label)

        let allPassed = try decodeMarket([
            "id": 70012,
            "name": "All past date ladder",
            "source": "polymarket",
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 10", "value": 20261110, "unit": "date", "probability": 0.60],
                    ["source": "date_bucket", "label": "November 20", "value": 20261120, "unit": "date", "probability": 0.90],
                ],
            ],
        ])
        XCTAssertEqual(HeatMapCardView(data: allPassed, navigationPath: .constant(NavigationPath()), now: now).lastAbove50Label, "November 10")
    }

    func testLongDate112818AndNonDate71579121StayUnchanged() throws {
        let now = utcDate("2026-11-26T12:00:00Z")

        let impeach = try decodeMarket([
            "id": 112818,
            "name": "Will the House impeach Trump?",
            "source": "kalshi",
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "Before Jan 1, 2027", "value": 20270101, "unit": "date", "probability": 0.0085],
                    ["source": "date_bucket", "label": "Before Feb 1, 2027", "value": 20270201, "unit": "date", "probability": 0.055],
                    ["source": "date_bucket", "label": "Before Mar 1, 2027", "value": 20270301, "unit": "date", "probability": 0.115],
                    ["source": "date_bucket", "label": "Before Apr 1, 2027", "value": 20270401, "unit": "date", "probability": 0.175],
                    ["source": "date_bucket", "label": "Before May 1, 2027", "value": 20270501, "unit": "date", "probability": 0.255],
                    ["source": "date_bucket", "label": "Before Jun 1, 2027", "value": 20270601, "unit": "date", "probability": 0.365],
                    ["source": "date_bucket", "label": "Before Jul 1, 2027", "value": 20270701, "unit": "date", "probability": 0.375],
                    ["source": "date_bucket", "label": "Before Aug 1, 2027", "value": 20270801, "unit": "date", "probability": 0.445],
                    ["source": "date_bucket", "label": "Before Oct 1, 2027", "value": 20271001, "unit": "date", "probability": 0.51],
                    ["source": "date_bucket", "label": "Before Jan 1, 2028", "value": 20280101, "unit": "date", "probability": 0.605],
                ],
            ],
        ])
        let impeachCard = HeatMapCardView(data: impeach, navigationPath: .constant(NavigationPath()), now: now)
        XCTAssertEqual(impeachCard.lastAbove50Label, "Before Oct 1, 2027")
        XCTAssertTrue(impeachCard.drawnLabels.contains("Before Oct 1, 2027"))

        let amazon = try decodeMarket([
            "id": 71579121,
            "name": "How high will Amazon (AMZN) finish the week of November 23?",
            "source": "polymarket",
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "outcome", "label": "$220", "value": 220.0, "unit": "$", "probability": 0.9065],
                    ["source": "outcome", "label": "$225", "value": 225.0, "unit": "$", "probability": 0.91],
                    ["source": "outcome", "label": "$230", "value": 230.0, "unit": "$", "probability": 0.9075],
                    ["source": "outcome", "label": "$235", "value": 235.0, "unit": "$", "probability": 0.875],
                    ["source": "outcome", "label": "$245", "value": 245.0, "unit": "$", "probability": 0.23],
                ],
            ],
        ])
        let amazonCard = HeatMapCardView(data: amazon, navigationPath: .constant(NavigationPath()), now: now)
        XCTAssertEqual(amazonCard.lastAbove50Label, "$235")
    }

    #if canImport(UIKit)
    func testRenderedCeasefireHeatMapCardCapturesAndOCR() async throws {
        let data = try decodeMarket(ceasefire69603905Payload())
        let nov26 = utcDate("2026-11-26T12:00:00Z")
        let auth = AuthManager(restoreOnInit: false)
        let pins = PinManager(defaults: .standard, allowLegacyGuestPins: false)

        let variants: [(String, CGFloat, ColorScheme, DynamicTypeSize)] = [
            ("after-390-light", 390, .light, .large),
            ("after-390-dark", 390, .dark, .large),
            ("after-390-ax5-light", 390, .light, .accessibility5),
        ]

        let outDir = ProcessInfo.processInfo.environment["TEST_RUNNER_BUILDER_C_RENDER_HEATMAP_DIR"]
            ?? ProcessInfo.processInfo.environment["BUILDER_C_RENDER_HEATMAP_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        for (name, width, scheme, dt) in variants {
            let view = VStack(spacing: 0) {
                HeatMapCardView(data: data, navigationPath: .constant(NavigationPath()), now: nov26)
            }
            .padding(16)
            .background(Color(scheme == .dark ? .black : .systemGroupedBackground))
            .environmentObject(auth)
            .environmentObject(pins)
            .environment(\.colorScheme, scheme)

            let shot = try await captureView(view, width: width, colorScheme: scheme, dynamicTypeSize: dt)
            let ocr = recognizeText(in: shot)
            XCTAssertTrue(ocr.contains("More likely than not"), "\(name) missing caption: \(ocr)")
            XCTAssertTrue(ocr.contains("November 30"), "\(name) must name November 30: \(ocr)")
            XCTAssertFalse(ocr.contains("More likely than not: November 22"), "\(name) must not name passed Nov 22: \(ocr)")

            if let outDir, !outDir.isEmpty {
                try XCTUnwrap(shot.pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("\(name).png")
                )
            }
        }
    }

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) async throws -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: width, alignment: .topLeading)
            .ignoresSafeArea()
            .environment(\.colorScheme, colorScheme)
            .environment(\.horizontalSizeClass, .compact)

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.traitOverrides.preferredContentSizeCategory =
            dynamicTypeSize == .accessibility5 ? .accessibilityExtraExtraExtraLarge : .large

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 2200))
        let height = min(2200, max(80, ceil(measured.height)))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 25_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            let bg: UIColor = colorScheme == .dark ? .black : .systemGroupedBackground
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }
    #endif
}
