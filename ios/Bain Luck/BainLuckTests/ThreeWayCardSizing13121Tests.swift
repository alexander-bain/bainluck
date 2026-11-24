import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13121 (`1.0.7`): On a soccer card (`EventCardView` in `My Stuff`, `Sports`, `Search`),
/// nothing shrinks below a two-way card's type size, no line ends in `"…"`, and when
/// `away_probability` is withheld (`#5363`, e.g. live MLS event `15345867`
/// `Philadelphia Union @ New England Revolution` from TestFlight report `236`), the empty
/// `Chance` cell keeps its column width so `Proj.` (`2`) stays under `Proj.` above `1`
/// rather than sliding into the `Chance` column.
@MainActor
final class ThreeWayCardSizing13121Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        try makeDecoder().decode(FeedEventData.self, from: Data(json.utf8))
    }

    /// Exact shape of `GET /api/events/15345867` (`MLS · Sat, Nov 21 — Philadelphia Union @ New England Revolution`)
    /// from TestFlight bug report `236` (`#13121`): `home_probability: 0.31`, `away_probability: null`,
    /// `draw_probability: null`, `projected_away_score: 1.7` (`2`), `projected_home_score: 1.2` (`1`).
    private func unionAtRevolutionReport236() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 15345867,
          "external_id": "b7ca8ba1c5ab8138e04db89aeb91b98a",
          "sport": "soccer_usa_mls",
          "sport_name": "MLS",
          "away_team": "Philadelphia Union",
          "home_team": "New England Revolution",
          "commence_time": "2026-11-21T19:00:00Z",
          "status": "scheduled",
          "away_team_data": {
            "primary_color": "#051f31",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/10739.png",
            "abbreviation": "PHI"
          },
          "home_team_data": {
            "primary_color": "#022166",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/189.png",
            "abbreviation": "NE"
          },
          "current_odds": {
            "home_probability": 0.31,
            "away_probability": null,
            "away_rendered_percent": null,
            "home_rendered_percent": 31,
            "projected_home_score": 1.2,
            "projected_away_score": 1.7
          }
        }
        """)
    }

    private func wolvesAtForestScheduled() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 91312101,
          "external_id": "epl_wolves_forest",
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "away_team": "Wolverhampton Wanderers",
          "home_team": "Nottingham Forest",
          "commence_time": "2026-11-21T15:00:00Z",
          "status": "scheduled",
          "away_team_data": {
            "primary_color": "#fdb913",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/380.png",
            "abbreviation": "WOL"
          },
          "home_team_data": {
            "primary_color": "#dd0000",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
            "abbreviation": "NFO"
          },
          "current_odds": {
            "away_probability": 0.28,
            "home_probability": 0.46,
            "draw_probability": 0.26,
            "away_rendered_percent": 28,
            "home_rendered_percent": 46
          }
        }
        """)
    }

    private func wolvesAtForestLive() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 91312102,
          "external_id": "epl_wolves_forest_live",
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "away_team": "Wolverhampton Wanderers",
          "home_team": "Nottingham Forest",
          "commence_time": "2026-11-19T20:00:00Z",
          "status": "live",
          "away_score": 1,
          "home_score": 1,
          "away_team_data": {
            "primary_color": "#fdb913",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/380.png",
            "abbreviation": "WOL"
          },
          "home_team_data": {
            "primary_color": "#dd0000",
            "logo_small": "https://a.espncdn.com/i/teamlogos/soccer/500/393.png",
            "abbreviation": "NFO"
          },
          "espn": {"game_clock": "68'", "period": "2nd Half"},
          "current_odds": {
            "away_probability": 0.29,
            "home_probability": 0.37,
            "draw_probability": 0.34,
            "away_rendered_percent": 29,
            "home_rendered_percent": 37
          },
          "prematch_odds": {
            "away_probability": 0.28,
            "home_probability": 0.46,
            "draw_probability": 0.26
          }
        }
        """)
    }

    private func celticsAtKingsScheduled() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 15349058,
          "external_id": "nba_bos_sac",
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Sacramento Kings",
          "commence_time": "2026-11-22T03:00:00Z",
          "status": "scheduled",
          "current_odds": {
            "away_probability": 0.8825,
            "home_probability": 0.1175,
            "away_rendered_percent": 88,
            "home_rendered_percent": 12
          }
        }
        """)
    }

    func testThreeWaySoccerCardUsesExactSameTeamNameFontSizeAsTwoWayBasketballCard() throws {
        let report236MLS = EventCardView(event: try unionAtRevolutionReport236(), reason: nil)
        let scheduledSoccer = EventCardView(event: try wolvesAtForestScheduled(), reason: "Starting Saturday — tight match")
        let liveSoccer = EventCardView(event: try wolvesAtForestLive(), reason: nil)
        let basketball = EventCardView(event: try celticsAtKingsScheduled(), reason: nil)

        XCTAssertTrue(report236MLS.isThreeWayCard13121)
        XCTAssertTrue(scheduledSoccer.isThreeWayCard13121)
        XCTAssertTrue(liveSoccer.isThreeWayCard13121)
        XCTAssertFalse(basketball.isThreeWayCard13121)

        for soccerCard in [report236MLS, scheduledSoccer, liveSoccer] {
            XCTAssertEqual(
                soccerCard.resolvedCompactTeamNameFontSizeForTest13121,
                basketball.resolvedCompactTeamNameFontSizeForTest13121,
                accuracy: 0.01,
                "Soccer card must never shrink below a two-way basketball card's name size"
            )
        }
    }

    private func captureSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        width: CGFloat = 390,
        height: CGFloat = 860
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, scheme), at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 1_200_000_000)
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeObservations(in image: UIImage) throws -> [(text: String, box: CGRect)] {
        let upscaledSize = CGSize(width: image.size.width * 2, height: image.size.height * 2)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        let hiRes = UIGraphicsImageRenderer(size: upscaledSize, format: fmt).image { _ in
            image.draw(in: CGRect(origin: .zero, size: upscaledSize))
        }
        let cgImage = try XCTUnwrap(hiRes.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let top = obs.topCandidates(1).first?.string else { return nil }
            return (text: top, box: obs.boundingBox)
        }
    }

    func testReport236MLSCardKeepsProjectedScoreInProjColumnWhenAwayChanceIsNil() async throws {
        let mls = try unionAtRevolutionReport236()
        let suiteName = "Test13121.MLS.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let cardList = List {
            EventCardView(event: mls, reason: nil)
                .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
        }
        .listStyle(.insetGrouped)
        .environmentObject(pinManager)

        let img = try await captureSnapshot(cardList, scheme: .light, width: 390, height: 320)
        let obs = try recognizeObservations(in: img)
        let joined = obs.map(\.text).joined(separator: " | ")

        let proj2 = try XCTUnwrap(
            obs.first(where: { $0.text.trimmingCharacters(in: .whitespaces) == "2" }),
            "Expected away projected score '2' in OCR: \(joined)"
        )
        let chance31 = try XCTUnwrap(
            obs.first(where: { $0.text.contains("31%") }),
            "Expected home chance '31%' in OCR: \(joined)"
        )
        XCTAssertLessThan(
            proj2.box.maxX,
            chance31.box.minX,
            "Away projected score '2' must stay in the Proj. column to the left of '31%', never sliding under Chance when away_probability is nil (report 236)"
        )
    }

    func testMyStuffSoccerCardBesideBasketballCardHasZeroEllipsisAndExports390Renders() async throws {
        let report236MLS = try unionAtRevolutionReport236()
        let scheduledSoccer = try wolvesAtForestScheduled()
        let liveSoccer = try wolvesAtForestLive()
        let basketball = try celticsAtKingsScheduled()

        let suiteName = "Test13121.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let myStuffList = List {
            Section {
                EventCardView(event: basketball, reason: nil)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                EventCardView(event: report236MLS, reason: nil)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                EventCardView(event: scheduledSoccer, reason: "Close match on Saturday")
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                EventCardView(event: liveSoccer, reason: nil)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
            } header: {
                Label("Upcoming & Live (My Stuff)", systemImage: "bookmark.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.orange)
                    .textCase(nil)
            }
        }
        .listStyle(.insetGrouped)
        .environmentObject(pinManager)

        let lightImg = try await captureSnapshot(myStuffList, scheme: .light, width: 390, height: 940)
        let darkImg = try await captureSnapshot(myStuffList, scheme: .dark, width: 390, height: 940)

        let joined = try recognizeObservations(in: lightImg).map(\.text).joined(separator: " | ")
        for expected in ["Celtics", "Kings", "Philadelphia", "Union", "Revolution", "Wolverhampton", "Wanderers", "Draw", "Nottingham", "Forest"] {
            XCTAssertTrue(
                joined.localizedCaseInsensitiveContains(expected),
                "Expected full word '\(expected)' in rendered My Stuff list; OCR read: \(joined)"
            )
        }
        XCTAssertFalse(joined.contains("…"), "No line on the My Stuff soccer card may end in '…': \(joined)")
        XCTAssertFalse(joined.contains("..."), "No line on the My Stuff soccer card may end in '...': \(joined)")

        if let outDir = ProcessInfo.processInfo.environment["RENDER_13121_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            try XCTUnwrap(lightImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13121-mystuff-soccer-beside-nba-light-390.png"))
            try XCTUnwrap(darkImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13121-mystuff-soccer-beside-nba-dark-390.png"))
        }
    }

    func testHyphenatedSoccerClubKeepsScoreInlineAt390And440() async throws {
        XCTAssertEqual(
            CardTeamNameSizing.lineBreakSegments(in: "FC Lausanne-Sport"),
            ["FC", "Lausanne-", "Sport"]
        )

        let event = try decodeEvent("""
        {
          "id": 910805,
          "external_id": "swiss_lausanne_zurich",
          "sport": "soccer_switzerland_superleague",
          "sport_name": "Swiss Super League",
          "away_team": "FC Lausanne-Sport",
          "home_team": "FC Zurich",
          "commence_time": "2026-11-22T15:00:00Z",
          "status": "live",
          "away_score": 2,
          "home_score": 1,
          "espn": { "period": "2H", "game_clock": "74'" },
          "current_odds": {
            "away_probability": 0.48,
            "home_probability": 0.29,
            "draw_probability": 0.23,
            "away_rendered_percent": 48,
            "home_rendered_percent": 29
          }
        }
        """)

        let suiteName = "Test13121.Lausanne.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        for width: CGFloat in [390, 440] {
            let cardList = List {
                EventCardView(event: event, reason: nil)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
            }
            .listStyle(.insetGrouped)
            .environmentObject(pinManager)

            let img = try await captureSnapshot(cardList, scheme: .light, width: width, height: 320)
            let obs = try recognizeObservations(in: img)
            let joined = obs.map(\.text).joined(separator: " | ")

            XCTAssertFalse(joined.contains("…"), "width \(width): truncated '\(joined)'")
            let lausanne = try XCTUnwrap(
                obs.first(where: { $0.text.localizedCaseInsensitiveContains("Lausanne") }),
                "Expected Lausanne in OCR at \(width): \(joined)"
            )
            let score2 = try XCTUnwrap(
                obs.first(where: { $0.text.trimmingCharacters(in: .whitespaces) == "2" }),
                "Expected away score '2' in OCR at \(width): \(joined)"
            )
            XCTAssertLessThan(lausanne.box.maxX, score2.box.minX, "width \(width): name & score sit side-by-side")
            XCTAssertLessThanOrEqual(
                abs(lausanne.box.maxY - score2.box.maxY),
                0.15,
                "width \(width): FC Lausanne-Sport must share its score line instead of pushing score to a second line (lausanne=\(lausanne.box), score2=\(score2.box))"
            )

            let att = XCTAttachment(image: img)
            att.name = "108-lausanne-inline-score-\(Int(width)).png"
            att.lifetime = .keepAlways
            add(att)
        }
    }
}
