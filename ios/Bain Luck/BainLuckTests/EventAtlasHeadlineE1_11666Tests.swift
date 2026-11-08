import XCTest
@testable import Bain_Luck

/// #11666 (Step E1) — Native event-page atlas headline and shared details sheet
/// behind `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasHeadlineE1_11666Tests: XCTestCase {

    // MARK: - Build flag & launch override

    func testBuildFlagDefaultsOnAndHonoursLaunchOverride() {
        XCTAssertTrue(
            ReleaseSurfaces.eventPageAtlasEnabled,
            "the shipping switch is enabled for Alex's TestFlight phone look (85-A / #12278)"
        )
        let suiteName = "bainluck.test.atlas.11666.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        XCTAssertFalse(ReleaseSurfaces.isEventPageAtlasEnabled(enabled: false, defaults: defaults))
        XCTAssertTrue(ReleaseSurfaces.isEventPageAtlasEnabled(enabled: true, defaults: defaults))

        defaults.set(true, forKey: ReleaseSurfaces.eventPageAtlasLaunchKey)
        XCTAssertTrue(
            ReleaseSurfaces.isEventPageAtlasEnabled(enabled: false, defaults: defaults),
            "-event_page_atlas_11666 YES enables the surface in tests and on the rig"
        )
    }

    // MARK: - Settled badge & hollow pregame mark

    func testSettledFavoriteWinnerShowsWonAndPregameChance() throws {
        let prematch = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.62, "away_probability": 0.38}
            """
        )
        let badge = EventAtlasHeadline11666.settledBadge(
            outcome: .home,
            awayTeam: "Buffalo Bills",
            homeTeam: "Kansas City Chiefs",
            sportKey: "americanfootball_nfl",
            prematch: prematch,
            opening: nil
        )
        XCTAssertEqual(badge.winnerLabel, "Chiefs Won")
        XCTAssertEqual(badge.systemImage, "checkmark")
        XCTAssertFalse(badge.isUpset)
        XCTAssertEqual(badge.pregameMarkText, "62% pregame")
    }

    func testSettledUnderdogWinnerFlagsUpsetViaPrematchReading9490() throws {
        let prematch = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.68, "away_probability": 0.32}
            """
        )
        let badge = EventAtlasHeadline11666.settledBadge(
            outcome: .away,
            awayTeam: "New York Jets",
            homeTeam: "Buffalo Bills",
            sportKey: "americanfootball_nfl",
            prematch: prematch,
            opening: nil
        )
        XCTAssertEqual(badge.winnerLabel, "Jets Won")
        XCTAssertEqual(badge.systemImage, "checkmark")
        XCTAssertTrue(badge.isUpset)
        XCTAssertEqual(badge.pregameMarkText, "Upset · 32% pregame")
    }

    func testDrawPricedFavouriteUnderFortyPercentIsNotAnUpset9490() throws {
        // #9490 specimen 15304745: Turkey 32.5% v Italy 39.5% on a three-way board.
        let awayFavPrematch = try decode(
            PrematchOdds.self,
            """
            {
              "home_probability": 0.325,
              "away_probability": 0.395,
              "home_rendered_percent": 33,
              "away_rendered_percent": 40,
              "source": "kalshi"
            }
            """
        )
        let awayFavBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .away,
            awayTeam: "Italy",
            homeTeam: "Turkey",
            sportKey: "soccer_uefa_nations_league",
            prematch: awayFavPrematch,
            opening: nil
        )
        XCTAssertEqual(awayFavBadge.winnerLabel, "Italy Won")
        XCTAssertFalse(awayFavBadge.isUpset, "39.5% beat 32.5% on a three-way board: favourite won")
        XCTAssertEqual(awayFavBadge.pregameMarkText, "40% pregame")

        // Mirror with the 39.5% favourite at home.
        let homeFavPrematch = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.395, "away_probability": 0.325, "source": "kalshi"}
            """
        )
        let homeFavBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .home,
            awayTeam: "Turkey",
            homeTeam: "Italy",
            sportKey: "soccer_uefa_nations_league",
            prematch: homeFavPrematch,
            opening: nil
        )
        XCTAssertFalse(homeFavBadge.isUpset)
        XCTAssertEqual(homeFavBadge.pregameMarkText, "40% pregame")

        // Real three-way upset: 33.5% away beat 42.5% home.
        let upsetPrematch = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.425, "away_probability": 0.335, "source": "kalshi"}
            """
        )
        let upsetBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .away,
            awayTeam: "Turkey",
            homeTeam: "Italy",
            sportKey: "soccer_uefa_nations_league",
            prematch: upsetPrematch,
            opening: nil
        )
        XCTAssertTrue(upsetBadge.isUpset)
        XCTAssertEqual(upsetBadge.pregameMarkText, "Upset · 34% pregame")

        // Complement-only three-way board withholds away and never invents an upset.
        let complementOnly = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.35, "source": "kalshi"}
            """
        )
        let homeComplementBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .home,
            awayTeam: "Turkey",
            homeTeam: "Italy",
            sportKey: "soccer_uefa_nations_league",
            prematch: complementOnly,
            opening: nil
        )
        XCTAssertFalse(homeComplementBadge.isUpset)
        XCTAssertEqual(homeComplementBadge.pregameMarkText, "35% pregame")

        let awayComplementBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .away,
            awayTeam: "Turkey",
            homeTeam: "Italy",
            sportKey: "soccer_uefa_nations_league",
            prematch: complementOnly,
            opening: nil
        )
        XCTAssertFalse(awayComplementBadge.isUpset)
        XCTAssertNil(awayComplementBadge.pregameMarkText)
    }

    func testSettledDrawAndUndecidedOutcomes() throws {
        let prematch = try decode(
            PrematchOdds.self,
            """
            {"home_probability": 0.45, "away_probability": 0.30}
            """
        )
        let drawBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .draw,
            awayTeam: "Arsenal",
            homeTeam: "Chelsea",
            sportKey: "soccer_epl",
            prematch: prematch,
            opening: nil
        )
        XCTAssertEqual(drawBadge.winnerLabel, "Draw")
        XCTAssertNil(drawBadge.systemImage)
        XCTAssertFalse(drawBadge.isUpset)

        let undecidedBadge = EventAtlasHeadline11666.settledBadge(
            outcome: .undecided,
            awayTeam: "Arsenal",
            homeTeam: "Chelsea",
            sportKey: "soccer_epl",
            prematch: nil,
            opening: nil
        )
        XCTAssertEqual(undecidedBadge.winnerLabel, "Final")
        XCTAssertNil(undecidedBadge.systemImage)
        XCTAssertNil(undecidedBadge.pregameMarkText)
    }

    // MARK: - Source attribution truth (never calls a single venue "Blended")

    func testSingleVenueNeverPrintsBlended() throws {
        XCTAssertEqual(
            EventAtlasHeadline11666.sourceAttribution(source: "kalshi", sourceCount: 1),
            "Kalshi"
        )
        XCTAssertEqual(
            EventAtlasHeadline11666.sourceAttribution(source: "polymarket", sourceCount: 1),
            "Polymarket"
        )
        XCTAssertEqual(
            EventAtlasHeadline11666.sourceAttribution(source: "draftkings", sourceCount: 1),
            "DraftKings"
        )

        let singleMap = try decode(
            [String: WinProbSource].self,
            """
            {"kalshi": {"value": 0.58, "display_name": "Kalshi"}}
            """
        )
        XCTAssertEqual(
            EventAtlasHeadline11666.sourceAttribution(
                source: "blended",
                sourceCount: 1,
                winProbSources: singleMap
            ),
            "Kalshi",
            "even if source says 'blended', a single contributing venue prints its own name"
        )
    }

    func testMultiVenuePrintsBlendedWithContributors() throws {
        let multiMap = try decode(
            [String: WinProbSource].self,
            """
            {
              "betting": {"value": 0.61, "display_name": "Sportsbooks"},
              "kalshi": {"value": 0.59, "display_name": "Kalshi"}
            }
            """
        )
        let label = EventAtlasHeadline11666.sourceAttribution(
            source: "blend",
            sourceCount: nil,
            winProbSources: multiMap
        )
        XCTAssertEqual(label, "Blended (Sportsbooks, Kalshi)")
    }

    // MARK: - Details sheet model from EventDetail

    func testDetailsSheetModelFromLiveAndSettledEvents() throws {
        let liveEvent = try decode(
            EventDetail.self,
            """
            {
              "id": 15341806,
              "sport": "americanfootball_nfl",
              "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "status": "live",
              "home_score": 14,
              "away_score": 10,
              "hero_probability_source": "blend",
              "current_odds": {"home_probability": 0.642, "away_probability": 0.358},
              "prematch_odds": {"home_probability": 0.55, "away_probability": 0.45},
              "win_probability_sources": {
                "betting": {"value": 0.65, "display_name": "Sportsbooks"},
                "kalshi": {"value": 0.63, "display_name": "Kalshi"}
              }
            }
            """
        )
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let sheet = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: liveEvent,
            phase: .current,
            observedAt: now,
            liveStatus: .live
        )
        XCTAssertEqual(sheet.marketTitle, "Game winner")
        XCTAssertEqual(sheet.primaryReadingLabel, "Current win chance")
        XCTAssertTrue(sheet.primaryReadingValue.contains("Bills"))
        XCTAssertTrue(sheet.primaryReadingValue.contains("Chiefs"))
        XCTAssertEqual(sheet.pregameBaseline, "Pre-match 45% – 55%")
        XCTAssertEqual(sheet.sourceLabel, "Blended (Sportsbooks, Kalshi)")

        let settledEvent = try decode(
            EventDetail.self,
            """
            {
              "id": 15341806,
              "sport": "americanfootball_nfl",
              "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "status": "completed",
              "home_score": 27,
              "away_score": 24,
              "hero_settled_result": "home",
              "hero_probability_source": "kalshi",
              "prematch_odds": {"home_probability": 0.62, "away_probability": 0.38},
              "win_probability_sources": {
                "kalshi": {"value": 1.0, "display_name": "Kalshi"}
              }
            }
            """
        )
        let settledSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: settledEvent,
            phase: nil,
            observedAt: now,
            liveStatus: .hidden
        )
        XCTAssertEqual(settledSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(settledSheet.primaryReadingValue, "Chiefs Won")
        XCTAssertEqual(settledSheet.pregameBaseline, "Pre-match 38% – 62%")
        XCTAssertEqual(settledSheet.sourceLabel, "Kalshi")
        XCTAssertNil(settledSheet.statusSummary)
    }

    func testHeadlineRowClockShiftsToLastRecordedAfterThirtyMinutes() throws {
        let liveEvent = try decode(
            EventDetail.self,
            """
            {
              "id": 15341806,
              "sport": "americanfootball_nfl",
              "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "status": "live",
              "home_score": 14,
              "away_score": 10,
              "hero_probability_source": "blend",
              "current_odds": {"home_probability": 0.642, "away_probability": 0.358}
            }
            """
        )
        let observed = Date(timeIntervalSince1970: 1_800_000_000)
        let freshPhase = EventAtlasHeadline11666.resolvePhase(
            event: liveEvent,
            observedAt: observed,
            liveStatus: .live,
            now: observed.addingTimeInterval(5 * 60)
        )
        XCTAssertEqual(freshPhase, .current)

        let stalePhase = EventAtlasHeadline11666.resolvePhase(
            event: liveEvent,
            observedAt: observed,
            liveStatus: .live,
            now: observed.addingTimeInterval(31 * 60)
        )
        XCTAssertEqual(stalePhase, .lastRecorded)

        let interruptedPhase = EventAtlasHeadline11666.resolvePhase(
            event: liveEvent,
            observedAt: observed,
            liveStatus: .interrupted,
            now: observed.addingTimeInterval(2 * 60)
        )
        XCTAssertEqual(interruptedPhase, .lastRecorded)
    }

    // MARK: - Page & phase label gating

    func testHeadlineWiringIsGatedByReleaseSurfaces() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        let page = try String(
            contentsOf: root.appendingPathComponent("Views/EventDetailView.swift"),
            encoding: .utf8
        )
        let phaseFile = try String(
            contentsOf: root.appendingPathComponent("Components/EventHeadlinePhase9483.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(page.contains("if ReleaseSurfaces.isEventPageAtlasEnabled() {"))
        XCTAssertTrue(page.contains("EventAtlasHeadlineControlRow11666("))
        XCTAssertTrue(phaseFile.contains("if ReleaseSurfaces.isEventPageAtlasEnabled() {"))
        XCTAssertTrue(phaseFile.contains("EventAtlasPregameMarkView11666(text: baseline)"))
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }
}
