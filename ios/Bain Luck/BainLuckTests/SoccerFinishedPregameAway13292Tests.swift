import XCTest
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
@testable import Bain_Luck

/// #13292 — Finished three-way soccer games must surface the away pregame chance
/// consistently with Discover's served `prematch_odds`:
/// 1) 3-way `prematch_odds` carrying `home_rendered_percent` + `away_rendered_percent`
///    keeps those exact whole percents when the remaining draw share sums cleanly to 100%.
/// 2) When `draw_probability` is omitted on a venue row whose `home + away < 0.985`
///    (explicit away price, not a `1 - home` complement), the 2-row fallback prints
///    both `Home` and `Away` pregame chances instead of blanking out the away cell.
/// 3) Complement-only soccer rows (`home + away >= 0.985` or missing away) still
///    withhold away per Ruling 196-A / #5271.
@MainActor
final class SoccerFinishedPregameAway13292Tests: XCTestCase {

    private func decodeEvent(
        prematchOddsJSON: String
    ) throws -> EventDetail {
        let json = """
        {
          "id": 15342130,
          "sport": "soccer_spain_la_liga",
          "sport_name": "La Liga",
          "home_team": "Athletic Bilbao",
          "away_team": "Espanyol",
          "status": "completed",
          "commence_time": "2026-11-20T20:00:00Z",
          "completed_at": "2026-11-20T21:55:00Z",
          "home_score": 0,
          "away_score": 1,
          "home_team_data": {
            "primary_color": "#EE2523",
            "secondary_color": "#FFFFFF",
            "abbreviation": "ATH"
          },
          "away_team_data": {
            "primary_color": "#007FC8",
            "secondary_color": "#FFFFFF",
            "abbreviation": "ESP"
          },
          "prematch_odds": \(prematchOddsJSON)
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    func testThreeWayAndDrawlessVenuePrematchShowAwayPregameWhileComplementStillWithholds() async throws {
        // 1. Live `15342130` shape with `draw_probability: 0.195`: must keep `69%`, `12%`, `19%` (sums to 100% and agrees with Discover "12%").
        let liveThreeWay = try decodeEvent(prematchOddsJSON: """
        {
          "home_probability": 0.685,
          "away_probability": 0.115,
          "draw_probability": 0.195,
          "home_rendered_percent": 69,
          "away_rendered_percent": 12,
          "source": "kalshi"
        }
        """)
        let liveModel = EventSportHeadlines12472.resolve(
            event: liveThreeWay,
            awayFullName: "Espanyol",
            homeFullName: "Athletic Bilbao",
            liveStatusText: nil,
            hasScore: true,
            numberStreams: false
        )
        XCTAssertEqual(liveModel.rows.count, 3)
        XCTAssertEqual(liveModel.rows[0].cells.first, "69%") // Athletic Bilbao (home)
        XCTAssertEqual(liveModel.rows[1].cells.first, "12%") // Espanyol (away)
        XCTAssertEqual(liveModel.rows[2].cells.first, "19%") // Draw
        XCTAssertEqual(liveModel.away.pregameChanceText, "12%")
        XCTAssertEqual(liveModel.home.pregameChanceText, "69%")

        // 2. Drawless venue shape (`0.685 / nil / 0.115`, sum 0.80 < 0.985): must show BOTH 69% and 12% (never blank away).
        let drawlessVenue = try decodeEvent(prematchOddsJSON: """
        {
          "home_probability": 0.685,
          "away_probability": 0.115,
          "home_rendered_percent": 69,
          "away_rendered_percent": 12,
          "source": "kalshi"
        }
        """)
        let drawlessModel = EventSportHeadlines12472.resolve(
            event: drawlessVenue,
            awayFullName: "Espanyol",
            homeFullName: "Athletic Bilbao",
            liveStatusText: nil,
            hasScore: true,
            numberStreams: false
        )
        XCTAssertEqual(drawlessModel.home.pregameChanceText, "69%")
        XCTAssertEqual(drawlessModel.away.pregameChanceText, "12%")

        // 3. Complement-only soccer shape (`0.685 / nil / 0.315`, sum 1.0): 196-A MUST still withhold away.
        let complementOnly = try decodeEvent(prematchOddsJSON: """
        {
          "home_probability": 0.685,
          "away_probability": 0.315,
          "source": "books"
        }
        """)
        let complementModel = EventSportHeadlines12472.resolve(
            event: complementOnly,
            awayFullName: "Espanyol",
            homeFullName: "Athletic Bilbao",
            liveStatusText: nil,
            hasScore: true,
            numberStreams: false
        )
        XCTAssertEqual(complementModel.home.pregameChanceText, "69%")
        XCTAssertNil(complementModel.away.pregameChanceText)

        #if canImport(UIKit)
        let now = Date()
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let bg = scheme == .dark ? Color.black : Color(white: 0.96)
            let colors = TeamTextContrast.cardColors(
                awayHex: liveThreeWay.awayTeamData?.primaryColor,
                homeHex: liveThreeWay.homeTeamData?.primaryColor
            )
            let card1 = EventSportHeadlineCard12472(
                model: liveModel,
                colors: colors,
                ekgTracker: .empty,
                liveUpdateStatus: .awaitingUpdate,
                displayAsOf: now,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: nil,
                confirmedAt: nil,
                revealForecast: nil
            )
            let card2 = EventSportHeadlineCard12472(
                model: drawlessModel,
                colors: colors,
                ekgTracker: .empty,
                liveUpdateStatus: .awaitingUpdate,
                displayAsOf: now,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: nil,
                confirmedAt: nil,
                revealForecast: nil
            )

            let sheetView = VStack(alignment: .leading, spacing: 14) {
                Text("Live 3-way prematch (69% / 12% / 19%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                card1
                Text("Venue without draw_probability (69% / 12%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                card2
            }
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)

            let measureHost = hostForMeasurement(sheetView, at: .large)
            measureHost.overrideUserInterfaceStyle = uiStyle
            let measured = measureHost.sizeThatFits(in: CGSize(width: 390, height: CGFloat.greatestFiniteMagnitude))
            let renderH = max(380, ceil(measured.height) + 12)

            let host = hostForMeasurement(sheetView, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
            let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: renderH))
            window.frame = CGRect(x: 0, y: 0, width: 390, height: renderH)
            window.overrideUserInterfaceStyle = uiStyle
            host.view.frame = window.bounds
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()

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
            let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = lines.joined(separator: " ")

            XCTAssertTrue(joined.contains("Athletic Bilbao"), "Expected Athletic Bilbao (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("Espanyol"), "Expected Espanyol (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("69%"), "Expected 69% (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("12%"), "Expected 12% (\(scheme)): \(joined)")
            XCTAssertTrue(joined.contains("19%"), "Expected 19% draw (\(scheme)): \(joined)")
            XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)): \(lines)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13292"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let tag = scheme == .dark ? "dark" : "light"
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("13292-soccer-pregame-\(tag)-390.png"))
                }
            }
        }
        #endif
    }
}
