import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #10830 — Condenses `Game odds → Totals` contiguous `.countThreshold`
/// ladders into a compact probability curve + 3-col (2-col `< 340pt`) grid while
/// preserving server order, exact labels/prices, search reachability, focus
/// return, and single-column AX5 fallback.
@MainActor
final class CompactTotalsLadder10830Tests: XCTestCase {

    private func ocrStrings(in image: UIImage) throws -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func rung(
        key: String,
        label: String,
        bound: Double?,
        value: EventQuestionMatrixAdapter.Value = .quoted(0.5),
        kind: QuestionMatrixKind = .countThreshold,
        optionCount: Int = 1,
        periodKey: String = "game",
        periodLabel: String = "Game",
        quantityKey: String = "points",
        relation: String = "gte",
        offersMoreOptions: Bool = false
    ) -> EventQuestionMatrixAdapter.Row {
        let options = (0..<optionCount).map { idx in
            EventQuestionMatrixAdapter.Option(
                selection: QuestionMatrixSelection(scope: .game, questionKey: key, optionKey: "o:\(idx)"),
                label: optionCount == 1 ? "Over \(bound.map { String(format: "%.1f", $0 - 0.5) } ?? "") \(quantityKey)" : "Option \(idx)",
                side: idx == 0 ? "over" : "under",
                value: value,
                observedAt: nil,
                basis: "published_blend",
                result: nil
            )
        }
        return EventQuestionMatrixAdapter.Row(
            id: .init(scope: .game, questionKey: key),
            kind: kind,
            label: label,
            quantity: QuestionMatrixQuantity(key: quantityKey, singular: "point", plural: quantityKey, integer: true),
            period: QuestionMatrixPeriod(key: periodKey, label: periodLabel),
            subject: QuestionMatrixSubject(side: "game", label: "Combined"),
            predicate: bound.map { QuestionMatrixPredicate(relation: relation, bound: $0, line: nil) },
            lifecycle: QuestionMatrixLifecycle(state: "open", marketStatus: "open"),
            options: options,
            missingOptions: [],
            offersMoreOptions: offersMoreOptions,
            complete: !offersMoreOptions,
            optionCounts: nil,
            sourceTotals: []
        )
    }

    func testSegmentGroupsEligibleContiguousRunsAndLeavesOthersUntouched() {
        var rows: [EventQuestionMatrixAdapter.Row] = []
        // 4 contiguous Totals rungs -> 1 ladder segment
        for i in 0..<4 {
            let b = Double(24 + i * 2)
            rows.append(rung(key: "tot-\(i)", label: "\(Int(b))+ points", bound: b, value: .quoted(0.9 - Double(i) * 0.1)))
        }
        // Only 2 consecutive 1H Totals rungs -> kept as 2 individual rows (< minimumRunLength)
        rows.append(rung(key: "h1-0", label: "1H 14+ points", bound: 14, periodKey: "1h", periodLabel: "1st half"))
        rows.append(rung(key: "h1-1", label: "1H 18+ points", bound: 18, periodKey: "1h", periodLabel: "1st half"))
        // Two-option O/U -> individual row
        rows.append(rung(key: "ou", label: "Total 48.5", bound: 48.5, optionCount: 2))
        // offersMoreOptions == true -> individual row
        rows.append(rung(key: "inc", label: "50+ points", bound: 50, offersMoreOptions: true))
        // bound == nil -> individual row
        rows.append(rung(key: "nb", label: "60+ points", bound: nil))
        // spread -> individual row
        rows.append(rung(key: "sp", label: "Spread 3.5", bound: nil, kind: .signedHandicap, optionCount: 2))

        let segments = EventQuestionMatrixLadderGroup10830.segment(rows)
        XCTAssertEqual(segments.count, 7)
        if case .ladder(let group) = segments[0] {
            XCTAssertEqual(group.rungs.count, 4)
            XCTAssertEqual(group.rungs.map(\.bound), [24, 26, 28, 30])
        } else {
            XCTFail("Expected first segment to be a ladder group")
        }
        for i in 1..<segments.count {
            if case .row = segments[i] {
                continue
            }
            XCTFail("Expected segment \(i) to remain an individual row")
        }
    }

