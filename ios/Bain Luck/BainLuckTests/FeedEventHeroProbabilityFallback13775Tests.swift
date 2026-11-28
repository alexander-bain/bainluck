import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13775 — Upcoming prediction-market-only Celtics games on Discover arrive on
/// `/api/feed` with `current_odds: null` while `hero_probability` /
/// `hero_probability_away` carry the blended probability (`hero_probability_source: "blend"`).
/// `FeedEventData` decodes both hero fields and `CompactGameCard12616.currentOddsForCard`
/// falls back to them while keeping `#12824` opening withholding and `#5363` away withholding.
@MainActor
final class FeedEventHeroProbabilityFallback13775Tests: XCTestCase {

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    /// Exact live `/api/feed` shape served for Hawks @ Celtics (`15352061`, Fri Nov 27):
    /// `current_odds` absent/null, `hero_probability: 0.7275`, `hero_probability_away: 0.2725`,
    /// `hero_probability_source: "blend"`.
    private static let hawksAtCelticsJSON = """
    {
      "id": 15352061,
      "sport": "basketball_nba",
      "sport_name": "NBA",
      "home_team": "Boston Celtics",
      "away_team": "Atlanta Hawks",
      "commence_time": "2026-11-28T01:00:00+00:00",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 100,
        "slug": "boston-celtics",
        "primary_color": "#008348",
        "secondary_color": "#ffffff",
        "record": "12-6",
        "abbreviation": "BOS"
      },
      "away_team_data": {
        "team_id": 43,
        "slug": "atlanta-hawks",
        "primary_color": "#c8102e",
        "secondary_color": "#fdb927",
        "record": "11-6",
        "abbreviation": "ATL"
      },
      "hero_probability": 0.7275,
      "hero_probability_away": 0.2725,
      "hero_probability_source": "blend",
      "hero_probability_observed_at": "2026-11-26T04:28:03.638801+00:00",
      "source_mark": {
        "state": "blend",
        "sources": [
          { "key": "kalshi", "name": "Kalshi", "probability": 0.73 },
          { "key": "polymarket", "name": "Polymarket", "probability": 0.725 }
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    private static let celticsAtSpursJSON = """
    {
      "id": 15353081,
      "sport": "basketball_nba",
      "sport_name": "NBA",
      "home_team": "San Antonio Spurs",
      "away_team": "Boston Celtics",
      "commence_time": "2026-11-29T21:00:00+00:00",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 38,
        "slug": "san-antonio-spurs",
        "primary_color": "#111827",
        "secondary_color": "#9ca3af",
        "record": "15-3",
        "abbreviation": "SA"
      },
      "away_team_data": {
        "team_id": 100,
        "slug": "boston-celtics",
        "primary_color": "#008348",
        "secondary_color": "#ffffff",
        "record": "12-6",
        "abbreviation": "BOS"
      },
      "hero_probability": 0.385,
      "hero_probability_away": 0.615,
      "hero_probability_source": "blend",
      "hero_probability_observed_at": "2026-11-26T04:28:05+00:00"
    }
    """

    private static let celticsAtMavsJSON = """
    {
      "id": 15353610,
      "sport": "basketball_nba",
      "sport_name": "NBA",
      "home_team": "Dallas Mavericks",
      "away_team": "Boston Celtics",
      "commence_time": "2026-12-01T01:00:00+00:00",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 37,
        "slug": "dallas-mavericks",
        "primary_color": "#0064b1",
        "secondary_color": "#bbc4ca",
        "record": "11-7",
        "abbreviation": "DAL"
      },
      "away_team_data": {
        "team_id": 100,
        "slug": "boston-celtics",
        "primary_color": "#008348",
        "secondary_color": "#ffffff",
        "record": "12-6",
        "abbreviation": "BOS"
      },
      "hero_probability": 0.355,
      "hero_probability_away": 0.645,
      "hero_probability_source": "blend",
      "hero_probability_observed_at": "2026-11-26T04:28:08.294739+00:00"
    }
    """

    // MARK: - Unit assertions

    func testHawksAtCelticsDecodesHeroProbabilityAndRendersChanceColumnWhenCurrentOddsIsNil() throws {
        let event = try decodeFeedEvent(Self.hawksAtCelticsJSON)
        XCTAssertNil(event.currentOdds)
        XCTAssertEqual(try XCTUnwrap(event.heroProbability), 0.7275, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(event.heroProbabilityAway), 0.2725, accuracy: 0.0001)

        let resolved = try XCTUnwrap(CompactGameCard12616.currentOddsForCard(event))
        XCTAssertEqual(try XCTUnwrap(resolved.homeProbability), 0.7275, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(resolved.awayProbability), 0.2725, accuracy: 0.0001)

        let model = DiscoverSingleGameCard190C.build(event: event, prematch: nil)
        XCTAssertEqual(model.headers.primary, "Chance")
        XCTAssertEqual(model.rows.count, 2)
        XCTAssertEqual(model.rows[0].primaryCell, .probability("27%"))
        XCTAssertEqual(model.rows[1].primaryCell, .probability("73%"))
        XCTAssertNotNil(model.bar)
    }

    func testOpeningSourceStillWithholdsProbabilityEvenWithHeroProbabilityPresent12824() throws {
        let openingJSON = """
        {
          "id": 9137752,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Boston Celtics",
          "away_team": "Atlanta Hawks",
          "commence_time": "2026-11-28T01:00:00+00:00",
          "status": "scheduled",
          "current_odds": {
            "home_probability": 0.72,
            "away_probability": 0.28,
            "projected_home_score": 115.0,
            "projected_away_score": 108.0
          },
          "hero_probability": 0.72,
          "hero_probability_away": 0.28,
          "hero_probability_source": "opening"
        }
        """
        let event = try decodeFeedEvent(openingJSON)
        let resolved = CompactGameCard12616.currentOddsForCard(event)
        XCTAssertNil(resolved?.homeProbability)
        XCTAssertNil(resolved?.awayProbability)
        XCTAssertEqual(resolved?.projectedHomeScore, 115.0)

        let model = DiscoverSingleGameCard190C.build(event: event, prematch: nil)
        XCTAssertNil(model.headers.primary)
    }

    func testDrawPricedSportWithNilCurrentOddsNeverInventsOneMinusHome5363() throws {
        let soccerJSON = """
        {
          "id": 9137753,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "commence_time": "2026-11-29T16:30:00+00:00",
          "status": "scheduled",
          "hero_probability": 0.45,
          "hero_probability_source": "blend"
        }
        """
        let event = try decodeFeedEvent(soccerJSON)
        let resolved = try XCTUnwrap(CompactGameCard12616.currentOddsForCard(event))
        XCTAssertEqual(try XCTUnwrap(resolved.homeProbability), 0.45, accuracy: 0.0001)
        XCTAssertNil(resolved.awayProbability, "Draw-priced sport without explicit away probability must never invent 1 - home")

        let model = DiscoverSingleGameCard190C.build(event: event, prematch: nil)
        XCTAssertEqual(model.headers.primary, "Chance")
        XCTAssertEqual(model.rows[0].primaryCell, .settledDash)
        XCTAssertEqual(model.rows[1].primaryCell, .probability("45%"))
    }

    func testSettledAndCompletedEventsDoNotSynthesizeLiveChance() throws {
        let settledJSON = """
        {
          "id": 9137754,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Boston Celtics",
          "away_team": "Atlanta Hawks",
          "commence_time": "2026-11-24T01:00:00+00:00",
          "status": "completed",
          "home_score": 114,
          "away_score": 103,
          "hero_probability": 1.0,
          "hero_probability_away": 0.0,
          "hero_probability_source": "settled"
        }
        """
        let event = try decodeFeedEvent(settledJSON)
        XCTAssertNil(CompactGameCard12616.currentOddsForCard(event))
    }

    // MARK: - Rendered iPad-width & iPhone-width proof capture + OCR

    private func recognizeText(in image: UIImage) throws -> String {
        guard let cg = image.cgImage else { return "" }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([request])
        let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        return lines.joined(separator: "\n")
    }

    private func renderCards(_ events: [FeedEventData], width: CGFloat, scheme: ColorScheme) -> UIImage {
        let suiteName = "test.13775.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        let followMgr = FollowManager295A(defaults: defaults, initialSubjects: [
            FollowedSubject295A.team(slug: "boston-celtics", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba"),
            FollowedSubject295A.team(slug: "san-antonio-spurs", teamId: 38, name: "San Antonio Spurs", sportKey: "basketball_nba"),
        ])
        let stack = VStack(alignment: .leading, spacing: 12) {
            ForEach(events) { ev in
                NativeEventDiscoverCard(
                    event: ev,
                    feedContext: nil,
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
        }
        .padding(14)
        .frame(width: width)
        .background(scheme == .dark ? Color.black : Color(uiColor: .systemGroupedBackground))
        .environment(\.colorScheme, scheme)
        .environment(\.dynamicTypeSize, .large)
        .environmentObject(PinManager())
        .environment(\.followManager295A, followMgr)

        let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let host = hostForMeasurement(stack, at: .large)
        host.overrideUserInterfaceStyle = uiStyle
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 10)
        let target = host.sizeThatFits(in: CGSize(width: width, height: UIView.layoutFittingExpandedSize.height))
        let bounds = CGRect(origin: .zero, size: CGSize(width: width, height: ceil(target.height)))
        host.view.frame = bounds

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: bounds)
        }
        window.frame = bounds
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

    func testRenderedCelticsDiscoverCardsPrintProbabilitiesAtIPadAndIPhoneWidths() throws {
        let fixedEvents = [
            try decodeFeedEvent(Self.hawksAtCelticsJSON),
            try decodeFeedEvent(Self.celticsAtSpursJSON),
            try decodeFeedEvent(Self.celticsAtMavsJSON),
        ]
        // Simulate pre-fix payload where FeedEventData lacked heroProbability / heroProbabilityAway.
        let beforeEvents: [FeedEventData] = fixedEvents.map { ev in
            var copy = ev
            copy.heroProbability = nil
            copy.heroProbabilityAway = nil
            return copy
        }

        let beforeIPad = renderCards(beforeEvents, width: 410, scheme: .light)
        let afterIPadLight = renderCards(fixedEvents, width: 410, scheme: .light)
        let afterIPadDark = renderCards(fixedEvents, width: 410, scheme: .dark)
        let afterIPhone = renderCards(fixedEvents, width: 390, scheme: .light)

        let beforeOCR = try recognizeText(in: beforeIPad)
        XCTAssertFalse(beforeOCR.localizedCaseInsensitiveContains("Chance"), "Before fix must lack Chance header: \(beforeOCR)")

        let afterOCR = try recognizeText(in: afterIPadLight)
        XCTAssertTrue(afterOCR.localizedCaseInsensitiveContains("Chance"), "Expected Chance column after fix: \(afterOCR)")
        XCTAssertTrue(afterOCR.contains("27%"), "Expected Hawks 27%: \(afterOCR)")
        XCTAssertTrue(afterOCR.contains("73%"), "Expected Celtics 73%: \(afterOCR)")
        XCTAssertTrue(afterOCR.contains("62%"), "Expected Celtics 62% vs Spurs: \(afterOCR)")
        XCTAssertTrue(afterOCR.contains("65%"), "Expected Celtics 65% vs Mavericks: \(afterOCR)")

        let colW: CGFloat = 410
        let gap: CGFloat = 18
        let pad: CGFloat = 20
        let labelH: CGFloat = 24
        let sheetW = pad * 2 + colW * 2 + gap
        let topH = max(beforeIPad.size.height, afterIPadLight.size.height)
        let botH = max(afterIPadDark.size.height, afterIPhone.size.height)
        let sheetH = pad + labelH + topH + gap + labelH + botH + pad

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let sheet = UIGraphicsImageRenderer(size: CGSize(width: sheetW, height: sheetH), format: fmt).image { ctx in
            UIColor.systemBackground.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: sheetW, height: sheetH))
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 13, weight: .semibold),
                .foregroundColor: UIColor.secondaryLabel,
            ]
            func drawPanel(_ title: String, _ img: UIImage, x: CGFloat, y: CGFloat) {
                (title as NSString).draw(at: CGPoint(x: x, y: y), withAttributes: attrs)
                img.draw(in: CGRect(x: x, y: y + labelH, width: img.size.width, height: img.size.height))
            }
            drawPanel("Before (#13775, hero_probability ignored) · iPad col (410pt)", beforeIPad, x: pad, y: pad)
            drawPanel("After (hero_probability fallback) · iPad col (410pt Light)", afterIPadLight, x: pad + colW + gap, y: pad)
            let row2Y = pad + labelH + topH + gap
            drawPanel("After · iPad col (410pt Dark)", afterIPadDark, x: pad, y: row2Y)
            drawPanel("After · iPhone (390pt Light)", afterIPhone, x: pad + colW + gap, y: row2Y)
        }
        let outURL = FileManager.default.temporaryDirectory.appendingPathComponent("sheet-13775-celtics-probabilities.jpg")
        if let jpg = sheet.jpegData(compressionQuality: 0.9) {
            try jpg.write(to: outURL)
            print("SHEET_13775=\(outURL.path)")
        }
    }
}
