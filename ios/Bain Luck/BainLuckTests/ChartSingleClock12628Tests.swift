import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12628 — a reader outside Pacific Time must see ONE consistent clock across
/// the win probability chart's x-axis ticks, tapped/scrubbed reading readout,
/// soccer 3-line scrub readout, and VoiceOver speech (never an Eastern x-axis
/// under a Pacific `"PT"` tap readout).
@MainActor
final class ChartSingleClock12628Tests: XCTestCase {

    private func makeDate(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    func testSelectedReadingAndXAxisShareOneClockOutsidePacificTime() throws {
        let eastern = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
        let london = try XCTUnwrap(TimeZone(identifier: "Europe/London"))
        let pacific = try XCTUnwrap(TimeZone(identifier: "America/Los_Angeles"))

        // 2026-11-07T01:30:09Z -> Nov 6 8:30:09 PM EST / 5:30:09 PM PST / Nov 7 1:30:09 AM GMT
        let t0 = makeDate("2026-11-07T01:30:09Z")
        let t1 = makeDate("2026-11-07T03:24:00Z")

        let points = [
            ChartDataPoint(date: t0, probability: 0.56, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.74, source: "aggregate"),
        ]
        let rows = EventAtlasChartMarks11666.observationRows(
            dataPoints: points,
            includesOpening: true,
            selectedDate: t0,
            gameStart: t0
        )

        let easternReadout = try XCTUnwrap(
            EventAtlasChartMarks11666.selectedReading(
                rows: rows,
                selectedDate: t0,
                outcomeName: "Knicks",
                includesOpening: true,
                timeZone: eastern
            )
        )
        XCTAssertEqual(easternReadout.timestampTextPT, "Nov 6, 8:30:09 PM EST")
        XCTAssertFalse(easternReadout.timestampTextPT.contains("PT"), "Eastern reader must never see PT")

        var easternCal = Calendar(identifier: .gregorian)
        easternCal.timeZone = eastern
        let domain = t0...t1
        let plan = OddsChartView.xAxisPlan(for: domain, plotWidth: 320, calendar: easternCal)
        let ticks = OddsChartView.xAxisTicks(for: domain, plan: plan, calendar: easternCal)
        XCTAssertFalse(ticks.isEmpty)
        let firstTickFormatted = ticks[0].formatted(plan.format(in: eastern))
            .replacingOccurrences(of: "\u{202F}", with: " ")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        XCTAssertTrue(
            firstTickFormatted.contains("8:") || firstTickFormatted.contains("9:"),
            "Eastern x-axis ticks (\(firstTickFormatted)) must sit in the 8–10 PM EST window, matching the 8:30:09 PM EST scrub readout"
        )

        let londonReadout = try XCTUnwrap(
            EventAtlasChartMarks11666.selectedReading(
                rows: rows,
                selectedDate: t0,
                outcomeName: "Arsenal",
                includesOpening: true,
                timeZone: london
            )
        )
        XCTAssertEqual(londonReadout.timestampTextPT, "Nov 7, 1:30:09 AM GMT")
        XCTAssertEqual(
            EventAtlasChartMarks11666.formatMinuteTimestamp(t0, timeZone: eastern),
            "Nov 6, 8:30 PM EST"
        )
        XCTAssertEqual(
            EventAtlasChartMarks11666.formatExactTimestamp(t0, timeZone: pacific),
            "Nov 6, 5:30:09 PM PT"
        )

        // VoiceOver spoken time via ChartReadoutContext9483 also shares the chart's timezone:
        var ctx = ChartReadoutContext9483.chart(
            playStart: t0,
            gameFinished: false,
            readoutPoints: points,
            checkpoints: nil,
            timeZone: eastern
        )
        ctx.locale = Locale(identifier: "en_US_POSIX")
        ctx.now = t0
        let spoken = ctx.spokenTime(t0)
            .replacingOccurrences(of: "\u{202F}", with: " ")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        XCTAssertEqual(spoken, "8:30 PM")

        // GamePlayCardView wall-clock and dated wall-clock also respect the chart's timezone:
        let playPoint = GamePlayPoint(timestamp: "2026-11-07T01:30:09Z", homeProb: 0.56, awayProb: 0.44)
        let easternWall = playPoint.wallClockDisplay(in: eastern)
            .replacingOccurrences(of: "\u{202F}", with: " ")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        let easternDated = playPoint.datedWallClockDisplay(in: eastern)
            .replacingOccurrences(of: "\u{202F}", with: " ")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
        XCTAssertTrue(easternWall.contains("8:30"), "Expected Eastern wall clock 8:30 PM, got \(easternWall)")
        XCTAssertTrue(easternDated.contains("Fri") && easternDated.contains("8:30"), "Expected Fri 8:30 PM, got \(easternDated)")
        XCTAssertFalse(easternDated.contains("5:30"), "Must not format in Pacific 5:30 PM, got \(easternDated)")
    }

    func testRenderedOddsChartViewInEasternTimeShowsMatchingScrubReadoutAndXAxisClock() throws {
        let eastern = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let history = try decoder.decode(EventHistoryResponse.self, from: Data(#"""
        {
          "event_id": 15350999,
          "home_team": "New York Knicks",
          "away_team": "Boston Celtics",
          "status": "live",
          "commence_time_is_kickoff": true,
          "history": [
            {"timestamp": "2026-11-07T01:30:00Z", "home_probability": 0.52},
            {"timestamp": "2026-11-07T01:45:00Z", "home_probability": 0.58},
            {"timestamp": "2026-11-07T02:15:00Z", "home_probability": 0.64},
            {"timestamp": "2026-11-07T03:00:00Z", "home_probability": 0.71}
          ],
          "win_prob_sources": {
            "polymarket": {"display_name": "Polymarket", "weight": 0.8},
            "kalshi": {"display_name": "Kalshi", "weight": 0.8}
          },
          "win_prob_history": {
            "polymarket": [
              {"timestamp": "2026-11-07T01:30:00Z", "home_probability": 0.51},
              {"timestamp": "2026-11-07T03:00:00Z", "home_probability": 0.70}
            ],
            "kalshi": [
              {"timestamp": "2026-11-07T01:30:00Z", "home_probability": 0.53},
              {"timestamp": "2026-11-07T03:00:00Z", "home_probability": 0.72}
            ]
          }
        }
        """#.utf8))

        let scrubDate = makeDate("2026-11-07T01:45:00Z") // 8:45:00 PM EST (NOT 5:45:00 PM PT!)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let selection = OddsChartSelection()
            selection.select(scrubDate)
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let surface = scheme == .dark ? Color.black : DS.surface

            let root = OddsChartView(
                eventId: 15350999,
                teamColors: (away: Color(hex: "#007A33"), home: Color(hex: "#F58426")),
                commenceTime: "2026-11-07T01:30:00Z",
                status: "live",
                homeTeamName: "New York Knicks",
                awayTeamName: "Boston Celtics",
                homeTeamAbbrev: "NYK",
                awayTeamAbbrev: "BOS",
                sportKey: "basketball_nba",
                selectedRange: .constant(.all),
                preloadedHistory: history,
                selection: selection
            )
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(surface)
            .environment(\.timeZone, eastern)
            .environment(\.colorScheme, scheme)

            let host = hostForMeasurement(root, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 1200))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: max(500, ceil(fitting.height) + 12)))

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = uiStyle
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }

            let until = Date().addingTimeInterval(0.22)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.015))
            } while Date() < until

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }

            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.minimumTextHeight = 0.0
            try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
            let ocrLines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = ocrLines.joined(separator: "\n")
            let compact = joined.replacingOccurrences(of: #"\s+"#, with: "", options: .regularExpression)

            XCTAssertTrue(
                joined.contains("8:45:00 PM EST") || joined.contains("8:45:00 PM") || compact.contains("8:45:00PM"),
                "Expected Eastern scrub readout '8:45:00 PM EST' (\(scheme)); got OCR:\n\(joined)"
            )
            XCTAssertTrue(
                compact.contains("8:29PM") && compact.contains("9:59PM"),
                "Expected Eastern x-axis ticks '8:29 PM' .. '9:59 PM' (\(scheme)); got OCR:\n\(joined)"
            )
            XCTAssertFalse(
                compact.contains("5:45:00PM") || compact.contains("Fri5:45PM") || compact.contains("PMPT") || compact.contains("5:29PM"),
                "Must never show Pacific readout or ticks on an Eastern chart (\(scheme)); got OCR:\n\(joined)"
            )
            XCTAssertFalse(
                ocrLines.contains(where: { $0.contains("…") || $0.contains("...") }),
                "Chart (\(scheme)) must have zero ellipsis; got OCR:\n\(joined)"
            )

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_12628"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let suffix = scheme == .dark ? "dark" : "light"
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("12628-eastern-chart-single-clock-\(suffix)-390.png"))
                }
            }
        }
    }
}