    func testChartPointsIgnoreNonQuotedStatesAndSortByBound() {
        let rows = [
            rung(key: "t40", label: "40+ points", bound: 40, value: .won),
            rung(key: "t30", label: "30+ points", bound: 30, value: .quoted(0.72)),
            rung(key: "t35", label: "35+ points", bound: 35, value: .unavailable),
            rung(key: "t20", label: "20+ points", bound: 20, value: .quoted(0.91)),
            rung(key: "t50", label: "50+ points", bound: 50, value: .lost),
        ]
        guard case .ladder(let group)? = EventQuestionMatrixLadderGroup10830.segment(rows).first else {
            return XCTFail("Expected ladder group")
        }
        let points = group.chartPoints
        XCTAssertEqual(points.map(\.bound), [20, 30], "Only quoted rungs enter the curve, sorted ascending")
        XCTAssertEqual(points.map(\.probability), [0.91, 0.72])
    }

    func testWindowingSearchReachabilityColumnsAndFocusReturn() {
        let rows = (0..<38).map { i -> EventQuestionMatrixAdapter.Row in
            let pts = 24 + i * 2
            let p = max(0.02, 0.96 - Double(i) * 0.024)
            return rung(key: "t-\(pts)", label: "\(pts)+ points", bound: Double(pts), value: .quoted(p))
        }
        let segments = EventQuestionMatrixLadderGroup10830.segment(rows)
        XCTAssertEqual(segments.count, 1)
        guard case .ladder(let group) = segments[0] else { return XCTFail("Expected single ladder") }

        XCTAssertEqual(group.visibleRungs(query: "", expanded: false).count, 12)
        XCTAssertEqual(group.visibleRungs(query: "", expanded: true).count, 38)

        // "56+" sits past index 12 (24 + 16*2 = 56) -> search surfaces it immediately
        let searchHits = group.visibleRungs(query: "56+", expanded: false)
        XCTAssertEqual(searchHits.map(\.row.label), ["56+ points"])

        XCTAssertEqual(EventQuestionMatrixLadderGroup10830.columnCount(forWidth: 358), 3)
        XCTAssertEqual(EventQuestionMatrixLadderGroup10830.columnCount(forWidth: 320), 2)

        let visibleCollapsed = EventQuestionMatrixLadderGroup10830.visibleRowIDs(
            forVisibleSegments: [segments[0].id],
            segments: segments,
            expandedLadderIDs: [],
            query: ""
        )
        let firstSelection = rows[0].options[0].selection
        let hiddenSelection = rows[16].options[0].selection
        XCTAssertEqual(
            EventQuestionMatrixSection10238.focusReturnTarget(firstSelection, rows: rows, visibleRowIDs: visibleCollapsed),
            firstSelection
        )
        XCTAssertNil(
            EventQuestionMatrixSection10238.focusReturnTarget(hiddenSelection, rows: rows, visibleRowIDs: visibleCollapsed),
            "Focus must not return to a tile collapsed past the initial 12 rungs"
        )
    }

