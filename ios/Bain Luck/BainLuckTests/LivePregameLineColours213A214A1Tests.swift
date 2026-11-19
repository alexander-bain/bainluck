import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Rulings 213-A & 214-A1 (Mon Nov 16, 2026):
/// - **213-A** (replaces 204-C): During a live game, phone cards (Discover, feed, search)
///   carry the page's one pregame line under the probability bar (`Score · Proj. · Now`,
///   bar and pregame tick, then `"Pregame  Lions 58% · projected 27–24"`).
/// - **214-A1**: On both the phone page and the Discover, feed, and search cards, each
///   number in the pregame line prints in its team's colour (`"Lions 58%"` and `27` in
///   the Lions' colour, `24` in the other team's colour), with the named team's number
///   always first, following Ruling 197 (same-colour-family secondary switch and
///   `#64748B` slate-grey fallback).
@MainActor
final class LivePregameLineColours213A214A1Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-16T20:55:00Z")!

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(type, from: Data(json.utf8))
    }

    // MARK: - Fixture Factory

    private func makeLiveGameJSON(
        id: Int,
        sport: String,
        sportName: String,
        awayTeam: String,
        homeTeam: String,
        awayAbbr: String,
        homeAbbr: String,
        awayPrimary: String,
        awaySecondary: String?,
        homePrimary: String,
        homeSecondary: String?,
        awayScore: Int,
        homeScore: Int,
        period: String,
        clock: String,
        awayNow: Double,
        homeNow: Double,
        liveProjAway: Double,
        liveProjHome: Double,
        prematchAway: Double,
        prematchHome: Double,
        pregameProjAway: Double,
        pregameProjHome: Double
    ) -> String {
        let awaySecField = awaySecondary.map { #", "secondary_color": "\#($0)""# } ?? ""
        let homeSecField = homeSecondary.map { #", "secondary_color": "\#($0)""# } ?? ""
        let awayNowPct = Int((awayNow * 100.0).rounded())
        let homeNowPct = 100 - awayNowPct
        let awayPrePct = Int((prematchAway * 100.0).rounded())
        let homePrePct = 100 - awayPrePct
        return """
        {
          "id": \(id),
          "sport": "\(sport)",
          "sport_name": "\(sportName)",
          "away_team": "\(awayTeam)",
          "home_team": "\(homeTeam)",
          "commence_time": "2026-11-16T20:00:00Z",
          "status": "live",
          "away_score": \(awayScore),
          "home_score": \(homeScore),
          "away_team_data": {
            "abbreviation": "\(awayAbbr)",
            "primary_color": "\(awayPrimary)"\(awaySecField)
          },
          "home_team_data": {
            "abbreviation": "\(homeAbbr)",
            "primary_color": "\(homePrimary)"\(homeSecField)
          },
          "current_odds": {
            "away_probability": \(awayNow),
            "home_probability": \(homeNow),
            "away_rendered_percent": \(awayNowPct),
            "home_rendered_percent": \(homeNowPct),
            "updated_at": "2026-11-16T20:54:00Z",
            "live_projection": {
              "projected_away_score": \(liveProjAway),
              "projected_home_score": \(liveProjHome),
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T20:00:00Z",
              "earliest_confirmed_at": "2026-11-16T20:30:00Z",
              "latest_captured_at": "2026-11-16T20:54:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 6,
              "unit": "points",
              "period": "full_game"
            }
          },
          "prematch_odds": {
            "away_probability": \(prematchAway),
            "home_probability": \(prematchHome),
            "away_rendered_percent": \(awayPrePct),
            "home_rendered_percent": \(homePrePct),
            "source": "kalshi"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T20:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "unit": "points",
            "period": "full_game",
            "projected_away_score": \(pregameProjAway),
            "projected_home_score": \(pregameProjHome),
            "bookmaker_count": 12,
            "earliest_captured_at": "2026-11-16T19:30:00Z",
            "latest_captured_at": "2026-11-16T19:58:00Z"
          },
          "espn": {
            "period": "\(period)",
            "game_clock": "\(clock)"
          },
          "hero_probability_observed_at": "2026-11-16T20:54:00Z"
        }
        """
    }

    // MARK: - 1. Exact Segment Inks, Ordering & Ruling 197 Across Page + All 3 Card Surfaces

    func testLivePregameSummaryCarriesTeamColoursNamedFirstAcrossPageDiscoverFeedAndSearch() throws {
        typealias Seg = EventSportHeadlines12472.LivePregameSummary.Segment

        // A. Distinct colours (Patriots @ Lions — Home favoured: Lions 58%, projected 27–24)
        let nflJSON = makeLiveGameJSON(
            id: 501001, sport: "americanfootball_nfl", sportName: "NFL",
            awayTeam: "New England Patriots", homeTeam: "Detroit Lions",
            awayAbbr: "NE", homeAbbr: "DET",
            awayPrimary: "#C60C30", awaySecondary: "#002244",
            homePrimary: "#0076B6", homeSecondary: "#B0B7BC",
            awayScore: 17, homeScore: 21, period: "Q3", clock: "8:14",
            awayNow: 0.338, homeNow: 0.662, liveProjAway: 23.4, liveProjHome: 28.2,
            prematchAway: 0.42, prematchHome: 0.58, pregameProjAway: 23.9, pregameProjHome: 27.1
        )
        let nflDetail = try decodeJSON(EventDetail.self, nflJSON)
        let nflFeed = try decodeJSON(FeedEventData.self, nflJSON)
        let nflSearch = SearchEventCardAdapter183A.fromSearchResult(
            try decodeJSON(SearchEvent.self, nflJSON),
            sportDisplayName: "NFL"
        )

        let pageSummary = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nflDetail,
                awayFullName: nflDetail.awayTeam,
                homeFullName: nflDetail.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            ).livePregameSummary
        )
        let discoverSummary = try XCTUnwrap(
            DiscoverSingleGameCard190C.build(
                event: nflFeed,
                prematch: PrematchReading.resolve(prematch: nflFeed.prematchOdds, opening: nil),
                usesPictureLayout: true
            ).livePregameSummary
        )
        let feedSummary = try XCTUnwrap(LivePregameCardSummary213A.resolve(event: nflFeed))
        let searchSummary = try XCTUnwrap(LivePregameCardSummary213A.resolve(event: nflSearch))

        let expectedLionsSegments: [Seg] = [
            Seg(text: "Pregame", ink: .quietLead),
            Seg(text: "  ", ink: .quiet),
            Seg(text: "Lions 58%", ink: .homeTeam),
            Seg(text: " · projected ", ink: .quiet),
            Seg(text: "27", ink: .homeTeam),
            Seg(text: "\u{2013}", ink: .quiet),
            Seg(text: "24", ink: .awayTeam),
        ]
        XCTAssertEqual(pageSummary.fullText, "Pregame  Lions 58% · projected 27–24")
        XCTAssertEqual(pageSummary.segments, expectedLionsSegments)
        XCTAssertEqual(discoverSummary, pageSummary)
        XCTAssertEqual(feedSummary, pageSummary)
        XCTAssertEqual(searchSummary, pageSummary)

        // B. Same-colour-family pair (Kansas @ Duke — Away favoured: Kansas 62%, projected 78–73;
        //    Ruling 197 switches Kansas from #0051BA blue to #E8000D crimson)
        let sameFamilyJSON = makeLiveGameJSON(
            id: 501002, sport: "basketball_ncaab", sportName: "NCAAB",
            awayTeam: "Kansas Jayhawks", homeTeam: "Duke Blue Devils",
            awayAbbr: "KU", homeAbbr: "DUKE",
            awayPrimary: "#0051BA", awaySecondary: "#E8000D",
            homePrimary: "#003087", homeSecondary: "#FFFFFF",
            awayScore: 44, homeScore: 41, period: "2H", clock: "11:20",
            awayNow: 0.578, homeNow: 0.422, liveProjAway: 79.2, liveProjHome: 75.1,
            prematchAway: 0.62, prematchHome: 0.38, pregameProjAway: 78.1, pregameProjHome: 73.2
        )
        let kuFeed = try decodeJSON(FeedEventData.self, sameFamilyJSON)
        let kuColors = TeamTextContrast.cardColorHexes(
            awayHex: kuFeed.awayTeamData?.primaryColor,
            homeHex: kuFeed.homeTeamData?.primaryColor,
            awaySecondaryHex: kuFeed.awayTeamData?.secondaryColor
        )
        XCTAssertEqual(kuColors.away.uppercased(), "#E8000D", "Ruling 197 switches Kansas away blue to crimson secondary")
        XCTAssertEqual(kuColors.home.uppercased(), "#003087", "Duke keeps home royal blue")

        let kuSummary = try XCTUnwrap(LivePregameCardSummary213A.resolve(event: kuFeed))
        XCTAssertEqual(kuSummary.fullText, "Pregame  Kansas 62% · projected 78–73")
        XCTAssertEqual(
            kuSummary.segments,
            [
                Seg(text: "Pregame", ink: .quietLead),
                Seg(text: "  ", ink: .quiet),
                Seg(text: "Kansas 62%", ink: .awayTeam),
                Seg(text: " · projected ", ink: .quiet),
                Seg(text: "78", ink: .awayTeam),
                Seg(text: "\u{2013}", ink: .quiet),
                Seg(text: "73", ink: .homeTeam),
            ],
            "Named away favourite's number (78) comes first in away colour; home's 73 comes second in home colour"
        )

        // C. Grey-fallback pair (Gonzaga @ Duke — Ruling 197 switches Gonzaga #041E42/#FFFFFF to #64748B slate)
        let greyFallbackJSON = makeLiveGameJSON(
            id: 501003, sport: "basketball_ncaab", sportName: "NCAAB",
            awayTeam: "Gonzaga Bulldogs", homeTeam: "Duke Blue Devils",
            awayAbbr: "GONZ", homeAbbr: "DUKE",
            awayPrimary: "#041E42", awaySecondary: "#FFFFFF",
            homePrimary: "#003087", homeSecondary: "#FFFFFF",
            awayScore: 39, homeScore: 37, period: "2H", clock: "14:05",
            awayNow: 0.542, homeNow: 0.458, liveProjAway: 77.0, liveProjHome: 74.8,
            prematchAway: 0.56, prematchHome: 0.44, pregameProjAway: 76.2, pregameProjHome: 74.1
        )
        let gonzFeed = try decodeJSON(FeedEventData.self, greyFallbackJSON)
        let gonzColors = TeamTextContrast.cardColorHexes(
            awayHex: gonzFeed.awayTeamData?.primaryColor,
            homeHex: gonzFeed.homeTeamData?.primaryColor,
            awaySecondaryHex: gonzFeed.awayTeamData?.secondaryColor
        )
        XCTAssertEqual(gonzColors.away.uppercased(), "#64748B", "Ruling 197 falls back to #64748B slate when secondary is white")
        XCTAssertEqual(gonzColors.home.uppercased(), "#003087")

        let gonzSummary = try XCTUnwrap(LivePregameCardSummary213A.resolve(event: gonzFeed))
        XCTAssertEqual(gonzSummary.fullText, "Pregame  Gonzaga 56% · projected 76–74")
        XCTAssertEqual(
            gonzSummary.segments,
            [
                Seg(text: "Pregame", ink: .quietLead),
                Seg(text: "  ", ink: .quiet),
                Seg(text: "Gonzaga 56%", ink: .awayTeam),
                Seg(text: " · projected ", ink: .quiet),
                Seg(text: "76", ink: .awayTeam),
                Seg(text: "\u{2013}", ink: .quiet),
                Seg(text: "74", ink: .homeTeam),
            ]
        )
    }

    // MARK: - 2. 390 px Render Contact Sheets (Distinct, Same-Family, Grey-Fallback Across All 4 Surfaces)

    private func renderImage<V: View>(_ view: V, width: CGFloat = 390) -> UIImage {
        let wrapped = view
            .frame(width: width)
            .background(Color(UIColor.systemGroupedBackground))
            .environmentObject(PinManager(
                defaults: UserDefaults(suiteName: "LivePregameLineColours213A214A1Tests")!,
                serverLoad: { PinsResponse(events: [], futures: []) },
                serverSync: { _, _, _ in }
            ))
            .environmentObject(NavigationCoordinator())
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(wrapped, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 12_000))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: max(fitting.height, 400))
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
        let until = Date().addingTimeInterval(0.25)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: width, height: 12_000)).height, 400)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.04))
        } while Date() < until

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: host.view.bounds.size, format: format)
        return renderer.image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func stitchVertical(_ images: [UIImage]) -> UIImage {
        let maxW = images.map(\.size.width).max() ?? 390
        let totalH = images.map(\.size.height).reduce(0, +)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        format.opaque = true
        let r = UIGraphicsImageRenderer(size: CGSize(width: maxW, height: totalH), format: format)
        return r.image { ctx in
            UIColor.systemGroupedBackground.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: maxW, height: totalH))
            var y: CGFloat = 0
            for img in images {
                img.draw(in: CGRect(x: 0, y: y, width: img.size.width, height: img.size.height))
                y += img.size.height
            }
        }
    }

    private func buildFourSurfaceStack(
        sectionTitle: String,
        gameJSON: String,
        liveStatusText: String,
        historyHomePoints: [Double]
    ) throws -> AnyView {
        let detail = try decodeJSON(EventDetail.self, gameJSON)
        let feedEvent = try decodeJSON(FeedEventData.self, gameJSON)
        let searchEvent = try decodeJSON(SearchEvent.self, gameJSON)
        let adaptedSearch = SearchEventCardAdapter183A.fromSearchResult(
            searchEvent,
            sportDisplayName: feedEvent.sportName
        )

        let colors = TeamTextContrast.cardColors(
            awayHex: feedEvent.awayTeamData?.primaryColor,
            homeHex: feedEvent.homeTeamData?.primaryColor,
            awaySecondaryHex: feedEvent.awayTeamData?.secondaryColor
        )

        let pageModel = EventSportHeadlines12472.resolve(
            event: detail,
            awayFullName: detail.awayTeam,
            homeFullName: detail.homeTeam,
            liveStatusText: liveStatusText,
            hasScore: true,
            numberStreams: true,
            now: fixedNow
        )

        let pageHeadline = EventSportHeadlineCard12472(
            model: pageModel,
            colors: colors,
            ekgTracker: .empty,
            liveUpdateStatus: .awaitingUpdate,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: fixedNow,
            confirmedAt: fixedNow,
            revealForecast: nil
        )
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1))

        let historyJSON = """
        {
          "event_id": \(feedEvent.id),
          "home_team": "\(feedEvent.homeTeam)",
          "away_team": "\(feedEvent.awayTeam)",
          "status": "live",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-16T20:05:00Z", "home_probability": \(historyHomePoints[0])},
              {"timestamp": "2026-11-16T20:20:00Z", "home_probability": \(historyHomePoints[1])},
              {"timestamp": "2026-11-16T20:38:00Z", "home_probability": \(historyHomePoints[2])},
              {"timestamp": "2026-11-16T20:54:00Z", "home_probability": \(historyHomePoints[3])}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-16T20:05:00Z", "home_probability": \(historyHomePoints[0])},
            {"timestamp": "2026-11-16T20:20:00Z", "home_probability": \(historyHomePoints[1])},
            {"timestamp": "2026-11-16T20:38:00Z", "home_probability": \(historyHomePoints[2])},
            {"timestamp": "2026-11-16T20:54:00Z", "home_probability": \(historyHomePoints[3])}
          ]
        }
        """
        let chartHistory = try decodeJSON(EventHistoryResponse.self, historyJSON)
        let discoverCard = NativeEventDiscoverCard(
            event: feedEvent,
            feedContext: "Tight second-half matchup",
            expandedContext: nil,
            navigationPath: .constant(NavigationPath()),
            chartHistory: chartHistory
        )

        let feedCard = EventCardView(event: feedEvent, reason: "Tight second-half matchup")
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1))

        let searchCard = EventCardView(event: adaptedSearch, reason: nil)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1))

        return AnyView(
            VStack(alignment: .leading, spacing: 12) {
                Text(sectionTitle)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 16)

                surfaceBlock("1 · Phone Game Page (.page)", pageHeadline)
                surfaceBlock("2 · Discover Card (.card + 191-A chart)", discoverCard)
                surfaceBlock("3 · Feed Card (.card)", feedCard)
                surfaceBlock("4 · Search Card (SearchEventCardAdapter183A → EventCardView)", searchCard)
            }
            .padding(.vertical, 14)
        )
    }

    private func surfaceBlock<V: View>(_ label: String, _ content: V) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            content
        }
        .padding(.horizontal, 16)
    }

    func testExport213A214A1PhoneSheetsAt390px() throws {
        // 1. Distinct Colours: Patriots (#C60C30 red) @ Lions (#0076B6 blue)
        let distinctJSON = makeLiveGameJSON(
            id: 501001, sport: "americanfootball_nfl", sportName: "NFL",
            awayTeam: "New England Patriots", homeTeam: "Detroit Lions",
            awayAbbr: "NE", homeAbbr: "DET",
            awayPrimary: "#C60C30", awaySecondary: "#002244",
            homePrimary: "#0076B6", homeSecondary: "#B0B7BC",
            awayScore: 17, homeScore: 21, period: "Q3", clock: "8:14",
            awayNow: 0.338, homeNow: 0.662, liveProjAway: 23.6, liveProjHome: 28.1,
            prematchAway: 0.42, prematchHome: 0.58, pregameProjAway: 23.9, pregameProjHome: 27.1
        )

        // 2. Same-Colour-Family Pair: Kansas (#0051BA blue -> #E8000D crimson secondary) @ Duke (#003087 blue)
        let sameFamilyJSON = makeLiveGameJSON(
            id: 501002, sport: "basketball_ncaab", sportName: "NCAAB",
            awayTeam: "Kansas Jayhawks", homeTeam: "Duke Blue Devils",
            awayAbbr: "KU", homeAbbr: "DUKE",
            awayPrimary: "#0051BA", awaySecondary: "#E8000D",
            homePrimary: "#003087", homeSecondary: "#FFFFFF",
            awayScore: 44, homeScore: 41, period: "2H", clock: "11:20",
            awayNow: 0.578, homeNow: 0.422, liveProjAway: 79.2, liveProjHome: 75.1,
            prematchAway: 0.62, prematchHome: 0.38, pregameProjAway: 78.1, pregameProjHome: 73.2
        )

        // 3. Grey-Fallback Pair: Gonzaga (#041E42 navy + #FFFFFF white -> #64748B slate fallback) @ Duke (#003087 blue)
        let greyFallbackJSON = makeLiveGameJSON(
            id: 501003, sport: "basketball_ncaab", sportName: "NCAAB",
            awayTeam: "Gonzaga Bulldogs", homeTeam: "Duke Blue Devils",
            awayAbbr: "GONZ", homeAbbr: "DUKE",
            awayPrimary: "#041E42", awaySecondary: "#FFFFFF",
            homePrimary: "#003087", homeSecondary: "#FFFFFF",
            awayScore: 39, homeScore: 37, period: "2H", clock: "14:05",
            awayNow: 0.542, homeNow: 0.458, liveProjAway: 77.0, liveProjHome: 74.8,
            prematchAway: 0.56, prematchHome: 0.44, pregameProjAway: 76.2, pregameProjHome: 74.1
        )

        let distinctView = try buildFourSurfaceStack(
            sectionTitle: "1 · DISTINCT COLOURS · Patriots @ Lions (213-A + 214-A1 · 390 px)",
            gameJSON: distinctJSON,
            liveStatusText: "Q3 · 8:14",
            historyHomePoints: [0.58, 0.51, 0.61, 0.662]
        )
        let sameFamilyView = try buildFourSurfaceStack(
            sectionTitle: "2 · SAME-FAMILY PAIR (Ruling 197 → Crimson) · Kansas @ Duke (390 px)",
            gameJSON: sameFamilyJSON,
            liveStatusText: "2H · 11:20",
            historyHomePoints: [0.38, 0.44, 0.40, 0.422]
        )
        let greyFallbackView = try buildFourSurfaceStack(
            sectionTitle: "3 · GREY-FALLBACK PAIR (Ruling 197 → #64748B Slate) · Gonzaga @ Duke (390 px)",
            gameJSON: greyFallbackJSON,
            liveStatusText: "2H · 14:05",
            historyHomePoints: [0.44, 0.49, 0.47, 0.458]
        )

        let imgDistinct = renderImage(distinctView)
        let imgSameFamily = renderImage(sameFamilyView)
        let imgGreyFallback = renderImage(greyFallbackView)
        let fullSheet = stitchVertical([imgDistinct, imgSameFamily, imgGreyFallback])

        XCTAssertEqual(imgDistinct.size.width, 390, accuracy: 0.5)
        XCTAssertEqual(imgSameFamily.size.width, 390, accuracy: 0.5)
        XCTAssertEqual(imgGreyFallback.size.width, 390, accuracy: 0.5)

        if let dir = ProcessInfo.processInfo.environment["EXPORT_213A_214A1_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(imgDistinct.pngData()).write(to: outURL.appendingPathComponent("213a-214a1-distinct-pair-390.png"))
            try XCTUnwrap(imgSameFamily.pngData()).write(to: outURL.appendingPathComponent("213a-214a1-same-family-pair-390.png"))
            try XCTUnwrap(imgGreyFallback.pngData()).write(to: outURL.appendingPathComponent("213a-214a1-grey-fallback-pair-390.png"))
            try XCTUnwrap(fullSheet.pngData()).write(to: outURL.appendingPathComponent("213a-214a1-full-sheet-390.png"))
        }
    }
}
