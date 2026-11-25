import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Follow-up from Fable's #13002 ACCEPT: where a live game card or live headline
/// prints tenths ("96.0%"), its "Where this number comes from" sheet (`SourceMarkSheet`)
/// prints tenths too — resolved once across Sports, Search, Team, Hub (`EventCardView`),
/// Discover (`DiscoverCompactSingleGameCard190CView`), and the Event Detail headline
/// (`EventSportHeadlineCard12472`).
@MainActor
final class LiveCardSourceMarkSheetTenthsTests: XCTestCase {

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

    func testLiveGameCardSheetPrintsTenthsMatchingNowCell() throws {
        let json = """
        {
          "id": 99501,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "away_score": 88,
          "home_score": 106,
          "espn": {
            "period": "Q4",
            "game_clock": "4:12"
          },
          "current_odds": {
            "away_probability": 0.04,
            "home_probability": 0.9602,
            "away_rendered_percent": 4,
            "home_rendered_percent": 96
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "sportsbooks", "name": "Sportsbooks", "count": 11, "probability": 0.962, "observed_at": "2026-11-18T23:09:40Z" },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.958, "observed_at": "2026-11-18T23:09:45Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.959, "observed_at": "2026-11-18T23:09:42Z" }
            ],
            "method": "Bain Luck blend · weighted average before rounding"
          }
        }
        """

        let event = try decodeSnake(FeedEventData.self, json)
        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: event,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false,
                showsLiveTenths: true
            )
        )
        XCTAssertTrue(resolved.showsTenths, "Live card printing 96.0% in Now must open its sheet in tenths")
        XCTAssertEqual(resolved.subject, "Nets")
        XCTAssertFalse(resolved.isPregame)
        XCTAssertEqual(
            SourceMarkSheet.headline(resolved.number, showsTenths: resolved.showsTenths),
            "96.0%"
        )
        let prices = SourceMarkSheet.lines(
            resolved.mark,
            showsTenths: resolved.showsTenths,
            now: fixedNow
        ).compactMap(\.price)
        XCTAssertEqual(prices, ["96.2%", "95.8%", "95.9%"])
    }

    func testScheduledFinishedAndBoundaryLiveCardsKeepWholeOrMarkerPrecision() throws {
        // 1. Scheduled card prints whole percent ("96%"), so sheet prints "96%".
        let scheduled = try decodeSnake(FeedEventData.self, """
        {
          "id": 99502,
          "sport": "basketball_nba",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "commence_time": "2026-11-19T00:30:00Z",
          "status": "scheduled",
          "current_odds": { "away_probability": 0.04, "home_probability": 0.9602 },
          "source_mark": {
            "state": "blend",
            "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.9602, "observed_at": null }]
          }
        }
        """)
        let schedResolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: scheduled,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertFalse(schedResolved.showsTenths)
        XCTAssertEqual(SourceMarkSheet.headline(schedResolved.number, showsTenths: schedResolved.showsTenths), "96%")

        // 2. Live card above 99% prints ">99%" (no decimal point), so sheet matches ">99%".
        let nearCertainLive = try decodeSnake(FeedEventData.self, """
        {
          "id": 99503,
          "sport": "basketball_nba",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "away_score": 80,
          "home_score": 118,
          "current_odds": { "away_probability": 0.006, "home_probability": 0.994 },
          "source_mark": {
            "state": "blend",
            "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.994, "observed_at": null }]
          }
        }
        """)
        let nearResolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: nearCertainLive,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertFalse(nearResolved.showsTenths)
        XCTAssertEqual(SourceMarkSheet.headline(nearResolved.number, showsTenths: nearResolved.showsTenths), ">99%")

        // 3. Overround live pair [0.624, 0.377] prints "62.3%" on the card after complement normalisation; sheet headline matches "62.3%".
        let overroundLive = try decodeSnake(FeedEventData.self, """
        {
          "id": 99504,
          "sport": "basketball_nba",
          "away_team": "Boston Celtics",
          "home_team": "Miami Heat",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "away_score": 54,
          "home_score": 49,
          "current_odds": { "away_probability": 0.624, "home_probability": 0.377 },
          "away_source_mark": {
            "state": "blend",
            "sources": [
              { "key": "sportsbooks", "name": "Sportsbooks", "count": 8, "probability": 0.624, "observed_at": null },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.621, "observed_at": null }
            ]
          }
        }
        """)
        let overroundResolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: overroundLive,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false,
                showsLiveTenths: true
            )
        )
        XCTAssertTrue(overroundResolved.showsTenths)
        XCTAssertEqual(overroundResolved.subject, "Celtics")
        XCTAssertEqual(
            SourceMarkSheet.headline(overroundResolved.number, showsTenths: overroundResolved.showsTenths),
            "62.3%"
        )
    }

    func testEventHeadlineCardSheetMatchesLiveAndStreamingTenths() throws {
        let liveDetail = try decodeSnake(EventDetail.self, """
        {
          "id": 99505,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "away_score": 88,
          "home_score": 106,
          "current_odds": { "away_probability": 0.04, "home_probability": 0.9602 },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "sportsbooks", "name": "Sportsbooks", "count": 11, "probability": 0.962, "observed_at": "2026-11-18T23:09:40Z" },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.958, "observed_at": "2026-11-18T23:09:45Z" }
            ]
          }
        }
        """)
        let liveModel = EventSportHeadlines12472.resolve(
            event: liveDetail,
            awayFullName: "Chicago Bulls",
            homeFullName: "Brooklyn Nets",
            liveStatusText: "Q4 4:12",
            hasScore: true,
            numberStreams: true,
            now: fixedNow
        )
        let liveResolved = try XCTUnwrap(EventSportHeadlineCard12472.resolvedHeadlineSourceMark(model: liveModel))
        XCTAssertTrue(liveResolved.showsTenths)
        XCTAssertEqual(
            SourceMarkSheet.headline(liveResolved.number, showsTenths: liveResolved.showsTenths),
            "96.0%"
        )
    }

    func testRenderLiveCardAndSheetLooksAt390() throws {
        let json = """
        {
          "id": 99510,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Chicago Bulls",
          "home_team": "Brooklyn Nets",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "away_score": 88,
          "home_score": 106,
          "espn": {
            "period": "Q4",
            "game_clock": "4:12"
          },
          "current_odds": {
            "away_probability": 0.04,
            "home_probability": 0.9602,
            "away_rendered_percent": 4,
            "home_rendered_percent": 96,
            "projected_away_score": 97.4,
            "projected_home_score": 114.2
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "sportsbooks", "name": "Sportsbooks", "count": 11, "probability": 0.962, "observed_at": "2026-11-18T23:09:40Z" },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.958, "observed_at": "2026-11-18T23:09:45Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.959, "observed_at": "2026-11-18T23:09:42Z" }
            ],
            "method": "Bain Luck blend · weighted average before rounding"
          }
        }
        """
        let event = try decodeSnake(FeedEventData.self, json)
        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMarkPresentation(
                event: event,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: nil,
                prematchAwayIsWithheld: false,
                showsLiveTenths: true
            )
        )

        let suiteName = "Render13002Tenths.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let sportsCard = EventCardView(event: event, reason: nil)
            .environment(\.liveOddsRefreshActive, true)
            .environmentObject(pinManager)
            .padding(16)
        let discoverCard = DiscoverCompactSingleGameCard190CView(
            event: event,
            prematch: nil,
            awayColor: Color(hex: "#CE1141"),
            homeColor: Color.primary
        ) {
            EmptyView()
        } footerRow: {
            EmptyView()
        }
        .environment(\.liveOddsRefreshActive, true)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
        .padding(16)

        let sheet = SourceMarkSheet(
            mark: resolved.mark,
            number: resolved.number,
            subject: resolved.subject,
            isPregame: resolved.isPregame,
            showsTenths: resolved.showsTenths,
            now: fixedNow
        )

        let sheetLight = captureView(sheet, fixedHeight: 460, scheme: .light, at: .large)
        let sheetLines = try ocrLines(sheetLight)
        let joinedSheet = sheetLines.joined(separator: " ")
        XCTAssertTrue(joinedSheet.contains("96.0%"), "Sheet must print 96.0%: \(sheetLines)")
        XCTAssertTrue(joinedSheet.contains("96.2%") && joinedSheet.contains("95.8%"), "Sheet venues must print tenths: \(sheetLines)")

        let outDir = URL(fileURLWithPath: "/tmp/renders-13002-live-sheet-tenths", isDirectory: true)
        guard FileManager.default.fileExists(atPath: outDir.path) else { return }

        for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            for (dtSize, sizeTag) in [(DynamicTypeSize.large, "default"), (DynamicTypeSize.xxxLarge, "larger")] {
                let sImg = captureView(sportsCard, scheme: scheme, at: dtSize)
                let dImg = captureView(discoverCard, scheme: scheme, at: dtSize)
                let shImg = captureView(sheet, fixedHeight: dtSize == .xxxLarge ? 560 : 460, scheme: scheme, at: dtSize)
                try XCTUnwrap(sImg.pngData()).write(to: outDir.appendingPathComponent("sports-live-card-\(sizeTag)-\(tag)-390.png"))
                try XCTUnwrap(dImg.pngData()).write(to: outDir.appendingPathComponent("discover-live-card-\(sizeTag)-\(tag)-390.png"))
                try XCTUnwrap(shImg.pngData()).write(to: outDir.appendingPathComponent("live-card-sheet-\(sizeTag)-\(tag)-390.png"))
            }
        }
    }
}
