import SwiftUI
import XCTest
@testable import Bain_Luck

/// #12616 (Decision 161-B, "chance first") — unit and 390pt render verification
/// for `EventCardView`'s compact two-column layout across Before, During, and
/// After, plus soccer draw rows, tennis blank projections, and large text.
@MainActor
final class CompactGameCard12616Tests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    // MARK: - 1. Column headers across states and sports

    func testColumnHeadersMatch161BAcrossStates() {
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: true, isLive: false, isFinished: false, isSuspended: false,
                hasProjectedBefore: true, hasCurrentChance: true, hasPrematchChance: false, hasScore: false),
            .init(medium: "Projected", large: "Chance")
        )
        // Tennis before: no projected score -> medium header omitted, Chance remains.
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: true, isLive: false, isFinished: false, isSuspended: false,
                hasProjectedBefore: false, hasCurrentChance: true, hasPrematchChance: false, hasScore: false),
            .init(medium: nil, large: "Chance")
        )
        // Live: Score (medium) and Now (large).
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: false, isLive: true, isFinished: false, isSuspended: false,
                hasProjectedBefore: false, hasCurrentChance: true, hasPrematchChance: true, hasScore: true),
            .init(medium: "Score", large: "Now")
        )
        // Finished: Pregame (medium) and Final (large).
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: false, isLive: false, isFinished: true, isSuspended: false,
                hasProjectedBefore: false, hasCurrentChance: false, hasPrematchChance: true, hasScore: true),
            .init(medium: "Pregame", large: "Final")
        )
        // Suspended-and-started: no headers under "No result reported".
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: false, isLive: false, isFinished: false, isSuspended: true,
                hasProjectedBefore: false, hasCurrentChance: false, hasPrematchChance: true, hasScore: true),
            .init(medium: nil, large: nil)
        )
    }

    // MARK: - 2. Live streaming tenths: complement sum & <1% / >99%

    func testLiveTenthsPairSumsTo100Point0AndNeverPrintsZeroOrHundred() {
        let duel = CompactGameCard12616.liveTenthsStrings(
            away: 0.7124, home: 0.2876, awayIsWithheld: false)
        XCTAssertEqual(duel.away, "71.2%")
        XCTAssertEqual(duel.home, "28.8%")

        // Half-tenth boundary (.xx05) still sums to 100.0%, anchored on favourite.
        let halfBoundary = CompactGameCard12616.liveTenthsStrings(
            away: 0.6425, home: 0.3575, awayIsWithheld: false)
        XCTAssertEqual(halfBoundary.away, "64.3%")
        XCTAssertEqual(halfBoundary.home, "35.7%")

        // Near-certain live: never 0%, 0.0%, 100%, or 100.0%.
        let nearCertain = CompactGameCard12616.liveTenthsStrings(
            away: 0.996, home: 0.004, awayIsWithheld: false)
        XCTAssertEqual(nearCertain.away, ">99%")
        XCTAssertEqual(nearCertain.home, "<1%")

        // Two-way complement soccer withholds away (#5363).
        let withheld = CompactGameCard12616.liveTenthsStrings(
            away: 0.36, home: 0.64, awayIsWithheld: true)
        XCTAssertNil(withheld.away)
        XCTAssertEqual(withheld.home, "64.0%")
    }

    // MARK: - 3. Scheduled projected final admission

    func testScheduledProjectionAdmitsSupportedSportsAndWithholdsTennisAndTies() throws {
        let nfl = try decodeEvent("""
        {"id": 1, "sport": "americanfootball_nfl", "home_team": "Detroit Lions", "away_team": "New England Patriots",
         "status": "scheduled", "current_odds": {"home_probability": 0.42, "away_probability": 0.58,
         "projected_home_score": 21.3, "projected_away_score": 24.1}}
        """)
        XCTAssertEqual(ScheduledCardProjectedFinal12616.card(nfl), .init(away: 24, home: 21))

        let tennis = try decodeEvent("""
        {"id": 2, "sport": "tennis_atp_us_open", "home_team": "Carlos Alcaraz", "away_team": "Jannik Sinner",
         "status": "scheduled", "current_odds": {"home_probability": 0.46, "away_probability": 0.54,
         "projected_home_score": 18.5, "projected_away_score": 19.5}}
        """)
        XCTAssertNil(ScheduledCardProjectedFinal12616.card(tennis), "tennis games spread is never a sets scoreline")
    }

    // MARK: - 4. Three-way soccer draw row vs two-way complement

    func testSoccerDrawRowRequiresExplicitThreeWayDrawProbability() throws {
        let twoWaySoccer = try decodeEvent("""
        {"id": 10, "sport": "soccer_epl", "home_team": "Chelsea", "away_team": "Arsenal",
         "status": "scheduled", "current_odds": {"home_probability": 0.34, "away_probability": 0.66}}
        """)
        XCTAssertNil(CompactGameCard12616.drawChanceText(
            event: twoWaySoccer, isScheduled: true, isLive: false, isFinished: false, isSuspended: false))

        let threeWaySoccer = try decodeEvent("""
        {"id": 11, "sport": "soccer_epl", "home_team": "Chelsea", "away_team": "Arsenal",
         "status": "scheduled", "current_odds": {"home_probability": 0.34, "away_probability": 0.41, "draw_probability": 0.25}}
        """)
        XCTAssertTrue(CompactGameCard12616.hasExplicitThreeWayCurrent(threeWaySoccer))
        XCTAssertEqual(
            CompactGameCard12616.drawChanceText(
                event: threeWaySoccer, isScheduled: true, isLive: false, isFinished: false, isSuspended: false),
            "25%"
        )
    }

    // MARK: - 5. 390pt native renders for PR review (when BUILDERC_EXPORT_12616=1)

    func testExport390PtRendersWhenRequested() throws {
        guard ProcessInfo.processInfo.environment["BUILDERC_EXPORT_12616"] == "1" else { return }
        let outDir = URL(fileURLWithPath: "/tmp/builderc-12616-renders", isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let pins = PinManager(
            defaults: UserDefaults(suiteName: "CompactGameCard12616Renders")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let beforeNFL = try decodeEvent("""
        {"id": 101, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "New England Patriots", "home_team": "Detroit Lions",
         "commence_time": "2026-11-15T21:25:00Z", "status": "scheduled",
         "away_team_data": {"primary_color": "#002244"}, "home_team_data": {"primary_color": "#0076B6"},
         "current_odds": {"away_probability": 0.58, "home_probability": 0.42,
                          "away_rendered_percent": 58, "home_rendered_percent": 42,
                          "projected_away_score": 24.2, "projected_home_score": 21.1}}
        """)

        let duringNBA = try decodeEvent("""
        {"id": 102, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Philadelphia 76ers",
         "commence_time": "2026-11-12T17:00:00Z", "status": "live",
         "away_score": 88, "home_score": 79,
         "espn": {"period": "Q3", "game_clock": "4:12"},
         "away_team_data": {"primary_color": "#007A33"}, "home_team_data": {"primary_color": "#006BB6"},
         "opening_odds": {"away_probability": 0.54, "home_probability": 0.46},
         "prematch_odds": {"away_probability": 0.54, "home_probability": 0.46,
                           "away_rendered_percent": 54, "home_rendered_percent": 46, "source": "kalshi"},
         "current_odds": {"away_probability": 0.712, "home_probability": 0.288,
                          "live_projection": {
                              "projected_away_score": 118.2, "projected_home_score": 109.1,
                              "kind": "in_play", "boundary": "commence_time",
                              "boundary_at": "2026-11-12T17:00:00Z",
                              "earliest_confirmed_at": "2026-11-12T17:45:00Z",
                              "latest_captured_at": "2026-11-12T17:46:00Z",
                              "source": "sportsbooks", "basis": "consensus_spread_total",
                              "bookmaker_count": 4, "unit": "points", "period": "full_game"
                          }}}
        """)

        let afterPackersUpset = try decodeEvent("""
        {"id": 103, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Green Bay Packers", "home_team": "New England Patriots",
         "commence_time": "2026-11-08T18:00:00Z", "status": "completed",
         "away_score": 45, "home_score": 27,
         "away_team_data": {"primary_color": "#203731"}, "home_team_data": {"primary_color": "#002244"},
         "prematch_odds": {"away_probability": 0.38, "home_probability": 0.62,
                           "away_rendered_percent": 38, "home_rendered_percent": 62, "source": "kalshi"},
         "pregame_projection": {
             "projected_away_score": 21.0, "projected_home_score": 24.0,
             "kind": "last_before_scheduled_start", "boundary": "scheduled_start",
             "boundary_at": "2026-11-08T18:00:00Z",
             "earliest_captured_at": "2026-11-08T17:30:00Z",
             "latest_captured_at": "2026-11-08T17:55:00Z",
             "source": "sportsbooks", "basis": "consensus_spread_total",
             "bookmaker_count": 5, "unit": "points", "period": "full_game"
         }}
        """)

        let afterCeltics76ers = try decodeEvent("""
        {"id": 104, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Philadelphia 76ers",
         "commence_time": "2026-11-10T00:00:00Z", "status": "completed",
         "away_score": 113, "home_score": 103,
         "away_team_data": {"primary_color": "#007A33"}, "home_team_data": {"primary_color": "#006BB6"},
         "prematch_odds": {"away_probability": 0.54, "home_probability": 0.46,
                           "away_rendered_percent": 54, "home_rendered_percent": 46, "source": "kalshi"},
         "pregame_projection": {
             "projected_away_score": 110.2, "projected_home_score": 106.4,
             "kind": "last_before_scheduled_start", "boundary": "scheduled_start",
             "boundary_at": "2026-11-10T00:00:00Z",
             "earliest_captured_at": "2026-11-09T23:30:00Z",
             "latest_captured_at": "2026-11-09T23:55:00Z",
             "source": "sportsbooks", "basis": "consensus_spread_total",
             "bookmaker_count": 5, "unit": "points", "period": "full_game"
         }}
        """)

        let afterCelticsBucks = try decodeEvent("""
        {"id": 105, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Milwaukee Bucks", "home_team": "Boston Celtics",
         "commence_time": "2026-11-09T00:00:00Z", "status": "completed",
         "away_score": 107, "home_score": 119,
         "away_team_data": {"primary_color": "#00471B"}, "home_team_data": {"primary_color": "#007A33"},
         "prematch_odds": {"away_probability": 0.13, "home_probability": 0.87,
                           "away_rendered_percent": 13, "home_rendered_percent": 87, "source": "kalshi"},
         "pregame_projection": {
             "projected_away_score": 108.0, "projected_home_score": 118.4,
             "kind": "last_before_scheduled_start", "boundary": "scheduled_start",
             "boundary_at": "2026-11-09T00:00:00Z",
             "earliest_captured_at": "2026-11-08T23:30:00Z",
             "latest_captured_at": "2026-11-08T23:55:00Z",
             "source": "sportsbooks", "basis": "consensus_spread_total",
             "bookmaker_count": 5, "unit": "points", "period": "full_game"
         }}
        """)

        let soccerThreeWay = try decodeEvent("""
        {"id": 106, "sport": "soccer_epl", "sport_name": "Premier League",
         "away_team": "Arsenal", "home_team": "Chelsea",
         "commence_time": "2026-11-15T16:30:00Z", "status": "scheduled",
         "away_team_data": {"primary_color": "#EF0107"}, "home_team_data": {"primary_color": "#034694"},
         "current_odds": {"away_probability": 0.41, "home_probability": 0.34, "draw_probability": 0.25,
                          "away_rendered_percent": 41, "home_rendered_percent": 34,
                          "projected_away_score": 1.6, "projected_home_score": 1.3}}
        """)

        let tennisBlankProj = try decodeEvent("""
        {"id": 107, "sport": "tennis_atp_finals", "sport_name": "ATP Finals",
         "away_team": "Jannik Sinner", "home_team": "Carlos Alcaraz",
         "commence_time": "2026-11-14T19:00:00Z", "status": "scheduled",
         "current_odds": {"away_probability": 0.56, "home_probability": 0.44,
                          "away_rendered_percent": 56, "home_rendered_percent": 44}}
        """)

        let longNamesLargeText = try decodeEvent("""
        {"id": 108, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Minnesota Timberwolves", "home_team": "Portland Trail Blazers",
         "commence_time": "2026-11-12T17:00:00Z", "status": "live",
         "away_score": 104, "home_score": 98,
         "espn": {"period": "Q4", "game_clock": "6:40"},
         "away_team_data": {"primary_color": "#0C2340"}, "home_team_data": {"primary_color": "#E03A3E"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.784, "home_probability": 0.216,
                          "live_projection": {
                              "projected_away_score": 119.3, "projected_home_score": 111.2,
                              "kind": "in_play", "boundary": "commence_time",
                              "boundary_at": "2026-11-12T17:00:00Z",
                              "earliest_confirmed_at": "2026-11-12T17:50:00Z",
                              "latest_captured_at": "2026-11-12T17:51:00Z",
                              "source": "sportsbooks", "basis": "consensus_spread_total",
                              "bookmaker_count": 4, "unit": "points", "period": "full_game"
                          }}}
        """)

        func saveRender<V: View>(_ view: V, fileName: String, typeSize: DynamicTypeSize = .large) throws {
            let wrapped = VStack(spacing: 12) { view }
                .padding(16)
                .frame(width: 390)
                .background(Color(white: 0.965))
                .environmentObject(pins)
                .environment(\.colorScheme, .light)
                .environment(\.dynamicTypeSize, typeSize)
            let host = UIHostingController(rootView: wrapped)
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 3000))
            let bounds = CGRect(x: 0, y: 0, width: 390, height: ceil(fitting.height))
            let window = UIWindow(frame: bounds)
            window.rootViewController = host
            host.view.frame = bounds
            window.isHidden = false
            for _ in 0..<6 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
            let format = UIGraphicsImageRendererFormat()
            format.scale = 3.0
            let image = UIGraphicsImageRenderer(bounds: bounds, format: format).image { _ in
                host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
            }
            window.isHidden = true
            try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent(fileName))
        }

        func cardBox(_ e: FeedEventData, reason: String? = nil) -> some View {
            EventCardView(event: e, reason: reason)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(Color.black.opacity(0.08), lineWidth: 1)
                )
        }

        try saveRender(
            VStack(spacing: 12) {
                cardBox(beforeNFL)
                cardBox(duringNBA)
                cardBox(afterPackersUpset, reason: "Green Bay Packers won as a 38% underdog")
            },
            fileName: "12616-states-before-during-after-390.png"
        )

        try saveRender(
            VStack(spacing: 12) {
                cardBox(afterPackersUpset, reason: "Green Bay Packers won as a 38% underdog")
                cardBox(afterCeltics76ers)
                cardBox(afterCelticsBucks)
            },
            fileName: "12616-my-stuff-three-finals-390.png"
        )

        try saveRender(
            VStack(spacing: 12) {
                cardBox(soccerThreeWay)
                cardBox(tennisBlankProj)
            },
            fileName: "12616-soccer-draw-and-tennis-390.png"
        )

        try saveRender(
            cardBox(longNamesLargeText),
            fileName: "12616-largest-text-timberwolves-blazers-390.png",
            typeSize: .xxxLarge
        )

        func legacyFinishedCardBox(_ e: FeedEventData, reason: String? = nil) -> some View {
            let awayWon = (e.awayScore ?? 0) > (e.homeScore ?? 0)
            let homeWon = (e.homeScore ?? 0) > (e.awayScore ?? 0)
            let awayPre = e.prematchOdds?.awayRenderedPercent ?? 50
            let homePre = e.prematchOdds?.homeRenderedPercent ?? 50
            let upsetAway = awayWon && awayPre < homePre
            return VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Text(e.sportName ?? "NFL").font(.caption).foregroundStyle(.secondary)
                    StatusBadge(status: e.status, commenceTime: e.commenceTime, gameClock: nil, period: nil)
                    Spacer()
                    Text("Nov 8").font(.caption2).foregroundStyle(.secondary)
                    Image(systemName: "bookmark").font(.caption).foregroundStyle(.secondary)
                }
                HStack(spacing: 8) {
                    Circle().fill(Color.secondary.opacity(0.18)).frame(width: 24, height: 24)
                    Text(e.awayTeam).font(.subheadline).fontWeight(awayWon ? .bold : .medium)
                        .foregroundStyle(awayWon ? .primary : .secondary).lineLimit(1)
                    Spacer()
                    Text("\(e.awayScore ?? 0)").font(.subheadline.monospacedDigit())
                        .fontWeight(awayWon ? .bold : .regular)
                        .foregroundStyle(awayWon ? .primary : .secondary)
                    HStack(spacing: 3) {
                        Text("Pregame").font(.caption).foregroundStyle(.secondary)
                        Text("\(awayPre)%").font(.caption.monospacedDigit()).fontWeight(.semibold)
                            .foregroundStyle(upsetAway ? Color.orange : Color.secondary.opacity(0.7))
                    }.fixedSize()
                }
                HStack(spacing: 8) {
                    Circle().fill(Color.secondary.opacity(0.18)).frame(width: 24, height: 24)
                    Text(e.homeTeam).font(.subheadline).fontWeight(homeWon ? .bold : .medium)
                        .foregroundStyle(homeWon ? .primary : .secondary).lineLimit(1)
                    Spacer()
                    Text("\(e.homeScore ?? 0)").font(.subheadline.monospacedDigit())
                        .fontWeight(homeWon ? .bold : .regular)
                        .foregroundStyle(homeWon ? .primary : .secondary)
                    HStack(spacing: 3) {
                        Text("Pregame").font(.caption).foregroundStyle(.secondary)
                        Text("\(homePre)%").font(.caption.monospacedDigit()).fontWeight(.semibold)
                            .foregroundStyle(.secondary.opacity(0.7))
                    }.fixedSize()
                }
                ProbabilityBar(
                    awayProb: Double(awayPre) / 100.0,
                    homeProb: Double(homePre) / 100.0,
                    awayColor: Color(hex: e.awayTeamData?.primaryColor ?? "#203731").opacity(0.65),
                    homeColor: Color(hex: e.homeTeamData?.primaryColor ?? "#002244").opacity(0.65),
                    height: 4
                )
                if let proj = e.pregameProjection,
                   let cmp = FinalForecastComparison11296.resolve(
                    sport: e.sport, status: e.status, homeScore: e.homeScore, awayScore: e.awayScore,
                    actualPeriod: .fullGame, projection: proj) {
                    FinalForecastLine11296(comparison: cmp, awayName: e.awayTeam, homeName: e.homeTeam)
                        .padding(.leading, 32)
                }
                if let reason {
                    HStack(spacing: 3) {
                        Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9, weight: .semibold))
                        Text(reason).font(.caption2).fontWeight(.medium)
                    }
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(Color.orange.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 14)
            .background(Color.white)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Color.black.opacity(0.08), lineWidth: 1))
        }

        try saveRender(
            VStack(spacing: 12) {
                legacyFinishedCardBox(afterPackersUpset, reason: "Green Bay Packers won as a 38% underdog")
                legacyFinishedCardBox(afterCeltics76ers)
                legacyFinishedCardBox(afterCelticsBucks)
            },
            fileName: "12616-my-stuff-three-finals-before-390.png"
        )
    }
}
