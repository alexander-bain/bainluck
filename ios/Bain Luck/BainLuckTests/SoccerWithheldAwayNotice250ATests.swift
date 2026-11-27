import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Ruling 250: A — On a draw-priced soccer match with a Home probability and no explicit
/// draw probability (Away withheld rather than invented from `1 - home`), the Away cell
/// prints `"No probability yet"` before the game has had any number and `"No recent probability"`
/// after, never an empty box.
@MainActor
final class SoccerWithheldAwayNotice250ATests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-26T20:00:00Z")!

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func soccerFixture(
        status: String,
        commenceTime: String,
        homeScore: Int? = nil,
        awayScore: Int? = nil,
        openingOddsJSON: String = "null",
        prematchOddsJSON: String = "null",
        espnJSON: String = "null"
    ) throws -> EventDetail {
        let homeScoreJSON = homeScore.map(String.init) ?? "null"
        let awayScoreJSON = awayScore.map(String.init) ?? "null"
        return try decodeEvent("""
        {
          "id": 15344943,
          "sport": "soccer_epl",
          "sport_name": "EPL",
          "home_team": "Nottingham Forest",
          "away_team": "Chelsea",
          "commence_time": "\(commenceTime)",
          "start_is_tbd": false,
          "status": "\(status)",
          "home_score": \(homeScoreJSON),
          "away_score": \(awayScoreJSON),
          "home_team_data": {
            "abbreviation": "NFO",
            "primary_color": "#c8102e",
            "secondary_color": "#1B3624",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
            "record": "2-3-6"
          },
          "away_team_data": {
            "abbreviation": "CHE",
            "primary_color": "#144992",
            "secondary_color": "#FFFFFF",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/363.png",
            "record": "5-1-5"
          },
          "espn": \(espnJSON),
          "opening_odds": \(openingOddsJSON),
          "prematch_odds": \(prematchOddsJSON),
          "current_odds": {
            "captured_at": "2026-11-26T19:59:30Z",
            "home_probability": 0.62,
            "home_rendered_percent": 62,
            "away_probability": 0.38,
            "away_rendered_percent": 38,
            "draw_probability": null
          },
          "hero_probability": 0.62,
          "hero_probability_source": "kalshi",
          "hero_probability_observed_at": "2026-11-26T19:59:30Z",
          "win_probability_sources": {
            "kalshi": {
              "value": 0.62,
              "display_name": "Kalshi",
              "observed_at": "2026-11-26T19:59:30Z"
            }
          }
        }
        """)
    }

    // MARK: - Model Rules (Ruling 250: A)

    func testScheduledWithoutPriorNumberPrintsNoProbabilityYetInAwayCell() throws {
        let scheduledFresh = try soccerFixture(
            status: "scheduled",
            commenceTime: "2026-11-27T20:00:00Z",
            espnJSON: #"{"broadcast":"USA Net, Universo"}"#
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: scheduledFresh,
                awayFullName: scheduledFresh.awayTeam,
                homeFullName: scheduledFresh.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.columns.map(\.role), [.projected, .chance])
        XCTAssertEqual(model.rows.map(\.role), [.away, .home])
        XCTAssertEqual(model.rows[0].cells, ["", "No probability yet"])
        XCTAssertEqual(model.rows[0].quietNoticeColumns, [1])
        XCTAssertNil(model.rows[0].rawProbability)
        XCTAssertEqual(model.rows[1].cells, ["", "62%"])
        XCTAssertEqual(model.rows[1].quietNoticeColumns, [])
        XCTAssertNil(model.probabilityUnavailableNotice)
    }

    func testScheduledWithPriorOddsAndLivePrintsNoRecentProbabilityInAwayCell() throws {
        let scheduledWithOpening = try soccerFixture(
            status: "scheduled",
            commenceTime: "2026-11-27T20:00:00Z",
            openingOddsJSON: #"{"home_probability":0.55,"away_probability":0.22}"#
        )
        let preWithPrior = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: scheduledWithOpening,
                awayFullName: scheduledWithOpening.awayTeam,
                homeFullName: scheduledWithOpening.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(preWithPrior.rows[0].cells, ["", "No recent probability"])
        XCTAssertEqual(preWithPrior.rows[0].quietNoticeColumns, [1])
        XCTAssertEqual(preWithPrior.rows[1].cells, ["", "62%"])

        let live = try soccerFixture(
            status: "live",
            commenceTime: "2026-11-26T18:40:00Z",
            homeScore: 1,
            awayScore: 0,
            espnJSON: #"{"period":"2nd Half","game_clock":"67'"}"#
        )
        let liveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: live,
                awayFullName: live.awayTeam,
                homeFullName: live.homeTeam,
                liveStatusText: "67'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(liveModel.columns.map(\.role), [.score, .projected, .now])
        XCTAssertEqual(liveModel.rows[0].cells, ["0", "", "No recent probability"])
        XCTAssertEqual(liveModel.rows[0].quietNoticeColumns, [2])
        XCTAssertNil(liveModel.rows[0].rawProbability)
        XCTAssertEqual(liveModel.rows[1].cells, ["1", "", "62.0%"])
        XCTAssertEqual(liveModel.rows[1].quietNoticeColumns, [])
        XCTAssertNil(liveModel.probabilityUnavailableNotice)
    }

    // MARK: - Rendered Proof at 320 & 390, Light & Dark, Default & AX5

    #if canImport(UIKit)
    private func seedCrestIfPresent(path: String, urlString: String) async {
        guard let url = URL(string: urlString),
              let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let img = UIImage(data: data) else { return }
        await ImageCache.shared.seedForTesting(img, url: url)
    }

    private func teamColors(for event: EventDetail, colorScheme: ColorScheme) -> (away: Color, home: Color) {
        if colorScheme == .dark {
            let darkHexes = EventDetailView.teamColorHexes(event, colorScheme: .dark)
            return (Color(hex: darkHexes.away), Color(hex: darkHexes.home))
        }
        return TeamTextContrast.cardColors(
            awayHex: event.awayTeamData?.primaryColor,
            homeHex: event.homeTeamData?.primaryColor,
            awaySecondaryHex: event.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )
    }

    private func renderCard(
        event: EventDetail,
        model: EventSportHeadlines12472.Model,
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) -> UIImage {
        let colors = teamColors(for: event, colorScheme: colorScheme)
        let card = EventSportHeadlineCard12472(
            model: model,
            colors: colors,
            ekgTracker: .empty,
            liveUpdateStatus: .hidden,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .frame(width: width - 32)
        .padding(16)
        .frame(width: width)
        .background(colorScheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground))
        .ignoresSafeArea()
        .environment(\.colorScheme, colorScheme)
        .environment(\.dynamicTypeSize, dynamicTypeSize)

        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let host = hostForMeasurement(card, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.view.traitOverrides.preferredContentSizeCategory =
            dynamicTypeSize == .accessibility5 ? .accessibilityExtraExtraExtraLarge : .large
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)
        let initTarget = host.sizeThatFits(in: CGSize(width: width, height: 2400))
        let initBounds = CGRect(origin: .zero, size: CGSize(width: width, height: ceil(initTarget.height) + 16))
        host.view.frame = initBounds

        let window = UIWindow(frame: initBounds)
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.08))

        let finalTarget = host.sizeThatFits(in: CGSize(width: width, height: 2400))
        let finalBounds = CGRect(origin: .zero, size: CGSize(width: width, height: ceil(finalTarget.height)))
        window.frame = finalBounds
        host.view.frame = finalBounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: finalBounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: finalBounds, afterScreenUpdates: true)
        }
    }

    private func recognizeText(in image: UIImage) throws -> String {
        guard let cg = image.cgImage else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }

    func testRenderedSoccerWithheldAwayNoticeAcross320And390LightDarkAndLargestText() async throws {
        let outDir = ProcessInfo.processInfo.environment["TEST_RUNNER_SOCCER_250A_SHEET_DIR"]
            ?? ProcessInfo.processInfo.environment["SOCCER_250A_SHEET_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            await seedCrestIfPresent(path: "\(outDir)/363.png", urlString: "https://a.espncdn.com/i/teamlogos/soccer/500/363.png")
            await seedCrestIfPresent(path: "\(outDir)/393.png", urlString: "https://a.espncdn.com/i/teamlogos/soccer/500/393.png")
        }

        let scheduledFresh = try soccerFixture(
            status: "scheduled",
            commenceTime: "2026-11-27T20:00:00Z",
            espnJSON: #"{"broadcast":"USA Net, Universo"}"#
        )
        let scheduledModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: scheduledFresh,
                awayFullName: scheduledFresh.awayTeam,
                homeFullName: scheduledFresh.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )

        let live = try soccerFixture(
            status: "live",
            commenceTime: "2026-11-26T18:40:00Z",
            homeScore: 1,
            awayScore: 0,
            espnJSON: #"{"period":"2nd Half","game_clock":"67'"}"#
        )
        let liveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: live,
                awayFullName: live.awayTeam,
                homeFullName: live.homeTeam,
                liveStatusText: "67'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )

        let matrix: [(name: String, event: EventDetail, model: EventSportHeadlines12472.Model, expectedNotice: String, width: CGFloat, scheme: ColorScheme, dt: DynamicTypeSize)] = [
            ("sched-390-light-default", scheduledFresh, scheduledModel, "No probability yet", 390, .light, .large),
            ("sched-390-dark-default", scheduledFresh, scheduledModel, "No probability yet", 390, .dark, .large),
            ("sched-320-light-default", scheduledFresh, scheduledModel, "No probability yet", 320, .light, .large),
            ("sched-320-dark-default", scheduledFresh, scheduledModel, "No probability yet", 320, .dark, .large),
            ("sched-390-light-ax5", scheduledFresh, scheduledModel, "No probability yet", 390, .light, .accessibility5),
            ("sched-390-dark-ax5", scheduledFresh, scheduledModel, "No probability yet", 390, .dark, .accessibility5),
            ("sched-320-light-ax5", scheduledFresh, scheduledModel, "No probability yet", 320, .light, .accessibility5),
            ("sched-320-dark-ax5", scheduledFresh, scheduledModel, "No probability yet", 320, .dark, .accessibility5),
            ("live-390-light-default", live, liveModel, "No recent probability", 390, .light, .large),
            ("live-390-dark-default", live, liveModel, "No recent probability", 390, .dark, .large),
            ("live-320-light-default", live, liveModel, "No recent probability", 320, .light, .large),
            ("live-320-dark-default", live, liveModel, "No recent probability", 320, .dark, .large),
            ("live-390-light-ax5", live, liveModel, "No recent probability", 390, .light, .accessibility5),
            ("live-390-dark-ax5", live, liveModel, "No recent probability", 390, .dark, .accessibility5),
            ("live-320-light-ax5", live, liveModel, "No recent probability", 320, .light, .accessibility5),
            ("live-320-dark-ax5", live, liveModel, "No recent probability", 320, .dark, .accessibility5),
        ]

        for entry in matrix {
            let shot = renderCard(
                event: entry.event,
                model: entry.model,
                width: entry.width,
                colorScheme: entry.scheme,
                dynamicTypeSize: entry.dt
            )
            let ocr = try recognizeText(in: shot)
            XCTAssertFalse(ocr.contains("…"), "\(entry.name) must not truncate with ellipsis: \(ocr)")
            XCTAssertTrue(ocr.contains("Chelsea"), "\(entry.name) missing Chelsea: \(ocr)")
            XCTAssertTrue(ocr.contains("62"), "\(entry.name) missing 62: \(ocr)")
            for word in entry.expectedNotice.split(separator: " ") {
                XCTAssertTrue(ocr.localizedCaseInsensitiveContains(String(word)), "\(entry.name) missing word '\(word)' in: \(ocr)")
            }
            if let outDir, !outDir.isEmpty {
                try XCTUnwrap(shot.pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("\(entry.name).png")
                )
            }
        }
    }
    #endif
}
