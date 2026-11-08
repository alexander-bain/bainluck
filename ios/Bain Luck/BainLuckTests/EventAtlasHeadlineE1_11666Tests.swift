import XCTest
import SwiftUI
import UIKit
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
        XCTAssertEqual(sheet.observedAtText?.hasSuffix(" PT"), true)

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
            liveStatus: .hidden,
            now: now
        )
        XCTAssertEqual(settledSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(settledSheet.primaryReadingValue, "Chiefs Won")
        XCTAssertEqual(settledSheet.pregameBaseline, "Pre-match 38% – 62%")
        XCTAssertEqual(settledSheet.sourceLabel, "Kalshi")
        XCTAssertEqual(settledSheet.observedAtText?.hasSuffix(" PT"), true)
        XCTAssertNil(settledSheet.statusSummary)

        // Settled event with multi-source win_probability_sources from during the game
        // attributes its single-rung pregame baseline to Sportsbooks, never "Blended (...)".
        let settledMultiSourceEvent = try decode(
            EventDetail.self,
            """
            {
              "id": 15341807,
              "sport": "americanfootball_nfl",
              "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "status": "completed",
              "home_score": 27,
              "away_score": 24,
              "hero_settled_result": "home",
              "hero_probability_source": "blend",
              "prematch_odds": {"home_probability": 0.62, "away_probability": 0.38},
              "win_probability_sources": {
                "betting": {"value": 1.0, "display_name": "Sportsbooks"},
                "kalshi": {"value": 1.0, "display_name": "Kalshi"}
              }
            }
            """
        )
        let settledMultiSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: settledMultiSourceEvent,
            phase: nil,
            observedAt: now,
            liveStatus: .hidden,
            now: now
        )
        XCTAssertEqual(settledMultiSheet.sourceLabel, "Sportsbooks")

        // Embedded hero visibility deduplicates phase, live mark, EKG, and (i) on live games,
        // while keeping the settled hollow pregame mark and single (i) on settled games.
        let liveVis = EventAtlasHeadlineControlRow11666.embeddedHeroVisibility(event: liveEvent, now: now)
        XCTAssertFalse(liveVis.showsPhaseAndLiveMark)
        XCTAssertFalse(liveVis.showsEkg)
        XCTAssertFalse(liveVis.showsDetailsButton)

        let settledVis = EventAtlasHeadlineControlRow11666.embeddedHeroVisibility(event: settledEvent, now: now)
        XCTAssertFalse(settledVis.showsSettledWinner)
        XCTAssertTrue(settledVis.showsSettledMark)
        XCTAssertFalse(settledVis.showsEkg)
        XCTAssertTrue(settledVis.showsDetailsButton)
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
        XCTAssertTrue(page.contains("embeddedInHero: true)"))
        XCTAssertTrue(page.contains("if !ReleaseSurfaces.isEventPageAtlasEnabled(),"))
        XCTAssertTrue(phaseFile.contains("if ReleaseSurfaces.isEventPageAtlasEnabled() {"))
        XCTAssertTrue(phaseFile.contains("EventAtlasPregameMarkView11666(text: baseline)"))
    }

    @MainActor
    func testRendersDeduplicatedHeroStatesAt390Width() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
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
        let settledEvent = try decode(
            EventDetail.self,
            """
            {
              "id": 15341807,
              "sport": "americanfootball_nfl",
              "home_team": "Kansas City Chiefs",
              "away_team": "Buffalo Bills",
              "status": "completed",
              "home_score": 27,
              "away_score": 24,
              "hero_settled_result": "home",
              "hero_probability_source": "blend",
              "prematch_odds": {"home_probability": 0.62, "away_probability": 0.38},
              "win_probability_sources": {
                "betting": {"value": 1.0, "display_name": "Sportsbooks"},
                "kalshi": {"value": 1.0, "display_name": "Kalshi"}
              }
            }
            """
        )

        let liveHero = VStack(spacing: 8) {
            HStack {
                Text("Buffalo Bills")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text("10 – 14")
                    .font(.title3.weight(.bold).monospacedDigit())
                Spacer()
                Text("Kansas City Chiefs")
                    .font(.subheadline.weight(.semibold))
            }
            HStack(spacing: 6) {
                Circle().fill(Color.green).frame(width: 6, height: 6)
                Text("35.8% – 64.2%")
                    .font(.title2.weight(.bold).monospacedDigit())
                Image(systemName: "info.circle")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            EventHeadlinePhaseLabel9483(
                phase: .current,
                baseline: "Pre-match 45% – 55%",
                maxWidth: nil
            )
            EventAtlasHeadlineControlRow11666(
                event: liveEvent,
                observedAt: now.addingTimeInterval(-120),
                liveStatus: .live,
                asOf: now,
                embeddedInHero: true
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let settledHero = VStack(spacing: 8) {
            HStack {
                Text("Buffalo Bills")
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Text("24 – 27")
                    .font(.title3.weight(.bold).monospacedDigit())
                Spacer()
                Text("Kansas City Chiefs")
                    .font(.subheadline.weight(.semibold))
            }
            Label("Chiefs Win", systemImage: "checkmark.circle.fill")
                .font(.headline)
                .foregroundStyle(.green)
            EventAtlasHeadlineControlRow11666(
                event: settledEvent,
                observedAt: now,
                liveStatus: .hidden,
                asOf: now,
                embeddedInHero: true
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let settledSheetModel = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: settledEvent,
            phase: nil,
            observedAt: now,
            liveStatus: .hidden,
            now: now
        )
        let settledDetailsPreview = VStack(alignment: .leading, spacing: 10) {
            Text(settledSheetModel.outcomeTitle)
                .font(.headline)
            Text(settledSheetModel.marketTitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Divider()
            HStack {
                Text(settledSheetModel.primaryReadingLabel)
                Spacer()
                Text(settledSheetModel.primaryReadingValue)
                    .foregroundStyle(.secondary)
            }
            if let pregame = settledSheetModel.pregameBaseline {
                HStack {
                    Text("Pregame baseline")
                    Spacer()
                    EventAtlasPregameMarkView11666(text: pregame)
                }
            }
            if let source = settledSheetModel.sourceLabel {
                HStack {
                    Text("Source")
                    Spacer()
                    Text(source)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .font(.subheadline)
        .padding(16)
        .frame(width: 390)
        .background(Color(.systemBackground))
        .environment(\.colorScheme, .light)

        let r1 = rendererForMeasurement(liveHero)
        r1.scale = 2.0
        let img1 = try XCTUnwrap(r1.uiImage)
        let png1 = try XCTUnwrap(img1.pngData())
        XCTAssertEqual(Int(img1.size.width), 390)
        XCTAssertGreaterThanOrEqual(Int(img1.size.height), 60)
        XCTAssertTrue(Self.hasNonWhiteInk(img1), "live hero render must contain visible non-white ink")

        let r2 = rendererForMeasurement(settledHero)
        r2.scale = 2.0
        let img2 = try XCTUnwrap(r2.uiImage)
        let png2 = try XCTUnwrap(img2.pngData())
        XCTAssertEqual(Int(img2.size.width), 390)
        XCTAssertGreaterThanOrEqual(Int(img2.size.height), 60)
        XCTAssertTrue(Self.hasNonWhiteInk(img2), "settled hero render must contain visible non-white ink")

        let r3 = rendererForMeasurement(settledDetailsPreview)
        r3.scale = 2.0
        let img3 = try XCTUnwrap(r3.uiImage)
        let png3 = try XCTUnwrap(img3.pngData())
        XCTAssertEqual(Int(img3.size.width), 390)
        XCTAssertGreaterThanOrEqual(Int(img3.size.height), 100)
        XCTAssertTrue(Self.hasNonWhiteInk(img3), "settled details render must contain visible non-white ink")

        if let outDir = ProcessInfo.processInfo.environment["ATLAS_E1_E5_HERO_SCREENSHOT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try png1.write(to: dirURL.appendingPathComponent("e1-e5-hero-live-390px.png"))
            try png2.write(to: dirURL.appendingPathComponent("e1-e5-hero-settled-390px.png"))
            try png3.write(to: dirURL.appendingPathComponent("e1-e5-hero-details-sheet-390px.png"))
        }
    }

    private static func hasNonWhiteInk(_ image: UIImage) -> Bool {
        guard let cgImage = image.cgImage,
              let data = cgImage.dataProvider?.data,
              let ptr = CFDataGetBytePtr(data) else {
            return false
        }
        let length = CFDataGetLength(data)
        var nonWhiteSamples = 0
        for idx in stride(from: 0, to: length - 3, by: 4) {
            if ptr[idx] < 245 || ptr[idx + 1] < 245 || ptr[idx + 2] < 245 {
                nonWhiteSamples += 1
                if nonWhiteSamples > 100 {
                    return true
                }
            }
        }
        return false
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }
}
