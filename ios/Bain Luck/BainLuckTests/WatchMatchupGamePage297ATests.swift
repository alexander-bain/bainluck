import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// Ruling 297: A (#12641) — Watch app game page in the Matchup look for 1.0.7
/// (Looks 1A Scheduled, 1B Live, 1C Final at 41 mm `176x215 pt` and 45 mm `198x242 pt`).
@MainActor
final class WatchMatchupGamePage297ATests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!
    private let pt = TimeZone(identifier: "America/Los_Angeles")!
    private let now = Date(timeIntervalSinceReferenceDate: 816_700_000)

    private func decodeGame(_ json: String) throws -> WatchSelectedGame {
        let dec = JSONDecoder()
        return try dec.decode(WatchSelectedGame.self, from: Data(json.utf8))
    }

    func testLook1AScheduledTwoWayAndUnpricedWithholding() throws {
        let scheduled = try decodeGame(#"""
        {
          "id": 21701,
          "away_team": "Pittsburgh Steelers",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"team_id": 101, "abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"team_id": 102, "abbreviation": "CIN", "primary_color": "#FB4F14", "secondary_color": "#000000"},
          "status": "scheduled",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-22T18:00:00Z",
          "hero_probability": 0.66,
          "hero_probability_away": 0.34,
          "hero_probability_observed_at": "2026-11-20T21:29:00Z"
        }
        """#)

        let model = WatchMatchupGameHeroModel297A.build(
            from: scheduled,
            now: Date(timeIntervalSince1970: 1_795_210_800), // 2026-11-20T22:20:00Z
            timeZone: pt,
            crestForTeamID: { _ in nil }
        )
        XCTAssertEqual(model.stage, .before)
        XCTAssertFalse(model.isLive)
        XCTAssertEqual(model.away.abbreviation, "PIT")
        XCTAssertEqual(model.home.abbreviation, "CIN")
        XCTAssertEqual(model.away.currentPercentText, "34%")
        XCTAssertEqual(model.home.currentPercentText, "66%")
        XCTAssertTrue(model.showsProbabilityBar)
        XCTAssertNil(model.centerScoreText)
        XCTAssertNil(model.probabilityUnavailableText)
        XCTAssertTrue(model.topBadgeText.contains("Sun"))

        // Opening-only withheld / unpriced: bar hidden + explicit unavailable message.
        let unpriced = try decodeGame(#"""
        {
          "id": 21709,
          "away_team": "Texas A&M Aggies",
          "home_team": "Miami (OH) RedHawks",
          "away_team_data": {"team_id": 245, "abbreviation": "TA&M", "primary_color": "#500000", "secondary_color": "#FFFFFF"},
          "home_team_data": {"team_id": 193, "abbreviation": "M-OH", "primary_color": "#C41230", "secondary_color": "#FFFFFF"},
          "status": "scheduled",
          "sport": "basketball_ncaab"
        }
        """#)
        let withheld = WatchMatchupGameHeroModel297A.build(from: unpriced, now: now, timeZone: utc, crestForTeamID: { _ in nil })
        XCTAssertEqual(withheld.away.abbreviation, "TA&M")
        XCTAssertEqual(withheld.home.abbreviation, "M-OH")
        XCTAssertFalse(withheld.showsProbabilityBar)
        XCTAssertNotNil(withheld.probabilityUnavailableText)
        XCTAssertEqual(withheld.topBadgeText, "Scheduled · time unavailable")
    }

    func testLook1BLiveThreeWaySoccerAndScorelessFallbackAndSeparateClocks() throws {
        // Live two-way with distinct score vs probability clocks
        let liveGame = try decodeGame(#"""
        {
          "id": 21702,
          "away_team": "Nashville Predators",
          "home_team": "Anaheim Ducks",
          "away_team_data": {"team_id": 201, "abbreviation": "NSH", "primary_color": "#FFB81C", "secondary_color": "#041E42"},
          "home_team_data": {"team_id": 202, "abbreviation": "ANA", "primary_color": "#F47A38", "secondary_color": "#B9975B"},
          "status": "live",
          "sport": "icehockey_nhl",
          "away_score": 2,
          "home_score": 2,
          "score_observed_at": "2026-11-20T22:18:00Z",
          "espn": {"period": "2nd Period", "game_clock": "08:14"},
          "hero_probability": 0.52,
          "hero_probability_away": 0.48,
          "hero_probability_observed_at": "2026-11-20T22:15:00Z"
        }
        """#)
        let checkNow = ISO8601DateFormatter().date(from: "2026-11-20T22:19:00Z")!
        let liveModel = WatchMatchupGameHeroModel297A.build(
            from: liveGame,
            now: checkNow,
            timeZone: pt,
            crestForTeamID: { _ in nil }
        )
        XCTAssertEqual(liveModel.stage, .during)
        XCTAssertTrue(liveModel.isLive)
        XCTAssertEqual(liveModel.topBadgeText, "P2 08:14")
        XCTAssertEqual(liveModel.centerScoreText, "2–2")
        XCTAssertEqual(liveModel.away.currentPercentText, "48%")
        XCTAssertEqual(liveModel.home.currentPercentText, "52%")
        XCTAssertTrue(liveModel.showsProbabilityBar)
        XCTAssertEqual(liveModel.scoreAsOfText, "Score as of 1m ago")
        XCTAssertNotNil(liveModel.probabilityAsOfText)
        XCTAssertNotEqual(liveModel.scoreAsOfText, liveModel.probabilityAsOfText)

        // Three-way soccer: never manufacture away when absent; show Home/Draw/Away when served
        let soccerWithheldAway = try decodeGame(#"""
        {
          "id": 21703,
          "away_team": "Arsenal",
          "home_team": "Chelsea",
          "away_team_data": {"team_id": 359, "abbreviation": "ARS", "primary_color": "#EF0107", "secondary_color": "#FFFFFF"},
          "home_team_data": {"team_id": 363, "abbreviation": "CHE", "primary_color": "#034694", "secondary_color": "#FFFFFF"},
          "status": "live",
          "sport": "soccer_epl",
          "away_score": 1,
          "home_score": 1,
          "espn": {"period": "2nd Half", "game_clock": "67:12"},
          "hero_probability": 0.44,
          "current_odds": {"home_probability": 0.44, "draw_probability": 0.29}
        }
        """#)
        let soccerModelWithheld = WatchMatchupGameHeroModel297A.build(from: soccerWithheldAway, now: checkNow, timeZone: pt, crestForTeamID: { _ in nil })
        XCTAssertTrue(soccerModelWithheld.isThreeWaySoccer)
        XCTAssertNil(soccerModelWithheld.away.currentPercentText, "Must never invent away on 3-way soccer")
        XCTAssertEqual(soccerModelWithheld.drawPercentText, "29%")
        XCTAssertEqual(soccerModelWithheld.home.currentPercentText, "44%")

        // Scoreless live fallback (250-A / #13140): omit dashes cleanly
        let scorelessLive = try decodeGame(#"""
        {
          "id": 21704,
          "away_team": "Arsenal",
          "home_team": "Chelsea",
          "status": "live",
          "sport": "soccer_epl",
          "hero_probability": 0.44,
          "hero_probability_away": 0.27,
          "current_odds": {"home_probability": 0.44, "away_probability": 0.27, "draw_probability": 0.29}
        }
        """#)
        let scorelessModel = WatchMatchupGameHeroModel297A.build(from: scorelessLive, now: checkNow, timeZone: pt, crestForTeamID: { _ in nil })
        XCTAssertNil(scorelessModel.centerScoreText)
        XCTAssertEqual(scorelessModel.liveScoreExplanation, "Score unavailable")
        XCTAssertEqual(scorelessModel.away.currentPercentText, "27%")
        XCTAssertEqual(scorelessModel.drawPercentText, "29%")
        XCTAssertEqual(scorelessModel.home.currentPercentText, "44%")
    }

    func testLook1CFinalUsesPregameNeverClosedAndOmitsBar() throws {
        let finalGame = try decodeGame(#"""
        {
          "id": 15344730,
          "away_team": "Boston Celtics",
          "home_team": "Philadelphia 76ers",
          "away_team_data": {"team_id": 2, "abbreviation": "BOS", "primary_color": "#007A33", "secondary_color": "#BA9653"},
          "home_team_data": {"team_id": 20, "abbreviation": "PHI", "primary_color": "#006BB6", "secondary_color": "#ED174C"},
          "status": "final",
          "sport": "basketball_nba",
          "away_score": 123,
          "home_score": 101,
          "score_observed_at": "2026-11-20T05:10:00Z",
          "prematch_odds": {"away_probability": 0.54, "home_probability": 0.46}
        }
        """#)
        let finalModel = WatchMatchupGameHeroModel297A.build(
            from: finalGame,
            now: Date(),
            timeZone: pt,
            crestForTeamID: { _ in nil }
        )
        XCTAssertEqual(finalModel.stage, .after)
        XCTAssertEqual(finalModel.topBadgeText, "FINAL")
        XCTAssertEqual(finalModel.centerScoreText, "123–101")
        XCTAssertTrue(finalModel.away.isWinner)
        XCTAssertTrue(finalModel.home.isLoser)
        XCTAssertEqual(finalModel.away.pregameText, "Pregame 54%")
        XCTAssertEqual(finalModel.home.pregameText, "Pregame 46%")
        XCTAssertFalse(finalModel.showsProbabilityBar)
        XCTAssertNil(finalModel.probabilityAsOfText)
        XCTAssertEqual(finalModel.bottomSummaryText, "Final · BOS 123–101 PHI")
        XCTAssertFalse((finalModel.bottomSummaryText ?? "").contains("Closed"))
        XCTAssertFalse((finalModel.away.pregameText ?? "").contains("Closed"))

        // Closed unverified: keeps "Closed · result unverified", no checkmark, no bar
        let closedGame = try decodeGame(#"""
        {
          "id": 21706,
          "away_team": "Kansas City Chiefs",
          "home_team": "Buffalo Bills",
          "status": "closed",
          "sport": "americanfootball_nfl",
          "away_score": 20,
          "home_score": 24,
          "prematch_odds": {"away_probability": 0.48, "home_probability": 0.52}
        }
        """#)
        let closedModel = WatchMatchupGameHeroModel297A.build(from: closedGame, now: Date(), timeZone: pt, crestForTeamID: { _ in nil })
        XCTAssertEqual(closedModel.stage, .closedUnverified)
        XCTAssertFalse(closedModel.away.isWinner)
        XCTAssertFalse(closedModel.home.isWinner)
        XCTAssertFalse(closedModel.showsProbabilityBar)
        XCTAssertEqual(closedModel.bottomSummaryText, "Closed · result unverified")
    }

    #if canImport(UIKit)
    private func crestData(abbr: String, fill: UIColor) -> Data? {
        if let dir = ProcessInfo.processInfo.environment["BUILDER_C_CREST_DIR_297A"], !dir.isEmpty {
            let url = URL(fileURLWithPath: dir, isDirectory: true).appendingPathComponent("\(abbr.lowercased()).png")
            if let data = try? Data(contentsOf: url), !data.isEmpty {
                return data
            }
        }
        // Deterministic offline PNG crest for CI runners without network access.
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 64, height: 64))
        let img = renderer.image { ctx in
            fill.setFill()
            UIBezierPath(ovalIn: CGRect(x: 4, y: 4, width: 56, height: 56)).fill()
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 20, weight: .heavy),
                .foregroundColor: UIColor.white
            ]
            let s = abbr as NSString
            let size = s.size(withAttributes: attrs)
            s.draw(at: CGPoint(x: (64 - size.width) / 2, y: (64 - size.height) / 2), withAttributes: attrs)
        }
        return img.pngData()
    }

    func testRender41mmAnd45mmLooks1A1B1CDefaultAndAX5WithoutEllipsis() throws {
        let fixedNow = ISO8601DateFormatter().date(from: "2026-11-20T22:20:00Z")!
        let pacific = self.pt

        let scheduled = try decodeGame(#"""
        {
          "id": 21701,
          "away_team": "Pittsburgh Steelers",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"team_id": 101, "abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"team_id": 102, "abbreviation": "CIN", "primary_color": "#FB4F14", "secondary_color": "#000000"},
          "status": "scheduled",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-22T18:00:00Z",
          "hero_probability": 0.66,
          "hero_probability_away": 0.34,
          "hero_probability_observed_at": "2026-11-20T21:29:00Z"
        }
        """#)
        let live = try decodeGame(#"""
        {
          "id": 21702,
          "away_team": "Nashville Predators",
          "home_team": "Anaheim Ducks",
          "away_team_data": {"team_id": 201, "abbreviation": "NSH", "primary_color": "#FFB81C", "secondary_color": "#041E42"},
          "home_team_data": {"team_id": 202, "abbreviation": "ANA", "primary_color": "#F47A38", "secondary_color": "#B9975B"},
          "status": "live",
          "sport": "icehockey_nhl",
          "away_score": 2,
          "home_score": 2,
          "score_observed_at": "2026-11-20T22:19:00Z",
          "espn": {"period": "2nd Period", "game_clock": "08:14"},
          "hero_probability": 0.52,
          "hero_probability_away": 0.48,
          "hero_probability_observed_at": "2026-11-20T22:19:15Z"
        }
        """#)
        let liveSoccer = try decodeGame(#"""
        {
          "id": 21703,
          "away_team": "Arsenal",
          "home_team": "Chelsea",
          "away_team_data": {"team_id": 359, "abbreviation": "ARS", "primary_color": "#EF0107", "secondary_color": "#FFFFFF"},
          "home_team_data": {"team_id": 363, "abbreviation": "CHE", "primary_color": "#034694", "secondary_color": "#FFFFFF"},
          "status": "live",
          "sport": "soccer_epl",
          "away_score": 1,
          "home_score": 2,
          "score_observed_at": "2026-11-20T22:19:00Z",
          "espn": {"period": "2nd Half", "game_clock": "74:10"},
          "hero_probability": 0.58,
          "hero_probability_away": 0.19,
          "hero_probability_observed_at": "2026-11-20T22:19:20Z",
          "current_odds": {"home_probability": 0.58, "away_probability": 0.19, "draw_probability": 0.23}
        }
        """#)
        let final = try decodeGame(#"""
        {
          "id": 15344730,
          "away_team": "Boston Celtics",
          "home_team": "Philadelphia 76ers",
          "away_team_data": {"team_id": 2, "abbreviation": "BOS", "primary_color": "#007A33", "secondary_color": "#BA9653"},
          "home_team_data": {"team_id": 20, "abbreviation": "PHI", "primary_color": "#006BB6", "secondary_color": "#ED174C"},
          "status": "final",
          "sport": "basketball_nba",
          "away_score": 123,
          "home_score": 101,
          "score_observed_at": "2026-11-20T05:10:00Z",
          "prematch_odds": {"away_probability": 0.54, "home_probability": 0.46}
        }
        """#)

        let crests: [Int: Data?] = [
            101: crestData(abbr: "pit", fill: UIColor(red: 1.0, green: 0.71, blue: 0.07, alpha: 1)),
            102: crestData(abbr: "cin", fill: UIColor(red: 0.98, green: 0.31, blue: 0.08, alpha: 1)),
            201: crestData(abbr: "nsh", fill: UIColor(red: 1.0, green: 0.72, blue: 0.11, alpha: 1)),
            202: crestData(abbr: "ana", fill: UIColor(red: 0.96, green: 0.48, blue: 0.22, alpha: 1)),
            359: crestData(abbr: "ars", fill: UIColor(red: 0.94, green: 0.0, blue: 0.03, alpha: 1)),
            363: crestData(abbr: "che", fill: UIColor(red: 0.01, green: 0.27, blue: 0.58, alpha: 1)),
            2: crestData(abbr: "bos", fill: UIColor(red: 0.0, green: 0.48, blue: 0.2, alpha: 1)),
            20: crestData(abbr: "phi", fill: UIColor(red: 0.0, green: 0.42, blue: 0.71, alpha: 1)),
        ]

        let specimens: [(title: String, game: WatchSelectedGame)] = [
            ("1A · Scheduled", scheduled),
            ("1B · Live", live),
            ("1B · 3-Way Soccer", liveSoccer),
            ("1C · Final", final),
        ]

        let sizes: [(tag: String, caseWidth: CGFloat, caseHeight: CGFloat, dynType: DynamicTypeSize)] = [
            ("default", 176, 215, .large),
            ("ax5", 176, 215, .accessibility5),
        ]

        for sizeSpec in sizes {
            let sheet = HStack(alignment: .top, spacing: 14) {
                ForEach([("41 mm", CGFloat(176)), ("45 mm", CGFloat(198))], id: \.0) { watchCase in
                    VStack(alignment: .leading, spacing: 12) {
                        Text("\(watchCase.0) (\(Int(watchCase.1)) pt)")
                            .font(.caption.bold())
                            .foregroundStyle(.white.opacity(0.85))
                        ForEach(specimens, id: \.title) { specimen in
                            let m = WatchMatchupGameHeroModel297A.build(
                                from: specimen.game,
                                now: fixedNow,
                                timeZone: pacific,
                                crestForTeamID: { crests[$0] ?? nil }
                            )
                            VStack(alignment: .leading, spacing: 4) {
                                Text(specimen.title)
                                    .font(.caption2.bold())
                                    .foregroundStyle(.white.opacity(0.7))
                                WatchMatchupGamePageHeroView297A(model: m, caseWidth: watchCase.1)
                                    .environment(\.dynamicTypeSize, sizeSpec.dynType)
                                    .padding(6)
                                    .frame(width: watchCase.1, alignment: .leading)
                                    .background(Color.black)
                                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 22, style: .continuous)
                                            .strokeBorder(Color.white.opacity(0.22), lineWidth: 1)
                                    )
                            }
                        }
                    }
                }
            }
            .padding(16)
            .background(Color(red: 0.06, green: 0.07, blue: 0.09))
            .environment(\.colorScheme, .dark)

            let host = hostForMeasurement(sheet, at: .large)
            host.overrideUserInterfaceStyle = .dark
            let fitting = host.sizeThatFits(in: CGSize(width: 440, height: 3200))
            let renderWidth = max(420, ceil(fitting.width))
            let renderHeight = max(500, ceil(fitting.height) + 12)
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: renderWidth, height: renderHeight))

            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = .dark
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }

            let until = Date().addingTimeInterval(0.25)
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
            try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
            let ocrLines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = ocrLines.joined(separator: "\n")

            XCTAssertFalse(
                ocrLines.contains(where: { $0.contains("…") || $0.contains("...") }),
                "Watch Matchup sheet (\(sizeSpec.tag)) must have zero ellipsis; got:\n\(joined)"
            )
            XCTAssertTrue(joined.contains("Pregame 54%") || joined.contains("54%"), "Final must display Pregame 54% (\(sizeSpec.tag)); got:\n\(joined)")
            XCTAssertFalse(joined.contains("Closed"), "Look 1C Final must never print Closed (\(sizeSpec.tag)); got:\n\(joined)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_297A"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("297a-watch-game-page-41-45mm-\(sizeSpec.tag).png"))
                }
            }
        }
    }
    #endif
}
