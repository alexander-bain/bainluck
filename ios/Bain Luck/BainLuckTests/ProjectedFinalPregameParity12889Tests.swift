import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12889 — iPhone parity with web #12890 (`fd47b36961`) on Event 15350164
/// (`Portland Trail Blazers at Minnesota Timberwolves`):
/// 1. Before a game (`phase == .before`), fit the Y-axis to the projections with
///    breathing room (`105..120` for `111..115.5`), keeping `0..yMax` during & after.
/// 2. No X-axis time label is ever cut (`"1…"`); labels inset inside the plot or drop.
/// 3. Print the page's own whole-number pair (`111 projected` and `114 projected`)
///    before and during the game, not the one sportsbook's `114.5` line.
@MainActor
final class ProjectedFinalPregameParity12889Tests: XCTestCase {

    private static let asOf = ISO8601DateFormatter().date(from: "2026-11-17T21:58:00Z")!

    private static let event15350164DetailJSON = """
    {
      "id": 15350164,
      "sport": "basketball_nba",
      "home_team": "Minnesota Timberwolves",
      "away_team": "Portland Trail Blazers",
      "commence_time": "2026-11-18T01:00:00+00:00",
      "status": "scheduled",
      "home_team_data": {
        "team_id": 106,
        "slug": "minnesota-timberwolves",
        "primary_color": "#266092",
        "secondary_color": "#79bc43",
        "record": "10-4",
        "abbreviation": "MIN"
      },
      "away_team_data": {
        "team_id": 104,
        "slug": "portland-trail-blazers",
        "primary_color": "#e03a3e",
        "secondary_color": "#000000",
        "record": "9-4",
        "abbreviation": "POR"
      },
      "current_odds": {
        "captured_at": "2026-11-17T21:48:50.235110+00:00",
        "home_probability": 0.5627,
        "away_probability": 0.4373,
        "away_rendered_percent": 44,
        "home_rendered_percent": 56,
        "spread": -3.2,
        "over_under": 225.2,
        "projected_home_score": 114.2,
        "projected_away_score": 111.0,
        "bookmaker_count": 18,
        "projection_captured_at": "2026-11-17T20:55:54.925052+00:00",
        "projection_bookmaker_count": 12
      },
      "hero_probability": 0.5627,
      "hero_probability_away": 0.4373,
      "hero_probability_source": "blend",
      "source_mark": {
        "state": "blend",
        "sources": [
          {"key": "kalshi", "name": "Kalshi", "probability": 0.555, "observed_at": null},
          {"key": "polymarket", "name": "Polymarket", "probability": 0.565, "observed_at": null},
          {"key": "betting", "name": "Sportsbooks", "probability": 0.5627, "observed_at": "2026-11-17T21:48:50.048920Z", "count": 12}
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    private static let event15350164HistoryJSON = """
    {
      "event_id": 15350164,
      "home_team": "Minnesota Timberwolves",
      "away_team": "Portland Trail Blazers",
      "status": "scheduled",
      "completed_at": null,
      "history": [],
      "score_history": [],
      "period_markers": [],
      "bookmaker_history": {
        "draftkings": [
          {"timestamp":"2026-11-17T03:55:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T03:55:31.634764+00:00"},
          {"timestamp":"2026-11-17T05:08:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T05:08:57.107306+00:00"},
          {"timestamp":"2026-11-17T05:42:00+00:00","home_probability":0.54,"projected_home_score":null,"projected_away_score":null,"kind":"recorded","observed_at":"2026-11-17T05:42:06.433339+00:00"},
          {"timestamp":"2026-11-17T06:07:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T06:07:12.891358+00:00"},
          {"timestamp":"2026-11-17T07:07:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T07:07:16.642438+00:00"},
          {"timestamp":"2026-11-17T08:11:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T08:11:29.298378+00:00"},
          {"timestamp":"2026-11-17T09:06:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T09:06:57.271702+00:00"},
          {"timestamp":"2026-11-17T10:10:00+00:00","home_probability":0.54,"projected_home_score":114.5,"projected_away_score":112.0,"kind":"recorded","observed_at":"2026-11-17T10:10:10.715694+00:00"},
          {"timestamp":"2026-11-17T11:12:00+00:00","home_probability":0.55,"projected_home_score":115.0,"projected_away_score":112.5,"kind":"recorded","observed_at":"2026-11-17T11:12:25.060501+00:00"},
          {"timestamp":"2026-11-17T12:11:00+00:00","home_probability":0.55,"projected_home_score":115.0,"projected_away_score":113.5,"kind":"recorded","observed_at":"2026-11-17T12:11:33.830890+00:00"},
          {"timestamp":"2026-11-17T13:09:00+00:00","home_probability":0.5514,"projected_home_score":115.0,"projected_away_score":112.5,"kind":"recorded","observed_at":"2026-11-17T13:09:13.395367+00:00"},
          {"timestamp":"2026-11-17T13:35:00+00:00","home_probability":0.5514,"projected_home_score":null,"projected_away_score":null,"kind":"recorded","observed_at":"2026-11-17T13:35:25.742551+00:00"},
          {"timestamp":"2026-11-17T14:06:00+00:00","home_probability":0.5514,"projected_home_score":115.0,"projected_away_score":113.5,"kind":"recorded","observed_at":"2026-11-17T14:06:59.740821+00:00"},
          {"timestamp":"2026-11-17T15:05:00+00:00","home_probability":0.5427,"projected_home_score":115.5,"projected_away_score":113.0,"kind":"recorded","observed_at":"2026-11-17T15:05:25.417977+00:00"},
          {"timestamp":"2026-11-17T16:08:00+00:00","home_probability":0.5427,"projected_home_score":115.0,"projected_away_score":113.5,"kind":"recorded","observed_at":"2026-11-17T16:08:33.172290+00:00"},
          {"timestamp":"2026-11-17T17:06:00+00:00","home_probability":0.5427,"projected_home_score":115.0,"projected_away_score":113.5,"kind":"recorded","observed_at":"2026-11-17T17:06:18.536655+00:00"},
          {"timestamp":"2026-11-17T18:06:00+00:00","home_probability":0.5427,"projected_home_score":114.5,"projected_away_score":113.0,"kind":"recorded","observed_at":"2026-11-17T18:06:42.120524+00:00"},
          {"timestamp":"2026-11-17T19:04:00+00:00","home_probability":0.5325,"projected_home_score":114.5,"projected_away_score":113.0,"kind":"recorded","observed_at":"2026-11-17T19:04:35.774116+00:00"},
          {"timestamp":"2026-11-17T19:27:00+00:00","home_probability":0.5696,"projected_home_score":null,"projected_away_score":null,"kind":"recorded","observed_at":"2026-11-17T19:27:36.829290+00:00"},
          {"timestamp":"2026-11-17T19:59:00+00:00","home_probability":0.5696,"projected_home_score":114.5,"projected_away_score":111.0,"kind":"recorded","observed_at":"2026-11-17T19:59:51.451047+00:00"},
          {"timestamp":"2026-11-17T20:05:00+00:00","home_probability":0.5696,"projected_home_score":null,"projected_away_score":null,"kind":"recorded","observed_at":"2026-11-17T20:05:26.911787+00:00"},
          {"timestamp":"2026-11-17T20:55:00+00:00","home_probability":0.5696,"projected_home_score":114.5,"projected_away_score":111.0,"kind":"recorded","observed_at":"2026-11-17T20:55:54.840991+00:00"},
          {"timestamp":"2026-11-17T21:01:00+00:00","home_probability":0.5696,"projected_home_score":null,"projected_away_score":null,"kind":"recorded","observed_at":"2026-11-17T21:01:35.797547+00:00"}
        ]
      }
    }
    """

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    func testEvent15350164FitsPregameYAxisSkipsH2HNullsAndPrintsWholeNumberPagePair() throws {
        let detail = try decode(EventDetail.self, Self.event15350164DetailJSON)
        let history = try decode(EventHistoryResponse.self, Self.event15350164HistoryJSON)

        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: detail.sport,
            eventStatus: detail.status,
            history: history,
            finalHome: nil,
            finalAway: nil,
            asOf: Self.asOf
        ))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))

        // 1. Fitted pregame Y-axis matching web #12890 (`105..120`, step `5`).
        XCTAssertEqual(series.phase, .before)
        XCTAssertEqual(series.yMin, 105)
        XCTAssertEqual(series.yMax, 120)
        XCTAssertEqual(series.yTicks, [105, 110, 115, 120])

        // Pregame h2h-only nil/nil rows are skipped, and hourly spread/total captures hold across <=2h.
        XCTAssertTrue(series.withheld.isEmpty)
        XCTAssertFalse(series.latestIntervalUnavailable)
        XCTAssertEqual(series.segments.count, 1)
        XCTAssertEqual(series.latest.home, 114.5, "the single sportsbook's line is still 114.5")
        XCTAssertEqual(series.latest.away, 111.0)

        // 3. The page's own whole-number pair is (111, 114), matching the headline.
        let view = EventDetailView(eventId: detail.id).withLoadedEventForTest12278(detail)
        let pair = try XCTUnwrap(view.pageProjectedPointsPair(detail))
        XCTAssertEqual(pair.away, 111)
        XCTAssertEqual(pair.home, 114)
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(
                pagePoints: pair.away,
                forecast: series.latest.away,
                phase: series.phase
            ),
            "111 projected"
        )
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(
                pagePoints: pair.home,
                forecast: series.latest.home,
                phase: series.phase
            ),
            "114 projected"
        )
    }

    func testDuringAndAfterKeepZeroBasedYAxisAndAfterPrintsBookLine() throws {
        let kickoff = Self.asOf.addingTimeInterval(-2_400)
        let duringInput = ProjectedFinalPointsSeries.Input(
            sportKey: "basketball_nba",
            sourceKey: "draftkings",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [
                .init(at: kickoff.addingTimeInterval(-600), home: 114.5, away: 111.0, homeProbability: 0.57, kind: .recorded),
                .init(at: kickoff.addingTimeInterval(900), home: 118.0, away: 109.5, homeProbability: 0.68, kind: .recorded),
            ],
            actuals: [
                .init(at: kickoff, home: 0, away: 0),
                .init(at: kickoff.addingTimeInterval(900), home: 34, away: 27),
            ],
            kickoffAt: nil,
            scoreObservationStartAt: kickoff,
            finalAt: nil,
            asOf: Self.asOf,
            windowStartAt: nil,
            requestCutoffAt: nil,
            openingScore: .init(at: kickoff, home: 0, away: 0)
        )
        let duringSeries = try XCTUnwrap(ProjectedFinalPointsSeries.build(duringInput))
        XCTAssertEqual(duringSeries.phase, .during)
        XCTAssertEqual(duringSeries.yMin, 0)
        XCTAssertEqual(duringSeries.yTicks, [0, 20, 40, 60, 80, 100, 120, 140])

        let afterInput = ProjectedFinalPointsSeries.Input(
            sportKey: "basketball_nba",
            sourceKey: "draftkings",
            basis: .sameBookSameCaptureFullGameSpreadAndTotal,
            pairs: [
                .init(at: kickoff.addingTimeInterval(-600), home: 114.5, away: 111.0, homeProbability: 0.57, kind: .recorded),
                .init(at: kickoff.addingTimeInterval(900), home: 115.5, away: 109.5, homeProbability: 0.68, kind: .recorded),
            ],
            actuals: [
                .init(at: Self.asOf, home: 116, away: 108),
            ],
            kickoffAt: nil,
            scoreObservationStartAt: kickoff,
            finalAt: Self.asOf,
            asOf: Self.asOf,
            windowStartAt: nil,
            requestCutoffAt: nil
        )
        let afterSeries = try XCTUnwrap(ProjectedFinalPointsSeries.build(afterInput))
        XCTAssertEqual(afterSeries.phase, .after)
        XCTAssertEqual(afterSeries.yMin, 0)
        XCTAssertEqual(afterSeries.yTicks.first, 0)
        XCTAssertEqual(
            ProjectedFinalPointsChartView.projectedReadoutText(
                pagePoints: 114,
                forecast: afterSeries.latest.home,
                phase: afterSeries.phase
            ),
            "115.5 projected",
            "finished games print the sportsbook's last projection before completion"
        )
    }

    func testXAxisLabelsAreInsetAndNeverCutOnEvent15350164At390Px() throws {
        // Direct geometry check: an end tick whose clamped label crowds its neighbour is dropped.
        let t0 = Self.asOf.addingTimeInterval(-7_200)
        let t1 = Self.asOf.addingTimeInterval(-3_600)
        let t2 = Self.asOf
        let keptCrowded = ProjectedFinalPointsChartView.nonCollidingTicks(
            [t0, t1, t2],
            positions: [10, 260, 294],
            plotWidth: 296,
            labelWidth: 42
        )
        XCTAssertEqual(keptCrowded, [t0, t1], "a right-edge tick that crowds the preceding label after edge-insetting is dropped")

        let detail: EventDetail
        let history: EventHistoryResponse
        if let savedDetail = try? Data(contentsOf: URL(fileURLWithPath: "/tmp/ev15350164_detail.json")),
           let savedHistory = try? Data(contentsOf: URL(fileURLWithPath: "/tmp/ev15350164_history.json")) {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            detail = try decoder.decode(EventDetail.self, from: savedDetail)
            history = try decoder.decode(EventHistoryResponse.self, from: savedHistory)
        } else {
            detail = try decode(EventDetail.self, Self.event15350164DetailJSON)
            history = try decode(EventHistoryResponse.self, Self.event15350164HistoryJSON)
        }

        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: detail.sport,
            eventStatus: detail.status,
            history: history,
            finalHome: nil,
            finalAway: nil,
            asOf: Self.asOf
        ))
        let pageView = EventDetailView(eventId: detail.id).withLoadedEventForTest12278(detail)
        let pagePair = try XCTUnwrap(pageView.pageProjectedPointsPair(detail))
        let pairColors = TeamTextContrast.surfaceColors(
            awayHex: detail.awayTeamData?.primaryColor,
            homeHex: detail.homeTeamData?.primaryColor,
            awaySecondaryHex: detail.awayTeamData?.secondaryColor,
            homeSecondaryHex: detail.homeTeamData?.secondaryColor,
            colorScheme: .light,
            checkHueFamily: true
        )

        let surface = VStack(alignment: .leading, spacing: 14) {
            pageView
                .heroSectionForTest12278(detail)
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
            ProjectedFinalPointsChartView(
                input: input,
                homeTeam: detail.homeTeam,
                awayTeam: detail.awayTeam,
                homeColor: pairColors.home,
                awayColor: pairColors.away,
                periodMarkers: history.periodMarkers,
                sportKey: detail.sport,
                pageProjectedPair: pagePair
            )
            .padding(16)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(uiColor: .systemGroupedBackground))
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())
        .environment(\.colorScheme, .light)

        let image = renderInWindow(surface, width: 390)
        let cgImage = try XCTUnwrap(image.cgImage)

        if FileManager.default.fileExists(atPath: "/tmp") {
            let exportDir = URL(fileURLWithPath: "/tmp/renders-12889-after")
            try? FileManager.default.createDirectory(at: exportDir, withIntermediateDirectories: true)
            if let png = image.pngData() {
                try? png.write(to: exportDir.appendingPathComponent("12889-ev15350164-after-light-390.png"))
            }
            // Also export dark mode at 390 px for inspection.
            let darkPairColors = TeamTextContrast.surfaceColors(
                awayHex: detail.awayTeamData?.primaryColor,
                homeHex: detail.homeTeamData?.primaryColor,
                awaySecondaryHex: detail.awayTeamData?.secondaryColor,
                homeSecondaryHex: detail.homeTeamData?.secondaryColor,
                colorScheme: .dark,
                checkHueFamily: true
            )
            let darkSurface = VStack(alignment: .leading, spacing: 14) {
                pageView
                    .heroSectionForTest12278(detail)
                    .padding(14)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                ProjectedFinalPointsChartView(
                    input: input,
                    homeTeam: detail.homeTeam,
                    awayTeam: detail.awayTeam,
                    homeColor: darkPairColors.home,
                    awayColor: darkPairColors.away,
                    periodMarkers: history.periodMarkers,
                    sportKey: detail.sport,
                    pageProjectedPair: pagePair
                )
                .padding(16)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 12))
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .environment(\.colorScheme, .dark)
            let darkImage = renderInWindow(darkSurface, width: 390, style: .dark)
            if let darkPng = darkImage.pngData() {
                try? darkPng.write(to: exportDir.appendingPathComponent("12889-ev15350164-after-dark-390.png"))
            }
        }

        let recognized = try recognizeStrings(in: cgImage)
        let joined = recognized.joined(separator: " | ")
        XCTAssertTrue(recognized.contains(where: { $0.contains("111 projected") }), "expected '111 projected' in OCR: \(joined)")
        XCTAssertTrue(recognized.contains(where: { $0.contains("114 projected") }), "expected '114 projected' in OCR: \(joined)")
        XCTAssertFalse(recognized.contains(where: { $0.contains("114.5") }), "must not print sportsbook 114.5 on card readout: \(joined)")
        for line in recognized {
            XCTAssertFalse(line.contains("…") || line.contains("..."), "truncated text '\(line)' in 390px render: \(joined)")
        }
    }

    private func renderInWindow<V: View>(_ view: V, width: CGFloat, style: UIUserInterfaceStyle = .light) -> UIImage {
        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = style
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 2_400))
        let targetSize = CGSize(width: width, height: ceil(fitting.height))
        host.view.frame = CGRect(origin: .zero, size: targetSize)

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let deadline = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < deadline

        let finalFit = host.sizeThatFits(in: CGSize(width: width, height: 2_400))
        let finalSize = CGSize(width: width, height: ceil(finalFit.height))
        host.view.frame = CGRect(origin: .zero, size: finalSize)
        window.frame = host.view.frame
        host.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func recognizeStrings(in cgImage: CGImage) throws -> [String] {
        var output: [String] = []
        let request = VNRecognizeTextRequest { req, _ in
            let observations = (req.results as? [VNRecognizedTextObservation]) ?? []
            output = observations.compactMap { $0.topCandidates(1).first?.string }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return output
    }
}
