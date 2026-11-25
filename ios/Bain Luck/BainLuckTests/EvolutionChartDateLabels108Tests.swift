import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 7(c) — Futures chart crowded date labels ("Nov 19 Nov 21").
/// Verifies `EvolutionChartView.axisTicks` never emits duplicate or overlapping
/// ticks across phone/iPad widths and text sizes, and renders Light/Dark 390 px checks.
@MainActor
final class EvolutionChartDateLabels108Tests: XCTestCase {

    private var utcCalendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(secondsFromGMT: 0)!
        return cal
    }

    private func makeDate(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    private func assertAxisClearsAndHasUniqueLabels(
        dates: [Date],
        plotWidth: CGFloat,
        size: DynamicTypeSize,
        calendar: Calendar,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let maxPointSize = EvolutionChartView.axisLabelPointSize(at: size)
        let axis = EvolutionChartView.axisLayout(
            for: dates,
            plotWidth: plotWidth,
            maxPointSize: maxPointSize,
            calendar: calendar
        )
        let ticks = EvolutionChartView.axisTicks(
            for: dates,
            plotWidth: plotWidth,
            axis: axis,
            calendar: calendar
        )
        XCTAssertFalse(ticks.isEmpty, "axisTicks must not be empty", file: file, line: line)
        guard let lo = dates.min(), let hi = dates.max(), hi > lo, ticks.count >= 2 else {
            return
        }

        let scale = axis.pointSize / EvolutionChartView.axisLabelBasePointSize
        let labelWidth = OddsChartView.xAxisLabelWidth(for: axis.plan.labelStyle) * scale
        let duration = hi.timeIntervalSince(lo)
        let rawPositions = ticks.map {
            CGFloat($0.timeIntervalSince(lo) / duration) * plotWidth
        }
        let centers = OddsChartView.xAxisLabelCenters(
            tickPositions: rawPositions,
            plotWidth: plotWidth,
            labelWidth: labelWidth
        )
        XCTAssertTrue(
            OddsChartView.xAxisLabelsClear(centers: centers, labelWidth: labelWidth),
            "labels collide at plotWidth=\(plotWidth) size=\(size) style=\(axis.plan.labelStyle) centers=\(centers)",
            file: file,
            line: line
        )

        var format = axis.plan.format(in: calendar.timeZone)
        format.calendar = calendar
        let rendered = ticks.map { format.format($0) }
        XCTAssertEqual(
            Set(rendered).count,
            rendered.count,
            "duplicate tick labels \(rendered) at plotWidth=\(plotWidth) size=\(size)",
            file: file,
            line: line
        )
    }

    func testNov15ToNov21AndNearEdgeWindowsNeverCrowdAtPhoneAndIPadWidths() {
        let cal = utcCalendar
        let start = makeDate("2026-11-15T00:00:00Z")
        let endVariants: [Date] = [
            makeDate("2026-11-20T06:00:00Z"),
            makeDate("2026-11-20T18:00:00Z"),
            makeDate("2026-11-21T02:00:00Z"),
            makeDate("2026-11-21T12:00:00Z"),
            makeDate("2026-11-21T20:00:00Z"),
            makeDate("2026-11-22T00:00:00Z"),
        ]
        let plotWidths: [CGFloat] = [180, 200, 222, 260, 302, 360, 600]
        let sizes: [DynamicTypeSize] = [.large, .xxxLarge, .accessibility3, .accessibility5]

        for end in endVariants {
            for plotWidth in plotWidths {
                for size in sizes {
                    assertAxisClearsAndHasUniqueLabels(
                        dates: [start, end],
                        plotWidth: plotWidth,
                        size: size,
                        calendar: cal
                    )
                }
            }
        }
    }

    func testWideRangeOfFuturesSpansClearsWithoutDuplicateOrOverlappingLabels() {
        let cal = utcCalendar
        let start = makeDate("2026-11-15T14:00:00Z")
        let hoursList: [Double] = [2, 12, 24, 36, 72, 120, 156, 168, 336, 720, 2160, 4320]
        let plotWidths: [CGFloat] = [180, 222, 297, 360, 620]
        let sizes: [DynamicTypeSize] = [.large, .xxxLarge, .accessibility5]

        for hours in hoursList {
            let end = start.addingTimeInterval(hours * 3600)
            for plotWidth in plotWidths {
                for size in sizes {
                    assertAxisClearsAndHasUniqueLabels(
                        dates: [start, end],
                        plotWidth: plotWidth,
                        size: size,
                        calendar: cal
                    )
                }
            }
        }
    }

    func testSingleTimestampAndEmptyDatesAreHandledSafely() {
        let cal = utcCalendar
        let single = makeDate("2026-11-21T12:00:00Z")
        let emptyAxis = EvolutionChartView.axisLayout(
            for: [], plotWidth: 222, maxPointSize: 9, calendar: cal
        )
        XCTAssertTrue(
            EvolutionChartView.axisTicks(for: [], plotWidth: 222, axis: emptyAxis, calendar: cal).isEmpty
        )
        let singleAxis = EvolutionChartView.axisLayout(
            for: [single], plotWidth: 222, maxPointSize: 9, calendar: cal
        )
        XCTAssertEqual(
            EvolutionChartView.axisTicks(for: [single], plotWidth: 222, axis: singleAxis, calendar: cal),
            [single]
        )
    }

    func testNov15ToNov21FuturesChartRenders390pxLightAndDarkAtDefaultAndXXXLarge() async throws {
        let timelineJSON = """
        {
          "market_id": 99108,
          "market_name": "2027 NBA Champion",
          "sport_category": "basketball",
          "hours": 168,
          "top": 5,
          "bucket_seconds": 3600,
          "outcomes": [
            { "id": 1, "name": "Oklahoma City Thunder", "current_probability": 0.28, "primary_color": "#007AC1" },
            { "id": 2, "name": "Boston Celtics", "current_probability": 0.22, "primary_color": "#007A33" },
            { "id": 3, "name": "Cleveland Cavaliers", "current_probability": 0.14, "primary_color": "#6F263D" }
          ],
          "timeline": [
            { "timestamp": "2026-11-15T12:00:00Z", "outcomes": { "Oklahoma City Thunder": 0.23, "Boston Celtics": 0.24, "Cleveland Cavaliers": 0.13 } },
            { "timestamp": "2026-11-17T00:00:00Z", "outcomes": { "Oklahoma City Thunder": 0.24, "Boston Celtics": 0.23, "Cleveland Cavaliers": 0.14 } },
            { "timestamp": "2026-11-19T00:00:00Z", "outcomes": { "Oklahoma City Thunder": 0.26, "Boston Celtics": 0.22, "Cleveland Cavaliers": 0.13 } },
            { "timestamp": "2026-11-21T02:00:00Z", "outcomes": { "Oklahoma City Thunder": 0.28, "Boston Celtics": 0.22, "Cleveland Cavaliers": 0.14 } }
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let timeline = try decoder.decode(ProbabilityTimelineResponse.self, from: Data(timelineJSON.utf8))
        let refNow = makeDate("2026-11-21T02:00:00Z")
        let outDir = ProcessInfo.processInfo.environment["EXPORT_108_FUTURES_DATE_LABELS_DIR"]
            ?? ProcessInfo.processInfo.environment["SIMCTL_CHILD_EXPORT_108_FUTURES_DATE_LABELS_DIR"]

        let configs: [(name: String, scheme: ColorScheme, uiStyle: UIUserInterfaceStyle, size: DynamicTypeSize)] = [
            ("108-futures-dates-light-default-390.png", .light, .light, .large),
            ("108-futures-dates-dark-default-390.png", .dark, .dark, .large),
            ("108-futures-dates-light-xxxlarge-390.png", .light, .light, .xxxLarge),
            ("108-futures-dates-dark-xxxlarge-390.png", .dark, .dark, .xxxLarge),
        ]

        for cfg in configs {
            let content = VStack(alignment: .leading, spacing: 8) {
                Text("2027 NBA Champion · \(cfg.name)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                EvolutionChartView(
                    marketId: 99108,
                    hours: 168,
                    headlineContenderNames: ["Oklahoma City Thunder", "Boston Celtics", "Cleveland Cavaliers"],
                    preloadedTimeline: timeline,
                    referenceNow: refNow
                )
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16)
            }
            .padding(.vertical, 12)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))
            .environment(\.colorScheme, cfg.scheme)
            .environment(\.timeZone, TimeZone(secondsFromGMT: 0)!)

            let host = hostForMeasurement(content, at: cfg.size)
            host.additionalSafeAreaInsets = .zero
            host.overrideUserInterfaceStyle = cfg.uiStyle
            let fittedH = max(180, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 1200)).height), 1200))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: fittedH))

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = cfg.uiStyle
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }

            try await Task.sleep(nanoseconds: 220_000_000)
            let until = Date().addingTimeInterval(0.18)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            fmt.opaque = true
            let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                UIColor.systemGroupedBackground.setFill()
                ctx.fill(host.view.bounds)
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            XCTAssertGreaterThan(image.size.height, 150)

            let attachment = XCTAttachment(image: image)
            attachment.name = cfg.name
            attachment.lifetime = .keepAlways
            add(attachment)

            if let outDir, !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let fileURL = dirURL.appendingPathComponent(cfg.name)
                try XCTUnwrap(image.pngData()).write(to: fileURL)
            }
        }
    }
}
