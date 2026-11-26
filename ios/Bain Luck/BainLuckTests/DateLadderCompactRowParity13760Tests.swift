import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13760: iPhone date-ladder grouped rows match the website's `compactLadderHeadlineRung` rule.
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

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }

    // MARK: - Unit & Parity Rules

    func testCeasefire69603905FollowsWebCompactLadderHeadlineRule() throws {
        let now = utcDate("2026-11-25T12:00:00Z")
        let ceasefire = try decodeMarket([
            "id": 69603905,
            "name": "US x Iran Effective Ceasefire begins by…",
            "llm_sport_category": "politics",
            "top_outcomes": [
                ["id": 1, "name": "December 31", "probability": 0.89, "movement": 0.06],
                ["id": 2, "name": "November 30", "probability": 0.75, "movement": 0.04],
                ["id": 3, "name": "November 22", "probability": 0.61, "movement": 0.02],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "probability": 0.89, "movement": 0.06],
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "probability": 0.61, "movement": 0.02],
                    ["source": "date_bucket", "label": "November 30", "value": 20261130, "probability": 0.75, "movement": 0.04],
                ],
            ],
        ])

        let summary = DiscoverGroupRows.compactSummary(for: ceasefire, now: now)
        XCTAssertEqual(summary.label, "November 30")
        XCTAssertEqual(try XCTUnwrap(summary.probability), 0.75, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(summary.movement), 0.04, accuracy: 0.0001)

        // When top_outcomes only serves December 31, rung falls back to thresholdPoint.movement (never December's)
        let sparseTopOutcomes = try decodeMarket([
            "id": 69603905,
            "name": "US x Iran Effective Ceasefire begins by…",
            "top_outcomes": [
                ["id": 1, "name": "December 31", "probability": 0.89, "movement": 0.06],
            ],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "date_bucket", "label": "November 22", "value": 20261122, "probability": 0.61, "movement": 0.02],
                    ["source": "date_bucket", "label": "November 30", "value": 20261130, "probability": 0.75, "movement": 0.04],
                    ["source": "date_bucket", "label": "December 31", "value": 20261231, "probability": 0.89, "movement": 0.06],
                ],
            ],
        ])
        let sparseSummary = DiscoverGroupRows.compactSummary(for: sparseTopOutcomes, now: now)
        XCTAssertEqual(sparseSummary.label, "November 30")
        XCTAssertEqual(try XCTUnwrap(sparseSummary.probability), 0.75, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(sparseSummary.movement), 0.04, accuracy: 0.0001)
    }

    func testEdgeCasesAllPassedUpcomingBelowEvenYearlessSentinelAndAtLeastLadder() throws {
        let now = utcDate("2026-11-25T12:00:00Z")

        // 1. All rungs passed -> falls back to ruleRung (earliest >= 50%)
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
            source: "date_bucket", label: "Nov 22", value: 20001122,
            unit: "date", direction: nil, probability: 0.55, needsSiblingMarkets: nil
        )
        XCTAssertEqual(DiscoverGroupRows.resolveRungDateIso(point: sentinelPt, distDateIso: nil, now: now), "2026-11-22")
        XCTAssertEqual(DiscoverGroupRows.resolveRungDateIso(point: sentinelPt, distDateIso: "2026-12-05", now: now), "2026-12-05")

        // 5. Non-date atLeastLadder still selects most specific (last) over-even rung
        let atLeast = try decodeMarket([
            "id": 70004,
            "name": "Points scored ladder",
            "top_outcomes": [["id": 1, "name": "Above 100", "probability": 0.91]],
            "discover_card": [
                "suggested_format": "threshold_heatmap",
                "threshold_points": [
                    ["source": "outcome", "label": "Above 100", "value": 100, "probability": 0.91],
                    ["source": "outcome", "label": "Above 150", "value": 150, "probability": 0.63],
                    ["source": "outcome", "label": "Above 200", "value": 200, "probability": 0.32],
                ],
            ],
        ])
        XCTAssertEqual(DiscoverGroupRows.compactSummary(for: atLeast, now: now).label, "Above 150")
    }

    // MARK: - Group Card UI Parity & 390 pt Middle East Ceasefire Sheet

    func testNativeGroupCardRendersUpcomingDateRungAt390AndSourceUsesCompactSummary() throws {
        // Verify NativeCompactFuturesRow routes through DiscoverGroupRows.compactSummary (not topOutcomes?.first)
        let discoverPath = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/DiscoverView.swift")
        let discoverSource = try String(contentsOf: discoverPath, encoding: .utf8)
        let compactRowStart = try XCTUnwrap(discoverSource.range(of: "private struct NativeCompactFuturesRow: View"))
        let compactRowEnd = try XCTUnwrap(discoverSource[compactRowStart.upperBound...].range(of: "private func compactMarketName"))
        let compactRowBody = String(discoverSource[compactRowStart.lowerBound..<compactRowEnd.lowerBound])
        XCTAssertTrue(compactRowBody.contains("DiscoverGroupRows.compactSummary(for: data)"))
        XCTAssertFalse(compactRowBody.contains("topOutcomes?.first"))

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

        let valueNum: (Date) -> Double = { date in
            let c = cal.dateComponents([.year, .month, .day], from: date)
            return Double((c.year ?? 2026) * 10_000 + (c.month ?? 1) * 100 + (c.day ?? 1))
        }

        let passedLabel = labelFmt.string(from: passedDate)
        let targetLabel = labelFmt.string(from: targetDate)
        let lateLabel = labelFmt.string(from: lateDate)

        let ceasefireItem = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
            "type": "futures",
            "score": 88.0,
            "data": [
                "id": 69603905,
                "name": "US x Iran Effective Ceasefire begins by…",
                "llm_sport_category": "politics",
                "top_outcomes": [
                    ["id": 1, "name": lateLabel, "probability": 0.89, "movement": 0.06],
                    ["id": 2, "name": targetLabel, "probability": 0.75, "movement": 0.04],
                    ["id": 3, "name": passedLabel, "probability": 0.61, "movement": 0.02],
                ],
                "discover_card": [
                    "suggested_format": "threshold_heatmap",
                    "threshold_points": [
                        ["source": "date_bucket", "label": passedLabel, "value": valueNum(passedDate), "probability": 0.61, "movement": 0.02],
                        ["source": "date_bucket", "label": targetLabel, "value": valueNum(targetDate), "probability": 0.75, "movement": 0.04],
                        ["source": "date_bucket", "label": lateLabel, "value": valueNum(lateDate), "probability": 0.89, "movement": 0.06],
                    ],
                ],
            ],
        ]))

        let card = NativeGroupCard(
            title: "Middle East",
            items: [ceasefireItem],
            kind: "theme",
            sharedQuestion: "What happens next in the Middle East?",
            navigationPath: .constant(NavigationPath())
        )
        .padding(14)
        .frame(width: 390)
        .background(DS.surface)
        .environment(\.colorScheme, .light)

        let renderer = rendererForMeasurement(card, at: .large)
        renderer.scale = 2.0
        let ocr = recognizeText(in: try XCTUnwrap(renderer.uiImage))
        XCTAssertTrue(ocr.contains(targetLabel), "Expected earliest upcoming over-even date '\(targetLabel)' in OCR: \(ocr)")
        XCTAssertTrue(ocr.contains("75%"), "Expected 75% in OCR: \(ocr)")
        XCTAssertFalse(ocr.contains("89%"), "Must not print loosest rung 89% in OCR: \(ocr)")

        // Optional 390 pt Middle East ceasefire sheet for #13760 (fixed Nov 22 / Nov 30 / Dec 31 specimen)
        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13760_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

            let nov25 = utcDate("2026-11-25T12:00:00Z")
            let fixedCeasefire = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
                "type": "futures",
                "score": 90.0,
                "data": [
                    "id": 69603905,
                    "name": "US x Iran Effective Ceasefire begins by…",
                    "llm_sport_category": "politics",
                    "top_outcomes": [
                        ["id": 1, "name": "December 31", "probability": 0.89, "movement": 0.06],
                        ["id": 2, "name": "November 30", "probability": 0.75, "movement": 0.04],
                        ["id": 3, "name": "November 22", "probability": 0.61, "movement": 0.02],
                    ],
                    "discover_card": [
                        "suggested_format": "threshold_heatmap",
                        "threshold_points": [
                            ["source": "date_bucket", "label": "November 22", "value": 20261122, "probability": 0.61, "movement": 0.02],
                            ["source": "date_bucket", "label": "November 30", "value": 20261130, "probability": 0.75, "movement": 0.04],
                            ["source": "date_bucket", "label": "December 31", "value": 20261231, "probability": 0.89, "movement": 0.06],
                        ],
                    ],
                ],
            ]))
            let siblingDiplomatic = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
                "type": "futures",
                "score": 82.0,
                "data": [
                    "id": 69603999,
                    "name": "US–Iran nuclear deal signed in 2026?",
                    "llm_sport_category": "politics",
                    "top_outcomes": [
                        ["id": 1, "name": "No", "probability": 0.78, "movement": -0.02],
                        ["id": 2, "name": "Yes", "probability": 0.22, "movement": 0.02],
                    ],
                ],
            ]))

            let resolved = DiscoverGroupRows.compactSummary(for: try XCTUnwrap(fixedCeasefire.futures), now: nov25)
            XCTAssertEqual(resolved.label, "November 30")
            XCTAssertEqual(try XCTUnwrap(resolved.probability), 0.75, accuracy: 0.0001)

            // "Before" card replicating old iPhone behavior (topOutcomes.first = December 31 · 89%)
            let beforeItem = try decoder().decode(FeedItem.self, from: JSONSerialization.data(withJSONObject: [
                "type": "futures",
                "score": 90.0,
                "data": [
                    "id": 69603905,
                    "name": "US x Iran Effective Ceasefire begins by…",
                    "llm_sport_category": "politics",
                    "top_outcomes": [
                        ["id": 1, "name": "December 31", "probability": 0.89, "movement": 0.06],
                    ],
                ],
            ]))

            for (schemeName, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
                let surfaceBg = scheme == .dark ? Color.groupedBackground : DS.surface

                let beforeView = NativeGroupCard(
                    title: "Middle East",
                    items: [beforeItem, siblingDiplomatic],
                    kind: "theme",
                    sharedQuestion: "Middle East",
                    navigationPath: .constant(NavigationPath())
                )
                .padding(14)
                .frame(width: 390)
                .background(surfaceBg)
                .environment(\.colorScheme, scheme)

                let afterView = NativeGroupCard(
                    title: "Middle East",
                    items: [fixedCeasefire, siblingDiplomatic],
                    kind: "theme",
                    sharedQuestion: "Middle East",
                    navigationPath: .constant(NavigationPath())
                )
                .padding(14)
                .frame(width: 390)
                .background(surfaceBg)
                .environment(\.colorScheme, scheme)

                let beforeR = rendererForMeasurement(beforeView, at: .large)
                beforeR.scale = 2.0
                try XCTUnwrap(try XCTUnwrap(beforeR.uiImage).pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("before-390-\(schemeName).png")
                )

                let afterR = rendererForMeasurement(afterView, at: .large)
                afterR.scale = 2.0
                try XCTUnwrap(try XCTUnwrap(afterR.uiImage).pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("after-390-\(schemeName).png")
                )
            }
        }
    }
}
