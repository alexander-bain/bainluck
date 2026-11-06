import XCTest
@testable import Bain_Luck

/// #11666 (Step E1) — Native event-page atlas headline and shared details sheet
/// behind `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasHeadlineE1_11666Tests: XCTestCase {

    // MARK: - Build flag & launch override

    func testBuildFlagDefaultsOffAndHonoursLaunchOverride() {
        XCTAssertFalse(
            ReleaseSurfaces.eventPageAtlasEnabled,
            "the shipping switch stays off until Alex's phone look"
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

    func testSettledUnderdogWinnerFlagsUpsetBelow45Percent() throws {
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
