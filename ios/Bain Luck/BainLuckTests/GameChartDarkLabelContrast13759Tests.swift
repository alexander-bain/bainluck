import Foundation
import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13759 — Dark appearance game chart side labels, axis percentages, and team ink.
///
/// Proves that `EventDetailView.teamColorHexes(_:colorScheme:)` routes dark-mode
/// pages through `TeamTextContrast` with WCAG AA normal-text contrast (`>= 4.5:1`)
/// against `#1C1C1E` (`0.0116122`) and `TeamTextContrast.darkSurfaceLuminance` (`0.012`),
/// fixing unreadable navy (`#002D62`), black (`#000000`), dark-green (`#004C54`),
/// and sub-4.5 red (`#CE1126`) chart labels while preserving `ProbabilityBarPalette`
/// pair separation and light-mode card colours.
@MainActor
final class GameChartDarkLabelContrast13759Tests: XCTestCase {

    /// Dark `Color.cardBackground` (`#1C1C1E` = `rgb(28, 28, 30)`).
    private static let darkCardSurfaceHex = "#1C1C1E"

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func makeEvent(
        id: Int = 15_353_823,
        homeName: String = "New Jersey Devils",
        homeAbbrev: String = "NJ",
        homePrimary: String?,
        homeSecondary: String? = nil,
        awayName: String = "Columbus Blue Jackets",
        awayAbbrev: String = "CBJ",
        awayPrimary: String?,
        awaySecondary: String? = nil
    ) throws -> EventDetail {
        func hexField(_ hex: String?) -> String {
            guard let hex else { return "null" }
            let escaped = hex.replacingOccurrences(of: "\"", with: "\\\"")
            return "\"\(escaped)\""
        }
        return try decoder().decode(EventDetail.self, from: Data("""
        {
          "id": \(id),
          "sport": "icehockey_nhl",
          "sport_name": "NHL",
          "status": "completed",
          "commence_time": "2026-11-24T00:00:00Z",
          "completed_at": "2026-11-24T02:35:00Z",
          "home_team": "\(homeName)",
          "away_team": "\(awayName)",
          "home_score": 4,
          "away_score": 2,
          "home_team_data": {
            "team_id": 1,
            "abbreviation": "\(homeAbbrev)",
            "primary_color": \(hexField(homePrimary)),
            "secondary_color": \(hexField(homeSecondary))
          },
          "away_team_data": {
            "team_id": 2,
            "abbreviation": "\(awayAbbrev)",
            "primary_color": \(hexField(awayPrimary)),
            "secondary_color": \(hexField(awaySecondary))
          },
          "current_odds": { "home_probability": 0.68, "away_probability": 0.32 }
        }
        """.utf8))
    }

    private func assertClearsDarkAA(_ hex: String, context: String) {
        let darkCardLum = TeamTextContrast.relativeLuminance(Self.darkCardSurfaceHex) ?? TeamTextContrast.darkSurfaceLuminance
        let cardRatio = TeamTextContrast.contrast(hex, againstSurfaceLuminance: darkCardLum) ?? 0
        let standardDarkRatio = TeamTextContrast.contrast(hex, againstSurfaceLuminance: TeamTextContrast.darkSurfaceLuminance) ?? 0
        XCTAssertGreaterThanOrEqual(
            cardRatio,
            TeamTextContrast.darkTextMinimumRatio,
            "\(context): \(hex) has contrast \(cardRatio) < 4.5 on #1C1C1E"
        )
        XCTAssertGreaterThanOrEqual(
            standardDarkRatio,
            TeamTextContrast.darkTextMinimumRatio,
            "\(context): \(hex) has contrast \(standardDarkRatio) < 4.5 on darkSurfaceLuminance"
        )
    }

