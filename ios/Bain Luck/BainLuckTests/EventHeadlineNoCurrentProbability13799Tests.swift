import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13799 — When a game that has not started or is in progress has no current probability,
/// `EventSportHeadlines12472` leaves out the empty `Chance` / `Now` column (no blank cell)
/// and prints the `EventAtlasStates11666.heroStateLabel` plain-English notice in its quiet
/// line (`"No probability yet"` before kickoff, `"No recent probability"` once started/live).
@MainActor
final class EventHeadlineNoCurrentProbability13799Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-26T04:00:00Z")!

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func makeFixture(
        status: String,
        sport: String = "basketball_nba",
        commenceTime: String,
        homeScore: Int? = nil,
        awayScore: Int? = nil,
        scoreUnavailable: Bool? = nil,
        venueSettled: Bool? = nil,
        venueClosedNoWinner: Bool? = nil,
        currentOddsJSON: String = "null",
        heroSource: String? = "blend"
    ) throws -> EventDetail {
        let heroSourceJSON = heroSource.map { "\"\($0)\"" } ?? "null"
        let homeScoreJSON = homeScore.map(String.init) ?? "null"
        let awayScoreJSON = awayScore.map(String.init) ?? "null"
        let unavailJSON = scoreUnavailable.map { $0 ? "true" : "false" } ?? "null"
        let settledJSON = venueSettled.map { $0 ? "true" : "false" } ?? "null"
        let closedJSON = venueClosedNoWinner.map { $0 ? "true" : "false" } ?? "null"
        let espnJSON = status == "live" ? #"{"period":"Q2","game_clock":"6:12"}"# : "null"

        return try decodeEvent("""
        {
          "id": 9137991,
          "sport": "\(sport)",
          "home_team": "Portland Trail Blazers",
          "away_team": "San Antonio Spurs",
          "commence_time": "\(commenceTime)",
          "start_is_tbd": false,
          "status": "\(status)",
          "home_score": \(homeScoreJSON),
          "away_score": \(awayScoreJSON),
          "score_source_unavailable": \(unavailJSON),
          "venue_settled": \(settledJSON),
          "venue_closed_no_winner": \(closedJSON),
          "home_team_data": {
            "abbreviation": "POR",
            "primary_color": "#E03A3E",
            "record": "11-6"
          },
          "away_team_data": {
            "abbreviation": "SA",
            "primary_color": "#111827",
            "record": "15-3"
          },
          "espn": \(espnJSON),
          "current_odds": \(currentOddsJSON),
          "hero_probability_source": \(heroSourceJSON)
        }
        """)
    }

    // MARK: - Model unit tests

    func testScheduledGameWithNoCurrentProbabilityOmitsChanceColumnAndSaysNoProbabilityYet() throws {
        let event = try makeFixture(
            status: "scheduled",
            commenceTime: "2026-11-28T03:00:00Z"
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )

        XCTAssertFalse(model.columns.contains(where: { $0.role == .chance }), "Chance column must be omitted when no current probability is printable")
        XCTAssertEqual(model.probabilityUnavailableNotice, EventAtlasStates11666.noPriceYet)
        XCTAssertEqual(model.probabilityUnavailableNotice, "No probability yet")
        XCTAssertNil(model.sourceMark)
        for row in model.rows {
            XCTAssertEqual(row.cells.count, model.columns.count)
        }
    }

    func testStartedGameWithoutLiveOddsOmitsChanceAndSaysNoRecentProbability() throws {
        let event = try makeFixture(
            status: "live",
            commenceTime: "2026-11-26T02:00:00Z",
            homeScore: 60,
            awayScore: 57
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: "Q2 · 6:12",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )

        XCTAssertFalse(model.columns.contains(where: { $0.role == .now }), "Now column must be omitted when live game has no current probability")
        XCTAssertEqual(model.columns.first?.role, .score)
        XCTAssertEqual(model.rows.map { $0.cells.first ?? "" }, ["57", "60"])
        XCTAssertEqual(model.probabilityUnavailableNotice, EventAtlasStates11666.noRecentPrice)
        XCTAssertEqual(model.probabilityUnavailableNotice, "No recent probability")
        XCTAssertFalse(model.showsEkg)
        XCTAssertNil(model.sourceMark)
    }

    func testScheduledGameWithWithheldOpeningOddsOmitsChanceAndSaysNoProbabilityYet() throws {
        let event = try makeFixture(
            status: "scheduled",
            commenceTime: "2026-11-28T03:00:00Z",
            currentOddsJSON: #"{"home_probability":0.55,"away_probability":0.45,"home_rendered_percent":55,"away_rendered_percent":45}"#,
            heroSource: OpeningLineHero.openingSource
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )

        XCTAssertFalse(model.columns.contains(where: { $0.role == .chance }))
        XCTAssertEqual(model.probabilityUnavailableNotice, "No probability yet")
    }

    func testLiveScorelessAndOddlessTennisShowsBothNoticesAndNoEmptyColumns() throws {
        let event = try makeFixture(
            status: "live",
            sport: "tennis_atp",
            commenceTime: "2026-11-26T02:00:00Z",
            scoreUnavailable: true
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: "Away Player",
                homeFullName: "Home Player",
                liveStatusText: "Live",
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )

        XCTAssertTrue(model.columns.isEmpty)
        XCTAssertEqual(model.scoreUnavailableNotice, EventSportHeadlines12472.noLiveScoreTournamentLine)
        XCTAssertEqual(model.probabilityUnavailableNotice, "No recent probability")
    }

    func testTerminalAndStoppedStatesNeverDuplicateBadgesWithProbabilityNotice() throws {
        let cases: [(String, String, Bool?, Bool?)] = [
            ("postponed", "2026-11-28T03:00:00Z", nil, nil),
            ("canceled", "2026-11-28T03:00:00Z", nil, nil),
            ("completed", "2026-11-25T03:00:00Z", nil, nil),
            ("suspended", "2026-11-26T02:00:00Z", false, false),
            ("scheduled", "2026-11-25T03:00:00Z", true, false),
            ("suspended", "2026-11-26T02:00:00Z", false, true),
        ]
        for (status, commence, settled, closedNoWinner) in cases {
            let event = try makeFixture(
                status: status,
                commenceTime: commence,
                venueSettled: settled,
                venueClosedNoWinner: closedNoWinner
            )
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            XCTAssertNil(model.probabilityUnavailableNotice, "Status \(status) must not emit no-probability notice")
        }
    }

    func testTwoWaySportWithOneSidedOddsOmitsProbabilityColumnAndPrintsNotice() throws {
        let partialOddsCases: [(status: String, commenceTime: String, homeScore: Int?, awayScore: Int?, oddsJSON: String, expectedNotice: String)] = [
            (
                "scheduled",
                "2026-11-28T03:00:00Z",
                nil,
                nil,
                #"{"home_probability":0.62,"away_probability":null}"#,
                "No probability yet"
            ),
            (
                "live",
                "2026-11-26T02:00:00Z",
                60,
                57,
                #"{"home_probability":0.62,"away_probability":null}"#,
                "No recent probability"
            ),
            (
                "live",
                "2026-11-26T02:00:00Z",
                60,
                57,
                #"{"home_probability":null,"away_probability":0.38}"#,
                "No recent probability"
            ),
        ]

        for entry in partialOddsCases {
            let event = try makeFixture(
                status: entry.status,
                sport: "basketball_nba",
                commenceTime: entry.commenceTime,
                homeScore: entry.homeScore,
                awayScore: entry.awayScore,
                currentOddsJSON: entry.oddsJSON
            )
            XCTAssertNil(
                DrawPricedWinner.printablePair(
                    away: event.currentOdds?.awayProbability,
                    home: event.currentOdds?.homeProbability,
                    sport: event.sport
                ),
                "Two-way sports must reject one-sided current odds before reaching resolveDuring's #5271 branch"
            )
            let isLive = entry.status == "live"
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: isLive ? "Q2 · 6:12" : nil,
                    hasScore: isLive,
                    numberStreams: isLive,
                    now: fixedNow
                )
            )
            XCTAssertFalse(model.columns.contains { $0.role == .chance || $0.role == .now }, "Partial two-way column must be omitted")
            XCTAssertEqual(model.probabilityUnavailableNotice, entry.expectedNotice)
        }
    }

    func testDrawPricedLiveMatchMissingDrawWithholdsAwayPer5271WithoutHidingHome() throws {
        // Only draw-priced sports (soccer) with draw_probability withheld reach resolveDuring's
        // single-side `homeNow` branch: per #5271 Home prints alone and Away stays withheld rather
        // than inventing `1 - home` or suppressing a valid Home probability.
        let soccer = try makeFixture(
            status: "live",
            sport: "soccer_epl",
            commenceTime: "2026-11-26T02:30:00Z",
            homeScore: 1,
            awayScore: 0,
            currentOddsJSON: #"{"home_probability":0.52,"away_probability":0.48,"draw_probability":null}"#
        )
        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: soccer,
                awayFullName: soccer.awayTeam,
                homeFullName: soccer.homeTeam,
                liveStatusText: "63'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.columns.map(\.role), [.score, .projected, .now])
        XCTAssertEqual(model.rows.count, 2)
        XCTAssertEqual(model.rows[0].role, .away)
        XCTAssertEqual(model.rows[0].cells.last, EventAtlasStates11666.noRecentPrice, "Ruling 250: A requires standing words in withheld soccer away cell")
        XCTAssertEqual(model.rows[0].quietNoticeColumns, [model.columns.count - 1])
        XCTAssertNil(model.rows[0].rawProbability)
        XCTAssertEqual(model.rows[1].role, .home)
        XCTAssertEqual(model.rows[1].cells.last, "52.0%")
        XCTAssertNil(model.probabilityUnavailableNotice)
    }

    // MARK: - Rendered headline proof + OCR + 390/320/AX5 sheet

    private func recognizeText(in image: UIImage) throws -> String {
        guard let cg = image.cgImage else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: "\n")
    }

    private func renderCard(
        model: EventSportHeadlines12472.Model,
        awayHex: String = "#111827",
        homeHex: String = "#E03A3E",
        width: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) -> UIImage {
        let card = EventSportHeadlineCard12472(
            model: model,
            colors: (away: Color(hex: awayHex), home: Color(hex: homeHex)),
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
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)
        let target = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
        let bounds = CGRect(origin: .zero, size: CGSize(width: width, height: ceil(target.height)))
        host.view.frame = bounds

        let window = UIWindow(frame: bounds)
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

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    func testRenderedHeadlinesReadWordsAndOmitEmptyColumnAcrossWidthsAndSizes() throws {
        let scheduled = try makeFixture(status: "scheduled", commenceTime: "2026-11-28T03:00:00Z")
        let live = try makeFixture(status: "live", commenceTime: "2026-11-26T02:00:00Z", homeScore: 60, awayScore: 57)

        let scheduledModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: scheduled,
                awayFullName: scheduled.awayTeam,
                homeFullName: scheduled.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        let liveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: live,
                awayFullName: live.awayTeam,
                homeFullName: live.homeTeam,
                liveStatusText: "Q2 · 6:12",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )

        let scheduledImg = renderCard(model: scheduledModel, width: 390, colorScheme: .light, dynamicTypeSize: .large)
        let scheduledText = try recognizeText(in: scheduledImg)
        XCTAssertTrue(scheduledText.localizedCaseInsensitiveContains("No probability yet"), "Expected notice in rendered card: \(scheduledText)")
        XCTAssertFalse(scheduledText.localizedCaseInsensitiveContains("Chance"), "Empty Chance header must be omitted: \(scheduledText)")

        let liveImg = renderCard(model: liveModel, width: 390, colorScheme: .light, dynamicTypeSize: .large)
        let liveText = try recognizeText(in: liveImg)
        XCTAssertTrue(liveText.localizedCaseInsensitiveContains("No recent probability"), "Expected notice in rendered live card: \(liveText)")
        XCTAssertFalse(liveText.localizedCaseInsensitiveContains("Now"), "Empty Now header must be omitted: \(liveText)")

        let panels: [(String, UIImage)] = [
            ("Before (no probability) · 390 Light · Default (.large)", scheduledImg),
            ("Before (no probability) · 390 Dark · Default (.large)", renderCard(model: scheduledModel, width: 390, colorScheme: .dark, dynamicTypeSize: .large)),
            ("Live with score (no probability) · 390 Light · Default (.large)", liveImg),
            ("Live with score (no probability) · 390 Dark · Default (.large)", renderCard(model: liveModel, width: 390, colorScheme: .dark, dynamicTypeSize: .large)),
            ("Before (no probability) · 320 Light · Default (.large)", renderCard(model: scheduledModel, width: 320, colorScheme: .light, dynamicTypeSize: .large)),
            ("Live with score (no probability) · 390 AX5 Light · AX5 (.accessibility5)", renderCard(model: liveModel, width: 390, colorScheme: .light, dynamicTypeSize: .accessibility5)),
            ("Live with score (no probability) · 390 AX5 Dark · AX5 (.accessibility5)", renderCard(model: liveModel, width: 390, colorScheme: .dark, dynamicTypeSize: .accessibility5)),
        ]

        // Assemble single vertical contact sheet for proof review (Simulator results, not phone)
        let pad: CGFloat = 20
        let labelH: CGFloat = 24
        let sheetWidthPt: CGFloat = 430
        var totalHeightPt: CGFloat = pad
        for (_, img) in panels {
            totalHeightPt += labelH + img.size.height + pad
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let sheet = UIGraphicsImageRenderer(size: CGSize(width: sheetWidthPt, height: totalHeightPt), format: fmt).image { ctx in
            UIColor(red: 0.96, green: 0.97, blue: 0.98, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: sheetWidthPt, height: totalHeightPt))
            var y: CGFloat = pad
            for (caption, img) in panels {
                let attrs: [NSAttributedString.Key: Any] = [
                    .font: UIFont.systemFont(ofSize: 12, weight: .semibold),
                    .foregroundColor: UIColor(red: 0.12, green: 0.16, blue: 0.23, alpha: 1.0),
                ]
                (caption as NSString).draw(at: CGPoint(x: 16, y: y), withAttributes: attrs)
                y += labelH
                img.draw(in: CGRect(x: 16, y: y, width: img.size.width, height: img.size.height))
                y += img.size.height + pad
            }
        }
        let envOut = ProcessInfo.processInfo.environment["TEST_RUNNER_EXPORT_13799_SHEET_PATH"]
            ?? ProcessInfo.processInfo.environment["EXPORT_13799_SHEET_PATH"]
        let outURL: URL
        if let envOut, !envOut.isEmpty {
            outURL = URL(fileURLWithPath: envOut)
            try FileManager.default.createDirectory(at: outURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        } else {
            outURL = FileManager.default.temporaryDirectory.appendingPathComponent("sheet-13799-no-current-probability.jpg")
        }
        if let jpg = sheet.jpegData(compressionQuality: 0.92) {
            try jpg.write(to: outURL)
            print("SHEET_13799=\(outURL.path)")
        }
    }
}
