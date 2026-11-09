import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class EventAtlasRacingCards11666Tests: XCTestCase {
    private typealias F = RacingAdapterFixtures10868
    private typealias P = RacingWinPodiumFixtures10868

    func testAppliesOnlyForMutuallyExclusiveMotorsportMarketsWhenAtlasEnabled() throws {
        let winnerMarket = try F.market(F.winnerBefore)
        XCTAssertTrue(EventAtlasRacingCards11666.applies(market: winnerMarket, atlasEnabled: true))
        XCTAssertFalse(EventAtlasRacingCards11666.applies(market: winnerMarket, atlasEnabled: false))

        let podiumMarket = try F.market(F.podiumBefore)
        XCTAssertFalse(
            EventAtlasRacingCards11666.applies(market: podiumMarket, atlasEnabled: true),
            "Non-mutually-exclusive podium field does not mount the race winner card deck on its own"
        )

        let hockeyMarket = try F.market(F.ladderDetail)
        XCTAssertFalse(EventAtlasRacingCards11666.applies(market: hockeyMarket, atlasEnabled: true))

        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "f1", atlasEnabled: true))
        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "formula_1", atlasEnabled: true))
        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "motorsports", atlasEnabled: true))
        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "nascar_cup", atlasEnabled: true))
        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "indycar", atlasEnabled: true))
        XCTAssertTrue(EventAtlasRacingCards11666.applies(sportSub: "motogp", atlasEnabled: true))
        XCTAssertFalse(EventAtlasRacingCards11666.applies(sportSub: "basketball_nba", atlasEnabled: true))
    }

    func testBuildOutlookAndChooserInputsBeforeAndAfterSettlement() throws {
        let marketBefore = try F.market(F.winnerBefore)
        let hostBefore = F.host(F.beforeCapture)

        let outlookBefore = EventAtlasRacingCards11666.buildOutlookInput(
            market: marketBefore,
            selectedOutcomeID: F.hamilton,
            host: hostBefore
        )
        XCTAssertEqual(outlookBefore.phase, .before)
        XCTAssertEqual(outlookBefore.displayed.count, 4)
        XCTAssertEqual(outlookBefore.displayed.map(\.shortLabel), ["Verstappen", "Hamilton", "Leclerc", "Antonelli"])
        XCTAssertEqual(outlookBefore.selected?.ref.outcomeID, String(F.hamilton))
        XCTAssertEqual(outlookBefore.chances.count, 4)
        XCTAssertEqual(outlookBefore.scale.ceiling, 0.75, accuracy: 0.0001)
        XCTAssertEqual(outlookBefore.copy.title, "Driver win chances")
        XCTAssertEqual(outlookBefore.copy.note, "4 drivers")

        let chooserBefore = EventAtlasRacingCards11666.buildChooserInput(
            market: marketBefore,
            selectedOutcomeID: F.leclerc,
            moreExpanded: true,
            browseExpanded: true,
            selectedSurnameGroup: .gToL,
            host: hostBefore
        )
        XCTAssertEqual(chooserBefore.featured.refs.map(\.outcomeID), [String(F.verstappen), String(F.hamilton)])
        XCTAssertEqual(chooserBefore.more?.refs.map(\.outcomeID), [String(F.leclerc), String(F.antonelli)])
        XCTAssertEqual(chooserBefore.more?.expanded, true)
        XCTAssertEqual(chooserBefore.browse?.selectedGroupID, "g-l")
        XCTAssertEqual(
            chooserBefore.browse?.groups.map(\.label),
            ["A–F", "G–L", "S–Z"],
            "Antonelli -> A–F, Hamilton & Leclerc -> G–L, Verstappen -> S–Z"
        )

        let detailsBefore = try XCTUnwrap(
            EventAtlasRacingCards11666.buildDriverDetails(
                ref: outlookBefore.displayed[0].ref,
                market: marketBefore,
                host: hostBefore
            )
        )
        XCTAssertEqual(detailsBefore.driverName, "Max Verstappen")
        XCTAssertEqual(detailsBefore.readingLabel, "Win chance")
        XCTAssertEqual(detailsBefore.readingValue, "62%")
        XCTAssertTrue(detailsBefore.readingDetail?.contains("Polymarket") == true)
        XCTAssertNil(detailsBefore.resultWords)

        // Settled market grades outcomes without showing 100% / 0% as live chances
        let marketFinal = try F.market(F.winnerFinal)
        let hostFinal = F.host(F.finalCapture)
        let outlookFinal = EventAtlasRacingCards11666.buildOutlookInput(
            market: marketFinal,
            host: hostFinal
        )
        XCTAssertEqual(outlookFinal.phase, .final)
        XCTAssertTrue(outlookFinal.chances.isEmpty)
        XCTAssertEqual(outlookFinal.copy.title, "Race winner results")

        let detailsFinal = try XCTUnwrap(
            EventAtlasRacingCards11666.buildDriverDetails(
                ref: outlookFinal.displayed[0].ref,
                market: marketFinal,
                host: hostFinal
            )
        )
        XCTAssertEqual(detailsFinal.driverName, "Max Verstappen")
        XCTAssertEqual(detailsFinal.readingValue, "Pre-race chance unavailable")
        XCTAssertEqual(detailsFinal.resultWords, "Won")
    }

    func testRaceAboutAndWinPodiumAboutContainNoVenueNamesAcrossAllKnownSources() throws {
        let knownSources = [
            "polymarket",
            "kalshi",
            "the_odds_api",
            "betting",
            "espn",
            "stat_model",
            "datagolf",
            "mlb_stats",
            "bovada"
        ]
        let knownVenueLabels = knownSources.compactMap { SourceLabels.label(for: $0) }
        XCTAssertFalse(knownVenueLabels.isEmpty)

        for sourceName in knownSources {
            let openWinnerJSON = F.replacing(F.winnerBefore, #""source":"polymarket""#, with: #""source":"\#(sourceName)""#)
            let finalWinnerJSON = F.replacing(F.winnerFinal, #""source":"polymarket""#, with: #""source":"\#(sourceName)""#)
            let openPodiumJSON = F.replacing(P.podiumBeforePaired, #""source":"polymarket""#, with: #""source":"\#(sourceName)""#)

            let openWinner = try F.market(openWinnerJSON)
            let finalWinner = try F.market(finalWinnerJSON)
            let openPodium = try F.market(openPodiumJSON)

            let openAbout = RacingFieldPageAdapter10868.raceAbout(openWinner)
            let finalAbout = RacingFieldPageAdapter10868.raceAbout(finalWinner)
            let podiumAbout = RacingWinPodiumAdapter10868.about(race: openWinner, podium: openPodium)

            let allParagraphs = openAbout.paragraphs + finalAbout.paragraphs + podiumAbout.paragraphs
            for paragraph in allParagraphs {
                for venueLabel in knownVenueLabels {
                    XCTAssertFalse(
                        paragraph.localizedCaseInsensitiveContains(venueLabel),
                        "About prose for source \(sourceName) must not contain venue name '\(venueLabel)': \(paragraph)"
                    )
                }
            }
        }
    }

    func testRenders390pxSnapshotDefaultAndAccessibility3() throws {
        let market = try F.market(F.winnerBefore)
        let podiumMarket = try F.market(P.podiumBeforePaired)
        let podium = RacingWinPodiumAdapter10868.Podium(
            market: podiumMarket,
            join: RacingWinPodiumAdapter10868.Join(
                winnerMarketID: P.winnerMarket,
                podiumMarketID: P.podiumMarket,
                outcomes: P.join
            )
        )
        let captureNow = try XCTUnwrap(F.beforeCapture.asDate)

        let defaultView = VStack(alignment: .leading, spacing: 16) {
            EventAtlasRacingSectionView11666(
                market: market,
                podium: podium,
                now: captureNow
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(DS.cardBg)
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, .large)

        let defaultRenderer = rendererForMeasurement(defaultView)
        defaultRenderer.scale = 2.0
        let defaultImage = try XCTUnwrap(defaultRenderer.uiImage)
        XCTAssertEqual(defaultImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(defaultImage.size.height, 600)

        let a11yView = VStack(alignment: .leading, spacing: 16) {
            EventAtlasRacingSectionView11666(
                market: market,
                podium: podium,
                now: captureNow
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(DS.cardBg)
        .environment(\.colorScheme, .light)
        .environment(\.dynamicTypeSize, .accessibility3)

        let a11yRenderer = rendererForMeasurement(a11yView)
        a11yRenderer.scale = 1.0
        let a11yImage = try XCTUnwrap(a11yRenderer.uiImage)
        XCTAssertEqual(a11yImage.size.width, 390, accuracy: 1.0)
        XCTAssertGreaterThan(a11yImage.size.height, defaultImage.size.height)
        XCTAssertNotNil(a11yImage.pngData())

        if let outDir = ProcessInfo.processInfo.environment["RACING_SNAPSHOT_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            if let png = defaultImage.pngData() {
                try png.write(to: dirURL.appendingPathComponent("racing-story-cards-default-390px.png"))
            }
            if let png = a11yImage.pngData() {
                try png.write(to: dirURL.appendingPathComponent("racing-story-cards-a11y-390px.png"))
            }
        }
    }
}