    private func decodeMatrixWith38TotalsAndSpreads() throws -> EventQuestionMatrix {
        var questions: [[String: Any]] = []
        for i in 0..<38 {
            let pts = 24 + i * 2
            let p = max(0.02, 0.96 - Double(i) * 0.024)
            questions.append([
                "question_key": "tot:\(pts)",
                "display_scope": "game",
                "kind": "count_threshold",
                "label": "\(pts)+ points",
                "quantity": ["key": "points", "singular": "point", "plural": "points", "integer": true],
                "period": ["key": "game", "label": "Game"],
                "subject": ["side": "game", "label": "Combined score"],
                "predicate": ["relation": "gte", "bound": Double(pts)],
                "typing": ["state": "typed"],
                "lifecycle": ["state": "open", "market_status": "open"],
                "complete": true,
                "options": [[
                    "option_key": "over_\(pts)",
                    "label": "Over \(Double(pts) - 0.5) points",
                    "side": "over",
                    "published": [
                        "value": p,
                        "value_state": "quoted",
                        "basis": "published_blend",
                    ],
                ]],
            ])
        }
        questions.append([
            "question_key": "spread:3.5",
            "display_scope": "game",
            "kind": "signed_handicap",
            "label": "Spread 3.5",
            "period": ["key": "game", "label": "Game"],
            "typing": ["state": "typed"],
            "lifecycle": ["state": "open", "market_status": "open"],
            "complete": true,
            "options": [
                [
                    "option_key": "ncsu",
                    "label": "NC State -3.5",
                    "side": "away",
                    "published": ["value": 0.58, "value_state": "quoted", "basis": "published_blend"],
                ],
                [
                    "option_key": "stan",
                    "label": "Stanford +3.5",
                    "side": "home",
                    "published": ["value": 0.42, "value_state": "quoted", "basis": "published_blend"],
                ],
            ],
        ])

        let payload: [String: Any] = [
            "contract": "10238.v1",
            "display_scope": "game",
            "questions": questions,
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventQuestionMatrix.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    func testTotalsLadderRendersCompactCurveAndGridAndReadableAX5() async throws {
        let matrix = try decodeMatrixWith38TotalsAndSpreads()

        let variants: [(name: String, scheme: ColorScheme, textSize: DynamicTypeSize)] = [
            ("10830-totals-ladder-light-390.png", .light, .large),
            ("10830-totals-ladder-dark-390.png", .dark, .large),
            ("10830-totals-ladder-ax5-390.png", .light, .accessibility5),
        ]

        var defaultHeight: CGFloat = 0
        var ax5Height: CGFloat = 0

        for variant in variants {
            let view = EventQuestionMatrixSection10238(matrix: matrix, scope: .game)
                .padding(14)
                .background(Color.pageBackground)
                .frame(width: 390, alignment: .topLeading)
                .environment(\.colorScheme, variant.scheme)
                .environment(\.dynamicTypeSize, variant.textSize)
                .environment(\.horizontalSizeClass, .compact)

            let host = hostForMeasurement(view, at: variant.textSize)
            host.overrideUserInterfaceStyle = variant.scheme == .dark ? .dark : .light
            let scene = try XCTUnwrap(
                UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
            )
            let existing = scene.windows
            existing.forEach { $0.isHidden = true }
            let window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: 390, height: 1200)
            window.overrideUserInterfaceStyle = variant.scheme == .dark ? .dark : .light
            window.rootViewController = host
            window.makeKeyAndVisible()
            defer {
                window.isHidden = true
                window.rootViewController = nil
                existing.forEach { $0.isHidden = false }
            }

            host.view.frame = window.bounds
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                await Task.yield()
                try await Task.sleep(for: .milliseconds(30))
            }

            let fitted = host.sizeThatFits(in: CGSize(width: 390, height: 2400))
            if variant.textSize == .large {
                defaultHeight = max(defaultHeight, fitted.height)
                XCTAssertLessThan(fitted.height, 700, "Condensed Totals curve + 3-col grid should fit well below 700 pt: \(fitted.height)")
            } else {
                ax5Height = fitted.height
                XCTAssertGreaterThan(fitted.height, 700, "AX5 stacked fallback should expand cleanly without collapse")
            }

            let maxRenderHeight: CGFloat = variant.textSize == .accessibility5 ? 2000 : 1400
            let bounds = CGRect(x: 0, y: 0, width: 390, height: min(maxRenderHeight, ceil(fitted.height)))
            window.frame = bounds
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()
            try await Task.sleep(for: .milliseconds(30))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let image = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
                if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                    window.layer.render(in: ctx.cgContext)
                }
            }

            if let dir = ProcessInfo.processInfo.environment["RENDER_10830_DIR"], !dir.isEmpty {
                try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                let url = URL(fileURLWithPath: dir).appendingPathComponent(variant.name)
                try XCTUnwrap(image.pngData()).write(to: url)
            }

            let ocr = try ocrStrings(in: image).joined(separator: " | ")
            XCTAssertTrue(ocr.contains("Game odds"), "Missing section title in \(variant.name): \(ocr)")
            XCTAssertTrue(ocr.contains("Totals"), "Missing Totals family pill in \(variant.name): \(ocr)")
            XCTAssertTrue(ocr.contains("24+ points"), "Missing first rung in \(variant.name): \(ocr)")
            XCTAssertTrue(ocr.contains("12 of 38 lines"), "Missing rung count status in \(variant.name): \(ocr)")
            XCTAssertFalse(ocr.contains("…") || ocr.contains("..."), "Unexpected ellipsis truncation in \(variant.name): \(ocr)")
        }

        XCTAssertLessThan(defaultHeight, ax5Height)
    }
}
