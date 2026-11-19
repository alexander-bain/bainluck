import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Sat Nov 14 Item 6 — Tennis tiebreak points on the score-first live tennis headline
/// (`backend/app/utils/tennis_live_score.py` `linescore` contract), plus inline chart
/// `.withheld` scrub withholding (`PublicationCheckpointReadoutSlot4974.withheldText`).
@MainActor
final class TennisTiebreakPointsSat6Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T20:00:00Z")!

    private func decodeDetail(_ json: String) throws -> EventDetail {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func makeLiveTiebreakFixture(
        includeCompletedSetSuperscript: Bool = false
    ) throws -> EventDetail {
        let tiebreaksField = includeCompletedSetSuperscript
            ? #","tiebreaks": [[7, 4], null, null]"#
            : ""
        let setsField = includeCompletedSetSuperscript
            ? "[[7, 6], [4, 6], [6, 6]]"
            : "[[6, 4], [6, 6]]"
        let homeSets = 1
        let awaySets = includeCompletedSetSuperscript ? 1 : 0
        return try decodeDetail("""
        {
          "id": 601901,
          "sport": "tennis_atp_finals",
          "sport_name": "ATP Finals",
          "home_team": "Jannik Sinner",
          "away_team": "Carlos Alcaraz",
          "commence_time": "2026-11-15T18:30:00Z",
          "status": "live",
          "home_score": \(homeSets),
          "away_score": \(awaySets),
          "current_odds": {
            "home_probability": 0.634,
            "away_probability": 0.366,
            "home_rendered_percent": 63,
            "away_rendered_percent": 37,
            "updated_at": "2026-11-15T19:59:50Z"
          },
          "prematch_odds": {
            "home_probability": 0.56,
            "away_probability": 0.44,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44
          },
          "hero_probability": 0.634,
          "hero_probability_away": 0.366,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-15T19:59:50Z",
          "espn": {
            "period": "\(includeCompletedSetSuperscript ? "Set 3" : "Set 2")"
          },
          "box_score_data": {
            "home_period_scores": \(includeCompletedSetSuperscript ? "[7, 4, 6]" : "[6, 6]"),
            "away_period_scores": \(includeCompletedSetSuperscript ? "[6, 6, 6]" : "[4, 6]")
          },
          "linescore": {
            "sets": \(setsField),
            "home_games": \(includeCompletedSetSuperscript ? 17 : 12),
            "away_games": \(includeCompletedSetSuperscript ? 18 : 10),
            "home_sets": \(homeSets),
            "away_sets": \(awaySets),
            "source": "statpal",
            "observed_at": "2026-11-15T19:59:52Z",
            "home_points": "5",
            "away_points": "3",
            "tiebreak": true,
            "serving": "home"\(tiebreaksField)
          },
          "win_probability_sources": {
            "kalshi": { "value": 0.634, "display_name": "Kalshi" },
            "polymarket": { "value": 0.634, "display_name": "Polymarket" }
          }
        }
        """)
    }

    private func makeLiveOrdinaryGameFixture() throws -> EventDetail {
        try decodeDetail("""
        {
          "id": 601902,
          "sport": "tennis_wta_finals",
          "sport_name": "WTA Finals",
          "home_team": "Aryna Sabalenka",
          "away_team": "Iga Swiatek",
          "commence_time": "2026-11-15T18:30:00Z",
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "current_odds": {
            "home_probability": 0.582,
            "away_probability": 0.418,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "updated_at": "2026-11-15T19:59:50Z"
          },
          "prematch_odds": {
            "home_probability": 0.52,
            "away_probability": 0.48,
            "home_rendered_percent": 52,
            "away_rendered_percent": 48
          },
          "hero_probability": 0.582,
          "hero_probability_away": 0.418,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-15T19:59:50Z",
          "espn": {
            "period": "Set 2",
            "game_clock": "30-40"
          },
          "box_score_data": {
            "home_period_scores": [6, 3],
            "away_period_scores": [4, 2]
          },
          "linescore": {
            "sets": [[6, 4], [3, 2]],
            "home_sets": 1,
            "away_sets": 0,
            "source": "statpal",
            "observed_at": "2026-11-15T19:59:52Z",
            "home_points": "40",
            "away_points": "30",
            "tiebreak": false,
            "serving": "home"
          }
        }
        """)
    }

    func testServedLinescoreTiebreakPointsRenderUnderTBHeaderWithoutGameClock() throws {
        // Server omits `espn.game_clock` when `linescore.tiebreak == true` (`tennis_live_score.py:228`).
        let event = try makeLiveTiebreakFixture(includeCompletedSetSuperscript: false)
        XCTAssertNil(event.espn?.gameClock)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: "Set 2",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.liveBadgeText, "LIVE · Set 2 · TB")

        let scoreFirst = try XCTUnwrap(model.tennisScoreFirst)
        XCTAssertTrue(scoreFirst.isTiebreakPoints)
        XCTAssertEqual(scoreFirst.pointsHeader, "TB")
        XCTAssertEqual(scoreFirst.pointsColumn?.away, "3")
        XCTAssertEqual(scoreFirst.pointsColumn?.home, "5")
        XCTAssertEqual(scoreFirst.setColumns.count, 2)
        XCTAssertEqual(scoreFirst.setColumns[0].awayValue, "4")
        XCTAssertEqual(scoreFirst.setColumns[0].homeValue, "6")
        XCTAssertEqual(scoreFirst.setColumns[1].awayValue, "6")
        XCTAssertEqual(scoreFirst.setColumns[1].homeValue, "6")
        // Truth pillar: unserved per-set tiebreak counts are never invented.
        XCTAssertNil(scoreFirst.setColumns[0].awayTiebreak)
        XCTAssertNil(scoreFirst.setColumns[0].homeTiebreak)
    }

    func testOrdinaryGamePointsKeepPtsHeaderAndServedSetSuperscriptsAttachCleanly() throws {
        let ordinary = try makeLiveOrdinaryGameFixture()
        let ordinaryModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: ordinary,
                awayFullName: ordinary.awayTeam,
                homeFullName: ordinary.homeTeam,
                liveStatusText: "Set 2",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(ordinaryModel.liveBadgeText, "LIVE · Set 2")
        let ordinarySF = try XCTUnwrap(ordinaryModel.tennisScoreFirst)
        XCTAssertFalse(ordinarySF.isTiebreakPoints)
        XCTAssertEqual(ordinarySF.pointsHeader, "Pts")
        XCTAssertEqual(ordinarySF.pointsColumn?.away, "30")
        XCTAssertEqual(ordinarySF.pointsColumn?.home, "40")

        let withSetTB = try makeLiveTiebreakFixture(includeCompletedSetSuperscript: true)
        let tbModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: withSetTB,
                awayFullName: withSetTB.awayTeam,
                homeFullName: withSetTB.homeTeam,
                liveStatusText: "Set 3",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        let tbSF = try XCTUnwrap(tbModel.tennisScoreFirst)
        XCTAssertEqual(tbSF.setColumns[0].homeValue, "7")
        XCTAssertEqual(tbSF.setColumns[0].homeTiebreak, "7")
        XCTAssertEqual(tbSF.setColumns[0].awayValue, "6")
        XCTAssertEqual(tbSF.setColumns[0].awayTiebreak, "4")
        XCTAssertNil(tbSF.setColumns[1].homeTiebreak)
    }

    func testTennisTiebreakSheetFitsAt390AndExportsRender() throws {
        let liveTB = try makeLiveTiebreakFixture(includeCompletedSetSuperscript: false)
        let liveTBWithSuperscript = try makeLiveTiebreakFixture(includeCompletedSetSuperscript: true)
        let ordinary = try makeLiveOrdinaryGameFixture()

        func makeCard(_ detail: EventDetail, status: String) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: detail,
                    awayFullName: detail.awayTeam,
                    homeFullName: detail.homeTeam,
                    liveStatusText: status,
                    hasScore: true,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            let colors = TeamTextContrast.cardColors(awayHex: nil, homeHex: nil)
            return EventSportHeadlineCard12472(
                model: model,
                colors: colors,
                ekgTracker: .empty,
                liveUpdateStatus: .autoRefresh,
                displayAsOf: fixedNow,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: fixedNow,
                confirmedAt: fixedNow,
                revealForecast: nil
            )
        }

        let card1 = try makeCard(liveTB, status: "Set 2")
        let card2 = try makeCard(liveTBWithSuperscript, status: "Set 3")
        let card3 = try makeCard(ordinary, status: "Set 2")

        let sheet = VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Live Tennis Tiebreak Points — Score-First Headline (390 px)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color(hex: "#111827"))
                Text("Served linescore tiebreak points (\"TB\") + optional set superscripts + ordinary \"Pts\" control")
                    .font(.caption2)
                    .foregroundStyle(Color(hex: "#6B7280"))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("1. Active Set 2 Tiebreak (linescore.tiebreak = true · TB 3–5)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                card1
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("2. Set 3 Tiebreak + S1 Tiebreak Superscript (7⁷–6⁴)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                card2
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("3. Control: Ordinary Game Points (Pts 30–40)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                card3
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(hex: "#F3F4F6"))
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(sheet, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 10_000))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: max(fitting.height, 400))
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.2)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: 390, height: 10_000)).height, 400)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        XCTAssertEqual(Int(image.size.width.rounded()), 390)

        if let exportDir = ProcessInfo.processInfo.environment["SAT6_TENNIS_TB_EXPORT_DIR"],
           !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: dirURL.appendingPathComponent("sat6-tennis-tiebreak-points-390.png"))
        }
    }
}
