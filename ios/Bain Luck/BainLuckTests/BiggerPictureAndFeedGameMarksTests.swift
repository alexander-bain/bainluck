import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12967, #12864, #12932 — Verifies served `source_mark` decoding and rendering on:
///   1. Game page **Bigger Picture / Season Futures** (`#12967`: `RelatedFuture.sourceMark`
///      across `RelatedFuturesView` and `RelatedMarketsCatalogView`).
///   2. **Discover single-game cards** (`#12864`: `FeedEventData.sourceMark` / `awaySourceMark`
///      on `DiscoverCompactSingleGameCard190CView`, matching `EventCardView` on Sports / league feeds `#12932`).
@MainActor
final class BiggerPictureAndFeedGameMarksTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-18T23:10:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat? = nil,
        scheme: ColorScheme = .light,
        at size: DynamicTypeSize = .large
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let sizedContent: AnyView = {
            if let fixedHeight {
                return AnyView(
                    view
                        .frame(width: width, height: fixedHeight, alignment: .topLeading)
                        .background(bg)
                        .environment(\.colorScheme, scheme)
                )
            }
            return AnyView(
                view
                    .frame(width: width, alignment: .topLeading)
                    .fixedSize(horizontal: false, vertical: true)
                    .background(bg)
                    .environment(\.colorScheme, scheme)
            )
        }()

        let measureHost = hostForMeasurement(sizedContent, at: size)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = fixedHeight ?? min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, 160), 2_400)

        let hostedRoot: AnyView = {
            if fixedHeight != nil {
                return sizedContent
            }
            return AnyView(
                NavigationStack {
                    sizedContent
                        .toolbar(.hidden, for: .navigationBar)
                }
            )
        }()

        let host = hostForMeasurement(hostedRoot, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<3 {
            if fixedHeight == nil {
                let nextH = min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, fittingH), 2_400)
                if abs(nextH - window.frame.height) > 0.5 {
                    window.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                    host.view.frame = window.bounds
                }
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let topInset = fixedHeight == nil ? host.view.safeAreaInsets.top : 0
        let cropSize = CGSize(width: width, height: max(host.view.bounds.height - topInset, 140))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: cropSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -topInset, width: width, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func writeRenderIfEnabled(_ image: UIImage, name: String) throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-12967-12864", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }
        let data = try XCTUnwrap(image.pngData())
        try data.write(to: dir.appendingPathComponent("\(name).png"))
    }

    func testRelatedFuturesDecodesAndRendersServedSourceMarks() throws {
        let json = """
        {
          "event_id": 15350555,
          "home_team": "Orlando Magic",
          "away_team": "Philadelphia 76ers",
          "sport": "basketball_nba",
          "event_status": "scheduled",
          "home_team_futures": [
            {
              "market_id": 90101,
              "market_name": "NBA Most Valuable Player",
              "clean_label": "MVP",
              "display_category": "award",
              "category": "award",
              "source": "kalshi",
              "outcome_id": 501001,
              "outcome_name": "Paolo Banchero",
              "probability": 0.08,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.085, "observed_at": "2026-11-18T23:05:00Z" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.075, "observed_at": "2026-11-18T23:04:00Z" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "market_id": 90103,
              "market_name": "Orlando Magic Regular Season Wins Over 47.5",
              "clean_label": "Regular Season Wins Over 47.5",
              "display_category": "season_stat",
              "category": "win_total",
              "source": "kalshi",
              "outcome_id": 501003,
              "outcome_name": "Orlando Magic",
              "probability": 0.62,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.63, "observed_at": "2026-11-18T23:05:00Z" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.61, "observed_at": "2026-11-18T23:04:00Z" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "market_id": 65536503,
              "market_name": "NBA Cup East Group B Winner",
              "clean_label": "NBA Cup East Group B",
              "display_category": "playoff_path",
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 501005,
              "outcome_name": "Orlando Magic",
              "probability": 0.48,
              "source_mark": {
                "state": "single",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.48 }
                ]
              }
            }
          ],
          "away_team_futures": [
            {
              "market_id": 90102,
              "market_name": "NBA Most Improved Player",
              "clean_label": "Most Improved",
              "display_category": "award",
              "category": "award",
              "source": "kalshi",
              "outcome_id": 501002,
              "outcome_name": "Tyrese Maxey",
              "probability": 0.14,
              "source_mark": {
                "state": "single",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.14 }
                ]
              }
            },
            {
              "market_id": 90104,
              "market_name": "Philadelphia 76ers Regular Season Wins Over 44.5",
              "clean_label": "Regular Season Wins Over 44.5",
              "display_category": "season_stat",
              "category": "win_total",
              "source": "kalshi",
              "outcome_id": 501004,
              "outcome_name": "Philadelphia 76ers",
              "probability": 0.51,
              "source_mark": {
                "state": "single",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.51 }
                ]
              }
            }
          ]
        }
        """

        let response = try decodeSnake(RelatedFuturesResponse.self, json)
        let homeFirst = try XCTUnwrap(response.homeTeamFutures?.first)
        XCTAssertEqual(homeFirst.sourceMark?.state, .blend)
        XCTAssertEqual(homeFirst.sourceMark?.sources.map(\.name), ["Kalshi", "Polymarket"])

        let view = RelatedFuturesView(
            eventId: 15350555,
            awayTeamColor: Color(hex: "#006BB6"),
            homeTeamColor: Color(hex: "#0077C0"),
            awayTeam: "Philadelphia 76ers",
            homeTeam: "Orlando Magic",
            sportKey: "basketball_nba",
            preloadedData: response
        )
        .padding(16)

        let light = captureView(view, scheme: .light, at: .large)
        let dark = captureView(view, scheme: .dark, at: .large)
        let lines = try ocrLines(light)
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("62%") && joined.contains("14%"), "RelatedFuturesView must render 62% and 14%: \(lines)")
        XCTAssertFalse(joined.contains("Kalshi") || joined.contains("Polymarket"), "Card face must never print venue names: \(lines)")
        XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "RelatedFuturesView must not truncate: \(lines)")

        let catalogRows = RelatedMarketsCatalog.rows(
            home: response.homeTeamFutures ?? [],
            away: response.awayTeamFutures ?? []
        )
        let catalogView = RelatedMarketsCatalogView(rows: catalogRows, initiallyOpen: true)
            .padding(16)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
            .padding(16)
        let catLight = captureView(catalogView, scheme: .light, at: .large)
        let catLines = try ocrLines(catLight)
        XCTAssertTrue(catLines.joined(separator: " ").contains("48%"), "Expanded catalog must render 48%: \(catLines)")

        try writeRenderIfEnabled(light, name: "fixture-12967-bigger-picture-light-390")
        try writeRenderIfEnabled(dark, name: "fixture-12967-bigger-picture-dark-390")
    }

    func testDiscoverSingleGameCardRendersServedHeadlineSourceMark() throws {
        let json = """
        {
          "id": 15350559,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "scheduled",
          "commence_time": "2099-11-19T00:30:00Z",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "away_team_data": { "abbreviation": "CHI", "primary_color": "#CE1141" },
          "home_team_data": { "abbreviation": "BKN", "primary_color": "#000000" },
          "current_odds": {
            "away_probability": 0.44,
            "home_probability": 0.56,
            "away_rendered_percent": 44,
            "home_rendered_percent": 56,
            "projected_away_score": 119.1,
            "projected_home_score": 120.8
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "sportsbooks", "name": "Sportsbooks", "count": 12, "probability": 0.562, "observed_at": "2026-11-18T23:06:00Z" },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.555, "observed_at": "2026-11-18T23:05:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.555, "observed_at": "2026-11-18T23:05:00Z" }
            ],
            "method": "Bain Luck blend · weighted average before rounding"
          }
        }
        """

        let event = try decodeSnake(FeedEventData.self, json)
        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: event,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(resolved.subject, "Nets")
        XCTAssertFalse(resolved.isPregame)

        let card = DiscoverCompactSingleGameCard190CView(
            event: event,
            prematch: nil,
            awayColor: Color(hex: "#CE1141"),
            homeColor: Color.primary
        ) {
            EmptyView()
        } footerRow: {
            EmptyView()
        }
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
        .padding(16)

        let light = captureView(card, scheme: .light, at: .large)
        let dark = captureView(card, scheme: .dark, at: .large)
        let lines = try ocrLines(light)
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("Bulls") && joined.contains("Nets"), "Discover game card must read Bulls and Nets: \(lines)")
        XCTAssertFalse(lines.contains(where: { $0.contains("…") }), "Discover game card must not truncate: \(lines)")

        try writeRenderIfEnabled(light, name: "fixture-12864-discover-game-light-390")
        try writeRenderIfEnabled(dark, name: "fixture-12864-discover-game-dark-390")
    }

    func testRenderLivePayloadsWhenStaged() throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-12967-12864", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let relatedPath = dir.appendingPathComponent("live-related-futures.json")
        if FileManager.default.fileExists(atPath: relatedPath.path) {
            let data = try Data(contentsOf: relatedPath)
            let response = try decoder.decode(RelatedFuturesResponse.self, from: data)
            let awayTeam = response.awayTeam ?? "Away"
            let homeTeam = response.homeTeam ?? "Home"
            let view = RelatedFuturesView(
                eventId: response.eventId,
                awayTeamColor: Color(hex: "#006BB6"),
                homeTeamColor: Color(hex: "#0077C0"),
                awayTeam: awayTeam,
                homeTeam: homeTeam,
                sportKey: "basketball_nba",
                preloadedData: response
            )
            .padding(16)
            try writeRenderIfEnabled(captureView(view, scheme: .light, at: .large), name: "12967-bigger-picture-light-390")
            try writeRenderIfEnabled(captureView(view, scheme: .dark, at: .large), name: "12967-bigger-picture-dark-390")

            let allRows = (response.awayTeamFutures ?? []) + (response.homeTeamFutures ?? [])
            if let marked = allRows.first(where: { $0.sourceMark?.state == .blend })
                ?? allRows.first(where: { $0.sourceMark?.draws == true }),
               let mark = marked.sourceMark {
                let sheet = SourceMarkSheet(
                    mark: mark,
                    number: mark.state == .settled ? nil : marked.probability,
                    subject: marked.outcomeName,
                    now: fixedNow
                )
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 460, scheme: .light, at: .large), name: "12967-bigger-picture-sheet-light-390")
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 460, scheme: .dark, at: .large), name: "12967-bigger-picture-sheet-dark-390")
            }

            let catalogRows = Array(RelatedMarketsCatalog.rows(
                home: response.homeTeamFutures ?? [],
                away: response.awayTeamFutures ?? []
            ).prefix(6))
            if !catalogRows.isEmpty {
                let catalogView = RelatedMarketsCatalogView(rows: catalogRows, initiallyOpen: true)
                    .padding(16)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                    .padding(16)
                try writeRenderIfEnabled(captureView(catalogView, scheme: .light, at: .large), name: "12967-bigger-picture-catalog-light-390")
                try writeRenderIfEnabled(captureView(catalogView, scheme: .dark, at: .large), name: "12967-bigger-picture-catalog-dark-390")
            }
        }

        let feedEventPath = dir.appendingPathComponent("live-feed-event.json")
        if FileManager.default.fileExists(atPath: feedEventPath.path) {
            let data = try Data(contentsOf: feedEventPath)
            let event = try decoder.decode(FeedEventData.self, from: data)
            let historyPath = dir.appendingPathComponent("live-feed-history.json")
            let history: EventHistoryResponse? = {
                guard FileManager.default.fileExists(atPath: historyPath.path),
                      let hData = try? Data(contentsOf: historyPath) else { return nil }
                return try? decoder.decode(EventHistoryResponse.self, from: hData)
            }()
            let card = NativeEventDiscoverCard(
                event: event,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: history
            )
            .environmentObject(PinManager())
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .padding(16)
            try writeRenderIfEnabled(captureView(card, scheme: .light, at: .large), name: "12864-discover-game-light-390")
            try writeRenderIfEnabled(captureView(card, scheme: .dark, at: .large), name: "12864-discover-game-dark-390")

            let pricesDraw = DrawPricedWinner.sportPricesADraw(event.sport)
            if let resolved = EventCardView.resolvedCardSourceMark(
                event: event,
                canStillBeGraded: event.status != "completed" && event.status != "closed",
                currentAwayIsWithheld: pricesDraw && !CompactGameCard12616.hasExplicitThreeWayCurrent(event),
                prematch: nil,
                prematchAwayIsWithheld: pricesDraw && !CompactGameCard12616.hasExplicitThreeWayPrematch(event)
            ) {
                let sheet = SourceMarkSheet(
                    mark: resolved.mark,
                    number: resolved.number,
                    subject: resolved.subject,
                    isPregame: resolved.isPregame,
                    now: fixedNow
                )
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 480, scheme: .light, at: .large), name: "12864-discover-game-sheet-light-390")
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 480, scheme: .dark, at: .large), name: "12864-discover-game-sheet-dark-390")
            }
        }
    }
}
