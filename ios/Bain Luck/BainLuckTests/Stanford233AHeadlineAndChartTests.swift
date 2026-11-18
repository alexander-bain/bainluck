import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 6 (#12938 / Ruling 233: A on iPhone) — UC Irvine at Stanford (`15350027`,
/// Stanford up 65–61 late) across both 233: A live states:
/// 1. Sportsbooks has left `Now` (`0.4%` / `99.6%` from Polymarket + Bain Luck Model,
///    while 2 current spread/total books still project `61` / `66`).
/// 2. Projected final is withheld (`in_play_projected_*` and `projected_*` nil once
///    no current line remains): no stale number, no `"Proj."` header, no empty
///    `"Proj."` column width, and no gap in the chart beyond the straight step.
@MainActor
final class Stanford233AHeadlineAndChartTests: XCTestCase {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(T.self, from: Data(json.utf8))
    }

    private func collectTexts(in view: UIView) -> [String] {
        var out: [String] = []
        if let label = view as? UILabel,
           let text = label.text,
           !text.isEmpty,
           !label.isHidden,
           label.alpha > 0.01 {
            out.append(text)
        }
        for sub in view.subviews {
            out.append(contentsOf: collectTexts(in: sub))
        }
        return out
    }

    private func makeStanfordEventJSON(includeCurrentProjection: Bool, atISO: String) -> String {
        let projFields: String = includeCurrentProjection
            ? """
              "spread": -4.6,
              "over_under": 127.0,
              "projected_home_score": 65.8,
              "projected_away_score": 61.2,
              "live_projection": {
                "projected_home_score": 65.8,
                "projected_away_score": 61.2,
                "kind": "in_play",
                "boundary": "commence_time",
                "boundary_at": "2026-11-18T03:00:00Z",
                "earliest_confirmed_at": "2026-11-18T05:13:09Z",
                "latest_captured_at": "2026-11-18T05:13:59Z",
                "source": "sportsbooks",
                "basis": "consensus_spread_total",
                "bookmaker_count": 2,
                "unit": "points",
                "period": "full_game"
              },
              """
            : """
              "spread": null,
              "over_under": null,
              "projected_home_score": null,
              "projected_away_score": null,
              """
        return """
        {
          "id": 15350027,
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "home_team": "Stanford Cardinal",
          "away_team": "UC Irvine Anteaters",
          "commence_time": "2026-11-18T03:00:00Z",
          "start_is_tbd": false,
          "status": "live",
          "home_score": 65,
          "away_score": 61,
          "home_team_data": {
            "team_id": 1179,
            "slug": "stanford-cardinal-ncaab",
            "primary_color": "#8C1515",
            "secondary_color": "#FFFFFF",
            "logo_small": "https://a.espncdn.com/i/teamlogos/ncaa/500/24.png",
            "abbreviation": "STAN"
          },
          "away_team_data": {
            "team_id": 1200,
            "slug": "uc-irvine-anteaters-ncaab",
            "primary_color": "#0C2340",
            "secondary_color": "#FFC72C",
            "logo_small": "https://a.espncdn.com/i/teamlogos/ncaa/500/300.png",
            "abbreviation": "UCI"
          },
          "espn": {
            "period": "2nd Half",
            "game_clock": "\(includeCurrentProjection ? "0:41" : "0:12")"
          },
          "current_odds": {
            "captured_at": "\(atISO)",
            "home_probability": 0.996,
            "away_probability": 0.004,
            "away_rendered_percent": 0,
            "home_rendered_percent": 100,
            \(projFields)
            "bookmaker_count": 2
          },
          "prematch_odds": {
            "home_probability": 0.73,
            "away_probability": 0.27,
            "home_rendered_percent": 73,
            "away_rendered_percent": 27,
            "source": "polymarket"
          },
          "pregame_projection": {
            "projected_home_score": 74.2,
            "projected_away_score": 67.8,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-11-17T21:06:42Z",
            "latest_captured_at": "2026-11-18T02:59:36Z",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-18T03:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 18,
            "unit": "points",
            "period": "full_game"
          },
          "hero_probability": 0.996,
          "hero_probability_away": 0.004,
          "hero_probability_source": "blend",
          "source_mark": {
            "state": "blend",
            "sources": [
              {"key": "polymarket", "name": "Polymarket", "probability": 0.9995, "observed_at": "2026-11-18T05:14:55Z"},
              {"key": "stat_model", "name": "Bain Luck Model", "probability": 0.9989, "observed_at": "2026-11-18T05:13:20Z"}
            ]
          }
        }
        """
    }

    func testStanford233AState1SportsbooksLeftNowAndState2ProjectedWithheld() throws {
        let iso = ISO8601DateFormatter()
        let nowState1 = try XCTUnwrap(iso.date(from: "2026-11-18T05:15:30Z"))
        let nowState2 = try XCTUnwrap(iso.date(from: "2026-11-18T05:17:30Z"))

        // State 1: Sportsbooks has left Now (99.6%), 2 current books project 61–66 (never frozen 65–68 or 93.2%)
        let event1 = try decode(EventDetail.self, makeStanfordEventJSON(includeCurrentProjection: true, atISO: "2026-11-18T05:13:59Z"))
        let model1 = EventSportHeadlines12472.resolve(
            event: event1,
            awayFullName: event1.awayTeam,
            homeFullName: event1.homeTeam,
            liveStatusText: "2nd Half · 0:41",
            hasScore: true,
            numberStreams: true,
            now: nowState1
        )
        XCTAssertEqual(model1.columns.map(\.header), ["Score", "Proj.", "Now"])
        XCTAssertEqual(model1.rows[0].cells, ["61", "61", "<1%"])
        XCTAssertEqual(model1.rows[1].cells, ["65", "66", ">99%"])
        XCTAssertEqual(model1.livePregameSummary?.fullText, "Pregame  Stanford 73% · projected 74\u{2013}68")

        let fit1 = HeadlineCellFit12822.resolve(
            model: model1,
            innerWidth: 330,
            crestSize: 30,
            isAccessibilitySize: false,
            nameFontSize: 16,
            nowFontSize: 24,
            secondProminentFontSize: 20,
            secondRegularFontSize: 16,
            headerFontSize: 11
        )
        XCTAssertEqual(fit1.columnWidths.count, 3)
        XCTAssertTrue(fit1.columnWidths.allSatisfy { $0 > 0 }, "All 3 columns active when current projection exists")

        // State 2: Projected final is withheld -> no 'Proj.' header, column width collapses to 0, no stale 65/68 or 66/70
        let event2 = try decode(EventDetail.self, makeStanfordEventJSON(includeCurrentProjection: false, atISO: "2026-11-18T05:17:00Z"))
        let model2 = EventSportHeadlines12472.resolve(
            event: event2,
            awayFullName: event2.awayTeam,
            homeFullName: event2.homeTeam,
            liveStatusText: "2nd Half · 0:12",
            hasScore: true,
            numberStreams: true,
            now: nowState2
        )
        XCTAssertEqual(model2.columns.map(\.header), ["Score", "", "Now"])
        XCTAssertEqual(model2.rows[0].cells, ["61", "", "<1%"])
        XCTAssertEqual(model2.rows[1].cells, ["65", "", ">99%"])

        let fit2 = HeadlineCellFit12822.resolve(
            model: model2,
            innerWidth: 330,
            crestSize: 30,
            isAccessibilitySize: false,
            nameFontSize: 16,
            nowFontSize: 24,
            secondProminentFontSize: 20,
            secondRegularFontSize: 16,
            headerFontSize: 11
        )
        XCTAssertEqual(fit2.columnWidths.count, 3)
        XCTAssertGreaterThan(fit2.columnWidths[0], 0, "Score column stays active")
        XCTAssertEqual(fit2.columnWidths[1], 0, "Withheld Proj. column must collapse to width 0 so no empty middle slot remains")
        XCTAssertGreaterThan(fit2.columnWidths[2], 0, "Now column stays active")
        XCTAssertEqual(fit2.extraLeadingGaps, [0, 0, 8])
        XCTAssertLessThan(fit2.totalColumnsWidth, fit1.totalColumnsWidth - 28, "Collapsing empty Proj. column reclaims horizontal width")

        // Mount State 2 headline at 390 pt and verify layout succeeds with zero stale numbers
        let card2 = EventSportHeadlineCard12472(
            model: model2,
            colors: (away: Color(hex: "#0C2340"), home: Color(hex: "#8C1515")),
            ekgTracker: EkgTracker(),
            liveUpdateStatus: .hidden,
            displayAsOf: nowState2,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .padding(.horizontal, 16)
        .frame(width: 390)

        let host = hostForMeasurement(card2, at: .large)
        let size = host.sizeThatFits(in: CGSize(width: 390, height: 600))
        XCTAssertGreaterThan(size.height, 100)
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: max(size.height, 180)))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        let renderedTexts = collectTexts(in: host.view)
        XCTAssertFalse(renderedTexts.contains("Proj."), "Withheld projection must not render 'Proj.' header")
        XCTAssertFalse(renderedTexts.contains("93.2%"), "No stale sportsbook-dragged 93.2%")
        XCTAssertFalse(renderedTexts.contains("68"), "No frozen 65–68 in-play projection")

        // Chart check: Stanford 233:A curve steps from 83.9% -> 90.6% -> 98.3% -> 99.6% in one connected run with zero gap
        let gameStart = try XCTUnwrap(iso.date(from: "2026-11-18T03:00:00Z"))
        let replayPoints: [(String, Double)] = [
            ("2026-11-18T03:00:00Z", 0.719),
            ("2026-11-18T03:30:00Z", 0.493),
            ("2026-11-18T03:49:00Z", 0.263),
            ("2026-11-18T04:30:00Z", 0.542),
            ("2026-11-18T05:05:00Z", 0.643),
            ("2026-11-18T05:10:00Z", 0.839),
            ("2026-11-18T05:12:00Z", 0.906),
            ("2026-11-18T05:13:00Z", 0.983),
            ("2026-11-18T05:15:00Z", 0.996),
            ("2026-11-18T05:17:00Z", 0.996),
        ]
        let chartDataPoints: [ChartDataPoint] = try replayPoints.map { ts, p in
            let d = try XCTUnwrap(iso.date(from: ts))
            return ChartDataPoint(date: d, probability: p, source: "aggregate")
        }
        let ink = OddsChartView.primaryInk9483(dataPoints: chartDataPoints, checkpoints: nil, gameStart: gameStart)
        XCTAssertEqual(ink.runs.count, 1, "Win-probability chart draws one single connected line with zero gap when Sportsbooks leaves Now")
        XCTAssertEqual(ink.runs[0].count, replayPoints.count)
        XCTAssertEqual(try XCTUnwrap(ink.runs[0].last?.probability), 0.996, accuracy: 0.0001)
    }

    // MARK: - 390 pt Light & Dark Render Export (Real Stanford Fixture 15350027)

    private func captureWindowSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        width: CGFloat = 390
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, scheme), at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let fitted = ceil(host.sizeThatFits(in: CGSize(width: width, height: 2_000)).height)
        let bounds = CGRect(x: 0, y: 0, width: width, height: max(fitted, 360))

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
        try await Task.sleep(nanoseconds: 900_000_000)
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            let bg = scheme == .light ? UIColor.systemGroupedBackground : UIColor.black
            bg.setFill()
            ctx.fill(bounds)
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    func testRenderStanford233ATwoStates390() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let outDir = env["RENDER_233A_DIR"], !outDir.isEmpty,
              let historyPath = env["RENDER_233A_HISTORY_JSON"], !historyPath.isEmpty else {
            return
        }
        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        let rawHistoryObj = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: historyPath))) as? [String: Any]
        )

        func buildLiveStanfordHistory(cutoffISO: String, endDomainISO: String) throws -> EventHistoryResponse {
            var obj = rawHistoryObj
            obj["status"] = "live"
            obj["completed_at"] = NSNull()
            obj["time_domain"] = [
                "start": "2026-11-18T03:00:00+00:00",
                "end": endDomainISO,
                "is_live": true,
                "min_window_seconds": 1800,
            ]
            // Apply Speed's #12972 233:A replay values from 05:10..cutoffISO onto the real Stanford aggregate_line:
            // 9:10 -> 83.9%, 9:12 -> 90.6%, 9:13 -> 98.3%, 9:15+ -> 99.6% (Sportsbooks has left Now), dropping terminal 05:19 Final.
            let replayOverrides: [String: Double] = [
                "2026-11-18T05:10:00+00:00": 0.839,
                "2026-11-18T05:11:00+00:00": 0.872,
                "2026-11-18T05:12:00+00:00": 0.906,
                "2026-11-18T05:13:00+00:00": 0.983,
                "2026-11-18T05:14:00+00:00": 0.989,
                "2026-11-18T05:15:00+00:00": 0.996,
                "2026-11-18T05:16:00+00:00": 0.996,
                "2026-11-18T05:17:00+00:00": 0.996,
            ]
            if let agg = obj["aggregate_line"] as? [[String: Any]] {
                var updated: [[String: Any]] = []
                for var pt in agg {
                    guard let ts = pt["timestamp"] as? String else { continue }
                    if ts >= "2026-11-18T03:00:00+00:00" && ts <= cutoffISO {
                        if let repl = replayOverrides[ts] {
                            pt["home_probability"] = repl
                        }
                        updated.append(pt)
                    }
                }
                obj["aggregate_line"] = updated
            }
            if let hist = obj["history"] as? [[String: Any]] {
                obj["history"] = hist.filter { ($0["timestamp"] as? String ?? "") <= cutoffISO }
            }
            if let espnHist = obj["espn_history"] as? [[String: Any]] {
                obj["espn_history"] = espnHist.filter { ($0["timestamp"] as? String ?? "") <= cutoffISO }
            }
            if let scoreHist = obj["score_history"] as? [[String: Any]] {
                obj["score_history"] = scoreHist.filter { ($0["timestamp"] as? String ?? "") <= cutoffISO }
            }
            if let wpHist = obj["win_prob_history"] as? [String: [[String: Any]]] {
                var filteredWP: [String: [[String: Any]]] = [:]
                for (k, arr) in wpHist {
                    filteredWP[k] = arr.filter { ($0["timestamp"] as? String ?? "") <= cutoffISO }
                }
                obj["win_prob_history"] = filteredWP
            }
            let data = try JSONSerialization.data(withJSONObject: obj)
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(EventHistoryResponse.self, from: data)
        }

        let iso = ISO8601DateFormatter()
        let nowState1 = try XCTUnwrap(iso.date(from: "2026-11-18T05:15:30Z"))
        let nowState2 = try XCTUnwrap(iso.date(from: "2026-11-18T05:17:30Z"))

        let event1 = try decode(EventDetail.self, makeStanfordEventJSON(includeCurrentProjection: true, atISO: "2026-11-18T05:13:59Z"))
        let history1 = try buildLiveStanfordHistory(cutoffISO: "2026-11-18T05:15:00+00:00", endDomainISO: "2026-11-18T05:20:00+00:00")

        let event2 = try decode(EventDetail.self, makeStanfordEventJSON(includeCurrentProjection: false, atISO: "2026-11-18T05:17:00Z"))
        let history2 = try buildLiveStanfordHistory(cutoffISO: "2026-11-18T05:17:00+00:00", endDomainISO: "2026-11-18T05:20:00+00:00")

        for (stateTag, event, history, nowDate, statusLabel) in [
            ("state1-sportsbooks-left-now", event1, history1, nowState1, "2nd Half · 0:41"),
            ("state2-projected-withheld", event2, history2, nowState2, "2nd Half · 0:12"),
        ] {
            let model = EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: statusLabel,
                hasScore: true,
                numberStreams: true,
                now: nowDate
            )
            for (schemeTag, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
                let awayHex: String
                let homeHex: String
                if scheme == .dark {
                    let pair = TeamTextContrast.darkSurfaceColorHexes(
                        awayHex: "#0C2340",
                        homeHex: "#8C1515",
                        awaySecondaryHex: "#FFC72C",
                        homeSecondaryHex: "#FFFFFF"
                    )
                    awayHex = pair.away
                    homeHex = pair.home
                } else {
                    let pair = TeamTextContrast.cardColorHexes(
                        awayHex: "#0C2340",
                        homeHex: "#8C1515",
                        awaySecondaryHex: "#FFC72C"
                    )
                    awayHex = pair.away
                    homeHex = pair.home
                }
                let colors = (away: Color(hex: awayHex), home: Color(hex: homeHex))
                let pageBg = scheme == .light ? Color(uiColor: .systemGroupedBackground) : Color(hex: "#0B0D12")

                let stackedPage = VStack(alignment: .leading, spacing: 12) {
                    EventSportHeadlineCard12472(
                        model: model,
                        colors: colors,
                        ekgTracker: EkgTracker(),
                        liveUpdateStatus: .hidden,
                        displayAsOf: nowDate,
                        updateStream: LiveUpdateStream(),
                        showUpdateStream: .constant(false),
                        showProbabilityDetails: .constant(false),
                        priceStreamingEligible: false,
                        lastReceivedAt: nil,
                        confirmedAt: nil,
                        revealForecast: nil
                    )

                    OddsChartView(
                        eventId: event.id,
                        teamColors: colors,
                        commenceTime: event.commenceTime,
                        status: "live",
                        homeTeamName: event.homeTeam,
                        awayTeamName: event.awayTeam,
                        homeTeamLogo: event.homeTeamData?.logoSmall,
                        awayTeamLogo: event.awayTeamData?.logoSmall,
                        homeTeamAbbrev: "STAN",
                        awayTeamAbbrev: "UCI",
                        sportKey: event.sport,
                        homeScore: event.homeScore,
                        awayScore: event.awayScore,
                        servedHomeProbability: 0.996,
                        servedAwayProbability: 0.004,
                        selectedRange: .constant(.sinceStart),
                        preloadedHistory: history,
                        preloadedHistoryGeneration: 1
                    )
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
                .padding(16)
                .frame(width: 390)
                .background(pageBg)

                let img = try await captureWindowSnapshot(stackedPage, scheme: scheme, width: 390)
                try XCTUnwrap(img.pngData()).write(
                    to: URL(fileURLWithPath: "\(outDir)/stanford-233a-\(stateTag)-\(schemeTag)-390.png")
                )
            }
        }
    }
}
