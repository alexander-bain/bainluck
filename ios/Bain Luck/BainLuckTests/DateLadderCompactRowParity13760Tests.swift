import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// #13760: iPhone date-ladder grouped rows skip passed dates using `compactLadderHeadlineRung`,
/// across every priced date rung in served order, while leaving non-date ladders as master (`markedRung`).
@MainActor
final class DateLadderCompactRowParity13760Tests: XCTestCase {

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

    // MARK: - Server-Shape Fixtures

    /// Exact served shape for live market `69603905` (`US x Iran Effective Ceasefire begins?`),
    /// where `threshold_points` carry yearless `2000MMDD` sentinels and `distribution_outcomes`
    /// carry the real `YYYY-MM-DD` calendar dates.
    private func ceasefire69603905Payload(
        includeSparseTopOutcomesOnly: Bool = false
    ) -> [String: Any] {
        let topOutcomes: [[String: Any]] = includeSparseTopOutcomesOnly
            ? [["id": 260868679, "name": "December 31", "probability": 0.87, "movement": 0.06, "rendered_percent": 87]]
            : [
                ["id": 260868679, "name": "December 31", "probability": 0.87, "movement": 0.06, "rendered_percent": 87],
                ["id": 260851406, "name": "November 30", "probability": 0.745, "movement": 0.04, "rendered_percent": 75],
                ["id": 260868681, "name": "November 22", "probability": 0.615, "movement": 0.02, "rendered_percent": 62],
            ]

        return [
            "id": 69603905,
            "name": "US x Iran Effective Ceasefire begins? (2 week pause)",
            "llm_sport_category": "geopolitics",
            "source": "polymarket",
            "top_outcomes": topOutcomes,
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20001122, "unit": "date", "direction": "before", "probability": 0.615, "movement": 0.02],
                    ["source": "date_bucket", "label": "November 30", "value": 20001130, "unit": "date", "direction": "before", "probability": 0.745, "movement": 0.04],
                    ["source": "date_bucket", "label": "December 31", "value": 20001231, "unit": "date", "direction": "before", "probability": 0.87, "movement": 0.06],
                ],
                "distribution_outcomes": [
                    ["label": "December 31", "probability": 0.87, "date": "2026-12-31"],
                    ["label": "November 30", "probability": 0.745, "date": "2026-11-30"],
                    ["label": "November 22", "probability": 0.615, "date": "2026-11-22"],
                ],
            ],
        ]
    }

    // MARK: - Unit & Parity Rules

    func testCeasefire69603905ServerShapeSkipsPassedDateAndPreservesMovement() throws {
        let now = utcDate("2026-11-26T12:00:00Z")
        let ceasefire = try decodeMarket(ceasefire69603905Payload())

        let summary = DiscoverGroupRows.compactSummary(for: ceasefire, now: now)
        XCTAssertEqual(summary.label, "November 30")
        XCTAssertEqual(try XCTUnwrap(summary.probability), 0.745, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(summary.movement), 0.04, accuracy: 0.0001)

        // When top_outcomes only serves December 31, rung falls back to thresholdPoint.movement (never December's)
        let sparseCeasefire = try decodeMarket(ceasefire69603905Payload(includeSparseTopOutcomesOnly: true))
        let sparseSummary = DiscoverGroupRows.compactSummary(for: sparseCeasefire, now: now)
        XCTAssertEqual(sparseSummary.label, "November 30")
        XCTAssertEqual(try XCTUnwrap(sparseSummary.probability), 0.745, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(sparseSummary.movement), 0.04, accuracy: 0.0001)
    }

    func testGuardCase112818LongDateLadderEvaluatesEveryPricedRungPastEight() throws {
        let now = utcDate("2026-11-26T12:00:00Z")
        let impeach = try decodeMarket([
            "id": 112818,
            "name": "Will the House impeach Trump?",
            "llm_sport_category": "politics",
            "source": "kalshi",
            "top_outcomes": [
                ["id": 1625535, "name": "Before Jan 1, 2028", "probability": 0.605, "rendered_percent": 61],
                ["id": 245386017, "name": "Before Oct 1, 2027", "probability": 0.51, "rendered_percent": 51],
                ["id": 253568048, "name": "Before Aug 1, 2027", "probability": 0.445, "rendered_percent": 45],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "Before Jan 1, 2027", "value": 20270101, "unit": "date", "direction": "before", "probability": 0.0085],
                    ["source": "date_bucket", "label": "Before Feb 1, 2027", "value": 20270201, "unit": "date", "direction": "before", "probability": 0.055],
                    ["source": "date_bucket", "label": "Before Mar 1, 2027", "value": 20270301, "unit": "date", "direction": "before", "probability": 0.115],
                    ["source": "date_bucket", "label": "Before Apr 1, 2027", "value": 20270401, "unit": "date", "direction": "before", "probability": 0.175],
                    ["source": "date_bucket", "label": "Before May 1, 2027", "value": 20270501, "unit": "date", "direction": "before", "probability": 0.255],
                    ["source": "date_bucket", "label": "Before Jun 1, 2027", "value": 20270601, "unit": "date", "direction": "before", "probability": 0.365],
                    ["source": "date_bucket", "label": "Before Jul 1, 2027", "value": 20270701, "unit": "date", "direction": "before", "probability": 0.375],
                    ["source": "date_bucket", "label": "Before Aug 1, 2027", "value": 20270801, "unit": "date", "direction": "before", "probability": 0.445],
                    ["source": "date_bucket", "label": "Before Oct 1, 2027", "value": 20271001, "unit": "date", "direction": "before", "probability": 0.51],
                    ["source": "date_bucket", "label": "Before Jan 1, 2028", "value": 20280101, "unit": "date", "direction": "before", "probability": 0.605],
                ],
            ],
        ])

        let summary = DiscoverGroupRows.compactSummary(for: impeach, now: now)
        let masterRung = DiscoverGroupRows.markedRung(in: try XCTUnwrap(impeach.discoverCard?.thresholdPoints))
        XCTAssertEqual(summary.label, "Before Oct 1, 2027")
        XCTAssertEqual(masterRung?.label, "Before Oct 1, 2027")
        XCTAssertEqual(try XCTUnwrap(summary.probability), 0.51, accuracy: 0.0001)
    }

    func testGuardCase71579121NonDateLadderMatchesMasterMarkedRung() throws {
        let now = utcDate("2026-11-26T12:00:00Z")
        let amazon = try decodeMarket([
            "id": 71579121,
            "name": "How high will Amazon (AMZN) finish the week of November 23?",
            "llm_sport_category": "economics",
            "source": "polymarket",
            "top_outcomes": [
                ["id": 270678946, "name": "$225", "probability": 0.91, "rendered_percent": 91],
                ["id": 270678947, "name": "$230", "probability": 0.9075, "rendered_percent": 91],
                ["id": 270678945, "name": "$220", "probability": 0.9065, "rendered_percent": 91],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "outcome", "label": "$220", "value": 220.0, "unit": "$", "direction": "exact", "probability": 0.9065],
                    ["source": "outcome", "label": "$225", "value": 225.0, "unit": "$", "direction": "exact", "probability": 0.91],
                    ["source": "outcome", "label": "$230", "value": 230.0, "unit": "$", "direction": "exact", "probability": 0.9075],
                    ["source": "outcome", "label": "$235", "value": 235.0, "unit": "$", "direction": "exact", "probability": 0.875],
                    ["source": "outcome", "label": "$240", "value": 240.0, "unit": "$", "direction": "exact", "probability": NSNull()],
                    ["source": "outcome", "label": "$245", "value": 245.0, "unit": "$", "direction": "exact", "probability": 0.23],
                    ["source": "outcome", "label": "$255", "value": 255.0, "unit": "$", "direction": "exact", "probability": 0.103],
                    ["source": "outcome", "label": "$260", "value": 260.0, "unit": "$", "direction": "exact", "probability": 0.082],
                    ["source": "outcome", "label": "$265", "value": 265.0, "unit": "$", "direction": "exact", "probability": 0.0825],
                    ["source": "outcome", "label": "$270", "value": 270.0, "unit": "$", "direction": "exact", "probability": 0.083],
                    ["source": "outcome", "label": "$275", "value": 275.0, "unit": "$", "direction": "exact", "probability": 0.082],
                ],
            ],
        ])

        let summary = DiscoverGroupRows.compactSummary(for: amazon, now: now)
        let pricedPoints = (amazon.discoverCard?.thresholdPoints ?? []).filter { $0.probability != nil }
        let masterRung = DiscoverGroupRows.markedRung(in: pricedPoints)
        XCTAssertEqual(masterRung?.label, "$235")
        XCTAssertEqual(summary.label, "$235")
        XCTAssertEqual(try XCTUnwrap(summary.probability), 0.875, accuracy: 0.0001)
    }

    func testEqualValueTiesPreserveServedOrderDeterministically() throws {
        let now = utcDate("2026-11-26T12:00:00Z")
        let tied = try decodeMarket([
            "id": 60527872,
            "name": "Tied date-value rungs",
            "top_outcomes": [
                ["id": 1, "name": "Second Served", "probability": 0.70],
                ["id": 2, "name": "First Served", "probability": 0.55],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "First Served", "value": 20261201, "probability": 0.55],
                    ["source": "date_bucket", "label": "Second Served", "value": 20261201, "probability": 0.70],
                ],
                "distribution_outcomes": [
                    ["label": "First Served", "probability": 0.55, "date": "2026-12-01"],
                    ["label": "Second Served", "probability": 0.70, "date": "2026-12-01"],
                ],
            ],
        ])
        for _ in 0..<10 {
            XCTAssertEqual(DiscoverGroupRows.compactSummary(for: tied, now: now).label, "First Served")
        }
    }

    func testEdgeCasesAllPassedUpcomingBelowEvenAndYearlessSentinel() throws {
        let now = utcDate("2026-11-26T12:00:00Z")

        // 1. All rungs passed -> falls back to earliest >= 50%
        let allPassed = try decodeMarket([
            "id": 70001,
            "name": "Past ladder",
            "top_outcomes": [["id": 1, "name": "November 20", "probability": 0.90]],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 10", "value": 20261110, "probability": 0.60],
                    ["source": "date_bucket", "label": "November 20", "value": 20261120, "probability": 0.90],
                ],
            ],
        ])
        XCTAssertEqual(DiscoverGroupRows.compactSummary(for: allPassed, now: now).label, "November 10")

        // 2. Upcoming rungs all < 50%, passed rung controlled headline -> highest upcoming rung
        let passedControlled = try decodeMarket([
            "id": 70002,
            "name": "Ceasefire expired lead",
            "top_outcomes": [["id": 1, "name": "November 22", "probability": 0.62]],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "probability": 0.62],
                    ["source": "date_bucket", "label": "November 30", "value": 20261130, "probability": 0.31],
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "probability": 0.44],
                ],
            ],
        ])
        let passedControlledSummary = DiscoverGroupRows.compactSummary(for: passedControlled, now: now)
        XCTAssertEqual(passedControlledSummary.label, "December 31")
        XCTAssertEqual(try XCTUnwrap(passedControlledSummary.probability), 0.44, accuracy: 0.0001)

        // 3. Upcoming rungs all < 50%, no passed rung controlled -> retain served leader
        let noPassedControl = try decodeMarket([
            "id": 70003,
            "name": "Low probability ladder",
            "top_outcomes": [["id": 1, "name": "December 31", "probability": 0.42]],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "probability": 0.10],
                    ["source": "date_bucket", "label": "November 30", "value": 20261130, "probability": 0.25],
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "probability": 0.42],
                ],
            ],
        ])
        XCTAssertEqual(DiscoverGroupRows.compactSummary(for: noPassedControl, now: now).label, "December 31")

        // 4. Yearless 2000MMDD sentinel resolution & distribution date override
        let sentinelPt = FeedDiscoverThresholdPoint(
            source: "date_bucket", label: "November 22", value: 20001122,
            unit: "date", direction: "before", probability: 0.615, needsSiblingMarkets: nil
        )
        XCTAssertEqual(DiscoverGroupRows.resolveRungDateIso(point: sentinelPt, distDateIso: nil, now: now), "2026-11-22")
        XCTAssertEqual(DiscoverGroupRows.resolveRungDateIso(point: sentinelPt, distDateIso: "2026-12-05", now: now), "2026-12-05")
    }

    // MARK: - Group Card UI Parity & 390 pt Middle East Ceasefire Sheet

    #if canImport(UIKit)
    func testNativeGroupCardRendersUpcomingDateRungAt390AndEmitsSheet() async throws {
        // Relative-date NativeGroupCard OCR assertion (resilient across any CI run date)
        let utc = TimeZone(identifier: "UTC")!
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = utc
        let today = Date()
        let passedDate = cal.date(byAdding: .day, value: -3, to: today)!
        let targetDate = cal.date(byAdding: .day, value: 5, to: today)!
        let lateDate = cal.date(byAdding: .day, value: 36, to: today)!

        let labelFmt = DateFormatter()
        labelFmt.locale = Locale(identifier: "en_US_POSIX")
        labelFmt.timeZone = utc
        labelFmt.dateFormat = "MMMM d"

        let isoFmt = DateFormatter()
        isoFmt.locale = Locale(identifier: "en_US_POSIX")
        isoFmt.timeZone = utc
        isoFmt.dateFormat = "yyyy-MM-dd"

        let sentinelNum: (Date) -> Double = { date in
            let c = cal.dateComponents([.month, .day], from: date)
            return Double(2000 * 10_000 + (c.month ?? 1) * 100 + (c.day ?? 1))
        }

        let passedLabel = labelFmt.string(from: passedDate)
        let targetLabel = labelFmt.string(from: targetDate)
        let lateLabel = labelFmt.string(from: lateDate)

        let ceasefireItem = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
            "type": "futures",
            "score": 88.0,
            "data": [
                "id": 69603905,
                "name": "US x Iran Effective Ceasefire begins? (2 week pause)",
                "llm_sport_category": "geopolitics",
                "source": "polymarket",
                "top_outcomes": [
                    ["id": 260868679, "name": lateLabel, "probability": 0.87, "rendered_percent": 87],
                    ["id": 260851406, "name": targetLabel, "probability": 0.745, "rendered_percent": 75],
                    ["id": 260868681, "name": passedLabel, "probability": 0.615, "rendered_percent": 62],
                ],
                "discover_card": [
                    "suggested_format": "threshold_heatmap",
                    "threshold_points": [
                        ["source": "date_bucket", "label": passedLabel, "value": sentinelNum(passedDate), "unit": "date", "direction": "before", "probability": 0.615],
                        ["source": "date_bucket", "label": targetLabel, "value": sentinelNum(targetDate), "unit": "date", "direction": "before", "probability": 0.745],
                        ["source": "date_bucket", "label": lateLabel, "value": sentinelNum(lateDate), "unit": "date", "direction": "before", "probability": 0.87],
                    ],
                    "distribution_outcomes": [
                        ["label": lateLabel, "probability": 0.87, "date": isoFmt.string(from: lateDate)],
                        ["label": targetLabel, "probability": 0.745, "date": isoFmt.string(from: targetDate)],
                        ["label": passedLabel, "probability": 0.615, "date": isoFmt.string(from: passedDate)],
                    ],
                ],
            ],
        ]))

        let card = NativeGroupCard(
            title: "Middle East",
            items: [ceasefireItem],
            kind: "theme",
            sharedQuestion: "Where is the Middle East conflict heading?",
            navigationPath: .constant(NavigationPath())
        )
        .padding(14)
        .background(DS.surface)
        .environment(\.colorScheme, .light)

        let img = try await captureView(card, width: 390, colorScheme: .light, dynamicTypeSize: .large)
        let ocr = recognizeText(in: img)
        XCTAssertTrue(ocr.contains(targetLabel), "Expected earliest upcoming over-even date '\(targetLabel)' in OCR: \(ocr)")
        XCTAssertTrue(ocr.contains("75%"), "Expected 75% in OCR: \(ocr)")
        XCTAssertFalse(ocr.contains("87%"), "Must not print loosest rung 87% in OCR: \(ocr)")

        // Render AFTER panels for #13835 sheet using real live Middle East members (113232 + 69603905)
        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13760_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

            let fixedCeasefire = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
                "type": "futures",
                "score": 90.0,
                "data": ceasefire69603905Payload(),
            ]))
            // Real live Middle East group sibling (feed market 113232, Nov 26)
            let realSiblingInvadeIran = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
                "type": "futures",
                "score": 95.0,
                "data": [
                    "id": 113232,
                    "name": "Will the U.S. invade Iran before 2027?",
                    "llm_sport_category": "politics",
                    "source": "polymarket",
                    "top_outcomes": [
                        ["id": 1628892, "name": "Yes", "probability": 0.055, "rendered_percent": 6],
                    ],
                ],
            ]))

            for (label, width, scheme, dt): (String, CGFloat, ColorScheme, DynamicTypeSize) in [
                ("after-390-light", 390, .light, .large),
                ("after-390-dark", 390, .dark, .large),
                ("after-320-light", 320, .light, .large),
            ] {
                let surfaceBg = scheme == .dark ? Color.groupedBackground : DS.surface
                let afterView = NativeGroupCard(
                    title: "Middle East",
                    items: [realSiblingInvadeIran, fixedCeasefire],
                    kind: "theme",
                    sharedQuestion: "Where is the Middle East conflict heading?",
                    navigationPath: .constant(NavigationPath())
                )
                .padding(14)
                .background(surfaceBg)
                .environment(\.colorScheme, scheme)

                let shot = try await captureView(afterView, width: width, colorScheme: scheme, dynamicTypeSize: dt)
                try XCTUnwrap(shot.pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("\(label).png")
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

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 1800))
        let height = min(1800, max(80, ceil(measured.height)))
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
