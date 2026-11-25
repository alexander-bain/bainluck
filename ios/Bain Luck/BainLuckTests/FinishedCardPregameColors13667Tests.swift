import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13667 — Finished game cards on league / Sports pages print team-coloured
/// short names beside each pregame projected score (`Pregame projection  Jazz 106 · Lakers 119`)
/// via `LivePregameSummaryRow214A1`, instead of bare grey `"Pregame projection 106–119"`.
@MainActor
final class FinishedCardPregameColors13667Tests: XCTestCase {

    private func finishedEvent(sport: String = "basketball_nba",
                               away: String = "Utah Jazz",
                               awayAbbr: String? = "UTA",
                               awayColor: String = "#753BBD",
                               home: String = "Los Angeles Lakers",
                               homeAbbr: String? = "LAL",
                               homeColor: String = "#FDB927",
                               awayScore: Int = 109,
                               homeScore: Int = 114,
                               projAway: Double = 106,
                               projHome: Double = 119,
                               period: String = "full_game") throws -> FeedEventData {
        let json = """
        {
          "id": 9136671,
          "sport": "\(sport)",
          "sport_name": "NBA",
          "home_team": "\(home)",
          "away_team": "\(away)",
          "home_team_data": {
            "team_id": 13,
            "name": "\(home)",
            "abbreviation": "\(homeAbbr ?? "HME")",
            "primary_color": "\(homeColor)",
            "record": "11-4"
          },
          "away_team_data": {
            "team_id": 26,
            "name": "\(away)",
            "abbreviation": "\(awayAbbr ?? "AWY")",
            "primary_color": "\(awayColor)",
            "record": "5-11"
          },
          "commence_time": "2026-11-23T02:30:00Z",
          "ended_at": "2026-11-23T05:00:00Z",
          "status": "completed",
          "home_score": \(homeScore),
          "away_score": \(awayScore),
          "final_score_period": "\(period)",
          "opening_odds": {
            "home_probability": 0.72,
            "away_probability": 0.28
          },
          "pregame_projection": {
            "projected_home_score": \(projHome),
            "projected_away_score": \(projAway),
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-11-23T01:00:00+00:00",
            "latest_captured_at": "2026-11-23T02:20:00+00:00",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-23T02:30:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 4,
            "unit": "\(sport.hasPrefix("soccer_") ? "goals" : "points")",
            "period": "\(period)"
          }
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    func testResolveFinishedIncludesTeamNamesScoresAndTeamInks() throws {
        let nba = try finishedEvent()
        let cmp = try XCTUnwrap(
            FinalForecastComparison11296.resolve(
                sport: nba.sport,
                status: nba.status,
                homeScore: nba.homeScore,
                awayScore: nba.awayScore,
                actualPeriod: .fullGame,
                projection: nba.pregameProjection
            )
        )
        let summary = LivePregameCardSummary213A.resolveFinished(comparison: cmp, event: nba)
        XCTAssertEqual(summary.leadWord, "Pregame projection")
        XCTAssertEqual(summary.bodyText, "Jazz 106 \u{00B7} Lakers 119")
        XCTAssertTrue(summary.segments.contains { $0.ink == .awayTeam && $0.text == "Jazz 106" })
        XCTAssertTrue(summary.segments.contains { $0.ink == .homeTeam && $0.text == "Lakers 119" })
        XCTAssertTrue(summary.segments.contains { $0.ink == .quietLead && $0.text == "Pregame projection" })

        let soccer = try finishedEvent(
            sport: "soccer_epl",
            away: "Arsenal",
            awayAbbr: "ARS",
            awayColor: "#EF0107",
            home: "Chelsea",
            homeAbbr: "CHE",
            homeColor: "#034694",
            awayScore: 2,
            homeScore: 1,
            projAway: 1.4,
            projHome: 1.8,
            period: "regulation"
        )
        let soccerCmp = try XCTUnwrap(
            FinalForecastComparison11296.resolve(
                sport: soccer.sport,
                status: soccer.status,
                homeScore: soccer.homeScore,
                awayScore: soccer.awayScore,
                actualPeriod: .regulation,
                projection: soccer.pregameProjection
            )
        )
        let soccerSummary = LivePregameCardSummary213A.resolveFinished(comparison: soccerCmp, event: soccer)
        XCTAssertEqual(soccerSummary.leadWord, "Pregame projection (90 min)")
        XCTAssertTrue(soccerSummary.segments.contains { $0.ink == .awayTeam && $0.text.contains("Arsenal") })
        XCTAssertTrue(soccerSummary.segments.contains { $0.ink == .homeTeam && $0.text.contains("Chelsea") })
    }

    func testHostedFinishedEventCardRendersTeamNamesAt390LightAndDarkWithoutTruncation() throws {
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13667_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let nba = try finishedEvent()
        let cmp = try XCTUnwrap(
            FinalForecastComparison11296.resolve(
                sport: nba.sport,
                status: nba.status,
                homeScore: nba.homeScore,
                awayScore: nba.awayScore,
                actualPeriod: .fullGame,
                projection: nba.pregameProjection
            )
        )

        // AFTER: actual finished EventCardView at Light & Dark 390pt.
        for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let suite = "test-13667-\(tag)-\(UUID().uuidString)"
            let defaults = UserDefaults(suiteName: suite)!
            defer { UserDefaults.standard.removePersistentDomain(forName: suite) }
            let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)

            let card = VStack(alignment: .leading, spacing: 10) {
                Text(scheme == .dark ? "Just Happened · Dark 390pt" : "Just Happened · Light 390pt")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                EventCardView(event: nba, reason: nil)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(scheme == .dark ? Color.black : DS.surface)
            .environmentObject(pinManager)
            .environmentObject(NavigationCoordinator())
            .environmentObject(AuthManager(restoreOnInit: false))
            .environment(\.colorScheme, scheme)

            let img = snapshot(card, scheme: scheme)
            let ocr = try ocrText(img)
            XCTAssertTrue(
                ocr.contains("Pregame projection") && ocr.contains("Jazz 106") && ocr.contains("Lakers 119"),
                "\(tag): expected team-named pregame projection line in \(ocr)"
            )
            XCTAssertFalse(ocr.contains("…"), "\(tag): truncated projection text in \(ocr)")

            if let outDir, !outDir.isEmpty, let data = img.pngData() {
                try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("after-13667-\(tag)-390.png"))
            }
        }

        // BEFORE capture (legacy bare grey CompactProjectedContextLine12616 inside the finished card frame)
        if let outDir, !outDir.isEmpty {
            let beforeCard = VStack(alignment: .leading, spacing: 10) {
                Text("Just Happened · Pre-fix bare grey line")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("NBA")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("Final")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Utah Jazz")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text("109")
                            .font(.subheadline.weight(.regular).monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Los Angeles Lakers")
                            .font(.subheadline.weight(.bold))
                        Spacer()
                        Text("114")
                            .font(.subheadline.weight(.bold).monospacedDigit())
                    }
                    CompactProjectedContextLine12616(
                        text: CompactGameCard12616.finalContextText(cmp),
                        spokenText: FinalForecastComparison11296.spokenText(
                            cmp, awayName: nba.awayTeam, homeName: nba.homeTeam),
                        accessibilityId: FinalForecastLine11296.accessibilityIdentifier
                    )
                }
                .padding(14)
                .background(DS.cardBg)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 1))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.surface)
            .environment(\.colorScheme, .light)

            let beforeImg = snapshot(beforeCard, scheme: .light)
            if let data = beforeImg.pngData() {
                try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("before-13667-light-390.png"))
            }
        }
    }

    private func snapshot<V: View>(_ view: V, scheme: ColorScheme) -> UIImage {
        let host = hostForMeasurement(view, at: .large)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 290)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.frame = bounds
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrText(_ image: UIImage) throws -> String {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }
}