    func testColumbusNavyAndDevilsRedClearFourPointFiveToOneInDarkAppearance() throws {
        let cbjNjd = try Self.makeEvent(
            homePrimary: "#CE1126",
            awayPrimary: "#002D62"
        )

        // Contrast of the raw colors measured in #13759 on #1C1C1E
        let rawLum = TeamTextContrast.relativeLuminance(Self.darkCardSurfaceHex)!
        XCTAssertLessThan(TeamTextContrast.contrast("#002D62", againstSurfaceLuminance: rawLum) ?? 0, 1.5)
        XCTAssertLessThan(TeamTextContrast.contrast("#CE1126", againstSurfaceLuminance: rawLum) ?? 0, 4.0)

        let darkPair = EventDetailView.teamColorHexes(cbjNjd, colorScheme: .dark)
        assertClearsDarkAA(darkPair.away, context: "CBJ navy away")
        assertClearsDarkAA(darkPair.home, context: "NJD red home")
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(darkPair.away), .blue)
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(darkPair.home), .red)
        XCTAssertTrue(ProbabilityBarPalette.distinguishable(darkPair.away, darkPair.home))

        // Light mode keeps light-card behaviour unchanged
        let lightPair = EventDetailView.teamColorHexes(cbjNjd, colorScheme: .light)
        XCTAssertEqual(lightPair.away, "#002D62")
        XCTAssertEqual(lightPair.home, "#CE1126")
    }

    func testEveryDarkNavyBlackAndDarkGreenTeamPairClearsFourPointFiveInDarkAppearance() throws {
        let swatches: [(label: String, primary: String?, secondary: String?)] = [
            ("cbj-navy", "#002D62", nil),
            ("dal-cowboys-navy", "#041E42", nil),
            ("chi-bears-navy", "#0C2340", nil),
            ("sea-navy", "#002244", nil),
            ("black-pure", "#000000", nil),
            ("black-charcoal", "#101820", "#000000"),
            ("slate-dark", "#111827", nil),
            ("eagles-midnight-green", "#004C54", nil),
            ("jets-dark-green", "#125740", nil),
            ("packers-dark-green", "#203731", "#FFB612"),
            ("celtics-green", "#007A33", nil),
            ("ravens-purple", "#241773", "#9E7C0C"),
            ("devils-red", "#CE1126", nil),
            ("white", "#FFFFFF", nil),
            ("absent", nil, nil),
            ("malformed", "bad", nil),
        ]

        for away in swatches {
            for home in swatches {
                let event = try Self.makeEvent(
                    homeName: "Home \(home.label)",
                    homeAbbrev: "HM",
                    homePrimary: home.primary,
                    homeSecondary: home.secondary,
                    awayName: "Away \(away.label)",
                    awayAbbrev: "AW",
                    awayPrimary: away.primary,
                    awaySecondary: away.secondary
                )

                let darkPair = EventDetailView.teamColorHexes(event, colorScheme: .dark)
                assertClearsDarkAA(darkPair.away, context: "dark away(\(away.label)) vs home(\(home.label))")
                assertClearsDarkAA(darkPair.home, context: "dark away(\(away.label)) home(\(home.label))")
                XCTAssertTrue(
                    ProbabilityBarPalette.distinguishable(darkPair.away, darkPair.home),
                    "dark pair \(darkPair) not distinguishable for (\(away.label), \(home.label))"
                )

                let lightPair = EventDetailView.teamColorHexes(event, colorScheme: .light)
                XCTAssertTrue(TeamTextContrast.readableOnCard(lightPair.away))
                XCTAssertTrue(TeamTextContrast.readableOnCard(lightPair.home))
                XCTAssertTrue(ProbabilityBarPalette.distinguishable(lightPair.away, lightPair.home))
            }
        }
    }

    func testEveryRGBSampleClearsFourPointFiveOnDarkGamePage() throws {
        // Sample the full RGB cube (6 x 6 x 6 = 216 colours) so no hue/darkness region can slip below 4.5:1.
        let steps = [0x00, 0x22, 0x55, 0x88, 0xBB, 0xFF]
        for r in steps {
            for g in steps {
                for b in steps {
                    let hex = String(format: "#%02X%02X%02X", r, g, b)
                    let event = try Self.makeEvent(homePrimary: hex, awayPrimary: hex)
                    let pair = EventDetailView.teamColorHexes(event, colorScheme: .dark)
                    assertClearsDarkAA(pair.away, context: "RGB cube away \(hex)")
                    assertClearsDarkAA(pair.home, context: "RGB cube home \(hex)")
                    XCTAssertTrue(ProbabilityBarPalette.distinguishable(pair.away, pair.home))
                }
            }
        }
    }

    func testRenderDarkChartSideLabelsSweepSheet390() throws {
        let sampleHistory = try Self.decoder().decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 15353823,
          "home_team": "Home",
          "away_team": "Away",
          "status": "completed",
          "commence_time": "2026-11-24T00:00:00Z",
          "completed_at": "2026-11-24T02:35:00Z",
          "pre_window_omitted": false,
          "commence_time_is_kickoff": true,
          "history": [
            {"timestamp": "2026-11-23T23:00:00Z", "home_probability": 0.56, "away_probability": 0.44},
            {"timestamp": "2026-11-24T00:30:00Z", "home_probability": 0.51, "away_probability": 0.49},
            {"timestamp": "2026-11-24T01:30:00Z", "home_probability": 0.62, "away_probability": 0.38},
            {"timestamp": "2026-11-24T02:35:00Z", "home_probability": 0.72, "away_probability": 0.28}
          ],
          "period_markers": [
            {"timestamp": "2026-11-24T00:00:00Z", "label": "P1", "period": "1"},
            {"timestamp": "2026-11-24T02:35:00Z", "label": "Final", "period": "Final"}
          ]
        }
        """.utf8))

        let cbjNjd = try Self.makeEvent(
            id: 1,
            homeName: "New Jersey Devils",
            homeAbbrev: "NJ",
            homePrimary: "#CE1126",
            awayName: "Columbus Blue Jackets",
            awayAbbrev: "CBJ",
            awayPrimary: "#002D62"
        )
        let pitBos = try Self.makeEvent(
            id: 2,
            homeName: "Boston Bruins",
            homeAbbrev: "BOS",
            homePrimary: "#FFB81C",
            awayName: "Pittsburgh Penguins",
            awayAbbrev: "PIT",
            awayPrimary: "#000000"
        )
        let phiNyj = try Self.makeEvent(
            id: 3,
            homeName: "New York Jets",
            homeAbbrev: "NYJ",
            homePrimary: "#125740",
            awayName: "Philadelphia Eagles",
            awayAbbrev: "PHI",
            awayPrimary: "#004C54"
        )

        let fixedCBJ = EventDetailView.teamColorHexes(cbjNjd, colorScheme: .dark)
        let beforeCBJ = EventDetailView.teamColorHexes(cbjNjd, colorScheme: .light)
        let fixedPIT = EventDetailView.teamColorHexes(pitBos, colorScheme: .dark)
        let fixedPHI = EventDetailView.teamColorHexes(phiNyj, colorScheme: .dark)

        let panels: [(filename: String, event: EventDetail, hexes: (away: String, home: String))] = [
            ("before-navy-cbj-dark-390.png", cbjNjd, beforeCBJ),
            ("after-navy-cbj-dark-390.png", cbjNjd, fixedCBJ),
            ("after-black-pit-dark-390.png", pitBos, fixedPIT),
            ("after-darkgreen-phi-dark-390.png", phiNyj, fixedPHI),
        ]

        for panel in panels {
            let colors = (away: Color(hex: panel.hexes.away), home: Color(hex: panel.hexes.home))
            let img = renderChartDark390 {
                OddsChartView(
                    eventId: panel.event.id,
                    teamColors: colors,
                    commenceTime: panel.event.commenceTime,
                    status: panel.event.status,
                    homeTeamName: panel.event.homeTeam,
                    awayTeamName: panel.event.awayTeam,
                    homeTeamAbbrev: panel.event.homeTeamData?.abbreviation,
                    awayTeamAbbrev: panel.event.awayTeamData?.abbreviation,
                    sportKey: "americanfootball_nfl",
                    homeScore: panel.event.homeScore,
                    awayScore: panel.event.awayScore,
                    servedHomeProbability: 0.72,
                    servedAwayProbability: 0.28,
                    selectedRange: .constant(.all),
                    preloadedHistory: sampleHistory
                )
                .padding(12)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                .padding(12)
                .frame(width: 390, height: 390, alignment: .topLeading)
                .background(Color.groupedBackground)
            }
            XCTAssertEqual(img.size.width, 390, accuracy: 0.5)

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13759_DIR"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                try XCTUnwrap(img.pngData()).write(
                    to: dirURL.appendingPathComponent(panel.filename),
                    options: .atomic
                )
            }
        }
    }

    private func renderChartDark390<Content: View>(@ViewBuilder content: () -> Content) -> UIImage {
        let host = UIHostingController(
            rootView: content()
                .environment(\.colorScheme, .dark)
                .environment(\.dynamicTypeSize, .large)
        )
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = .dark
        host.view.backgroundColor = .black
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 390)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = .dark
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<5 {
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.04))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }
}
