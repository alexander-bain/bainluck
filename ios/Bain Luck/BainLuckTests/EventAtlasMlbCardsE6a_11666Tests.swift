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
        XCTAssertEqual(details.statusLabel, "Comparison")
        XCTAssertEqual(details.sourceLabel, "Kalshi")
        XCTAssertEqual(details.originalSections.count, 2)

        // Strikeout target original ("Pregame mark · Over") preserves pregameBaseline,
        // Pending venue result, and all frozen original sections (Over, Under, count).
        let strikeoutOriginal = MLBOriginal11284(
            id: "mlb-o:15330459:target:glasnow-7+",
            title: "Tyler Glasnow · 7+ strikeouts",
            sections: [
                .init(
                    title: "Over · Tyler Glasnow: Strikeouts O/U 6.5",
                    fields: [
                        .init(label: "Original side", value: "Over"),
                        .init(label: "Line", value: "6.5"),
                        .init(label: "Venue", value: "Kalshi"),
                        .init(label: "Pregame mark · Over", value: "58%"),
                        .init(label: "Venue result", value: "Pending"),
                    ]
                ),
                .init(
                    title: "Under · Tyler Glasnow: Strikeouts O/U 6.5",
                    fields: [
                        .init(label: "Original side", value: "Under"),
                    ]
                ),
                .init(
                    title: "7+ strikeouts",
                    fields: [
                        .init(label: "Official final", value: "Unavailable"),
                        .init(label: "Against 7+", value: "Final result unavailable"),
                    ]
                ),
            ]
        )
        let strikeoutDetails = EventAtlasMlbCards11666.detailsModel(for: strikeoutOriginal)
        XCTAssertEqual(strikeoutDetails.pregameBaseline, "58%")
        XCTAssertEqual(strikeoutDetails.primaryReadingLabel, "Venue result")
        XCTAssertEqual(strikeoutDetails.primaryReadingValue, "Pending")
        XCTAssertEqual(strikeoutDetails.statusLabel, "Comparison")
        XCTAssertEqual(strikeoutDetails.originalSections.count, 3)

        // Extra-innings markKey says "✓ Won" (never "✓ Won / ✗ Lost", since ✗ Lost cannot occur under #11284)
        let extraCard = MLBExtraInningsCard11284(
            eventID: 15330459,
            outcomes: [
                .init(
                    label: "Yes",
                    venue: "Kalshi",
                    venueResult: .notConfirmed,
                    original: original,
                    pregameChance: 0.11
                ),
                .init(
                    label: "No",
                    venue: "Kalshi",
                    venueResult: .won,
                    original: original,
                    pregameChance: 0.89
                ),
            ]
        )
        let extraKeyItems = EventAtlasMlbCards11666.markKey(for: .extraInnings(extraCard))
        XCTAssertEqual(extraKeyItems.map(\.label), ["Pregame", "✓ Won"])
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
                "resolution_source": "api_settlement"
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
        // and conflicting venue grades -> .pending, while case variants ("no", "YES") canonicalize and sort Yes first.
        let multiUnblendedJSON = """
        [
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "no",
                "probability": 0.90,
                "pregame_mark": 0.90,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "api_settlement"
            },
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "YES",
                "probability": 0.10,
                "pregame_mark": 0.10,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "kalshi",
                "is_winner": true,
                "resolution_source": "api_settlement"
            },
            {
                "market_name": "MIL at LAD: Extra Innings",
                "outcome_name": "yes",
                "probability": 0.14,
                "pregame_mark": 0.14,
                "observed_at": "2026-10-20T03:25:00Z",
                "source": "polymarket",
                "is_winner": false,
                "resolution_source": "clob_authoritative"
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
        XCTAssertEqual(multiEntries.map(\.label), ["Yes", "No"])
        XCTAssertEqual(multiEntries.map(\.id), ["mlb-extra:yes", "mlb-extra:no"])
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

    @MainActor
    func testExtraInningsCardBuildsAndRoutesMultiSourceAttributionThroughReaderDetailsModel() throws {
        let now = try XCTUnwrap("2026-10-26T04:00:00Z".asDate)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let unblendedJSON = """
        [
            {"_market_id": 980, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "Yes", "probability": 0.01, "pregame_mark": 0.11, "observed_at": "2026-10-25T23:50:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement"},
            {"_market_id": 981, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "Yes", "probability": 0.01, "pregame_mark": 0.14, "observed_at": "2026-10-25T23:50:00Z", "source": "polymarket", "is_winner": false, "resolution_source": "clob_authoritative"},
            {"_market_id": 980, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "No", "probability": 0.99, "pregame_mark": 0.88, "observed_at": "2026-10-25T23:50:00Z", "source": "blended", "is_winner": true, "resolution_source": "api_settlement"},
            {"_market_id": 981, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "No", "probability": 0.99, "pregame_mark": 0.86, "observed_at": "2026-10-25T23:50:00Z", "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement"}
        ]
        """
        let rows = try decoder.decode([GameMarketOther].self, from: Data(unblendedJSON.utf8))
        let extraCard = try XCTUnwrap(MLBExtraInningsCard11284.build(rows, eventID: 9901, now: now))
        let cards: [NFLEventCard9483] = [.mlb(.extraInnings(extraCard))]

        let yesOutcome = try XCTUnwrap(extraCard.outcomes.first(where: { $0.label == "Yes" }))
        let yesSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: yesOutcome.id,
                cards: cards,
                rows: [:],
                awayName: "Yankees",
                homeName: "Dodgers"
            )
        )
        XCTAssertEqual(yesSheet.outcomeTitle, "Yes")
        XCTAssertEqual(yesSheet.sourceLabel, "2 sources, not blended")

        let noOutcome = try XCTUnwrap(extraCard.outcomes.first(where: { $0.label == "No" }))
        let noSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: noOutcome.id,
                cards: cards,
                rows: [:],
                awayName: "Yankees",
                homeName: "Dodgers"
            )
        )
        XCTAssertEqual(noSheet.outcomeTitle, "No")
        XCTAssertEqual(noSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(noSheet.primaryReadingValue, EventAtlasStates11666.wonWithCheck)
        XCTAssertEqual(noSheet.pregameBaseline, "88%")
        XCTAssertEqual(noSheet.sourceLabel, "Blended (2 sources)")

        // Single-source ("kalshi" -> "Kalshi") and unknown-source ("unknown_provider" -> nil)
        let singleAndUnknownJSON = """
        [
            {"_market_id": 990, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "Yes", "probability": 0.01, "pregame_mark": 0.12, "observed_at": "2026-10-25T23:50:00Z", "source": "kalshi", "is_winner": false, "resolution_source": "api_settlement"},
            {"_market_id": 990, "market_name": "NYY at LAD: Extra Innings", "outcome_name": "No", "probability": 0.99, "pregame_mark": 0.88, "observed_at": "2026-10-25T23:50:00Z", "source": "unknown_provider", "is_winner": true, "resolution_source": "api_settlement"}
        ]
        """
        let singleRows = try decoder.decode([GameMarketOther].self, from: Data(singleAndUnknownJSON.utf8))
        let singleCard = try XCTUnwrap(MLBExtraInningsCard11284.build(singleRows, eventID: 9902, now: now))
        let singleCards: [NFLEventCard9483] = [.mlb(.extraInnings(singleCard))]

        let singleYes = try XCTUnwrap(singleCard.outcomes.first(where: { $0.label == "Yes" }))
        let singleYesSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: singleYes.id,
                cards: singleCards,
                rows: [:],
                awayName: "Yankees",
                homeName: "Dodgers"
            )
        )
        XCTAssertEqual(singleYesSheet.sourceLabel, "Kalshi")

        let unknownNo = try XCTUnwrap(singleCard.outcomes.first(where: { $0.label == "No" }))
        let unknownNoSheet = try XCTUnwrap(
            EventAtlasStoryCards11666.readerDetailsModel(
                rowID: unknownNo.id,
                cards: singleCards,
                rows: [:],
                awayName: "Yankees",
                homeName: "Dodgers"
            )
        )
        XCTAssertNil(unknownNoSheet.sourceLabel, "Unknown source with sourceCount == 1 must omit Venue and return nil sourceLabel")
    }
}
