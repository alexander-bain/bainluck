import XCTest
@testable import Bain_Luck

/// #11666 Step E6a — Native Event-page Atlas MLB story cards (`baseball_mlb`),
/// mark-grammar keys, shared details sheet models, and extra-innings multi-source
/// withholding behind `ReleaseSurfaces.isEventPageAtlasEnabled()`.
final class EventAtlasMlbCardsE6a_11666Tests: XCTestCase {

    func testGatesMlbAtlasCardsStrictlyOnAtlasEnabledAndBaseballMlb() {
        XCTAssertFalse(EventAtlasMlbCards11666.applies(sportKey: "baseball_mlb", atlasEnabled: false))
        XCTAssertTrue(EventAtlasMlbCards11666.applies(sportKey: "baseball_mlb", atlasEnabled: true))
        XCTAssertFalse(EventAtlasMlbCards11666.applies(sportKey: "americanfootball_nfl", atlasEnabled: true))
        XCTAssertFalse(EventAtlasMlbCards11666.applies(sportKey: nil, atlasEnabled: true))
    }

    func testVerdictLabelUsesAtlasVocabularyOnlyWhenEnabled() {
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.won, atlasEnabled: false), "Won")
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.lost, atlasEnabled: false), "Lost")

        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.won, atlasEnabled: true), "✓ Won")
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.lost, atlasEnabled: true), "✗ Lost")
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.open, atlasEnabled: true), "Open")
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.pending, atlasEnabled: true), "Pending")
        XCTAssertEqual(EventAtlasMlbCards11666.verdictLabel(.notConfirmed, atlasEnabled: true), "Not confirmed")
    }

    func testBuildsMarkGrammarKeysAndDetailsSheetModelsForMlbStoryCards() throws {
        let original = MLBOriginal11284(
            id: "mlb-o:15330459:after:q:edman|hr|1",
            title: "Tommy Edman · 1+ home runs",
            sections: [
                .init(
                    title: "Before first pitch",
                    fields: [
                        .init(label: "Saved pregame chance", value: "9%"),
                        .init(label: "Saved", value: "Oct 19, 4:55 PM PT"),
                        .init(label: "Venue", value: "Kalshi"),
                    ]
                ),
                .init(
                    title: "After the final",
                    fields: [
                        .init(label: "Official final", value: "1 home run"),
                        .init(label: "Against 1+", value: "Reached 1+"),
                        .init(label: "Venue settlement", value: "Won"),
                    ]
                ),
            ]
        )

        let hrCard = MLBHomeRunCard11284(
            eventID: 15330459,
            story: .homered,
            entries: [
                .init(
                    questionKey: "q:edman|hr|1",
                    player: "Tommy Edman",
                    saved: 0.09,
                    finalCount: 1,
                    side: .home,
                    original: original
                )
            ]
        )
        let wrapped = MLBFinalCard11284.homeRuns(hrCard)
        let keyItems = EventAtlasMlbCards11666.markKey(for: wrapped)
        XCTAssertEqual(keyItems.map(\.label), ["Pregame", "Official final", "✓ Won"])

        // When Venue settlement is Pending (market still open after the game), markKey never mints "✓ Won" from finalCount >= 1
        let pendingOriginal = MLBOriginal11284(
            id: "mlb-o:15330459:after:q:edman|hr|1",
            title: "Tommy Edman · 1+ home runs",
            sections: [
                .init(
                    title: "After the final",
                    fields: [
                        .init(label: "Official final", value: "1 home run"),
                        .init(label: "Venue settlement", value: "Pending"),
                    ]
                )
            ]
        )
        let pendingHrCard = MLBHomeRunCard11284(
            eventID: 15330459,
            story: .homered,
            entries: [
                .init(
                    questionKey: "q:edman|hr|1",
                    player: "Tommy Edman",
                    saved: 0.09,
                    finalCount: 1,
                    side: .home,
                    original: pendingOriginal
                )
            ]
        )
        let pendingKeyItems = EventAtlasMlbCards11666.markKey(for: .homeRuns(pendingHrCard))
        XCTAssertEqual(pendingKeyItems.map(\.label), ["Pregame", "Official final"])

        let details = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: original.id,
                cards: [.mlb(wrapped)],
                rows: [:],
                awayName: "Brewers",
                homeName: "Dodgers"
            )
        )
        XCTAssertEqual(details.id, original.id)
        XCTAssertEqual(details.marketTitle, "Tommy Edman · 1+ home runs")
        XCTAssertEqual(details.primaryReadingLabel, "Result")
        XCTAssertEqual(details.primaryReadingValue, "✓ Won · 1 home run")
        XCTAssertEqual(details.pregameBaseline, "9%")
        XCTAssertEqual(details.observedAtText, "Oct 19, 4:55 PM PT")
        XCTAssertEqual(details.statusSummary, "Reached 1+")
        XCTAssertEqual(details.sourceLabel, "Kalshi")
    }

    func testExtraInningsUsesSingleVenueOrBlendedPregameMarkAndWithholdsUnblendedMultiSource() throws {
        let now = try XCTUnwrap("2026-10-20T03:30:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Single source with pregame_mark and settled winner -> keeps pregameChance and grades .won
        let singleRowsJSON = """
        [
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "Yes",
                "probability": 0.01,
                "pregame_mark": 0.11,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": false,
                "resolution_source": "kalshi"
            },
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "No",
                "probability": 0.99,
                "pregame_mark": 0.89,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "kalshi"
            }
        ]
        """
        let singleRows = try decoder.decode([GameMarketOther].self, from: Data(singleRowsJSON.utf8))
        let singleEntries = EventAtlasMlbCards11666.buildExtraInningsEntries(
            rows: singleRows,
            finished: true,
            isBefore: false,
            now: now
        )
        XCTAssertEqual(singleEntries.count, 2)
        XCTAssertEqual(singleEntries[0].label, "Yes")
        XCTAssertEqual(singleEntries[0].pregameChance ?? 0, 0.11, accuracy: 1e-6)
        XCTAssertEqual(singleEntries[0].venueResult, .notConfirmed, "Non-winning other row follows #11284 MLBVenueResult11284.venue (.notConfirmed)")
        XCTAssertEqual(singleEntries[1].label, "No")
        XCTAssertEqual(singleEntries[1].pregameChance ?? 0, 0.89, accuracy: 1e-6)
        XCTAssertEqual(singleEntries[1].venueResult, .won)

        // 2. Multiple unblended sources without a blended row -> withholds pregameChance (never averages)
        // and conflicting venue grades -> .pending
        let multiUnblendedJSON = """
        [
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "Yes",
                "probability": 0.10,
                "pregame_mark": 0.10,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "kalshi"
            },
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "Yes",
                "probability": 0.14,
                "pregame_mark": 0.14,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "polymarket",
                "is_winner": false,
                "resolution_source": "polymarket"
            },
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "No",
                "probability": 0.90,
                "pregame_mark": 0.90,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "kalshi"
            }
        ]
        """
        let multiRows = try decoder.decode([GameMarketOther].self, from: Data(multiUnblendedJSON.utf8))
        let multiEntries = EventAtlasMlbCards11666.buildExtraInningsEntries(
            rows: multiRows,
            finished: true,
            isBefore: false,
            now: now
        )
        XCTAssertEqual(multiEntries.count, 2)
        XCTAssertNil(multiEntries[0].pregameChance, "Unblended multi-source pregameChance must be withheld, never averaged")
        XCTAssertNil(multiEntries[0].source)
        XCTAssertEqual(multiEntries[0].sourceCount, 2)
        XCTAssertEqual(multiEntries[0].venueResult, .pending, "Disagreeing venue verdicts must show Pending")
    }

    func testWiresMlbAtlasMarkKeyAndDetailsInMLBFinalCardsAndStoryCards() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")

        let mlbCardsSource = try String(
            contentsOf: root.appendingPathComponent("Components/MLBFinalCards11284.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(mlbCardsSource.contains("EventAtlasMlbCards11666.markKey(for: card)"))
        XCTAssertTrue(mlbCardsSource.contains("EventAtlasMlbCards11666.verdictLabel("))

        let storyCardsSource = try String(
            contentsOf: root.appendingPathComponent("Components/EventAtlasStoryCards11666.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(storyCardsSource.contains("EventAtlasMlbCards11666.detailsModel(for: mlbOriginal)"))

        let mlbReaderSource = try String(
            contentsOf: root.appendingPathComponent("Utilities/MLBFinalReader11284.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(mlbReaderSource.contains("EventAtlasMlbCards11666.buildExtraInningsEntries("))

        let cardReaderSource = try String(
            contentsOf: root.appendingPathComponent("Components/NFLCardReader9483.swift"),
            encoding: .utf8
        )
        let atlasRange = try XCTUnwrap(cardReaderSource.range(of: "EventAtlasStoryCards11666.readerDetailsModel("))
        let legacyMlbRange = try XCTUnwrap(cardReaderSource.range(of: "MLBFinalDeck11284.original("))
        XCTAssertLessThan(
            atlasRange.lowerBound,
            legacyMlbRange.lowerBound,
            "Atlas readerDetailsModel branch must precede legacy MLBOriginalDetails11284 branch in NFLCardReader9483"
        )
    }
}
